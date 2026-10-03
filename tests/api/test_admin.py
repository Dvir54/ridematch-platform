"""`/admin/*` (CONTRACT.md §2 Admin, §3 ride state machine force-cancel, §4
Users deactivate/reactivate + Rides/analytics). Every admin endpoint requires
`CurrentAdmin`: a non-admin caller gets 403 FORBIDDEN (openapi.yaml documents
401/403 on all of them, same as any authenticated endpoint - CONTRACT.md §2).
Generic 401/ONBOARDING_REQUIRED/ACCOUNT_DEACTIVATED behaviour is covered once,
for every authenticated endpoint, by test_auth.py - this file only adds what is
specific to admin.
"""

from __future__ import annotations

import pytest
from starlette.testclient import WebSocketDisconnect

from support import clock, env
from support.assertions import expect_error, expect_status, expect_validation_error
from support.factories import onboarding_payload
from support.keys import auth_header
from support.rides import STARTABLE_HOURS, notification_types, ride_in_status
from support.websocket import authed_socket

API = env.API_PREFIX

ADMIN_ENDPOINTS = [
    ("get", "/admin/users", False),
    ("get", "/admin/users/{user_id}", False),
    ("post", "/admin/users/{user_id}/deactivate", False),
    ("post", "/admin/users/{user_id}/reactivate", False),
    ("get", "/admin/rides", False),
    ("post", "/admin/rides/{ride_id}/force-cancel", True),
    ("get", "/admin/analytics", False),
]


def _analytics_params() -> dict[str, str]:
    return {"from": clock.iso_in_hours(-24), "to": clock.iso_in_hours(24)}


class TestNonAdminForbidden:
    @pytest.mark.parametrize(
        "method,path,needs_body",
        ADMIN_ENDPOINTS,
        ids=[f"{m} {p}" for m, p, _ in ADMIN_ENDPOINTS],
    )
    async def test_each_admin_endpoint_rejects_a_non_admin(
        self, client, user, other_user, offer, method: str, path: str, needs_body: bool
    ) -> None:
        url = path.format(user_id=other_user.id, ride_id=offer.id)
        kwargs: dict = {"headers": user.headers}
        if needs_body:
            kwargs["json"] = {"reason": "testing"}
        if "analytics" in path:
            kwargs["params"] = _analytics_params()
        response = await getattr(client, method)(url, **kwargs)
        expect_error(response, 403, "FORBIDDEN")


class TestListUsers:
    async def test_total_count_header_and_pagination(self, client, admin, users) -> None:
        await users.create()
        await users.create()
        response = await client.get(
            "/admin/users", params={"limit": 1, "offset": 0}, headers=admin.headers
        )
        body = expect_status(response, 200)
        assert len(body) == 1
        total = int(response.headers["X-Total-Count"])
        assert total >= 3, "admin + the two created users, at least"

    async def test_filter_by_q_matches_name_or_email(self, client, admin, users) -> None:
        target = await users.create(name="Zelda Searchable")
        response = await client.get(
            "/admin/users", params={"q": "searchable"}, headers=admin.headers
        )
        body = expect_status(response, 200)
        assert [u["id"] for u in body] == [target.id]

    async def test_filter_by_is_active(self, client, admin, users, user) -> None:
        await users.deactivate(user)
        response = await client.get(
            "/admin/users", params={"is_active": False}, headers=admin.headers
        )
        body = expect_status(response, 200)
        assert user.id in [u["id"] for u in body]
        assert all(u["is_active"] is False for u in body)

    async def test_filter_by_is_admin(self, client, admin) -> None:
        response = await client.get(
            "/admin/users", params={"is_admin": True}, headers=admin.headers
        )
        body = expect_status(response, 200)
        assert [u["id"] for u in body] == [admin.id]


class TestGetUserDetail:
    async def test_includes_rides_requests_and_ratings(
        self, client, admin, rides, requests, driver, passenger, ratings
    ) -> None:
        offer = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        request = await requests.approved(offer, passenger)
        await rides.start(offer)
        await rides.complete(offer)
        await ratings.create(driver, ride_id=offer.id, to_user_id=passenger.id)

        body = expect_status(
            await client.get(f"/admin/users/{driver.id}", headers=admin.headers), 200
        )
        assert body["user"]["id"] == driver.id
        assert [r["id"] for r in body["rides_as_driver"]] == [offer.id]

        passenger_body = expect_status(
            await client.get(f"/admin/users/{passenger.id}", headers=admin.headers), 200
        )
        assert [r["id"] for r in passenger_body["requests_as_passenger"]] == [request["id"]]
        assert len(passenger_body["ratings_received"]) == 1

    async def test_a_missing_user_is_404(self, client, admin) -> None:
        expect_error(
            await client.get("/admin/users/9999999", headers=admin.headers), 404, "NOT_FOUND"
        )


class TestDeactivateReactivate:
    async def test_deactivate_blocks_the_next_request(self, client, admin, user) -> None:
        body = expect_status(
            await client.post(f"/admin/users/{user.id}/deactivate", headers=admin.headers), 200
        )
        assert body["is_active"] is False

        expect_error(
            await client.get("/users/me", headers=user.headers), 403, "ACCOUNT_DEACTIVATED"
        )

    async def test_reactivate_restores_access(self, client, admin, user) -> None:
        await client.post(f"/admin/users/{user.id}/deactivate", headers=admin.headers)
        body = expect_status(
            await client.post(f"/admin/users/{user.id}/reactivate", headers=admin.headers), 200
        )
        assert body["is_active"] is True
        expect_status(await client.get("/users/me", headers=user.headers), 200)

    async def test_admin_cannot_deactivate_self(self, client, admin) -> None:
        expect_error(
            await client.post(f"/admin/users/{admin.id}/deactivate", headers=admin.headers),
            409,
            "CANNOT_DEACTIVATE_SELF",
        )

    async def test_deactivate_a_missing_user_is_404(self, client, admin) -> None:
        expect_error(
            await client.post("/admin/users/9999999/deactivate", headers=admin.headers),
            404,
            "NOT_FOUND",
        )

    async def test_deactivate_closes_open_sockets(self, ws_client, users, admin) -> None:
        sub, email = users.new_identity()
        token = users.signer.sign(sub=sub, email=email)
        onboarded = ws_client.post(
            f"{API}/users/me/onboarding", json=onboarding_payload(), headers=auth_header(token)
        ).json()

        with authed_socket(ws_client, token) as ws:
            response = ws_client.post(
                f"{API}/admin/users/{onboarded['id']}/deactivate", headers=admin.headers
            )
            assert response.status_code == 200, response.text
            with pytest.raises(WebSocketDisconnect) as exc_info:
                ws.receive_text()
        assert exc_info.value.code == 4403


class TestForceCancel:
    @pytest.mark.parametrize("status", ["upcoming", "full", "in_progress"])
    async def test_cancels_a_non_terminal_ride(
        self, client, admin, rides, requests, users, status: str
    ) -> None:
        offer = await ride_in_status(
            status, rides=rides, requests=requests, users=users, capacity=2
        )
        body = expect_status(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel",
                json={"reason": "safety report"},
                headers=admin.headers,
            ),
            200,
        )
        assert body["status"] == "cancelled"

    @pytest.mark.parametrize("status", ["completed", "cancelled"])
    async def test_terminal_rides_cannot_be_force_cancelled(
        self, client, admin, rides, requests, users, status: str
    ) -> None:
        offer = await ride_in_status(status, rides=rides, requests=requests, users=users)
        expect_error(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel",
                json={"reason": "safety report"},
                headers=admin.headers,
            ),
            409,
            "INVALID_STATE_TRANSITION",
        )

    async def test_notifies_driver_and_active_passengers(
        self, client, admin, rides, requests, driver, passenger, db
    ) -> None:
        offer = await rides.offer(driver, capacity=2, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)

        expect_status(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel",
                json={"reason": "fleet recall"},
                headers=admin.headers,
            ),
            200,
        )

        assert "ride_cancelled" in await notification_types(db, passenger.id)
        assert "ride_cancelled" in await notification_types(db, driver.id)

    async def test_seats_return_to_the_ride(
        self, client, admin, rides, requests, driver, passenger
    ) -> None:
        offer = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)
        await rides.refresh(offer)
        assert offer.status == "full"

        body = expect_status(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel",
                json={"reason": "fleet recall"},
                headers=admin.headers,
            ),
            200,
        )
        assert body["available_seats"] == body["capacity"]

    async def test_reason_is_required(self, client, admin, offer) -> None:
        expect_validation_error(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel", json={}, headers=admin.headers
            ),
            field="reason",
        )

    async def test_admin_view_never_shows_the_plate(self, client, admin, offer) -> None:
        body = expect_status(
            await client.post(
                f"/admin/rides/{offer.id}/force-cancel",
                json={"reason": "fleet recall"},
                headers=admin.headers,
            ),
            200,
        )
        assert body["driver_vehicle_plate"] is None
        assert body["my_request"] is None

    async def test_a_missing_ride_is_404(self, client, admin) -> None:
        expect_error(
            await client.post(
                "/admin/rides/9999999/force-cancel",
                json={"reason": "x"},
                headers=admin.headers,
            ),
            404,
            "NOT_FOUND",
        )


class TestListRides:
    async def test_total_count_header(self, client, admin, offer) -> None:
        response = await client.get("/admin/rides", headers=admin.headers)
        body = expect_status(response, 200)
        assert int(response.headers["X-Total-Count"]) >= 1
        assert offer.id in [r["id"] for r in body]

    async def test_filter_by_driver_id(self, client, admin, rides, users) -> None:
        wanted = await rides.offer()
        other = await rides.offer()
        body = expect_status(
            await client.get(
                "/admin/rides", params={"driver_id": wanted.driver.id}, headers=admin.headers
            ),
            200,
        )
        ids = [r["id"] for r in body]
        assert wanted.id in ids
        assert other.id not in ids

    async def test_filter_by_status(self, client, admin, rides, requests, users) -> None:
        cancelled = await ride_in_status("cancelled", rides=rides, requests=requests, users=users)
        upcoming = await rides.offer()
        body = expect_status(
            await client.get("/admin/rides", params={"status": "cancelled"}, headers=admin.headers),
            200,
        )
        ids = [r["id"] for r in body]
        assert cancelled.id in ids
        assert upcoming.id not in ids


class TestAnalytics:
    async def test_requires_from_and_to(self, client, admin) -> None:
        expect_validation_error(await client.get("/admin/analytics", headers=admin.headers))

    async def test_counts_rides_and_requests_in_window(
        self, client, admin, rides, requests, driver, passenger
    ) -> None:
        offer = await rides.offer(driver, capacity=1, departure_in=STARTABLE_HOURS)
        await requests.approved(offer, passenger)
        await rides.start(offer)
        await rides.complete(offer)

        params = {"from": clock.iso_in_hours(-48), "to": clock.iso_in_hours(48)}
        body = expect_status(
            await client.get("/admin/analytics", params=params, headers=admin.headers), 200
        )
        assert body["rides_created"] >= 1
        assert body["rides_completed"] >= 1
        assert body["requests_created"] >= 1
        assert body["completion_rate"] == 1.0
        assert body["approval_rate"] == 1.0

    async def test_completion_rate_is_null_with_no_terminal_rides_in_window(
        self, client, admin
    ) -> None:
        params = {"from": clock.iso_in_hours(100), "to": clock.iso_in_hours(101)}
        body = expect_status(
            await client.get("/admin/analytics", params=params, headers=admin.headers), 200
        )
        assert body["completion_rate"] is None
        assert body["approval_rate"] is None
