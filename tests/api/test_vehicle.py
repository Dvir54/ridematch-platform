"""The vehicle on users.vehicle (CONTRACT.md 4 "Vehicles", D14; openapi Vehicle).

PATCH /users/me is a *full replace* of the vehicle: "It's set at onboarding
(optional) or with PATCH /users/me (full replace)."

The two rules that need a ride to exist - VEHICLE_REQUIRED when offering a ride
without one, and VEHICLE_REQUIRED when removing one while rides are open - land
in Phase 2 with the rides endpoints.
"""

from __future__ import annotations

import pytest

from support.assertions import expect_error, expect_status, expect_validation_error
from support.factories import DEFAULT_VEHICLE

ME = "/users/me"
OTHER_VEHICLE = {"make": "Mazda", "model": "3", "color": "Red", "plate": "98-765-43"}


def vehicle(**overrides):
    return {**DEFAULT_VEHICLE, **overrides}


class TestSetAndReplace:
    async def test_set_a_vehicle(self, client, user) -> None:
        response = await client.patch(ME, json={"vehicle": vehicle()}, headers=user.headers)
        body = expect_status(response, 200)
        assert body["vehicle"] == vehicle()

    async def test_patch_replaces_the_whole_vehicle(self, client, users) -> None:
        driver = await users.create_driver()
        response = await client.patch(ME, json={"vehicle": OTHER_VEHICLE}, headers=driver.headers)
        assert expect_status(response, 200)["vehicle"] == OTHER_VEHICLE

    async def test_a_partial_vehicle_is_rejected(self, client, users) -> None:
        """Full replace plus required fields: a partial object cannot be a merge."""
        driver = await users.create_driver()
        response = await client.patch(
            ME, json={"vehicle": {"color": "Blue"}}, headers=driver.headers
        )
        expect_error(response, 422, "VALIDATION_ERROR")

    async def test_vehicle_survives_an_unrelated_patch(self, client, users) -> None:
        driver = await users.create_driver()
        response = await client.patch(ME, json={"name": "Dana"}, headers=driver.headers)
        assert expect_status(response, 200)["vehicle"] == DEFAULT_VEHICLE

    async def test_vehicle_is_persisted(self, client, user) -> None:
        await client.patch(ME, json={"vehicle": vehicle()}, headers=user.headers)
        body = expect_status(await client.get(ME, headers=user.headers), 200)
        assert body["vehicle"] == vehicle()


class TestRemoval:
    async def test_null_removes_the_vehicle(self, client, users) -> None:
        """CONTRACT.md 4: null removes it. With no open rides that is allowed."""
        driver = await users.create_driver()
        response = await client.patch(ME, json={"vehicle": None}, headers=driver.headers)
        assert expect_status(response, 200)["vehicle"] is None
        assert expect_status(await client.get(ME, headers=driver.headers), 200)["vehicle"] is None


class TestFieldValidation:
    @pytest.mark.parametrize("missing", ["make", "model", "color", "plate"])
    async def test_every_field_is_required(self, client, user, missing: str) -> None:
        payload = vehicle()
        payload.pop(missing)
        response = await client.patch(ME, json={"vehicle": payload}, headers=user.headers)
        expect_validation_error(response, field=missing)

    @pytest.mark.parametrize("field", ["make", "model", "color", "plate"])
    async def test_empty_values_are_rejected(self, client, user, field: str) -> None:
        response = await client.patch(
            ME, json={"vehicle": vehicle(**{field: ""})}, headers=user.headers
        )
        expect_validation_error(response, field=field)

    @pytest.mark.parametrize(
        ("field", "limit"),
        [("make", 50), ("model", 50), ("color", 30), ("plate", 15)],
    )
    async def test_maximum_lengths(self, client, user, field: str, limit: int) -> None:
        at_limit = vehicle(**{field: "A" * limit})
        expect_status(await client.patch(ME, json={"vehicle": at_limit}, headers=user.headers), 200)

        over_limit = vehicle(**{field: "A" * (limit + 1)})
        response = await client.patch(ME, json={"vehicle": over_limit}, headers=user.headers)
        expect_validation_error(response, field=field)

    async def test_plate_minimum_length(self, client, user) -> None:
        response = await client.patch(
            ME, json={"vehicle": vehicle(plate="X")}, headers=user.headers
        )
        expect_validation_error(response, field="plate")

    async def test_unknown_vehicle_field_is_not_stored(self, client, user) -> None:
        response = await client.patch(
            ME, json={"vehicle": vehicle(year=2020)}, headers=user.headers
        )
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
            return
        assert expect_status(response, 200)["vehicle"] == vehicle()

    async def test_wrong_type_for_vehicle(self, client, user) -> None:
        response = await client.patch(ME, json={"vehicle": "a red car"}, headers=user.headers)
        expect_error(response, 422, "VALIDATION_ERROR")


class TestPlateNormalisation:
    async def test_plate_is_trimmed_and_uppercased(self, client, user) -> None:
        """openapi Vehicle.plate: "Stored as entered (trimmed, uppercased)."."""
        response = await client.patch(
            ME, json={"vehicle": vehicle(plate="  ab-123-cd  ")}, headers=user.headers
        )
        assert expect_status(response, 200)["vehicle"]["plate"] == "AB-123-CD"


class TestOnboardingVehicleValidation:
    @pytest.mark.parametrize("missing", ["make", "model", "color", "plate"])
    async def test_partial_vehicle_at_onboarding(self, client, users, missing: str) -> None:
        payload = vehicle()
        payload.pop(missing)
        expect_validation_error(await users.onboard_response(vehicle=payload), field=missing)

    async def test_plate_normalised_at_onboarding(self, client, users) -> None:
        response = await users.onboard_response(vehicle=vehicle(plate=" xy-99-zz "))
        assert expect_status(response, 201)["vehicle"]["plate"] == "XY-99-ZZ"


class TestPlatePrivacy:
    async def test_the_owner_sees_their_own_plate(self, client, users) -> None:
        driver = await users.create_driver()
        body = expect_status(await client.get(ME, headers=driver.headers), 200)
        assert body["vehicle"]["plate"] == DEFAULT_VEHICLE["plate"]

    async def test_nobody_else_sees_it_on_the_public_profile(self, client, users) -> None:
        driver = await users.create_driver()
        viewer = await users.create()
        body = expect_status(await client.get(f"/users/{driver.id}", headers=viewer.headers), 200)
        assert "plate" not in body["vehicle"]
