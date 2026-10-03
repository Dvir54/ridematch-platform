"""APP_ENV=production fails fast on a weak or incomplete config (CONTRACT.md §2, plan §3.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from support.keys import KeyPair

KEYS = KeyPair.generate()


def valid_production(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "app_env": "production",
        "clerk_issuer": "https://clerk.ridematch.app",
        "clerk_jwt_key": KEYS.public_pem,
        "clerk_authorized_parties": "https://app.ridematch.app",
        "cors_origins": "https://app.ridematch.app",
        "clerk_secret_key": "sk_live_abc",
        "clerk_webhook_signing_secret": "whsec_dGVzdC13ZWJob29rLXNpZ25pbmctc2VjcmV0LTMyYg==",
        "database_url": "postgresql://u:p@db.internal:5432/ridematch",
        "redis_url": "redis://kv.internal:6379/0",
        "email_backend": "smtp",
        "smtp_host": "smtp.example.com",
        "email_from": "noreply@ridematch.app",
        "admin_email": "",
    }
    values.update(overrides)
    return values


def build(**overrides: object):
    from app.config import Settings

    return Settings(_env_file=None, **valid_production(**overrides))


def test_a_complete_production_config_passes() -> None:
    settings = build()
    assert settings.is_production


@pytest.mark.parametrize(
    ("field", "value", "variable"),
    [
        ("clerk_issuer", "", "CLERK_ISSUER"),
        ("clerk_issuer", "http://clerk.ridematch.app", "CLERK_ISSUER"),
        ("clerk_issuer", "https://neat-fox-1.clerk.accounts.dev", "CLERK_ISSUER"),
        ("clerk_jwt_key", "", "CLERK_JWT_KEY"),
        ("clerk_jwt_key", "not a pem", "CLERK_JWT_KEY"),
        ("clerk_authorized_parties", "", "CLERK_AUTHORIZED_PARTIES"),
        ("clerk_authorized_parties", "http://localhost:5173", "CLERK_AUTHORIZED_PARTIES"),
        ("clerk_authorized_parties", "https://*", "CLERK_AUTHORIZED_PARTIES"),
        ("cors_origins", "", "CORS_ORIGINS"),
        ("cors_origins", "https://127.0.0.1", "CORS_ORIGINS"),
        ("cors_origins", "https://other.ridematch.app", "CORS_ORIGINS"),
        ("clerk_secret_key", "sk_test_abc", "CLERK_SECRET_KEY"),
        ("clerk_webhook_signing_secret", "secret", "CLERK_WEBHOOK_SIGNING_SECRET"),
        ("clerk_webhook_signing_secret", "whsec_***", "CLERK_WEBHOOK_SIGNING_SECRET"),
        ("database_url", "postgresql://u:p@localhost:5432/db", "DATABASE_URL"),
        ("redis_url", "redis://127.0.0.1:6379/0", "REDIS_URL"),
        ("email_backend", "console", "EMAIL_BACKEND"),
        ("smtp_host", "", "SMTP_HOST"),
        ("email_from", "noreply@ridematch.local", "EMAIL_FROM"),
        ("admin_email", "me@ridematch.app", "ADMIN_EMAIL"),
    ],
)
def test_each_rule_names_its_variable(field: str, value: object, variable: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        build(**{field: value})
    assert variable in str(excinfo.value)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ValidationError) as excinfo:
        build(clerk_issuer="", clerk_secret_key="", admin_email="me@ridematch.app")
    message = str(excinfo.value)
    for variable in ("CLERK_ISSUER", "CLERK_SECRET_KEY", "ADMIN_EMAIL"):
        assert variable in message


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_other_environments_stay_permissive(app_env: str) -> None:
    from app.config import Settings

    settings = Settings(_env_file=None, app_env=app_env, admin_email="me@example.com")
    assert not settings.is_production


@pytest.mark.parametrize(
    "url",
    [
        "postgres://u:p@h:5432/db",
        "postgresql://u:p@h:5432/db",
        "postgresql+asyncpg://u:p@h:5432/db",
    ],
)
def test_database_urls_are_normalised_to_asyncpg(url: str) -> None:
    from app.config import Settings

    settings = Settings(_env_file=None, database_url=url, test_database_url=url)
    assert settings.database_url == "postgresql+asyncpg://u:p@h:5432/db"
    assert settings.test_database_url == "postgresql+asyncpg://u:p@h:5432/db"


async def test_seed_refuses_production() -> None:
    from app.seed import seed

    with pytest.raises(RuntimeError, match="production"):
        await seed(reset=False, settings=build())


def test_the_error_never_echoes_secret_values() -> None:
    """The message lands in the host's deploy log."""
    with pytest.raises(ValidationError) as excinfo:
        build(clerk_issuer="", clerk_secret_key="sk_test_SECRETVALUE123")
    message = str(excinfo.value)
    assert "SECRETVALUE123" not in message
    assert "dGVzdC13ZWJob29r" not in message
