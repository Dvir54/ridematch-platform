"""Settings, loaded from the repo-root `.env` (see `.env.example` for every key).

Every field has a default so that `import app.main` works without a `.env` file.
"""

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# app/config.py -> app -> backend -> repo root (where .env lives)
REPO_ROOT = Path(__file__).resolve().parents[2]

CommaList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # A startup failure is printed to the host's deploy log; never echo the secrets in it.
        hide_input_in_errors=True,
    )

    # ── App ──
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    cors_origins: CommaList = ["http://localhost:5173", "http://localhost:3000"]
    log_level: str = "INFO"

    # ── PostgreSQL ──
    database_url: str = "postgresql+asyncpg://ridematch:ridematch@localhost:5434/ridematch"
    test_database_url: str = (
        "postgresql+asyncpg://ridematch:ridematch@localhost:5434/ridematch_test"
    )

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_command_timeout_seconds: float = 30.0

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth (Clerk) ──
    clerk_secret_key: str = ""
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_jwt_key: str = ""
    clerk_authorized_parties: CommaList = []
    clerk_webhook_signing_secret: str = ""

    # ── WebSocket ──
    ws_auth_timeout_seconds: float = 10.0

    # ── Matching ──
    search_radius_km: float = 10.0
    match_min_score: float = 40.0

    # ── Email ──
    email_backend: Literal["console", "smtp", "memory"] = "console"
    email_from: str = "noreply@ridematch.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # ── Background jobs ──
    jobs_enabled: bool = True
    reminder_minutes_before: int = 60
    auto_complete_after_hours: int = 12

    # ── Admin ──
    admin_email: str = ""

    @field_validator("cors_origins", "clerk_authorized_parties", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        """`CommaList` fields come from the environment as `a,b` rather than JSON."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("database_url", "test_database_url", mode="after")
    @classmethod
    def _asyncpg_scheme(cls, value: str) -> str:
        """Hosts hand out `postgres://` or `postgresql://`; SQLAlchemy needs the asyncpg driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @field_validator("clerk_jwt_key", mode="before")
    @classmethod
    def _normalise_pem(cls, value: object) -> object:
        """A PEM in a single-line `.env` carries literal `\\n` sequences."""
        if isinstance(value, str):
            return value.replace("\\n", "\n").strip()
        return value

    @model_validator(mode="after")
    def _production_must_be_complete(self) -> "Settings":
        """Fail fast at import if production is misconfigured (CONTRACT.md §2), all at once."""
        if self.is_production:
            problems = production_problems(self)
            if problems:
                raise ValueError(
                    "Invalid production configuration:\n" + "\n".join(f"- {p}" for p in problems)
                )
        return self

    @property
    def effective_database_url(self) -> str:
        """`APP_ENV=test` always uses the throwaway test database."""
        return self.test_database_url if self.app_env == "test" else self.database_url

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _origin_problems(name: str, origins: list[str]) -> list[str]:
    if not origins:
        return [f"{name} must not be empty"]
    problems = []
    for origin in origins:
        if "*" in origin or not origin.startswith("https://") or _host(origin) in LOCAL_HOSTS:
            problems.append(f"{name} entry {origin!r} must be https and not localhost or '*'")
    return problems


def production_problems(s: Settings) -> list[str]:
    """Every rule `APP_ENV=production` enforces; an empty list means the config is usable."""
    problems: list[str] = []

    if not s.clerk_issuer.startswith("https://"):
        problems.append("CLERK_ISSUER must be set and start with https://")
    elif _host(s.clerk_issuer).endswith(".clerk.accounts.dev"):
        problems.append("CLERK_ISSUER is a Clerk development instance (*.clerk.accounts.dev)")

    try:
        key = load_pem_public_key(s.clerk_jwt_key.encode())
        if not isinstance(key, RSAPublicKey):
            problems.append("CLERK_JWT_KEY must be an RSA public key")
    except ValueError:
        problems.append("CLERK_JWT_KEY must be set to Clerk's PEM public key")

    problems += _origin_problems("CLERK_AUTHORIZED_PARTIES", s.clerk_authorized_parties)
    problems += _origin_problems("CORS_ORIGINS", s.cors_origins)
    for origin in s.cors_origins:
        if origin not in s.clerk_authorized_parties:
            problems.append(f"CORS_ORIGINS entry {origin!r} is not in CLERK_AUTHORIZED_PARTIES")

    if not s.clerk_secret_key.startswith("sk_live_"):
        problems.append("CLERK_SECRET_KEY must be a live key (sk_live_...)")

    secret = s.clerk_webhook_signing_secret
    try:
        if not secret.startswith("whsec_"):
            raise ValueError
        base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except (ValueError, binascii.Error):
        problems.append("CLERK_WEBHOOK_SIGNING_SECRET must be a whsec_... signing secret")

    for name, url in (("DATABASE_URL", s.database_url), ("REDIS_URL", s.redis_url)):
        host = _host(url)
        if not host or host in LOCAL_HOSTS:
            problems.append(f"{name} must be set to a non-localhost server")

    if s.email_backend != "smtp":
        problems.append("EMAIL_BACKEND must be smtp")
    if not s.smtp_host:
        problems.append("SMTP_HOST must be set")
    if not s.email_from or s.email_from.endswith(".local"):
        problems.append("EMAIL_FROM must be a real sending address (not *.local)")

    if s.admin_email:
        problems.append("ADMIN_EMAIL must be empty; grant admins with `python -m app.admin_cli`")

    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
