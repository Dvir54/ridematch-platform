"""`python -m app.admin_cli grant|revoke <email>` (CONTRACT.md §4 Users), and the production guards."""

from __future__ import annotations

import pytest

from support import env
from support.assertions import expect_status

pytestmark = pytest.mark.contract


async def run(*argv: str) -> int:
    from app.admin_cli import run as cli_run

    return await cli_run(list(argv))


async def test_grant_makes_an_existing_user_admin(users, db) -> None:
    user = await users.create()
    assert await run("grant", user.email) == 0
    assert (await db.user_row(user.id))["is_admin"] is True


async def test_grant_matches_email_case_insensitively(users, db) -> None:
    user = await users.create()
    assert await run("grant", user.email.upper()) == 0
    assert (await db.user_row(user.id))["is_admin"] is True


async def test_grant_twice_is_idempotent(users, db) -> None:
    user = await users.create()
    assert await run("grant", user.email) == 0
    assert await run("grant", user.email) == 0
    assert (await db.user_row(user.id))["is_admin"] is True


async def test_revoke_removes_admin_and_is_idempotent(users, db) -> None:
    user = await users.create()
    await db.set_admin(user.id, True)
    assert await run("revoke", user.email) == 0
    assert await run("revoke", user.email) == 0
    assert (await db.user_row(user.id))["is_admin"] is False


async def test_unknown_email_exits_1(db) -> None:
    assert await run("grant", "nobody@ridematch.test") == 1


async def test_deactivated_user_is_refused(users, db) -> None:
    user = await users.create()
    await users.deactivate(user)
    assert await run("grant", user.email) == 1
    assert (await db.user_row(user.id))["is_admin"] is False


async def test_production_onboarding_never_bootstraps_an_admin(
    backend_app, users, monkeypatch
) -> None:
    production = backend_app.state.settings.model_copy(update={"app_env": "production"})
    monkeypatch.setattr(backend_app.state, "settings", production)
    body = expect_status(await users.onboard_response(email=env.ADMIN_EMAIL), 201)
    assert body["is_admin"] is False


async def test_docs_are_off_in_production(backend_app) -> None:
    import httpx
    from app.main import create_app

    production = backend_app.state.settings.model_copy(update={"app_env": "production"})
    prod_app = create_app(production)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=prod_app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/docs")).status_code == 404
    await prod_app.state.engine.dispose()
    await prod_app.state.redis.aclose()
