"""`POST /webhooks/clerk` (CONTRACT.md §2 Webhooks, §4 Users; openapi.yaml
`/webhooks/clerk`). `security: []`: no Clerk session token, verified instead by
the `svix-*` headers over the raw body. Handles `user.updated` (sync email) and
`user.deleted` (deactivate); every other type is a no-op 204. Idempotent on
`svix-id`.
"""

from __future__ import annotations

from starlette.testclient import WebSocketDisconnect

from support import env
from support.assertions import expect_error, expect_no_content
from support.factories import onboarding_payload
from support.keys import auth_header
from support.webhooks import event_body, sign, unique_svix_id, user_deleted_data, user_updated_data

WEBHOOK = "/webhooks/clerk"
API = env.API_PREFIX


class TestSignature:
    async def test_valid_signature_is_accepted(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(
            await client.post(WEBHOOK, content=body, headers=headers)
        )

    async def test_missing_headers_is_a_signature_error(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        expect_error(
            await client.post(WEBHOOK, content=body), 400, "INVALID_WEBHOOK_SIGNATURE"
        )

    async def test_wrong_signature_is_rejected(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        headers = {
            "svix-id": unique_svix_id(),
            "svix-timestamp": "1700000000",
            "svix-signature": "v1,not-the-right-signature",
        }
        expect_error(
            await client.post(WEBHOOK, content=body, headers=headers), 400, "INVALID_WEBHOOK_SIGNATURE"
        )

    async def test_a_tampered_body_is_rejected(self, client, user) -> None:
        """The signature covers the raw body: changing it after signing must fail."""
        signed_body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email=user.email)
        )
        headers = sign(svix_id=unique_svix_id(), body=signed_body)
        tampered_body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email="attacker@evil.test")
        )
        expect_error(
            await client.post(WEBHOOK, content=tampered_body, headers=headers),
            400,
            "INVALID_WEBHOOK_SIGNATURE",
        )

    async def test_unhandled_event_type_is_ignored(self, client, user) -> None:
        body = event_body("session.created", {"id": user.clerk_user_id})
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))


class TestUserUpdated:
    async def test_syncs_the_email(self, client, admin, user) -> None:
        body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email="new-address@ridematch.test")
        )
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))

        detail = (await client.get(f"/admin/users/{user.id}", headers=admin.headers)).json()
        assert detail["user"]["email"] == "new-address@ridematch.test"

    async def test_an_unknown_clerk_user_id_is_still_a_no_op_204(self, client) -> None:
        body = event_body(
            "user.updated", user_updated_data("user_not_in_our_db", email="nobody@ridematch.test")
        )
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))


class TestUserDeleted:
    async def test_deactivates_the_user(self, client, admin, user) -> None:
        body = event_body("user.deleted", user_deleted_data(user.clerk_user_id))
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))

        expect_error(
            await client.get("/users/me", headers=user.headers), 403, "ACCOUNT_DEACTIVATED"
        )

    async def test_closes_open_sockets(self, ws_client, users) -> None:
        sub, email = users.new_identity()
        token = users.signer.sign(sub=sub, email=email)
        onboarded = ws_client.post(
            f"{API}/users/me/onboarding", json=onboarding_payload(), headers=auth_header(token)
        ).json()

        with ws_client.websocket_connect(f"{API}/ws?token={token}") as ws:
            body = event_body("user.deleted", user_deleted_data(sub))
            headers = sign(svix_id=unique_svix_id(), body=body)
            response = ws_client.post(f"{API}{WEBHOOK}", content=body, headers=headers)
            assert response.status_code == 204, response.text
            try:
                ws.receive_text()
                assert False, "expected the socket to close"
            except WebSocketDisconnect as exc:
                assert exc.code == 4403


class TestIdempotency:
    async def test_a_replayed_svix_id_is_a_no_op(self, client, admin, user) -> None:
        svix_id = unique_svix_id()
        first_body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email="first-address@ridematch.test")
        )
        headers = sign(svix_id=svix_id, body=first_body)
        expect_no_content(await client.post(WEBHOOK, content=first_body, headers=headers))

        replay_body = event_body(
            "user.updated",
            user_updated_data(user.clerk_user_id, email="second-address@ridematch.test"),
        )
        replay_headers = sign(svix_id=svix_id, body=replay_body)
        expect_no_content(await client.post(WEBHOOK, content=replay_body, headers=replay_headers))

        detail = (await client.get(f"/admin/users/{user.id}", headers=admin.headers)).json()
        assert detail["user"]["email"] == "first-address@ridematch.test", (
            "CONTRACT.md §2: deliveries are deduplicated on svix-id, so the replay "
            "(same id, different body) must not re-apply"
        )

    async def test_a_new_svix_id_is_applied_normally(self, client, admin, user) -> None:
        first_body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email="first-address@ridematch.test")
        )
        expect_no_content(
            await client.post(
                WEBHOOK, content=first_body, headers=sign(svix_id=unique_svix_id(), body=first_body)
            )
        )
        second_body = event_body(
            "user.updated", user_updated_data(user.clerk_user_id, email="second-address@ridematch.test")
        )
        expect_no_content(
            await client.post(
                WEBHOOK, content=second_body, headers=sign(svix_id=unique_svix_id(), body=second_body)
            )
        )

        detail = (await client.get(f"/admin/users/{user.id}", headers=admin.headers)).json()
        assert detail["user"]["email"] == "second-address@ridematch.test"
