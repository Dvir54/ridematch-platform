"""User profile logic: onboarding, reading and updating (CONTRACT.md §4 Users / Vehicles)."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import exists, func, null, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import Conflict, NotFound, UnprocessableEntity
from app.modules.notifications import service as notifications_service
from app.modules.notifications.service import EmailContent
from app.modules.users.models import User
from app.modules.users.schemas import (
    OnboardingRequest,
    UserPreferences,
    UserPreferencesPatch,
    UserUpdate,
)

MINIMUM_AGE = 18
#: Preference keys where an explicit `null` is a real value rather than "leave it alone".
NULLABLE_PREFERENCE_KEYS = frozenset({"default_mode"})


def normalise_email(email: str) -> str:
    return email.strip().lower()


def age_on(day: date, born: date) -> int:
    """Whole years old on `day`."""
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def merge_preferences(stored: dict[str, Any] | None, patch: UserPreferencesPatch | None) -> dict:
    """Defaults, then what is stored, then the keys the client just sent (shallow merge).

    The `notifications` sub-object is merged too, rather than replaced.
    """
    merged = UserPreferences().model_dump(mode="json")
    for key, value in (stored or {}).items():
        if key == "notifications" and isinstance(value, dict):
            merged["notifications"].update(value)
        else:
            merged[key] = value

    if patch is None:
        return merged

    incoming = patch.model_dump(mode="json", exclude_unset=True)
    notifications = incoming.pop("notifications", None)
    if isinstance(notifications, dict):
        # All three keys are non-nullable booleans, so what was sent is what should land.
        merged["notifications"].update(notifications)
    for key, value in incoming.items():
        if value is not None or key in NULLABLE_PREFERENCE_KEYS:
            merged[key] = value
    return merged


#: `date_of_birth` is NOT NULL; the 18+ check already happened at onboarding (CONTRACT.md §4).
ANONYMISED_DATE_OF_BIRTH = date(1900, 1, 1)
ANONYMISED_CLERK_PREFIX = "deleted_"


def is_anonymised(user: User) -> bool:
    return user.clerk_user_id.startswith(ANONYMISED_CLERK_PREFIX)


def anonymise(user: User) -> None:
    """Remove the personal data of a deleted account (CONTRACT.md §4 Users). Rides, requests and
    ratings stay, so the other party's history is intact. Committing is the caller's business."""
    user.name = "Deleted user"
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.clerk_user_id = f"{ANONYMISED_CLERK_PREFIX}{user.id}"
    user.gender = None
    # SQL NULL, not the JSON value `null` a plain None would store in a JSONB column.
    user.vehicle = null()
    user.preferences = null()
    user.date_of_birth = ANONYMISED_DATE_OF_BIRTH
    user.is_active = False


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise NotFound("NOT_FOUND", "User not found.")
    return user


async def get_users_by_ids(db: AsyncSession, user_ids: Sequence[int]) -> dict[int, User]:
    """`{id: user}` in one query — for responses that embed several users at once."""
    wanted = set(user_ids)
    if not wanted:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(wanted)))).scalars().all()
    return {user.id: user for user in rows}


async def email_exists(db: AsyncSession, email: str) -> bool:
    stmt = select(exists().where(func.lower(User.email) == email))
    return bool((await db.execute(stmt)).scalar())


async def admin_exists(db: AsyncSession) -> bool:
    return bool((await db.execute(select(exists().where(User.is_admin)))).scalar())


def _welcome_email(user: User) -> EmailContent:
    return EmailContent(
        to=user.email,
        subject="Welcome to RideMatch",
        body=(
            f"Hi {user.name},\n\n"
            "Your RideMatch profile is ready. Offer a ride as a driver or search for one "
            "as a passenger — whichever way you're travelling.\n\n"
            "— RideMatch"
        ),
    )


async def onboard_user(
    db: AsyncSession,
    settings: Settings,
    *,
    clerk_user_id: str,
    email: str,
    data: OnboardingRequest,
    now: datetime,
) -> User:
    """Create the profile row for a fresh Clerk sign-up, and send the welcome notification."""
    if data.accepted_terms is not True:
        raise UnprocessableEntity(
            "TERMS_NOT_ACCEPTED",
            "You must accept the terms of service.",
            details=[{"field": "body.accepted_terms", "message": "Must be true."}],
        )
    if age_on(now.date(), data.date_of_birth) < MINIMUM_AGE:
        raise UnprocessableEntity(
            "UNDERAGE",
            f"You must be at least {MINIMUM_AGE} years old to use RideMatch.",
            details=[{"field": "body.date_of_birth", "message": f"Must be {MINIMUM_AGE}+."}],
        )

    email = normalise_email(email)
    if await email_exists(db, email):
        raise Conflict("EMAIL_ALREADY_EXISTS", "Another profile already uses this email.")

    # The first admin, outside production only: this email, while no admin exists yet
    # (CONTRACT.md §4 Users). Production admins come from `app.admin_cli`.
    is_admin = (
        not settings.is_production
        and bool(settings.admin_email)
        and email == normalise_email(settings.admin_email)
    )
    if is_admin and await admin_exists(db):
        is_admin = False

    preferences = merge_preferences(None, data.preferences)
    user = User(
        clerk_user_id=clerk_user_id,
        email=email,
        is_admin=is_admin,
        name=data.name,
        date_of_birth=data.date_of_birth,
        gender=data.gender.value if data.gender else None,
        is_active=True,
        terms_accepted_at=now,
        driver_rating_count=0,
        passenger_rating_count=0,
        preferences=preferences,
        vehicle=data.vehicle.model_dump() if data.vehicle else None,
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        detail = str(exc.orig)
        if "users_clerk_user_id_uq" in detail:
            raise Conflict("ALREADY_ONBOARDED", "This account is already onboarded.") from exc
        if "users_email_lower_uq" in detail:
            raise Conflict(
                "EMAIL_ALREADY_EXISTS", "Another profile already uses this email."
            ) from exc
        raise

    wants_email = bool(preferences.get("notifications", {}).get("email", True))
    await notifications_service.notify(
        db,
        settings,
        user_id=user.id,
        type="welcome",
        title="Welcome to RideMatch",
        message="Your profile is ready. Offer a ride, or find one.",
        email=_welcome_email(user) if wants_email else None,
        push=notifications_service.websocket_enabled(preferences),
        now=now,
    )
    await notifications_service.commit_and_push(db)
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    data: UserUpdate,
    *,
    now: datetime,
    open_rides: int,
) -> User:
    """Apply a PATCH /users/me body. `open_rides` gates removing the vehicle."""
    sent = data.model_fields_set
    if data.name is not None:
        user.name = data.name
    if "gender" in sent:
        user.gender = data.gender.value if data.gender else None
    if data.preferences is not None:
        user.preferences = merge_preferences(user.preferences, data.preferences)
    if "vehicle" in sent:
        if data.vehicle is None:
            if open_rides > 0:
                raise Conflict(
                    "VEHICLE_REQUIRED",
                    "You can't remove your vehicle while you have upcoming rides.",
                )
            user.vehicle = None
        else:
            user.vehicle = data.vehicle.model_dump()
    user.updated_at = now
    await db.commit()
    return user
