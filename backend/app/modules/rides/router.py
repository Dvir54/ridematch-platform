"""`/rides/*` — thin routing only; the rules live in `service.py`.

`/rides/mine` is declared before `/rides/{ride_id}` so the literal path wins.
"""

from fastapi import APIRouter

from app.auth.deps import AppSettings, CurrentUser
from app.clock import Now
from app.db import DbSession
from app.modules.rides import service as rides_service
from app.modules.rides.models import RIDE_STATUSES
from app.modules.rides.schemas import RideCreate, RideOut, RideUpdate, ride_out
from app.params import PageParams, StatusFilter, parse_status_filter

router = APIRouter(tags=["rides"])


@router.post("/rides", response_model=RideOut, status_code=201, summary="Offer a ride")
async def create_ride(payload: RideCreate, user: CurrentUser, db: DbSession, now: Now) -> RideOut:
    ride = await rides_service.create_ride(db, driver=user, data=payload, now=now)
    return ride_out(ride, show_plate=True)


@router.get("/rides/mine", response_model=list[RideOut], summary="Rides the caller offers")
async def list_my_rides(
    user: CurrentUser,
    db: DbSession,
    page: PageParams,
    status: StatusFilter = None,
) -> list[RideOut]:
    rides = await rides_service.list_my_rides(
        db,
        driver_id=user.id,
        statuses=parse_status_filter(status, RIDE_STATUSES),
        limit=page.limit,
        offset=page.offset,
    )
    return [ride_out(ride, show_plate=True) for ride in rides]


@router.get("/rides/{ride_id}", response_model=RideOut, summary="A single ride")
async def get_ride(ride_id: int, user: CurrentUser, db: DbSession) -> RideOut:
    ride = await rides_service.get_ride_or_404(db, ride_id)
    show_plate = await rides_service.plate_visible(db, ride, user.id)
    return ride_out(ride, show_plate=show_plate)


@router.patch("/rides/{ride_id}", response_model=RideOut, summary="Edit a ride")
async def update_ride(
    ride_id: int, payload: RideUpdate, user: CurrentUser, db: DbSession, now: Now
) -> RideOut:
    ride = await rides_service.update_ride(db, ride_id=ride_id, driver=user, data=payload, now=now)
    return ride_out(ride, show_plate=True)


@router.post("/rides/{ride_id}/cancel", response_model=RideOut, summary="Cancel a ride")
async def cancel_ride(
    ride_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideOut:
    ride = await rides_service.cancel_ride(db, settings, ride_id=ride_id, driver=user, now=now)
    return ride_out(ride, show_plate=True)


@router.post("/rides/{ride_id}/start", response_model=RideOut, summary="Start a ride")
async def start_ride(
    ride_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideOut:
    ride = await rides_service.start_ride(db, settings, ride_id=ride_id, driver=user, now=now)
    return ride_out(ride, show_plate=True)


@router.post("/rides/{ride_id}/complete", response_model=RideOut, summary="Complete a ride")
async def complete_ride(
    ride_id: int, user: CurrentUser, db: DbSession, settings: AppSettings, now: Now
) -> RideOut:
    ride = await rides_service.complete_ride(db, settings, ride_id=ride_id, driver=user, now=now)
    return ride_out(ride, show_plate=True)
