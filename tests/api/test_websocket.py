"""`GET /api/v1/ws` (CONTRACT.md §6, 0.5.0).

No token in the URL: the page's `Origin` must be one of `CORS_ORIGINS` (else
4403), and the first message must be `{"event": "auth", "token": ...}` within
WS_AUTH_TIMEOUT_SECONDS. The server answers `{"event": "ready"}`. Close codes:
4401 (invalid/expired token, no profile, any other first message, timeout),
4403 (deactivated account, foreign origin). The socket is accepted *before*
the close (app/ws.py), so the code only reaches the client once a frame is
read after the handshake. Ping/pong keeps the socket alive. The server pushes
`{"event": "notification", "data": <Notification>}` - the exact object `GET
/notifications` returns - gated on `preferences.notifications.websocket`; the
DB row is written either way.

`ws_client` (conftest.py) runs on its own app/engine, because
`TestClient.websocket_connect` drives the ASGI app from a background thread
with its own event loop - reusing the shared `app` fixture's engine there
breaks asyncpg. That means delivery (`app/ws.py`: "in-process... the live
sockets of this worker") only reaches a socket opened through *that same*
`ws_client`, so the push tests also trigger the action through `ws_client`
itself, not through the ordinary `client`/`rides`/`requests` fixtures.
"""

from __future__ import annotations

import logging

import pytest
from starlette.testclient import WebSocketDisconnect

from support import env
from support.assertions import expect_status
from support.factories import DEFAULT_VEHICLE, onboarding_payload
from support.keys import auth_header
from support.rides import notification_types, ride_payload
from support.websocket import WS_PATH, authed_socket, open_socket, receive_json

API = env.API_PREFIX


def _close_code(ws_client, first_message: dict | None, *, headers=None) -> int:
    """Open a socket, send `first_message` (if any), and return the close code."""
    with open_socket(ws_client, headers=headers) as ws, pytest.raises(WebSocketDisconnect) as exc:
        if first_message is not None:
            ws.send_json(first_message)
        ws.receive_text()
    return exc.value.code


def _auth(token: str) -> dict:
    return {"event": "auth", "token": token}


def _onboard(ws_client, users, **overrides) -> tuple[dict, str]:
    """Create a profile through `ws_client`'s own app, so it lands in the same
    in-process WsRegistry a socket on `ws_client` registers with."""
    sub, email = users.new_identity()
    token = users.signer.sign(sub=sub, email=email)
    response = ws_client.post(
        f"{API}/users/me/onboarding",
        json=onboarding_payload(**overrides),
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json(), token


class TestAuth:
    def test_an_invalid_token_closes_4401(self, ws_client) -> None:
        assert _close_code(ws_client, _auth("not-a-real-token")) == 4401

    async def test_an_expired_token_closes_4401(self, ws_client, user) -> None:
        assert _close_code(ws_client, _auth(user.token(expires_in=-3600))) == 4401

    async def test_a_valid_token_with_no_profile_closes_4401(self, ws_client, users) -> None:
        sub, email = users.new_identity()
        assert _close_code(ws_client, _auth(users.signer.sign(sub=sub, email=email))) == 4401

    async def test_a_deactivated_account_closes_4403(self, ws_client, users, user) -> None:
        await users.deactivate(user)
        assert _close_code(ws_client, _auth(user.token())) == 4403

    async def test_a_valid_auth_message_gets_ready_and_stays_open(self, ws_client, user) -> None:
        with authed_socket(ws_client, user.token()) as ws:
            ws.send_json({"event": "ping"})
            assert receive_json(ws) == {"event": "pong"}, "the socket must still be open"

    async def test_a_non_auth_first_message_closes_4401(self, ws_client, user) -> None:
        assert _close_code(ws_client, {"event": "ping"}) == 4401

    async def test_an_auth_message_without_a_token_closes_4401(self, ws_client) -> None:
        assert _close_code(ws_client, {"event": "auth"}) == 4401

    async def test_a_query_token_is_ignored(self, ws_client, user) -> None:
        """The legacy `?token=` (pre-0.5.0) authenticates nothing; a ping first is 4401."""
        with (
            ws_client.websocket_connect(
                f"{WS_PATH}?token={user.token()}", headers={"Origin": env.CLERK_AUTHORIZED_PARTY}
            ) as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.send_json({"event": "ping"})
            ws.receive_text()
        assert exc.value.code == 4401

    def test_no_auth_within_the_timeout_closes_4401(self, backend_app) -> None:
        from app.main import create_app
        from starlette.testclient import TestClient

        quick = backend_app.state.settings.model_copy(update={"ws_auth_timeout_seconds": 0.3})
        with TestClient(create_app(quick), base_url="http://testserver") as quick_client:
            assert _close_code(quick_client, None) == 4401

    @pytest.mark.parametrize("origin", ["https://evil.example", None])
    async def test_a_foreign_or_missing_origin_closes_4403(
        self, ws_client, user, origin: str | None
    ) -> None:
        headers = {"Origin": origin} if origin else {}
        assert _close_code(ws_client, _auth(user.token()), headers=headers) == 4403

    async def test_the_token_never_reaches_the_logs(self, ws_client, user, caplog) -> None:
        token = user.token()
        with caplog.at_level(logging.DEBUG), authed_socket(ws_client, token) as ws:
            ws.send_json({"event": "ping"})
            receive_json(ws)
        assert token not in caplog.text
        assert "eyJ" not in caplog.text


class TestPingPong:
    async def test_ping_gets_pong(self, ws_client, user) -> None:
        with authed_socket(ws_client, user.token()) as ws:
            ws.send_json({"event": "ping"})
            assert receive_json(ws) == {"event": "pong"}


class TestPush:
    def test_push_payload_equals_the_rest_object(self, ws_client, users) -> None:
        _driver, driver_token = _onboard(ws_client, users, vehicle=dict(DEFAULT_VEHICLE))

        with authed_socket(ws_client, driver_token) as ws:
            ride = ws_client.post(
                f"{API}/rides", json=ride_payload(), headers=auth_header(driver_token)
            ).json()
            _passenger, passenger_token = _onboard(ws_client, users)
            request_response = ws_client.post(
                f"{API}/rides/{ride['id']}/requests",
                json={"seats_requested": 1},
                headers=auth_header(passenger_token),
            )
            assert request_response.status_code == 201, request_response.text

            push = receive_json(ws)

        assert push["event"] == "notification"
        notifications = expect_status(
            ws_client.get(f"{API}/notifications", headers=auth_header(driver_token)), 200
        )
        assert push["data"] == notifications[0], (
            "CONTRACT.md §6: the push is the exact object GET /notifications returns"
        )

    async def test_no_push_when_the_user_opted_out(self, ws_client, users, db) -> None:
        driver, driver_token = _onboard(
            ws_client,
            users,
            vehicle=dict(DEFAULT_VEHICLE),
            preferences={"notifications": {"websocket": False}},
        )

        with authed_socket(ws_client, driver_token) as ws:
            ride = ws_client.post(
                f"{API}/rides", json=ride_payload(), headers=auth_header(driver_token)
            ).json()
            _passenger, passenger_token = _onboard(ws_client, users)
            request_response = ws_client.post(
                f"{API}/rides/{ride['id']}/requests",
                json={"seats_requested": 1},
                headers=auth_header(passenger_token),
            )
            assert request_response.status_code == 201, request_response.text

            ws.send_json({"event": "ping"})
            assert receive_json(ws) == {"event": "pong"}, (
                "a notification push would have arrived before the pong (FIFO) if one was sent"
            )

        assert "request_created" in await notification_types(db, driver["id"]), (
            "CONTRACT.md §6: the DB row is written regardless of the websocket preference"
        )
