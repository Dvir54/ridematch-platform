"""`/admin/*` — thin routing only; the rules live in `service.py`.

Admin-only (`CurrentAdmin`): `openapi.yaml` documents 401/403 on every path here, same as any
other authenticated endpoint (CONTRACT.md §2).
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.auth.deps import AppSettings, CurrentAdmin
from app.clock import Now
from app.db import DbSession
from app.modules.admin import service as admin_service
from app.modules.admin.schemas import AdminUserDetailOut, AnalyticsSummaryOut, ForceCancelRequest
from app.modules.feedback.schemas import RatingOut
from app.modules.requests.schemas import request_out
from app.modules.rides import service as rides_service
from app.modules.rides.models import RIDE_STATUSES
from app.modules.rides.schemas import RideOut, ride_out
from app.modules.users.schemas import UserMe
from app.params import PageParams, StatusFilter, parse_status_filter
from app.schemas import InputDatetime
from app.ws import WsRegistryDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/users", response_model=list[UserMe], summary="Admin only. Total count in X-Total-Count."
)
async def admin_list_users(
    response: Response,
    db: DbSession,
    _: CurrentAdmin,
    page: PageParams,
    q: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> list[UserMe]:
    users, total = await admin_service.list_users(
        db, q=q, is_active=is_active, is_admin=is_admin, limit=page.limit, offset=page.offset
    )
    response.headers["X-Total-Count"] = str(total)
    return users


@router.get("/users/{user_id}", response_model=AdminUserDetailOut, summary="User with history")
async def admin_get_user(user_id: int, db: DbSession, _: CurrentAdmin) -> AdminUserDetailOut:
    user, rides, requests, ratings = await admin_service.get_user_detail(db, user_id)
    viewer = rides_service.admin_viewer()
    return AdminUserDetailOut(
        user=user,
        rides_as_driver=[ride_out(ride, viewer) for ride in rides],
        requests_as_passenger=[request_out(request, viewer) for request in requests],
        ratings_received=[RatingOut.model_validate(rating) for rating in ratings],
    )


@router.post(
    "/users/{user_id}/deactivate", response_model=UserMe, summary="Deactivate + ban in Clerk"
)
async def admin_deactivate_user(
    user_id: int,
    admin: CurrentAdmin,
    db: DbSession,
    settings: AppSettings,
    now: Now,
    registry: WsRegistryDep,
) -> UserMe:
    return await admin_service.deactivate_user(
        db, settings, admin=admin, user_id=user_id, now=now, registry=registry
    )


@router.post(
    "/users/{user_id}/reactivate", response_model=UserMe, summary="Reactivate + unban in Clerk"
)
async def admin_reactivate_user(
    user_id: int, _: CurrentAdmin, db: DbSession, settings: AppSettings, now: Now
) -> UserMe:
    return await admin_service.reactivate_user(db, settings, user_id=user_id, now=now)


@router.get(
    "/rides", response_model=list[RideOut], summary="Admin only. Total count in X-Total-Count."
)
async def admin_list_rides(
    response: Response,
    db: DbSession,
    _: CurrentAdmin,
    page: PageParams,
    status: StatusFilter = None,
    driver_id: int | None = None,
    from_: Annotated[InputDatetime | None, Query(alias="from")] = None,
    to: InputDatetime | None = None,
) -> list[RideOut]:
    rides, total = await admin_service.list_rides(
        db,
        statuses=parse_status_filter(status, RIDE_STATUSES),
        driver_id=driver_id,
        from_=from_,
        to=to,
        limit=page.limit,
        offset=page.offset,
    )
    response.headers["X-Total-Count"] = str(total)
    viewer = rides_service.admin_viewer()
    return [ride_out(ride, viewer) for ride in rides]


@router.post(
    "/rides/{ride_id}/force-cancel", response_model=RideOut, summary="Cancel any non-terminal ride"
)
async def admin_force_cancel_ride(
    ride_id: int,
    payload: ForceCancelRequest,
    _: CurrentAdmin,
    db: DbSession,
    settings: AppSettings,
    now: Now,
) -> RideOut:
    ride = await admin_service.force_cancel_ride(
        db, settings, ride_id=ride_id, reason=payload.reason, now=now
    )
    return ride_out(ride, rides_service.admin_viewer())


@router.get("/analytics", response_model=AnalyticsSummaryOut, summary="Summary for a date range")
async def admin_analytics(
    db: DbSession,
    _: CurrentAdmin,
    from_: Annotated[InputDatetime, Query(alias="from")],
    to: InputDatetime,
) -> AnalyticsSummaryOut:
    return await admin_service.get_analytics(db, from_=from_, to=to)
