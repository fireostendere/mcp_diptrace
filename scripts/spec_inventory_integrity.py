"""Integrity checks for the project-authored factual XML inventory."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA_VERSION = "diptrace-factual-inventory-v1"
MIN_ELEMENT_COUNT = 1
MIN_ATTRIBUTE_COUNT = 1
_XML_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FACT_FIELDS = frozenset(
    {
        "element",
        "attribute",
        "value_type",
        "observed_values",
        "source_kind",
        "source_files",
        "diptrace_version",
        "diptrace_build",
        "evidence_id",
        "confidence",
        "notes",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "file",
        "sha256",
        "size_bytes",
        "source_kind",
        "diptrace_version",
        "diptrace_build",
        "source_type",
        "evidence_id",
        "confidence",
        "redistribution_basis",
        "contains_third_party_design",
    }
)


def _fail(context: str, message: str) -> ValueError:
    return ValueError(f"{context}: {message}")


def _require_string(value: object, context: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise _fail(context, "expected a string")
    return value


def _require_digest(value: object, context: str) -> str:
    candidate = _require_string(value, context)
    if not _SHA256_RE.fullmatch(candidate):
        raise _fail(context, "expected lowercase SHA-256")
    return candidate


def validate_inventory(inventory: dict[str, Any], repository_root: Path) -> None:
    """Validate the schema, source hashes, and clean-room content policy."""

    if not isinstance(inventory, dict):
        raise _fail("inventory", "expected an object")
    required = {"schema_version", "generated_by", "source_policy", "sources", "facts", "elements"}
    if set(inventory) != required:
        raise _fail("inventory", f"expected fields {sorted(required)}")
    if inventory["schema_version"] != INVENTORY_SCHEMA_VERSION:
        raise _fail("inventory.schema_version", "unsupported schema version")
    if not isinstance(inventory["source_policy"], str) or "no pdf" not in inventory[
        "source_policy"
    ].casefold():
        raise _fail("inventory.source_policy", "must state the clean-room boundary")

    sources = inventory["sources"]
    if not isinstance(sources, list) or not sources:
        raise _fail("inventory.sources", "must contain at least one source")
    source_by_file: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        context = f"inventory.sources[{index}]"
        if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
            raise _fail(context, "has unexpected or missing fields")
        relative = _require_string(source["file"], f"{context}.file")
        if relative in source_by_file:
            raise _fail(context, "duplicate source file")
        if (
            relative.casefold().endswith((".pdf", ".pages.json"))
            or "extracted_text" in relative.casefold()
            or "/sources/" in f"/{relative.casefold()}"
        ):
            raise _fail(context, "source path is not a project-owned XML observation")
        source_path = (repository_root / relative).resolve()
        if repository_root.resolve() not in source_path.parents:
            raise _fail(context, "source escapes repository root")
        if not source_path.is_file() or source_path.suffix.casefold() != ".xml":
            raise _fail(context, "source XML file is missing")
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual != _require_digest(source["sha256"], f"{context}.sha256"):
            raise _fail(context, "source SHA-256 does not match")
        for field in ("diptrace_version", "diptrace_build", "source_type"):
            if source[field] is not None and not isinstance(source[field], str):
                raise _fail(f"{context}.{field}", "expected a string or null")
        if not isinstance(source["redistribution_basis"], str) or not source[
            "redistribution_basis"
        ].strip():
            raise _fail(f"{context}.redistribution_basis", "must be non-empty")
        if source["source_kind"] not in {"synthetic_fixture", "controlled_real_export"}:
            raise _fail(context, "unsupported source kind")
        if source["contains_third_party_design"] is not False:
            raise _fail(context, "third-party designs are not accepted")
        source_by_file[relative] = source

    facts = inventory["facts"]
    if not isinstance(facts, list) or not facts:
        raise _fail("inventory.facts", "must contain factual observations")
    seen_facts: set[tuple[str, str]] = set()
    for index, fact in enumerate(facts):
        context = f"inventory.facts[{index}]"
        if not isinstance(fact, dict) or set(fact) != _FACT_FIELDS:
            raise _fail(context, "has unexpected or missing fields")
        element = _require_string(fact["element"], f"{context}.element")
        attribute = _require_string(fact["attribute"], f"{context}.attribute")
        if not _XML_NAME_RE.fullmatch(element) or not _XML_NAME_RE.fullmatch(attribute):
            raise _fail(context, "element and attribute names must be XML names")
        identity = (element, attribute)
        if identity in seen_facts:
            raise _fail(context, "duplicate element/attribute fact")
        seen_facts.add(identity)
        values = fact["observed_values"]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise _fail(context, "observed_values must be strings")
        if values != sorted(set(values)):
            raise _fail(context, "observed_values must be sorted and unique")
        files = fact["source_files"]
        if not isinstance(files, list) or files != sorted(set(files)) or not files:
            raise _fail(context, "source_files must be sorted and unique")
        if any(file not in source_by_file for file in files):
            raise _fail(context, "fact references an unknown source file")
        if fact["source_kind"] not in {"synthetic_fixture", "controlled_real_export"}:
            raise _fail(context, "unsupported fact source kind")
        for field in ("diptrace_version", "diptrace_build"):
            if fact[field] is not None and not isinstance(fact[field], str):
                raise _fail(f"{context}.{field}", "expected a string or null")
        if fact["confidence"] not in {"synthetic", "observed"}:
            raise _fail(context, "unsupported confidence")
        if not isinstance(fact["notes"], str) or not fact["notes"].startswith(
            "Project-authored factual summary"
        ):
            raise _fail(context, "notes must be project-authored")
        forbidden = ("copyright", "license text", "according to", "documentation", "specification")
        if any(term in fact["notes"].casefold() for term in forbidden):
            raise _fail(context, "notes contain source-derived prose")

    elements = inventory["elements"]
    if not isinstance(elements, dict) or len(elements) < MIN_ELEMENT_COUNT:
        raise _fail("inventory.elements", "must contain observed XML elements")
    fact_elements = {element for element, _attribute in seen_facts}
    if not fact_elements <= set(elements):
        raise _fail("inventory.elements", "does not contain all fact element names")
    attribute_count = 0
    for element, value in elements.items():
        if not _XML_NAME_RE.fullmatch(element) or not isinstance(value, dict):
            raise _fail(f"inventory.elements.{element}", "invalid element record")
        if set(value) != {"attributes", "text_content", "children", "source_kind"}:
            raise _fail(f"inventory.elements.{element}", "unexpected fields")
        attributes = value["attributes"]
        if not isinstance(attributes, dict):
            raise _fail(f"inventory.elements.{element}.attributes", "expected an object")
        attribute_count += len(attributes)
        if value["text_content"] != []:
            raise _fail(f"inventory.elements.{element}.text_content", "must remain empty")
        if value["source_kind"] not in {"synthetic_fixture", "controlled_real_export"}:
            raise _fail(f"inventory.elements.{element}.source_kind", "unsupported source kind")
        for attribute, metadata in attributes.items():
            if not _XML_NAME_RE.fullmatch(attribute) or not isinstance(metadata, dict):
                raise _fail(f"inventory.elements.{element}.{attribute}", "invalid attribute")
            if set(metadata) != {"type", "observed_values"}:
                raise _fail(f"inventory.elements.{element}.{attribute}", "unexpected fields")
    if attribute_count < MIN_ATTRIBUTE_COUNT:
        raise _fail("inventory.elements", "must contain at least one observed attribute")
