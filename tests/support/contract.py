"""Validate responses against contracts/openapi.yaml.

Used by every API test, so that "the backend answered 200" is never confused
with "the backend answered what the contract promised".

Two things this does beyond plain schema validation:

* An undocumented status code is a failure. A 500 where the contract lists
  401/403/404 is a contract violation, not a passing test.
* Strict mode (the default) closes every object schema that declares
  `properties` and says nothing about `additionalProperties`. OpenAPI leaves
  objects open, which would let a backend leak an undeclared field through an
  otherwise "valid" response - a plate or an email in `UserPublic`, say.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from . import env

_PATH_PARAM = re.compile(r"^\{[^/{}]+\}$")


class ContractError(AssertionError):
    """A response does not match contracts/openapi.yaml."""


class ContractValidator:
    def __init__(self, spec_path: Path | None = None, api_prefix: str = env.API_PREFIX) -> None:
        self.spec_path = spec_path or env.OPENAPI_PATH
        self.api_prefix = api_prefix.rstrip("/")
        self.spec: dict[str, Any] = yaml.safe_load(self.spec_path.read_text(encoding="utf-8"))
        self._schema_cache: dict[tuple[str, str, int, bool], Any] = {}

    # -- $ref resolution ------------------------------------------------
    def _lookup(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            raise ContractError(f"Only local $refs are supported, got {ref!r}")
        node: Any = self.spec
        for raw in ref[2:].split("/"):
            node = node[raw.replace("~1", "/").replace("~0", "~")]
        return node

    def _resolve(self, node: Any, stack: tuple[str, ...] = ()) -> Any:
        """Inline every local $ref. The contract has no recursive schemas."""
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref in stack:
                    raise ContractError(f"Recursive $ref chain: {' -> '.join((*stack, ref))}")
                resolved = self._resolve(self._lookup(ref), (*stack, ref))
                siblings = {k: self._resolve(v, stack) for k, v in node.items() if k != "$ref"}
                if siblings and isinstance(resolved, dict):
                    return {**resolved, **siblings}
                return resolved
            return {k: self._resolve(v, stack) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve(item, stack) for item in node]
        return node

    # -- strict mode ----------------------------------------------------
    @classmethod
    def _close(cls, node: Any) -> Any:
        if isinstance(node, dict):
            closed = {k: cls._close(v) for k, v in node.items()}
            if "properties" in closed and not (
                {"additionalProperties", "patternProperties", "unevaluatedProperties"}
                & closed.keys()
            ):
                closed["additionalProperties"] = False
            return closed
        if isinstance(node, list):
            return [cls._close(item) for item in node]
        return node

    # -- spec navigation ------------------------------------------------
    def strip_prefix(self, path: str) -> str:
        if self.api_prefix and path.startswith(self.api_prefix):
            return path[len(self.api_prefix) :] or "/"
        return path

    def match_path(self, path: str) -> str:
        """Map a concrete request path onto its openapi.yaml template."""
        wanted = self.strip_prefix(path).rstrip("/") or "/"
        wanted_parts = wanted.split("/")
        for template in self.spec["paths"]:
            template_parts = (template.rstrip("/") or "/").split("/")
            if len(template_parts) != len(wanted_parts):
                continue
            if all(
                _PATH_PARAM.match(t) or t == w
                for t, w in zip(template_parts, wanted_parts, strict=True)
            ):
                return template
        raise ContractError(f"{path!r} does not match any path in {self.spec_path.name}")

    def resolve_schema_by_name(self, name: str) -> dict[str, Any]:
        """One schema from `components.schemas`, with every $ref inlined.

        Lets a test read a *request* schema, not only the response schemas
        `validate_response` handles - support.nullability uses it to take the
        field list from the contract instead of repeating it by hand.
        """
        schemas = self.spec.get("components", {}).get("schemas", {})
        if name not in schemas:
            raise ContractError(
                f"{self.spec_path.name} has no schema {name!r}. Known: {', '.join(sorted(schemas))}"
            )
        resolved = self._resolve(schemas[name])
        if not isinstance(resolved, dict):
            raise ContractError(f"schema {name!r} is not an object schema: {resolved!r}")
        return resolved

    def operation(self, method: str, path_template: str) -> dict[str, Any]:
        try:
            return self.spec["paths"][path_template][method.lower()]
        except KeyError:
            raise ContractError(
                f"{method.upper()} {path_template} is not defined in {self.spec_path.name}"
            ) from None

    def documented_statuses(self, method: str, path_template: str) -> list[str]:
        return sorted(self.operation(method, path_template).get("responses", {}))

    def response_schema(
        self, method: str, path: str, status: int, *, strict: bool = True
    ) -> Any | None:
        """The JSON schema for one response, or None when none is defined (204)."""
        template = self.match_path(path)
        key = (method.lower(), template, status, strict)
        if key in self._schema_cache:
            return self._schema_cache[key]

        responses = self.operation(method, template).get("responses", {})
        entry = responses.get(str(status))
        if entry is None:
            raise ContractError(
                f"{method.upper()} {template} returned {status}, which "
                f"{self.spec_path.name} does not document. Documented: "
                + ", ".join(self.documented_statuses(method, template))
            )

        content = self._resolve(entry).get("content") or {}
        media = content.get("application/json")
        schema = media.get("schema") if media else None
        if schema is not None and strict:
            schema = self._close(schema)
        self._schema_cache[key] = schema
        return schema

    # -- validation -----------------------------------------------------
    def validate(
        self, *, method: str, path: str, status: int, body: Any, strict: bool = True
    ) -> None:
        schema = self.response_schema(method, path, status, strict=strict)
        if schema is None:
            if body not in (None, "", b""):
                raise ContractError(
                    f"{method.upper()} {path} -> {status} defines no JSON body, "
                    f"but the response had one: {body!r}"
                )
            return

        validator_ = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator_.iter_errors(body), key=lambda e: list(e.absolute_path))
        if errors:
            raise ContractError(_format_errors(method, path, status, body, errors))

    def validate_response(self, response: Any, *, strict: bool = True) -> Any:
        """Validate an httpx.Response and return its decoded body."""
        if response.status_code == 204 or not response.content:
            body = None
        else:
            try:
                body = response.json()
            except ValueError as exc:
                raise ContractError(
                    f"{response.request.method} {response.request.url.path} -> "
                    f"{response.status_code} returned a non-JSON body: {response.text[:400]!r}"
                ) from exc

        self.validate(
            method=response.request.method,
            path=response.request.url.path,
            status=response.status_code,
            body=body,
            strict=strict,
        )
        return body


def _format_errors(method: str, path: str, status: int, body: Any, errors: list) -> str:
    lines = [f"{method.upper()} {path} -> {status} does not match openapi.yaml:"]
    for error in errors[:10]:
        where = "/".join(str(part) for part in error.absolute_path) or "<root>"
        lines.append(f"  at {where}: {error.message}")
    if len(errors) > 10:
        lines.append(f"  ... and {len(errors) - 10} more")
    lines.append("body: " + json.dumps(body, indent=2, default=str)[:2000])
    return "\n".join(lines)


@lru_cache(maxsize=1)
def validator() -> ContractValidator:
    return ContractValidator()
