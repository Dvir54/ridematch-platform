"""Clerk session-token verification (CONTRACT.md 2 and 5).

GET /users/me stands in for "any authenticated endpoint": it is the first call
the frontend makes after sign-in, and it exercises the whole dependency -
signature, exp/nbf, iss, azp, user lookup, is_active.

CONTRACT.md 2: "Any failure -> 401 UNAUTHENTICATED."
"""

from __future__ import annotations

import pytest

from support import env
from support.assertions import expect_error, expect_status
from support.keys import KeyPair, TokenSigner, auth_header, forge_hs256, forge_unsigned

ME = "/users/me"


class TestMissingOrMalformedHeader:
    async def test_no_authorization_header(self, client) -> None:
        expect_error(await client.get(ME), 401, "UNAUTHENTICATED")

    @pytest.mark.parametrize(
        "header",
        [
            "",
            "Bearer",
            "Bearer ",
            "token-without-a-scheme",
            "Basic dXNlcjpwYXNz",
            "Bearer not.a.jwt",
            "Bearer aaaa.bbbb",
        ],
        ids=[
            "empty",
            "scheme-only",
            "scheme-and-space",
            "no-scheme",
            "basic-auth",
            "not-a-jwt",
            "two-segments",
        ],
    )
    async def test_malformed_authorization_header(self, client, header: str) -> None:
        response = await client.get(ME, headers={"Authorization": header})
        expect_error(response, 401, "UNAUTHENTICATED")


class TestSignature:
    async def test_token_signed_with_another_key(self, client, other_keys: KeyPair, users) -> None:
        sub, email = users.new_identity()
        token = TokenSigner(other_keys.private_pem).sign(sub=sub, email=email)
        expect_error(await client.get(ME, headers=auth_header(token)), 401, "UNAUTHENTICATED")

    async def test_unsigned_alg_none_token(self, client, signer: TokenSigner, users) -> None:
        """A backend that trusts `alg: none` would let anyone in as anyone."""
        sub, email = users.new_identity()
        token = forge_unsigned(signer.claims(sub=sub, email=email))
        expect_error(await client.get(ME, headers=auth_header(token)), 401, "UNAUTHENTICATED")

    async def test_hs256_token_signed_with_the_public_key(
        self, client, signer: TokenSigner, keys: KeyPair, users
    ) -> None:
        """Algorithm confusion: RS256 must be pinned, not read from the header."""
        sub, email = users.new_identity()
        token = forge_hs256(signer.claims(sub=sub, email=email), keys.public_pem)
        expect_error(await client.get(ME, headers=auth_header(token)), 401, "UNAUTHENTICATED")


class TestExpiryAndNotBefore:
    async def test_expired_token(self, client, user) -> None:
        headers = user.headers_with(expires_in=-3600)
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_expired_just_past_the_leeway(self, client, user) -> None:
        headers = user.headers_with(expires_in=-(env.CLOCK_LEEWAY_SECONDS + 25))
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_expired_within_the_leeway_is_accepted(self, client, user) -> None:
        """CONTRACT.md 2: exp/nbf are checked with 5s leeway."""
        headers = user.headers_with(expires_in=-(env.CLOCK_LEEWAY_SECONDS - 3))
        expect_status(await client.get(ME, headers=headers), 200)

    async def test_not_yet_valid_token(self, client, user) -> None:
        headers = user.headers_with(not_before=600, expires_in=1200)
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_not_before_within_the_leeway_is_accepted(self, client, user) -> None:
        headers = user.headers_with(not_before=env.CLOCK_LEEWAY_SECONDS - 3)
        expect_status(await client.get(ME, headers=headers), 200)


class TestIssuerAndAuthorizedParty:
    async def test_wrong_issuer(self, client, user) -> None:
        headers = user.headers_with(issuer="https://clerk.attacker.test")
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_missing_issuer(self, client, user) -> None:
        headers = user.headers_with(drop_claims=("iss",))
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_wrong_authorized_party(self, client, user) -> None:
        headers = user.headers_with(azp="https://not-our-frontend.test")
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_missing_authorized_party(self, client, user) -> None:
        headers = user.headers_with(drop_claims=("azp",))
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_configured_authorized_party_is_accepted(self, client, user) -> None:
        headers = user.headers_with(azp=env.CLERK_AUTHORIZED_PARTY)
        expect_status(await client.get(ME, headers=headers), 200)


class TestUserLookup:
    async def test_valid_token_without_a_profile(self, client, users) -> None:
        """CONTRACT.md 2: no row for this clerk_user_id -> ONBOARDING_REQUIRED."""
        response = await client.get(ME, headers=users.stranger_headers())
        expect_error(response, 403, "ONBOARDING_REQUIRED")

    async def test_token_without_a_subject(self, client, users) -> None:
        headers = users.stranger_headers(drop_claims=("sub",))
        expect_error(await client.get(ME, headers=headers), 401, "UNAUTHENTICATED")

    async def test_deactivated_account(self, client, users, user) -> None:
        await users.deactivate(user)
        expect_error(await client.get(ME, headers=user.headers), 403, "ACCOUNT_DEACTIVATED")

    async def test_deactivated_account_beats_onboarding_required(self, client, users, user) -> None:
        """A deactivated user may not re-onboard their way back in."""
        await users.deactivate(user)
        response = await users.onboard_response(clerk_user_id=user.clerk_user_id, email=user.email)
        expect_error(response, 403, "ACCOUNT_DEACTIVATED")

    async def test_reactivated_account_works_again(self, client, users, user) -> None:
        await users.deactivate(user)
        await users.reactivate(user)
        expect_status(await client.get(ME, headers=user.headers), 200)

    async def test_a_valid_token_reaches_the_right_profile(self, client, users) -> None:
        first = await users.create(name="First")
        second = await users.create(name="Second")
        assert expect_status(await client.get(ME, headers=first.headers), 200)["id"] == first.id
        assert expect_status(await client.get(ME, headers=second.headers), 200)["id"] == second.id


class TestLastLogin:
    async def test_last_login_is_recorded(self, client, user) -> None:
        """CONTRACT.md 4: last_login_at is refreshed when it is over an hour old."""
        await client.get(ME, headers=user.headers)
        body = expect_status(await client.get(ME, headers=user.headers), 200)
        assert body["last_login_at"] is not None
