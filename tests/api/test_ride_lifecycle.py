"""The ride state machine (CONTRACT.md §3 "Ride", D7).

    upcoming ──(seats hit 0)──▶ full ──(seats freed by capacity edit)──▶ upcoming
    upcoming | full ──start──▶ in_progress ──complete──▶ completed
    upcoming | full ──cancel (driver)──▶ cancelled

`completed` and `cancelled` are terminal; any other transition is 409
INVALID_STATE_TRANSITION. Admin force-cancel is Phase 6.

Every ride here departs inside the 2h start window unless the test is about
TOO_EARLY_TO_START, so a 409 can only mean the *state* was wrong.
"""

from __future__ import annotations

import pytest

from support.assertions import expect_error, expect_status
from support.rides import (
    BOUNDARY_MARGIN_HOURS,
    RIDE_STATUSES,
    STARTABLE_HOURS,
    TOO_EARLY_HOURS,
    assert_seat_invariant,
    notification_rows,
    notification_types,
    request_statuses,
    ride_in_status,
)

# The action → the statuses it is allowed from, and the status it produces.
TRANSITIONS = {
    "cancel": (("upcoming", "full"), "cancelled"),
    "start": (("upcoming", "full"), "in_progress"),
    "complete": (("in_progress",), "completed"),
}

MATRIX = [
    (action, status, status in allowed)
    for action, (allowed, _) in TRANSITIONS.items()
    for status in RIDE_STATUSES
]


class TestStateMachine:
    @pytest.mark.parametrize(
        ("action", "status", "allowed"),
        MATRIX,
        ids=[f"{a}-from-{s}" for a, s, _ in MATRIX],
    )
    async def test_every_transition(
        self, rides, requests, users, action: str, status: str, allowed: bool
    ) -> None:
        offer = await ride_in_status(
            status, rides=rides, requests=requests, users=users, departure_in=STARTABLE_HOURS
        )
        response = await getattr(rides, action)(offer)

        if allowed:
            body = expect_status(response, 200)
            assert body["status"] == TRANSITIONS[action][1]
        else:
            expect_error(response, 409, "INVALID_STATE_TRANSITION")
            assert (await rides.fetch(offer))["status"] == status, (
                "a refused transition must leave the ride where it was"
            )

    async def test_a_terminal_status_cannot_be_repeated(self, rides, offer) -> None:
        expect_status(await rides.cancel(offer), 200)
        expect_error(await rides.cancel(offer), 409, "INVALID_STATE_TRANSITION")

    async def test_the_full_ride_round_trip(self, rides, requests, passenger, db) -> None:
        """upcoming → full → upcoming, driven by seats only (CONTRACT.md §3)."""
        offer = await rides.offer(capacity=1, departure_in=24)
        request = await requests.approved(offer, passenger)
        assert (await rides.refresh(offer))["status"] == "full"

        expect_status(await requests.cancel(request, passenger), 200)
        assert (await rides.refresh(offer))["status"] == "upcoming"
        await assert_seat_invariant(db, offer.id)


class TestStartWindow:
    """CONTRACT.md §3 + D7: start is allowed from `departure_time - 2h` onward."""

    async def test_too_early(self, rides, driver) -> None:
        offer = await rides.offer(driver, departure_in=TOO_EARLY_HOURS)
        expect_error(await rides.start(offer), 409, "TOO_EARLY_TO_START")
        assert (await rides.fetch(offer))["status"] == "upcoming"

    async def test_just_inside_the_window(self, rides, driver) -> None:
        offer = await rides.offer(driver, departure_in=2 - BOUNDARY_MARGIN_HOURS)
        assert expect_status(await rides.start(offer), 200)["status"] == "in_progress"

    async def test_just_outside_the_window(self, rides, driver) -> None:
        offer = await rides.offer(driver, departure_in=2 + BOUNDARY_MARGIN_HOURS)
        expect_error(await rides.start(offer), 409, "TOO_EARLY_TO_START")

    async def test_a_ride_already_past_its_departure_can_still_start(self, rides, driver) -> None:
        """ "from departure - 2h onward" has no upper bound; the stale-ride job
        (Phase 4) is what eventually closes a forgotten ride."""
        offer = await rides.offer(driver, departure_in=0.1)
        expect_status(await rides.start(offer), 200)


class TestStartCascade:
    async def test_pending_requests_are_auto_rejected(self, rides, requests, users, db) -> None:
        offer = await rides.offer(capacity=3, departure_in=STARTABLE_HOURS)
        approved_passenger = await users.create()
        pending_passenger = await users.create()
        approved = await requests.approved(offer, approved_passenger)
        pending = await requests.create(offer, pending_passenger)

        expect_status(await rides.start(offer), 200)

        statuses = await request_statuses(db, offer.id)
        assert statuses[pending["id"]] == "rejected", "CONTRACT.md §3: pending → rejected on start"
        assert statuses[approved["id"]] == "approved", "an approved seat survives the start"

    async def test_the_auto_rejection_sets_responded_at(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.create(offer, passenger)
        assert request["responded_at"] is None

        expect_status(await rides.start(offer), 200)
        after = await requests.fetch(request, passenger)
        assert after["status"] == "rejected"
        assert after["responded_at"] is not None, (
            "CONTRACT.md §3: responded_at is set on every transition out of pending"
        )

    async def test_seats_are_untouched_by_the_auto_rejection(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, await users.create(), seats=2)
        await requests.create(offer, await users.create())

        body = expect_status(await rides.start(offer), 200)
        assert body["available_seats"] == 1
        await assert_seat_invariant(db, offer.id)


class TestCancelCascade:
    async def test_pending_and_approved_requests_are_cancelled(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=24)
        approved = await requests.approved(offer, await users.create())
        pending = await requests.create(offer, await users.create())

        expect_status(await rides.cancel(offer), 200)

        statuses = await request_statuses(db, offer.id)
        assert statuses[approved["id"]] == "cancelled"
        assert statuses[pending["id"]] == "cancelled"

    async def test_a_rejected_request_stays_rejected(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        rejected = await requests.rejected(offer, passenger)

        expect_status(await rides.cancel(offer), 200)
        assert (await request_statuses(db, offer.id))[rejected["id"]] == "rejected"

    async def test_cancelling_with_approved_passengers_is_allowed(
        self, rides, requests, passenger
    ) -> None:
        """D3: the driver may cancel a ride that has approved passengers."""
        offer = await rides.offer(capacity=2, departure_in=24)
        await requests.approved(offer, passenger)
        assert expect_status(await rides.cancel(offer), 200)["status"] == "cancelled"

    async def test_cancelling_is_allowed_close_to_departure(self, rides, driver) -> None:
        """The 1h cutoff is the *passenger's* (D15); the driver has none."""
        offer = await rides.offer(driver, departure_in=0.25)
        expect_status(await rides.cancel(offer), 200)


class TestCompletion:
    async def test_approved_requests_survive_completion(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        approved = await requests.approved(offer, passenger)

        expect_status(await rides.start(offer), 200)
        expect_status(await rides.complete(offer), 200)

        assert (await request_statuses(db, offer.id))[approved["id"]] == "approved", (
            "the ride is history now; the approved seat is what makes the passenger a participant"
        )

    async def test_completion_does_not_free_seats(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=1, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)

        body = expect_status(await rides.complete(offer), 200)
        assert body["available_seats"] == 0
        await assert_seat_invariant(db, offer.id)


class TestPermissions:
    @pytest.mark.parametrize("action", ["cancel", "start", "complete"])
    async def test_another_user_cannot_drive_the_ride(
        self, rides, offer, other_user, action: str
    ) -> None:
        response = await getattr(rides, action)(offer, other_user)
        expect_error(response, 403, "FORBIDDEN")

    @pytest.mark.parametrize("action", ["cancel", "start", "complete"])
    async def test_a_passenger_cannot_drive_the_ride(
        self, rides, requests, passenger, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)

        response = await getattr(rides, action)(offer, passenger)
        expect_error(response, 403, "FORBIDDEN")

    @pytest.mark.parametrize("action", ["cancel", "start", "complete"])
    async def test_an_admin_has_no_back_door(self, rides, offer, admin, action: str) -> None:
        """Admins cancel through /admin/rides/{id}/force-cancel (Phase 6)."""
        expect_error(await getattr(rides, action)(offer, admin), 403, "FORBIDDEN")

    @pytest.mark.parametrize("action", ["cancel", "start", "complete"])
    async def test_forbidden_beats_the_state_check(
        self, rides, requests, users, other_user, action: str
    ) -> None:
        """A stranger must not learn the ride's state from the error code."""
        offer = await ride_in_status("completed", rides=rides, requests=requests, users=users)
        expect_error(await getattr(rides, action)(offer, other_user), 403, "FORBIDDEN")

    @pytest.mark.parametrize("action", ["cancel", "start", "complete"])
    async def test_a_missing_ride_is_404(self, client, user, action: str) -> None:
        response = await client.post(f"/rides/9999999/{action}", headers=user.headers)
        expect_error(response, 404, "NOT_FOUND")


class TestNotificationRows:
    """PLAN Phase 2 for @backend: "Write notification rows (no push yet)".
    The endpoints and the WebSocket arrive in Phase 4, so Phase 2 reads the
    table directly. Triggers: CONTRACT.md §7.
    """

    async def test_ride_cancelled_reaches_pending_and_approved_passengers(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=24)
        approved_passenger = await users.create()
        pending_passenger = await users.create()
        await requests.approved(offer, approved_passenger)
        await requests.create(offer, pending_passenger)

        expect_status(await rides.cancel(offer), 200)

        for passenger in (approved_passenger, pending_passenger):
            assert "ride_cancelled" in await notification_types(db, passenger.id), (
                f"user {passenger.id} was not told the ride was cancelled"
            )
        assert "ride_cancelled" not in await notification_types(db, offer.driver.id), (
            "CONTRACT.md §7: the driver is notified only when an *admin* cancels"
        )

    async def test_ride_started_reaches_approved_passengers_only(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=STARTABLE_HOURS)
        approved_passenger = await users.create()
        pending_passenger = await users.create()
        await requests.approved(offer, approved_passenger)
        await requests.create(offer, pending_passenger)

        expect_status(await rides.start(offer), 200)

        assert "ride_started" in await notification_types(db, approved_passenger.id)
        started = await notification_types(db, pending_passenger.id)
        assert "ride_started" not in started
        assert "request_rejected" in started, "the auto-rejection is notified (CONTRACT.md §7)"

    async def test_ride_completed_reaches_the_driver_and_passengers(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)
        expect_status(await rides.complete(offer), 200)

        assert "ride_completed" in await notification_types(db, passenger.id)
        assert "ride_completed" in await notification_types(db, offer.driver.id)

    async def test_a_notification_points_back_at_its_ride(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        await requests.approved(offer, passenger)
        expect_status(await rides.cancel(offer), 200)

        rows = await notification_rows(db, passenger.id, type_="ride_cancelled")
        assert rows, "no ride_cancelled row"
        row = rows[0]
        assert row["related_entity_type"] == "ride"
        assert row["related_entity_id"] == offer.id
        assert row["is_read"] is False
        assert str(row["title"]).strip(), "a notification needs a title"
        assert str(row["message"]).strip(), "a notification needs a message"
        assert row["created_at"] is not None
