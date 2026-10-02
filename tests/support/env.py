"""The environment the suite forces on the backend.

`apply()` must run **before** the backend package is imported, because
pydantic-settings reads the environment at import time. conftest.py calls it at
module level for exactly that reason.

Process environment wins over any `.env` file in pydantic-settings, so these
values override the worktree's `.env` without the suite ever reading it.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
OPENAPI_PATH = CONTRACTS_DIR / "openapi.yaml"
SCHEMA_SQL_PATH = CONTRACTS_DIR / "schema.sql"

# ── fixed test values (tests assert against these, so keep them stable) ──
API_PREFIX = "/api/v1"
CLERK_ISSUER = "https://clerk.test.ridematch.local"
CLERK_AUTHORIZED_PARTY = "http://localhost:5173"
CLERK_AUTHORIZED_PARTIES = CLERK_AUTHORIZED_PARTY
ADMIN_EMAIL = "first-admin@ridematch.test"
SEARCH_RADIUS_KM = 10.0
MATCH_MIN_SCORE = 40.0
CLERK_SECRET_KEY = "sk_test_not_a_real_clerk_key"
# The part after "whsec_" must be valid base64 (app/modules/webhooks/service.py
# base64-decodes it to get the HMAC key) - this is base64("test-webhook-signing-secret-32b").
CLERK_WEBHOOK_SIGNING_SECRET = "whsec_dGVzdC13ZWJob29rLXNpZ25pbmctc2VjcmV0LTMyYg=="

# CONTRACT.md §2: exp/nbf are checked with 5s leeway.
CLOCK_LEEWAY_SECONDS = 5

DEFAULT_DATABASE_URL = "postgresql+asyncpg://ridematch:ridematch@127.0.0.1:5434/ridematch_test"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/15"


def database_url() -> str:
    """The async SQLAlchemy URL of the test database."""
    return os.environ.get("TEST_DATABASE_URL") or DEFAULT_DATABASE_URL


def redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL") or DEFAULT_REDIS_URL


def asyncpg_dsn(url: str | None = None) -> str:
    """Turn a SQLAlchemy URL into the plain DSN asyncpg wants."""
    return (url or database_url()).replace("+asyncpg", "", 1)


def _guard_test_database(url: str) -> None:
    """Refuse to run against anything that is not obviously a test database.

    The suite truncates every table between tests; pointing it at the dev
    database would wipe Dvir's data.
    """
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in name.lower():
        raise RuntimeError(
            f"Refusing to run: TEST_DATABASE_URL points at database {name!r}, "
            "which does not look like a test database. The suite truncates "
            "every table between tests."
        )


def apply(clerk_public_key_pem: str) -> None:
    """Pin the backend's configuration for this test session."""
    url = database_url()
    _guard_test_database(url)

    os.environ.update(
        {
            "APP_ENV": "test",
            "API_PREFIX": API_PREFIX,
            "LOG_LEVEL": "WARNING",
            "CORS_ORIGINS": CLERK_AUTHORIZED_PARTY,
            # Both names point at the test database: whichever one the backend
            # reads, it can never reach the development database.
            "DATABASE_URL": url,
            "TEST_DATABASE_URL": url,
            "REDIS_URL": redis_url(),
            # CONTRACT.md §2 + D13: verify against our own public key, offline.
            "CLERK_JWT_KEY": clerk_public_key_pem,
            "CLERK_JWKS_URL": "",
            "CLERK_ISSUER": CLERK_ISSUER,
            "CLERK_AUTHORIZED_PARTIES": CLERK_AUTHORIZED_PARTIES,
            "CLERK_SECRET_KEY": CLERK_SECRET_KEY,
            "CLERK_WEBHOOK_SIGNING_SECRET": CLERK_WEBHOOK_SIGNING_SECRET,
            "SEARCH_RADIUS_KM": str(SEARCH_RADIUS_KM),
            "MATCH_MIN_SCORE": str(MATCH_MIN_SCORE),
            "EMAIL_BACKEND": "memory",
            "EMAIL_FROM": "noreply@ridematch.test",
            "JOBS_ENABLED": "false",
            "REMINDER_MINUTES_BEFORE": "60",
            "AUTO_COMPLETE_AFTER_HOURS": "12",
            "ADMIN_EMAIL": ADMIN_EMAIL,
        }
    )
