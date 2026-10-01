"""GET and PATCH /users/me (CONTRACT.md 2, 4; openapi UserMe / UserUpdate).

Preference merging is the subtle part: CONTRACT.md 4 says a PATCH is a shallow
merge, "the `notifications` sub-object is merged too".
"""

from __future__ import annotations

import pytest

from support.assertions import expect_error, expect_status, expect_validation_error

ME = "/users/me"
DEFAULT_NOTIFICATIONS = {"email": True, "push": True, "websocket": True}


class TestGet:
    async def test_returns_the_callers_profile(self, client, user) -> None:
        body = expect_status(await client.get(ME, headers=user.headers), 200)
        assert body["id"] == user.id
        assert body["email"] == user.email
        assert body["name"] == user.name

    async def test_preference_defaults_are_filled_on_read(self, client, user) -> None:
        """CONTRACT.md 4: the server fills defaults for missing keys."""
        prefs = expect_status(await client.get(ME, headers=user.headers), 200)["preferences"]
        assert prefs.keys() >= {
            "default_mode",
            "smoking",
            "pets",
            "notifications",
            "language",
            "theme",
        }
        assert prefs["notifications"] == DEFAULT_NOTIFICATIONS

    async def test_requires_authentication(self, client) -> None:
        expect_error(await client.get(ME), 401, "UNAUTHENTICATED")

    async def test_requires_onboarding(self, client, users) -> None:
        response = await client.get(ME, headers=users.stranger_headers())
        expect_error(response, 403, "ONBOARDING_REQUIRED")


class TestPatchProfileFields:
    async def test_update_name(self, client, user) -> None:
        body = expect_status(
            await client.patch(ME, json={"name": "Dana"}, headers=user.headers), 200
        )
        assert body["name"] == "Dana"
        assert expect_status(await client.get(ME, headers=user.headers), 200)["name"] == "Dana"

    async def test_update_phone(self, client, user) -> None:
        response = await client.patch(ME, json={"phone": "+972 52-000-0000"}, headers=user.headers)
        assert expect_status(response, 200)["phone"] == "+972 52-000-0000"

    async def test_clear_phone_with_null(self, client, users) -> None:
        user = await users.create(phone="+972 52-000-0000")
        response = await client.patch(ME, json={"phone": None}, headers=user.headers)
        assert expect_status(response, 200)["phone"] is None

    async def test_update_gender(self, client, user) -> None:
        response = await client.patch(ME, json={"gender": "other"}, headers=user.headers)
        assert expect_status(response, 200)["gender"] == "other"

    async def test_empty_patch_changes_nothing(self, client, user) -> None:
        before = expect_status(await client.get(ME, headers=user.headers), 200)
        after = expect_status(await client.patch(ME, json={}, headers=user.headers), 200)
        assert after["name"] == before["name"]
        assert after["preferences"] == before["preferences"]

    async def test_unspecified_fields_are_left_alone(self, client, users) -> None:
        user = await users.create(name="Keep", gender="male")
        body = expect_status(
            await client.patch(ME, json={"name": "Changed"}, headers=user.headers), 200
        )
        assert body["gender"] == "male"


class TestPatchPreferences:
    async def test_shallow_merge_keeps_untouched_keys(self, client, user) -> None:
        response = await client.patch(
            ME, json={"preferences": {"theme": "dark"}}, headers=user.headers
        )
        prefs = expect_status(response, 200)["preferences"]
        assert prefs["theme"] == "dark"
        assert prefs["language"] == "en"
        assert prefs["smoking"] is False
        assert prefs["notifications"] == DEFAULT_NOTIFICATIONS

    async def test_notifications_sub_object_is_merged_too(self, client, user) -> None:
        """CONTRACT.md 4: the notifications sub-object is merged, not replaced."""
        response = await client.patch(
            ME,
            json={"preferences": {"notifications": {"email": False}}},
            headers=user.headers,
        )
        notifications = expect_status(response, 200)["preferences"]["notifications"]
        assert notifications == {"email": False, "push": True, "websocket": True}

    async def test_successive_patches_accumulate(self, client, user) -> None:
        await client.patch(ME, json={"preferences": {"smoking": True}}, headers=user.headers)
        response = await client.patch(
            ME, json={"preferences": {"pets": True}}, headers=user.headers
        )
        prefs = expect_status(response, 200)["preferences"]
        assert prefs["smoking"] is True
        assert prefs["pets"] is True

    async def test_default_mode_can_be_set_and_cleared(self, client, user) -> None:
        response = await client.patch(
            ME, json={"preferences": {"default_mode": "passenger"}}, headers=user.headers
        )
        assert expect_status(response, 200)["preferences"]["default_mode"] == "passenger"

        response = await client.patch(
            ME, json={"preferences": {"default_mode": None}}, headers=user.headers
        )
        assert expect_status(response, 200)["preferences"]["default_mode"] is None

    async def test_preferences_survive_an_unrelated_patch(self, client, user) -> None:
        await client.patch(ME, json={"preferences": {"theme": "dark"}}, headers=user.headers)
        response = await client.patch(ME, json={"name": "Dana"}, headers=user.headers)
        assert expect_status(response, 200)["preferences"]["theme"] == "dark"


class TestPatchValidation:
    async def test_empty_name(self, client, user) -> None:
        response = await client.patch(ME, json={"name": ""}, headers=user.headers)
        expect_validation_error(response, field="name")

    async def test_name_too_long(self, client, user) -> None:
        response = await client.patch(ME, json={"name": "x" * 101}, headers=user.headers)
        expect_validation_error(response, field="name")

    async def test_invalid_gender(self, client, user) -> None:
        response = await client.patch(ME, json={"gender": "spaceship"}, headers=user.headers)
        expect_validation_error(response, field="gender")

    async def test_invalid_theme(self, client, user) -> None:
        response = await client.patch(
            ME, json={"preferences": {"theme": "neon"}}, headers=user.headers
        )
        expect_error(response, 422, "VALIDATION_ERROR")

    async def test_invalid_default_mode(self, client, user) -> None:
        response = await client.patch(
            ME, json={"preferences": {"default_mode": "pilot"}}, headers=user.headers
        )
        expect_error(response, 422, "VALIDATION_ERROR")

    @pytest.mark.xfail(
        reason='FAIL reported to @backend: PATCH /users/me coerces preferences.smoking="yes" '
        "to true and returns 200. openapi.yaml types it as boolean and CONTRACT.md 2 says "
        "openapi.yaml wins for shapes, so a string should be 422 VALIDATION_ERROR."
    )
    async def test_wrong_type_for_a_boolean_preference(self, client, user) -> None:
        response = await client.patch(
            ME, json={"preferences": {"smoking": "yes"}}, headers=user.headers
        )
        expect_error(response, 422, "VALIDATION_ERROR")

    async def test_validation_error_lists_the_field(self, client, user) -> None:
        body = expect_validation_error(
            await client.patch(ME, json={"gender": "spaceship"}, headers=user.headers)
        )
        assert body.get("details"), "VALIDATION_ERROR should list the offending fields"


class TestPatchCannotEscalate:
    async def test_is_admin_is_not_settable(self, client, user, db) -> None:
        """UserUpdate has no is_admin: "is_admin/is_active are admin-only"."""
        response = await client.patch(ME, json={"is_admin": True}, headers=user.headers)
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
        else:
            assert expect_status(response, 200)["is_admin"] is False
        assert (await db.user_row(user.id))["is_admin"] is False

    async def test_is_active_is_not_settable(self, client, user, db) -> None:
        response = await client.patch(ME, json={"is_active": False}, headers=user.headers)
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
        else:
            assert expect_status(response, 200)["is_active"] is True
        assert (await db.user_row(user.id))["is_active"] is True

    async def test_email_is_not_settable(self, client, user) -> None:
        """CONTRACT.md 2: email changes happen in Clerk, mirrored by webhook."""
        response = await client.patch(
            ME, json={"email": "hijack@ridematch.test"}, headers=user.headers
        )
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
        else:
            assert expect_status(response, 200)["email"] == user.email

    async def test_ratings_are_not_settable(self, client, user) -> None:
        response = await client.patch(
            ME, json={"driver_rating": 5, "driver_rating_count": 99}, headers=user.headers
        )
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
        else:
            body = expect_status(response, 200)
            assert body["driver_rating"] is None
            assert body["driver_rating_count"] == 0


class TestPatchPermissions:
    async def test_requires_authentication(self, client) -> None:
        expect_error(await client.patch(ME, json={"name": "Dana"}), 401, "UNAUTHENTICATED")

    @pytest.mark.xfail(
        reason="Reported to @backend: openapi.yaml documents no 403 for this operation, "
        "though CONTRACT.md 2 lets any authenticated endpoint return ONBOARDING_REQUIRED "
        "or ACCOUNT_DEACTIVATED. The backend behaves correctly; the contract is incomplete."
    )
    async def test_requires_onboarding(self, client, users) -> None:
        response = await client.patch(ME, json={"name": "Dana"}, headers=users.stranger_headers())
        expect_error(response, 403, "ONBOARDING_REQUIRED")

    @pytest.mark.xfail(
        reason="Reported to @backend: openapi.yaml documents no 403 for this operation, "
        "though CONTRACT.md 2 lets any authenticated endpoint return ONBOARDING_REQUIRED "
        "or ACCOUNT_DEACTIVATED. The backend behaves correctly; the contract is incomplete."
    )
    async def test_deactivated_account_cannot_patch(self, client, users, user) -> None:
        await users.deactivate(user)
        response = await client.patch(ME, json={"name": "Dana"}, headers=user.headers)
        expect_error(response, 403, "ACCOUNT_DEACTIVATED")

    async def test_one_user_cannot_touch_another(self, client, users) -> None:
        first = await users.create(name="First")
        second = await users.create(name="Second")
        await client.patch(ME, json={"name": "Renamed"}, headers=second.headers)
        assert expect_status(await client.get(ME, headers=first.headers), 200)["name"] == "First"
