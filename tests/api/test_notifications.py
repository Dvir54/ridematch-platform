"""GET/DELETE /notifications, GET /notifications/unread-count,
POST /notifications/{id}/read, POST /notifications/read-all.

Contract: CONTRACT.md §7 (trigger table), openapi `Notification`. The rows
themselves are proven elsewhere (Phase 2/3: notification_rows reads the table
directly); this file is the Phase 4 endpoints the frontend's Notifications tab
is built on.
"""

from __future__ import annotations

from support.assertions import expect_error, expect_no_content, expect_status


async def _ids(client, as_user, **params):
    body = expect_status(await client.get("/notifications", params=params, headers=as_user.headers), 200)
    return [n["id"] for n in body]


class TestList:
    async def test_newest_first(self, client, users, rides, requests) -> None:
        user = await users.create()  # welcome notification
        offer = await rides.offer()
        request = await requests.create(offer, user)  # request_created, to the driver
        await requests.approve(request, offer.driver)  # request_approved, to `user`

        ids = await _ids(client, user)
        assert ids == sorted(ids, reverse=True), f"expected newest-first order, got {ids}"
        assert len(ids) >= 2

    async def test_unread_only_excludes_read_notifications(self, client, users) -> None:
        user = await users.create()
        notification_id = (await _ids(client, user))[0]
        expect_status(
            await client.post(f"/notifications/{notification_id}/read", headers=user.headers), 200
        )

        unread_ids = await _ids(client, user, unread_only=True)
        assert notification_id not in unread_ids
        assert notification_id in await _ids(client, user)

    async def test_pagination(self, client, users, rides, requests) -> None:
        user = await users.create()
        offer = await rides.offer()
        await requests.approved(offer, user)  # a 2nd row: welcome + request_approved

        all_ids = await _ids(client, user)
        assert len(all_ids) >= 2
        page = await _ids(client, user, limit=1)
        assert page == all_ids[:1]
        rest = await _ids(client, user, limit=1, offset=1)
        assert rest == all_ids[1:2]

    async def test_requires_auth(self, client) -> None:
        expect_error(await client.get("/notifications"), 401, "UNAUTHENTICATED")

    async def test_a_stranger_is_onboarding_required(self, client, users) -> None:
        response = await client.get("/notifications", headers=users.stranger_headers())
        expect_error(response, 403, "ONBOARDING_REQUIRED")

    async def test_a_deactivated_user_is_forbidden(self, client, users, user) -> None:
        await users.deactivate(user)
        expect_error(await client.get("/notifications", headers=user.headers), 403, "ACCOUNT_DEACTIVATED")


class TestUnreadCount:
    async def test_counts_only_unread(self, client, users) -> None:
        user = await users.create()
        before = expect_status(
            await client.get("/notifications/unread-count", headers=user.headers), 200
        )
        assert before["count"] >= 1

        notification_id = (await _ids(client, user))[0]
        expect_status(
            await client.post(f"/notifications/{notification_id}/read", headers=user.headers), 200
        )
        after = expect_status(
            await client.get("/notifications/unread-count", headers=user.headers), 200
        )
        assert after["count"] == before["count"] - 1


class TestMarkRead:
    async def test_marks_is_read(self, client, users) -> None:
        user = await users.create()
        notification_id = (await _ids(client, user))[0]

        body = expect_status(
            await client.post(f"/notifications/{notification_id}/read", headers=user.headers), 200
        )
        assert body["id"] == notification_id
        assert body["is_read"] is True

    async def test_is_idempotent(self, client, users) -> None:
        user = await users.create()
        notification_id = (await _ids(client, user))[0]
        for _ in range(2):
            body = expect_status(
                await client.post(f"/notifications/{notification_id}/read", headers=user.headers),
                200,
            )
            assert body["is_read"] is True

    async def test_someone_elses_notification_is_forbidden(self, client, users, other_user) -> None:
        """Same convention as GET /requests/{id} (test_requests.py): exists but
        not yours is 403 FORBIDDEN, not a privacy-hiding 404."""
        user = await users.create()
        notification_id = (await _ids(client, user))[0]

        response = await client.post(
            f"/notifications/{notification_id}/read", headers=other_user.headers
        )
        expect_error(response, 403, "FORBIDDEN")

    async def test_a_missing_notification_is_404(self, client, user) -> None:
        response = await client.post("/notifications/9999999/read", headers=user.headers)
        expect_error(response, 404, "NOT_FOUND")


class TestReadAll:
    async def test_marks_everything_read(self, client, users, rides, requests) -> None:
        user = await users.create()
        offer = await rides.offer()
        await requests.approved(offer, user)

        expect_no_content(await client.post("/notifications/read-all", headers=user.headers))

        unread = expect_status(
            await client.get("/notifications/unread-count", headers=user.headers), 200
        )
        assert unread["count"] == 0
        for notification in expect_status(
            await client.get("/notifications", headers=user.headers), 200
        ):
            assert notification["is_read"] is True

    async def test_does_not_touch_another_users_notifications(
        self, client, users, other_user
    ) -> None:
        user = await users.create()
        expect_no_content(await client.post("/notifications/read-all", headers=user.headers))

        other_unread = expect_status(
            await client.get("/notifications/unread-count", headers=other_user.headers), 200
        )
        assert other_unread["count"] >= 1, "another user's notifications must be untouched"


class TestClear:
    async def test_deletes_everything(self, client, users) -> None:
        user = await users.create()
        expect_no_content(await client.delete("/notifications", headers=user.headers))
        assert await _ids(client, user) == []

    async def test_does_not_touch_another_users_notifications(
        self, client, users, other_user
    ) -> None:
        user = await users.create()
        expect_no_content(await client.delete("/notifications", headers=user.headers))
        assert await _ids(client, other_user) != []
