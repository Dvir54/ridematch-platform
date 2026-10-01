"""Factories that build users the way the contract says users come into being:
through POST /users/me/onboarding with a signed Clerk-style token.

Only the things the API deliberately offers no route for (is_admin, is_active)
are set with SQL - CONTRACT.md 4 says more admins are made "by script/SQL",
and deactivation is an admin endpoint that does not exist until Phase 6.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from . import clock
from .assertions import expect_status
from .db import TestDatabase
from .keys import TokenSigner, auth_header

DEFAULT_AGE = 30
DEFAULT_VEHICLE = {"make": "Toyota", "model": "Corolla", "color": "White", "plate": "12-345-67"}

# openapi.yaml Phone (0.4.0, D17): maxLength 20, pattern ^\+?[0-9 \-]{7,20}$.
# One primitive backs both OnboardingRequest.phone and UserUpdate.phone, so both
# paths are held to the same list here - that is what stops the two drifting.
VALID_PHONES = (
    "050-123-4567",
    "+972 50-123-4567",
    "1234567",
    "+1 555 010 9999",
)
INVALID_PHONES = {
    "letters": "call me",
    "alphanumeric": "abc",
    "too-short": "12345",
    "parenthesised": "+1 (555) 010-9999",
    "at-sign": "555@0101234",
    "too-long": "+" + "1" * 21,
    "empty": "",
}

_counter = itertools.count(1)

# Sentinel: pass OMIT as an override to drop a key from the payload entirely.
_OMIT = object()
OMIT = _OMIT


def unique_suffix() -> str:
    return f"{next(_counter):04d}"


def onboarding_payload(**overrides: Any) -> dict[str, Any]:
    """A minimal valid onboarding body. Pass overrides to break it on purpose."""
    payload: dict[str, Any] = {
        "name": "Test User",
        "date_of_birth": clock.birth_date_for_age(DEFAULT_AGE).isoformat(),
        "accepted_terms": True,
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not _OMIT}


@dataclass
class TestUser:
    """A user that exists in the database, plus the means to authenticate as them."""

    __test__ = False  # not a pytest test class

    id: int
    clerk_user_id: str
    email: str
    name: str
    profile: dict[str, Any] = field(repr=False)
    signer: TokenSigner = field(repr=False)

    def token(self, **overrides: Any) -> str:
        overrides.setdefault("sub", self.clerk_user_id)
        overrides.setdefault("email", self.email)
        return self.signer.sign(**overrides)

    @property
    def headers(self) -> dict[str, str]:
        return auth_header(self.token())

    def headers_with(self, **overrides: Any) -> dict[str, str]:
        return auth_header(self.token(**overrides))


class Users:
    """Creates users through the API, for tests that need one as a precondition."""

    def __init__(self, client: Any, signer: TokenSigner, db: TestDatabase) -> None:
        self.client = client
        self.signer = signer
        self.db = db

    # -- identities without a profile ------------------------------------
    def new_identity(self, *, email: str | None = None) -> tuple[str, str]:
        """A Clerk `sub`/email pair that has not onboarded yet."""
        suffix = unique_suffix()
        return f"user_test_{suffix}", email or f"user{suffix}@ridematch.test"

    def stranger_headers(self, **overrides: Any) -> dict[str, str]:
        """Auth headers for a valid token whose user has no RideMatch profile."""
        sub, email = self.new_identity()
        overrides.setdefault("sub", sub)
        overrides.setdefault("email", email)
        return auth_header(self.signer.sign(**overrides))

    # -- creation ---------------------------------------------------------
    async def onboard_response(
        self,
        *,
        clerk_user_id: str | None = None,
        email: str | None = None,
        token: str | None = None,
        **payload_overrides: Any,
    ) -> Any:
        """Raw POST /users/me/onboarding, for tests that assert on the failure."""
        if clerk_user_id is None or email is None:
            generated_sub, generated_email = self.new_identity(email=email)
            clerk_user_id = clerk_user_id or generated_sub
            email = email or generated_email
        if token is None:
            token = self.signer.sign(sub=clerk_user_id, email=email)
        return await self.client.post(
            "/users/me/onboarding",
            json=onboarding_payload(**payload_overrides),
            headers=auth_header(token),
        )

    async def create(
        self,
        *,
        clerk_user_id: str | None = None,
        email: str | None = None,
        is_admin: bool = False,
        is_active: bool = True,
        **payload_overrides: Any,
    ) -> TestUser:
        if clerk_user_id is None or email is None:
            generated_sub, generated_email = self.new_identity(email=email)
            clerk_user_id = clerk_user_id or generated_sub
            email = email or generated_email

        response = await self.onboard_response(
            clerk_user_id=clerk_user_id, email=email, **payload_overrides
        )
        profile = expect_status(response, 201)

        user = TestUser(
            id=profile["id"],
            clerk_user_id=clerk_user_id,
            email=profile["email"],
            name=profile["name"],
            profile=profile,
            signer=self.signer,
        )
        if is_admin and not profile["is_admin"]:
            await self.db.set_admin(user.id, True)
            user.profile["is_admin"] = True
        if not is_active:
            await self.db.set_active(user.id, False)
            user.profile["is_active"] = False
        return user

    async def create_driver(self, **kwargs: Any) -> TestUser:
        """A user with a vehicle, so they may offer rides (CONTRACT.md 4)."""
        kwargs.setdefault("vehicle", dict(DEFAULT_VEHICLE))
        return await self.create(**kwargs)

    async def create_admin(self, **kwargs: Any) -> TestUser:
        return await self.create(is_admin=True, **kwargs)

    async def deactivate(self, user: TestUser) -> None:
        await self.db.set_active(user.id, False)
        user.profile["is_active"] = False

    async def reactivate(self, user: TestUser) -> None:
        await self.db.set_active(user.id, True)
        user.profile["is_active"] = True
