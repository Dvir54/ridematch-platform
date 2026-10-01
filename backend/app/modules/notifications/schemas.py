"""openapi.yaml #/components/schemas/Notification."""

from typing import Literal

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
