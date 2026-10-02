"""A `receive_json` with a timeout, for the WebSocket tests (CONTRACT.md §6).

`WebSocketTestSession.receive_json` blocks forever if nothing arrives. A
backend bug (no pong, no push) must fail the test, not hang the whole suite -
hence the daemon thread instead of a bare call.
"""

from __future__ import annotations

import queue
import threading
from typing import Any


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
