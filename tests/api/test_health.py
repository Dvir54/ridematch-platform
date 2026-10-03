"""GET /health (liveness) and GET /ready (readiness), CONTRACT.md §5 and D22.

Both are `security: []`. /health does no I/O; /ready is gated by the database only.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx

from support import env
from support.assertions import expect_error, expect_status

CLOSED_DB = "postgresql+asyncpg://ridematch:ridematch@127.0.0.1:1/ridematch_test"
CLOSED_REDIS = "redis://127.0.0.1:1/0"


@asynccontextmanager
async def client_for(backend_app, **overrides):
    """A client on a fresh app whose settings point somewhere else (e.g. a closed port)."""
    from app.main import create_app

    app = create_app(backend_app.state.settings.model_copy(update=overrides))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=f"http://testserver{env.API_PREFIX}",
        ) as client:
            yield client
    finally:
        await app.state.engine.dispose()
        await app.state.redis.aclose()


async def test_health_needs_no_token(client) -> None:
    assert expect_status(await client.get("/health"), 200) == {"status": "ok"}


async def test_health_ignores_a_broken_token(client) -> None:
    """An unauthenticated endpoint must not start failing because of a bad header."""
    response = await client.get("/health", headers={"Authorization": "Bearer not-a-jwt"})
    expect_status(response, 200)


async def test_health_stays_up_when_the_database_is_down(backend_app) -> None:
    """Liveness must not check the DB, or a DB outage becomes a restart loop."""
    async with client_for(backend_app, test_database_url=CLOSED_DB) as client:
        assert expect_status(await client.get("/health"), 200) == {"status": "ok"}


async def test_ready_reports_db_and_redis(client) -> None:
    body = expect_status(await client.get("/ready"), 200)
    assert body == {"status": "ready", "db": True, "redis": True}


async def test_ready_needs_no_token(client) -> None:
    response = await client.get("/ready", headers={"Authorization": "Bearer not-a-jwt"})
    expect_status(response, 200)


async def test_ready_is_still_ready_without_redis(backend_app) -> None:
    async with client_for(backend_app, redis_url=CLOSED_REDIS) as client:
        body = expect_status(await client.get("/ready"), 200)
    assert body == {"status": "ready", "db": True, "redis": False}


async def test_ready_is_503_when_the_database_is_down(backend_app) -> None:
    async with client_for(backend_app, test_database_url=CLOSED_DB) as client:
        body = expect_error(await client.get("/ready"), 503, "NOT_READY")
    assert body["details"][0]["field"] == "db"


async def test_every_response_carries_a_request_id(client) -> None:
    generated = await client.get("/health")
    assert generated.headers["x-request-id"]
    echoed = await client.get("/health", headers={"X-Request-ID": "trace-me"})
    assert echoed.headers["x-request-id"] == "trace-me"
