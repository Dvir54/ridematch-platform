"""Factory for the rating endpoints (CONTRACT.md §4 "Ratings", PLAN Phase 5).

Everything is built through the API, same discipline as support/rides.py: a
rating comes from `POST /ratings`, nothing is written with SQL except the
things the contract itself says only SQL can reach (none, here - unlike
driver_rating in Phase 3, Phase 5 is the endpoint that writes the cache).
"""

from __future__ import annotations

from typing import Any

from .assertions import expect_status
from .factories import TestUser


class Ratings:
    """Drives `/ratings` and `/ratings/pending`."""

    def __init__(self, client: Any) -> None:
        self.client = client

    async def create_response(
        self,
        rater: TestUser,
        *,
        ride_id: int,
        to_user_id: int,
        score: int = 5,
        comment: str | None = None,
        tags: list[str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        if body is None:
            body = {"ride_id": ride_id, "to_user_id": to_user_id, "score": score}
            if comment is not None:
                body["comment"] = comment
            if tags is not None:
                body["tags"] = tags
        return await self.client.post("/ratings", json=body, headers=rater.headers)

    async def create(self, rater: TestUser, **kwargs: Any) -> dict[str, Any]:
        return expect_status(await self.create_response(rater, **kwargs), 201)

    async def pending_response(self, as_user: TestUser) -> Any:
        return await self.client.get("/ratings/pending", headers=as_user.headers)

    async def pending(self, as_user: TestUser) -> list[dict[str, Any]]:
        return expect_status(await self.pending_response(as_user), 200)

    async def for_user(self, user_id: int, as_user: TestUser, **params: Any) -> Any:
        return await self.client.get(
            f"/users/{user_id}/ratings", params=params, headers=as_user.headers
        )


def average_after(old: float | None, old_count: int, score: int) -> float:
    """CONTRACT.md §4: `new = (old * count + score) / (count + 1)`. `old=None`
    (no prior rating) behaves as 0 since `old_count` is then 0."""
    base = old or 0.0
    return (base * old_count + score) / (old_count + 1)
