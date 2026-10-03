"""Sentry, errors only (decision D2): no tracing, no profiling, no personal data.

What could reach Sentry, and what stops it:

- the FastAPI integration attaches the request (URL, query string, headers, cookies, body):
  `scrub_event` keeps only the method and the path; `max_request_body_size="never"`
- stack frames carry local variables (tokens, emails, bodies): `include_local_variables=False`
- exception values and log messages can quote SQL parameters or an email address (an
  `IntegrityError` does): both are redacted in messages, exception values and breadcrumbs
- breadcrumbs from logging and HTTP clients can carry URLs with query strings: stripped
- the WebSocket `auth` token never goes in a URL (CONTRACT.md §6) or a log line

An empty `SENTRY_DSN` turns all of this off, so development and tests are unaffected.
"""

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app import __version__
from app.config import Settings

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
#: SQLAlchemy appends the bound values to a DB error: `[parameters: (...)]`.
SQL_PARAMETERS = re.compile(r"\[parameters: .*?\](?=\s|\Z|\n)", re.DOTALL)
#: A JWT (the Clerk session token), wherever it turns up.
JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*")
REDACTED = "[redacted]"


def redact(text: str) -> str:
    text = SQL_PARAMETERS.sub("[parameters: redacted]", text)
    text = JWT.sub(REDACTED, text)
    return EMAIL.sub(REDACTED, text)


def strip_query(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return REDACTED
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _scrub_breadcrumb(crumb: dict[str, Any]) -> dict[str, Any]:
    if isinstance(crumb.get("message"), str):
        crumb["message"] = redact(crumb["message"])
    data = crumb.get("data")
    if isinstance(data, dict):
        for key in ("url", "to", "from"):
            if isinstance(data.get(key), str):
                data[key] = strip_query(data[key])
        for key, value in list(data.items()):
            if isinstance(value, str):
                data[key] = redact(value)
    return crumb


def scrub_event(event: dict[str, Any], hint: Any = None) -> dict[str, Any]:
    """`before_send`: keep what diagnoses the error, drop anything that identifies a person."""
    request = event.get("request")
    if isinstance(request, dict):
        url = request.get("url")
        event["request"] = {
            "method": request.get("method"),
            "url": strip_query(url) if isinstance(url, str) else None,
        }

    event.pop("user", None)
    event.pop("server_name", None)

    for exception in (event.get("exception") or {}).get("values") or []:
        if isinstance(exception.get("value"), str):
            exception["value"] = redact(exception["value"])
        for frame in (exception.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)

    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = redact(logentry[key])
        logentry.pop("params", None)
    if isinstance(event.get("message"), str):
        event["message"] = redact(event["message"])

    breadcrumbs = event.get("breadcrumbs")
    values = breadcrumbs.get("values") if isinstance(breadcrumbs, dict) else breadcrumbs
    for crumb in values or []:
        _scrub_breadcrumb(crumb)
    return event


def scrub_breadcrumb(crumb: dict[str, Any], hint: Any = None) -> dict[str, Any]:
    return _scrub_breadcrumb(crumb)


def init_sentry(settings: Settings, **overrides: Any) -> bool:
    """Start Sentry when `SENTRY_DSN` is set. Returns whether it did."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=f"ridematch-backend@{__version__}",
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=None,
        profiles_sample_rate=None,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        **overrides,
    )
    return True
