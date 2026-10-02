"""`GET /search` — thin routing only; the formula lives in `service.py`."""

from fastapi import APIRouter

from app.auth.deps import AppSettings, CurrentUser
from app.clock import Now
from app.db import DbSession
from app.modules.rides import service as rides_service
from app.modules.rides.schemas import ride_out
from app.modules.search import service as search_service
from app.modules.search.schemas import (
    BudgetQuery,
    LatitudeQuery,
    LongitudeQuery,
    RideMatchOut,
    SeatsQuery,
    SortQuery,
    TimeQuery,
)
from app.params import PageParams

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[RideMatchOut], summary="Rides matching a trip")
async def search_rides(
    start_lat: LatitudeQuery,
    start_lng: LongitudeQuery,
    end_lat: LatitudeQuery,
    end_lng: LongitudeQuery,
    time: TimeQuery,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    now: Now,
    page: PageParams,
    budget: BudgetQuery = None,
    seats: SeatsQuery = 1,
    sort: SortQuery = "best_match",
) -> list[RideMatchOut]:
    query = search_service.query_for(
        user,
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        time=time,
        budget=budget,
        seats=seats,
        sort=sort,
    )
    matches = await search_service.search_rides(
        db,
        settings,
        user=user,
        query=query,
        limit=page.limit,
        offset=page.offset,
        now=now,
    )
    # One viewer for the whole page, so `my_request` and the plate cost one extra query in total.
    viewer = await rides_service.viewer_for(db, [match.ride for match in matches], user)
    return [
        RideMatchOut(
            ride=ride_out(match.ride, viewer),
            match_score=match.match_score,
            breakdown=match.breakdown,
            pickup_distance_km=match.pickup_distance_km,
            dropoff_distance_km=match.dropoff_distance_km,
        )
        for match in matches
    ]
