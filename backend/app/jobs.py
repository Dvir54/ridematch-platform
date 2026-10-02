"""The in-process background jobs of CONTRACT.md §3 and §7.

Three passes, each callable on its own with an injected `now` so tests control time:

    await run_reminders(db, settings, now)       # 1h before departure
    await run_auto_complete(db, settings, now)   # in_progress 12h after departure
    await run_stale_cancel(db, settings, now)    # still open 12h after departure

`run_all` runs the three in that order, and `jobs_loop` runs `run_all` every minute from app
startup when `JOBS_ENABLED=true`. Each pass commits through `commit_and_push`, so the WebSocket
push leaves after the commit, exactly as in a request.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import utc_now
from app.config import Settings
from app.modules.notifications import service as notifications_service
from app.modules.notifications.models import Notification
from app.modules.notifications.service import EmailContent
from app.modules.requests.models import RideRequest
from app.modules.rides.models import OPEN_RIDE_STATUSES, Ride
from app.modules.rides.service import ACTIVE_REQUEST_STATUSES, describe_ride
from app.modules.users.models import User
from app.ws_push import PUSHER_KEY

logger = logging.getLogger(__name__)

#: How often `jobs_loop` runs a pass — §7 says the reminder job runs every minute.
JOB_INTERVAL_SECONDS = 60


async def _requests_in(
    db: AsyncSession, ride_id: int, statuses: tuple[str, ...]
) -> list[RideRequest]:
    stmt = (
        select(RideRequest)
        .where(RideRequest.ride_id == ride_id, RideRequest.status.in_(statuses))
        .order_by(RideRequest.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _notify(
    db: AsyncSession,
    settings: Settings,
    *,
    recipient: User,
    type: str,
    title: str,
    message: str,
    related_entity_type: str,
    related_entity_id: int,
    email: EmailContent | None = None,
    now: datetime,
) -> None:
    await notifications_service.notify(
        db,
        settings,
        user_id=recipient.id,
        type=type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        email=email,
        push=notifications_service.websocket_enabled(recipient.preferences),
        now=now,
    )


# ── 1h before departure (CONTRACT.md §7) ─────────────────────────────


async def run_reminders(db: AsyncSession, settings: Settings, now: datetime) -> int:
    """`ride_reminder` to the driver and every approved passenger. Returns rides reminded.

    Idempotent without a new column: a ride that already has a `ride_reminder` row is skipped,
    so a restart or an overlapping pass never reminds twice.
    """
    already_reminded = select(Notification.related_entity_id).where(
        Notification.type == "ride_reminder",
        Notification.related_entity_type == "ride",
        # A NULL in a `NOT IN` subquery would swallow every row.
        Notification.related_entity_id.is_not(None),
    )
    stmt = (
        select(Ride)
        .where(
            Ride.status.in_(OPEN_RIDE_STATUSES),
            Ride.departure_time > now,
            Ride.departure_time <= now + timedelta(minutes=settings.reminder_minutes_before),
            Ride.id.not_in(already_reminded),
        )
        .order_by(Ride.departure_time.asc())
    )
    rides = list((await db.execute(stmt)).scalars().all())
    for ride in rides:
        approved = await _requests_in(db, ride.id, ("approved",))
        message = f"Your ride {describe_ride(ride)} departs in about an hour."
        for recipient in [ride.driver, *(request.passenger for request in approved)]:
            await _notify(
                db,
                settings,
                recipient=recipient,
                type="ride_reminder",
                title="Ride reminder",
                message=message,
                related_entity_type="ride",
                related_entity_id=ride.id,
                now=now,
            )
    await notifications_service.commit_and_push(db)
    return len(rides)


# ── auto-complete (CONTRACT.md §3 Ride) ──────────────────────────────


async def run_auto_complete(db: AsyncSession, settings: Settings, now: datetime) -> int:
    """Complete rides still `in_progress` `AUTO_COMPLETE_AFTER_HOURS` after departure."""
    cutoff = now - timedelta(hours=settings.auto_complete_after_hours)
    stmt = (
        select(Ride)
        .where(Ride.status == "in_progress", Ride.departure_time <= cutoff)
        .order_by(Ride.id.asc())
    )
    rides = list((await db.execute(stmt)).scalars().all())
    for ride in rides:
        ride.status = "completed"
        ride.updated_at = now
        approved = await _requests_in(db, ride.id, ("approved",))
        message = f"Your ride {describe_ride(ride)} is complete. Rate who you travelled with."
        for recipient in [ride.driver, *(request.passenger for request in approved)]:
            await _notify(
                db,
                settings,
                recipient=recipient,
                type="ride_completed",
                title="Ride completed",
                message=message,
                related_entity_type="ride",
                related_entity_id=ride.id,
                now=now,
            )
    await notifications_service.commit_and_push(db)
    return len(rides)


# ── stale rides (CONTRACT.md §3 Ride) ────────────────────────────────


async def run_stale_cancel(db: AsyncSession, settings: Settings, now: datetime) -> int:
    """Cancel rides still `upcoming`/`full` 12h after departure; auto-reject pending requests.

    §7: `ride_cancelled` goes to pending **and** approved passengers, and a pending request
    that is auto-rejected also gets its own `request_rejected` (with email).
    """
    cutoff = now - timedelta(hours=settings.auto_complete_after_hours)
    stmt = (
        select(Ride)
        .where(Ride.status.in_(OPEN_RIDE_STATUSES), Ride.departure_time <= cutoff)
        .order_by(Ride.id.asc())
    )
    rides = list((await db.execute(stmt)).scalars().all())
    for ride in rides:
        affected = await _requests_in(db, ride.id, ACTIVE_REQUEST_STATUSES)
        pending = [request for request in affected if request.status == "pending"]
        for request in affected:
            # §3 Ride request: on a stale ride a pending request goes to `rejected` and an
            # approved one to `cancelled`, so seats come back and the seat invariant holds.
            request.status = "rejected" if request.status == "pending" else "cancelled"
            request.responded_at = now
        ride.status = "cancelled"
        ride.available_seats = ride.capacity
        ride.updated_at = now

        cancelled_message = (
            f"The ride {describe_ride(ride)} was cancelled because it never started."
        )
        for request in affected:
            await _notify(
                db,
                settings,
                recipient=request.passenger,
                type="ride_cancelled",
                title="Ride cancelled",
                message=cancelled_message,
                related_entity_type="ride",
                related_entity_id=ride.id,
                now=now,
            )
        for request in pending:
            passenger = request.passenger
            rejected_message = (
                f"The ride {describe_ride(ride)} was cancelled, so your request was declined."
            )
            email = (
                EmailContent(
                    to=passenger.email,
                    subject="Your RideMatch request was declined",
                    body=f"Hi {passenger.name},\n\n{rejected_message}\n\n— RideMatch",
                )
                if notifications_service.email_enabled(passenger.preferences)
                else None
            )
            await _notify(
                db,
                settings,
                recipient=passenger,
                type="request_rejected",
                title="Request declined",
                message=rejected_message,
                related_entity_type="ride_request",
                related_entity_id=request.id,
                email=email,
                now=now,
            )
    await notifications_service.commit_and_push(db)
    return len(rides)


# ── the loop ─────────────────────────────────────────────────────────


async def run_all(db: AsyncSession, settings: Settings, now: datetime) -> None:
    await run_reminders(db, settings, now)
    await run_auto_complete(db, settings, now)
    await run_stale_cancel(db, settings, now)


async def jobs_loop(app: FastAPI) -> None:
    """One pass a minute, each in its own session. Started by the app lifespan."""
    settings: Settings = app.state.settings
    while True:
        try:
            async with app.state.sessionmaker() as session:
                session.info[PUSHER_KEY] = app.state.ws_registry.push
                await run_all(session, settings, utc_now())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("A background job pass failed; retrying next cycle")
        await asyncio.sleep(JOB_INTERVAL_SECONDS)
