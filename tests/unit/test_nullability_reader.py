"""The nullability reader itself (support/nullability.py). No backend needed.

api/test_nullability.py generates its cases from this module, so a reader that
quietly mis-read the spec would turn 69 real assertions into 69 vacuous ones.
These tests pin the two spellings openapi 3.1 allows, the nullable-wrapper case,
and the copy-on-write behaviour of `set_at`.
"""

from __future__ import annotations

import pytest

from support.nullability import (
    MAX_DEPTH,
    Field,
    _is_nullable,
    _object_properties,
    fields_of,
    set_at,
)


class TestIsNullable:
    @pytest.mark.parametrize(
        "schema",
        [
            {"type": ["string", "null"]},
            {"type": ["null", "integer"]},
            {"type": "null"},
            {"oneOf": [{"type": "string"}, {"type": "null"}]},
            {"anyOf": [{"type": "null"}, {"type": "object"}]},
            # The shape the contract actually uses for vehicle and gender.
            {"oneOf": [{"type": "object", "properties": {}}, {"type": "null"}]},
        ],
    )
    def test_nullable_spellings(self, schema: dict) -> None:
        assert _is_nullable(schema) is True

    @pytest.mark.parametrize(
        "schema",
        [
            {"type": "string"},
            {"type": "boolean"},
            {"type": ["string", "integer"]},
            {"oneOf": [{"type": "string"}, {"type": "integer"}]},
            {"type": "object", "properties": {"a": {"type": ["string", "null"]}}},
            {},
        ],
    )
    def test_non_nullable_spellings(self, schema: dict) -> None:
        """The last object case matters: a nullable *child* must not make the
        parent nullable, or the walk would excuse the parent from its 422."""
        assert _is_nullable(schema) is False


class TestObjectProperties:
    def test_a_plain_object(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        assert _object_properties(schema) == {"a": {"type": "string"}}

    def test_looks_through_a_nullable_wrapper(self) -> None:
        """`vehicle` is `oneOf: [Vehicle, null]`: the field takes a null and its
        sub-fields still have to be walked."""
        schema = {
            "oneOf": [
                {"type": "object", "properties": {"plate": {"type": "string"}}},
                {"type": "null"},
            ]
        }
        assert _object_properties(schema) == {"plate": {"type": "string"}}

    def test_a_leaf_has_none(self) -> None:
        assert _object_properties({"type": "string"}) is None


class TestFieldsOf:
    def test_reads_the_real_contract(self) -> None:
        fields = {field.dotted: field.nullable for field in fields_of("UserUpdate")}

        assert fields["phone"] is True
        assert fields["gender"] is True
        assert fields["vehicle"] is True
        assert fields["preferences.default_mode"] is True

        assert fields["name"] is False
        assert fields["preferences"] is False
        assert fields["preferences.smoking"] is False
        assert fields["vehicle.plate"] is False, (
            "a nullable vehicle must not make its sub-fields nullable"
        )
        assert fields["preferences.notifications.email"] is False

    def test_ride_create_preferences_is_not_nullable(self) -> None:
        """The field whose missing 422 was the FAIL of 2026-10-02. If the reader
        ever calls this nullable, the generated case flips to expecting a 201 and
        the regression walks straight back in."""
        fields = {field.dotted: field.nullable for field in fields_of("RideCreate")}
        assert fields["preferences"] is False
        assert fields["notes"] is True, "notes is the one nullable field on a ride body"

    def test_nesting_is_reported_as_paths(self) -> None:
        paths = {field.path for field in fields_of("UserUpdate")}
        assert ("preferences", "notifications", "email") in paths
        assert all(len(path) <= MAX_DEPTH for path in paths)

    def test_an_unknown_schema_is_an_error(self) -> None:
        with pytest.raises(AssertionError):
            fields_of("NoSuchSchema")


class TestSetAt:
    def test_a_top_level_field(self) -> None:
        assert set_at({"a": 1}, ("a",), None) == {"a": None}

    def test_a_nested_field_keeps_its_siblings(self) -> None:
        payload = {"preferences": {"smoking": True, "pets": False}}
        assert set_at(payload, ("preferences", "pets"), None) == {
            "preferences": {"smoking": True, "pets": None}
        }

    def test_the_original_is_untouched(self) -> None:
        """Parametrised cases share one baseline, so a leak would make the order
        of the cases matter."""
        payload = {"preferences": {"notifications": {"email": True}}}
        set_at(payload, ("preferences", "notifications", "email"), None)
        assert payload == {"preferences": {"notifications": {"email": True}}}

    def test_it_creates_missing_levels(self) -> None:
        assert set_at({}, ("preferences", "theme"), None) == {"preferences": {"theme": None}}

    def test_an_empty_path_is_refused(self) -> None:
        with pytest.raises(ValueError):
            set_at({}, (), None)


class TestField:
    def test_dotted_and_name(self) -> None:
        field = Field(path=("preferences", "notifications", "email"), nullable=False)
        assert field.dotted == "preferences.notifications.email"
        assert field.name == "email"
