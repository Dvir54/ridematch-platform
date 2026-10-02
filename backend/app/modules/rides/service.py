"""Ride logic: the lifecycle of CONTRACT.md §3 and the rules of §4.

`RideRequest` rows are read and cascaded here — seat arithmetic, and the auto-rejections when a
ride is cancelled or started. The requests *service* is never called from here, so the dependency
between the two modules still points one way.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import Conflict, Forbidden, NotFound, UnprocessableEntity
from app.modules.notifications import service as notifications_service
from app.modules.notifications.service import EmailContent
from app.modules.requests.models import BLOCKING_REQUEST_STATUSES, RideRequest
from app.modules.rides.models import OPEN_RIDE_STATUSES, Ride
from app.modules.rides.schemas import (
    LOCKED_FIELDS,
    PLAIN_FIELDS,
    MyRequest,
    RideCreate,
    RidePreferences,
    RidePreferencesPatch,
    RideUpdate,
)
from app.modules.users.models import User

#: A driver may start a ride from this long before `departure_time` (CONTRACT.md §3, D7).
EARLIEST_START = timedelta(hours=2)
#: Request statuses a ride still holds; these are cascaded when the ride ends early.
ACTIVE_REQUEST_STATUSES = ("pending", "approved")


def describe_ride(ride: Ride) -> str:
    """The phrase every notification is built around: `from A to B on 2026-10-05 08:30 UTC`."""
    when = ride.departure_time.astimezone(UTC)
    return f"from {ride.start_address} to {ride.end_address} on {when:%Y-%m-%d %H:%M} UTC"


def merge_preferences(stored: dict | None, patch: RidePreferencesPatch | None) -> dict:
    """Defaults, then what is stored, then the keys the client just sent (CONTRACT.md D16)."""
    merged = RidePreferences().model_dump(mode="json")
    merged.update(stored or {})
    if patch is not None:
        # Every key is a non-nullable boolean, so what was sent is what should land.
        merged.update(patch.model_dump(mode="json", exclude_unset=True))
    return merged


# ── reads ────────────────────────────────────────────────────────────


async def get_ride_or_404(db: AsyncSession, ride_id: int) -> Ride:
    stmt = select(Ride).where(Ride.id == ride_id).execution_options(populate_existing=True)
    ride = (await db.execute(stmt)).scalar_one_or_none()
    if ride is None:
        raise NotFound("NOT_FOUND", "Ride not found.")
    return ride


async def lock_ride(db: AsyncSession, ride_id: int) -> None:
    """`SELECT … FOR UPDATE` on the ride row, so seat changes serialise (CONTRACT.md §4 Rides).

    Only the id is selected: the caller re-reads the ride through the ORM afterwards and, holding
    the lock, is then its only writer.
    """
    await db.execute(select(Ride.id).where(Ride.id == ride_id).with_for_update())


def require_driver(ride: Ride, user: User) -> None:
    if ride.driver_id != user.id:
        raise Forbidden("FORBIDDEN", "This ride belongs to another driver.")


async def load_ride_for_update(db: AsyncSession, ride_id: int, driver: User) -> Ride:
    """The driver's own ride, locked — how every mutating ride operation starts."""
    await lock_ride(db, ride_id)
    ride = await get_ride_or_404(db, ride_id)
    require_driver(ride, driver)
    return ride


async def approved_totals(db: AsyncSession, ride_id: int) -> tuple[int, int]:
    """`(number of approved requests, seats they hold)`."""
    stmt = select(func.count(), func.coalesce(func.sum(RideRequest.seats_requested), 0)).where(
        RideRequest.ride_id == ride_id, RideRequest.status == "approved"
    )
    count, seats = (await db.execute(stmt)).one()
    return int(count), int(seats)


async def count_open_rides_for_driver(db: AsyncSession, driver_id: int) -> int:
    """Rides the driver still has `upcoming` or `full` (CONTRACT.md §4 Vehicles)."""
    stmt = (
        select(func.count())
        .select_from(Ride)
        .where(Ride.driver_id == driver_id, Ride.status.in_(OPEN_RIDE_STATUSES))
    )
    return int((await db.execute(stmt)).scalar_one())


@dataclass(frozen=True, slots=True)
class RideViewer:
    """Who is asking, and the per-ride facts that depend on them.

    Both viewer-dependent fields on `Ride` come from the same place: the caller's own blocking
    request. `my_request` *is* that request (CONTRACT.md D20), and an `approved` one is exactly
    what reveals the plate (§4 Vehicles). So one query answers both, and the rule lives once.
    """

    user_id: int
    my_requests: Mapping[int, MyRequest]

    def my_request(self, ride: Ride) -> MyRequest | None:
        return self.my_requests.get(ride.id)

    def plate_visible(self, ride: Ride) -> bool:
        if ride.driver_id == self.user_id:
            return True
        mine = self.my_requests.get(ride.id)
        return mine is not None and mine.status == "approved"


async def viewer_for(db: AsyncSession, rides: Sequence[Ride], user: User) -> RideViewer:
    """Resolve one caller's view of these rides in a single query.

    Call it once per response with every ride that response will serialize, embedded ones
    included, so the cost is one query however long the list is.
    """
    ride_ids = {ride.id for ride in rides}
    if not ride_ids:
        return RideViewer(user_id=user.id, my_requests={})
    # The partial unique index allows at most one row per (ride, passenger) in these statuses,
    # so there is exactly one to report per ride and no "latest" to choose. Columns only, so
    # this doesn't drag the relationships along.
    stmt = select(
        RideRequest.ride_id,
        RideRequest.id,
        RideRequest.status,
        RideRequest.seats_requested,
    ).where(
        RideRequest.ride_id.in_(ride_ids),
        RideRequest.passenger_id == user.id,
        RideRequest.status.in_(BLOCKING_REQUEST_STATUSES),
    )
    mine = {
        ride_id: MyRequest(id=request_id, status=status, seats_requested=seats)
        for ride_id, request_id, status, seats in (await db.execute(stmt)).all()
    }
    return RideViewer(user_id=user.id, my_requests=mine)


async def list_my_rides(
    db: AsyncSession,
    *,
    driver_id: int,
    statuses: tuple[str, ...],
    limit: int,
    offset: int,
) -> list[Ride]:
    stmt = select(Ride).where(Ride.driver_id == driver_id)
    if statuses:
        stmt = stmt.where(Ride.status.in_(statuses))
    stmt = stmt.order_by(Ride.departure_time.asc(), Ride.id.asc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def _requests_in(
    db: AsyncSession, ride_id: int, statuses: tuple[str, ...]
) -> list[RideRequest]:
    stmt = (
        select(RideRequest)
        .where(RideRequest.ride_id == ride_id, RideRequest.status.in_(statuses))
        .order_by(RideRequest.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── notifications (CONTRACT.md §7) ───────────────────────────────────


async def _notify_ride_cancelled(
    db: AsyncSession, settings: Settings, ride: Ride, request: RideRequest, now: datetime
) -> None:
    await notifications_service.notify(
        db,
        settings,
        user_id=request.passenger_id,
        type="ride_cancelled",
        title="Ride cancelled",
        message=f"The ride {describe_ride(ride)} was cancelled by the driver.",
        related_entity_type="ride",
        related_entity_id=ride.id,
        push=notifications_service.websocket_enabled(request.passenger.preferences),
        now=now,
    )


async def _notify_auto_rejected(
    db: AsyncSession, settings: Settings, ride: Ride, request: RideRequest, now: datetime
) -> None:
    """A pending request on a ride that has just started (CONTRACT.md §3 Start)."""
    message = f"The ride {describe_ride(ride)} has started, so your request was declined."
    email = (
        EmailContent(
            to=request.passenger.email,
            subject="Your RideMatch request was declined",
            body=f"Hi {request.passenger.name},\n\n{message}\n\n— RideMatch",
        )
        if notifications_service.email_enabled(request.passenger.preferences)
        else None
    )
    await notifications_service.notify(
        db,
        settings,
        user_id=request.passenger_id,
        type="request_rejected",
        title="Request declined",
        message=message,
        related_entity_type="ride_request",
        related_entity_id=request.id,
        email=email,
        push=notifications_service.websocket_enabled(request.passenger.preferences),
        now=now,
    )


async def _notify_ride_event(
    db: AsyncSession,
    settings: Settings,
    ride: Ride,
    recipient: User,
    *,
    type: str,
    title: str,
    message: str,
    now: datetime,
) -> None:
    await notifications_service.notify(
        db,
        settings,
        user_id=recipient.id,
        type=type,
        title=title,
        message=message,
        related_entity_type="ride",
        related_entity_id=ride.id,
        push=notifications_service.websocket_enabled(recipient.preferences),
        now=now,
    )


# ── writes ───────────────────────────────────────────────────────────


def _departure_in_past() -> UnprocessableEntity:
    return UnprocessableEntity(
        "DEPARTURE_IN_PAST",
        "The departure time must be in the future.",
        details=[{"field": "body.departure_time", "message": "Must be in the future."}],
    )


async def create_ride(db: AsyncSession, *, driver: User, data: RideCreate, now: datetime) -> Ride:
    """A new `upcoming` ride with every seat free. The driver needs a vehicle (CONTRACT.md §4)."""
    if not driver.vehicle:
        raise Conflict("VEHICLE_REQUIRED", "Add your vehicle before offering a ride.")
    if data.departure_time <= now:
        raise _departure_in_past()

    ride = Ride(
        driver_id=driver.id,
        start_lat=data.start_lat,
        start_lng=data.start_lng,
        start_address=data.start_address,
        end_lat=data.end_lat,
        end_lng=data.end_lng,
        end_address=data.end_address,
        departure_time=data.departure_time,
        capacity=data.capacity,
        available_seats=data.capacity,
        price_per_seat=data.price_per_seat,
        status="upcoming",
        preferences=merge_preferences(None, data.preferences),
        notes=data.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(ride)
    await notifications_service.commit_and_push(db)
    return await get_ride_or_404(db, ride.id)


async def update_ride(
    db: AsyncSession, *, ride_id: int, driver: User, data: RideUpdate, now: datetime
) -> Ride:
    """Apply a `PATCH /rides/{ride_id}` body (CONTRACT.md §4 Rides, Edit)."""
    ride = await load_ride_for_update(db, ride_id, driver)
    if ride.status not in OPEN_RIDE_STATUSES:
        raise Conflict("INVALID_STATE_TRANSITION", f"A {ride.status} ride can't be edited.")

    sent = data.model_fields_set
    approved_count, approved_seats = await approved_totals(db, ride.id)
    if approved_count and any(field in sent for field in LOCKED_FIELDS):
        raise Conflict(
            "RIDE_HAS_APPROVED_PASSENGERS",
            "The route and departure time are fixed once a passenger is approved.",
        )
    if data.capacity is not None and data.capacity < approved_seats:
        raise Conflict(
            "CAPACITY_BELOW_APPROVED",
            f"{approved_seats} seats are already approved on this ride.",
        )
    if data.departure_time is not None and data.departure_time <= now:
        raise _departure_in_past()

    for field in PLAIN_FIELDS:
        if field in sent:
            setattr(ride, field, getattr(data, field))
    if data.preferences is not None:
        ride.preferences = merge_preferences(ride.preferences, data.preferences)
    if data.capacity is not None:
        ride.capacity = data.capacity
        ride.available_seats = data.capacity - approved_seats
        ride.status = "full" if ride.available_seats == 0 else "upcoming"
    ride.updated_at = now
    await notifications_service.commit_and_push(db)
    return ride


async def cancel_ride(
    db: AsyncSession, settings: Settings, *, ride_id: int, driver: User, now: datetime
) -> Ride:
    """Driver cancel. Allowed with approved passengers, who are notified (CONTRACT.md D3)."""
    ride = await load_ride_for_update(db, ride_id, driver)
    if ride.status not in OPEN_RIDE_STATUSES:
        raise Conflict("INVALID_STATE_TRANSITION", f"A {ride.status} ride can't be cancelled.")

    affected = await _requests_in(db, ride.id, ACTIVE_REQUEST_STATUSES)
    for request in affected:
        request.status = "cancelled"
        request.responded_at = now
    ride.status = "cancelled"
    # No approved request is left, so `available_seats = capacity - approved seats` still holds.
    ride.available_seats = ride.capacity
    ride.updated_at = now

    for request in affected:
        await _notify_ride_cancelled(db, settings, ride, request, now)
    await notifications_service.commit_and_push(db)
    return ride


async def start_ride(
    db: AsyncSession, settings: Settings, *, ride_id: int, driver: User, now: datetime
) -> Ride:
    """Driver start, from `departure_time - 2h` onward. Pending requests are auto-rejected."""
    ride = await load_ride_for_update(db, ride_id, driver)
    if ride.status not in OPEN_RIDE_STATUSES:
        raise Conflict("INVALID_STATE_TRANSITION", f"A {ride.status} ride can't be started.")
    if now < ride.departure_time - EARLIEST_START:
        raise Conflict(
            "TOO_EARLY_TO_START", "A ride can be started at most 2 hours before departure."
        )

    affected = await _requests_in(db, ride.id, ACTIVE_REQUEST_STATUSES)
    pending = [request for request in affected if request.status == "pending"]
    approved = [request for request in affected if request.status == "approved"]
    for request in pending:
        request.status = "rejected"
        request.responded_at = now
    ride.status = "in_progress"
    ride.updated_at = now

    for request in pending:
        await _notify_auto_rejected(db, settings, ride, request, now)
    for request in approved:
        await _notify_ride_event(
            db,
            settings,
            ride,
            request.passenger,
            type="ride_started",
            title="Ride started",
            message=f"Your ride {describe_ride(ride)} has started.",
            now=now,
        )
    await notifications_service.commit_and_push(db)
    return ride


async def complete_ride(
    db: AsyncSession, settings: Settings, *, ride_id: int, driver: User, now: datetime
) -> Ride:
    """Driver complete, from `in_progress`. Opens rating for everyone on board."""
    ride = await load_ride_for_update(db, ride_id, driver)
    if ride.status != "in_progress":
        raise Conflict("INVALID_STATE_TRANSITION", f"A {ride.status} ride can't be completed.")

    ride.status = "completed"
    ride.updated_at = now

    approved = await _requests_in(db, ride.id, ("approved",))
    message = f"Your ride {describe_ride(ride)} is complete. Rate who you travelled with."
    for recipient in [ride.driver, *(request.passenger for request in approved)]:
        await _notify_ride_event(
            db,
            settings,
            ride,
            recipient,
            type="ride_completed",
            title="Ride completed",
            message=message,
            now=now,
        )
    await notifications_service.commit_and_push(db)
    return ride
