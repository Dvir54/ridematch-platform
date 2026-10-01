"""The token signer and clock helpers, checked without the backend."""

from __future__ import annotations

import re
from datetime import date

import jwt
import pytest

from support import clock, env
from support.factories import INVALID_PHONES, OMIT, VALID_PHONES, onboarding_payload
from support.keys import KeyPair, TokenSigner, auth_header


@pytest.fixture(scope="module")
def pair() -> KeyPair:
    return KeyPair.generate()


@pytest.fixture(scope="module")
def signer(pair: KeyPair) -> TokenSigner:
    return TokenSigner(pair.private_pem)


def decode(token: str, pair: KeyPair, **kwargs):
    return jwt.decode(
        token,
        pair.public_pem,
        algorithms=["RS256"],
        issuer=env.CLERK_ISSUER,
        options={"verify_aud": False},
        **kwargs,
    )


class TestTokenSigner:
    def test_claims_match_what_clerk_sends(self, signer: TokenSigner, pair: KeyPair) -> None:
        claims = decode(signer.sign(sub="user_abc", email="a@b.test"), pair)
        assert claims["sub"] == "user_abc"
        assert claims["email"] == "a@b.test"
        assert claims["iss"] == env.CLERK_ISSUER
        assert claims["azp"] == env.CLERK_AUTHORIZED_PARTY
        assert claims["nbf"] <= claims["iat"] < claims["exp"]

    def test_header_carries_an_rs256_kid(self, signer: TokenSigner) -> None:
        header = jwt.get_unverified_header(signer.sign(sub="user_abc"))
        assert header["alg"] == "RS256"
        assert header["kid"]

    def test_expired_token(self, signer: TokenSigner, pair: KeyPair) -> None:
        token = signer.sign(sub="user_abc", expires_in=-60)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode(token, pair)

    def test_not_yet_valid_token(self, signer: TokenSigner, pair: KeyPair) -> None:
        token = signer.sign(sub="user_abc", not_before=600, expires_in=1200)
        with pytest.raises(jwt.ImmatureSignatureError):
            decode(token, pair)

    def test_overridable_issuer_and_azp(self, signer: TokenSigner, pair: KeyPair) -> None:
        token = signer.sign(sub="user_abc", issuer="https://evil.test", azp="https://evil.test")
        claims = jwt.decode(
            token, pair.public_pem, algorithms=["RS256"], options={"verify_aud": False}
        )
        assert claims["iss"] == "https://evil.test"
        assert claims["azp"] == "https://evil.test"

    def test_a_token_from_another_key_does_not_verify(self, pair: KeyPair) -> None:
        other = KeyPair.generate()
        token = TokenSigner(other.private_pem).sign(sub="user_abc")
        with pytest.raises(jwt.InvalidSignatureError):
            decode(token, pair)

    def test_dropping_a_claim(self, signer: TokenSigner, pair: KeyPair) -> None:
        claims = decode(signer.sign(sub="user_abc", drop_claims=("azp",)), pair)
        assert "azp" not in claims

    def test_auth_header(self, signer: TokenSigner) -> None:
        token = signer.sign(sub="user_abc")
        assert auth_header(token) == {"Authorization": f"Bearer {token}"}


class TestClock:
    def test_iso_uses_a_z_suffix(self) -> None:
        assert clock.iso(clock.now()).endswith("Z")

    def test_round_trip(self) -> None:
        moment = clock.now()
        assert clock.parse(clock.iso(moment)) == moment

    def test_birth_date_for_age(self) -> None:
        assert clock.birth_date_for_age(18, on=date(2026, 10, 1)) == date(2008, 10, 1)

    def test_birth_date_avoids_29_february(self) -> None:
        assert clock.birth_date_for_age(18, on=date(2024, 2, 29)) == date(2006, 2, 28)


class TestOnboardingPayload:
    def test_default_payload_is_complete(self) -> None:
        payload = onboarding_payload()
        assert payload.keys() == {"name", "date_of_birth", "accepted_terms"}
        assert payload["accepted_terms"] is True

    def test_overrides_and_omission(self) -> None:
        payload = onboarding_payload(name="Dana", accepted_terms=OMIT, gender="other")
        assert payload["name"] == "Dana"
        assert payload["gender"] == "other"
        assert "accepted_terms" not in payload


class TestEnvGuard:
    def test_refuses_a_non_test_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "TEST_DATABASE_URL", "postgresql+asyncpg://ridematch:ridematch@localhost:5434/ridematch"
        )
        with pytest.raises(RuntimeError, match="does not look like a test database"):
            env.apply("not-a-real-key")

    def test_asyncpg_dsn_drops_the_driver(self) -> None:
        assert env.asyncpg_dsn("postgresql+asyncpg://u:p@h:1/d") == "postgresql://u:p@h:1/d"


@pytest.fixture(scope="module")
def phone_pattern() -> re.Pattern:
    phone = _spec()["components"]["schemas"]["Phone"]
    assert phone["maxLength"] == 20
    return re.compile(phone["pattern"])


def _spec() -> dict:
    import yaml

    return yaml.safe_load(env.OPENAPI_PATH.read_text(encoding="utf-8"))


class TestPhoneSamples:
    """Keep VALID_PHONES / INVALID_PHONES honest against openapi.yaml itself.

    The sample lists drive both the onboarding and the PATCH phone tests. If a
    contract bump changes the pattern and nobody updates the lists, this fails
    straight away - without needing the backend or a database.
    """

    @pytest.mark.parametrize("phone", VALID_PHONES)
    def test_valid_samples_match_the_contract(self, phone_pattern: re.Pattern, phone: str) -> None:
        assert phone_pattern.fullmatch(phone), (
            f"{phone!r} is in VALID_PHONES but the pattern rejects it"
        )
        assert len(phone) <= 20

    @pytest.mark.parametrize("phone", list(INVALID_PHONES.values()), ids=list(INVALID_PHONES))
    def test_invalid_samples_are_rejected_by_the_contract(
        self, phone_pattern: re.Pattern, phone: str
    ) -> None:
        assert not phone_pattern.fullmatch(phone) or len(phone) > 20, (
            f"{phone!r} is in INVALID_PHONES but the contract accepts it"
        )

    def test_both_paths_reference_the_same_primitive(self) -> None:
        """D17: one Phone primitive, so the two paths cannot drift."""
        spec = _spec()
        onboarding = spec["components"]["schemas"]["OnboardingRequest"]["properties"]["phone"]
        update = spec["components"]["schemas"]["UserUpdate"]["properties"]["phone"]
        assert onboarding == update, (
            "OnboardingRequest.phone and UserUpdate.phone have diverged again"
        )
