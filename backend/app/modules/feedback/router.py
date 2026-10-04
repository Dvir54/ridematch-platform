"""`/ratings*` and `/users/{user_id}/ratings` — thin routing only; the rules live in `service.py`.

`/ratings/pending` is declared before `/ratings` so neither path can shadow the other, and the
public rating list lives here rather than in the users router because it is a ratings read.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.deps import AppSettings, CurrentUser
from app.clock import Now
from app.db import DbSession
from app.modules.feedback import service as feedback_service
from app.modules.feedback.schemas import (
    PendingRatingOut,
    RatingCreate,
    RatingOut,
    RoleRated,
    UserStatsOut,
)
from app.modules.rides import service as rides_service
from app.modules.rides.schemas import ride_out
from app.params import PageParams

router = APIRouter(tags=["ratings"])


@router.get(
    "/ratings/pending",
    response_model=list[PendingRatingOut],
    summary="Ratings the caller still owes on completed rides",
)
async def list_pending_ratings(
    user: CurrentUser, db: DbSession, now: Now
) -> list[PendingRatingOut]:
    pending = await feedback_service.list_pending_ratings(db, user=user, now=now)
    # One viewer query for every ride in the response, embedded ones included.
    viewer = await rides_service.viewer_for(db, [ride for ride, _, _ in pending], user)
    return [
        PendingRatingOut(ride=ride_out(ride, viewer), to_user=ratee, role_rated=role)
        for ride, ratee, role in pending
    ]


@router.post(
    "/ratings",
    response_model=RatingOut,
    status_code=201,
    summary="Rate someone you rode with on a completed ride",
)
async def create_rating(
    payload: RatingCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    now: Now,
) -> RatingOut:
    rating = await feedback_service.create_rating(db, settings, rater=user, data=payload, now=now)
    return RatingOut.model_validate(rating)


#: `/users/me/stats` counts rides and requests, so it can only live in a module that may import
#: them — which the users module, being further in (backend/README.md), is not. It keeps the
#: `users` tag of `openapi.yaml` regardless.
@router.get(
    "/users/me/stats",
    response_model=UserStatsOut,
    tags=["users"],
    summary="Counters for driver Home and passenger Profile",
)
async def get_my_stats(user: CurrentUser, db: DbSession) -> UserStatsOut:
    return UserStatsOut.model_validate(await feedback_service.user_stats(db, user_id=user.id))


@router.get(
    "/users/{user_id}/ratings",
    response_model=list[RatingOut],
    summary="Ratings a user received, newest first",
)
async def list_user_ratings(
    user_id: int,
    db: DbSession,
    page: PageParams,
    _: CurrentUser,
    role_rated: Annotated[RoleRated | None, Query()] = None,
) -> list[RatingOut]:
    ratings = await feedback_service.list_user_ratings(
        db,
        user_id=user_id,
        role_rated=role_rated,
        limit=page.limit,
        offset=page.offset,
    )
    return [RatingOut.model_validate(rating) for rating in ratings]
