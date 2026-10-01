"""Settings, loaded from the repo-root `.env` (see `.env.example` for every key).

Every field has a default so that `import app.main` works without a `.env` file.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
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

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth (Clerk) ──
    clerk_secret_key: str = ""
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_jwt_key: str = ""
    clerk_authorized_parties: CommaList = []
    clerk_webhook_signing_secret: str = ""

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

    @field_validator("clerk_jwt_key", mode="before")
    @classmethod
    def _normalise_pem(cls, value: object) -> object:
        """A PEM in a single-line `.env` carries literal `\\n` sequences."""
        if isinstance(value, str):
            return value.replace("\\n", "\n").strip()
        return value

    @property
    def effective_database_url(self) -> str:
        """`APP_ENV=test` always uses the throwaway test database."""
        return self.test_database_url if self.app_env == "test" else self.database_url

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
