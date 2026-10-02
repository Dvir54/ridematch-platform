"""The WebSocket of CONTRACT.md §6: `GET /api/v1/ws?token=<clerk_session_token>`.

- the token is checked once, at connect: invalid/expired or no profile closes with **4401**,
  a deactivated account with **4403**
- the connection is counted in Redis under `ws:online:{user_id}` (several tabs per user)
- the client pings every 25s and the server answers `{"event": "pong"}`; 60s without a ping
  closes the socket
- the server pushes `{"event": "notification", "data": <Notification>}` after commit

Delivery itself is in-process: `WsRegistry` holds the live sockets of this worker, and Redis
holds the presence counters the rest of the system reads.
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnected

from app.errors import AppError
from app.modules.users.models import User
from app.ws_push import PushItem

logger = logging.getLogger(__name__)

#: §6 close codes. 4401 = get a fresh token and reconnect; 4403 = don't.
WS_UNAUTHENTICATED = 4401
WS_DEACTIVATED = 4403
#: The client pings every 25s; the server gives up after this long without one.
PING_TIMEOUT_SECONDS = 60.0


def online_key(user_id: int) -> str:
    return f"ws:online:{user_id}"


class WsRegistry:
    """The live sockets of this process, plus the Redis presence counters.

    Redis is best-effort: a registry that can't reach it still delivers, because the counters
    are presence information and not the delivery path.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._sockets: dict[int, set[WebSocket]] = {}

    async def register(self, user_id: int, websocket: WebSocket) -> None:
        self._sockets.setdefault(user_id, set()).add(websocket)
        try:
            await self._redis.incr(online_key(user_id))
        except Exception:
            logger.warning("Redis unreachable; not counting the socket of user %s", user_id)

    async def unregister(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._sockets.get(user_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                self._sockets.pop(user_id, None)
        try:
            if await self._redis.decr(online_key(user_id)) <= 0:
                await self._redis.delete(online_key(user_id))
        except Exception:
            logger.warning("Redis unreachable; stale counter for user %s", user_id)

    async def online_count(self, user_id: int) -> int:
        try:
            value = await self._redis.get(online_key(user_id))
        except Exception:
            return len(self._sockets.get(user_id, ()))
        return max(0, int(value or 0))

    async def send(self, user_id: int, message: dict[str, Any]) -> int:
        """Send to every open socket of one user; returns how many got it."""
        delivered = 0
        for websocket in list(self._sockets.get(user_id, ())):
            try:
                await websocket.send_json(message)
                delivered += 1
            except Exception:
                # A socket that's already gone: the disconnect handler will tidy up.
                logger.debug("Dropping a dead socket of user %s", user_id)
        return delivered

    async def push(self, items: Sequence[PushItem]) -> int:
        """The `ws_push.Pusher` the session hands its after-commit messages to."""
        return sum([await self.send(user_id, message) for user_id, message in items])

    async def close_user(self, user_id: int, code: int = WS_DEACTIVATED) -> None:
        """Deactivating a user closes their open sockets (CONTRACT.md §6)."""
        for websocket in list(self._sockets.get(user_id, ())):
            try:
                await websocket.close(code=code)
            except Exception:
                logger.debug("Socket of user %s was already closed", user_id)


def get_ws_registry(request: Request) -> WsRegistry:
    return request.app.state.ws_registry


WsRegistryDep = Annotated[WsRegistry, Depends(get_ws_registry)]

router = APIRouter()


async def _authenticate(websocket: WebSocket, token: str | None) -> User | None:
    """The §6 handshake. Returns None once the socket has been closed with its code."""
    if not token:
        await websocket.close(code=WS_UNAUTHENTICATED, reason="Missing token.")
        return None
    try:
        claims = await websocket.app.state.clerk_verifier.verify(token)
    except AppError:
        await websocket.close(code=WS_UNAUTHENTICATED, reason="Invalid token.")
        return None

    async with websocket.app.state.sessionmaker() as session:
        user = (
            await session.execute(select(User).where(User.clerk_user_id == claims.sub))
        ).scalar_one_or_none()
    if user is None:
        await websocket.close(code=WS_UNAUTHENTICATED, reason="Onboarding required.")
        return None
    if not user.is_active:
        await websocket.close(code=WS_DEACTIVATED, reason="Account deactivated.")
        return None
    return user


@router.websocket("/ws")
async def notifications_socket(
    websocket: WebSocket,
    token: Annotated[str | None, Query(description="A fresh Clerk session token")] = None,
) -> None:
    # Accepted first: a close code only reaches the client over an open socket, and §6 is
    # written around the client reading 4401 and 4403.
    await websocket.accept()
    user = await _authenticate(websocket, token)
    if user is None:
        return

    registry: WsRegistry = websocket.app.state.ws_registry
    await registry.register(user.id, websocket)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=PING_TIMEOUT_SECONDS)
            except TimeoutError:
                # The socket may already be gone by now — e.g. an admin deactivated this user
                # and `WsRegistry.close_user` closed it from the other side (CONTRACT.md §6) —
                # in which case `close()` itself raises `WebSocketDisconnected`, not something
                # worth propagating as an unhandled error.
                with suppress(WebSocketDisconnect, WebSocketDisconnected):
                    await websocket.close(code=1000, reason="No ping.")
                return
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("event") == "ping":
                await websocket.send_json({"event": "pong"})
    except (WebSocketDisconnect, WebSocketDisconnected):
        # `WebSocketDisconnect`: the client went away. `WebSocketDisconnected`: `receive()` was
        # called again after a disconnect was already observed — e.g. the client's own close
        # racing a server-initiated one (`WsRegistry.close_user`) — functionally the same thing.
        pass
    finally:
        await registry.unregister(user.id, websocket)
