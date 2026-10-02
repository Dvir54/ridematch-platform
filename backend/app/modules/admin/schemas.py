"""Pydantic mirrors of the admin schemas in openapi.yaml."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.feedback.schemas import RatingOut
from app.modules.requests.schemas import RideRequestOut
from app.modules.rides.schemas import RideOut
from app.modules.users.schemas import UserMe
from app.schemas import UtcDatetime

Reason = Annotated[str, Field(min_length=1, max_length=500)]


class ForceCancelRequest(BaseModel):
    reason: Reason


class AdminUserDetailOut(BaseModel):
    """openapi.yaml #/components/schemas/AdminUserDetail."""

    user: UserMe
    rides_as_driver: list[RideOut]
    requests_as_passenger: list[RideRequestOut]
    ratings_received: list[RatingOut]


class AnalyticsSummaryOut(BaseModel):
    """openapi.yaml #/components/schemas/AnalyticsSummary. `from`/`to` echo the query range."""

    model_config = ConfigDict(populate_by_name=True)

    from_: UtcDatetime = Field(alias="from")
    to: UtcDatetime
    rides_created: int
    rides_completed: int
    rides_cancelled: int
    completion_rate: float | None
    requests_created: int
    approval_rate: float | None
    active_users: int
    new_users: int
