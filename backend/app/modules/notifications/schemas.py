"""openapi.yaml #/components/schemas/Notification and the unread-count envelope."""

from typing import Literal

from pydantic import Field

from app.schemas import ApiModel, UtcDatetime


class NotificationOut(ApiModel):
    id: int
    type: str
    title: str
    message: str
    related_entity_type: Literal["ride", "ride_request"] | None = None
    related_entity_id: int | None = None
    is_read: bool
    created_at: UtcDatetime


class UnreadCountOut(ApiModel):
    """openapi.yaml getUnreadCount — `{ "count": 3 }`."""

    count: int = Field(ge=0)
