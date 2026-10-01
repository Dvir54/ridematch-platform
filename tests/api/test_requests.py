"""Asking for a seat, and the lists that show requests.

POST /rides/{id}/requests, GET /rides/{id}/requests, GET /requests/mine,
GET /requests/incoming, GET /requests/{id}.

Contract: CONTRACT.md §4 "Requests", D2, openapi `RideRequestCreate` /
`RideRequest`.
"""

from __future__ import annotations

import pytest

from support import clock
from support.assertions import expect_error, expect_status, expect_validation_error
from support.rides import (
    STARTABLE_HOURS,
    assert_seat_invariant,
    notification_types,
    ride_in_status,
)


class TestCreate:
    async def test_a_passenger_asks_for_a_seat(self, rides, offer, requests, passenger, db) -> None:
        body = expect_status(await requests.create_response(offer, passenger), 201)

        assert body["status"] == "pending"
        assert body["seats_requested"] == 1
        assert body["passenger"]["id"] == passenger.id
        assert body["ride"]["id"] == offer.id
        assert body["responded_at"] is None, "a pending request has no response yet"
        assert body["requested_at"].endswith("Z")
        await assert_seat_invariant(db, offer.id)

    async def test_seats_are_not_held_by_a_pending_request(
        self, rides, offer, requests, passenger
    ) -> None:
        """CONTRACT.md §4: `available_seats` counts *approved* requests only."""
        await requests.create(offer, passenger)
        assert (await rides.refresh(offer))["available_seats"] == offer.ride["capacity"]
        assert offer.status == "upcoming"

    async def test_seats_requested_defaults_to_one(self, offer, requests, passenger) -> None:
        body = expect_status(await requests.create_response(offer, passenger, seats=None), 201)
        assert body["seats_requested"] == 1

    async def test_several_seats(self, offer, requests, passenger) -> None:
        body = expect_status(await requests.create_response(offer, passenger, seats=3), 201)
        assert body["seats_requested"] == 3

    async def test_the_nested_ride_is_the_full_object(self, offer, requests, passenger) -> None:
        body = expect_status(await requests.create_response(offer, passenger), 201)
        assert body["ride"]["driver"]["id"] == offer.driver.id
        assert body["ride"]["status"] == "upcoming"

    async def test_the_passenger_is_public_only(self, offer, requests, passenger) -> None:
        body = expect_status(await requests.create_response(offer, passenger), 201)
        for private in ("email", "phone", "date_of_birth", "is_admin", "preferences"):
            assert private not in body["passenger"], f"RideRequest.passenger leaks {private}"

    async def test_the_driver_is_notified(self, offer, requests, passenger, db) -> None:
        await requests.create(offer, passenger)
        assert "request_created" in await notification_types(db, offer.driver.id)
        assert "request_created" not in await notification_types(db, passenger.id)

    async def test_a_missing_ride_is_404(self, client, user) -> None:
        response = await client.post(
            "/rides/9999999/requests", json={"seats_requested": 1}, headers=user.headers
        )
        expect_error(response, 404, "NOT_FOUND")


class TestCreateRefusals:
    async def test_the_driver_cannot_request_their_own_ride(self, offer, requests) -> None:
        response = await requests.create_response(offer, offer.driver)
        expect_error(response, 409, "CANNOT_REQUEST_OWN_RIDE")

    @pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
    async def test_only_an_upcoming_ride_accepts_requests(
        self, rides, requests, users, passenger, status: str
    ) -> None:
        offer = await ride_in_status(status, rides=rides, requests=requests, users=users)
        expect_error(await requests.create_response(offer, passenger), 409, "RIDE_NOT_OPEN")

    async def test_a_full_ride_is_not_open(self, rides, requests, users, passenger) -> None:
        """A full ride answers RIDE_NOT_OPEN, not NOT_ENOUGH_SEATS: CONTRACT.md §4
        says "Only rides with `status=upcoming` accept requests"."""
        offer = await ride_in_status("full", rides=rides, requests=requests, users=users)
        expect_error(await requests.create_response(offer, passenger), 409, "RIDE_NOT_OPEN")

    async def test_more_seats_than_are_free(self, rides, requests, users, passenger) -> None:
        offer = await rides.offer(capacity=3)
        await requests.approved(offer, await users.create(), seats=2)

        expect_error(
            await requests.create_response(offer, passenger, seats=2), 409, "NOT_ENOUGH_SEATS"
        )
        expect_status(await requests.create_response(offer, passenger, seats=1), 201)

    async def test_more_seats_than_the_capacity(self, rides, driver, requests, passenger) -> None:
        offer = await rides.offer(driver, capacity=2)
        expect_error(
            await requests.create_response(offer, passenger, seats=3), 409, "NOT_ENOUGH_SEATS"
        )

    @pytest.mark.parametrize("existing", ["pending", "approved"])
    async def test_one_active_request_per_ride_and_passenger(
        self, rides, driver, requests, passenger, existing: str
    ) -> None:
        offer = await rides.offer(driver, capacity=4)
        await requests.in_status(offer, existing, passenger)

        expect_error(
            await requests.create_response(offer, passenger), 409, "REQUEST_ALREADY_EXISTS"
        )

    async def test_a_rejected_passenger_cannot_come_back(
        self, rides, driver, requests, passenger
    ) -> None:
        """D2: a driver's reject is final for that ride."""
        offer = await rides.offer(driver, capacity=4)
        await requests.rejected(offer, passenger)

        expect_error(await requests.create_response(offer, passenger), 409, "PREVIOUSLY_REJECTED")

    async def test_re_requesting_after_the_passengers_own_cancel(
        self, rides, driver, requests, passenger
    ) -> None:
        """D2: re-requesting is allowed after the passenger's *own* cancel."""
        offer = await rides.offer(driver, capacity=4, departure_in=24)
        await requests.cancelled(offer, passenger)

        body = expect_status(await requests.create_response(offer, passenger), 201)
        assert body["status"] == "pending"

    async def test_re_requesting_after_cancelling_an_approved_seat(
        self, rides, driver, requests, passenger, db
    ) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=24)
        request = await requests.approved(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

        expect_status(await requests.create_response(offer, passenger, seats=2), 201)
        await assert_seat_invariant(db, offer.id)

    async def test_another_passenger_is_unaffected_by_a_rejection(
        self, rides, driver, requests, users
    ) -> None:
        offer = await rides.offer(driver, capacity=4)
        await requests.rejected(offer, await users.create())
        expect_status(await requests.create_response(offer, await users.create()), 201)

    async def test_a_rejection_on_another_ride_does_not_carry_over(
        self, rides, driver, requests, passenger
    ) -> None:
        """PREVIOUSLY_REJECTED is per ride, not per driver."""
        rejected_on = await rides.offer(driver, capacity=2)
        await requests.rejected(rejected_on, passenger)

        other = await rides.offer(driver, capacity=2, departure_in=30)
        expect_status(await requests.create_response(other, passenger), 201)


class TestTheOrderOfRefusals:
    """D19: the 409s on POST /rides/{id}/requests are checked in the order
    openapi.yaml lists them - own ride, ride not open, seats, active request,
    previously rejected. Two reasons at once must give the earlier code."""

    async def test_own_ride_beats_ride_not_open(self, rides, driver, requests, users) -> None:
        offer = await rides.offer(driver, capacity=1)
        await requests.approved(offer, await users.create())  # ride is now full

        expect_error(await requests.create_response(offer, driver), 409, "CANNOT_REQUEST_OWN_RIDE")

    async def test_ride_not_open_beats_the_seat_check(
        self, rides, requests, users, passenger
    ) -> None:
        offer = await rides.offer(capacity=1)
        await requests.approved(offer, await users.create())

        expect_error(
            await requests.create_response(offer, passenger, seats=5), 409, "RIDE_NOT_OPEN"
        )

    async def test_the_seat_check_beats_an_existing_request(
        self, rides, requests, users, passenger
    ) -> None:
        """D19 spells this one out: "a passenger who already has a pending
        request and asks for more seats than are free gets NOT_ENOUGH_SEATS,
        not REQUEST_ALREADY_EXISTS"."""
        offer = await rides.offer(capacity=3)
        await requests.create(offer, passenger)
        await requests.approved(offer, await users.create(), seats=2)

        expect_error(
            await requests.create_response(offer, passenger, seats=2), 409, "NOT_ENOUGH_SEATS"
        )


class TestCreateValidation:
    @pytest.mark.parametrize("seats", [0, -1, 9])
    async def test_seats_outside_1_to_8(self, offer, requests, passenger, seats: int) -> None:
        expect_validation_error(
            await requests.create_response(offer, passenger, seats=seats),
            field="seats_requested",
        )

    @pytest.mark.parametrize("seats", [2.5, None, "many"])
    async def test_seats_must_be_an_integer(self, offer, requests, passenger, seats) -> None:
        expect_validation_error(
            await requests.create_response(offer, passenger, body={"seats_requested": seats}),
            field="seats_requested",
        )

    async def test_an_empty_body_uses_the_default(self, offer, requests, passenger) -> None:
        response = await requests.create_response(offer, passenger, body={})
        assert expect_status(response, 201)["seats_requested"] == 1


class TestGetOne:
    async def test_the_passenger_sees_their_own_request(self, offer, requests, passenger) -> None:
        request = await requests.create(offer, passenger)
        assert (await requests.fetch(request, passenger))["id"] == request["id"]

    async def test_the_driver_sees_a_request_on_their_ride(
        self, offer, requests, passenger
    ) -> None:
        request = await requests.create(offer, passenger)
        assert (await requests.fetch(request, offer.driver))["id"] == request["id"]

    async def test_nobody_else_sees_it(self, offer, requests, passenger, other_user) -> None:
        request = await requests.create(offer, passenger)
        expect_error(await requests.get(request, other_user), 403, "FORBIDDEN")

    async def test_an_admin_is_not_special_here(self, offer, requests, passenger, admin) -> None:
        """openapi: "Visible to the passenger who made it and the ride's driver".
        Admin reads go through /admin/* (Phase 6)."""
        request = await requests.create(offer, passenger)
        expect_error(await requests.get(request, admin), 403, "FORBIDDEN")

    async def test_a_missing_request_is_404(self, client, user) -> None:
        expect_error(await client.get("/requests/9999999", headers=user.headers), 404, "NOT_FOUND")


class TestRequestsOnARide:
    async def test_the_driver_lists_every_request(self, rides, driver, requests, users) -> None:
        offer = await rides.offer(driver, capacity=4)
        first = await requests.create(offer, await users.create())
        second = await requests.create(offer, await users.create())

        body = expect_status(await rides.requests_on(offer), 200)
        assert {item["id"] for item in body} == {first["id"], second["id"]}

    async def test_newest_first(self, rides, driver, requests, users) -> None:
        offer = await rides.offer(driver, capacity=4)
        first = await requests.create(offer, await users.create())
        second = await requests.create(offer, await users.create())
        third = await requests.create(offer, await users.create())

        body = expect_status(await rides.requests_on(offer), 200)
        assert [item["id"] for item in body] == [third["id"], second["id"], first["id"]]

    async def test_requests_on_another_ride_are_not_included(
        self, rides, driver, requests, users, passenger
    ) -> None:
        offer = await rides.offer(driver, capacity=4)
        other = await rides.offer(driver, capacity=4, departure_in=30)
        mine = await requests.create(offer, passenger)
        await requests.create(other, await users.create())

        body = expect_status(await rides.requests_on(offer), 200)
        assert [item["id"] for item in body] == [mine["id"]]

    async def test_status_filter(self, rides, driver, requests, users) -> None:
        offer = await rides.offer(driver, capacity=4)
        pending = await requests.create(offer, await users.create())
        approved = await requests.approved(offer, await users.create())
        rejected = await requests.rejected(offer, await users.create())

        for status, expected in (
            ("pending", pending["id"]),
            ("approved", approved["id"]),
            ("rejected", rejected["id"]),
        ):
            body = expect_status(await rides.requests_on(offer, status=status), 200)
            assert [item["id"] for item in body] == [expected], f"status={status}"

    async def test_an_unknown_status_is_rejected(self, rides, offer) -> None:
        """CONTRACT.md §2 (D19): 422 VALIDATION_ERROR with
        `details[].field = "query.status"`."""
        expect_validation_error(
            await rides.requests_on(offer, status="maybe"), field="query.status"
        )

    async def test_a_passenger_cannot_see_the_other_requests(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.create(offer, passenger)
        expect_error(await rides.requests_on(offer, passenger), 403, "FORBIDDEN")

    async def test_another_driver_cannot_see_them(self, rides, offer, other_user) -> None:
        expect_error(await rides.requests_on(offer, other_user), 403, "FORBIDDEN")

    async def test_empty_for_a_ride_with_no_requests(self, rides, offer) -> None:
        assert expect_status(await rides.requests_on(offer), 200) == []

    async def test_a_missing_ride_is_404(self, client, user) -> None:
        response = await client.get("/rides/9999999/requests", headers=user.headers)
        expect_error(response, 404, "NOT_FOUND")


class TestMine:
    async def test_only_the_callers_own_requests(
        self, rides, offer, requests, passenger, users
    ) -> None:
        mine = await requests.create(offer, passenger)
        await requests.create(offer, await users.create())

        body = expect_status(await requests.mine(passenger), 200)
        assert [item["id"] for item in body] == [mine["id"]]

    async def test_newest_first(self, rides, driver, requests, passenger) -> None:
        first = await requests.create(await rides.offer(driver, departure_in=48), passenger)
        second = await requests.create(await rides.offer(driver, departure_in=6), passenger)

        body = expect_status(await requests.mine(passenger), 200)
        assert [item["id"] for item in body] == [second["id"], first["id"]]

    async def test_every_status_is_listed_by_default(
        self, rides, driver, requests, passenger
    ) -> None:
        pending = await requests.create(await rides.offer(driver, capacity=2), passenger)
        approved = await requests.approved(
            await rides.offer(driver, capacity=2, departure_in=30), passenger
        )
        rejected = await requests.rejected(
            await rides.offer(driver, capacity=2, departure_in=36), passenger
        )

        body = expect_status(await requests.mine(passenger), 200)
        assert {item["id"] for item in body} == {pending["id"], approved["id"], rejected["id"]}

    async def test_status_filter_is_comma_separated(
        self, rides, driver, requests, passenger
    ) -> None:
        pending = await requests.create(await rides.offer(driver, capacity=2), passenger)
        approved = await requests.approved(
            await rides.offer(driver, capacity=2, departure_in=30), passenger
        )
        rejected = await requests.rejected(
            await rides.offer(driver, capacity=2, departure_in=36), passenger
        )

        body = expect_status(await requests.mine(passenger, status="pending,approved"), 200)
        assert {item["id"] for item in body} == {pending["id"], approved["id"]}
        assert rejected["id"] not in {item["id"] for item in body}

    async def test_limit_and_offset(self, rides, driver, requests, passenger) -> None:
        made = [
            await requests.create(await rides.offer(driver, departure_in=6 + index), passenger)
            for index in range(3)
        ]
        newest_first = [item["id"] for item in reversed(made)]

        page = expect_status(await requests.mine(passenger, limit=2), 200)
        assert [item["id"] for item in page] == newest_first[:2]

        page = expect_status(await requests.mine(passenger, limit=2, offset=2), 200)
        assert [item["id"] for item in page] == newest_first[2:]

    @pytest.mark.parametrize(("param", "value"), [("limit", 0), ("limit", 101), ("offset", -1)])
    async def test_pagination_bounds(self, requests, passenger, param: str, value: int) -> None:
        expect_error(await requests.mine(passenger, **{param: value}), 422, "VALIDATION_ERROR")

    @pytest.mark.parametrize("status", ["maybe", "pending,maybe", "PENDING"])
    async def test_an_unknown_status_in_the_filter(self, requests, passenger, status: str) -> None:
        expect_validation_error(await requests.mine(passenger, status=status), field="query.status")

    async def test_a_repeated_status_is_ignored(self, rides, driver, requests, passenger) -> None:
        """CONTRACT.md §2 (D19): "Repeats are ignored"."""
        request = await requests.create(await rides.offer(driver, capacity=2), passenger)
        body = expect_status(await requests.mine(passenger, status="pending,pending"), 200)
        assert [item["id"] for item in body] == [request["id"]]

    async def test_empty_for_a_passenger_with_no_trips(self, requests, passenger) -> None:
        assert expect_status(await requests.mine(passenger), 200) == []


class TestIncoming:
    async def test_requests_across_all_of_the_callers_rides(
        self, rides, driver, requests, users
    ) -> None:
        first = await rides.offer(driver, capacity=2)
        second = await rides.offer(driver, capacity=2, departure_in=30)
        on_first = await requests.create(first, await users.create())
        on_second = await requests.create(second, await users.create())

        body = expect_status(await requests.incoming(driver), 200)
        assert {item["id"] for item in body} == {on_first["id"], on_second["id"]}

    async def test_pending_by_default(self, rides, driver, requests, users) -> None:
        """openapi: "Default status=pending" - it feeds the Home badge."""
        offer = await rides.offer(driver, capacity=4)
        pending = await requests.create(offer, await users.create())
        await requests.approved(offer, await users.create())
        await requests.rejected(offer, await users.create())

        body = expect_status(await requests.incoming(driver), 200)
        assert [item["id"] for item in body] == [pending["id"]]

    async def test_an_explicit_status(self, rides, driver, requests, users) -> None:
        offer = await rides.offer(driver, capacity=4)
        await requests.create(offer, await users.create())
        approved = await requests.approved(offer, await users.create())

        body = expect_status(await requests.incoming(driver, status="approved"), 200)
        assert [item["id"] for item in body] == [approved["id"]]

    async def test_requests_the_caller_made_are_not_incoming(
        self, rides, requests, passenger, users
    ) -> None:
        offer = await rides.offer(await users.create_driver(), capacity=2)
        await requests.create(offer, passenger)
        assert expect_status(await requests.incoming(passenger), 200) == []

    async def test_an_unknown_status_is_rejected(self, requests, driver) -> None:
        expect_validation_error(
            await requests.incoming(driver, status="whatever"), field="query.status"
        )

    async def test_empty_for_a_driver_with_no_requests(self, rides, driver, requests) -> None:
        await rides.offer(driver)
        assert expect_status(await requests.incoming(driver), 200) == []


class TestTheRideSnapshotInARequest:
    async def test_it_reflects_the_rides_current_state(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)

        body = await requests.fetch(request, passenger)
        assert body["ride"]["status"] == "in_progress", (
            "RideRequest.ride is the live ride, not a copy taken at request time"
        )

    async def test_the_departure_time_is_utc(self, offer, requests, passenger) -> None:
        request = await requests.create(offer, passenger)
        assert request["ride"]["departure_time"].endswith("Z")
        assert clock.parse(request["ride"]["departure_time"]) > clock.now()
