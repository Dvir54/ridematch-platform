"""Request dependencies: the token's claims, and the RideMatch user behind them.

CONTRACT.md §2: no profile row → 403 ONBOARDING_REQUIRED (except on `POST /users/me/onboarding`,
which uses `CurrentUserOrNone`), `is_active=false` → 403 ACCOUNT_DEACTIVATED.
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from app.auth.clerk import ClerkClaims, ClerkVerifier
from app.clock import Now
from app.config import Settings
from app.db import DbSession
from app.errors import Forbidden, Unauthenticated
from app.modules.users.models import User

#: `last_login_at` is refreshed at most this often (it feeds `active_users` in analytics).
LOGIN_TOUCH_INTERVAL = timedelta(hours=1)


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_settings_from_app)]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthenticated()
    return token.strip()


async def get_claims(request: Request) -> ClerkClaims:
    verifier: ClerkVerifier = request.app.state.clerk_verifier
    return await verifier.verify(_bearer_token(request))


Claims = Annotated[ClerkClaims, Depends(get_claims)]


async def _touch_last_login(db: DbSession, user: User, now: datetime) -> None:
    if user.last_login_at is None or now - user.last_login_at > LOGIN_TOUCH_INTERVAL:
        user.last_login_at = now
        await db.commit()


async def get_current_user_or_none(db: DbSession, claims: Claims, now: Now) -> User | None:
    """The caller's profile, or None when they haven't onboarded yet."""
    user = (
        await db.execute(select(User).where(User.clerk_user_id == claims.sub))
    ).scalar_one_or_none()
    if user is None:
        return None
    if not user.is_active:
        raise Forbidden("ACCOUNT_DEACTIVATED", "This account has been deactivated.")
    await _touch_last_login(db, user, now)
    return user


CurrentUserOrNone = Annotated[User | None, Depends(get_current_user_or_none)]


async def get_current_user(user: CurrentUserOrNone) -> User:
    if user is None:
        raise Forbidden("ONBOARDING_REQUIRED", "Complete onboarding to use RideMatch.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise Forbidden()
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
