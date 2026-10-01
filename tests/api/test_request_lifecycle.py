"""The ride-request state machine and the seat arithmetic behind it.

CONTRACT.md §3 "Ride request":
    pending ──approve (driver)──▶ approved
    pending ──reject (driver)──▶ rejected
    pending ──cancel (passenger, before ride starts)──▶ cancelled
    approved ──cancel (passenger, until departure - 1h)──▶ cancelled

CONTRACT.md §4: `available_seats = capacity - SUM(seats_requested of approved
requests)` must hold at all times, and approve runs under a row lock.
"""

from __future__ import annotations

import asyncio

import pytest

from support.assertions import expect_error, expect_status
from support.rides import (
    BOUNDARY_MARGIN_HOURS,
    REQUEST_STATUSES,
    STARTABLE_HOURS,
    TOO_LATE_HOURS,
    approved_seats,
    assert_seat_invariant,
    notification_types,
)

# action → (statuses it is allowed from, the status it produces, who may do it)
TRANSITIONS = {
    "approve": (("pending",), "approved", "driver"),
    "reject": (("pending",), "rejected", "driver"),
    "cancel": (("pending", "approved"), "cancelled", "passenger"),
}

MATRIX = [
    (action, status, status in allowed)
    for action, (allowed, _, _) in TRANSITIONS.items()
    for status in REQUEST_STATUSES
]


class TestStateMachine:
    @pytest.mark.parametrize(
        ("action", "status", "allowed"),
        MATRIX,
        ids=[f"{a}-from-{s}" for a, s, _ in MATRIX],
    )
    async def test_every_transition(
        self, rides, requests, passenger, action: str, status: str, allowed: bool
    ) -> None:
        offer = await rides.offer(capacity=4, departure_in=24)
        request = await requests.in_status(offer, status, passenger)
        actor = offer.driver if TRANSITIONS[action][2] == "driver" else passenger

        response = await getattr(requests, action)(request, actor)

        if allowed:
            body = expect_status(response, 200)
            assert body["status"] == TRANSITIONS[action][1]
        else:
            expect_error(response, 409, "INVALID_STATE_TRANSITION")
            assert (await requests.fetch(request, passenger))["status"] == status, (
                "a refused transition must leave the request where it was"
            )

    @pytest.mark.parametrize("action", ["approve", "reject"])
    async def test_responded_at_is_set_on_the_way_out_of_pending(
        self, rides, requests, passenger, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)
        assert request["responded_at"] is None

        body = expect_status(await getattr(requests, action)(request, offer.driver), 200)
        assert body["responded_at"] is not None
        assert body["requested_at"] == request["requested_at"], "requested_at must not move"

    async def test_responded_at_is_set_when_the_passenger_cancels(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)

        body = expect_status(await requests.cancel(request, passenger), 200)
        assert body["responded_at"] is not None

    async def test_a_second_approval_is_refused(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=4, departure_in=24)
        request = await requests.approved(offer, passenger)
        expect_error(await requests.approve(request, offer.driver), 409, "INVALID_STATE_TRANSITION")

    async def test_a_rejected_request_cannot_be_approved_later(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=4, departure_in=24)
        request = await requests.rejected(offer, passenger)
        expect_error(await requests.approve(request, offer.driver), 409, "INVALID_STATE_TRANSITION")


class TestApproveSeats:
    async def test_approving_takes_the_requested_seats(
        self, rides, requests, passenger, db
    ) -> None:
        """D1: approving deducts `seats_requested`, not always 1."""
        offer = await rides.offer(capacity=4)
        body = expect_status(
            await requests.approve(await requests.create(offer, passenger, 3), offer.driver), 200
        )

        assert body["ride"]["available_seats"] == 1
        assert body["ride"]["status"] == "upcoming"
        assert await approved_seats(db, offer.id) == 3
        await assert_seat_invariant(db, offer.id)

    async def test_the_last_seat_makes_the_ride_full(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2)
        body = expect_status(
            await requests.approve(await requests.create(offer, passenger, 2), offer.driver), 200
        )

        assert body["ride"]["available_seats"] == 0
        assert body["ride"]["status"] == "full"
        await assert_seat_invariant(db, offer.id)

    async def test_seats_add_up_across_passengers(self, rides, requests, users, db) -> None:
        offer = await rides.offer(capacity=5)
        await requests.approved(offer, await users.create(), seats=2)
        await requests.approved(offer, await users.create(), seats=1)

        assert (await rides.refresh(offer))["available_seats"] == 2
        assert await approved_seats(db, offer.id) == 3
        await assert_seat_invariant(db, offer.id)

    async def test_approving_more_seats_than_are_left(self, rides, requests, users, db) -> None:
        """The seat check is re-run at approval time (CONTRACT.md §4): the
        request was legal when it was made, and is not any more."""
        offer = await rides.offer(capacity=3)
        greedy = await requests.create(offer, await users.create(), seats=2)
        other = await requests.create(offer, await users.create(), seats=2)

        expect_status(await requests.approve(greedy, offer.driver), 200)
        expect_error(await requests.approve(other, offer.driver), 409, "NOT_ENOUGH_SEATS")

        assert (await requests.fetch(other, offer.driver))["status"] == "pending", (
            "a refused approval leaves the request pending, so the driver may retry"
        )
        await assert_seat_invariant(db, offer.id)

    async def test_approving_on_a_full_ride(self, rides, requests, users, db) -> None:
        """A pending request can outlive the seats. CONTRACT.md §4 spells the
        approve path out: check `available_seats ≥ seats_requested`, else 409
        NOT_ENOUGH_SEATS. (openapi's summary says "ride `upcoming`"; CONTRACT.md
        wins for behaviour, and the explicit seat check is what can fire here.)
        """
        offer = await rides.offer(capacity=2)
        waiting = await requests.create(offer, await users.create())
        await requests.approved(offer, await users.create(), seats=2)
        assert (await rides.refresh(offer))["status"] == "full"

        expect_error(await requests.approve(waiting, offer.driver), 409, "NOT_ENOUGH_SEATS")
        await assert_seat_invariant(db, offer.id)

    async def test_capacity_freed_by_an_edit_lets_the_approval_through(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=2)
        waiting = await requests.create(offer, await users.create())
        await requests.approved(offer, await users.create(), seats=2)

        expect_status(await rides.patch(offer, {"capacity": 4}), 200)
        expect_status(await requests.approve(waiting, offer.driver), 200)
        await assert_seat_invariant(db, offer.id)

    async def test_rejecting_does_not_touch_the_seats(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2)
        expect_status(
            await requests.reject(await requests.create(offer, passenger, 2), offer.driver), 200
        )

        assert (await rides.refresh(offer))["available_seats"] == 2
        assert await approved_seats(db, offer.id) == 0
        await assert_seat_invariant(db, offer.id)

    async def test_the_passenger_is_notified(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2)
        await requests.approved(offer, passenger)
        assert "request_approved" in await notification_types(db, passenger.id)

    async def test_a_rejected_passenger_is_notified(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2)
        await requests.rejected(offer, passenger)
        assert "request_rejected" in await notification_types(db, passenger.id)


class TestCancelReturnsSeats:
    async def test_cancelling_an_approved_request_frees_the_seats(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=24)
        request = await requests.approved(offer, passenger, seats=2)

        body = expect_status(await requests.cancel(request, passenger), 200)
        assert body["ride"]["available_seats"] == 3
        assert await approved_seats(db, offer.id) == 0
        await assert_seat_invariant(db, offer.id)

    async def test_a_full_ride_reopens(self, rides, requests, passenger, db) -> None:
        """CONTRACT.md §3: "Seats return to the ride (`full` → `upcoming`)"."""
        offer = await rides.offer(capacity=1, departure_in=24)
        request = await requests.approved(offer, passenger)
        assert (await rides.refresh(offer))["status"] == "full"

        body = expect_status(await requests.cancel(request, passenger), 200)
        assert body["ride"]["status"] == "upcoming"
        assert body["ride"]["available_seats"] == 1
        await assert_seat_invariant(db, offer.id)

    async def test_cancelling_a_pending_request_changes_no_seats(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger, seats=2)

        body = expect_status(await requests.cancel(request, passenger), 200)
        assert body["ride"]["available_seats"] == 2
        await assert_seat_invariant(db, offer.id)

    async def test_the_driver_is_notified(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.approved(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

        assert "request_cancelled" in await notification_types(db, offer.driver.id)

    async def test_the_driver_is_notified_about_a_pending_cancel_too(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

        assert "request_cancelled" in await notification_types(db, offer.driver.id)


class TestRideCancelReturnsEverySeat:
    """D19: "Every pending and approved request becomes `cancelled`, so
    `available_seats` goes back to `capacity`"."""

    async def test_available_seats_go_back_to_capacity(self, rides, requests, users, db) -> None:
        offer = await rides.offer(capacity=4, departure_in=24)
        await requests.approved(offer, await users.create(), seats=2)
        await requests.approved(offer, await users.create(), seats=1)
        assert (await rides.refresh(offer))["available_seats"] == 1

        body = expect_status(await rides.cancel(offer), 200)
        assert body["available_seats"] == 4
        assert await approved_seats(db, offer.id) == 0
        await assert_seat_invariant(db, offer.id)

    async def test_a_full_ride_releases_every_seat(self, rides, requests, users, db) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        await requests.approved(offer, await users.create(), seats=2)
        assert (await rides.refresh(offer))["status"] == "full"

        body = expect_status(await rides.cancel(offer), 200)
        assert (body["status"], body["available_seats"]) == ("cancelled", 2)
        await assert_seat_invariant(db, offer.id)


class TestCancelCutoff:
    """D15 / CONTRACT.md §3: an approved passenger may cancel until
    `departure_time - 1h`; after that it is 409 TOO_LATE_TO_CANCEL."""

    async def test_too_late_for_an_approved_seat(self, rides, requests, passenger, db) -> None:
        offer = await rides.offer(capacity=2, departure_in=TOO_LATE_HOURS)
        request = await requests.approved(offer, passenger)

        expect_error(await requests.cancel(request, passenger), 409, "TOO_LATE_TO_CANCEL")
        assert (await requests.fetch(request, passenger))["status"] == "approved"
        await assert_seat_invariant(db, offer.id)

    async def test_just_inside_the_cutoff(self, rides, requests, passenger) -> None:
        """D19 fixes the boundary itself: too late is `now > departure - 1h`, so
        exactly on the hour the seat may still be given back."""
        offer = await rides.offer(capacity=2, departure_in=1 + BOUNDARY_MARGIN_HOURS)
        request = await requests.approved(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

    async def test_just_outside_the_cutoff(self, rides, requests, passenger) -> None:
        offer = await rides.offer(capacity=2, departure_in=1 - BOUNDARY_MARGIN_HOURS)
        request = await requests.approved(offer, passenger)
        expect_error(await requests.cancel(request, passenger), 409, "TOO_LATE_TO_CANCEL")

    async def test_a_pending_request_has_no_cutoff(self, rides, requests, passenger) -> None:
        """ "pending → cancelled any time before the ride starts" - the 1h cutoff
        protects the driver from losing a seat late, and no seat is held yet."""
        offer = await rides.offer(capacity=2, departure_in=TOO_LATE_HOURS)
        request = await requests.create(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)

    async def test_the_cutoff_does_not_apply_to_a_ride_further_out(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.approved(offer, passenger)
        expect_status(await requests.cancel(request, passenger), 200)


class TestPermissions:
    @pytest.mark.parametrize("action", ["approve", "reject"])
    async def test_only_the_driver_responds(
        self, rides, requests, passenger, other_user, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)

        expect_error(await getattr(requests, action)(request, passenger), 403, "FORBIDDEN")
        expect_error(await getattr(requests, action)(request, other_user), 403, "FORBIDDEN")

    @pytest.mark.parametrize("action", ["approve", "reject"])
    async def test_another_driver_cannot_respond(
        self, rides, requests, passenger, users, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)
        intruder = await users.create_driver()

        expect_error(await getattr(requests, action)(request, intruder), 403, "FORBIDDEN")

    async def test_only_the_passenger_cancels(self, rides, requests, passenger, other_user) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)

        expect_error(await requests.cancel(request, offer.driver), 403, "FORBIDDEN")
        expect_error(await requests.cancel(request, other_user), 403, "FORBIDDEN")
        expect_status(await requests.cancel(request, passenger), 200)

    @pytest.mark.parametrize("action", ["approve", "reject", "cancel"])
    async def test_a_missing_request_is_404(self, client, user, action: str) -> None:
        response = await client.post(f"/requests/9999999/{action}", headers=user.headers)
        expect_error(response, 404, "NOT_FOUND")

    @pytest.mark.parametrize("action", ["approve", "reject", "cancel"])
    async def test_forbidden_beats_the_state_check(
        self, rides, requests, passenger, other_user, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.rejected(offer, passenger)
        expect_error(await getattr(requests, action)(request, other_user), 403, "FORBIDDEN")


class TestTheApproveRace:
    """CONTRACT.md §4: approve runs in one transaction with `SELECT … FOR UPDATE`
    on the ride. Two drivers' clicks on the last seat must not both win."""

    async def test_two_concurrent_approvals_of_the_last_seat(
        self, rides, requests, users, db, second_client
    ) -> None:
        offer = await rides.offer(capacity=1)
        first = await requests.create(offer, await users.create())
        second = await requests.create(offer, await users.create())

        headers = offer.driver.headers
        responses = await asyncio.wait_for(
            asyncio.gather(
                requests.client.post(f"/requests/{first['id']}/approve", headers=headers),
                second_client.post(f"/requests/{second['id']}/approve", headers=headers),
            ),
            timeout=30,
        )

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [200, 409], (
            "exactly one approval may win the last seat, got "
            f"{[(r.status_code, r.text[:200]) for r in responses]}"
        )

        winner = next(r for r in responses if r.status_code == 200)
        loser = next(r for r in responses if r.status_code == 409)
        expect_status(winner, 200)
        expect_error(loser, 409, "NOT_ENOUGH_SEATS")

        assert await approved_seats(db, offer.id) == 1
        await assert_seat_invariant(db, offer.id)
        assert (await rides.refresh(offer))["status"] == "full"

    async def test_concurrent_approvals_that_both_fit(
        self, rides, requests, users, db, second_client
    ) -> None:
        """The lock must not turn a legal pair of approvals into a conflict."""
        offer = await rides.offer(capacity=2)
        first = await requests.create(offer, await users.create())
        second = await requests.create(offer, await users.create())

        headers = offer.driver.headers
        responses = await asyncio.wait_for(
            asyncio.gather(
                requests.client.post(f"/requests/{first['id']}/approve", headers=headers),
                second_client.post(f"/requests/{second['id']}/approve", headers=headers),
            ),
            timeout=30,
        )

        assert [r.status_code for r in responses] == [200, 200], (
            f"both seats were free: {[(r.status_code, r.text[:200]) for r in responses]}"
        )
        assert await approved_seats(db, offer.id) == 2
        await assert_seat_invariant(db, offer.id)

    async def test_a_cancel_racing_an_approval_keeps_the_books(
        self, rides, requests, users, db, second_client
    ) -> None:
        offer = await rides.offer(capacity=1, departure_in=24)
        holder = await users.create()
        waiting_passenger = await users.create()
        # Both requests have to exist before the ride fills up: a full ride
        # stops accepting new ones (CONTRACT.md §4, RIDE_NOT_OPEN).
        held = await requests.create(offer, holder)
        waiting = await requests.create(offer, waiting_passenger)
        expect_status(await requests.approve(held, offer.driver), 200)

        await asyncio.wait_for(
            asyncio.gather(
                requests.client.post(f"/requests/{held['id']}/cancel", headers=holder.headers),
                second_client.post(
                    f"/requests/{waiting['id']}/approve", headers=offer.driver.headers
                ),
            ),
            timeout=30,
        )

        # Either order is legal; what may never happen is two seats sold on a
        # one-seat ride, or a seat lost for good.
        await assert_seat_invariant(db, offer.id)
        assert await approved_seats(db, offer.id) <= 1


class TestRideStateBlocksResponses:
    @pytest.mark.parametrize("action", ["approve", "reject"])
    async def test_after_the_ride_starts_the_request_is_already_rejected(
        self, rides, requests, passenger, action: str
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.create(offer, passenger)
        expect_status(await rides.start(offer), 200)

        expect_error(
            await getattr(requests, action)(request, offer.driver),
            409,
            "INVALID_STATE_TRANSITION",
        )

    async def test_after_the_ride_is_cancelled_the_request_is_already_cancelled(
        self, rides, requests, passenger
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        request = await requests.create(offer, passenger)
        expect_status(await rides.cancel(offer), 200)

        expect_error(await requests.cancel(request, passenger), 409, "INVALID_STATE_TRANSITION")
        expect_error(await requests.approve(request, offer.driver), 409, "INVALID_STATE_TRANSITION")

    async def test_an_approved_seat_on_a_started_ride_cannot_be_cancelled(
        self, rides, requests, passenger
    ) -> None:
        """The ride is rolling, yet the 1h clock has not run out: the departure
        is 1.5h away and the driver started early (allowed from -2h, D7).

        D19: cancelling needs the ride still `upcoming`/`full`, so this is
        INVALID_STATE_TRANSITION and not TOO_LATE_TO_CANCEL - "the cutoff only
        decides between a seat the passenger may still give back and one they
        may not".
        """
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)

        expect_error(await requests.cancel(request, passenger), 409, "INVALID_STATE_TRANSITION")
        assert (await requests.fetch(request, passenger))["status"] == "approved"

    async def test_a_pending_request_on_a_started_ride(self, rides, requests, passenger) -> None:
        """Starting auto-rejects it, so the state machine refuses the cancel on
        the *request's* status - either way it is INVALID_STATE_TRANSITION."""
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.create(offer, passenger)
        expect_status(await rides.start(offer), 200)

        expect_error(await requests.cancel(request, passenger), 409, "INVALID_STATE_TRANSITION")

    @pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
    async def test_approving_needs_an_open_ride(
        self, rides, requests, users, passenger, status: str
    ) -> None:
        """D19: approving needs the ride `upcoming`/`full`; in_progress or
        terminal is INVALID_STATE_TRANSITION."""
        offer = await rides.offer(capacity=2, departure_in=STARTABLE_HOURS)
        request = await requests.create(offer, passenger)
        if status == "in_progress":
            expect_status(await rides.start(offer), 200)
        elif status == "completed":
            expect_status(await rides.start(offer), 200)
            expect_status(await rides.complete(offer), 200)
        else:
            expect_status(await rides.cancel(offer), 200)

        expect_error(await requests.approve(request, offer.driver), 409, "INVALID_STATE_TRANSITION")


class TestIdempotenceOfRefusals:
    async def test_a_refused_approval_leaves_no_notification(
        self, rides, requests, users, db
    ) -> None:
        offer = await rides.offer(capacity=1)
        latecomer = await users.create()
        waiting = await requests.create(offer, latecomer)
        await requests.approved(offer, await users.create())

        expect_error(await requests.approve(waiting, offer.driver), 409, "NOT_ENOUGH_SEATS")
        assert "request_approved" not in await notification_types(db, latecomer.id), (
            "a failed approval must not notify the passenger"
        )

    async def test_a_refused_cancel_leaves_no_notification(
        self, rides, requests, passenger, db
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=TOO_LATE_HOURS)
        request = await requests.approved(offer, passenger)
        before = (await notification_types(db, offer.driver.id)).count("request_cancelled")

        expect_error(await requests.cancel(request, passenger), 409, "TOO_LATE_TO_CANCEL")
        after = (await notification_types(db, offer.driver.id)).count("request_cancelled")
        assert after == before
