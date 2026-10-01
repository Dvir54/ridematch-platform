"""Factories for rides and ride requests (CONTRACT.md §3-§4, PLAN Phase 2).

Everything is built through the API, the way a real client would: a ride comes
from `POST /rides`, a request from `POST /rides/{id}/requests`, and a status
such as `full` or `in_progress` is reached by driving the documented
transitions. No factory fabricates a state with SQL, because then a test using
it would prove nothing about the endpoints that are supposed to produce it.

Reading the database is a different matter: `assert_seat_invariant` checks the
stored row, because CONTRACT.md §4 states its invariant about the row
("`available_seats = capacity - SUM(seats_requested of approved requests)` must
hold at all times"), not about one response body.

Time is controlled with relative departure times only - no sleeps, no frozen
clock. The offsets below sit clear of both documented boundaries so the tests
cannot race the wall clock; the boundaries themselves get their own tests with
a deliberate 30-second margin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import clock
from .assertions import expect_status
from .db import TestDatabase
from .factories import OMIT, TestUser, Users

# Two real places ~54 km apart, so a ride between them is never accidentally
# inside the 10 km search radius of the other end (that matters from Phase 3).
TEL_AVIV = (32.0853, 34.7818)
JERUSALEM = (31.7683, 35.2137)

DEFAULT_CAPACITY = 3
DEFAULT_PRICE = "25.50"
DEFAULT_DEPARTURE_HOURS = 24.0

# Start is allowed from departure - 2h (CONTRACT.md §3, D7); an approved
# passenger may cancel until departure - 1h (D15).
STARTABLE_HOURS = 1.5  # inside the 2h start window, outside the 1h cancel cutoff
TOO_EARLY_HOURS = 3.0  # outside the 2h start window
TOO_LATE_HOURS = 0.5  # inside the 1h cancel cutoff, so an approved seat is stuck

# Margin used by the boundary tests. Requests take milliseconds in-process, so
# 30s pins each cutoff to within a minute without ever flaking.
BOUNDARY_MARGIN_HOURS = 30 / 3600

RIDE_STATUSES = ("upcoming", "full", "in_progress", "completed", "cancelled")
REQUEST_STATUSES = ("pending", "approved", "rejected", "cancelled")

OPEN_RIDE_STATUSES = ("upcoming", "full")
TERMINAL_RIDE_STATUSES = ("completed", "cancelled")


def ride_payload(
    *, departure_in: float = DEFAULT_DEPARTURE_HOURS, **overrides: Any
) -> dict[str, Any]:
    """A minimal valid RideCreate body. `departure_in` is hours from now."""
    start_lat, start_lng = TEL_AVIV
    end_lat, end_lng = JERUSALEM
    payload: dict[str, Any] = {
        "start_lat": start_lat,
        "start_lng": start_lng,
        "start_address": "Rothschild Blvd 1, Tel Aviv",
        "end_lat": end_lat,
        "end_lng": end_lng,
        "end_address": "Jaffa St 1, Jerusalem",
        "departure_time": clock.iso_in_hours(departure_in),
        "capacity": DEFAULT_CAPACITY,
        "price_per_seat": DEFAULT_PRICE,
    }
    payload.update(overrides)
    # Pass OMIT (from support.factories) to drop a key entirely - overriding it
    # with None would test nullability, not a missing field.
    return {key: value for key, value in payload.items() if value is not OMIT}


@dataclass
class Offer:
    """A ride that exists, plus the driver who may act on it."""

    driver: TestUser
    ride: dict[str, Any]

    @property
    def id(self) -> int:
        return int(self.ride["id"])

    @property
    def status(self) -> str:
        return str(self.ride["status"])

    @property
    def available_seats(self) -> int:
        return int(self.ride["available_seats"])


def _ride_id(ride: Offer | dict[str, Any] | int) -> int:
    if isinstance(ride, Offer):
        return ride.id
    if isinstance(ride, dict):
        return int(ride["id"])
    return int(ride)


def _request_id(request: dict[str, Any] | int) -> int:
    return int(request["id"]) if isinstance(request, dict) else int(request)


class Rides:
    """Drives the ride endpoints. Each method returns the raw response unless
    its name says otherwise, so a test can assert on a failure."""

    def __init__(self, client: Any, users: Users) -> None:
        self.client = client
        self.users = users

    # ── creation ────────────────────────────────────────────────────────
    async def create_response(self, driver: TestUser, **overrides: Any) -> Any:
        return await self.client.post(
            "/rides", json=ride_payload(**overrides), headers=driver.headers
        )

    async def offer(self, driver: TestUser | None = None, **overrides: Any) -> Offer:
        """Create a ride and return it with its driver. Fails loudly if the
        contract would not have allowed the creation."""
        driver = driver or await self.users.create_driver()
        body = expect_status(await self.create_response(driver, **overrides), 201)
        return Offer(driver=driver, ride=body)

    # ── reads ───────────────────────────────────────────────────────────
    async def get(self, ride: Offer | dict[str, Any] | int, as_user: TestUser | None = None) -> Any:
        actor = as_user or (ride.driver if isinstance(ride, Offer) else None)
        assert actor is not None, "GET /rides/{id} needs a caller"
        return await self.client.get(f"/rides/{_ride_id(ride)}", headers=actor.headers)

    async def fetch(
        self, ride: Offer | dict[str, Any] | int, as_user: TestUser | None = None
    ) -> dict[str, Any]:
        return expect_status(await self.get(ride, as_user), 200)

    async def refresh(self, offer: Offer, as_user: TestUser | None = None) -> dict[str, Any]:
        """Re-read the ride through the API and update the Offer in place."""
        offer.ride = await self.fetch(offer, as_user)
        return offer.ride

    async def mine(self, driver: TestUser, **params: Any) -> Any:
        return await self.client.get("/rides/mine", params=params, headers=driver.headers)

    async def requests_on(
        self, ride: Offer | dict[str, Any] | int, as_user: TestUser | None = None, **params: Any
    ) -> Any:
        actor = as_user or (ride.driver if isinstance(ride, Offer) else None)
        assert actor is not None, "GET /rides/{id}/requests needs a caller"
        return await self.client.get(
            f"/rides/{_ride_id(ride)}/requests", params=params, headers=actor.headers
        )

    # ── transitions ─────────────────────────────────────────────────────
    async def patch(
        self,
        ride: Offer | dict[str, Any] | int,
        body: dict[str, Any],
        as_user: TestUser | None = None,
    ) -> Any:
        actor = as_user or (ride.driver if isinstance(ride, Offer) else None)
        assert actor is not None, "PATCH /rides/{id} needs a caller"
        return await self.client.patch(f"/rides/{_ride_id(ride)}", json=body, headers=actor.headers)

    async def _action(
        self, ride: Offer | dict[str, Any] | int, action: str, as_user: TestUser | None
    ) -> Any:
        actor = as_user or (ride.driver if isinstance(ride, Offer) else None)
        assert actor is not None, f"POST /rides/{{id}}/{action} needs a caller"
        return await self.client.post(f"/rides/{_ride_id(ride)}/{action}", headers=actor.headers)

    async def cancel(self, ride: Any, as_user: TestUser | None = None) -> Any:
        return await self._action(ride, "cancel", as_user)

    async def start(self, ride: Any, as_user: TestUser | None = None) -> Any:
        return await self._action(ride, "start", as_user)

    async def complete(self, ride: Any, as_user: TestUser | None = None) -> Any:
        return await self._action(ride, "complete", as_user)


class RideRequests:
    """Drives the ride-request endpoints."""

    def __init__(self, client: Any, users: Users) -> None:
        self.client = client
        self.users = users

    # ── creation ────────────────────────────────────────────────────────
    async def create_response(
        self,
        ride: Offer | dict[str, Any] | int,
        passenger: TestUser,
        seats: int | None = 1,
        body: dict[str, Any] | None = None,
    ) -> Any:
        if body is None:
            body = {} if seats is None else {"seats_requested": seats}
        return await self.client.post(
            f"/rides/{_ride_id(ride)}/requests", json=body, headers=passenger.headers
        )

    async def create(
        self,
        ride: Offer | dict[str, Any] | int,
        passenger: TestUser,
        seats: int | None = 1,
    ) -> dict[str, Any]:
        return expect_status(await self.create_response(ride, passenger, seats), 201)

    # ── reads ───────────────────────────────────────────────────────────
    async def get(self, request: dict[str, Any] | int, as_user: TestUser) -> Any:
        return await self.client.get(f"/requests/{_request_id(request)}", headers=as_user.headers)

    async def fetch(self, request: dict[str, Any] | int, as_user: TestUser) -> dict[str, Any]:
        return expect_status(await self.get(request, as_user), 200)

    async def mine(self, passenger: TestUser, **params: Any) -> Any:
        return await self.client.get("/requests/mine", params=params, headers=passenger.headers)

    async def incoming(self, driver: TestUser, **params: Any) -> Any:
        return await self.client.get("/requests/incoming", params=params, headers=driver.headers)

    # ── transitions ─────────────────────────────────────────────────────
    async def _action(self, request: dict[str, Any] | int, action: str, as_user: TestUser) -> Any:
        return await self.client.post(
            f"/requests/{_request_id(request)}/{action}", headers=as_user.headers
        )

    async def approve(self, request: dict[str, Any] | int, as_user: TestUser) -> Any:
        return await self._action(request, "approve", as_user)

    async def reject(self, request: dict[str, Any] | int, as_user: TestUser) -> Any:
        return await self._action(request, "reject", as_user)

    async def cancel(self, request: dict[str, Any] | int, as_user: TestUser) -> Any:
        return await self._action(request, "cancel", as_user)

    # ── composites ──────────────────────────────────────────────────────
    async def approved(self, offer: Offer, passenger: TestUser, seats: int = 1) -> dict[str, Any]:
        request = await self.create(offer, passenger, seats)
        return expect_status(await self.approve(request, offer.driver), 200)

    async def rejected(self, offer: Offer, passenger: TestUser, seats: int = 1) -> dict[str, Any]:
        request = await self.create(offer, passenger, seats)
        return expect_status(await self.reject(request, offer.driver), 200)

    async def cancelled(self, offer: Offer, passenger: TestUser, seats: int = 1) -> dict[str, Any]:
        request = await self.create(offer, passenger, seats)
        return expect_status(await self.cancel(request, passenger), 200)

    async def in_status(
        self, offer: Offer, status: str, passenger: TestUser, seats: int = 1
    ) -> dict[str, Any]:
        """A request on `offer` in the given status, reached by its own
        documented transition (CONTRACT.md §3 "Ride request")."""
        if status == "pending":
            return await self.create(offer, passenger, seats)
        if status == "approved":
            return await self.approved(offer, passenger, seats)
        if status == "rejected":
            return await self.rejected(offer, passenger, seats)
        if status == "cancelled":
            return await self.cancelled(offer, passenger, seats)
        raise AssertionError(f"unknown request status {status!r}")


async def ride_in_status(
    status: str,
    *,
    rides: Rides,
    requests: RideRequests,
    users: Users,
    departure_in: float = STARTABLE_HOURS,
    capacity: int = 2,
) -> Offer:
    """A ride in the given status, reached through the documented transitions.

    `departure_in` defaults to a departure close enough that `start` is allowed,
    so a 409 from any other action can only mean INVALID_STATE_TRANSITION.
    """
    if status == "upcoming":
        return await rides.offer(capacity=capacity, departure_in=departure_in)
    if status == "full":
        offer = await rides.offer(capacity=capacity, departure_in=departure_in)
        await requests.approved(offer, await users.create(), seats=capacity)
        await rides.refresh(offer)
        assert offer.status == "full", f"expected a full ride, got {offer.status!r}"
        return offer
    if status == "in_progress":
        offer = await rides.offer(capacity=capacity, departure_in=departure_in)
        offer.ride = expect_status(await rides.start(offer), 200)
        return offer
    if status == "completed":
        offer = await rides.offer(capacity=capacity, departure_in=departure_in)
        expect_status(await rides.start(offer), 200)
        offer.ride = expect_status(await rides.complete(offer), 200)
        return offer
    if status == "cancelled":
        offer = await rides.offer(capacity=capacity, departure_in=departure_in)
        offer.ride = expect_status(await rides.cancel(offer), 200)
        return offer
    raise AssertionError(f"unknown ride status {status!r}")


# ── invariants read straight from the row ───────────────────────────────
async def approved_seats(db: TestDatabase, ride_id: int) -> int:
    return int(
        await db.fetchval(
            "SELECT COALESCE(SUM(seats_requested), 0) FROM ride_requests "
            "WHERE ride_id = $1 AND status = 'approved'",
            ride_id,
        )
    )


async def assert_seat_invariant(db: TestDatabase, ride_id: int) -> None:
    """CONTRACT.md §4: `available_seats = capacity - SUM(approved seats)` must
    hold at all times, and an open ride is `full` exactly when it has no seats.
    """
    row = await db.fetchrow(
        "SELECT capacity, available_seats, status FROM rides WHERE id = $1", ride_id
    )
    assert row is not None, f"ride {ride_id} vanished"
    taken = await approved_seats(db, ride_id)
    assert row["available_seats"] == row["capacity"] - taken, (
        f"ride {ride_id}: available_seats={row['available_seats']} but "
        f"capacity={row['capacity']} - approved seats={taken}"
    )
    if row["status"] in OPEN_RIDE_STATUSES:
        expected = "full" if row["available_seats"] == 0 else "upcoming"
        assert row["status"] == expected, (
            f"ride {ride_id}: {row['available_seats']} seat(s) free but status={row['status']!r}, "
            f"expected {expected!r} (CONTRACT.md §3)"
        )


async def request_statuses(db: TestDatabase, ride_id: int) -> dict[int, str]:
    rows = await db.fetch(
        "SELECT id, status FROM ride_requests WHERE ride_id = $1 ORDER BY id", ride_id
    )
    return {int(r["id"]): str(r["status"]) for r in rows}


async def notification_rows(
    db: TestDatabase, user_id: int, *, type_: str | None = None
) -> list[Any]:
    """Notification rows for a user. Phase 2 writes the rows; the endpoints and
    the WebSocket push arrive in Phase 4 (PLAN), so Phase 2 reads the table."""
    if type_ is None:
        return await db.fetch("SELECT * FROM notifications WHERE user_id = $1 ORDER BY id", user_id)
    return await db.fetch(
        "SELECT * FROM notifications WHERE user_id = $1 AND type = $2 ORDER BY id",
        user_id,
        type_,
    )


async def notification_types(db: TestDatabase, user_id: int) -> list[str]:
    return [str(r["type"]) for r in await notification_rows(db, user_id)]
