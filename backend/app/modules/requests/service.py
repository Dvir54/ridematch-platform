"""Ride-request logic: the state machine of CONTRACT.md §3 and the rules of §4 Requests."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import Conflict, Forbidden, NotFound
from app.modules.notifications import service as notifications_service
from app.modules.notifications.service import EmailContent
from app.modules.requests.models import BLOCKING_REQUEST_STATUSES, RideRequest
from app.modules.requests.schemas import RideRequestCreate
from app.modules.rides import service as rides_service
from app.modules.rides.models import OPEN_RIDE_STATUSES, Ride
from app.modules.rides.service import describe_ride
from app.modules.users.models import User

#: An approved passenger may cancel up to this long before departure (CONTRACT.md §3, D15).
CANCEL_CUTOFF = timedelta(hours=1)
#: Statuses a passenger may still cancel from.
CANCELLABLE_STATUSES = ("pending", "approved")


# ── reads ────────────────────────────────────────────────────────────


async def get_request_or_404(db: AsyncSession, request_id: int) -> RideRequest:
    stmt = (
        select(RideRequest)
        .where(RideRequest.id == request_id)
        .execution_options(populate_existing=True)
    )
    request = (await db.execute(stmt)).scalar_one_or_none()
    if request is None:
        raise NotFound("NOT_FOUND", "Request not found.")
    return request


def require_viewer(request: RideRequest, user: User) -> None:
    """Only the passenger who made the request and the ride's driver may see it."""
    if user.id not in (request.passenger_id, request.ride.driver_id):
        raise Forbidden("FORBIDDEN", "This request is not yours.")


def require_ride_driver(request: RideRequest, user: User) -> None:
    if request.ride.driver_id != user.id:
        raise Forbidden("FORBIDDEN", "Only the ride's driver can respond to this request.")


def require_passenger(request: RideRequest, user: User) -> None:
    if request.passenger_id != user.id:
        raise Forbidden("FORBIDDEN", "This request belongs to another passenger.")


async def _blocking_request(
    db: AsyncSession, ride_id: int, passenger_id: int
) -> RideRequest | None:
    """The one pending/approved/rejected row the partial unique index allows, if any."""
    stmt = select(RideRequest).where(
        RideRequest.ride_id == ride_id,
        RideRequest.passenger_id == passenger_id,
        RideRequest.status.in_(BLOCKING_REQUEST_STATUSES),
    )
    return (await db.execute(stmt)).scalars().first()


async def list_my_requests(
    db: AsyncSession,
    *,
    passenger_id: int,
    statuses: tuple[str, ...],
    limit: int,
    offset: int,
) -> list[RideRequest]:
    stmt = select(RideRequest).where(RideRequest.passenger_id == passenger_id)
    if statuses:
        stmt = stmt.where(RideRequest.status.in_(statuses))
    stmt = (
        stmt.order_by(RideRequest.requested_at.desc(), RideRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_ride_requests(
    db: AsyncSession, *, ride_id: int, driver: User, status: str | None
) -> list[RideRequest]:
    """Every request on one of the driver's own rides, newest first."""
    ride = await rides_service.get_ride_or_404(db, ride_id)
    rides_service.require_driver(ride, driver)
    stmt = select(RideRequest).where(RideRequest.ride_id == ride.id)
    if status is not None:
        stmt = stmt.where(RideRequest.status == status)
    stmt = stmt.order_by(RideRequest.requested_at.desc(), RideRequest.id.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_incoming_requests(
    db: AsyncSession, *, driver_id: int, status: str
) -> list[RideRequest]:
    """Requests across all of the caller's rides — the driver's Requests tab."""
    stmt = (
        select(RideRequest)
        .join(Ride, Ride.id == RideRequest.ride_id)
        .where(Ride.driver_id == driver_id, RideRequest.status == status)
        .order_by(RideRequest.requested_at.desc(), RideRequest.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── notifications (CONTRACT.md §7) ───────────────────────────────────


async def _notify_driver(
    db: AsyncSession,
    settings: Settings,
    request: RideRequest,
    *,
    type: str,
    title: str,
    message: str,
    now: datetime,
) -> None:
    await notifications_service.notify(
        db,
        settings,
        user_id=request.ride.driver_id,
        type=type,
        title=title,
        message=message,
        related_entity_type="ride_request",
        related_entity_id=request.id,
        now=now,
    )


async def _notify_passenger(
    db: AsyncSession,
    settings: Settings,
    request: RideRequest,
    *,
    type: str,
    title: str,
    message: str,
    subject: str,
    now: datetime,
) -> None:
    """The passenger-facing decisions, which also go out by email (CONTRACT.md §7)."""
    passenger = request.passenger
    email = (
        EmailContent(
            to=passenger.email,
            subject=subject,
            body=f"Hi {passenger.name},\n\n{message}\n\n— RideMatch",
        )
        if notifications_service.email_enabled(passenger.preferences)
        else None
    )
    await notifications_service.notify(
        db,
        settings,
        user_id=request.passenger_id,
        type=type,
        title=title,
        message=message,
        related_entity_type="ride_request",
        related_entity_id=request.id,
        email=email,
        now=now,
    )


def _seats(count: int) -> str:
    return "1 seat" if count == 1 else f"{count} seats"


# ── writes ───────────────────────────────────────────────────────────


async def create_request(
    db: AsyncSession,
    settings: Settings,
    *,
    ride_id: int,
    passenger: User,
    data: RideRequestCreate,
    now: datetime,
) -> RideRequest:
    """A new `pending` request. The 409s are checked in the order openapi.yaml lists them."""
    ride = await rides_service.get_ride_or_404(db, ride_id)
    if ride.driver_id == passenger.id:
        raise Conflict("CANNOT_REQUEST_OWN_RIDE", "You can't request a seat on your own ride.")
    if ride.status != "upcoming":
        raise Conflict("RIDE_NOT_OPEN", f"A {ride.status} ride doesn't take requests.")
    if data.seats_requested > ride.available_seats:
        raise Conflict(
            "NOT_ENOUGH_SEATS", f"Only {_seats(ride.available_seats)} are left on this ride."
        )

    existing = await _blocking_request(db, ride.id, passenger.id)
    if existing is not None:
        if existing.status == "rejected":
            raise Conflict(
                "PREVIOUSLY_REJECTED", "The driver already declined your request for this ride."
            )
        raise Conflict("REQUEST_ALREADY_EXISTS", "You already have a request on this ride.")

    request = RideRequest(
        ride_id=ride.id,
        passenger_id=passenger.id,
        seats_requested=data.seats_requested,
        status="pending",
        requested_at=now,
    )
    db.add(request)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "ride_requests_active_uq" in str(exc.orig):
            raise Conflict(
                "REQUEST_ALREADY_EXISTS", "You already have a request on this ride."
            ) from exc
        raise

    await _notify_driver(
        db,
        settings,
        request,
        type="request_created",
        title="New ride request",
        message=(
            f"{passenger.name} asked for {_seats(data.seats_requested)} on your ride "
            f"{describe_ride(ride)}."
        ),
        now=now,
    )
    await db.commit()
    return await get_request_or_404(db, request.id)


async def approve_request(
    db: AsyncSession, settings: Settings, *, request_id: int, driver: User, now: datetime
) -> RideRequest:
    """One transaction, under the ride's row lock (CONTRACT.md §4 Rides, Approve)."""
    request = await get_request_or_404(db, request_id)
    require_ride_driver(request, driver)

    # Every approval on this ride serialises here, so the re-read below and the seat check that
    # follows see what is actually committed — this is what makes the last-seat race safe.
    await rides_service.lock_ride(db, request.ride_id)
    request = await get_request_or_404(db, request_id)
    ride = request.ride

    if request.status != "pending":
        raise Conflict("INVALID_STATE_TRANSITION", f"A {request.status} request can't be approved.")
    if ride.status not in OPEN_RIDE_STATUSES:
        raise Conflict("INVALID_STATE_TRANSITION", f"A {ride.status} ride can't take passengers.")
    if request.seats_requested > ride.available_seats:
        raise Conflict(
            "NOT_ENOUGH_SEATS", f"Only {_seats(ride.available_seats)} are left on this ride."
        )

    ride.available_seats -= request.seats_requested
    if ride.available_seats == 0:
        ride.status = "full"
    ride.updated_at = now
    request.status = "approved"
    request.responded_at = now

    await _notify_passenger(
        db,
        settings,
        request,
        type="request_approved",
        title="Request approved",
        message=f"You have {_seats(request.seats_requested)} on the ride {describe_ride(ride)}.",
        subject="Your RideMatch seat is confirmed",
        now=now,
    )
    await db.commit()
    return request


async def reject_request(
    db: AsyncSession, settings: Settings, *, request_id: int, driver: User, now: datetime
) -> RideRequest:
    request = await get_request_or_404(db, request_id)
    require_ride_driver(request, driver)
    if request.status != "pending":
        raise Conflict("INVALID_STATE_TRANSITION", f"A {request.status} request can't be rejected.")

    request.status = "rejected"
    request.responded_at = now
    await _notify_passenger(
        db,
        settings,
        request,
        type="request_rejected",
        title="Request declined",
        message=f"The driver declined your request for the ride {describe_ride(request.ride)}.",
        subject="Your RideMatch request was declined",
        now=now,
    )
    await db.commit()
    return request


async def cancel_request(
    db: AsyncSession, settings: Settings, *, request_id: int, passenger: User, now: datetime
) -> RideRequest:
    """Passenger cancel. Approved seats go back to the ride (CONTRACT.md §3, D15)."""
    request = await get_request_or_404(db, request_id)
    require_passenger(request, passenger)

    await rides_service.lock_ride(db, request.ride_id)
    request = await get_request_or_404(db, request_id)
    ride = request.ride

    if request.status not in CANCELLABLE_STATUSES:
        raise Conflict(
            "INVALID_STATE_TRANSITION", f"A {request.status} request can't be cancelled."
        )
    if ride.status not in OPEN_RIDE_STATUSES:
        # The ride has started or is over; a seat on it can no longer be given back.
        raise Conflict(
            "INVALID_STATE_TRANSITION", f"A seat on a {ride.status} ride can't be cancelled."
        )

    if request.status == "approved":
        if now > ride.departure_time - CANCEL_CUTOFF:
            raise Conflict(
                "TOO_LATE_TO_CANCEL",
                "An approved seat can only be cancelled up to 1 hour before departure.",
            )
        ride.available_seats += request.seats_requested
        if ride.status == "full":
            ride.status = "upcoming"
        ride.updated_at = now

    request.status = "cancelled"
    request.responded_at = now
    await _notify_driver(
        db,
        settings,
        request,
        type="request_cancelled",
        title="Passenger cancelled",
        message=(
            f"{passenger.name} cancelled {_seats(request.seats_requested)} on your ride "
            f"{describe_ride(ride)}."
        ),
        now=now,
    )
    await db.commit()
    return request
