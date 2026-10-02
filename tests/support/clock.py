"""Time helpers. CONTRACT.md: the server returns UTC with a `Z` suffix."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """ISO 8601 with a literal `Z`, the way the server emits timestamps."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def whole_seconds(moment: datetime) -> datetime:
    """Drop the microseconds. The server answers timestamps at second
    resolution, so a test that compares what it sent against what came back
    sends whole seconds rather than asserting a precision nobody promised."""
    return moment.replace(microsecond=0)


def iso_in_hours(hours: float, *, base: datetime | None = None) -> str:
    """A whole-second UTC timestamp `hours` from now, ready to send."""
    return iso(whole_seconds(in_hours(hours, base=base)))


def iso_at_offset(moment: datetime, offset_hours: float) -> str:
    """The same instant written with a fixed UTC offset instead of `Z`.

    CONTRACT.md §2: the server "accepts any offset" and always answers UTC.
    """
    zone = timezone(timedelta(hours=offset_hours))
    return whole_seconds(moment).astimezone(zone).isoformat()


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
