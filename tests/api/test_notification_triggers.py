"""Every row of the notification trigger table (CONTRACT.md §7), including the
email column. Who gets a *row* is already proven in test_onboarding.py,
test_requests.py, test_request_lifecycle.py and test_ride_lifecycle.py (PLAN
Phase 2/3: "write notification rows (no push yet)"); this file is what PLAN
Phase 4 adds on top - whether each one also went out through
`notifications_service.send_email`, read back from the memory outbox
(`EMAIL_BACKEND=memory`).

`ride_reminder` (the 1h-before job) and the admin-cancel column are out of
scope here: the reminder is a background job (see test_jobs.py) and
force-cancel is Phase 6 (test_ride_lifecycle.py's TestStateMachine docstring).
"""

from __future__ import annotations

from support.assertions import expect_status
from support.rides import STARTABLE_HOURS


class TestWelcomeEmails:
    async def test_onboarding_sends_a_welcome_email(self, users, outbox) -> None:
        user = await users.create()
        [message] = [m for m in outbox if m.to == user.email]
        assert message.subject
        assert user.name in message.body

    async def test_no_welcome_email_when_the_user_opted_out(self, users, outbox) -> None:
        user = await users.create(preferences={"notifications": {"email": False}})
        assert not [m for m in outbox if m.to == user.email]


class TestRequestCreatedHasNoEmail:
    async def test_the_driver_is_not_emailed(self, offer, requests, passenger, outbox) -> None:
        await requests.create(offer, passenger)
        assert not [m for m in outbox if m.to == offer.driver.email], (
            "CONTRACT.md §7: request_created has no email column"
        )


class TestRequestApprovedEmailsThePassenger:
    async def test_the_passenger_is_emailed(self, offer, requests, passenger, outbox) -> None:
        await requests.approved(offer, passenger)
        [message] = [m for m in outbox if m.to == passenger.email]
        assert message.subject
        assert not [m for m in outbox if m.to == offer.driver.email], (
            "CONTRACT.md §7: the driver has no email on this row"
        )

    async def test_no_email_when_the_passenger_opted_out(self, offer, requests, users, outbox) -> None:
        passenger = await users.create(preferences={"notifications": {"email": False}})
        await requests.approved(offer, passenger)
        assert not [m for m in outbox if m.to == passenger.email]


class TestRequestRejectedEmailsThePassenger:
    async def test_a_manual_rejection_emails_the_passenger(
        self, offer, requests, passenger, outbox
    ) -> None:
        await requests.rejected(offer, passenger)
        assert [m for m in outbox if m.to == passenger.email]

    async def test_auto_rejection_on_start_emails_the_passenger(
        self, rides, requests, users, outbox
    ) -> None:
        """CONTRACT.md §7: request_rejected ("incl. auto") still gets the email."""
        offer = await rides.offer(departure_in=STARTABLE_HOURS)
        passenger = await users.create()
        await requests.create(offer, passenger)
        expect_status(await rides.start(offer), 200)
        assert [m for m in outbox if m.to == passenger.email], (
            "an auto-rejected pending request is emailed like any other request_rejected"
        )


class TestRequestCancelledHasNoEmail:
    async def test_the_driver_is_not_emailed(self, offer, requests, passenger, outbox) -> None:
        await requests.cancelled(offer, passenger)
        assert not [m for m in outbox if m.to == offer.driver.email], (
            "CONTRACT.md §7: request_cancelled has no email column"
        )


class TestRideCancelledHasNoEmail:
    async def test_notified_passengers_are_not_emailed(
        self, rides, requests, users, outbox
    ) -> None:
        offer = await rides.offer(capacity=2, departure_in=24)
        passenger = await users.create()
        await requests.approved(offer, passenger)

        outbox.clear()  # drop the request_approved email from setup
        expect_status(await rides.cancel(offer), 200)

        assert not [m for m in outbox if m.to == passenger.email], (
            "CONTRACT.md §7: ride_cancelled has no email column"
        )


class TestRideStartedHasNoEmail:
    async def test_approved_passengers_are_not_emailed(
        self, rides, requests, users, outbox
    ) -> None:
        offer = await rides.offer(departure_in=STARTABLE_HOURS)
        passenger = await users.create()
        await requests.approved(offer, passenger)

        outbox.clear()  # drop the request_approved email from setup
        expect_status(await rides.start(offer), 200)

        assert not [m for m in outbox if m.to == passenger.email], (
            "CONTRACT.md §7: ride_started has no email column"
        )


class TestRideCompletedHasNoEmail:
    async def test_driver_and_passengers_are_not_emailed(
        self, rides, requests, users, outbox
    ) -> None:
        offer = await rides.offer(departure_in=STARTABLE_HOURS)
        passenger = await users.create()
        await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)

        outbox.clear()  # drop the request_approved email from setup
        expect_status(await rides.complete(offer), 200)

        assert not [m for m in outbox if m.to == passenger.email]
        assert not [m for m in outbox if m.to == offer.driver.email]
