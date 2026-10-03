"""`POST /webhooks/clerk` (CONTRACT.md §2 Webhooks, §4 Users; openapi.yaml
`/webhooks/clerk`). `security: []`: no Clerk session token, verified instead by
the `svix-*` headers over the raw body. Handles `user.updated` (sync email) and
`user.deleted` (deactivate); every other type is a no-op 204. Idempotent on
`svix-id`.
"""

from __future__ import annotations

from starlette.testclient import WebSocketDisconnect

from support import env
from support.assertions import expect_error, expect_no_content, expect_status
from support.factories import onboarding_payload
from support.keys import auth_header
from support.webhooks import event_body, sign, unique_svix_id, user_deleted_data, user_updated_data
from support.websocket import authed_socket

WEBHOOK = "/webhooks/clerk"
API = env.API_PREFIX


class TestSignature:
    async def test_valid_signature_is_accepted(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))

    async def test_missing_headers_is_a_signature_error(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        expect_error(await client.post(WEBHOOK, content=body), 400, "INVALID_WEBHOOK_SIGNATURE")

    async def test_wrong_signature_is_rejected(self, client, user) -> None:
        body = event_body("user.updated", user_updated_data(user.clerk_user_id, email=user.email))
        headers = {
            "svix-id": unique_svix_id(),
            "svix-timestamp": "1700000000",
            "svix-signature": "v1,not-the-right-signature",
        }
        expect_error(
            await client.post(WEBHOOK, content=body, headers=headers),
            400,
            "INVALID_WEBHOOK_SIGNATURE",
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
            "user.updated",
            user_updated_data(user.clerk_user_id, email="new-address@ridematch.test"),
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
    async def test_deactivates_the_user(self, client, admin, user, db) -> None:
        body = event_body("user.deleted", user_deleted_data(user.clerk_user_id))
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))

        assert (await db.user_row(user.id))["is_active"] is False
        # The Clerk id is anonymised too (CONTRACT.md §4), so a still-valid token from the
        # deleted Clerk account no longer maps to the row at all.
        expect_error(
            await client.get("/users/me", headers=user.headers), 403, "ONBOARDING_REQUIRED"
        )

    async def test_closes_open_sockets(self, ws_client, users) -> None:
        sub, email = users.new_identity()
        token = users.signer.sign(sub=sub, email=email)
        ws_client.post(
            f"{API}/users/me/onboarding", json=onboarding_payload(), headers=auth_header(token)
        )

        with authed_socket(ws_client, token) as ws:
            body = event_body("user.deleted", user_deleted_data(sub))
            headers = sign(svix_id=unique_svix_id(), body=body)
            response = ws_client.post(f"{API}{WEBHOOK}", content=body, headers=headers)
            assert response.status_code == 204, response.text
            try:
                ws.receive_text()
                raise AssertionError("expected the socket to close")
            except WebSocketDisconnect as exc:
                assert exc.code == 4403


class TestUserDeletedAnonymises:
    """CONTRACT.md §4 Users: `user.deleted` removes the personal data, keeps the history."""

    async def _delete(self, client, clerk_user_id: str) -> None:
        body = event_body("user.deleted", user_deleted_data(clerk_user_id))
        headers = sign(svix_id=unique_svix_id(), body=body)
        expect_no_content(await client.post(WEBHOOK, content=body, headers=headers))

    async def test_the_row_keeps_none_of_the_personal_data(self, client, users, db) -> None:
        user = await users.create_driver(gender="female")
        before = await db.user_row(user.id)

        await self._delete(client, user.clerk_user_id)

        row = await db.user_row(user.id)
        assert row["name"] == "Deleted user"
        assert row["email"] == f"deleted-{user.id}@deleted.invalid"
        assert row["clerk_user_id"] == f"deleted_{user.id}"
        assert row["gender"] is None
        assert row["vehicle"] is None
        assert row["preferences"] is None
        assert str(row["date_of_birth"]) == "1900-01-01"
        assert row["is_active"] is False
        for column in ("name", "email", "clerk_user_id", "date_of_birth"):
            assert row[column] != before[column], column

    async def test_the_public_profile_shows_deleted_user(self, client, users) -> None:
        subject = await users.create()
        viewer = await users.create()
        await self._delete(client, subject.clerk_user_id)

        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert body["name"] == "Deleted user"

    async def test_rides_stay_for_the_other_party(self, client, users, rides, db) -> None:
        offer = await rides.offer()
        await self._delete(client, offer.driver.clerk_user_id)
        assert await db.count("rides") == 1

    async def test_a_second_delivery_is_a_no_op(self, client, users, db) -> None:
        user = await users.create()
        await self._delete(client, user.clerk_user_id)
        first = await db.user_row(user.id)
        await self._delete(client, user.clerk_user_id)  # new svix id, same Clerk user
        assert await db.user_row(user.id) == first

    async def test_an_admin_deactivated_user_is_still_anonymised(self, client, users, db) -> None:
        user = await users.create()
        await users.deactivate(user)
        await self._delete(client, user.clerk_user_id)
        assert (await db.user_row(user.id))["name"] == "Deleted user"


class TestIdempotency:
    async def test_a_replayed_svix_id_is_a_no_op(self, client, admin, user) -> None:
        svix_id = unique_svix_id()
        first_body = event_body(
            "user.updated",
            user_updated_data(user.clerk_user_id, email="first-address@ridematch.test"),
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
            "user.updated",
            user_updated_data(user.clerk_user_id, email="first-address@ridematch.test"),
        )
        expect_no_content(
            await client.post(
                WEBHOOK, content=first_body, headers=sign(svix_id=unique_svix_id(), body=first_body)
            )
        )
        second_body = event_body(
            "user.updated",
            user_updated_data(user.clerk_user_id, email="second-address@ridematch.test"),
        )
        expect_no_content(
            await client.post(
                WEBHOOK,
                content=second_body,
                headers=sign(svix_id=unique_svix_id(), body=second_body),
            )
        )

        detail = (await client.get(f"/admin/users/{user.id}", headers=admin.headers)).json()
        assert detail["user"]["email"] == "second-address@ridematch.test"
