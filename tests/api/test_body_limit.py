"""Request bodies over 64 KiB are 413 PAYLOAD_TOO_LARGE on any endpoint (CONTRACT.md §2, §5)."""

from __future__ import annotations

import json

import pytest

from support.assertions import expect_error

pytestmark = pytest.mark.contract

LIMIT = 64 * 1024


def _body(size: int) -> bytes:
    return json.dumps({"name": "x" * size}).encode()


async def test_a_declared_oversized_body_is_413(client, user) -> None:
    response = await client.post(
        "/rides",
        content=_body(LIMIT + 1024),
        headers={**user.headers, "Content-Type": "application/json"},
    )
    expect_error(response, 413, "PAYLOAD_TOO_LARGE")


async def test_an_unauthenticated_oversized_body_is_413(client) -> None:
    """The webhook takes no token; the cap still applies before any handler work."""
    response = await client.post(
        "/webhooks/clerk",
        content=_body(LIMIT + 1024),
        headers={"Content-Type": "application/json"},
    )
    expect_error(response, 413, "PAYLOAD_TOO_LARGE")


async def test_a_chunked_oversized_body_is_413(client, user) -> None:
    """No Content-Length: the body is counted as it is read."""
    data = _body(LIMIT + 1024)

    async def chunks():
        for start in range(0, len(data), 8192):
            yield data[start : start + 8192]

    response = await client.patch(
        "/users/me",
        content=chunks(),
        headers={**user.headers, "Content-Type": "application/json"},
    )
    assert "content-length" not in {key.lower() for key in response.request.headers}
    expect_error(response, 413, "PAYLOAD_TOO_LARGE")


async def test_a_body_under_the_cap_passes_through(client, user) -> None:
    response = await client.patch("/users/me", json={"name": "Dana"}, headers=user.headers)
    assert response.status_code == 200
