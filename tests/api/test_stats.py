"""GET /users/me/stats (CONTRACT.md D9, openapi `UserStats`).

The schema's own field descriptions pin down `passengers_carried` exactly
("Sum of approved seats on completed rides") and `pending_requests`
("Home badge"). The rest is read the symmetric way the schema groups them:
*_offered/*_requested count every ride/request ever created (regardless of
status, like `rides.mine` with no filter), *_completed needs the ride itself
`completed` (and, for a passenger, an *approved* seat on it - a rejected or
cancelled request never rode), and upcoming_* counts an `upcoming`/`full`
ride with no further requirement that the ride has not yet started by clock
time. If @backend's reading differs, this file gets fixed up, not deleted.
"""

from __future__ import annotations

from support.assertions import expect_status
from support.rides import STARTABLE_HOURS, ride_in_status

STATS = "/users/me/stats"


async def stats_for(client, user) -> dict:
    return expect_status(await client.get(STATS, headers=user.headers), 200)


class TestShape:
    async def test_zero_for_a_brand_new_user(self, client, user) -> None:
        body = await stats_for(client, user)
        assert body["as_driver"] == {
            "rides_offered": 0,
            "rides_completed": 0,
            "upcoming_rides": 0,
            "pending_requests": 0,
            "passengers_carried": 0,
        }
        assert body["as_passenger"] == {
            "trips_requested": 0,
            "trips_completed": 0,
            "upcoming_trips": 0,
        }

    async def test_requires_authentication(self, client) -> None:
        response = await client.get(STATS)
        assert response.status_code == 401

    async def test_requires_onboarding(self, client, users) -> None:
        response = await client.get(STATS, headers=users.stranger_headers())
        assert response.status_code == 403


class TestAsDriver:
    async def test_rides_offered_counts_every_ride_regardless_of_status(
        self, client, rides, requests, driver, users
    ) -> None:
        await rides.offer(driver, departure_in=48)
        await ride_in_status(
            "cancelled", rides=rides, requests=requests, users=users, departure_in=24
        )  # a different driver - does not count for `driver`
        cancelled_own = await rides.offer(driver, departure_in=30)
        await rides.cancel(cancelled_own)

        body = await stats_for(client, driver)
        assert body["as_driver"]["rides_offered"] == 2

    async def test_upcoming_rides_counts_upcoming_and_full(
        self, client, rides, requests, driver, users
    ) -> None:
        await rides.offer(driver, departure_in=48, capacity=2)
        full = await rides.offer(driver, departure_in=30, capacity=1)
        await requests.approved(full, await users.create())
        await rides.refresh(full)
        assert full.status == "full"

        completed = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        await rides.start(completed)
        await rides.complete(completed)

        cancelled = await rides.offer(driver, departure_in=20)
        await rides.cancel(cancelled)

        body = await stats_for(client, driver)
        assert body["as_driver"]["upcoming_rides"] == 2

    async def test_rides_completed(self, client, rides, driver) -> None:
        offer = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        await rides.start(offer)
        await rides.complete(offer)
        await rides.offer(driver, departure_in=24)  # still upcoming

        body = await stats_for(client, driver)
        assert body["as_driver"]["rides_completed"] == 1

    async def test_pending_requests_across_all_of_the_drivers_rides(
        self, client, rides, requests, driver, users
    ) -> None:
        first = await rides.offer(driver, capacity=2, departure_in=24)
        second = await rides.offer(driver, capacity=2, departure_in=30)
        await requests.create(first, await users.create())
        await requests.create(second, await users.create())
        approved_elsewhere = await requests.create(first, await users.create())
        await requests.approve(approved_elsewhere, driver)

        body = await stats_for(client, driver)
        assert body["as_driver"]["pending_requests"] == 2

    async def test_passengers_carried_sums_approved_seats_on_completed_rides_only(
        self, client, rides, requests, driver, users
    ) -> None:
        completed = await rides.offer(driver, capacity=3, departure_in=STARTABLE_HOURS)
        await requests.approved(completed, await users.create(), seats=2)
        await rides.start(completed)
        await rides.complete(completed)

        still_upcoming = await rides.offer(driver, capacity=3, departure_in=24)
        await requests.approved(still_upcoming, await users.create(), seats=3)

        body = await stats_for(client, driver)
        assert body["as_driver"]["passengers_carried"] == 2


class TestAsPassenger:
    async def test_trips_requested_counts_every_request_regardless_of_status(
        self, client, rides, requests, driver, passenger, users
    ) -> None:
        pending_on = await rides.offer(driver, capacity=2, departure_in=24)
        await requests.create(pending_on, passenger)
        rejected_on = await rides.offer(driver, capacity=2, departure_in=30)
        await requests.rejected(rejected_on, passenger)

        body = await stats_for(client, passenger)
        assert body["as_passenger"]["trips_requested"] == 2

    async def test_trips_completed_needs_an_approved_seat_on_a_completed_ride(
        self, client, rides, requests, driver, passenger, users
    ) -> None:
        completed = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        await requests.approved(completed, passenger)
        await rides.start(completed)
        await rides.complete(completed)

        rejected_elsewhere = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        await requests.rejected(rejected_elsewhere, passenger)
        await rides.start(rejected_elsewhere)
        await rides.complete(rejected_elsewhere)

        body = await stats_for(client, passenger)
        assert body["as_passenger"]["trips_completed"] == 1

    async def test_upcoming_trips_needs_an_approved_seat_on_an_open_ride(
        self, client, rides, requests, driver, passenger, users
    ) -> None:
        approved = await rides.offer(driver, capacity=2, departure_in=24)
        await requests.approved(approved, passenger)
        pending = await rides.offer(driver, capacity=2, departure_in=30)
        await requests.create(pending, passenger)

        body = await stats_for(client, passenger)
        assert body["as_passenger"]["upcoming_trips"] == 1
