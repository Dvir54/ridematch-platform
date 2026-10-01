"""Time helpers. CONTRACT.md: the server returns UTC with a `Z` suffix."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """ISO 8601 with a literal `Z`, the way the server emits timestamps."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def in_hours(hours: float, *, base: datetime | None = None) -> datetime:
    return (base or now()) + timedelta(hours=hours)


def in_days(days: float, *, base: datetime | None = None) -> datetime:
    return (base or now()) + timedelta(days=days)


def parse(value: str) -> datetime:
    """Parse a server timestamp, accepting the `Z` suffix."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def birth_date_for_age(age: int, *, on: date | None = None) -> date:
    """The latest birth date that makes someone exactly `age` on `on`."""
    today = on or now().date()
    day = today.day
    if today.month == 2 and day == 29:  # no 29 Feb in a non-leap birth year
        day = 28
    return date(today.year - age, today.month, day)
