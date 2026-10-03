"""`GET /api/v1/ws?token=<token>` (CONTRACT.md §6).

Browsers can't set headers on a WebSocket, hence the query-string token. Close
codes: 4401 (invalid/expired token, or a valid token with no onboarded
profile), 4403 (deactivated account). The socket is accepted *before* the
close (app/ws.py), so the code only reaches the client once a frame is read
after the handshake - a WebSocketDisconnect from entering the connection
itself would mean something else (e.g. a 404) went wrong. Ping/pong keeps the
socket alive. The server pushes `{"event": "notification", "data":
<Notification>}` - the exact object `GET /notifications` returns - gated on
`preferences.notifications.websocket`; the DB row is written either way.

`ws_client` (conftest.py) runs on its own app/engine, because
`TestClient.websocket_connect` drives the ASGI app from a background thread
with its own event loop - reusing the shared `app` fixture's engine there
breaks asyncpg. That means delivery (`app/ws.py`: "in-process... the live
sockets of this worker") only reaches a socket opened through *that same*
`ws_client`, so the push tests also trigger the action through `ws_client`
itself, not through the ordinary `client`/`rides`/`requests` fixtures.

`ws_client`'s `base_url` carries no API_PREFIX (`websocket_connect` does not
merge a base_url sub-path into the ASGI scope the way ordinary requests do),
so every path here spells out `API` itself.
"""

from __future__ import annotations

import pytest
from starlette.testclient import WebSocketDisconnect

from support import env
from support.assertions import expect_status
from support.factories import DEFAULT_VEHICLE, onboarding_payload
from support.keys import auth_header
from support.rides import notification_types, ride_payload
from support.websocket import receive_json

API = env.API_PREFIX


def _ws_url(token: str) -> str:
    return f"{API}/ws?token={token}"


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
        with (
            ws_client.websocket_connect(_ws_url("not-a-real-token")) as ws,
            pytest.raises(WebSocketDisconnect) as exc_info,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4401

    async def test_an_expired_token_closes_4401(self, ws_client, user) -> None:
        with (
            ws_client.websocket_connect(_ws_url(user.token(expires_in=-3600))) as ws,
            pytest.raises(WebSocketDisconnect) as exc_info,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4401

    async def test_a_valid_token_with_no_profile_closes_4401(self, ws_client, users) -> None:
        sub, email = users.new_identity()
        token = users.signer.sign(sub=sub, email=email)
        with (
            ws_client.websocket_connect(_ws_url(token)) as ws,
            pytest.raises(WebSocketDisconnect) as exc_info,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4401

    async def test_a_deactivated_account_closes_4403(self, ws_client, users, user) -> None:
        await users.deactivate(user)
        with (
            ws_client.websocket_connect(_ws_url(user.token())) as ws,
            pytest.raises(WebSocketDisconnect) as exc_info,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4403

    async def test_a_valid_token_connects_and_stays_open(self, ws_client, user) -> None:
        with ws_client.websocket_connect(_ws_url(user.token())) as ws:
            ws.send_json({"event": "ping"})
            assert receive_json(ws) == {"event": "pong"}, "the socket must still be open"


class TestPingPong:
    async def test_ping_gets_pong(self, ws_client, user) -> None:
        with ws_client.websocket_connect(_ws_url(user.token())) as ws:
            ws.send_json({"event": "ping"})
            assert receive_json(ws) == {"event": "pong"}


class TestPush:
    def test_push_payload_equals_the_rest_object(self, ws_client, users) -> None:
        _driver, driver_token = _onboard(ws_client, users, vehicle=dict(DEFAULT_VEHICLE))

        with ws_client.websocket_connect(_ws_url(driver_token)) as ws:
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

        with ws_client.websocket_connect(_ws_url(driver_token)) as ws:
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
