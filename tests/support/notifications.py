"""The in-memory email outbox (`EMAIL_BACKEND=memory`), for CONTRACT.md §7 trigger tests.

Phase 2/3 already prove *who* gets a notification row (see `support.rides.notification_rows`).
Phase 4 adds *which of those also get an email* - this module reads the same outbox
`app.modules.notifications.email` appends to, so a test never has to parse a log line.
"""

from __future__ import annotations

from typing import Any


def outbox() -> list[Any]:
    """The live list object the backend appends to. Mutating the returned list
    (e.g. `.clear()`) affects what the backend sees next, since it's the same object."""
    from app.modules.notifications.email import outbox as _outbox

    return _outbox


def clear_outbox() -> None:
    outbox().clear()


def emails_to(address: str) -> list[Any]:
    return [message for message in outbox() if message.to == address]
