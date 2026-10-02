"""Search & matching — CONTRACT.md §7 "Matching formula", literally.

The candidate filters SQL can express run in SQL; the two distance limits run in Python, because
`haversine` is not an index-friendly expression. The status and time filters already cut the set
down to a few hours of `upcoming` rides (`rides_status_dep_idx`), so few rows reach Python.
Scoring, the `MATCH_MIN_SCORE` cut and the sort all come after that, which is why `limit`/`offset`
are applied last rather than in the query.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.requests.models import RideRequest
from app.modules.rides.models import Ride
from app.modules.rides.service import ACTIVE_REQUEST_STATUSES
from app.modules.search.schemas import ScoreBreakdown, SortOrder
from app.modules.users.models import User
from app.modules.users.schemas import UserPreferences

#: CONTRACT.md §7: "Earth radius = 6371 km".
EARTH_RADIUS_KM = 6371.0
#: The candidate window: `|departure_time - time| <= 4h`.
MAX_TIME_DELTA = timedelta(hours=4)
#: The two edges of the time component.
TIME_FULL_DELTA_HOURS = 2.0
TIME_ZERO_DELTA_HOURS = 4.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km on a sphere of radius `EARTH_RADIUS_KM`."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ── the formula (CONTRACT.md §7) ─────────────────────────────────────


def route_score(pickup_km: float, dropoff_km: float, radius_km: float) -> float:
    """`20·max(0, 1 - p/R) + 20·max(0, 1 - d/R)`, max 40."""
    return 20 * max(0.0, 1 - pickup_km / radius_km) + 20 * max(0.0, 1 - dropoff_km / radius_km)


def time_score(delta_hours: float) -> float:
    """`Δ ≤ 2` → 25; `2 < Δ ≤ 4` → `25·(4 - Δ)/2`; else 0."""
    if delta_hours <= TIME_FULL_DELTA_HOURS:
        return 25.0
    if delta_hours <= TIME_ZERO_DELTA_HOURS:
        return 25 * (TIME_ZERO_DELTA_HOURS - delta_hours) / 2
    return 0.0


def price_score(price: Decimal, budget: Decimal | None) -> float:
    """No budget or within budget → 15; over → `15·max(0, 1 - (price - budget)/budget)`.

    A budget of 0 scores 0 for anything above it — §7's "(budget 0 → 0)", and the only reading
    that doesn't divide by zero.
    """
    if budget is None or price <= budget:
        return 15.0
    if budget == 0:
        return 0.0
    return 15 * max(0.0, 1 - float((price - budget) / budget))


def rating_score(rating: float | None) -> float:
    """No rating → 5; `≥ 4.5` → 10; else `10·(rating - 1)/3.5`."""
    if rating is None:
        return 5.0
    if rating >= 4.5:
        return 10.0
    return 10 * (rating - 1) / 3.5


def preferences_score(ride_preferences: dict | None, *, smoking: bool, pets: bool) -> float:
    """10, less 5 for each of smoking/pets the ride allows and the passenger doesn't want."""
    allowed = ride_preferences or {}
    score = 10.0
    if allowed.get("smoking") and not smoking:
        score -= 5
    if allowed.get("pets") and not pets:
        score -= 5
    return max(0.0, score)


# ── the search ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """One passenger's search: the route and time asked for, plus their own preferences."""

    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    time: datetime
    budget: Decimal | None
    seats: int
    sort: SortOrder
    smoking: bool
    pets: bool


def query_for(
    user: User,
    *,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    time: datetime,
    budget: Decimal | None,
    seats: int,
    sort: SortOrder,
) -> SearchQuery:
    """Passenger preferences come from the caller's saved profile, not from the query string."""
    preferences = UserPreferences.model_validate(user.preferences or {})
    return SearchQuery(
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        time=time,
        budget=budget,
        seats=seats,
        sort=sort,
        smoking=preferences.smoking,
        pets=preferences.pets,
    )


@dataclass(frozen=True, slots=True)
class RideMatch:
    """A scored candidate, ready to serialize once the caller's `RideViewer` is known."""

    ride: Ride
    match_score: float
    breakdown: ScoreBreakdown
    pickup_distance_km: float
    dropoff_distance_km: float


#: `sort` → the key it sorts by (CONTRACT.md §7). The ride id is the last tiebreak everywhere, so
#: that equally ranked rides keep one stable order across pages.
SORT_KEYS: dict[SortOrder, Callable[[RideMatch], tuple]] = {
    "best_match": lambda m: (-m.match_score, m.ride.departure_time, m.ride.id),
    "earliest": lambda m: (m.ride.departure_time, m.ride.id),
    "cheapest": lambda m: (m.ride.price_per_seat, -m.match_score, m.ride.id),
}


async def candidate_rides(
    db: AsyncSession, *, user: User, query: SearchQuery, now: datetime
) -> Sequence[Ride]:
    """Everything in §7's "Candidates" except the two distance limits."""
    # `preferences->'gender_only'`, with a missing key or a null column reading as false.
    gender_only = func.coalesce(Ride.preferences["gender_only"].as_boolean(), false())
    # D4: a gender_only ride is for passengers whose gender equals the driver's. An unset gender
    # can never equal it, so such a caller sees no gender_only ride at all.
    gender_ok = (
        ~gender_only
        if user.gender is None
        else or_(~gender_only, Ride.driver.has(User.gender == user.gender))
    )
    # A `rejected` request is deliberately not a blocker: the ride stays a candidate and is
    # reported with `my_request.status = "rejected"` (CONTRACT.md D20).
    already_requested = exists().where(
        RideRequest.ride_id == Ride.id,
        RideRequest.passenger_id == user.id,
        RideRequest.status.in_(ACTIVE_REQUEST_STATUSES),
    )
    stmt = select(Ride).where(
        Ride.status == "upcoming",
        Ride.available_seats >= query.seats,
        Ride.departure_time > now,
        Ride.departure_time >= query.time - MAX_TIME_DELTA,
        Ride.departure_time <= query.time + MAX_TIME_DELTA,
        Ride.driver_id != user.id,
        ~already_requested,
        gender_ok,
    )
    return list((await db.execute(stmt)).scalars().all())


def score_ride(ride: Ride, query: SearchQuery, *, radius_km: float) -> RideMatch:
    """Score one candidate. `match_score` is the sum of the components, rounded to 1 decimal."""
    pickup_km = haversine_km(query.start_lat, query.start_lng, ride.start_lat, ride.start_lng)
    dropoff_km = haversine_km(query.end_lat, query.end_lng, ride.end_lat, ride.end_lng)
    delta_hours = abs((ride.departure_time - query.time).total_seconds()) / 3600
    breakdown = ScoreBreakdown(
        route=route_score(pickup_km, dropoff_km, radius_km),
        time=time_score(delta_hours),
        price=price_score(ride.price_per_seat, query.budget),
        # The driver is driving, so it is their driver rating that counts.
        rating=rating_score(ride.driver.driver_rating),
        preferences=preferences_score(ride.preferences, smoking=query.smoking, pets=query.pets),
    )
    total = (
        breakdown.route
        + breakdown.time
        + breakdown.price
        + breakdown.rating
        + breakdown.preferences
    )
    return RideMatch(
        ride=ride,
        match_score=round(total, 1),
        breakdown=breakdown,
        pickup_distance_km=pickup_km,
        dropoff_distance_km=dropoff_km,
    )


async def search_rides(
    db: AsyncSession,
    settings: Settings,
    *,
    user: User,
    query: SearchQuery,
    limit: int,
    offset: int,
    now: datetime,
) -> list[RideMatch]:
    """Candidates → scores → the radius limits → the `MATCH_MIN_SCORE` cut → sort → one page."""
    radius_km = settings.search_radius_km
    matches: list[RideMatch] = []
    for ride in await candidate_rides(db, user=user, query=query, now=now):
        match = score_ride(ride, query, radius_km=radius_km)
        if match.pickup_distance_km > radius_km or match.dropoff_distance_km > radius_km:
            continue
        if match.match_score < settings.match_min_score:
            continue
        matches.append(match)
    matches.sort(key=SORT_KEYS[query.sort])
    return matches[offset : offset + limit]
