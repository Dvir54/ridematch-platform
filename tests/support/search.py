"""Drives GET /search (CONTRACT.md §7 "Matching formula", PLAN Phase 3).

Passenger pickup and dropoff anchors are independent points (different
latitude, same longitude as each other) so a ride's start/end can be placed a
controlled `p`/`d` number of kilometers from each one via `support.geo.north`,
without the two legs interfering.
"""

from __future__ import annotations

from typing import Any

from . import clock
from .factories import TestUser

PASSENGER_START = (32.0000, 34.8000)
PASSENGER_END = (32.5000, 34.8000)

DEFAULT_SEARCH_DEPARTURE_HOURS = 24.0


def search_params(**overrides: Any) -> dict[str, Any]:
    """A minimal valid /search query. Pass overrides to move/break it."""
    start_lat, start_lng = PASSENGER_START
    end_lat, end_lng = PASSENGER_END
    params: dict[str, Any] = {
        "start_lat": start_lat,
        "start_lng": start_lng,
        "end_lat": end_lat,
        "end_lng": end_lng,
        "time": clock.iso_in_hours(DEFAULT_SEARCH_DEPARTURE_HOURS),
    }
    params.update(overrides)
    return params


class Search:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def response(self, caller: TestUser, **params: Any) -> Any:
        return await self.client.get(
            "/search", params=search_params(**params), headers=caller.headers
        )

    def result_for(self, results: list[dict[str, Any]], ride_id: int) -> dict[str, Any] | None:
        return next((r for r in results if r["ride"]["id"] == ride_id), None)
