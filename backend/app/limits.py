"""Request body cap: anything over 64 KiB is 413 `PAYLOAD_TOO_LARGE` (CONTRACT.md §2, §5).

A declared `Content-Length` over the cap is refused before the app runs. A body without one
(chunked) is counted as it is read, and the read fails with the same 413 once it passes the cap.
"""

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 64 * 1024
CODE = "PAYLOAD_TOO_LARGE"
MESSAGE = "The request body is over 64 KiB."


class PayloadTooLarge(HTTPException):
    """An `HTTPException`, so FastAPI's body parsing re-raises it rather than calling it a 400."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=MESSAGE)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            response = JSONResponse({"code": CODE, "message": MESSAGE}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise PayloadTooLarge()
            return message

        await self.app(scope, limited_receive, send)
