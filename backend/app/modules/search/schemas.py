"""Pydantic mirrors of the search schemas in openapi.yaml, plus the `/search` query types."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BeforeValidator

from app.modules.rides.schemas import RideOut
from app.schemas import ApiModel, InputDatetime, money_from_string

SortOrder = Literal["best_match", "earliest", "cheapest"]


def _optional_money(value: object) -> object:
    """`budget` may be absent; when it is sent it follows the Money rule of CONTRACT.md §2."""
    return None if value is None else money_from_string(value)


# The `/search` query parameters. Constraints live in `Query` rather than in a separate `Field`,
# so each annotation carries exactly one `FieldInfo` and a 422 says `query.<name>`.
LatitudeQuery = Annotated[float, Query(ge=-90, le=90)]
LongitudeQuery = Annotated[float, Query(ge=-180, le=180)]
TimeQuery = Annotated[
    InputDatetime, Query(description="Desired departure time (ISO 8601 with offset)")
]
BudgetQuery = Annotated[
    Decimal | None,
    BeforeValidator(_optional_money),
    Query(description="Max acceptable price per seat"),
]
SeatsQuery = Annotated[int, Query(ge=1, le=8)]
SortQuery = Annotated[SortOrder, Query()]


class ScoreBreakdown(ApiModel):
    """openapi.yaml #/components/schemas/ScoreBreakdown — the components of CONTRACT.md §7.

    Reported as computed. Only `match_score` has a rounding rule in the contract, so rounding
    the parts too would risk making them disagree with the whole.
    """

    route: float
    time: float
    price: float
    rating: float
    preferences: float


class RideMatchOut(ApiModel):
    """openapi.yaml #/components/schemas/RideMatch."""

    ride: RideOut
    match_score: float
    breakdown: ScoreBreakdown
    pickup_distance_km: float
    dropoff_distance_km: float
