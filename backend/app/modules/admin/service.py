"""Admin logic: user/ride management and analytics (CONTRACT.md §2 Admin, §4, /admin/* in
openapi.yaml). Reads `requests`/`feedback`/`rides` models directly and calls into `rides.service`
for force-cancel, matching the one-way module dependency in `docs/roles/backend.md` §4.2.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import clerk_admin
from app.config import Settings
from app.errors import Conflict
from app.modules.admin.schemas import AnalyticsSummaryOut
from app.modules.feedback.models import Rating
from app.modules.requests.models import RideRequest
from app.modules.rides import service as rides_service
from app.modules.rides.models import Ride
from app.modules.users import service as users_service
from app.modules.users.models import User

if TYPE_CHECKING:
    from app.ws import WsRegistry


# ── users ────────────────────────────────────────────────────────────


async def list_users(
    db: AsyncSession,
    *,
    q: str | None,
    is_active: bool | None,
    is_admin: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[User], int]:
    conditions = []
    if q:
        like = f"%{q.strip().lower()}%"
        conditions.append(or_(func.lower(User.name).like(like), func.lower(User.email).like(like)))
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if is_admin is not None:
        conditions.append(User.is_admin == is_admin)

    count_stmt = select(func.count()).select_from(User)
    stmt = select(User).order_by(User.id.asc())
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
        stmt = stmt.where(condition)

    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = stmt.limit(limit).offset(offset)
    users = list((await db.execute(stmt)).scalars().all())
    return users, total


async def get_user_detail(
    db: AsyncSession, user_id: int
) -> tuple[User, list[Ride], list[RideRequest], list[Rating]]:
    user = await users_service.get_user_or_404(db, user_id)
    rides = list(
        (
            await db.execute(
                select(Ride)
                .where(Ride.driver_id == user_id)
                .order_by(Ride.departure_time.desc(), Ride.id.desc())
            )
        )
        .scalars()
        .all()
    )
    requests = list(
        (
            await db.execute(
                select(RideRequest)
                .where(RideRequest.passenger_id == user_id)
                .order_by(RideRequest.requested_at.desc(), RideRequest.id.desc())
            )
        )
        .scalars()
        .all()
    )
    ratings = list(
        (
            await db.execute(
                select(Rating)
                .where(Rating.to_user_id == user_id)
                .order_by(Rating.created_at.desc(), Rating.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return user, rides, requests, ratings


async def deactivate_user(
    db: AsyncSession,
    settings: Settings,
    *,
    admin: User,
    user_id: int,
    now: datetime,
    registry: "WsRegistry",
) -> User:
    if admin.id == user_id:
        raise Conflict("CANNOT_DEACTIVATE_SELF", "You can't deactivate your own account.")
    user = await users_service.get_user_or_404(db, user_id)
    user.is_active = False
    user.updated_at = now
    await db.commit()
    await clerk_admin.ban_user(settings, user.clerk_user_id)
    await registry.close_user(user.id)
    return user


async def reactivate_user(
    db: AsyncSession, settings: Settings, *, user_id: int, now: datetime
) -> User:
    user = await users_service.get_user_or_404(db, user_id)
    user.is_active = True
    user.updated_at = now
    await db.commit()
    await clerk_admin.unban_user(settings, user.clerk_user_id)
    return user


# ── rides ────────────────────────────────────────────────────────────


async def list_rides(
    db: AsyncSession,
    *,
    statuses: tuple[str, ...],
    driver_id: int | None,
    from_: datetime | None,
    to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[Ride], int]:
    conditions = []
    if statuses:
        conditions.append(Ride.status.in_(statuses))
    if driver_id is not None:
        conditions.append(Ride.driver_id == driver_id)
    if from_ is not None:
        conditions.append(Ride.departure_time >= from_)
    if to is not None:
        conditions.append(Ride.departure_time < to)

    count_stmt = select(func.count()).select_from(Ride)
    stmt = select(Ride).order_by(Ride.departure_time.desc(), Ride.id.desc())
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
        stmt = stmt.where(condition)

    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = stmt.limit(limit).offset(offset)
    rides = list((await db.execute(stmt)).scalars().all())
    return rides, total


async def force_cancel_ride(
    db: AsyncSession, settings: Settings, *, ride_id: int, reason: str, now: datetime
) -> Ride:
    return await rides_service.admin_force_cancel(
        db, settings, ride_id=ride_id, reason=reason, now=now
    )


# ── analytics ────────────────────────────────────────────────────────


async def _count(db: AsyncSession, *conditions) -> int:
    stmt = select(func.count()).select_from(Ride)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int((await db.execute(stmt)).scalar_one())


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


async def get_analytics(db: AsyncSession, *, from_: datetime, to: datetime) -> AnalyticsSummaryOut:
    """CONTRACT.md §2 Lists / openapi.yaml AnalyticsSummary.

    `rides_created` counts by `created_at` (rides offered in the window); `rides_completed` and
    `rides_cancelled` count by `departure_time`, matching `completion_rate`'s own description
    ("among rides departing in range"). `requests_created`/`approval_rate` apply the same window
    to `ride_requests.requested_at`. `new_users`/`active_users` use `users.created_at`/
    `last_login_at` respectively.
    """
    rides_created = await _count(db, Ride.created_at >= from_, Ride.created_at < to)
    rides_completed = await _count(
        db, Ride.departure_time >= from_, Ride.departure_time < to, Ride.status == "completed"
    )
    rides_cancelled = await _count(
        db, Ride.departure_time >= from_, Ride.departure_time < to, Ride.status == "cancelled"
    )

    requests_stmt = select(RideRequest.status, func.count()).where(
        RideRequest.requested_at >= from_, RideRequest.requested_at < to
    )
    requests_stmt = requests_stmt.group_by(RideRequest.status)
    by_status = dict((await db.execute(requests_stmt)).all())
    requests_created = sum(by_status.values())
    approved = int(by_status.get("approved", 0))
    rejected = int(by_status.get("rejected", 0))

    active_users = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.last_login_at >= from_, User.last_login_at < to)
            )
        ).scalar_one()
    )
    new_users = int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.created_at >= from_, User.created_at < to)
            )
        ).scalar_one()
    )

    return AnalyticsSummaryOut(
        **{
            "from": from_,
            "to": to,
            "rides_created": rides_created,
            "rides_completed": rides_completed,
            "rides_cancelled": rides_cancelled,
            "completion_rate": _rate(rides_completed, rides_completed + rides_cancelled),
            "requests_created": requests_created,
            "approval_rate": _rate(approved, approved + rejected),
            "active_users": active_users,
            "new_users": new_users,
        }
    )
