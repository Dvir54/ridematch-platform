"""`rides` — mirrors contracts/schema.sql.

The `rides_set_updated_at` trigger lives in the Alembic migration.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.modules.users.models import User

RIDE_STATUSES = ("upcoming", "full", "in_progress", "completed", "cancelled")
# Statuses a driver's ride still occupies a seat plan for (CONTRACT.md §3).
OPEN_RIDE_STATUSES = ("upcoming", "full")


class Ride(Base):
    __tablename__ = "rides"
    __table_args__ = (
        CheckConstraint("start_lat BETWEEN -90 AND 90", name="rides_start_lat_check"),
        CheckConstraint("start_lng BETWEEN -180 AND 180", name="rides_start_lng_check"),
        CheckConstraint("end_lat BETWEEN -90 AND 90", name="rides_end_lat_check"),
        CheckConstraint("end_lng BETWEEN -180 AND 180", name="rides_end_lng_check"),
        CheckConstraint("capacity BETWEEN 1 AND 8", name="rides_capacity_check"),
        CheckConstraint("price_per_seat >= 0", name="rides_price_per_seat_check"),
        CheckConstraint(
            "status IN ('upcoming', 'full', 'in_progress', 'completed', 'cancelled')",
            name="rides_status_check",
        ),
        CheckConstraint("available_seats BETWEEN 0 AND capacity", name="rides_seats_range"),
        Index("rides_driver_idx", "driver_id", "departure_time"),
        Index("rides_start_idx", "start_lat", "start_lng"),
        Index("rides_end_idx", "end_lat", "end_lng"),
        Index("rides_departure_idx", "departure_time"),
        Index("rides_status_dep_idx", "status", "departure_time"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    start_lat: Mapped[float] = mapped_column(Double, nullable=False)
    start_lng: Mapped[float] = mapped_column(Double, nullable=False)
    start_address: Mapped[str] = mapped_column(String(255), nullable=False)
    end_lat: Mapped[float] = mapped_column(Double, nullable=False)
    end_lng: Mapped[float] = mapped_column(Double, nullable=False)
    end_address: Mapped[str] = mapped_column(String(255), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    available_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_seat: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'upcoming'")
    )
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # `selectin`, not the default lazy load: every read of a ride needs its driver (the `Ride`
    # schema embeds `UserPublic`), and a lazy load inside async code would raise.
    driver: Mapped[User] = relationship(lazy="selectin")
