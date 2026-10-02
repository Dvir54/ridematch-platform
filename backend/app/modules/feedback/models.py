"""`ratings` — mirrors contracts/schema.sql."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.modules.users.models import User

ROLES_RATED = ("driver", "passenger")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint("role_rated IN ('driver', 'passenger')", name="ratings_role_rated_check"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ratings_score_check"),
        UniqueConstraint("ride_id", "from_user_id", "to_user_id", name="ratings_one_per_direction"),
        CheckConstraint("from_user_id <> to_user_id", name="ratings_not_self"),
        Index("ratings_to_user_idx", "to_user_id", "role_rated", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), nullable=False)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role_rated: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # `selectin`, like `Ride.driver`: the `Rating` schema embeds the rater as `UserPublic`, and a
    # lazy load inside async code would raise.
    from_user: Mapped[User] = relationship(lazy="selectin", foreign_keys=[from_user_id])
