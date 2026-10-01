"""GET /health - openapi.yaml marks it `security: []`, so it takes no token."""

from __future__ import annotations

from support.assertions import expect_status


async def test_health_needs_no_token(client) -> None:
    body = expect_status(await client.get("/health"), 200)
    assert body["status"] in {"ok", "degraded"}


async def test_health_reports_db_and_redis(client) -> None:
    body = expect_status(await client.get("/health"), 200)
    assert body["db"] is True, "the test database should be reachable"
    assert body["redis"] is True, "redis should be reachable"
    assert body["status"] == "ok"


async def test_health_ignores_a_broken_token(client, users) -> None:
    """An unauthenticated endpoint must not start failing because of a bad header."""
    response = await client.get("/health", headers={"Authorization": "Bearer not-a-jwt"})
    expect_status(response, 200)
