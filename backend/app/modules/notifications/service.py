"""Notification rows plus the optional email that goes with them (CONTRACT.md §7).

The innermost module: it depends on nothing else under `app/modules`, so callers pass everything
they want sent (including whether an email is wanted) rather than having preferences read here.
The WebSocket push after commit arrives in Phase 4.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.notifications.email import send_email
from app.modules.notifications.models import Notification


@dataclass(frozen=True, slots=True)
class EmailContent:
    to: str
    subject: str
    body: str


def email_enabled(preferences: dict | None) -> bool:
    """`preferences.notifications.email`, defaulting to on. A plain dict, so no module above
    this one has to be imported here."""
    return bool((preferences or {}).get("notifications", {}).get("email", True))


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
    now: datetime | None = None,
) -> Notification:
    """Write the notification row and, when `email` is given, send the email."""
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
        await send_email(settings, email.to, email.subject, email.body)
    return notification
