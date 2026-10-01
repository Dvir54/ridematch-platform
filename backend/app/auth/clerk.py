"""Clerk session-token verification (CONTRACT.md §2).

RS256 against Clerk's JWKS (cached), or against `CLERK_JWT_KEY` when that PEM is set, which needs
no network call — that is also how tests run: they sign with their own key pair, so the code path
here is identical and there is no test-only bypass.

Checked: signature, `exp`/`nbf` (5s leeway), `iss == CLERK_ISSUER`, and `azp` against
CLERK_AUTHORIZED_PARTIES.
Any failure → 401 UNAUTHENTICATED.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.config import Settings
from app.errors import Unauthenticated

logger = logging.getLogger(__name__)

LEEWAY_SECONDS = 5
ALGORITHMS = ["RS256"]


@dataclass(frozen=True, slots=True)
class ClerkClaims:
    """The claims RideMatch uses. `email` is a custom session-token claim."""

    sub: str
    email: str | None
    azp: str | None
    raw: dict[str, Any]

    def require_email(self) -> str:
        if not self.email:
            raise Unauthenticated(
                message=(
                    "The session token has no `email` claim. Add "
                    '{"email": "{{user.primary_email_address}}"} to the Clerk session token.'
                )
            )
        return self.email.strip().lower()


class ClerkVerifier:
    """Verifies tokens and caches the JWKS for the life of the app."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _fetch_jwks(self) -> dict[str, Any]:
        if not self._settings.clerk_jwks_url:
            raise Unauthenticated(message="Token verification is not configured.")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._settings.clerk_jwks_url)
            response.raise_for_status()
            return response.json()

    async def _jwks_key(self, kid: str | None) -> Any:
        async with self._lock:
            for attempt in (1, 2):
                if self._jwks is None:
                    try:
                        self._jwks = await self._fetch_jwks()
                    except Unauthenticated:
                        raise
                    except Exception as exc:
                        logger.warning("Fetching Clerk JWKS failed: %s", exc)
                        raise Unauthenticated(
                            message="Could not verify the session token."
                        ) from exc
                for key in self._jwks.get("keys", []):
                    if kid is None or key.get("kid") == kid:
                        return RSAAlgorithm.from_jwk(key)
                # Unknown kid: Clerk may have rotated keys, so refetch once.
                if attempt == 1:
                    self._jwks = None
        raise Unauthenticated(message="Unknown token signing key.")

    async def _signing_key(self, token: str) -> Any:
        if self._settings.clerk_jwt_key:
            return self._settings.clerk_jwt_key
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise Unauthenticated() from exc
        return await self._jwks_key(header.get("kid"))

    async def verify(self, token: str) -> ClerkClaims:
        if not token:
            raise Unauthenticated()
        key = await self._signing_key(token)
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                leeway=LEEWAY_SECONDS,
                issuer=self._settings.clerk_issuer or None,
                options={
                    "verify_aud": False,
                    "verify_iss": bool(self._settings.clerk_issuer),
                    "require": ["exp", "sub"],
                },
            )
        except jwt.PyJWTError as exc:
            raise Unauthenticated() from exc

        azp = payload.get("azp")
        parties = self._settings.clerk_authorized_parties
        if parties and azp not in parties:
            raise Unauthenticated(message="The token was issued for another party.")

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
            raise Unauthenticated()
        email = payload.get("email")
        return ClerkClaims(
            sub=sub,
            email=email if isinstance(email, str) else None,
            azp=azp if isinstance(azp, str) else None,
            raw=payload,
        )
