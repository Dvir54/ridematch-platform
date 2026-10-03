"""The contract validator is what every API test leans on, so it is tested too."""

from __future__ import annotations

import pytest

from support.contract import ContractError, ContractValidator

DEFAULT_PREFERENCES = {
    "default_mode": None,
    "smoking": False,
    "pets": False,
    "notifications": {"email": True, "push": True, "websocket": True},
    "language": "en",
    "theme": "system",
}

USER_ME = {
    "id": 1,
    "email": "rider@ridematch.test",
    "name": "Rider",
    "date_of_birth": "1995-04-01",
    "gender": "female",
    "is_admin": False,
    "is_active": True,
    "driver_rating": None,
    "driver_rating_count": 0,
    "passenger_rating": None,
    "passenger_rating_count": 0,
    "preferences": DEFAULT_PREFERENCES,
    "vehicle": None,
    "created_at": "2026-10-01T09:00:00Z",
    "last_login_at": None,
}

USER_PUBLIC = {
    "id": 2,
    "name": "Driver",
    "driver_rating": 4.5,
    "driver_rating_count": 2,
    "passenger_rating": None,
    "passenger_rating_count": 0,
    "vehicle": {"make": "Toyota", "model": "Corolla", "color": "White"},
    "created_at": "2026-09-01T09:00:00Z",
}


@pytest.fixture(scope="module")
def contract() -> ContractValidator:
    return ContractValidator()


class TestPathMatching:
    def test_literal_path(self, contract: ContractValidator) -> None:
        assert contract.match_path("/users/me") == "/users/me"

    def test_templated_path(self, contract: ContractValidator) -> None:
        assert contract.match_path("/users/42") == "/users/{user_id}"

    def test_api_prefix_is_stripped(self, contract: ContractValidator) -> None:
        assert contract.match_path("/api/v1/rides/7/requests") == "/rides/{ride_id}/requests"

    def test_literal_beats_nothing_and_unknown_path_is_an_error(
        self, contract: ContractValidator
    ) -> None:
        with pytest.raises(ContractError, match="does not match any path"):
            contract.match_path("/api/v1/not-a-real-endpoint")


class TestSchemaLookup:
    def test_refs_are_resolved(self, contract: ContractValidator) -> None:
        schema = contract.response_schema("get", "/users/me", 200)
        assert "id" in schema["properties"]
        assert schema["properties"]["preferences"]["properties"]["theme"]["enum"] == [
            "light",
            "dark",
            "system",
        ]

    def test_nested_refs_are_resolved(self, contract: ContractValidator) -> None:
        schema = contract.response_schema("get", "/rides/1", 200)
        driver = schema["properties"]["driver"]
        assert "name" in driver["properties"]
        assert "email" not in driver["properties"], "UserPublic must not expose email"

    def test_undocumented_status_is_a_contract_error(self, contract: ContractValidator) -> None:
        with pytest.raises(ContractError, match="does not document"):
            contract.response_schema("get", "/users/me", 500)

    def test_response_without_a_body_has_no_schema(self, contract: ContractValidator) -> None:
        assert contract.response_schema("post", "/notifications/read-all", 204) is None


class TestValidation:
    def test_valid_body_passes(self, contract: ContractValidator) -> None:
        contract.validate(method="get", path="/api/v1/users/me", status=200, body=USER_ME)

    def test_missing_required_field_fails(self, contract: ContractValidator) -> None:
        body = {k: v for k, v in USER_ME.items() if k != "is_admin"}
        with pytest.raises(ContractError, match="is_admin"):
            contract.validate(method="get", path="/api/v1/users/me", status=200, body=body)

    def test_wrong_type_fails(self, contract: ContractValidator) -> None:
        with pytest.raises(ContractError, match="id"):
            contract.validate(
                method="get", path="/api/v1/users/me", status=200, body={**USER_ME, "id": "1"}
            )

    def test_bad_timestamp_fails(self, contract: ContractValidator) -> None:
        with pytest.raises(ContractError, match="created_at"):
            contract.validate(
                method="get",
                path="/api/v1/users/me",
                status=200,
                body={**USER_ME, "created_at": "the first of October"},
            )

    def test_strict_mode_catches_a_leaked_field(self, contract: ContractValidator) -> None:
        """A backend returning UserMe where UserPublic is promised must fail."""
        leaky = {**USER_PUBLIC, "email": "driver@ridematch.test"}
        with pytest.raises(ContractError):
            contract.validate(method="get", path="/api/v1/users/2", status=200, body=leaky)

        contract.validate(
            method="get", path="/api/v1/users/2", status=200, body=leaky, strict=False
        )

    def test_strict_mode_catches_a_leaked_plate(self, contract: ContractValidator) -> None:
        leaky = {
            **USER_PUBLIC,
            "vehicle": {**USER_PUBLIC["vehicle"], "plate": "12-345-67"},
        }
        with pytest.raises(ContractError):
            contract.validate(method="get", path="/api/v1/users/2", status=200, body=leaky)

    def test_array_responses(self, contract: ContractValidator) -> None:
        contract.validate(method="get", path="/api/v1/rides/mine", status=200, body=[])

    def test_error_envelope(self, contract: ContractValidator) -> None:
        contract.validate(
            method="get",
            path="/api/v1/users/me",
            status=403,
            body={"code": "ONBOARDING_REQUIRED", "message": "Complete onboarding first"},
        )

    def test_error_envelope_requires_a_code(self, contract: ContractValidator) -> None:
        with pytest.raises(ContractError, match="code"):
            contract.validate(
                method="get", path="/api/v1/users/me", status=403, body={"detail": "nope"}
            )

    def test_validation_error_details(self, contract: ContractValidator) -> None:
        contract.validate(
            method="post",
            path="/api/v1/users/me/onboarding",
            status=422,
            body={
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": [{"field": "body.date_of_birth", "message": "required"}],
            },
        )

    def test_body_on_a_204_fails(self, contract: ContractValidator) -> None:
        with pytest.raises(ContractError, match="defines no JSON body"):
            contract.validate(
                method="post", path="/api/v1/notifications/read-all", status=204, body={"ok": True}
            )
