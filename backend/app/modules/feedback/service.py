"""Rating logic: the rules of CONTRACT.md §4 Ratings and the counters behind `/users/me/stats`.

Like `rides.service`, this reads `requests.models` directly but never calls the requests
*service*, so the dependency between the two still points one way.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import Conflict, Forbidden
from app.modules.feedback.models import Rating
from app.modules.feedback.schemas import RatingCreate
from app.modules.notifications import service as notifications_service
from app.modules.requests.models import RideRequest
from app.modules.rides import service as rides_service
from app.modules.rides.models import OPEN_RIDE_STATUSES, Ride
from app.modules.rides.service import describe_ride
from app.modules.users import service as users_service
from app.modules.users.models import User

#: `/ratings/pending` only prompts for recent rides, so the list cannot grow forever (D21).
PENDING_WINDOW = timedelta(days=30)
#: What "upcoming" means for both `upcoming_rides` and `upcoming_trips` (D21): a ride that has
#: not left yet. An `in_progress` ride is no longer upcoming and not yet completed, so it counts
#: in neither — the same rule on both sides, so the two numbers can't drift apart.
UPCOMING_RIDE_STATUSES = OPEN_RIDE_STATUSES


# ── participants ─────────────────────────────────────────────────────


async def _approved_passenger_ids(db: AsyncSession, ride_ids: list[int]) -> dict[int, list[int]]:
    """`{ride_id: [passenger_id, …]}` for the approved requests on these rides."""
    if not ride_ids:
        return {}
    stmt = (
        select(RideRequest.ride_id, RideRequest.passenger_id)
        .where(RideRequest.ride_id.in_(ride_ids), RideRequest.status == "approved")
        .order_by(RideRequest.passenger_id.asc())
    )
    by_ride: dict[int, list[int]] = {}
    for ride_id, passenger_id in (await db.execute(stmt)).all():
        by_ride.setdefault(ride_id, []).append(passenger_id)
    return by_ride


def _role_on_ride(ride: Ride, approved_passenger_ids: list[int], user_id: int) -> str | None:
    """`driver`, `passenger`, or `None` when the user was not on this ride."""
    if ride.driver_id == user_id:
        return "driver"
    if user_id in approved_passenger_ids:
        return "passenger"
    return None


# ── reads ────────────────────────────────────────────────────────────


async def list_user_ratings(
    db: AsyncSession,
    *,
    user_id: int,
    role_rated: str | None,
    limit: int,
    offset: int,
) -> list[Rating]:
    """Ratings the user *received*, newest first (`openapi.yaml` listUserRatings)."""
    await users_service.get_user_or_404(db, user_id)
    stmt = select(Rating).where(Rating.to_user_id == user_id)
    if role_rated is not None:
        stmt = stmt.where(Rating.role_rated == role_rated)
    stmt = stmt.order_by(Rating.created_at.desc(), Rating.id.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def _rides_i_was_on(db: AsyncSession, *, user_id: int, cutoff: datetime) -> list[Ride]:
    """Completed rides inside the prompt window where the caller drove or held a seat (D21)."""
    was_on = (
        select(Ride.id)
        .where(Ride.driver_id == user_id)
        .union(
            select(RideRequest.ride_id).where(
                RideRequest.passenger_id == user_id, RideRequest.status == "approved"
            )
        )
    )
    stmt = (
        select(Ride)
        .where(
            Ride.status == "completed",
            Ride.departure_time >= cutoff,
            Ride.id.in_(was_on),
        )
        .order_by(Ride.departure_time.desc(), Ride.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_pending_ratings(
    db: AsyncSession, *, user: User, now: datetime
) -> list[tuple[Ride, User, str]]:
    """`(ride, ratee, role_rated)` for every rating the caller still owes (D21).

    A driver owes one per approved passenger; an approved passenger owes one to the driver.
    """
    rides = await _rides_i_was_on(db, user_id=user.id, cutoff=now - PENDING_WINDOW)
    if not rides:
        return []

    ride_ids = [ride.id for ride in rides]
    approved = await _approved_passenger_ids(db, ride_ids)
    already = {
        (ride_id, to_user_id)
        for ride_id, to_user_id in (
            await db.execute(
                select(Rating.ride_id, Rating.to_user_id).where(
                    Rating.ride_id.in_(ride_ids), Rating.from_user_id == user.id
                )
            )
        ).all()
    }

    owed: list[tuple[Ride, int, str]] = []
    for ride in rides:
        passengers = approved.get(ride.id, [])
        role = _role_on_ride(ride, passengers, user.id)
        if role == "driver":
            owed.extend(
                (ride, passenger_id, "passenger")
                for passenger_id in passengers
                if (ride.id, passenger_id) not in already
            )
        elif role == "passenger" and (ride.id, ride.driver_id) not in already:
            owed.append((ride, ride.driver_id, "driver"))

    ratees = await users_service.get_users_by_ids(db, [user_id for _, user_id, _ in owed])
    return [(ride, ratees[ratee_id], role) for ride, ratee_id, role in owed if ratee_id in ratees]


# ── stats (CONTRACT.md D21) ──────────────────────────────────────────


async def _count(db: AsyncSession, stmt: Select[Any]) -> int:
    return int((await db.execute(stmt)).scalar_one())


def _my_requests_on_my_rides(user_id: int, *, request_status: str) -> Select[Any]:
    """Requests on rides the caller drives — the driver side of the counters."""
    return (
        select(func.count())
        .select_from(RideRequest)
        .join(Ride, Ride.id == RideRequest.ride_id)
        .where(Ride.driver_id == user_id, RideRequest.status == request_status)
    )


def _my_approved_trips(user_id: int, *, ride_statuses: tuple[str, ...]) -> Select[Any]:
    """The caller's approved requests on rides in these statuses — the passenger side."""
    return (
        select(func.count())
        .select_from(RideRequest)
        .join(Ride, Ride.id == RideRequest.ride_id)
        .where(
            RideRequest.passenger_id == user_id,
            RideRequest.status == "approved",
            Ride.status.in_(ride_statuses),
        )
    )


async def user_stats(db: AsyncSession, *, user_id: int) -> dict[str, dict[str, int]]:
    """The counters behind driver Home and passenger Profile. Each one is defined in D21."""
    my_rides = select(func.count()).select_from(Ride).where(Ride.driver_id == user_id)
    my_requests = (
        select(func.count()).select_from(RideRequest).where(RideRequest.passenger_id == user_id)
    )
    carried = (
        select(func.coalesce(func.sum(RideRequest.seats_requested), 0))
        .select_from(RideRequest)
        .join(Ride, Ride.id == RideRequest.ride_id)
        .where(
            Ride.driver_id == user_id,
            Ride.status == "completed",
            RideRequest.status == "approved",
        )
    )

    return {
        "as_driver": {
            "rides_offered": await _count(db, my_rides),
            "rides_completed": await _count(db, my_rides.where(Ride.status == "completed")),
            "upcoming_rides": await _count(
                db, my_rides.where(Ride.status.in_(UPCOMING_RIDE_STATUSES))
            ),
            "pending_requests": await _count(
                db, _my_requests_on_my_rides(user_id, request_status="pending")
            ),
            "passengers_carried": await _count(db, carried),
        },
        "as_passenger": {
            "trips_requested": await _count(db, my_requests),
            "trips_completed": await _count(
                db, _my_approved_trips(user_id, ride_statuses=("completed",))
            ),
            "upcoming_trips": await _count(
                db, _my_approved_trips(user_id, ride_statuses=UPCOMING_RIDE_STATUSES)
            ),
        },
    }


# ── writes ───────────────────────────────────────────────────────────


def _apply_average(ratee: User, *, role_rated: str, score: int) -> None:
    """`new = (old * count + score) / (count + 1)`, in the caller transaction (§4 Ratings)."""
    if role_rated == "driver":
        average, count = ratee.driver_rating, ratee.driver_rating_count
    else:
        average, count = ratee.passenger_rating, ratee.passenger_rating_count
    updated = ((average or 0.0) * count + score) / (count + 1)
    if role_rated == "driver":
        ratee.driver_rating, ratee.driver_rating_count = updated, count + 1
    else:
        ratee.passenger_rating, ratee.passenger_rating_count = updated, count + 1


async def _rating_exists(
    db: AsyncSession, *, ride_id: int, from_user_id: int, to_user_id: int
) -> bool:
    stmt = select(Rating.id).where(
        Rating.ride_id == ride_id,
        Rating.from_user_id == from_user_id,
        Rating.to_user_id == to_user_id,
    )
    return (await db.execute(stmt)).scalars().first() is not None


async def create_rating(
    db: AsyncSession,
    settings: Settings,
    *,
    rater: User,
    data: RatingCreate,
    now: datetime,
) -> Rating:
    """One rating, in the order of checks D21 fixes: 404s, completed, participant, duplicate."""
    ride = await rides_service.get_ride_or_404(db, data.ride_id)
    ratee = await users_service.get_user_or_404(db, data.to_user_id)
    if ride.status != "completed":
        raise Conflict("RIDE_NOT_COMPLETED", f"A {ride.status} ride can only be rated once done.")

    passengers = (await _approved_passenger_ids(db, [ride.id])).get(ride.id, [])
    rater_role = _role_on_ride(ride, passengers, rater.id)
    ratee_role = _role_on_ride(ride, passengers, ratee.id)
    # Equal roles covers both passenger-to-passenger and rating yourself.
    if rater_role is None or ratee_role is None or rater_role == ratee_role:
        raise Forbidden("NOT_A_PARTICIPANT", "You cannot rate this person for this ride.")

    # `ratings_one_per_direction` is the real guard; this check is what makes the second
    # attempt a 409 instead of a 500.
    if await _rating_exists(db, ride_id=ride.id, from_user_id=rater.id, to_user_id=ratee.id):
        raise Conflict("ALREADY_RATED", "You already rated this person for this ride.")

    rating = Rating(
        ride_id=ride.id,
        # The object, not just the id: `Rating.from_user` is `selectin` on *load*, and a fresh
        # row has never been loaded, so the response would otherwise lazy-load it mid-serialize.
        from_user=rater,
        to_user_id=ratee.id,
        role_rated=ratee_role,
        score=data.score,
        comment=data.comment,
        tags=data.unique_tags(),
        created_at=now,
    )
    db.add(rating)
    try:
        await db.flush()
    except IntegrityError as exc:  # the same direction submitted twice at once
        await db.rollback()
        if "ratings_one_per_direction" in str(exc.orig):
            raise Conflict("ALREADY_RATED", "You already rated this person for this ride.") from exc
        raise

    # Same transaction as the row, so the average can never drift from the ratings (§4 Ratings).
    _apply_average(ratee, role_rated=ratee_role, score=data.score)
    await notifications_service.notify(
        db,
        settings,
        user_id=ratee.id,
        type="rating_received",
        title="New rating",
        message=(
            f"{rater.name} rated you {data.score}/5 as a {ratee_role} "
            f"for the ride {describe_ride(ride)}."
        ),
        related_entity_type="ride",
        related_entity_id=ride.id,
        push=notifications_service.websocket_enabled(ratee.preferences),
        now=now,
    )
    await notifications_service.commit_and_push(db)
    return rating
