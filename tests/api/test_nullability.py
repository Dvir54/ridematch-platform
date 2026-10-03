"""Every request field, checked against the nullability `openapi.yaml` declares.

The field list comes from the spec, not from this file: `support.nullability`
walks each request schema and reports which fields admit an explicit null. Each
one is then sent as null and the implementation has to agree with the contract -
a 422 naming the field where the schema gives no `"null"`, and a success where it
does.

Why it is generated rather than written out: @backend swept the ride and user
schemas by eye for contract 0.4.3 and missed `RideCreate.preferences`, which
shipped accepting a null that `PATCH` already refused. Both of us had also
enumerated fields by hand on our own side and neither list caught it. Reading
the spec covers the fields nobody has thought about yet, and keeps covering them
as the contract grows (suggested by @backend 2026-10-02).

The sample bodies below are the one hand-written part, and `test_every_field_has
_a_sample` makes that safe: a field added to the contract without a sample here
fails loudly instead of going unchecked. Each sample is a *complete*, valid body,
so nulling one field leaves every sibling valid and a 422 can only be about the
null - not about a missing required field next to it.
"""

from __future__ import annotations

import pytest

from support import clock
from support.assertions import expect_status, expect_validation_error
from support.factories import DEFAULT_VEHICLE, onboarding_payload
from support.nullability import Field, assert_depth_is_covered, fields_of, set_at
from support.rides import ride_payload

FULL_PREFERENCES = {
    "default_mode": "driver",
    "smoking": True,
    "pets": True,
    "notifications": {"email": True, "push": False, "websocket": True},
    "language": "en",
    "theme": "dark",
}
FULL_RIDE_PREFERENCES = {"smoking": True, "pets": True, "music": False, "gender_only": False}


def full_onboarding() -> dict:
    return onboarding_payload(
        gender="female",
        preferences=dict(FULL_PREFERENCES),
        vehicle=dict(DEFAULT_VEHICLE),
    )


def full_user_update() -> dict:
    return {
        "name": "Dana Cohen",
        "gender": "female",
        "preferences": dict(FULL_PREFERENCES),
        "vehicle": dict(DEFAULT_VEHICLE),
    }


def full_ride_create() -> dict:
    return ride_payload(notes="Two bags max", preferences=dict(FULL_RIDE_PREFERENCES))


def full_ride_update() -> dict:
    return {
        **ride_payload(departure_in=48),
        "notes": "Changed",
        "preferences": dict(FULL_RIDE_PREFERENCES),
    }


# schema name -> a complete, valid body for it
SAMPLES = {
    "OnboardingRequest": full_onboarding,
    "UserUpdate": full_user_update,
    "RideCreate": full_ride_create,
    "RideUpdate": full_ride_update,
    "RideRequestCreate": lambda: {"seats_requested": 1},
}

SCHEMAS = sorted(SAMPLES)


def cases(schema: str) -> list:
    """One parametrised case per field, labelled with its dotted path."""
    return [pytest.param(field, id=field.dotted) for field in fields_of(schema)]


class TestTheSpecIsReadable:
    """If these fail, the generated cases below are testing the wrong thing."""

    @pytest.mark.parametrize("schema", SCHEMAS)
    async def test_the_contract_nests_no_deeper_than_we_walk(self, schema: str) -> None:
        assert_depth_is_covered(schema)

    @pytest.mark.parametrize("schema", SCHEMAS)
    async def test_every_field_has_a_sample(self, schema: str) -> None:
        """A field added to the contract must appear in the sample body above,
        or nulling it would leave a sibling missing and the resulting 422 would
        prove nothing. This is the guard that keeps the hand-written half honest.
        """
        sample = SAMPLES[schema]()
        missing = sorted(
            field.dotted
            for field in fields_of(schema)
            if len(field.path) == 1 and field.name not in sample
        )
        assert not missing, (
            f"{schema} has fields with no value in the sample body: {missing}. "
            f"Add them to SAMPLES in this file so their nulls are checked against "
            f"valid siblings."
        )

    async def test_the_known_nullable_fields_are_found(self) -> None:
        """A sanity check on the reader itself: the four nulls the contract
        grants are the four it should report, so a reader that quietly returned
        'nothing is nullable' could not make this file pass vacuously."""
        granted = {
            ("UserUpdate", "gender"),
            ("UserUpdate", "vehicle"),
            ("UserUpdate", "preferences.default_mode"),
            ("RideUpdate", "notes"),
        }
        found = {
            (schema, field.dotted)
            for schema in SCHEMAS
            for field in fields_of(schema)
            if field.nullable
        }
        assert granted <= found, f"the reader lost a documented null: {granted - found}"


class TestOnboarding:
    @pytest.mark.parametrize("field", cases("OnboardingRequest"))
    async def test_null(self, users, field: Field) -> None:
        body = set_at(full_onboarding(), field.path, None)
        response = await users.onboard_response(**body)

        if field.nullable:
            expect_status(response, 201)
        else:
            expect_validation_error(response, field=field.name)


class TestPatchMe:
    @pytest.mark.parametrize("field", cases("UserUpdate"))
    async def test_null(self, client, user, field: Field) -> None:
        body = set_at(full_user_update(), field.path, None)
        response = await client.patch("/users/me", json=body, headers=user.headers)

        if field.nullable:
            expect_status(response, 200)
        else:
            expect_validation_error(response, field=field.name)


class TestCreateRide:
    @pytest.mark.parametrize("field", cases("RideCreate"))
    async def test_null(self, client, driver, field: Field) -> None:
        body = set_at(full_ride_create(), field.path, None)
        response = await client.post("/rides", json=body, headers=driver.headers)

        if field.nullable:
            expect_status(response, 201)
        else:
            expect_validation_error(response, field=field.name)


class TestPatchRide:
    @pytest.mark.parametrize("field", cases("RideUpdate"))
    async def test_null(self, rides, offer, field: Field) -> None:
        body = set_at(full_ride_update(), field.path, None)
        response = await rides.patch(offer, body)

        if field.nullable:
            expect_status(response, 200)
        else:
            expect_validation_error(response, field=field.name)


class TestCreateRequest:
    @pytest.mark.parametrize("field", cases("RideRequestCreate"))
    async def test_null(self, offer, requests, passenger, field: Field) -> None:
        body = set_at({"seats_requested": 1}, field.path, None)
        response = await requests.create_response(offer, passenger, body=body)

        if field.nullable:
            expect_status(response, 201)
        else:
            expect_validation_error(response, field=field.name)


class TestTheSamplesThemselvesAreValid:
    """Each sample body must be accepted as it stands. Otherwise a 422 in the
    tests above could come from the sample rather than from the null, and every
    'not nullable' case would pass for the wrong reason."""

    async def test_onboarding(self, users) -> None:
        expect_status(await users.onboard_response(**full_onboarding()), 201)

    async def test_patch_me(self, client, user) -> None:
        expect_status(
            await client.patch("/users/me", json=full_user_update(), headers=user.headers), 200
        )

    async def test_create_ride(self, client, driver) -> None:
        expect_status(
            await client.post("/rides", json=full_ride_create(), headers=driver.headers), 201
        )

    async def test_patch_ride(self, rides, offer) -> None:
        expect_status(await rides.patch(offer, full_ride_update()), 200)

    async def test_create_request(self, offer, requests, passenger) -> None:
        expect_status(
            await requests.create_response(offer, passenger, body={"seats_requested": 1}), 201
        )

    async def test_the_ride_update_sample_stays_in_the_future(self) -> None:
        """`full_ride_update` carries a departure_time, which D19 says must still
        be in the future - a stale constant here would make every PATCH case 422
        for the wrong reason."""
        assert clock.parse(full_ride_update()["departure_time"]) > clock.now()
