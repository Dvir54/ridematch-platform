"""Pydantic mirrors of the ride schemas in openapi.yaml."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from app.modules.rides.models import Ride
from app.modules.users.schemas import UserPublic
from app.schemas import ApiModel, InputDatetime, Latitude, Longitude, Money, UtcDatetime

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

    smoking: StrictBool | None = None
    pets: StrictBool | None = None
    music: StrictBool | None = None
    gender_only: StrictBool | None = None


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
    price_per_seat: Money
    preferences: RidePreferencesPatch | None = None
    notes: Notes | None = None


class RideUpdate(BaseModel):
    """Every field optional; `PATCH /rides/{ride_id}` says which ones may change when."""

    start_lat: Latitude | None = None
    start_lng: Longitude | None = None
    start_address: Address | None = None
    end_lat: Latitude | None = None
    end_lng: Longitude | None = None
    end_address: Address | None = None
    departure_time: InputDatetime | None = None
    capacity: Capacity | None = None
    price_per_seat: Money | None = None
    preferences: RidePreferencesPatch | None = None
    #: The only nullable field in openapi.yaml: `null` clears the notes.
    notes: Notes | None = None

    @model_validator(mode="after")
    def _reject_nulls(self) -> "RideUpdate":
        """openapi.yaml marks only `notes` as nullable, so an explicit `null` elsewhere is a 422."""
        nulled = [
            field
            for field in self.model_fields_set
            if field != "notes" and getattr(self, field) is None
        ]
        if nulled:
            raise ValueError(f"may not be null: {', '.join(sorted(nulled))}")
        return self


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
