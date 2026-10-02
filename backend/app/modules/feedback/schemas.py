"""Pydantic mirrors of the rating schemas in openapi.yaml."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.modules.rides.schemas import RideOut
from app.modules.users.schemas import UserPublic
from app.schemas import ApiModel, UtcDatetime

#: openapi.yaml #/components/schemas/RoleRated — the role of the person being rated.
RoleRated = Literal["driver", "passenger"]

Tags = Annotated[list[Annotated[str, Field(max_length=30)]], Field(max_length=10)]


class RatingCreate(BaseModel):
    """`role_rated` is derived server-side from who rated whom, so it isn't in the body."""

    ride_id: int
    to_user_id: int
    score: Annotated[int, Field(ge=1, le=5)]
    comment: Annotated[str | None, Field(max_length=1000)] = None
    tags: Tags = []

    @field_validator("tags")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        """openapi.yaml marks `tags` `uniqueItems`, so a repeat is invalid input, not something
        to quietly clean up — silently deduplicating would hide a client bug behind a 201."""
        duplicates = sorted({tag for tag in value if value.count(tag) > 1})
        if duplicates:
            raise ValueError(f"must not repeat a tag: {', '.join(duplicates)}")
        return value


class RatingOut(ApiModel):
    """openapi.yaml #/components/schemas/Rating."""

    id: int
    ride_id: int
    from_user: UserPublic
    to_user_id: int
    role_rated: RoleRated
    score: int
    comment: str | None = None
    tags: list[str]
    created_at: UtcDatetime


class PendingRatingOut(BaseModel):
    """openapi.yaml #/components/schemas/PendingRating — one counterpart still owed a rating."""

    ride: RideOut
    to_user: UserPublic
    role_rated: RoleRated


class DriverStats(BaseModel):
    """Each counter is defined in CONTRACT.md D21."""

    rides_offered: int
    rides_completed: int
    upcoming_rides: int
    #: The driver Home badge.
    pending_requests: int
    passengers_carried: int


class PassengerStats(BaseModel):
    trips_requested: int
    trips_completed: int
    upcoming_trips: int


class UserStatsOut(BaseModel):
    """openapi.yaml #/components/schemas/UserStats."""

    as_driver: DriverStats
    as_passenger: PassengerStats
