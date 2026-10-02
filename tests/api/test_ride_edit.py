"""PATCH /rides/{id}: the edit-lock rules.

CONTRACT.md §4 "Rides":
  Edit (PATCH): only in `upcoming`/`full`. With ≥1 approved request, changes to
  any location field or `departure_time` → 409 RIDE_HAS_APPROVED_PASSENGERS,
  and `capacity` below the approved seats → 409 CAPACITY_BELOW_APPROVED.
  Price/notes/preferences are always editable.

Plus D16: ride preferences shallow-merge on PATCH, absent keys left alone.
"""

from __future__ import annotations

import pytest

from support import clock
from support.assertions import expect_error, expect_status, expect_validation_error
from support.rides import assert_seat_invariant, ride_in_status

LOCATION_FIELDS = {
    "start_lat": 31.9,
    "start_lng": 34.9,
    "start_address": "Allenby St 10, Tel Aviv",
    "end_lat": 31.8,
    "end_lng": 35.3,
    "end_address": "King George St 5, Jerusalem",
}
ALWAYS_EDITABLE = {
    "price_per_seat": "31.00",
    "notes": "Leaving from the north entrance",
    "preferences": {"music": False},
}
DEFAULT_PREFERENCES = {"smoking": False, "pets": False, "music": True, "gender_only": False}

# openapi gives only `notes` a `"null"` in its type, so every other field on
# RideCreate/RideUpdate refuses an explicit null.
NEVER_NULLABLE = [
    "start_lat",
    "start_lng",
    "start_address",
    "departure_time",
    "capacity",
    "price_per_seat",
    "preferences",
]


class TestFreeEditing:
    """With no approved passengers, everything is editable."""

    @pytest.mark.parametrize(("field", "value"), sorted(LOCATION_FIELDS.items()))
    async def test_locations_are_editable(self, rides, offer, field: str, value) -> None:
        body = expect_status(await rides.patch(offer, {field: value}), 200)
        assert body[field] == value

    async def test_departure_time_is_editable(self, rides, offer) -> None:
        later = clock.iso_in_hours(72)
        body = expect_status(await rides.patch(offer, {"departure_time": later}), 200)
        assert clock.parse(body["departure_time"]) == clock.parse(later)

    async def test_a_pending_request_does_not_lock_the_ride(
        self, rides, offer, requests, passenger
    ) -> None:
        """The lock is about *approved* passengers; a pending request is not one."""
        await requests.create(offer, passenger)
        body = expect_status(await rides.patch(offer, {"start_address": "Somewhere else"}), 200)
        assert body["start_address"] == "Somewhere else"

    async def test_a_cancelled_request_does_not_lock_the_ride(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.cancelled(offer, passenger)
        expect_status(await rides.patch(offer, {"departure_time": clock.iso_in_hours(72)}), 200)

    async def test_a_rejected_request_does_not_lock_the_ride(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.rejected(offer, passenger)
        expect_status(await rides.patch(offer, {"departure_time": clock.iso_in_hours(72)}), 200)

    async def test_an_empty_patch_changes_nothing(self, rides, offer) -> None:
        body = expect_status(await rides.patch(offer, {}), 200)
        assert body["start_address"] == offer.ride["start_address"]
        assert body["capacity"] == offer.ride["capacity"]

    async def test_updated_at_moves_forward(self, rides, offer) -> None:
        body = expect_status(await rides.patch(offer, {"notes": "changed"}), 200)
        assert clock.parse(body["updated_at"]) >= clock.parse(offer.ride["updated_at"])
        assert clock.parse(body["created_at"]) == clock.parse(offer.ride["created_at"])


class TestAlwaysEditable:
    """ "Price/notes/preferences are always editable" - approved seats and all."""

    @pytest.mark.parametrize(("field", "value"), sorted(ALWAYS_EDITABLE.items()))
    async def test_with_an_approved_passenger(
        self, rides, requests, users, passenger, field: str, value
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)

        body = expect_status(await rides.patch(offer, {field: value}), 200)
        if field == "preferences":
            assert body["preferences"] == {**DEFAULT_PREFERENCES, **value}
        else:
            assert body[field] == value

    async def test_on_a_full_ride(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=1)
        await requests.approved(offer, passenger)
        await rides.refresh(offer)
        assert offer.status == "full"

        body = expect_status(await rides.patch(offer, {"price_per_seat": "9.00"}), 200)
        assert body["price_per_seat"] == "9.00"
        assert body["status"] == "full", "a price change must not move the ride out of full"

    async def test_notes_can_be_cleared(self, rides, driver) -> None:
        offer = await rides.offer(driver, notes="old")
        assert expect_status(await rides.patch(offer, {"notes": None}), 200)["notes"] is None


class TestLockedByApprovedPassengers:
    @pytest.mark.parametrize(("field", "value"), sorted(LOCATION_FIELDS.items()))
    async def test_changing_a_location_is_a_conflict(
        self, rides, requests, passenger, field: str, value
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)

        response = await rides.patch(offer, {field: value})
        expect_error(response, 409, "RIDE_HAS_APPROVED_PASSENGERS")

    async def test_changing_the_departure_time_is_a_conflict(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)

        response = await rides.patch(offer, {"departure_time": clock.iso_in_hours(72)})
        expect_error(response, 409, "RIDE_HAS_APPROVED_PASSENGERS")

    async def test_the_locked_change_is_not_applied(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)
        original = await rides.fetch(offer)

        await rides.patch(offer, {"start_address": "Nowhere", "price_per_seat": "99.00"})

        after = await rides.fetch(offer)
        assert after["start_address"] == original["start_address"]
        assert after["price_per_seat"] == original["price_per_seat"], (
            "a rejected PATCH must not half-apply: the price moved while the address did not"
        )

    async def test_the_lock_lifts_when_the_passenger_cancels(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.approved(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

        expect_status(await rides.patch(offer, {"start_address": "Back to editable"}), 200)


class TestPresenceCountsAsAChange:
    """D19: "A locked field counts as a **change** when the key is present, even
    if the value is identical - the server compares what was sent, not what it
    means." The Edit Ride form therefore has to send only what it touched."""

    @pytest.mark.parametrize("field", sorted(LOCATION_FIELDS))
    async def test_resending_the_current_value_is_still_a_conflict(
        self, rides, requests, passenger, field: str
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)

        unchanged = (await rides.fetch(offer))[field]
        response = await rides.patch(offer, {field: unchanged})
        expect_error(response, 409, "RIDE_HAS_APPROVED_PASSENGERS")

    async def test_resending_the_current_departure_time_is_still_a_conflict(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)

        unchanged = (await rides.fetch(offer))["departure_time"]
        response = await rides.patch(offer, {"departure_time": unchanged})
        expect_error(response, 409, "RIDE_HAS_APPROVED_PASSENGERS")

    async def test_a_locked_field_alongside_an_editable_one_still_conflicts(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)
        unchanged = (await rides.fetch(offer))["start_lat"]

        response = await rides.patch(offer, {"start_lat": unchanged, "notes": "fine on its own"})
        expect_error(response, 409, "RIDE_HAS_APPROVED_PASSENGERS")
        assert (await rides.fetch(offer))["notes"] is None, "nothing may be applied"


class TestDepartureInPast:
    """D19: "a `departure_time` sent on `PATCH` must still be in the future
    (422 DEPARTURE_IN_PAST), exactly as on create"."""

    async def test_moving_the_departure_into_the_past(self, rides, offer) -> None:
        response = await rides.patch(offer, {"departure_time": clock.iso_in_hours(-1)})
        expect_error(response, 422, "DEPARTURE_IN_PAST")

    async def test_the_ride_keeps_its_departure_time(self, rides, offer) -> None:
        await rides.patch(offer, {"departure_time": clock.iso_in_hours(-1)})
        after = await rides.fetch(offer)
        assert clock.parse(after["departure_time"]) == clock.parse(offer.ride["departure_time"])

    async def test_a_near_future_departure_is_fine(self, rides, offer) -> None:
        soon = clock.iso_in_hours(0.5)
        body = expect_status(await rides.patch(offer, {"departure_time": soon}), 200)
        assert clock.parse(body["departure_time"]) == clock.parse(soon)


class TestNullability:
    """@backend, Phase 2: "notes is the only nullable field on
    RideCreate/RideUpdate; an explicit null on any other field is a 422" - which
    is what openapi.yaml says, since only `notes` has `"null"` in its type."""

    @pytest.mark.parametrize("field", NEVER_NULLABLE)
    async def test_an_explicit_null_is_rejected_and_names_its_field(
        self, rides, offer, field: str
    ) -> None:
        """CONTRACT.md §5: `details` lists fields. The null has to be reported
        where it was sent (`body.<field>`), because that is what @frontend
        highlights - a whole-body error leaves it nothing to point at."""
        expect_validation_error(await rides.patch(offer, {field: None}), field=field)

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param(
                name,
                marks=pytest.mark.xfail(
                    reason="FAIL reported to @backend 2026-10-02: POST /rides accepts "
                    "preferences: null (201, silently ignored) while PATCH correctly answers 422 "
                    "at body.preferences. The per-key nulls are right on both "
                    "(body.preferences.pets), so only the whole object on create is missing the "
                    "NotNull annotation.",
                    strict=True,
                )
                if name == "preferences"
                else (),
            )
            for name in NEVER_NULLABLE
        ],
    )
    async def test_the_same_null_is_rejected_on_create(self, rides, driver, field: str) -> None:
        """One shape in both directions: POST and PATCH must agree, because
        @frontend's Create and Edit forms share their validation handling."""
        expect_validation_error(await rides.create_response(driver, **{field: None}), field=field)


class TestCapacity:
    async def test_raising_capacity_frees_seats(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=1)
        await requests.approved(offer, passenger)
        await rides.refresh(offer)
        assert offer.status == "full"

        body = expect_status(await rides.patch(offer, {"capacity": 3}), 200)
        assert body["capacity"] == 3
        assert body["available_seats"] == 2
        assert body["status"] == "upcoming", "CONTRACT.md §3: seats freed by a capacity edit"
        await assert_seat_invariant(db, offer.id)

    async def test_lowering_capacity_to_exactly_the_approved_seats(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=4)
        await requests.approved(offer, passenger, seats=2)

        body = expect_status(await rides.patch(offer, {"capacity": 2}), 200)
        assert body["available_seats"] == 0
        assert body["status"] == "full"
        await assert_seat_invariant(db, offer.id)

    async def test_lowering_capacity_below_the_approved_seats(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=4)
        await requests.approved(offer, passenger, seats=3)

        expect_error(await rides.patch(offer, {"capacity": 2}), 409, "CAPACITY_BELOW_APPROVED")
        await rides.refresh(offer)
        assert offer.ride["capacity"] == 4, "the rejected capacity change must not be applied"
        await assert_seat_invariant(db, offer.id)

    async def test_capacity_may_be_lowered_with_no_approved_seats(self, rides, driver, db) -> None:
        offer = await rides.offer(driver, capacity=4)
        body = expect_status(await rides.patch(offer, {"capacity": 1}), 200)
        assert (body["capacity"], body["available_seats"], body["status"]) == (1, 1, "upcoming")
        await assert_seat_invariant(db, offer.id)

    async def test_capacity_is_not_a_locked_field(self, rides, requests, passenger) -> None:
        """A capacity change with approved passengers is governed by
        CAPACITY_BELOW_APPROVED, not by RIDE_HAS_APPROVED_PASSENGERS."""
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)
        expect_status(await rides.patch(offer, {"capacity": 5}), 200)

    @pytest.mark.parametrize("capacity", [0, 9])
    async def test_capacity_bounds_still_apply(self, rides, offer, capacity: int) -> None:
        expect_validation_error(await rides.patch(offer, {"capacity": capacity}), field="capacity")


class TestPreferencesMerge:
    """D16: ride preferences shallow-merge, exactly like user preferences."""

    async def test_a_partial_patch_leaves_the_other_keys_alone(self, rides, driver) -> None:
        offer = await rides.offer(driver, preferences={"smoking": True, "pets": True})

        body = expect_status(await rides.patch(offer, {"preferences": {"music": False}}), 200)
        assert body["preferences"] == {
            "smoking": True,
            "pets": True,
            "music": False,
            "gender_only": False,
        }

    async def test_an_empty_preferences_object_changes_nothing(self, rides, driver) -> None:
        offer = await rides.offer(driver, preferences={"smoking": True})
        body = expect_status(await rides.patch(offer, {"preferences": {}}), 200)
        assert body["preferences"]["smoking"] is True

    async def test_reads_always_come_back_complete(self, rides, driver) -> None:
        offer = await rides.offer(driver, preferences={"gender_only": True})
        body = await rides.fetch(offer)
        assert set(body["preferences"]) == set(DEFAULT_PREFERENCES)

    async def test_the_merge_is_persisted(self, rides, driver) -> None:
        offer = await rides.offer(driver, preferences={"pets": True})
        expect_status(await rides.patch(offer, {"preferences": {"smoking": True}}), 200)
        assert (await rides.fetch(offer))["preferences"] == {
            "smoking": True,
            "pets": True,
            "music": True,
            "gender_only": False,
        }

    @pytest.mark.parametrize("value", ["yes", 1])
    async def test_a_preference_must_be_a_real_boolean(self, rides, offer, value) -> None:
        expect_validation_error(
            await rides.patch(offer, {"preferences": {"pets": value}}), field="pets"
        )

    @pytest.mark.parametrize("key", ["smoking", "pets", "music", "gender_only"])
    async def test_a_preference_may_not_be_null(self, rides, offer, key: str) -> None:
        """A merge leaves an absent key alone; null is not a way to spell absent."""
        expect_validation_error(await rides.patch(offer, {"preferences": {key: None}}), field=key)


class TestEditableStatuses:
    @pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
    async def test_patch_is_refused_after_the_ride_leaves_upcoming_or_full(
        self, rides, requests, users, status: str
    ) -> None:
        offer = await ride_in_status(status, rides=rides, requests=requests, users=users)
        expect_error(
            await rides.patch(offer, {"notes": "too late"}), 409, "INVALID_STATE_TRANSITION"
        )

    @pytest.mark.parametrize("status", ["upcoming", "full"])
    async def test_patch_is_allowed_while_the_ride_is_open(
        self, rides, requests, users, status: str
    ) -> None:
        offer = await ride_in_status(status, rides=rides, requests=requests, users=users)
        expect_status(await rides.patch(offer, {"notes": "still editable"}), 200)


class TestPermissions:
    async def test_another_user_cannot_edit_the_ride(self, rides, offer, other_user) -> None:
        expect_error(await rides.patch(offer, {"notes": "mine now"}, other_user), 403, "FORBIDDEN")

    async def test_a_passenger_cannot_edit_the_ride(
        self, rides, offer, requests, passenger
    ) -> None:
        await requests.approved(offer, passenger)
        expect_error(await rides.patch(offer, {"notes": "mine now"}, passenger), 403, "FORBIDDEN")

    async def test_an_admin_does_not_get_a_back_door_here(self, rides, offer, admin) -> None:
        """PATCH /rides/{id} is "driver only". Admins act through /admin/* (Phase 6)."""
        expect_error(await rides.patch(offer, {"notes": "admin"}, admin), 403, "FORBIDDEN")

    async def test_a_missing_ride_is_404(self, client, user) -> None:
        response = await client.patch("/rides/9999999", json={"notes": "x"}, headers=user.headers)
        expect_error(response, 404, "NOT_FOUND")
