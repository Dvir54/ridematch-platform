"""POST /users/me/onboarding (CONTRACT.md 2, 4, 5 and D8/D11/D12).

The row is created here and nowhere else: no webhook, no lazy creation.
"""

from __future__ import annotations

from datetime import timedelta

from support import clock, env
from support.assertions import expect_error, expect_status, expect_validation_error
from support.factories import DEFAULT_VEHICLE, OMIT, onboarding_payload
from support.keys import auth_header

ONBOARDING = "/users/me/onboarding"


class TestHappyPath:
    async def test_creates_the_profile(self, client, users) -> None:
        sub, email = users.new_identity()
        body = expect_status(await users.onboard_response(clerk_user_id=sub, email=email), 201)

        assert body["email"] == email
        assert body["name"] == "Test User"
        assert body["is_admin"] is False
        assert body["is_active"] is True
        assert body["driver_rating"] is None
        assert body["driver_rating_count"] == 0
        assert body["passenger_rating"] is None
        assert body["passenger_rating_count"] == 0
        assert body["vehicle"] is None

    async def test_links_the_row_to_the_token_subject(self, client, users, db) -> None:
        sub, email = users.new_identity()
        body = expect_status(await users.onboard_response(clerk_user_id=sub, email=email), 201)
        assert (await db.user_row(body["id"]))["clerk_user_id"] == sub

    async def test_stores_the_terms_acceptance_time(self, client, users, db) -> None:
        """CONTRACT.md 4: terms_accepted_at is stored (NOT NULL in schema.sql)."""
        body = expect_status(await users.onboard_response(), 201)
        assert (await db.user_row(body["id"]))["terms_accepted_at"] is not None

    async def test_preferences_defaults_are_filled(self, client, users) -> None:
        prefs = expect_status(await users.onboard_response(), 201)["preferences"]
        assert prefs["default_mode"] is None, "null -> the client shows Role Selection"
        assert prefs["smoking"] is False
        assert prefs["pets"] is False
        assert prefs["language"] == "en"
        assert prefs["theme"] == "system"
        assert prefs["notifications"] == {"email": True, "push": True, "websocket": True}

    async def test_supplied_preferences_are_merged_over_the_defaults(self, client, users) -> None:
        response = await users.onboard_response(
            preferences={"default_mode": "driver", "theme": "dark"}
        )
        prefs = expect_status(response, 201)["preferences"]
        assert prefs["default_mode"] == "driver"
        assert prefs["theme"] == "dark"
        assert prefs["language"] == "en", "unset keys keep their default"
        assert prefs["notifications"]["email"] is True

    async def test_optional_fields(self, client, users) -> None:
        response = await users.onboard_response(phone="+972 50-123-4567", gender="female")
        body = expect_status(response, 201)
        assert body["phone"] == "+972 50-123-4567"
        assert body["gender"] == "female"

    async def test_profile_is_visible_immediately(self, client, users) -> None:
        user = await users.create()
        body = expect_status(await client.get("/users/me", headers=user.headers), 200)
        assert body["id"] == user.id


class TestEmailHandling:
    async def test_email_comes_from_the_token_not_the_body(self, client, users) -> None:
        """OnboardingRequest has no email field; the `email` claim is the source."""
        sub, email = users.new_identity()
        response = await client.post(
            ONBOARDING,
            json=onboarding_payload(email="someone.else@ridematch.test"),
            headers=auth_header(users.signer.sign(sub=sub, email=email)),
        )
        assert expect_status(response, 201)["email"] == email

    async def test_email_is_lowercased_and_trimmed(self, client, users) -> None:
        """CONTRACT.md 2: emails are lowercased and trimmed before storing."""
        sub, _ = users.new_identity()
        response = await users.onboard_response(
            clerk_user_id=sub, email="  Mixed.Case@RideMatch.TEST  "
        )
        assert expect_status(response, 201)["email"] == "mixed.case@ridematch.test"

    async def test_duplicate_email_from_another_clerk_user(self, client, users) -> None:
        first = await users.create()
        other_sub, _ = users.new_identity()
        response = await users.onboard_response(clerk_user_id=other_sub, email=first.email)
        expect_error(response, 409, "EMAIL_ALREADY_EXISTS")

    async def test_duplicate_email_differing_only_in_case(self, client, users) -> None:
        first = await users.create()
        other_sub, _ = users.new_identity()
        response = await users.onboard_response(clerk_user_id=other_sub, email=first.email.upper())
        expect_error(response, 409, "EMAIL_ALREADY_EXISTS")


class TestOnboardingTwice:
    async def test_second_call_conflicts(self, client, users) -> None:
        user = await users.create()
        response = await users.onboard_response(clerk_user_id=user.clerk_user_id, email=user.email)
        expect_error(response, 409, "ALREADY_ONBOARDED")

    async def test_second_call_does_not_change_the_profile(self, client, users, db) -> None:
        user = await users.create(name="Original")
        await users.onboard_response(
            clerk_user_id=user.clerk_user_id, email=user.email, name="Overwritten"
        )
        body = expect_status(await client.get("/users/me", headers=user.headers), 200)
        assert body["name"] == "Original"
        assert await db.count("users") == 1


class TestAgeAndTerms:
    async def test_exactly_eighteen_today_is_allowed(self, client, users) -> None:
        dob = clock.birth_date_for_age(18)
        expect_status(await users.onboard_response(date_of_birth=dob.isoformat()), 201)

    async def test_turning_eighteen_tomorrow_is_rejected(self, client, users) -> None:
        dob = clock.birth_date_for_age(18) + timedelta(days=1)
        response = await users.onboard_response(date_of_birth=dob.isoformat())
        expect_validation_error(response, "UNDERAGE")

    async def test_clearly_underage(self, client, users) -> None:
        dob = clock.birth_date_for_age(12)
        response = await users.onboard_response(date_of_birth=dob.isoformat())
        expect_validation_error(response, "UNDERAGE")

    async def test_terms_must_be_accepted(self, client, users) -> None:
        """CONTRACT.md 4/5: accepted_terms=false -> 422 TERMS_NOT_ACCEPTED."""
        response = await users.onboard_response(accepted_terms=False)
        expect_validation_error(response, "TERMS_NOT_ACCEPTED")

    async def test_missing_terms_is_a_validation_error(self, client, users) -> None:
        response = await users.onboard_response(accepted_terms=OMIT)
        expect_error(response, 422, "VALIDATION_ERROR")

    async def test_underage_user_has_no_row(self, client, users, db) -> None:
        dob = clock.birth_date_for_age(10)
        await users.onboard_response(date_of_birth=dob.isoformat())
        assert await db.count("users") == 0


class TestBodyValidation:
    async def test_missing_name(self, client, users) -> None:
        expect_validation_error(await users.onboard_response(name=OMIT), field="name")

    async def test_empty_name(self, client, users) -> None:
        expect_validation_error(await users.onboard_response(name=""), field="name")

    async def test_name_too_long(self, client, users) -> None:
        expect_validation_error(await users.onboard_response(name="x" * 101), field="name")

    async def test_missing_date_of_birth(self, client, users) -> None:
        """D8: date_of_birth is required; 18+ cannot be enforced without it."""
        response = await users.onboard_response(date_of_birth=OMIT)
        expect_validation_error(response, field="date_of_birth")

    async def test_malformed_date_of_birth(self, client, users) -> None:
        response = await users.onboard_response(date_of_birth="not-a-date")
        expect_validation_error(response, field="date_of_birth")

    async def test_invalid_gender(self, client, users) -> None:
        expect_validation_error(await users.onboard_response(gender="spaceship"), field="gender")

    async def test_malformed_phone(self, client, users) -> None:
        expect_validation_error(await users.onboard_response(phone="call me"), field="phone")

    async def test_invalid_preference_value(self, client, users) -> None:
        response = await users.onboard_response(preferences={"theme": "neon"})
        expect_error(response, 422, "VALIDATION_ERROR")


class TestPrivilegeEscalation:
    async def test_is_admin_in_the_body_is_ignored(self, client, users, db) -> None:
        """OnboardingRequest has no is_admin field, so it must not take effect."""
        response = await users.onboard_response(is_admin=True)
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
            return
        body = expect_status(response, 201)
        assert body["is_admin"] is False
        assert (await db.user_row(body["id"]))["is_admin"] is False

    async def test_is_active_in_the_body_is_ignored(self, client, users) -> None:
        response = await users.onboard_response(is_active=False)
        if response.status_code == 422:
            expect_error(response, 422, "VALIDATION_ERROR")
            return
        assert expect_status(response, 201)["is_active"] is True


class TestFirstAdminSeed:
    async def test_admin_email_becomes_admin_when_no_admin_exists(self, client, users) -> None:
        """CONTRACT.md 4: that is how the first admin comes to exist."""
        body = expect_status(await users.onboard_response(email=env.ADMIN_EMAIL), 201)
        assert body["is_admin"] is True

    async def test_admin_email_is_ordinary_once_an_admin_exists(self, client, users, db) -> None:
        existing = await users.create()
        await db.set_admin(existing.id, True)

        body = expect_status(await users.onboard_response(email=env.ADMIN_EMAIL), 201)
        assert body["is_admin"] is False, "only the first admin is seeded"

    async def test_other_emails_never_become_admin(self, client, users) -> None:
        body = expect_status(await users.onboard_response(email="someone@ridematch.test"), 201)
        assert body["is_admin"] is False

    async def test_admin_email_match_is_case_insensitive(self, client, users) -> None:
        body = expect_status(await users.onboard_response(email=env.ADMIN_EMAIL.upper()), 201)
        assert body["is_admin"] is True


class TestAuthentication:
    async def test_onboarding_requires_a_token(self, client) -> None:
        response = await client.post(ONBOARDING, json=onboarding_payload())
        expect_error(response, 401, "UNAUTHENTICATED")

    async def test_onboarding_rejects_an_invalid_token(self, client) -> None:
        response = await client.post(
            ONBOARDING, json=onboarding_payload(), headers=auth_header("not-a-jwt")
        )
        expect_error(response, 401, "UNAUTHENTICATED")


class TestVehicleAtOnboarding:
    async def test_vehicle_is_optional(self, client, users) -> None:
        assert expect_status(await users.onboard_response(), 201)["vehicle"] is None

    async def test_vehicle_can_be_set(self, client, users) -> None:
        body = expect_status(await users.onboard_response(vehicle=dict(DEFAULT_VEHICLE)), 201)
        assert body["vehicle"]["make"] == DEFAULT_VEHICLE["make"]
        assert body["vehicle"]["model"] == DEFAULT_VEHICLE["model"]
        assert body["vehicle"]["color"] == DEFAULT_VEHICLE["color"]

    async def test_explicit_null_vehicle(self, client, users) -> None:
        assert expect_status(await users.onboard_response(vehicle=None), 201)["vehicle"] is None
