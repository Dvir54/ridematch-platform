"""`notifications` — mirrors contracts/schema.sql."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# openapi.yaml NotificationType
NOTIFICATION_TYPES = (
    "welcome",
    "request_created",
    "request_approved",
    "request_rejected",
    "request_cancelled",
    "ride_reminder",
    "ride_cancelled",
    "ride_started",
    "ride_completed",
    "rating_received",
)
RELATED_ENTITY_TYPES = ("ride", "ride_request")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "related_entity_type IN ('ride', 'ride_request')",
            name="notifications_related_entity_type_check",
        ),
        Index("notifications_feed_idx", "user_id", "is_read", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(20))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
