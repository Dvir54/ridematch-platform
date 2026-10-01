"""RSA key pair and Clerk-session-token signer (CONTRACT.md §2, D13).

Tests never call Clerk. We generate a key pair, hand the public half to the
backend as `CLERK_JWT_KEY`, and sign tokens with the private half using the
same claims Clerk puts in a session token. The backend's verification path is
identical to production; only the key differs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import env

KEY_ID = "test-key-1"


@dataclass(frozen=True)
class KeyPair:
    private_pem: str
    public_pem: str

    @classmethod
    def generate(cls, bits: int = 2048) -> KeyPair:
        key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        public_pem = (
            key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        return cls(private_pem=private_pem, public_pem=public_pem)


class TokenSigner:
    """Signs tokens that look exactly like Clerk session tokens.

    Every parameter can be overridden so the auth tests can produce the broken
    variants the backend must reject.
    """

    def __init__(
        self,
        private_pem: str,
        *,
        issuer: str = env.CLERK_ISSUER,
        azp: str = env.CLERK_AUTHORIZED_PARTY,
    ) -> None:
        self._private_pem = private_pem
        self.issuer = issuer
        self.azp = azp

    def claims(
        self,
        *,
        sub: str,
        email: str | None = None,
        issuer: str | None = None,
        azp: str | None = None,
        expires_in: int = 60,
        not_before: int = 0,
        issued_at_offset: int = 0,
        extra_claims: dict[str, Any] | None = None,
        drop_claims: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Build the claim set Clerk would put in a session token.

        `expires_in` / `not_before` / `issued_at_offset` are seconds relative to
        now, so negative values produce expired or not-yet-valid tokens.
        """
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": sub,
            "iss": self.issuer if issuer is None else issuer,
            "azp": self.azp if azp is None else azp,
            "iat": now + issued_at_offset,
            "nbf": now + not_before,
            "exp": now + expires_in,
            "sid": f"sess_{uuid.uuid4().hex[:16]}",
            "jti": uuid.uuid4().hex[:16],
            "v": 2,
        }
        if email is not None:
            claims["email"] = email
        if extra_claims:
            claims.update(extra_claims)
        for name in drop_claims:
            claims.pop(name, None)
        return claims

    def sign(
        self,
        *,
        algorithm: str = "RS256",
        key: str | None = None,
        **claim_kwargs: Any,
    ) -> str:
        """Return a signed JWT. Pass `key` to sign with the wrong key."""
        return jwt.encode(
            self.claims(**claim_kwargs),
            key if key is not None else self._private_pem,
            algorithm=algorithm,
            headers={"kid": KEY_ID},
        )


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── deliberately malformed tokens, for the auth tests ───────────────────
def _segment(data: dict[str, Any]) -> bytes:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def forge_unsigned(claims: dict[str, Any]) -> str:
    """An `alg: none` token. A backend that honours it accepts anyone."""
    header = _segment({"alg": "none", "typ": "JWT"})
    return (header + b"." + _segment(claims) + b".").decode()


def forge_hs256(claims: dict[str, Any], secret: str) -> str:
    """An HS256 token signed with the RSA *public* key as the HMAC secret.

    The classic algorithm-confusion attack: a verifier that trusts the header's
    `alg` instead of pinning RS256 will accept this from anyone who can read
    the public key. PyJWT refuses to build it, so it is assembled by hand.
    """
    signing_input = _segment({"alg": "HS256", "typ": "JWT"}) + b"." + _segment(claims)
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()
