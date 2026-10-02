"""Pydantic mirrors of the ride-request schemas in openapi.yaml."""

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field

from app.modules.requests.models import RideRequest
from app.modules.rides.schemas import RideOut, ride_out
from app.modules.users.schemas import UserPublic
from app.schemas import ApiModel, RequestStatus, UtcDatetime

if TYPE_CHECKING:
    from app.modules.rides.service import RideViewer

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


def request_out(request: RideRequest, viewer: "RideViewer") -> RideRequestOut:
    """The embedded ride goes through the same viewer as a standalone one, so the plate rule and
    `my_request` have one implementation rather than one per endpoint."""
    return RideRequestOut(
        id=request.id,
        ride=ride_out(request.ride, viewer),
        passenger=UserPublic.model_validate(request.passenger),
        seats_requested=request.seats_requested,
        status=request.status,
        requested_at=request.requested_at,
        responded_at=request.responded_at,
    )
