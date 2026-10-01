"""Shared schema primitives that mirror `openapi.yaml` #/components/schemas (CONTRACT.md §2).

- datetimes go out as UTC with a `Z` suffix, and any offset is accepted on the way in
- money is a decimal **string**, never a JSON number, and always goes out with 2 places
"""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)

#: openapi.yaml #/components/schemas/Money, anchored with `fullmatch`.
MONEY_PATTERN = re.compile(r"\d{1,8}(\.\d{1,2})?")


def _as_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_money(value: Decimal) -> str:
    return f"{value:.2f}"


def _as_aware(value: datetime) -> datetime:
    """A naive datetime on the way in is read as UTC; any offset is kept as sent."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _money_from_string(value: object) -> object:
    """openapi.yaml types Money as a `string`, which is exactly what keeps a float out.

    Pydantic would happily read `25.5` into a `Decimal`, so the check has to be explicit.
    """
    if isinstance(value, str) and MONEY_PATTERN.fullmatch(value):
        return Decimal(value)
    raise ValueError('must be a decimal string with up to 2 places, e.g. "25.50"')


def _reject_null(value: object) -> object:
    if value is None:
        raise ValueError("may not be null")
    return value


T = TypeVar("T")

UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_z, return_type=str)]
#: Datetimes in request bodies, so business logic only ever sees tz-aware values.
InputDatetime = Annotated[datetime, AfterValidator(_as_aware)]
#: Money on the way **out**: the value comes from the DB as a `Decimal`.
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(_as_money, return_type=str),
]
#: Money on the way **in**: a decimal string only (CONTRACT.md §2 — "Never a float").
MoneyIn = Annotated[
    Decimal,
    BeforeValidator(_money_from_string),
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(_as_money, return_type=str),
]
#: A field that may be **absent** from a PATCH body ("leave it alone") but may not be `null`,
#: which is how openapi.yaml marks every property it doesn't give a `"null"` type. Rejecting the
#: null per field rather than per body is what puts the field name in `details[].field`.
NotNull = Annotated[T | None, BeforeValidator(_reject_null)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class ApiModel(BaseModel):
    """Base for response models read straight off ORM objects."""

    model_config = ConfigDict(from_attributes=True)
