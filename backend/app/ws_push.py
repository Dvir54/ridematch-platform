"""The hand-off between a service transaction and the WebSocket (CONTRACT.md §4, §6).

The push must happen **after commit**, so a service collects what it wants pushed on the
session (`db.info`) while it works and drains it once the transaction is durable. This module
imports nothing from `app`, which is what lets both `app.db` (where the pusher is attached to
the session) and the notifications service (where messages are collected) use it.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: `db.info` keys: the messages waiting for a commit, and the sender to hand them to.
PENDING_KEY = "ws_pending"
PUSHER_KEY = "ws_pusher"

#: `(user_id, message)` pairs; the message is a `WsServerMessage` from `openapi.yaml`.
type PushItem = tuple[int, dict[str, Any]]
type Pusher = Callable[[Sequence[PushItem]], Awaitable[Any]]


def collect(db: AsyncSession, user_id: int, message: dict[str, Any]) -> None:
    """Queue a message to be pushed once the current transaction commits."""
    db.info.setdefault(PENDING_KEY, []).append((user_id, message))


def discard(db: AsyncSession) -> None:
    """Drop what was queued — used when the transaction is rolled back."""
    db.info.pop(PENDING_KEY, None)


async def commit_and_push(db: AsyncSession) -> None:
    """Commit, then push what the transaction queued.

    The pending list is taken before the commit, so a failed commit pushes nothing. A failing
    push is logged and swallowed: the rows are written, and the client still has `GET
    /notifications`.
    """
    pending: list[PushItem] = db.info.pop(PENDING_KEY, [])
    await db.commit()
    pusher: Pusher | None = db.info.get(PUSHER_KEY)
    if not pending or pusher is None:
        return
    try:
        await pusher(pending)
    except Exception:
        logger.exception("Pushing %d notification(s) over the WebSocket failed", len(pending))
