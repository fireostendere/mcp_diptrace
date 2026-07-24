from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

_REFERENCE_PACKAGE = "diptrace_mcp"
_REFERENCE_RESOURCE = "data/serializer_reference.json"


@lru_cache(maxsize=1)
def load_serializer_reference() -> dict[str, Any]:
    """Load the bundled serializer-derived reference.

    This data is reference-only: it constrains parser/writer behavior but is not
    DipTrace round-trip evidence and must never raise document provenance/trust.
    """

    text = (
        resources.files(_REFERENCE_PACKAGE)
        .joinpath(_REFERENCE_RESOURCE)
        .read_text(encoding="utf-8")
    )
    value = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError("serializer reference root must be an object")
    if value.get("trust_effect") != "none":
        raise RuntimeError("serializer reference must remain reference-only")
    return value


def serializer_rule(rule_id: str) -> dict[str, Any]:
    """Return one named attribute/element rule."""

    for rule in load_serializer_reference().get("rules", []):
        if isinstance(rule, dict) and rule.get("id") == rule_id:
            return rule
    raise KeyError(f"Unknown serializer reference rule: {rule_id}")


def serializer_behavior(behavior_id: str) -> dict[str, Any]:
    """Return one cross-cutting import/format behavior."""

    for behavior in load_serializer_reference().get("behaviors", []):
        if isinstance(behavior, dict) and behavior.get("id") == behavior_id:
            return behavior
    raise KeyError(f"Unknown serializer reference behavior: {behavior_id}")


def serializer_enum(rule_id: str) -> tuple[str, ...]:
    """Return the documented enum values for a rule."""

    values = serializer_rule(rule_id).get("enum_values", [])
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise RuntimeError(f"Invalid enum metadata for serializer rule {rule_id!r}")
    return tuple(values)


def serializer_allows(rule_id: str, value: str) -> bool:
    """Check a value against a documented enum without treating the reference as runtime trust."""

    values = serializer_enum(rule_id)
    return not values or value in values


def serializer_reference_provenance() -> dict[str, Any]:
    """Return bounded provenance metadata for diagnostics and tests."""

    reference = load_serializer_reference()
    return {
        "reference_id": reference.get("reference_id"),
        "reference_kind": reference.get("reference_kind"),
        "authority": reference.get("authority"),
        "trust_effect": reference.get("trust_effect"),
        "serializer_revision": reference.get("serializer_revision"),
        "claimed_generated_date": reference.get("claimed_generated_date"),
        "source_documents": reference.get("source_documents", []),
    }
