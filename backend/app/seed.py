"""Demo data: `cd backend && uv run python -m app.seed [--reset]`.

Seeds the database named by `DATABASE_URL`. The users carry fake Clerk ids (`seed_*`), so nobody
can sign in as them; they exist to populate search, the ride pages and the ratings. Re-running
without `--reset` does nothing; `--reset` deletes the seed users and everything tied to them first.
"""

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, or_, select

from app.clock import utc_now
from app.config import get_settings
from app.db import create_engine, create_sessionmaker
from app.models import Notification, Rating, Ride, RideRequest, User

SEED_PREFIX = "seed_"

# name, gender, (make, model, color, plate), smoking, pets
DRIVERS = [
    ("Noa Levi", "female", ("Toyota", "Corolla", "white", "12-345-67"), False, True),
    ("Amir Cohen", "male", ("Hyundai", "i30", "grey", "23-456-78"), False, False),
    ("Dana Mizrahi", "female", ("Mazda", "3", "red", "34-567-89"), True, False),
]
PASSENGERS = [
    ("Yael Peretz", "female"),
    ("Omer Katz", "male"),
    ("Lior Shapira", "other"),
]

# start, end: (address, lat, lng)
TEL_AVIV = ("Azrieli Center, Tel Aviv", 32.0743, 34.7922)
JERUSALEM = ("Central Bus Station, Jerusalem", 31.7889, 35.2030)
HAIFA = ("Haifa Hof HaCarmel Station", 32.7940, 34.9590)
RAANANA = ("Ra'anana Central Park", 32.1848, 34.8713)
BEER_SHEVA = ("Beer Sheva North Station", 31.2627, 34.8089)
HERZLIYA = ("Herzliya Marina", 32.1624, 34.7954)


def _user(index: int, name: str, gender: str, *, vehicle: tuple | None, prefs: dict) -> User:
    now = utc_now()
    return User(
        clerk_user_id=f"{SEED_PREFIX}{index}",
        email=f"{SEED_PREFIX}{index}@example.com",
        name=name,
        gender=gender,
        date_of_birth=date(1990 + index % 8, 1 + index % 12, 10),
        terms_accepted_at=now,
        vehicle=(
            dict(zip(("make", "model", "color", "plate"), vehicle, strict=True))
            if vehicle
            else None
        ),
        preferences={"smoking": prefs["smoking"], "pets": prefs["pets"], "language": "en"},
    )


def _ride(driver: User, start: tuple, end: tuple, departure: datetime, price: str, **kw) -> Ride:
    capacity = kw.pop("capacity", 3)
    return Ride(
        driver=driver,
        start_address=start[0],
        start_lat=start[1],
        start_lng=start[2],
        end_address=end[0],
        end_lat=end[1],
        end_lng=end[2],
        departure_time=departure,
        capacity=capacity,
        available_seats=kw.pop("available_seats", capacity),
        price_per_seat=price,
        status=kw.pop("status", "upcoming"),
        preferences={"smoking": False, "pets": False, "music": True, "gender_only": False}
        | kw.pop("preferences", {}),
        **kw,
    )


async def seed(*, reset: bool) -> str:
    settings = get_settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as db, db.begin():
            seed_ids = (
                (
                    await db.execute(
                        select(User.id).where(User.clerk_user_id.like(f"{SEED_PREFIX}%"))
                    )
                )
                .scalars()
                .all()
            )
            if seed_ids and not reset:
                return f"{len(seed_ids)} seed users already exist; use --reset to rebuild"
            if seed_ids:
                ride_ids = select(Ride.id).where(Ride.driver_id.in_(seed_ids))
                await db.execute(delete(Rating).where(Rating.ride_id.in_(ride_ids)))
                await db.execute(delete(RideRequest).where(RideRequest.ride_id.in_(ride_ids)))
                await db.execute(delete(RideRequest).where(RideRequest.passenger_id.in_(seed_ids)))
                await db.execute(delete(Notification).where(Notification.user_id.in_(seed_ids)))
                await db.execute(delete(Ride).where(Ride.driver_id.in_(seed_ids)))
                await db.execute(
                    delete(User).where(
                        or_(User.id.in_(seed_ids), User.clerk_user_id.like(f"{SEED_PREFIX}%"))
                    )
                )

            drivers = [
                _user(i, n, g, vehicle=v, prefs={"smoking": s, "pets": p})
                for i, (n, g, v, s, p) in enumerate(DRIVERS)
            ]
            passengers = [
                _user(10 + i, n, g, vehicle=None, prefs={"smoking": False, "pets": False})
                for i, (n, g) in enumerate(PASSENGERS)
            ]
            db.add_all([*drivers, *passengers])

            # Whole hours from now, so a search "now + 2h" lands in the 4h window of several rides.
            base = utc_now().replace(minute=0, second=0, microsecond=0, tzinfo=UTC)
            noa, amir, dana = drivers
            yael, omer, lior = passengers
            upcoming = [
                _ride(noa, TEL_AVIV, JERUSALEM, base + timedelta(hours=3), "35.00"),
                _ride(noa, JERUSALEM, TEL_AVIV, base + timedelta(hours=27), "35.00"),
                _ride(amir, RAANANA, TEL_AVIV, base + timedelta(hours=2), "15.00", capacity=4),
                _ride(amir, HERZLIYA, HAIFA, base + timedelta(hours=5), "28.00"),
                _ride(
                    dana,
                    TEL_AVIV,
                    BEER_SHEVA,
                    base + timedelta(hours=4),
                    "40.00",
                    preferences={"smoking": True, "gender_only": True},
                ),
                _ride(dana, HAIFA, TEL_AVIV, base + timedelta(hours=50), "30.00", capacity=2),
            ]
            db.add_all(upcoming)

            full = _ride(
                amir,
                TEL_AVIV,
                HERZLIYA,
                base + timedelta(hours=6),
                "12.00",
                capacity=1,
                available_seats=0,
                status="full",
            )
            done = _ride(
                noa,
                TEL_AVIV,
                HAIFA,
                base - timedelta(days=2),
                "32.00",
                status="completed",
                available_seats=2,
            )
            db.add_all([full, done])
            await db.flush()

            db.add_all(
                [
                    RideRequest(ride=upcoming[0], passenger=yael, status="pending"),
                    RideRequest(ride=upcoming[0], passenger=omer, status="approved"),
                    RideRequest(ride=full, passenger=lior, status="approved"),
                    RideRequest(ride=done, passenger=yael, status="approved"),
                ]
            )
            upcoming[0].available_seats -= 1

            # One completed ride, rated both ways; the aggregates match the rows.
            db.add_all(
                [
                    Rating(
                        ride_id=done.id,
                        from_user_id=yael.id,
                        to_user_id=noa.id,
                        role_rated="driver",
                        score=5,
                        comment="Smooth and on time.",
                        tags=["punctual", "friendly"],
                    ),
                    Rating(
                        ride_id=done.id,
                        from_user_id=noa.id,
                        to_user_id=yael.id,
                        role_rated="passenger",
                        score=4,
                        comment="Easy pickup.",
                        tags=[],
                    ),
                ]
            )
            noa.driver_rating, noa.driver_rating_count = 5.0, 1
            yael.passenger_rating, yael.passenger_rating_count = 4.0, 1
        return f"seeded {len(drivers)} drivers, {len(passengers)} passengers, 8 rides"
    finally:
        await engine.dispose()


def main() -> None:
    print(asyncio.run(seed(reset="--reset" in sys.argv[1:])))


if __name__ == "__main__":
    main()
