"""Pydantic mirrors of the ride-request schemas in openapi.yaml."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.modules.requests.models import RideRequest
from app.modules.rides.schemas import RideOut, ride_out
from app.modules.users.schemas import UserPublic
from app.schemas import ApiModel, UtcDatetime

RequestStatus = Literal["pending", "approved", "rejected", "cancelled"]
Seats = Annotated[int, Field(ge=1, le=8)]


class RideRequestCreate(BaseModel):
    seats_requested: Seats = 1


class RideRequestOut(ApiModel):
    """openapi.yaml #/components/schemas/RideRequest."""

    id: int
    ride: RideOut
    passenger: UserPublic
    seats_requested: int
    status: RequestStatus
    requested_at: UtcDatetime
    responded_at: UtcDatetime | None = None


def plate_visible(request: RideRequest, viewer_id: int) -> bool:
    """The ride's driver always; the passenger only once approved (CONTRACT.md §4 Vehicles).

    No query needed: the request itself says whether this viewer has an approved seat.
    """
    return viewer_id == request.ride.driver_id or (
        viewer_id == request.passenger_id and request.status == "approved"
    )


def request_out(request: RideRequest, *, viewer_id: int) -> RideRequestOut:
    return RideRequestOut(
        id=request.id,
        ride=ride_out(request.ride, show_plate=plate_visible(request, viewer_id)),
        passenger=UserPublic.model_validate(request.passenger),
        seats_requested=request.seats_requested,
        status=request.status,
        requested_at=request.requested_at,
        responded_at=request.responded_at,
    )
