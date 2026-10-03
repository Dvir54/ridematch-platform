"""Rating a completed ride's counterpart, and the lists that surface ratings.

POST /ratings, GET /ratings/pending, GET /users/{id}/ratings.

Contract: CONTRACT.md §4 "Ratings", D21 (pending-list window/order, the
rating_received notification), openapi `RatingCreate` / `Rating` /
`PendingRating`, error codes `NOT_A_PARTICIPANT` / `RIDE_NOT_COMPLETED` /
`ALREADY_RATED`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from support import clock
from support.assertions import expect_error, expect_status, expect_validation_error
from support.ratings import average_after
from support.rides import STARTABLE_HOURS, notification_types, ride_in_status


async def completed_ride(rides, requests, driver, passenger, *, capacity: int = 1):
    """A ride driven to `completed`, with `passenger` as its one approved rider."""
    offer = await rides.offer(driver, capacity=capacity, departure_in=STARTABLE_HOURS)
    await requests.approved(offer, passenger)
    await rides.start(offer)
    await rides.refresh(offer)
    await rides.complete(offer)
    await rides.refresh(offer)
    return offer


class TestCreate:
    async def test_the_driver_rates_a_passenger(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)

        body = await ratings.create(
            driver,
            ride_id=offer.id,
            to_user_id=passenger.id,
            score=5,
            tags=["on_time", "clean_car"],
        )

        assert body["ride_id"] == offer.id
        assert body["to_user_id"] == passenger.id
        assert body["from_user"]["id"] == driver.id
        assert body["role_rated"] == "passenger", "the ratee (passenger) was rated as a passenger"
        assert body["score"] == 5
        assert body["tags"] == ["on_time", "clean_car"]
        assert body["comment"] is None

    async def test_the_passenger_rates_the_driver(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)

        body = await ratings.create(passenger, ride_id=offer.id, to_user_id=driver.id, score=4)

        assert body["from_user"]["id"] == passenger.id
        assert body["to_user_id"] == driver.id
        assert body["role_rated"] == "driver"

    async def test_from_user_is_public_only(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        body = await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)
        for private in ("email", "phone", "date_of_birth", "is_admin", "preferences"):
            assert private not in body["from_user"], f"Rating.from_user leaks {private}"

    async def test_comment_is_stored(self, rides, requests, driver, passenger, ratings) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        body = await ratings.create(
            driver, ride_id=offer.id, to_user_id=passenger.id, comment="Great rider!"
        )
        assert body["comment"] == "Great rider!"

    async def test_both_directions_can_be_rated_on_the_same_ride(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)
        await ratings.create(passenger, ride_id=offer.id, to_user_id=driver.id)

    async def test_the_driver_rates_each_approved_passenger_separately(
        self, rides, requests, driver, users, ratings
    ) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        first = await users.create()
        second = await users.create()
        await requests.approved(offer, first, seats=1)
        await requests.approved(offer, second, seats=1)
        await rides.start(offer)
        await rides.complete(offer)

        await ratings.create(driver, ride_id=offer.id, to_user_id=first.id)
        await ratings.create(driver, ride_id=offer.id, to_user_id=second.id)

    async def test_a_missing_ride_is_404(self, user, ratings) -> None:
        response = await ratings.create_response(user, ride_id=9999999, to_user_id=user.id)
        expect_error(response, 404, "NOT_FOUND")

    async def test_a_missing_to_user_is_404(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_error(
            await ratings.create_response(driver, ride_id=offer.id, to_user_id=9999999),
            404,
            "NOT_FOUND",
        )


class TestCreateRefusals:
    @pytest.mark.parametrize("status", ["upcoming", "full", "in_progress", "cancelled"])
    async def test_only_a_completed_ride_can_be_rated(
        self, rides, requests, users, status: str, ratings
    ) -> None:
        offer = await ride_in_status(
            status, rides=rides, requests=requests, users=users, capacity=1
        )
        passenger = await users.create()
        expect_error(
            await ratings.create_response(offer.driver, ride_id=offer.id, to_user_id=passenger.id),
            409,
            "RIDE_NOT_COMPLETED",
        )

    async def test_duplicate_rating_in_the_same_direction(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)

        expect_error(
            await ratings.create_response(driver, ride_id=offer.id, to_user_id=passenger.id),
            409,
            "ALREADY_RATED",
        )

    async def test_a_stranger_is_not_a_participant(
        self, rides, requests, driver, passenger, other_user, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_error(
            await ratings.create_response(other_user, ride_id=offer.id, to_user_id=driver.id),
            403,
            "NOT_A_PARTICIPANT",
        )

    async def test_a_never_approved_requester_is_not_a_participant(
        self, rides, requests, driver, passenger, users, ratings
    ) -> None:
        """A pending/rejected request never rode: not a participant."""
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        rejected = await users.create()
        await requests.rejected(offer, rejected)
        await requests.approved(offer, passenger)
        await rides.start(offer)
        await rides.complete(offer)

        expect_error(
            await ratings.create_response(rejected, ride_id=offer.id, to_user_id=driver.id),
            403,
            "NOT_A_PARTICIPANT",
        )

    async def test_passenger_to_passenger_is_not_allowed(
        self, rides, requests, driver, users, ratings
    ) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        first = await users.create()
        second = await users.create()
        await requests.approved(offer, first, seats=1)
        await requests.approved(offer, second, seats=1)
        await rides.start(offer)
        await rides.complete(offer)

        expect_error(
            await ratings.create_response(first, ride_id=offer.id, to_user_id=second.id),
            403,
            "NOT_A_PARTICIPANT",
        )

    async def test_the_driver_cannot_rate_themselves(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_error(
            await ratings.create_response(driver, ride_id=offer.id, to_user_id=driver.id),
            403,
            "NOT_A_PARTICIPANT",
        )


class TestCreateValidation:
    @pytest.mark.parametrize("score", [0, 6, -1])
    async def test_score_outside_1_to_5(
        self, rides, requests, driver, passenger, ratings, score: int
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_validation_error(
            await ratings.create_response(
                driver, ride_id=offer.id, to_user_id=passenger.id, score=score
            ),
            field="score",
        )

    async def test_score_must_be_an_integer(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_validation_error(
            await ratings.create_response(
                driver, ride_id=offer.id, to_user_id=passenger.id, score=3.5
            ),
            field="score",
        )

    async def test_too_many_tags(self, rides, requests, driver, passenger, ratings) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_validation_error(
            await ratings.create_response(
                driver,
                ride_id=offer.id,
                to_user_id=passenger.id,
                tags=[f"tag{i}" for i in range(11)],
            ),
            field="tags",
        )

    async def test_duplicate_tags(self, rides, requests, driver, passenger, ratings) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_validation_error(
            await ratings.create_response(
                driver, ride_id=offer.id, to_user_id=passenger.id, tags=["on_time", "on_time"]
            ),
            field="tags",
        )

    async def test_comment_too_long(self, rides, requests, driver, passenger, ratings) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        expect_validation_error(
            await ratings.create_response(
                driver, ride_id=offer.id, to_user_id=passenger.id, comment="x" * 1001
            ),
            field="comment",
        )


class TestAverageMath:
    """CONTRACT.md §4: `new = (old * count + score) / (count + 1)`, per role."""

    async def test_first_rating_sets_the_average_to_the_score(
        self, rides, requests, driver, passenger, ratings, client
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id, score=4)

        profile = expect_status(await client.get("/users/me", headers=passenger.headers), 200)
        assert profile["passenger_rating"] == average_after(None, 0, 4) == 4.0
        assert profile["passenger_rating_count"] == 1
        assert profile["driver_rating"] is None, "only the passenger_rating cache moved"

    async def test_successive_ratings_average_exactly(
        self, rides, requests, driver, users, ratings, client
    ) -> None:
        scores = [5, 3, 4]
        expected_avg: float | None = None
        for index, score in enumerate(scores):
            passenger = await users.create()
            offer = await completed_ride(rides, requests, driver, passenger)
            await ratings.create(passenger, ride_id=offer.id, to_user_id=driver.id, score=score)
            expected_avg = average_after(expected_avg, index, score)

            profile = expect_status(await client.get("/users/me", headers=driver.headers), 200)
            assert profile["driver_rating_count"] == index + 1
            assert round(profile["driver_rating"], 1) == round(expected_avg, 1), (
                f"after rating #{index + 1}"
            )

    async def test_driver_and_passenger_caches_are_independent(
        self, rides, requests, driver, passenger, ratings, client
    ) -> None:
        """Rating the driver (role_rated=driver) must not move their own
        passenger_rating, and vice versa - the two caches track different
        roles the same person can play across rides."""
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(passenger, ride_id=offer.id, to_user_id=driver.id, score=5)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id, score=3)

        driver_profile = expect_status(await client.get("/users/me", headers=driver.headers), 200)
        assert driver_profile["driver_rating"] == 5.0
        assert driver_profile["passenger_rating"] is None

        passenger_profile = expect_status(
            await client.get("/users/me", headers=passenger.headers), 200
        )
        assert passenger_profile["passenger_rating"] == 3.0
        assert passenger_profile["driver_rating"] is None


class TestPending:
    async def test_a_completed_ride_owes_a_rating_each_way(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)

        driver_owes = await ratings.pending(driver)
        assert [
            (item["ride"]["id"], item["to_user"]["id"], item["role_rated"]) for item in driver_owes
        ] == [(offer.id, passenger.id, "passenger")]

        passenger_owes = await ratings.pending(passenger)
        assert [
            (item["ride"]["id"], item["to_user"]["id"], item["role_rated"])
            for item in passenger_owes
        ] == [(offer.id, driver.id, "driver")]

    async def test_disappears_once_rated(self, rides, requests, driver, passenger, ratings) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)
        assert await ratings.pending(driver) == []

    async def test_a_rejected_requester_owes_nothing(
        self, rides, requests, driver, passenger, users, ratings
    ) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        rejected = await users.create()
        await requests.rejected(offer, rejected)
        await requests.approved(offer, passenger)
        await rides.start(offer)
        await rides.complete(offer)

        assert await ratings.pending(rejected) == []

    async def test_empty_with_no_completed_rides(self, user, ratings) -> None:
        assert await ratings.pending(user) == []

    async def test_an_upcoming_ride_owes_nothing_yet(
        self, offer, requests, passenger, ratings
    ) -> None:
        await requests.approved(offer, passenger)
        assert await ratings.pending(offer.driver) == []
        assert await ratings.pending(passenger) == []


class TestListUserRatings:
    async def test_ratings_received_by_a_user(
        self, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        created = await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id, score=5)

        body = expect_status(await ratings.for_user(passenger.id, passenger), 200)
        assert [item["id"] for item in body] == [created["id"]]

    async def test_role_rated_filter(self, rides, requests, driver, users, ratings) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        passenger = await users.create()
        await requests.approved(offer, passenger)
        await rides.start(offer)
        await rides.complete(offer)
        await ratings.create(passenger, ride_id=offer.id, to_user_id=driver.id)

        other_offer = await rides.offer(
            await users.create_driver(), capacity=2, departure_in=STARTABLE_HOURS
        )
        await requests.approved(other_offer, driver)  # driver also rides as a passenger
        await rides.start(other_offer)
        await rides.complete(other_offer)
        await ratings.create(other_offer.driver, ride_id=other_offer.id, to_user_id=driver.id)

        as_driver = expect_status(
            await ratings.for_user(driver.id, driver, role_rated="driver"), 200
        )
        assert len(as_driver) == 1 and as_driver[0]["role_rated"] == "driver"

        as_passenger = expect_status(
            await ratings.for_user(driver.id, driver, role_rated="passenger"), 200
        )
        assert len(as_passenger) == 1 and as_passenger[0]["role_rated"] == "passenger"

    async def test_newest_first(self, rides, requests, driver, users, ratings) -> None:
        first_passenger = await users.create()
        first = await completed_ride(rides, requests, driver, first_passenger)
        first_rating = await ratings.create(first_passenger, ride_id=first.id, to_user_id=driver.id)

        second_passenger = await users.create()
        second = await completed_ride(rides, requests, driver, second_passenger)
        second_rating = await ratings.create(
            second_passenger, ride_id=second.id, to_user_id=driver.id
        )

        body = expect_status(await ratings.for_user(driver.id, driver), 200)
        assert [item["id"] for item in body] == [second_rating["id"], first_rating["id"]]

    async def test_a_missing_user_is_404(self, user, ratings) -> None:
        expect_error(await ratings.for_user(9999999, user), 404, "NOT_FOUND")

    async def test_empty_for_a_user_with_no_ratings(self, user, ratings) -> None:
        assert expect_status(await ratings.for_user(user.id, user), 200) == []


class TestRatingReceivedNotification:
    """CONTRACT.md §4 / D21: a rating writes `rating_received` for the ratee
    only, no email, `related_entity_type="ride"` since `rating` is not one of
    the two values the column allows."""

    async def test_the_ratee_is_notified_and_the_rater_is_not(
        self, rides, requests, driver, passenger, ratings, db, outbox
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        outbox.clear()  # drop the request_approved email from completed_ride's setup
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)

        assert "rating_received" in await notification_types(db, passenger.id)
        assert "rating_received" not in await notification_types(db, driver.id)
        assert not outbox, "CONTRACT.md §4: rating_received has no email column"

    async def test_related_entity_points_at_the_ride(
        self, rides, requests, driver, passenger, ratings, db
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)

        [row] = [
            r
            for r in await db.fetch(
                "SELECT * FROM notifications WHERE user_id = $1 AND type = 'rating_received'",
                passenger.id,
            )
        ]
        assert row["related_entity_type"] == "ride"
        assert row["related_entity_id"] == offer.id


class TestPendingWindowAndOrder:
    """D21: `/ratings/pending` lists only completed rides whose
    `departure_time` is within the last 30 days, ordered by `departure_time`
    descending then `to_user.id` ascending.

    Boundary tests sit a minute clear of the 30-day cutoff on each side, the
    same margin `support.rides.BOUNDARY_MARGIN_HOURS` uses for the 1h/2h
    cutoffs - the request and the query each take real wall-clock time, so a
    row backdated to *exactly* "30 days ago" may already read as 30 days and
    a few milliseconds by the time the server evaluates `now()`.
    """

    MARGIN_DAYS = 60 / 86400

    async def _backdate(self, db, ride_id: int, days_ago: float) -> None:
        await db.execute(
            "UPDATE rides SET departure_time = $2 WHERE id = $1",
            ride_id,
            clock.now() - timedelta(days=days_ago),
        )

    async def test_older_than_30_days_is_excluded(
        self, rides, requests, driver, passenger, ratings, db
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await self._backdate(db, offer.id, 30 + self.MARGIN_DAYS)

        assert await ratings.pending(driver) == []

    async def test_just_inside_30_days_is_included(
        self, rides, requests, driver, passenger, ratings, db
    ) -> None:
        offer = await completed_ride(rides, requests, driver, passenger)
        await self._backdate(db, offer.id, 30 - self.MARGIN_DAYS)

        body = await ratings.pending(driver)
        assert [item["ride"]["id"] for item in body] == [offer.id]

    async def test_newest_departure_first_then_to_user_id(
        self, rides, driver, requests, users, ratings, db
    ) -> None:
        older = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        first_passenger = await users.create()
        second_passenger = await users.create()
        await requests.approved(older, first_passenger)
        await requests.approved(older, second_passenger)
        await rides.start(older)
        await rides.complete(older)
        await self._backdate(db, older.id, 10)

        newer = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        newest_passenger = await users.create()
        await requests.approved(newer, newest_passenger)
        await rides.start(newer)
        await rides.complete(newer)
        await self._backdate(db, newer.id, 1)

        body = await ratings.pending(driver)
        ordered_counterparts = [item["to_user"]["id"] for item in body]
        first, second = sorted([first_passenger.id, second_passenger.id])
        assert ordered_counterparts == [newest_passenger.id, first, second]
