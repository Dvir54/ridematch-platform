"""Offering and reading rides: POST /rides, GET /rides/mine, GET /rides/{id}.

Contract: openapi.yaml `RideCreate` / `Ride`, CONTRACT.md §4 "Rides" and
"Vehicles", §2 (Money, timestamps, list conventions).
"""

from __future__ import annotations

import pytest

from support import clock
from support.assertions import expect_error, expect_status, expect_validation_error
from support.factories import DEFAULT_VEHICLE, OMIT
from support.rides import DEFAULT_CAPACITY, assert_seat_invariant, ride_payload

RIDES = "/rides"
MINE = "/rides/mine"

DEFAULT_PREFERENCES = {"smoking": False, "pets": False, "music": True, "gender_only": False}


class TestCreate:
    async def test_a_driver_offers_a_ride(self, rides, driver, db) -> None:
        body = expect_status(await rides.create_response(driver), 201)

        assert body["status"] == "upcoming"
        assert body["capacity"] == DEFAULT_CAPACITY
        assert body["available_seats"] == DEFAULT_CAPACITY, (
            "CONTRACT.md §4: a new ride has every seat free"
        )
        assert body["driver"]["id"] == driver.id
        assert body["notes"] is None
        await assert_seat_invariant(db, body["id"])

    async def test_the_echoed_ride_matches_the_request(self, rides, driver) -> None:
        payload = ride_payload(capacity=4, price_per_seat="12.00", notes="Two bags max")
        body = expect_status(await rides.create_response(driver, **payload), 201)

        for field in (
            "start_lat",
            "start_lng",
            "start_address",
            "end_lat",
            "end_lng",
            "end_address",
        ):
            assert body[field] == payload[field], f"{field} came back changed"
        assert body["capacity"] == 4
        assert body["notes"] == "Two bags max"
        assert clock.parse(body["departure_time"]) == clock.parse(payload["departure_time"])

    async def test_preferences_default_to_the_documented_values(self, rides, driver) -> None:
        """openapi `RidePreferences` carries the defaults; `RidePreferencesPatch`
        (the write shape) has none, so the server fills them on create."""
        body = expect_status(await rides.create_response(driver), 201)
        assert body["preferences"] == DEFAULT_PREFERENCES

    async def test_given_preferences_are_merged_over_the_defaults(self, rides, driver) -> None:
        body = expect_status(
            await rides.create_response(driver, preferences={"smoking": True}), 201
        )
        assert body["preferences"] == {**DEFAULT_PREFERENCES, "smoking": True}

    async def test_timestamps_come_back_as_utc_with_z(self, rides, driver) -> None:
        body = expect_status(await rides.create_response(driver), 201)
        for field in ("departure_time", "created_at", "updated_at"):
            assert body[field].endswith("Z"), f"CONTRACT.md §2: {field} must be UTC with Z"

    async def test_timestamps_are_second_resolution(self, rides, driver) -> None:
        """CONTRACT.md §2 (0.4.3): UTC `Z` at **second** resolution, microseconds
        dropped. Pinned because the suite sends whole seconds and compares."""
        sent = clock.iso(clock.in_hours(24).replace(microsecond=123456))
        body = expect_status(await rides.create_response(driver, departure_time=sent), 201)
        for field in ("departure_time", "created_at", "updated_at"):
            assert clock.parse(body[field]).microsecond == 0, f"{field} kept microseconds"
        assert clock.parse(body["departure_time"]) == clock.parse(sent).replace(microsecond=0)

    async def test_a_naive_departure_time_is_read_as_utc(self, rides, driver) -> None:
        """§2 (0.4.3): "a naive datetime is read as UTC"."""
        naive = clock.whole_seconds(clock.in_hours(24)).replace(tzinfo=None).isoformat()
        assert not naive.endswith("Z") and "+" not in naive
        body = expect_status(await rides.create_response(driver, departure_time=naive), 201)
        assert clock.parse(body["departure_time"]) == clock.parse(naive + "Z")

    async def test_an_offset_departure_time_is_accepted_and_normalised(self, rides, driver) -> None:
        """CONTRACT.md §2: the server accepts any offset and answers in UTC."""
        as_offset = clock.iso_at_offset(clock.in_hours(24), 2)
        assert as_offset.endswith("+02:00")
        body = expect_status(await rides.create_response(driver, departure_time=as_offset), 201)
        assert body["departure_time"].endswith("Z")
        assert clock.parse(body["departure_time"]) == clock.parse(as_offset)

    async def test_the_driver_is_a_public_user_without_the_plate(self, rides, driver) -> None:
        """`Ride.driver` is a UserPublic: make/model/colour, never the plate
        (CONTRACT.md §4 "Vehicles", D14). The plate has its own field."""
        body = expect_status(await rides.create_response(driver), 201)
        vehicle = body["driver"]["vehicle"]
        assert vehicle == {k: v for k, v in DEFAULT_VEHICLE.items() if k != "plate"}
        assert "plate" not in vehicle
        for private in ("email", "phone", "date_of_birth", "is_admin"):
            assert private not in body["driver"], f"Ride.driver leaks {private}"


class TestCreateRequiresAVehicle:
    """CONTRACT.md §4 "Vehicles": a vehicle is required to create a ride."""

    async def test_no_vehicle_is_a_conflict(self, rides, passenger) -> None:
        expect_error(await rides.create_response(passenger), 409, "VEHICLE_REQUIRED")

    async def test_adding_a_vehicle_unblocks_it(self, client, rides, passenger) -> None:
        expect_status(
            await client.patch(
                "/users/me", json={"vehicle": dict(DEFAULT_VEHICLE)}, headers=passenger.headers
            ),
            200,
        )
        expect_status(await rides.create_response(passenger), 201)


class TestCreateValidation:
    async def test_a_past_departure_is_rejected(self, rides, driver) -> None:
        response = await rides.create_response(driver, departure_in=-1)
        expect_error(response, 422, "DEPARTURE_IN_PAST")

    @pytest.mark.parametrize(
        "field",
        [
            "start_lat",
            "start_lng",
            "start_address",
            "end_lat",
            "end_lng",
            "end_address",
            "departure_time",
            "capacity",
            "price_per_seat",
        ],
    )
    async def test_every_required_field_is_required(self, rides, driver, field: str) -> None:
        response = await rides.create_response(driver, **{field: OMIT})
        expect_validation_error(response, field=field)

    @pytest.mark.parametrize("capacity", [0, -1, 9])
    async def test_capacity_outside_1_to_8(self, rides, driver, capacity: int) -> None:
        expect_validation_error(
            await rides.create_response(driver, capacity=capacity), field="capacity"
        )

    @pytest.mark.parametrize("capacity", [1, 8])
    async def test_capacity_at_the_bounds_is_accepted(self, rides, driver, capacity: int) -> None:
        body = expect_status(await rides.create_response(driver, capacity=capacity), 201)
        assert body["capacity"] == capacity

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("start_lat", 90.1),
            ("start_lat", -90.1),
            ("start_lng", 180.1),
            ("start_lng", -180.1),
            ("end_lat", 91),
            ("end_lng", -181),
        ],
    )
    async def test_coordinates_outside_the_world(self, rides, driver, field, value) -> None:
        expect_validation_error(await rides.create_response(driver, **{field: value}), field=field)

    @pytest.mark.parametrize("price", [-1, "-1.00", "abc", "", None])
    async def test_a_price_that_is_not_money(self, rides, driver, price) -> None:
        """CONTRACT.md §2: money is a decimal **string**, never a float."""
        expect_validation_error(
            await rides.create_response(driver, price_per_seat=price), field="price_per_seat"
        )

    @pytest.mark.parametrize("price", [25.5, 25, 0, True])
    async def test_a_json_number_is_not_money(self, rides, driver, price) -> None:
        """CONTRACT.md §2 (0.4.3): "a JSON number in a request body is a 422
        VALIDATION_ERROR, since that's what typing it as a string is for" - even
        one that would round-trip cleanly."""
        expect_validation_error(
            await rides.create_response(driver, price_per_seat=price), field="price_per_seat"
        )

    @pytest.mark.parametrize(
        ("sent", "returned"), [("25", "25.00"), ("25.5", "25.50"), ("25.50", "25.50")]
    )
    async def test_one_or_two_places_in_two_places_out(
        self, rides, driver, sent: str, returned: str
    ) -> None:
        """§2: "On the way in, 1 or 2 decimal places or none ...; on the way out,
        always 2"."""
        body = expect_status(await rides.create_response(driver, price_per_seat=sent), 201)
        assert body["price_per_seat"] == returned

    @pytest.mark.parametrize("price", ["1.234", "0.001"])
    async def test_more_than_two_places_is_rejected(self, rides, driver, price: str) -> None:
        expect_validation_error(
            await rides.create_response(driver, price_per_seat=price), field="price_per_seat"
        )

    async def test_a_free_ride_is_allowed(self, rides, driver) -> None:
        body = expect_status(await rides.create_response(driver, price_per_seat="0.00"), 201)
        assert body["price_per_seat"] == "0.00"

    async def test_money_comes_back_with_two_decimals(self, rides, driver) -> None:
        """CONTRACT.md §2: "decimal string with 2 places, e.g. "25.50"."""
        body = expect_status(await rides.create_response(driver, price_per_seat="7.5"), 201)
        assert body["price_per_seat"] == "7.50"

    @pytest.mark.parametrize("address", ["", "x" * 256])
    async def test_address_length(self, rides, driver, address: str) -> None:
        expect_validation_error(
            await rides.create_response(driver, start_address=address), field="start_address"
        )

    async def test_notes_too_long(self, rides, driver) -> None:
        expect_validation_error(
            await rides.create_response(driver, notes="x" * 1001), field="notes"
        )

    async def test_notes_may_be_null(self, rides, driver) -> None:
        assert expect_status(await rides.create_response(driver, notes=None), 201)["notes"] is None

    @pytest.mark.parametrize("value", ["yes", 1, "true"])
    async def test_preferences_must_be_real_booleans(self, rides, driver, value) -> None:
        """CONTRACT.md §4: "Booleans must be real JSON booleans."""
        expect_validation_error(
            await rides.create_response(driver, preferences={"smoking": value}), field="smoking"
        )

    async def test_an_unknown_preference_key_is_not_stored(self, rides, driver) -> None:
        """The contract names exactly four keys. Rejecting or ignoring a fifth
        are both defensible; silently storing it is not."""
        response = await rides.create_response(driver, preferences={"karaoke": True})
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
            return
        assert expect_status(response, 201)["preferences"] == DEFAULT_PREFERENCES


class TestGetOne:
    async def test_the_driver_reads_their_own_ride(self, rides, offer) -> None:
        assert (await rides.fetch(offer))["id"] == offer.id

    async def test_any_onboarded_user_may_read_a_ride(self, rides, offer, other_user) -> None:
        """Rides are public to signed-in users - that is how a passenger opens
        Ride Details from search. Only the plate is held back (D14)."""
        body = await rides.fetch(offer, other_user)
        assert body["id"] == offer.id
        assert body["driver_vehicle_plate"] is None

    async def test_a_missing_ride_is_404(self, rides, user) -> None:
        expect_error(await rides.get(9_999_999, user), 404, "NOT_FOUND")

    async def test_a_cancelled_ride_is_still_readable(self, rides, offer) -> None:
        expect_status(await rides.cancel(offer), 200)
        assert (await rides.fetch(offer))["status"] == "cancelled"


class TestMine:
    async def test_only_the_callers_own_rides(self, rides, driver, users) -> None:
        mine = await rides.offer(driver)
        other = await rides.offer(await users.create_driver())

        body = expect_status(await rides.mine(driver), 200)
        assert [ride["id"] for ride in body] == [mine.id]
        assert other.id not in [ride["id"] for ride in body]

    async def test_empty_for_a_driver_with_no_rides(self, rides, driver) -> None:
        assert expect_status(await rides.mine(driver), 200) == []

    async def test_ordered_by_departure_ascending(self, rides, driver) -> None:
        late = await rides.offer(driver, departure_in=48)
        early = await rides.offer(driver, departure_in=6)
        middle = await rides.offer(driver, departure_in=24)

        body = expect_status(await rides.mine(driver), 200)
        assert [ride["id"] for ride in body] == [early.id, middle.id, late.id]

    async def test_every_status_is_listed_by_default(self, rides, driver, users, requests) -> None:
        upcoming = await rides.offer(driver, departure_in=30)
        cancelled = await rides.offer(driver, departure_in=36)
        expect_status(await rides.cancel(cancelled), 200)

        statuses = {
            ride["id"]: ride["status"] for ride in expect_status(await rides.mine(driver), 200)
        }
        assert statuses == {upcoming.id: "upcoming", cancelled.id: "cancelled"}

    async def test_status_filter_is_comma_separated(self, rides, driver, requests, users) -> None:
        """CONTRACT.md §2: "Status filters: comma-separated, e.g. ?status=upcoming,full"."""
        upcoming = await rides.offer(driver, capacity=2, departure_in=30)
        full = await rides.offer(driver, capacity=1, departure_in=36)
        await requests.approved(full, await users.create(), seats=1)
        cancelled = await rides.offer(driver, departure_in=42)
        expect_status(await rides.cancel(cancelled), 200)

        body = expect_status(await rides.mine(driver, status="upcoming,full"), 200)
        assert {ride["id"] for ride in body} == {upcoming.id, full.id}

        body = expect_status(await rides.mine(driver, status="cancelled"), 200)
        assert [ride["id"] for ride in body] == [cancelled.id]

    async def test_limit_and_offset(self, rides, driver) -> None:
        first = await rides.offer(driver, departure_in=6)
        second = await rides.offer(driver, departure_in=12)
        third = await rides.offer(driver, departure_in=18)

        page = expect_status(await rides.mine(driver, limit=2), 200)
        assert [ride["id"] for ride in page] == [first.id, second.id]

        page = expect_status(await rides.mine(driver, limit=2, offset=2), 200)
        assert [ride["id"] for ride in page] == [third.id]

    @pytest.mark.parametrize(("param", "value"), [("limit", 0), ("limit", 101), ("offset", -1)])
    async def test_pagination_bounds(self, rides, driver, param: str, value: int) -> None:
        expect_error(await rides.mine(driver, **{param: value}), 422, "VALIDATION_ERROR")

    @pytest.mark.parametrize("status", ["nearly", "upcoming,nearly", "UPCOMING"])
    async def test_an_unknown_status_in_the_filter(self, rides, driver, status: str) -> None:
        """CONTRACT.md §2 (D19): an unknown value is a 422 VALIDATION_ERROR with
        `details[].field = "query.status"`, like a single-value enum parameter."""
        expect_validation_error(await rides.mine(driver, status=status), field="query.status")

    async def test_a_repeated_status_is_ignored(self, rides, driver) -> None:
        offer = await rides.offer(driver)
        body = expect_status(await rides.mine(driver, status="upcoming,upcoming"), 200)
        assert [ride["id"] for ride in body] == [offer.id]

    @pytest.mark.parametrize("status", ["", ",", ",,"])
    async def test_an_empty_status_means_no_filter(self, rides, driver, status: str) -> None:
        """CONTRACT.md §2 (0.4.3): an empty value, or one that is all commas,
        means no filter rather than an error - "it's what a filter UI sends with
        nothing selected"."""
        upcoming = await rides.offer(driver, departure_in=30)
        cancelled = await rides.offer(driver, departure_in=36)
        expect_status(await rides.cancel(cancelled), 200)

        body = expect_status(await rides.mine(driver, status=status), 200)
        assert {ride["id"] for ride in body} == {upcoming.id, cancelled.id}

    async def test_a_filter_that_matches_nothing_is_empty_not_an_error(self, rides, driver) -> None:
        await rides.offer(driver)
        assert expect_status(await rides.mine(driver, status="completed"), 200) == []

    async def test_the_plate_is_visible_on_the_drivers_own_list(self, rides, offer) -> None:
        body = expect_status(await rides.mine(offer.driver), 200)
        assert body[0]["driver_vehicle_plate"] == DEFAULT_VEHICLE["plate"]
