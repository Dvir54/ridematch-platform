"""Helpers for the WebSocket tests (CONTRACT.md §6): a `receive_json` with a timeout, and the
connect-then-`auth` handshake.

`WebSocketTestSession.receive_json` blocks forever if nothing arrives. A
backend bug (no pong, no push) must fail the test, not hang the whole suite -
hence the daemon thread instead of a bare call.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from . import env

WS_PATH = f"{env.API_PREFIX}/ws"
#: A page origin the backend allows (`CORS_ORIGINS` in support/env.py).
ORIGIN = env.CLERK_AUTHORIZED_PARTY
ORIGIN_HEADERS = {"Origin": ORIGIN}


def receive_json(ws: Any, timeout: float = 5.0) -> dict[str, Any]:
    result: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def _run() -> None:
        try:
            result.put(("ok", ws.receive_json()))
        except Exception as exc:  # relayed to the caller, whatever it is
            result.put(("error", exc))

    threading.Thread(target=_run, daemon=True).start()
    try:
        kind, value = result.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError(f"no WebSocket message received within {timeout}s") from None
    if kind == "error":
        raise value
    return value


def open_socket(ws_client: Any, *, headers: dict[str, str] | None = None) -> Any:
    """Open `GET /ws` from an allowed page origin, without authenticating yet."""
    return ws_client.websocket_connect(
        WS_PATH, headers=ORIGIN_HEADERS if headers is None else headers
    )


@contextmanager
def authed_socket(ws_client: Any, token: str) -> Iterator[Any]:
    """Connect, send the `auth` message, and wait for `ready`."""
    with open_socket(ws_client) as ws:
        ws.send_json({"event": "auth", "token": token})
        assert receive_json(ws) == {"event": "ready"}
        yield ws
