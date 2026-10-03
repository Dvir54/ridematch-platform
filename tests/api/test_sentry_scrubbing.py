"""Sentry (decision D2) receives no personal data or credentials.

A real Sentry client with an in-memory transport captures what an unhandled error on a request
full of secrets would send, and the serialised events must contain none of them.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi import Request

from support import env

EMAIL = "secret.person@ridematch.test"
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.c2lnbmF0dXJl"
COOKIE = "__session=cookie-secret-value"
SVIX = "msg_svix-secret-id"
QUERY_SECRET = "query-secret-value"
BODY_SECRET = "body-secret-value"
SECRETS = (EMAIL, JWT, "cookie-secret-value", SVIX, QUERY_SECRET, BODY_SECRET, "eyJ")


def _capture_transport_class():
    from sentry_sdk.transport import Transport

    class CaptureTransport(Transport):
        """Keeps every envelope payload in memory instead of sending it anywhere."""

        def __init__(self, options=None) -> None:
            super().__init__(options)
            self.payloads: list[str] = []

        def capture_envelope(self, envelope) -> None:
            for item in envelope.items:
                self.payloads.append(item.payload.get_bytes().decode("utf-8", "replace"))

    return CaptureTransport


@pytest.fixture
def captured(backend_app):
    import sentry_sdk
    from app.main import create_app
    from app.monitoring import init_sentry

    # The app itself starts without a DSN; Sentry is then started with an in-memory transport,
    # so nothing ever leaves the process.
    app = create_app(backend_app.state.settings)
    settings = backend_app.state.settings.model_copy(
        update={"sentry_dsn": "https://public@sentry.example.invalid/1"}
    )
    transport = _capture_transport_class()()
    assert init_sentry(settings, transport=transport)

    async def boom(request: Request) -> None:
        body = await request.json()
        logging.getLogger("app.test").warning("about to fail for %s", body["email"])
        raise ValueError(f"duplicate key for {body['email']} [parameters: ('{body['name']}',)]")

    app.add_api_route(f"{env.API_PREFIX}/boom", boom, methods=["POST"])
    yield app, transport
    sentry_sdk.init()  # no DSN: Sentry off again for the rest of the suite


async def test_an_error_event_carries_no_personal_data(captured) -> None:
    import sentry_sdk

    app, transport = captured
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"{env.API_PREFIX}/boom?token={JWT}&q={QUERY_SECRET}&email={EMAIL}",
            json={"email": EMAIL, "name": BODY_SECRET},
            headers={
                "Authorization": f"Bearer {JWT}",
                "Cookie": COOKIE,
                "svix-id": SVIX,
                "svix-signature": f"v1,{SVIX}",
            },
        )
    assert response.status_code == 500
    sentry_sdk.flush()

    assert transport.payloads, "Sentry should have captured the error"
    captured_text = "\n".join(transport.payloads)
    for secret in SECRETS:
        assert secret not in captured_text, f"{secret!r} reached Sentry"
    event = next(json.loads(p) for p in transport.payloads if '"exception"' in p)
    assert event["request"]["url"].endswith("/boom"), "the path is kept for diagnosis"
    assert event["exception"]["values"][-1]["type"] == "ValueError"


def test_an_empty_dsn_does_not_start_sentry(backend_app) -> None:
    from app.monitoring import init_sentry

    assert init_sentry(backend_app.state.settings.model_copy(update={"sentry_dsn": ""})) is False
