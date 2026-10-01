"""`users` and `clerk_webhook_events` — mirrors contracts/schema.sql.

The `users_set_updated_at` trigger lives in the Alembic migration; SQLAlchemy can't express it.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

GENDERS = ("male", "female", "other", "prefer_not_to_say")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "gender IN ('male', 'female', 'other', 'prefer_not_to_say')",
            name="users_gender_check",
        ),
        CheckConstraint("driver_rating BETWEEN 1 AND 5", name="users_driver_rating_check"),
        CheckConstraint("driver_rating_count >= 0", name="users_driver_rating_count_check"),
        CheckConstraint("passenger_rating BETWEEN 1 AND 5", name="users_passenger_rating_check"),
        CheckConstraint("passenger_rating_count >= 0", name="users_passenger_rating_count_check"),
        Index("users_clerk_user_id_uq", "clerk_user_id", unique=True),
        # Case-insensitive uniqueness: the app lowercases email before insert/lookup.
        Index("users_email_lower_uq", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    driver_rating: Mapped[float | None] = mapped_column(Double)
    driver_rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    passenger_rating: Mapped[float | None] = mapped_column(Double)
    passenger_rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    vehicle: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClerkWebhookEvent(Base):
    """Idempotency log for Clerk webhooks, keyed on `svix-id`."""

    __tablename__ = "clerk_webhook_events"

    svix_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
