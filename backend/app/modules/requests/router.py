"""`/rides/{ride_id}/requests` and `/requests/*` — thin routing only.

`/requests/mine` and `/requests/incoming` are declared before `/requests/{request_id}` so the
literal paths win.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import AppSettings, CurrentUser
from app.clock import Now
from app.db import DbSession
from app.modules.requests import service as requests_service
from app.modules.requests.models import REQUEST_STATUSES, RideRequest
from app.modules.requests.schemas import (
    RideRequestCreate,
    RideRequestOut,
    request_out,
)
from app.modules.rides import service as rides_service
from app.modules.users.models import User
from app.params import PageParams, StatusFilter, parse_status_filter
from app.schemas import RequestStatus

router = APIRouter(tags=["requests"])


async def _out(
    db: AsyncSession, requests: Sequence[RideRequest], user: User
) -> list[RideRequestOut]:
    """One viewer for the whole response, so the embedded rides cost one extra query."""
    viewer = await rides_service.viewer_for(db, [request.ride for request in requests], user)
    return [request_out(request, viewer) for request in requests]


@router.post(
    "/rides/{ride_id}/requests",
    response_model=RideRequestOut,
    status_code=201,
    summary="Ask the driver for seats",
)
async def create_request(
    ride_id: int,
    payload: RideRequestCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    now: Now,
) -> RideRequestOut:
    request = await requests_service.create_request(
        db, settings, ride_id=ride_id, passenger=user, data=payload, now=now
    )
    return (await _out(db, [request], user))[0]


@router.get(
    "/rides/{ride_id}/requests",
    response_model=list[RideRequestOut],
    summary="Every request on one of the caller's rides",
)
async def list_ride_requests(
    ride_id: int,
    user: CurrentUser,
    db: DbSession,
    status: RequestStatus | None = None,
) -> list[RideRequestOut]:
    requests = await requests_service.list_ride_requests(
        db, ride_id=ride_id, driver=user, status=status
    )
    return await _out(db, requests, user)


@router.get(
    "/requests/mine", response_model=list[RideRequestOut], summary="The caller's trips as passenger"
)
async def list_my_requests(
    user: CurrentUser,
    db: DbSession,
    page: PageParams,
    status: StatusFilter = None,
) -> list[RideRequestOut]:
    requests = await requests_service.list_my_requests(
        db,
        passenger_id=user.id,
        statuses=parse_status_filter(status, REQUEST_STATUSES),
        limit=page.limit,
        offset=page.offset,
    )
    return await _out(db, requests, user)


@router.get(
    "/requests/incoming",
    response_model=list[RideRequestOut],
    summary="Requests across all of the caller's rides",
)
async def list_incoming_requests(
    user: CurrentUser,
    db: DbSession,
    status: Annotated[RequestStatus, Query()] = "pending",
) -> list[RideRequestOut]:
    requests = await requests_service.list_incoming_requests(db, driver_id=user.id, status=status)
    return await _out(db, requests, user)


@router.get("/requests/{request_id}", response_model=RideRequestOut, summary="A single request")
async def get_request(request_id: int, user: CurrentUser, db: DbSession) -> RideRequestOut:
    request = await requests_service.get_request_or_404(db, request_id)
    requests_service.require_viewer(request, user)
    return (await _out(db, [request], user))[0]


@router.post(
    "/requests/{request_id}/approve", response_model=RideRequestOut, summary="Approve a request"
)
async def approve_request(
    request_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideRequestOut:
    request = await requests_service.approve_request(
        db, settings, request_id=request_id, driver=user, now=now
    )
    return (await _out(db, [request], user))[0]


@router.post(
    "/requests/{request_id}/reject", response_model=RideRequestOut, summary="Reject a request"
)
async def reject_request(
    request_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideRequestOut:
    request = await requests_service.reject_request(
        db, settings, request_id=request_id, driver=user, now=now
    )
    return (await _out(db, [request], user))[0]


@router.post(
    "/requests/{request_id}/cancel",
    response_model=RideRequestOut,
    summary="Cancel the caller's own request",
)
async def cancel_request(
    request_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideRequestOut:
    request = await requests_service.cancel_request(
        db, settings, request_id=request_id, passenger=user, now=now
    )
    return (await _out(db, [request], user))[0]
