"""The error envelope `{code, message, details}` (CONTRACT.md §5).

Every error response in the API has this shape, including FastAPI's 422 and any unhandled
exception. Clients branch on `code`, never on `message`.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base for every error the API raises deliberately."""

    status_code: int = 500
    default_code: str = "INTERNAL_ERROR"
    default_message: str = "Something went wrong."

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        details: list[dict[str, str]] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.default_message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def body(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class BadRequest(AppError):
    status_code = 400
    default_code = "INVALID_WEBHOOK_SIGNATURE"
    default_message = "Missing or invalid webhook signature."


class Unauthenticated(AppError):
    status_code = 401
    default_code = "UNAUTHENTICATED"
    default_message = "Missing, invalid or expired session token."


class Forbidden(AppError):
    status_code = 403
    default_code = "FORBIDDEN"
    default_message = "You are not allowed to do that."


class NotFound(AppError):
    status_code = 404
    default_code = "NOT_FOUND"
    default_message = "Resource not found."


class Conflict(AppError):
    status_code = 409
    default_code = "CONFLICT"
    default_message = "The request conflicts with the current state."


class UnprocessableEntity(AppError):
    """422s with a specific code, e.g. UNDERAGE or TERMS_NOT_ACCEPTED."""

    status_code = 422
    default_code = "VALIDATION_ERROR"
    default_message = "The request could not be processed."


# HTTP statuses FastAPI/Starlette may raise on their own (unknown route, bad method, …).
_HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _validation_details(errors: list[Any]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        details.append({"field": location, "message": error.get("msg", "Invalid value.")})
    return details


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        error = UnprocessableEntity(
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=_validation_details(list(exc.errors())),
        )
        return JSONResponse(status_code=error.status_code, content=error.body())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": message},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=AppError().body())
