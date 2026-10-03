"""Which request fields `openapi.yaml` declares nullable, read from the spec.

A null is only legal where the schema says `"null"`, and CONTRACT.md §4 gives
the reason the rest must refuse it: a PATCH is a shallow merge where "an absent
key is left alone", so a null cannot also mean "leave alone" - there would be no
way left to say either one. The places the contract *does* grant it
(`gender`, `vehicle`, `preferences.default_mode`, plus `notes` on a
ride) are its only way to clear a value.

Enumerating those by hand is what failed: @backend swept the schemas by eye for
0.4.3 and missed `RideCreate.preferences`, which shipped accepting a null that
`PATCH` correctly refused. Reading the field list out of the spec instead means
the test covers fields nobody has thought about yet and stays right as the
contract grows - and a new field that is nullable in the implementation but not
in the contract fails here rather than in a client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract import validator

# Object schemas whose fields are checked one level down as well. The contract
# nests exactly this far, and the depth is asserted by `assert_depth_is_covered`
# below rather than assumed.
MAX_DEPTH = 3


@dataclass(frozen=True)
class Field:
    """One writable leaf (or object) in a request body, and whether the contract
    lets it be null."""

    path: tuple[str, ...]
    nullable: bool

    @property
    def dotted(self) -> str:
        return ".".join(self.path)

    @property
    def name(self) -> str:
        return self.path[-1]

    def __str__(self) -> str:  # pragma: no cover - test ids only
        return self.dotted


def _is_nullable(schema: dict[str, Any]) -> bool:
    """True when the schema admits an explicit JSON null.

    openapi 3.1 spells this two ways, and the contract uses both: `type:
    [string, "null"]` for a plain field, and `oneOf: [{$ref: ...}, {type:
    "null"}]` where the non-null half is a named schema.
    """
    declared = schema.get("type")
    if declared == "null":
        return True
    if isinstance(declared, list) and "null" in declared:
        return True
    for key in ("oneOf", "anyOf"):
        for branch in schema.get(key, ()):
            if isinstance(branch, dict) and _is_nullable(branch):
                return True
    return False


def _object_properties(schema: dict[str, Any]) -> dict[str, Any] | None:
    """The `properties` of an object schema, looking through a nullable wrapper.

    `vehicle` is `oneOf: [Vehicle, null]`: the field itself takes a null, and its
    sub-fields still have to be checked, so the Vehicle branch is what we walk.
    """
    if isinstance(schema.get("properties"), dict):
        return schema["properties"]
    for key in ("oneOf", "anyOf"):
        for branch in schema.get(key, ()):
            if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
                return branch["properties"]
    return None


def fields_of(schema_name: str) -> list[Field]:
    """Every writable field of a request schema, nested paths included."""
    spec = validator()
    resolved = spec.resolve_schema_by_name(schema_name)
    found: list[Field] = []

    def walk(schema: dict[str, Any], prefix: tuple[str, ...]) -> None:
        properties = _object_properties(schema)
        if not properties:
            return
        for name, raw in properties.items():
            path = (*prefix, name)
            found.append(Field(path=path, nullable=_is_nullable(raw)))
            if len(path) < MAX_DEPTH:
                walk(raw, path)

    walk(resolved, ())
    assert found, f"{schema_name} declares no properties - is the name right?"
    return found


def assert_depth_is_covered(schema_name: str) -> None:
    """Fail if the contract has grown an object below MAX_DEPTH.

    Without this the walk would silently stop covering a newly nested field,
    which is the same by-hand blind spot this module exists to remove.
    """
    spec = validator()
    resolved = spec.resolve_schema_by_name(schema_name)

    def deepest(schema: dict[str, Any], depth: int = 0) -> int:
        properties = _object_properties(schema)
        if not properties:
            return depth
        return max(deepest(raw, depth + 1) for raw in properties.values())

    actual = deepest(resolved)
    assert actual <= MAX_DEPTH, (
        f"{schema_name} nests {actual} levels deep but support.nullability walks "
        f"{MAX_DEPTH}. Raise MAX_DEPTH so the new level is covered."
    )


def set_at(payload: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    """A copy of `payload` with `path` set to `value`, creating objects as needed.

    Copies at every level it descends, so a baseline payload shared between
    parametrised cases cannot be mutated by one of them.
    """
    if not path:
        raise ValueError("path must not be empty")
    head, *rest = path
    updated = dict(payload)
    if rest:
        branch = updated.get(head)
        updated[head] = set_at(branch if isinstance(branch, dict) else {}, tuple(rest), value)
    else:
        updated[head] = value
    return updated
