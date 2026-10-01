"""Shared schema primitives that mirror `openapi.yaml` #/components/schemas (CONTRACT.md §2).

- datetimes go out as UTC with a `Z` suffix, and any offset is accepted on the way in
- money is a decimal **string** with 2 places, never a float
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer


def _as_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_money(value: Decimal) -> str:
    return f"{value:.2f}"


def _as_aware(value: datetime) -> datetime:
    """A naive datetime on the way in is read as UTC; any offset is kept as sent."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_z, return_type=str)]
#: Datetimes in request bodies, so business logic only ever sees tz-aware values.
InputDatetime = Annotated[datetime, AfterValidator(_as_aware)]
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(_as_money, return_type=str),
]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class ApiModel(BaseModel):
    """Base for response models read straight off ORM objects."""

    model_config = ConfigDict(from_attributes=True)
