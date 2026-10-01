"""Pydantic mirrors of the user schemas in openapi.yaml."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.schemas import ApiModel, NotNull, UtcDatetime

#: openapi.yaml #/components/schemas/Phone — digits, spaces, hyphens, parentheses, dots and
#: an optional leading `+` (CONTRACT.md D17, widened by D18).
PHONE_PATTERN = r"^\+?[0-9 ().\-]{7,20}$"


class Gender(StrEnum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class Mode(StrEnum):
    driver = "driver"
    passenger = "passenger"


Theme = Literal["light", "dark", "system"]
Name = Annotated[str, Field(min_length=1, max_length=100)]
#: One format for every write path — openapi.yaml #/components/schemas/Phone (CONTRACT.md D17).
Phone = Annotated[str, Field(max_length=20, pattern=PHONE_PATTERN)]


class NotificationPrefs(BaseModel):
    """Defaults the server fills in on read."""

    email: bool = True
    push: bool = True
    websocket: bool = True


class UserPreferences(BaseModel):
    default_mode: Mode | None = None
    smoking: bool = False
    pets: bool = False
    notifications: NotificationPrefs = NotificationPrefs()
    language: str = "en"
    theme: Theme = "system"


class NotificationPrefsPatch(BaseModel):
    """Only the keys the client actually sent are merged (CONTRACT.md §4 Users).

    `StrictBool` here and in `UserPreferencesPatch`/`OnboardingRequest`: openapi.yaml says
    `type: boolean`, so `"yes"` is not a boolean. The response models stay lenient, because
    coercing a stored oddity beats turning a read into a 500.
    """

    email: NotNull[StrictBool] = None
    push: NotNull[StrictBool] = None
    websocket: NotNull[StrictBool] = None


class UserPreferencesPatch(BaseModel):
    """`default_mode` is the one key openapi.yaml marks nullable — `null` genuinely clears it."""

    default_mode: Mode | None = None
    smoking: NotNull[StrictBool] = None
    pets: NotNull[StrictBool] = None
    notifications: NotNull[NotificationPrefsPatch] = None
    language: NotNull[str] = None
    theme: NotNull[Theme] = None


class Vehicle(BaseModel):
    make: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=50)
    color: str = Field(min_length=1, max_length=30)
    plate: str = Field(min_length=2, max_length=15)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("plate")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class VehiclePublic(BaseModel):
    """The vehicle without the plate — what anyone may see (CONTRACT.md §4 Vehicles)."""

    make: str
    model: str
    color: str


def _vehicle_public(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: value.get(key) for key in ("make", "model", "color")}
    return value


class OnboardingRequest(BaseModel):
    name: Name
    phone: Phone | None = None
    date_of_birth: date
    gender: Gender | None = None
    preferences: NotNull[UserPreferencesPatch] = None
    vehicle: Vehicle | None = None
    # `false` is enforced in the service so the failure carries TERMS_NOT_ACCEPTED rather than
    # VALIDATION_ERROR; a non-boolean is a plain shape error.
    accepted_terms: StrictBool


class UserUpdate(BaseModel):
    """`phone`, `gender` and `vehicle` are the nullable ones in openapi.yaml; the rest are not."""

    name: NotNull[Name] = None
    phone: Phone | None = None
    gender: Gender | None = None
    preferences: NotNull[UserPreferencesPatch] = None
    #: Full replace; null removes it (409 VEHICLE_REQUIRED while the user has open rides).
    vehicle: Vehicle | None = None


class UserMe(ApiModel):
    """The caller's own full profile (also used in admin views)."""

    id: int
    # Plain `str`: this mirrors the email Clerk already verified, so re-validating it
    # on the way out could only turn good data into a 500.
    email: str
    name: str
    phone: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    is_admin: bool
    is_active: bool
    driver_rating: float | None = None
    driver_rating_count: int
    passenger_rating: float | None = None
    passenger_rating_count: int
    preferences: UserPreferences
    vehicle: Vehicle | None = None
    created_at: UtcDatetime
    last_login_at: UtcDatetime | None = None

    @field_validator("preferences", mode="before")
    @classmethod
    def _fill_defaults(cls, value: Any) -> Any:
        return value or {}


class UserPublic(ApiModel):
    """What other users may see. No email/phone/DOB."""

    id: int
    name: str
    driver_rating: float | None = None
    driver_rating_count: int
    passenger_rating: float | None = None
    passenger_rating_count: int
    vehicle: VehiclePublic | None = None
    created_at: UtcDatetime

    @field_validator("vehicle", mode="before")
    @classmethod
    def _strip_plate(cls, value: Any) -> Any:
        return _vehicle_public(value)
