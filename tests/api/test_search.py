"""GET /search - the matching formula (CONTRACT.md §7, PLAN Phase 3).

Each score component is checked in isolation by holding every other input at
a known, fixed value and varying only the one under test, then comparing the
backend's `match_score` against the formula computed by hand below. Exclusion
tests check candidates that the summary says must never be scored at all.
"""

from __future__ import annotations

import pytest

from support import clock
from support.assertions import expect_status
from support.env import MATCH_MIN_SCORE, SEARCH_RADIUS_KM
from support.geo import north
from support.search import PASSENGER_END, PASSENGER_START, DEFAULT_SEARCH_DEPARTURE_HOURS

R = SEARCH_RADIUS_KM
DEFAULT_PRICE = "20.00"
RADIUS_MARGIN_KM = 0.05  # like BOUNDARY_MARGIN_HOURS in support.rides: safely off the knife-edge


# ── hand-computed formula (CONTRACT.md §7) ──────────────────────────────────
def route_score(p: float, d: float) -> float:
    return 20 * max(0.0, 1 - p / R) + 20 * max(0.0, 1 - d / R)


def time_score(delta_hours: float) -> float:
    if delta_hours <= 2:
        return 25.0
    if delta_hours <= 4:
        return 25 * (4 - delta_hours) / 2
    return 0.0


def price_score(price: float, budget: float | None) -> float:
    if budget is None or price <= budget:
        return 15.0
    if budget == 0:
        return 0.0
    return 15 * max(0.0, 1 - (price - budget) / budget)


def rating_score(rating: float | None) -> float:
    if rating is None:
        return 5.0
    if rating >= 4.5:
        return 10.0
    return 10 * (rating - 1) / 3.5


def preferences_score(
    *, ride_smoking: bool, ride_pets: bool, passenger_smoking: bool, passenger_pets: bool
) -> float:
    score = 10.0
    if ride_smoking and not passenger_smoking:
        score -= 5
    if ride_pets and not passenger_pets:
        score -= 5
    return max(0.0, score)


def expected_total(
    *,
    p: float = 0.0,
    d: float = 0.0,
    delta_hours: float = 0.0,
    price: float = 20.0,
    budget: float | None = None,
    rating: float | None = None,
    ride_smoking: bool = False,
    ride_pets: bool = False,
    passenger_smoking: bool = False,
    passenger_pets: bool = False,
) -> float:
    return (
        route_score(p, d)
        + time_score(delta_hours)
        + price_score(price, budget)
        + rating_score(rating)
        + preferences_score(
            ride_smoking=ride_smoking,
            ride_pets=ride_pets,
            passenger_smoking=passenger_smoking,
            passenger_pets=passenger_pets,
        )
    )


# ── fixtures ─────────────────────────────────────────────────────────────
async def make_offer(
    rides,
    driver=None,
    *,
    p: float = 0.0,
    d: float = 0.0,
    delta_hours: float = 0.0,
    price: str = DEFAULT_PRICE,
    capacity: int = 3,
    ride_smoking: bool = False,
    ride_pets: bool = False,
    gender_only: bool = False,
):
    """A ride placed `p`/`d` km from the passenger anchors, `delta_hours` away
    from the default search time (support.search.DEFAULT_SEARCH_DEPARTURE_HOURS)."""
    start_lat, start_lng = north(PASSENGER_START, p)
    end_lat, end_lng = north(PASSENGER_END, d)
    return await rides.offer(
        driver,
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        departure_time=clock.iso_in_hours(DEFAULT_SEARCH_DEPARTURE_HOURS + delta_hours),
        price_per_seat=price,
        capacity=capacity,
        preferences={"smoking": ride_smoking, "pets": ride_pets, "gender_only": gender_only},
    )


def result_for(results, ride_id: int):
    return next((r for r in results if r["ride"]["id"] == ride_id), None)


# ── exact component scores ──────────────────────────────────────────────
class TestScoreComponents:
    async def test_baseline_all_components_at_their_default_max(
        self, rides, users, search
    ) -> None:
        """p=0, d=0, Δ=0, no budget, no rating on file, no restrictive prefs."""
        passenger = await users.create()
        offer = await make_offer(rides)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total()
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["route"] == pytest.approx(40.0, abs=0.05)
        assert match["breakdown"]["time"] == pytest.approx(25.0, abs=0.05)
        assert match["breakdown"]["price"] == pytest.approx(15.0, abs=0.05)
        assert match["breakdown"]["rating"] == pytest.approx(5.0, abs=0.05)
        assert match["breakdown"]["preferences"] == pytest.approx(10.0, abs=0.05)
        assert match["pickup_distance_km"] == pytest.approx(0.0, abs=0.05)
        assert match["dropoff_distance_km"] == pytest.approx(0.0, abs=0.05)

    @pytest.mark.parametrize(
        "p, d",
        [
            (R / 2, 0.0),
            (R / 2, R / 2),
        ],
    )
    async def test_route_component(self, rides, users, search, p, d) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, p=p, d=d)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(p=p, d=d)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["route"] == pytest.approx(route_score(p, d), abs=0.05)

    @pytest.mark.parametrize("delta_hours", [2.0, 3.0, 4.0])
    async def test_time_component_boundaries(self, rides, users, search, delta_hours) -> None:
        """CONTRACT.md §7: Δ≤2 -> 25, 2<Δ≤4 -> 25·(4-Δ)/2, else 0."""
        passenger = await users.create()
        offer = await make_offer(rides, delta_hours=delta_hours)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(delta_hours=delta_hours)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["time"] == pytest.approx(time_score(delta_hours), abs=0.05)

    async def test_time_component_beyond_four_hours_is_excluded(self, rides, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, delta_hours=4.5)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None

    async def test_price_component_within_budget(self, rides, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, price="20.00")
        results = expect_status(await search.response(passenger, budget="25.00"), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(price=20.0, budget=25.0)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["price"] == pytest.approx(15.0, abs=0.05)

    async def test_price_component_over_budget(self, rides, users, search) -> None:
        """price=20, budget=15 -> 15·(1 - (20-15)/15) = 10.0 exactly."""
        passenger = await users.create()
        offer = await make_offer(rides, price="20.00")
        results = expect_status(await search.response(passenger, budget="15.00"), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(price=20.0, budget=15.0)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["price"] == pytest.approx(10.0, abs=0.05)

    async def test_price_component_budget_zero(self, rides, users, search) -> None:
        """CONTRACT.md §7: budget 0 -> 0 (avoids dividing by zero)."""
        passenger = await users.create()
        offer = await make_offer(rides, price="20.00")
        results = expect_status(await search.response(passenger, budget="0"), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(price=20.0, budget=0.0)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["price"] == pytest.approx(0.0, abs=0.05)

    async def test_rating_component_no_rating_on_file(self, rides, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        assert match["breakdown"]["rating"] == pytest.approx(5.0, abs=0.05)

    @pytest.mark.parametrize("rating", [4.5, 1.0, 2.5])
    async def test_rating_component_values(self, rides, users, db, search, rating) -> None:
        passenger = await users.create()
        offer = await make_offer(rides)
        await db.set_driver_rating(offer.driver.id, rating)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(rating=rating)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["rating"] == pytest.approx(rating_score(rating), abs=0.05)

    async def test_preferences_component_smoking_penalty(self, rides, users, search) -> None:
        passenger = await users.create(preferences={"smoking": False})
        offer = await make_offer(rides, ride_smoking=True)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(ride_smoking=True, passenger_smoking=False)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["preferences"] == pytest.approx(5.0, abs=0.05)

    async def test_preferences_component_pets_penalty(self, rides, users, search) -> None:
        passenger = await users.create(preferences={"pets": False})
        offer = await make_offer(rides, ride_pets=True)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(ride_pets=True, passenger_pets=False)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["preferences"] == pytest.approx(5.0, abs=0.05)

    async def test_preferences_component_floors_at_zero(self, rides, users, search) -> None:
        passenger = await users.create(preferences={"smoking": False, "pets": False})
        offer = await make_offer(rides, ride_smoking=True, ride_pets=True)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(ride_smoking=True, ride_pets=True)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["preferences"] == pytest.approx(0.0, abs=0.05)

    async def test_preferences_component_no_penalty_when_passenger_tolerates(
        self, rides, users, search
    ) -> None:
        passenger = await users.create(preferences={"smoking": True})
        offer = await make_offer(rides, ride_smoking=True)
        results = expect_status(await search.response(passenger), 200)
        match = result_for(results, offer.id)
        assert match is not None
        expected = expected_total(ride_smoking=True, passenger_smoking=True)
        assert match["match_score"] == round(expected, 1)
        assert match["breakdown"]["preferences"] == pytest.approx(10.0, abs=0.05)


# ── radius boundary ──────────────────────────────────────────────────────
class TestRadiusBoundary:
    async def test_just_inside_radius_is_included(self, rides, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, p=R - RADIUS_MARGIN_KM)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is not None

    async def test_just_outside_radius_is_excluded(self, rides, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, p=R + RADIUS_MARGIN_KM)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None


# ── exclusions ───────────────────────────────────────────────────────────
class TestExclusions:
    async def test_excludes_own_ride(self, rides, users, search) -> None:
        driver = await users.create_driver()
        offer = await make_offer(rides, driver)
        results = expect_status(await search.response(driver), 200)
        assert result_for(results, offer.id) is None

    async def test_excludes_ride_with_a_pending_request(self, rides, requests, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides)
        await requests.create(offer, passenger)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None

    async def test_excludes_ride_with_an_approved_request(
        self, rides, requests, users, search
    ) -> None:
        passenger = await users.create()
        offer = await make_offer(rides)
        await requests.approved(offer, passenger)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None

    async def test_excludes_gender_only_ride_when_caller_gender_unset(
        self, rides, users, search
    ) -> None:
        driver = await users.create_driver(gender="male")
        passenger = await users.create()  # no gender set
        offer = await make_offer(rides, driver, gender_only=True)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None

    async def test_excludes_gender_only_ride_when_gender_differs(self, rides, users, search) -> None:
        driver = await users.create_driver(gender="male")
        passenger = await users.create(gender="female")
        offer = await make_offer(rides, driver, gender_only=True)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None

    async def test_includes_gender_only_ride_when_gender_matches(self, rides, users, search) -> None:
        driver = await users.create_driver(gender="male")
        passenger = await users.create(gender="male")
        offer = await make_offer(rides, driver, gender_only=True)
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is not None

    async def test_excludes_full_ride(self, rides, requests, users, search) -> None:
        passenger = await users.create()
        offer = await make_offer(rides, capacity=1)
        await requests.approved(offer, await users.create())
        await rides.refresh(offer)
        assert offer.status == "full"
        results = expect_status(await search.response(passenger), 200)
        assert result_for(results, offer.id) is None


# ── sort orders ──────────────────────────────────────────────────────────
class TestSortOrders:
    async def test_best_match_sorts_by_score_desc_then_departure_asc(
        self, rides, users, search
    ) -> None:
        passenger = await users.create()
        # Same score (p=0, Δ=2h both), tie broken by earlier departure.
        earlier = await make_offer(rides, delta_hours=-2.0)
        later = await make_offer(rides, delta_hours=2.0)
        # Clearly lower score via distance.
        farther = await make_offer(rides, p=9.0)

        results = expect_status(await search.response(passenger, sort="best_match"), 200)
        ids = [r["ride"]["id"] for r in results]
        assert ids.index(earlier.id) < ids.index(later.id) < ids.index(farther.id)

    async def test_earliest_sorts_by_departure_asc(self, rides, users, search) -> None:
        passenger = await users.create()
        first = await make_offer(rides, delta_hours=-2.0, p=9.0)  # lowest score, earliest
        second = await make_offer(rides, delta_hours=0.0)
        third = await make_offer(rides, delta_hours=2.0)

        results = expect_status(await search.response(passenger, sort="earliest"), 200)
        ids = [r["ride"]["id"] for r in results]
        assert ids.index(first.id) < ids.index(second.id) < ids.index(third.id)

    async def test_cheapest_sorts_by_price_asc_then_score_desc(self, rides, users, search) -> None:
        passenger = await users.create()
        cheap_best = await make_offer(rides, price="10.00", p=0.0)
        cheap_worse = await make_offer(rides, price="10.00", p=9.0)
        expensive = await make_offer(rides, price="30.00", p=0.0)

        results = expect_status(await search.response(passenger, sort="cheapest"), 200)
        ids = [r["ride"]["id"] for r in results]
        assert ids.index(cheap_best.id) < ids.index(cheap_worse.id) < ids.index(expensive.id)
