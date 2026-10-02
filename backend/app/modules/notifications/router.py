"""`/notifications` — the feed, the badge count and the read/clear writes."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.auth.deps import CurrentUser
from app.db import DbSession
from app.modules.notifications import service as notifications_service
from app.modules.notifications.schemas import NotificationOut, UnreadCountOut
from app.params import PageParams

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut], summary="The caller's feed, newest first")
async def list_notifications(
    user: CurrentUser,
    db: DbSession,
    page: PageParams,
    unread_only: Annotated[bool, Query()] = False,
) -> list[NotificationOut]:
    notifications = await notifications_service.list_notifications(
        db, user_id=user.id, unread_only=unread_only, limit=page.limit, offset=page.offset
    )
    return [NotificationOut.model_validate(row) for row in notifications]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Clear all")
async def clear_notifications(user: CurrentUser, db: DbSession) -> Response:
    await notifications_service.clear_all(db, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/unread-count", response_model=UnreadCountOut, summary="Badge count")
async def get_unread_count(user: CurrentUser, db: DbSession) -> UnreadCountOut:
    return UnreadCountOut(count=await notifications_service.unread_count(db, user_id=user.id))


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all read")
async def mark_all_notifications_read(user: CurrentUser, db: DbSession) -> Response:
    await notifications_service.mark_all_read(db, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark read")
async def mark_notification_read(
    notification_id: int, user: CurrentUser, db: DbSession
) -> NotificationOut:
    notification = await notifications_service.mark_read(
        db, notification_id=notification_id, user_id=user.id
    )
    return NotificationOut.model_validate(notification)
