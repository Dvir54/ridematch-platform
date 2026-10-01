"""GET /users/{user_id} - the public profile (openapi UserPublic, CONTRACT.md 4).

UserPublic is deliberately narrower than UserMe: "No email/phone/DOB." The
contract validator runs in strict mode, so an undeclared field fails on its
own, but the fields that matter are also asserted by name here.
"""

from __future__ import annotations

from support.assertions import assert_absent, expect_error, expect_status
from support.factories import DEFAULT_VEHICLE

PRIVATE_FIELDS = (
    "email",
    "phone",
    "date_of_birth",
    "is_admin",
    "is_active",
    "preferences",
    "last_login_at",
)


class TestPublicProfile:
    async def test_returns_the_public_shape(self, client, users) -> None:
        subject = await users.create(name="Noa")
        viewer = await users.create()

        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert body["id"] == subject.id
        assert body["name"] == "Noa"
        assert body["driver_rating"] is None
        assert body["driver_rating_count"] == 0
        assert body["passenger_rating"] is None
        assert body["passenger_rating_count"] == 0
        assert body["created_at"], 'created_at drives the "Member since" line'

    async def test_hides_private_fields(self, client, users) -> None:
        subject = await users.create(phone="+972 50-123-4567", gender="female")
        viewer = await users.create()

        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert_absent(body, *PRIVATE_FIELDS)

    async def test_hides_private_fields_from_the_subject_too(self, client, users) -> None:
        """The endpoint has one shape; /users/me is where you see your own data."""
        subject = await users.create(phone="+972 50-123-4567")
        body = expect_status(await client.get(f"/users/{subject.id}", headers=subject.headers), 200)
        assert_absent(body, *PRIVATE_FIELDS)

    async def test_admin_status_is_not_public(self, client, users, db) -> None:
        subject = await users.create()
        await db.set_admin(subject.id, True)
        viewer = await users.create()

        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert_absent(body, "is_admin")


class TestPublicVehicle:
    async def test_vehicle_is_shown_without_the_plate(self, client, users) -> None:
        """CONTRACT.md 4 / D14: make, model and colour are public; the plate is not."""
        subject = await users.create_driver()
        viewer = await users.create()

        vehicle = expect_status(
            await client.get(f"/users/{subject.id}", headers=viewer.headers), 200
        )["vehicle"]
        assert vehicle["make"] == DEFAULT_VEHICLE["make"]
        assert vehicle["model"] == DEFAULT_VEHICLE["model"]
        assert vehicle["color"] == DEFAULT_VEHICLE["color"]
        assert_absent(vehicle, "plate")

    async def test_plate_is_hidden_from_the_owner_here_too(self, client, users) -> None:
        subject = await users.create_driver()
        vehicle = expect_status(
            await client.get(f"/users/{subject.id}", headers=subject.headers), 200
        )["vehicle"]
        assert_absent(vehicle, "plate")

    async def test_no_vehicle_is_null(self, client, users) -> None:
        subject = await users.create()
        viewer = await users.create()
        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert body["vehicle"] is None


class TestPermissionsAndLookup:
    async def test_unknown_user(self, client, user) -> None:
        expect_error(await client.get("/users/999999", headers=user.headers), 404, "NOT_FOUND")

    async def test_requires_authentication(self, client, users) -> None:
        subject = await users.create()
        expect_error(await client.get(f"/users/{subject.id}"), 401, "UNAUTHENTICATED")

    async def test_requires_onboarding(self, client, users) -> None:
        subject = await users.create()
        response = await client.get(f"/users/{subject.id}", headers=users.stranger_headers())
        expect_error(response, 403, "ONBOARDING_REQUIRED")

    async def test_deactivated_caller_is_refused(self, client, users) -> None:
        subject = await users.create()
        viewer = await users.create()
        await users.deactivate(viewer)
        response = await client.get(f"/users/{subject.id}", headers=viewer.headers)
        expect_error(response, 403, "ACCOUNT_DEACTIVATED")

    async def test_deactivated_subject_is_still_visible(self, client, users) -> None:
        """Their rides and ratings stay for history, so the profile has to resolve."""
        subject = await users.create()
        viewer = await users.create()
        await users.deactivate(subject)
        body = expect_status(await client.get(f"/users/{subject.id}", headers=viewer.headers), 200)
        assert body["id"] == subject.id

    async def test_non_numeric_id(self, client, user) -> None:
        response = await client.get("/users/not-an-id", headers=user.headers)
        assert response.status_code in (404, 422), (
            f"expected 404 or 422 for a non-integer id, got {response.status_code}"
        )
