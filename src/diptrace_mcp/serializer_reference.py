from __future__ import annotations

import copy
import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

_REFERENCE_SCHEMA_VERSION = "diptrace-serializer-reference-v1"
_REFERENCE_RESOURCE = "data/serializer_reference.json"


@lru_cache(maxsize=1)
def _load_reference_cached() -> dict[str, Any]:
    package_root = files("diptrace_mcp")
    payload = json.loads(package_root.joinpath(_REFERENCE_RESOURCE).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("serializer reference root must be an object")
    if payload.get("schema_version") != _REFERENCE_SCHEMA_VERSION:
        raise RuntimeError("unsupported serializer reference schema version")
    trust = payload.get("trust")
    if not isinstance(trust, dict) or trust.get("trust_effect") != "none":
        raise RuntimeError("serializer reference must remain reference-only")
    if trust.get("may_grant_roundtrip_trust") is not False:
        raise RuntimeError("serializer reference may not grant round-trip trust")
    _index(payload, "rules")
    _index(payload, "cross_cutting_behaviors")
    return payload


def _index(payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    records = payload.get(key)
    if not isinstance(records, list):
        raise RuntimeError(f"serializer reference {key} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(f"serializer reference {key} entries must be objects")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError(f"serializer reference {key} entry has no id")
        if identifier in result:
            raise RuntimeError(f"duplicate serializer reference id: {identifier}")
        result[identifier] = record
    return result


def load_serializer_reference() -> dict[str, Any]:
    """Return an isolated copy of the bundled reference-only serializer knowledge."""

    return copy.deepcopy(_load_reference_cached())


def serializer_rule(rule_id: str) -> dict[str, Any]:
    """Return one machine-readable serializer rule by stable rule id."""

    rules = _index(_load_reference_cached(), "rules")
    try:
        return copy.deepcopy(rules[rule_id])
    except KeyError as exc:
        raise KeyError(f"unknown serializer rule: {rule_id}") from exc


def serializer_behavior(behavior_id: str) -> dict[str, Any]:
    """Return one cross-cutting serializer/import behavior by stable id."""

    behaviors = _index(_load_reference_cached(), "cross_cutting_behaviors")
    try:
        return copy.deepcopy(behaviors[behavior_id])
    except KeyError as exc:
        raise KeyError(f"unknown serializer behavior: {behavior_id}") from exc


def serializer_enum(rule_id: str) -> tuple[str, ...]:
    """Return the documented value set for an enum/literal rule."""

    rule = serializer_rule(rule_id)
    values = rule.get("values")
    if not isinstance(values, list):
        raise ValueError(f"serializer rule {rule_id!r} has no value set")
    return tuple(str(value) for value in values)


def serializer_accepts(rule_id: str, value: str) -> bool:
    """Check a value against a documented enum/literal set."""

    return value in serializer_enum(rule_id)
