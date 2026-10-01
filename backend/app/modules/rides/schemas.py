"""Pydantic mirrors of the ride schemas in openapi.yaml."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator

from app.modules.rides.models import Ride
from app.modules.users.schemas import UserPublic
from app.schemas import (
    ApiModel,
    InputDatetime,
    Latitude,
    Longitude,
    Money,
    MoneyIn,
    NotNull,
    UtcDatetime,
)

RideStatus = Literal["upcoming", "full", "in_progress", "completed", "cancelled"]
Address = Annotated[str, Field(min_length=1, max_length=255)]
Capacity = Annotated[int, Field(ge=1, le=8)]
Notes = Annotated[str, Field(max_length=1000)]

#: Location and time: locked once the ride has an approved passenger (CONTRACT.md §4 Rides).
LOCKED_FIELDS = (
    "start_lat",
    "start_lng",
    "start_address",
    "end_lat",
    "end_lng",
    "end_address",
    "departure_time",
)
#: Fields `PATCH` copies straight across (capacity needs the seat recount, preferences a merge).
PLAIN_FIELDS = (*LOCKED_FIELDS, "price_per_seat", "notes")


class RidePreferences(BaseModel):
    """Defaults the server fills in on read, so `Ride.preferences` is always complete."""

    smoking: bool = False
    pets: bool = False
    music: bool = True
    gender_only: bool = False


class RidePreferencesPatch(BaseModel):
    """Write shape: no defaults, and an absent key is left alone (CONTRACT.md D16).

    `StrictBool`, because openapi.yaml says `type: boolean` — `"yes"` is a 422.
    """

    smoking: NotNull[StrictBool] = None
    pets: NotNull[StrictBool] = None
    music: NotNull[StrictBool] = None
    gender_only: NotNull[StrictBool] = None


class RideCreate(BaseModel):
    start_lat: Latitude
    start_lng: Longitude
    start_address: Address
    end_lat: Latitude
    end_lng: Longitude
    end_address: Address
    #: Must be in the future; the service answers 422 DEPARTURE_IN_PAST.
    departure_time: InputDatetime
    capacity: Capacity
    price_per_seat: MoneyIn
    preferences: RidePreferencesPatch | None = None
    notes: Notes | None = None


class RideUpdate(BaseModel):
    """Every field optional; `PATCH /rides/{ride_id}` says which ones may change when."""

    # `NotNull`, because openapi.yaml marks only `notes` as nullable: an explicit `null` on any
    # of these is a 422 that names the field it came from.
    start_lat: NotNull[Latitude] = None
    start_lng: NotNull[Longitude] = None
    start_address: NotNull[Address] = None
    end_lat: NotNull[Latitude] = None
    end_lng: NotNull[Longitude] = None
    end_address: NotNull[Address] = None
    departure_time: NotNull[InputDatetime] = None
    capacity: NotNull[Capacity] = None
    price_per_seat: NotNull[MoneyIn] = None
    preferences: NotNull[RidePreferencesPatch] = None
    #: The only nullable field in openapi.yaml: `null` clears the notes.
    notes: Notes | None = None


class RideOut(ApiModel):
    """openapi.yaml #/components/schemas/Ride."""

    id: int
    driver: UserPublic
    start_lat: float
    start_lng: float
    start_address: str
    end_lat: float
    end_lng: float
    end_address: str
    departure_time: UtcDatetime
    capacity: int
    available_seats: int
    price_per_seat: Money
    status: RideStatus
    preferences: RidePreferences
    notes: str | None = None
    #: The driver's plate, for the driver and approved passengers only (CONTRACT.md §4 Vehicles).
    driver_vehicle_plate: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    @field_validator("preferences", mode="before")
    @classmethod
    def _fill_defaults(cls, value: Any) -> Any:
        return value or {}


def ride_out(ride: Ride, *, show_plate: bool) -> RideOut:
    """`Ride` plus the plate, which only some viewers may see."""
    out = RideOut.model_validate(ride)
    if show_plate:
        out.driver_vehicle_plate = (ride.driver.vehicle or {}).get("plate")
    return out
