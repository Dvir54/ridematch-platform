"""Who may see the licence plate (CONTRACT.md §4 "Vehicles", D14).

    Make/model/color are public (`UserPublic.vehicle`). The plate is private:
    it appears only in `Ride.driver_vehicle_plate`, and only for the driver and
    passengers with an approved request on that ride.

So `driver_vehicle_plate` is a per-caller field: the same ride row answers a
plate to one caller and `null` to the next. Every place a Ride is embedded has
to honour that, which is why this file checks the lists too.
"""

from __future__ import annotations

import pytest

from support.assertions import expect_error, expect_status
from support.factories import DEFAULT_VEHICLE
from support.rides import STARTABLE_HOURS

PLATE = DEFAULT_VEHICLE["plate"]
PUBLIC_VEHICLE = {k: v for k, v in DEFAULT_VEHICLE.items() if k != "plate"}


class TestOnTheRide:
    async def test_the_driver_sees_the_plate(self, rides, offer) -> None:
        assert (await rides.fetch(offer))["driver_vehicle_plate"] == PLATE

    async def test_an_approved_passenger_sees_the_plate(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.approved(offer, passenger)
        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] == PLATE

    @pytest.mark.parametrize("status", ["pending", "rejected", "cancelled"])
    async def test_without_an_approved_request_there_is_no_plate(
        self, rides, requests, passenger, status: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        await requests.in_status(offer, status, passenger)
        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] is None

    async def test_a_stranger_sees_no_plate(self, rides, offer, other_user) -> None:
        assert (await rides.fetch(offer, other_user))["driver_vehicle_plate"] is None

    async def test_an_admin_sees_no_plate_here(self, rides, offer, admin) -> None:
        """D14 names the driver and approved passengers. Admin tooling is Phase 6."""
        assert (await rides.fetch(offer, admin))["driver_vehicle_plate"] is None

    async def test_the_plate_is_withdrawn_when_the_passenger_cancels(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.approved(offer, passenger)
        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] == PLATE

        expect_status(await requests.cancel(request, passenger), 200)
        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] is None

    async def test_the_plate_survives_the_ride_completing(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)
        expect_status(await rides.complete(offer), 200)

        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] == PLATE

    async def test_a_driver_with_no_vehicle_has_no_plate(
        self, client, rides, requests, driver, passenger
    ) -> None:
        """A vehicle can be removed once the ride is no longer open, and then
        there is no plate to show - but the ride keeps its history."""
        offer = await rides.offer(driver, capacity=2, departure_in=24)
        await requests.approved(offer, passenger)
        expect_status(await rides.cancel(offer), 200)
        expect_status(
            await client.patch("/users/me", json={"vehicle": None}, headers=driver.headers), 200
        )

        body = await rides.fetch(offer, passenger)
        assert body["driver_vehicle_plate"] is None
        assert body["driver"]["vehicle"] is None


class TestInTheLists:
    async def test_the_drivers_own_list(self, rides, offer) -> None:
        body = expect_status(await rides.mine(offer.driver), 200)
        assert [ride["driver_vehicle_plate"] for ride in body] == [PLATE]

    async def test_the_requests_on_a_ride(self, rides, offer, requests, passenger) -> None:
        """The driver is reading, so the nested ride carries their own plate."""
        await requests.approved(offer, passenger)
        body = expect_status(await rides.requests_on(offer), 200)
        assert body[0]["ride"]["driver_vehicle_plate"] == PLATE

    async def test_my_trips_shows_the_plate_once_approved(
        self, rides, requests, passenger, users
    ) -> None:
        approved_on = await rides.offer(await users.create_driver(), capacity=2)
        pending_on = await rides.offer(await users.create_driver(), capacity=2, departure_in=30)
        await requests.approved(approved_on, passenger)
        await requests.create(pending_on, passenger)

        body = expect_status(await requests.mine(passenger), 200)
        plates = {item["ride"]["id"]: item["ride"]["driver_vehicle_plate"] for item in body}
        assert plates == {approved_on.id: PLATE, pending_on.id: None}

    async def test_a_single_request_read_by_each_side(
        self, rides, offer, requests, passenger
    ) -> None:
        request = await requests.approved(offer, passenger)

        as_passenger = await requests.fetch(request, passenger)
        as_driver = await requests.fetch(request, offer.driver)
        assert as_passenger["ride"]["driver_vehicle_plate"] == PLATE
        assert as_driver["ride"]["driver_vehicle_plate"] == PLATE

    async def test_incoming_requests_carry_the_drivers_plate(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.create(offer, passenger)
        body = expect_status(await requests.incoming(offer.driver), 200)
        assert body[0]["ride"]["driver_vehicle_plate"] == PLATE

    async def test_a_pending_requester_never_sees_it_in_their_own_list(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.create(offer, passenger)
        body = expect_status(await requests.mine(passenger), 200)
        assert body[0]["ride"]["driver_vehicle_plate"] is None


class TestThePublicVehicle:
    async def test_the_nested_driver_never_carries_the_plate(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.approved(offer, passenger)
        for caller in (offer.driver, passenger):
            body = await rides.fetch(offer, caller)
            assert body["driver"]["vehicle"] == PUBLIC_VEHICLE
            assert "plate" not in body["driver"]["vehicle"], (
                "the plate belongs in Ride.driver_vehicle_plate only (D14)"
            )

    async def test_the_public_profile_never_carries_the_plate(
        self, client, offer, requests, passenger
    ) -> None:
        await requests.approved(offer, passenger)
        body = expect_status(
            await client.get(f"/users/{offer.driver.id}", headers=passenger.headers), 200
        )
        assert body["vehicle"] == PUBLIC_VEHICLE


class TestVehicleRemovalWithOpenRides:
    """CONTRACT.md §4: the vehicle "can't be removed while the user has
    `upcoming`/`full` rides (409 VEHICLE_REQUIRED)". Deferred here from Phase 1,
    which had no rides to open."""

    # openapi.yaml lists only 200/401/403/422 under PATCH /users/me, so the
    # schema check in expect_error refuses the 409 the backend (correctly) sends.
    # Reported to @backend 2026-10-01; additive fix, then these two go green.
    UNDOCUMENTED_409 = pytest.mark.xfail(
        reason="FAIL reported to @backend 2026-10-01: PATCH /users/me answers 409 "
        "VEHICLE_REQUIRED as CONTRACT.md §4 requires, but openapi.yaml documents no 409 for that "
        "operation (only 200/401/403/422), even though UserUpdate.vehicle's own description names "
        "the code. Please add the Conflict response.",
        strict=True,
    )

    @UNDOCUMENTED_409
    async def test_an_upcoming_ride_blocks_removal(self, client, rides, driver) -> None:
        await rides.offer(driver)
        response = await client.patch("/users/me", json={"vehicle": None}, headers=driver.headers)
        expect_error(response, 409, "VEHICLE_REQUIRED")

        assert (
            expect_status(await client.get("/users/me", headers=driver.headers), 200)["vehicle"]
            == DEFAULT_VEHICLE
        )

    @UNDOCUMENTED_409
    async def test_a_full_ride_blocks_removal(
        self, client, rides, requests, driver, passenger
    ) -> None:
        offer = await rides.offer(driver, capacity=1)
        await requests.approved(offer, passenger)
        assert (await rides.refresh(offer))["status"] == "full"

        response = await client.patch("/users/me", json={"vehicle": None}, headers=driver.headers)
        expect_error(response, 409, "VEHICLE_REQUIRED")

    @pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
    async def test_a_closed_ride_does_not_block_removal(
        self, client, rides, requests, users, driver, status: str
    ) -> None:
        from support.rides import ride_in_status

        await ride_in_status(status, rides=rides, requests=requests, users=users, capacity=2)
        lone_driver = await users.create_driver()
        offer = await rides.offer(lone_driver, departure_in=STARTABLE_HOURS)
        if status == "in_progress":
            expect_status(await rides.start(offer), 200)
        elif status == "completed":
            expect_status(await rides.start(offer), 200)
            expect_status(await rides.complete(offer), 200)
        else:
            expect_status(await rides.cancel(offer), 200)

        response = await client.patch(
            "/users/me", json={"vehicle": None}, headers=lone_driver.headers
        )
        assert expect_status(response, 200)["vehicle"] is None

    async def test_replacing_the_vehicle_is_always_allowed(self, client, rides, driver) -> None:
        """The rule is about *removing* it: an open ride still needs a car."""
        await rides.offer(driver)
        replacement = {"make": "Mazda", "model": "3", "color": "Red", "plate": "98-765-43"}
        body = expect_status(
            await client.patch("/users/me", json={"vehicle": replacement}, headers=driver.headers),
            200,
        )
        assert body["vehicle"] == replacement

    async def test_the_new_plate_shows_up_on_the_ride(
        self, client, rides, requests, driver, passenger
    ) -> None:
        offer = await rides.offer(driver, capacity=2)
        await requests.approved(offer, passenger)
        replacement = {"make": "Mazda", "model": "3", "color": "Red", "plate": "98-765-43"}
        expect_status(
            await client.patch("/users/me", json={"vehicle": replacement}, headers=driver.headers),
            200,
        )

        assert (await rides.fetch(offer, passenger))["driver_vehicle_plate"] == replacement["plate"]
