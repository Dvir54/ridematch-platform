"""`/users/*` — thin routing only; the rules live in `service.py`."""

from fastapi import APIRouter

from app.auth.deps import AppSettings, Claims, CurrentUser, CurrentUserOrNone
from app.clock import Now
from app.db import DbSession
from app.errors import Conflict
from app.modules.rides import service as rides_service
from app.modules.users import service as users_service
from app.modules.users.models import User
from app.modules.users.schemas import OnboardingRequest, UserMe, UserPublic, UserUpdate

router = APIRouter(tags=["users"])


@router.post(
    "/users/me/onboarding",
    response_model=UserMe,
    status_code=201,
    summary="Create the RideMatch profile for a fresh Clerk sign-up",
)
async def complete_onboarding(
    payload: OnboardingRequest,
    db: DbSession,
    settings: AppSettings,
    claims: Claims,
    existing: CurrentUserOrNone,
    now: Now,
) -> User:
    if existing is not None:
        raise Conflict("ALREADY_ONBOARDED", "This account is already onboarded.")
    return await users_service.onboard_user(
        db,
        settings,
        clerk_user_id=claims.sub,
        email=claims.require_email(),
        data=payload,
        now=now,
    )


@router.get("/users/me", response_model=UserMe, summary="The caller's own profile")
async def get_me(user: CurrentUser) -> User:
    return user


@router.patch("/users/me", response_model=UserMe, summary="Update profile and/or preferences")
async def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession, now: Now) -> User:
    open_rides = 0
    if "vehicle" in payload.model_fields_set and payload.vehicle is None:
        open_rides = await rides_service.count_open_rides_for_driver(db, user.id)
    return await users_service.update_user(db, user, payload, now=now, open_rides=open_rides)


@router.get("/users/{user_id}", response_model=UserPublic, summary="Public profile")
async def get_user_public(user_id: int, db: DbSession, _: CurrentUser) -> User:
    return await users_service.get_user_or_404(db, user_id)
