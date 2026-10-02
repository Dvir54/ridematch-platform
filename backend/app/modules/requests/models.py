"""`ride_requests` — mirrors contracts/schema.sql."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.modules.rides.models import Ride
from app.modules.users.models import User

REQUEST_STATUSES = ("pending", "approved", "rejected", "cancelled")
# Statuses that block a second request from the same passenger (CONTRACT.md §8, D2).
BLOCKING_REQUEST_STATUSES = ("pending", "approved", "rejected")


class RideRequest(Base):
    __tablename__ = "ride_requests"
    __table_args__ = (
        CheckConstraint(
            "seats_requested BETWEEN 1 AND 8", name="ride_requests_seats_requested_check"
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ride_requests_status_check",
        ),
        # One non-cancelled request per passenger per ride: re-requesting is possible only after
        # the passenger's own cancel; a driver's reject is final.
        Index(
            "ride_requests_active_uq",
            "ride_id",
            "passenger_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved', 'rejected')"),
        ),
        Index("ride_requests_ride_idx", "ride_id", "status"),
        Index("ride_requests_passenger_idx", "passenger_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), nullable=False)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    seats_requested: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Both are always needed: the `RideRequest` schema embeds the full ride and the passenger.
    ride: Mapped[Ride] = relationship(lazy="selectin")
    passenger: Mapped[User] = relationship(lazy="selectin")
