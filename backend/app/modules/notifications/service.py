"""Notification rows plus the optional email that goes with them (CONTRACT.md §7).

The innermost module: it depends on nothing else under `app/modules`, so callers pass everything
they want sent (including whether an email or a push is wanted) rather than having preferences
read here. The push itself leaves after the caller commits — see `app.ws_push`.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import ws_push
from app.config import Settings
from app.errors import Forbidden, NotFound
from app.modules.notifications import email as email_delivery
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationOut

#: `db.info` key: `(settings, user_id, EmailContent)` waiting for the commit.
EMAIL_PENDING_KEY = "email_pending"


async def commit_and_push(db: AsyncSession) -> None:
    """Services commit through this one call (`db.commit()` would push and send nothing).

    Commit, then push what the transaction queued, then hand its emails to the mailer. The
    queues are taken before the commit, so a failed commit sends nothing.
    """
    emails = db.info.pop(EMAIL_PENDING_KEY, [])
    await ws_push.commit_and_push(db)
    for settings, user_id, content in emails:
        email_delivery.dispatch(
            settings, content.to, content.subject, content.body, user_id=user_id
        )


@dataclass(frozen=True, slots=True)
class EmailContent:
    to: str
    subject: str
    body: str


def _notifications_pref(preferences: dict | None, key: str) -> bool:
    """One `preferences.notifications.*` flag, defaulting to on. A plain dict, so no module
    above this one has to be imported here."""
    return bool((preferences or {}).get("notifications", {}).get(key, True))


def email_enabled(preferences: dict | None) -> bool:
    return _notifications_pref(preferences, "email")


def websocket_enabled(preferences: dict | None) -> bool:
    """CONTRACT.md §6: the row is written regardless, the push is not sent when this is false."""
    return _notifications_pref(preferences, "websocket")


def ws_message(notification: Notification) -> dict:
    """`openapi.yaml` WsServerMessage — the same object `GET /notifications` returns."""
    return {
        "event": "notification",
        "data": NotificationOut.model_validate(notification).model_dump(mode="json"),
    }


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
    now: datetime | None = None,
) -> Notification:
    """Adds (and flushes) the row. Committing is the caller's business."""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        is_read=False,
    )
    if now is not None:
        notification.created_at = now
    db.add(notification)
    await db.flush()
    return notification


async def notify(
    db: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
    email: EmailContent | None = None,
    push: bool = True,
    now: datetime | None = None,
) -> Notification:
    """Write the row, and queue the email (when `email` is given) and the WebSocket push.

    Both leave only once the caller calls `commit_and_push` (CONTRACT.md §4).
    """
    notification = await create_notification(
        db,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        now=now,
    )
    if email is not None:
        db.info.setdefault(EMAIL_PENDING_KEY, []).append((settings, user_id, email))
    if push:
        ws_push.collect(db, user_id, ws_message(notification))
    return notification


# ── the notification endpoints ───────────────────────────────────────


async def list_notifications(
    db: AsyncSession, *, user_id: int, unread_only: bool, limit: int, offset: int
) -> list[Notification]:
    """Newest first (`openapi.yaml` listNotifications)."""
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = (
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def unread_count(db: AsyncSession, *, user_id: int) -> int:
    stmt = select(func.count()).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    return int((await db.execute(stmt)).scalar_one())


async def mark_read(db: AsyncSession, *, notification_id: int, user_id: int) -> Notification:
    """404 when it doesn't exist, 403 when it's someone else's (CONTRACT.md §2)."""
    notification = (
        await db.execute(select(Notification).where(Notification.id == notification_id))
    ).scalar_one_or_none()
    if notification is None:
        raise NotFound("NOT_FOUND", "Notification not found.")
    if notification.user_id != user_id:
        raise Forbidden("FORBIDDEN", "This notification is not yours.")
    notification.is_read = True
    await db.commit()
    return notification


async def mark_all_read(db: AsyncSession, *, user_id: int) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()


async def clear_all(db: AsyncSession, *, user_id: int) -> None:
    await db.execute(delete(Notification).where(Notification.user_id == user_id))
    await db.commit()
