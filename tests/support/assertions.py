"""Assertions every API test goes through.

The suite rule: "Every API test checks the status code, the error `code`
(for errors) and that the body validates against the spec schema." These
helpers make that one call, so no test can quietly skip the schema check.
"""

from __future__ import annotations

from typing import Any

from .contract import ContractError, validator


def _describe(response: Any) -> str:
    return f"{response.request.method} {response.request.url.path}"


def matches_contract(response: Any, *, strict: bool = True) -> Any:
    """Validate the body against openapi.yaml and return it."""
    return validator().validate_response(response, strict=strict)


def expect_status(response: Any, status: int, *, strict: bool = True) -> Any:
    assert response.status_code == status, (
        f"{_describe(response)}: expected {status}, got {response.status_code}\n"
        f"body: {response.text[:1000]}"
    )
    return matches_contract(response, strict=strict)


def expect_error(response: Any, status: int, code: str, *, strict: bool = True) -> Any:
    """Assert an error response: status, envelope shape and the stable `code`."""
    body = expect_status(response, status, strict=strict)
    assert isinstance(body, dict), f"{_describe(response)}: error body is not an object: {body!r}"
    assert body.get("code") == code, (
        f"{_describe(response)}: expected error code {code!r}, got {body.get('code')!r}\n"
        f"body: {body}"
    )
    message = body.get("message")
    assert isinstance(message, str) and message.strip(), (
        f"{_describe(response)}: error {code} has no human-readable message: {body}"
    )
    if status == 422:
        _assert_details_present(response, body)
    return body


def _assert_details_present(response: Any, body: dict[str, Any]) -> None:
    """CONTRACT.md §2 (0.4.6): every 422 carries `details` with at least one
    entry, whatever its `code` - the specific ones (UNDERAGE,
    TERMS_NOT_ACCEPTED, DEPARTURE_IN_PAST) as much as VALIDATION_ERROR.

    Checked here rather than per test, so that no 422 assertion anywhere can
    accept the shape that caused @frontend's silent onboarding form: the right
    code with nowhere to put the message. A response that carries the code and
    an empty `details` passes a code-only check while showing the user nothing.
    """
    details = body.get("details")
    assert isinstance(details, list) and details, (
        f"{_describe(response)}: 422 {body.get('code')!r} carries no `details`. "
        f"CONTRACT.md §2: every 422 has at least one entry, so a client always has "
        f"somewhere to put the message.\nbody: {body}"
    )
    for index, entry in enumerate(details):
        assert isinstance(entry, dict), f"{_describe(response)}: details[{index}] is not an object"
        for key in ("field", "message"):
            value = entry.get(key)
            assert isinstance(value, str) and value.strip(), (
                f"{_describe(response)}: details[{index}].{key} is empty: {entry!r}"
            )


def expect_validation_error(
    response: Any, code: str = "VALIDATION_ERROR", *, field: str | None = None
) -> Any:
    """A 422 with the given code, optionally mentioning a field in `details`."""
    body = expect_error(response, 422, code)
    if field is not None:
        details = body.get("details") or []
        fields = [entry.get("field") for entry in details]
        assert any(field == name or str(name).endswith(f".{field}") for name in fields), (
            f"{_describe(response)}: expected {field!r} in error details, got {fields}"
        )
    return body


def expect_no_content(response: Any) -> None:
    assert response.status_code == 204, (
        f"{_describe(response)}: expected 204, got {response.status_code}\n"
        f"body: {response.text[:1000]}"
    )
    assert not response.content, f"{_describe(response)}: 204 must have an empty body"


def assert_absent(body: dict[str, Any], *names: str) -> None:
    """Assert fields the contract does not grant the caller are not present."""
    leaked = [name for name in names if name in body]
    assert not leaked, f"response leaks fields the contract does not define here: {leaked}"


__all__ = [
    "ContractError",
    "assert_absent",
    "expect_error",
    "expect_no_content",
    "expect_status",
    "expect_validation_error",
    "matches_contract",
]
