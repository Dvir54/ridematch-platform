"""Background jobs (CONTRACT.md §3 "Auto-complete"/"Stale rides", §7 "1h before
departure"). `JOBS_ENABLED=false` in tests (support/env.py), so no loop runs on
its own; these call `app.jobs.run_x(db, settings, now)` directly with an
injected `now`, exactly like `app.jobs.jobs_loop` does - so no sleeps and no
dependency on wall-clock time.
"""

from __future__ import annotations

from datetime import timedelta

from support import clock
from support.assertions import expect_status
from support.rides import STARTABLE_HOURS, notification_types, request_statuses


async def _run(app, name: str, *, now) -> int:
    from app import jobs

    func = {
        "reminders": jobs.run_reminders,
        "auto_complete": jobs.run_auto_complete,
        "stale_cancel": jobs.run_stale_cancel,
    }[name]
    async with app.state.sessionmaker() as session:
        return await func(session, app.state.settings, now)


class TestReminders:
    async def test_reminds_the_driver_and_approved_passengers_only(
        self, rides, requests, users, db, backend_app
    ) -> None:
        offer = await rides.offer(departure_in=1.0)
        approved_passenger = await users.create()
        pending_passenger = await users.create()
        await requests.approved(offer, approved_passenger)
        await requests.create(offer, pending_passenger)
        departure = clock.parse(offer.ride["departure_time"])

        count = await _run(backend_app, "reminders", now=departure - timedelta(minutes=55))

        assert count == 1
        assert "ride_reminder" in await notification_types(db, offer.driver.id)
        assert "ride_reminder" in await notification_types(db, approved_passenger.id)
        assert "ride_reminder" not in await notification_types(db, pending_passenger.id)

    async def test_is_idempotent_for_the_same_ride(self, rides, db, backend_app) -> None:
        offer = await rides.offer(departure_in=1.0)
        departure = clock.parse(offer.ride["departure_time"])
        now = departure - timedelta(minutes=30)

        first = await _run(backend_app, "reminders", now=now)
        second = await _run(backend_app, "reminders", now=now)

        assert (first, second) == (1, 0)
        assert (await notification_types(db, offer.driver.id)).count("ride_reminder") == 1

    async def test_more_than_an_hour_out_is_not_due_yet(self, rides, backend_app) -> None:
        offer = await rides.offer(departure_in=1.0)
        departure = clock.parse(offer.ride["departure_time"])
        assert await _run(backend_app, "reminders", now=departure - timedelta(minutes=90)) == 0

    async def test_a_departed_ride_is_not_reminded(self, rides, backend_app) -> None:
        offer = await rides.offer(departure_in=1.0)
        departure = clock.parse(offer.ride["departure_time"])
        assert await _run(backend_app, "reminders", now=departure + timedelta(minutes=1)) == 0


class TestAutoComplete:
    async def test_completes_an_in_progress_ride_after_the_cutoff(
        self, rides, requests, users, db, backend_app
    ) -> None:
        offer = await rides.offer(departure_in=STARTABLE_HOURS)
        passenger = await users.create()
        await requests.approved(offer, passenger)
        expect_status(await rides.start(offer), 200)
        departure = clock.parse(offer.ride["departure_time"])

        count = await _run(backend_app, "auto_complete", now=departure + timedelta(hours=13))

        assert count == 1
        await rides.refresh(offer)
        assert offer.status == "completed"
        assert "ride_completed" in await notification_types(db, offer.driver.id)
        assert "ride_completed" in await notification_types(db, passenger.id)

    async def test_not_yet_due_is_untouched(self, rides, backend_app) -> None:
        offer = await rides.offer(departure_in=STARTABLE_HOURS)
        expect_status(await rides.start(offer), 200)
        departure = clock.parse(offer.ride["departure_time"])
        assert await _run(backend_app, "auto_complete", now=departure + timedelta(hours=11)) == 0

    async def test_an_upcoming_ride_is_not_touched(self, rides, backend_app) -> None:
        """Only `in_progress` rides are completed; an upcoming one is `run_stale_cancel`'s job."""
        offer = await rides.offer(departure_in=1.0)
        departure = clock.parse(offer.ride["departure_time"])
        assert await _run(backend_app, "auto_complete", now=departure + timedelta(hours=13)) == 0


class TestStaleCancel:
    async def test_cancels_a_stale_ride_and_resolves_its_requests(
        self, rides, requests, users, db, backend_app
    ) -> None:
        offer = await rides.offer(capacity=3, departure_in=1.0)
        approved_passenger = await users.create()
        pending_passenger = await users.create()
        await requests.approved(offer, approved_passenger)
        await requests.create(offer, pending_passenger)
        departure = clock.parse(offer.ride["departure_time"])

        count = await _run(backend_app, "stale_cancel", now=departure + timedelta(hours=13))

        assert count == 1
        await rides.refresh(offer)
        assert offer.status == "cancelled"
        assert offer.available_seats == offer.ride["capacity"], (
            "CONTRACT.md §4: available_seats returns to capacity when a ride is cancelled"
        )
        statuses = await request_statuses(db, offer.id)
        assert set(statuses.values()) == {"cancelled", "rejected"}, (
            "CONTRACT.md §3: approved -> cancelled, pending -> rejected on a stale ride"
        )

        for passenger_id in (approved_passenger.id, pending_passenger.id):
            assert "ride_cancelled" in await notification_types(db, passenger_id), (
                "CONTRACT.md §7: ride_cancelled reaches pending and approved passengers alike"
            )
        assert "request_rejected" in await notification_types(db, pending_passenger.id)
        assert "request_rejected" not in await notification_types(db, approved_passenger.id)

    async def test_the_auto_rejection_is_emailed(
        self, rides, requests, users, outbox, backend_app
    ) -> None:
        offer = await rides.offer(departure_in=1.0)
        passenger = await users.create()
        await requests.create(offer, passenger)
        departure = clock.parse(offer.ride["departure_time"])
        outbox.clear()  # drop the welcome email from users.create()

        await _run(backend_app, "stale_cancel", now=departure + timedelta(hours=13))

        assert [m for m in outbox if m.to == passenger.email], (
            "CONTRACT.md §7: request_rejected (incl. auto) is always emailed"
        )

    async def test_not_yet_stale_is_untouched(self, rides, backend_app) -> None:
        offer = await rides.offer(departure_in=1.0)
        departure = clock.parse(offer.ride["departure_time"])
        assert await _run(backend_app, "stale_cancel", now=departure + timedelta(hours=11)) == 0


class TestJobsLock:
    """A deploy briefly runs two processes; the advisory lock lets one run each pass."""

    async def test_a_pass_is_skipped_while_another_process_holds_the_lock(
        self, rides, db, backend_app
    ) -> None:
        from app import jobs

        offer = await rides.offer(departure_in=1.0)
        now = clock.parse(offer.ride["departure_time"]) - timedelta(minutes=30)
        state = backend_app.state

        pool = await db._get_pool()
        async with pool.acquire() as other_process:
            await other_process.execute("SELECT pg_advisory_lock($1)", jobs.JOBS_LOCK_KEY)
            try:
                ran = await jobs.run_exclusive(
                    state.engine, state.sessionmaker, state.settings, now
                )
            finally:
                await other_process.execute("SELECT pg_advisory_unlock($1)", jobs.JOBS_LOCK_KEY)

        assert ran is False
        assert "ride_reminder" not in await notification_types(db, offer.driver.id)

    async def test_concurrent_passes_write_one_set_of_reminders(
        self, rides, db, backend_app
    ) -> None:
        import asyncio

        from app import jobs

        offer = await rides.offer(departure_in=1.0)
        now = clock.parse(offer.ride["departure_time"]) - timedelta(minutes=30)
        state = backend_app.state

        results = await asyncio.gather(
            *(
                jobs.run_exclusive(state.engine, state.sessionmaker, state.settings, now)
                for _ in range(2)
            )
        )

        assert True in results
        assert (await notification_types(db, offer.driver.id)).count("ride_reminder") == 1
        # Released afterwards, so the next pass can run.
        assert await jobs.run_exclusive(state.engine, state.sessionmaker, state.settings, now)
