#!/usr/bin/env python3
"""Operator-assisted collection of reviewable DipTrace XML evidence candidates.

This collector intentionally stops at a quarantine/candidate boundary.  It does
not write into a fixture tree and cannot grant a DipTrace validation level.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import xml.parsers.expat as expat
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

STATE_SCHEMA = "diptrace-operator-capture-state-v1"
RECIPE_SCHEMA = "diptrace-capture-recipe-v1"
CANDIDATE_SCHEMA = "diptrace-capture-candidate-v1"
STORE_NAME = ".diptrace-capture"
STAGES = ("source", "open_save", "reexport")
SOURCE_TYPES = frozenset(
    {
        "DipTrace-PCB",
        "DipTrace-Schematic",
        "DipTrace-ComponentLibrary",
        "DipTrace-PatternLibrary",
    }
)
UNITS = frozenset({"mm", "inch", "mil"})
SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ITEM_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_XML_BYTES = 128 * 1024 * 1024
MAX_INPUT_ARTIFACTS = 32
MAX_INPUT_ARTIFACT_BYTES = 128 * 1024 * 1024
INPUT_ARTIFACT_KEYS = {"role", "name", "path", "sha256", "size_bytes"}
FORBIDDEN_XML_TEXT = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
FORBIDDEN_XML_BYTES = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
SECURE_DIR_FD_AVAILABLE = (
    os.name == "posix"
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and os.rename in os.supports_dir_fd
    and os.link in os.supports_dir_fd
)


class CaptureError(Exception):
    """A typed, user-correctable capture error."""

    def __init__(self, message: str, *, code: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


@dataclass(frozen=True)
class XmlInventory:
    source_type: str
    version: str | None
    units: str | None
    root_tag: str
    element_count: int
    element_counts: dict[str, int]
    direct_child_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "version": self.version,
            "units": self.units,
            "root_tag": self.root_tag,
            "element_count": self.element_count,
            "element_counts": self.element_counts,
            "direct_child_counts": self.direct_child_counts,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _decoded_xml_candidates(data: bytes) -> Iterator[str]:
    """Yield safe, fixed-codec decodings used only by the DTD/entity guard."""

    codecs = ("utf-8-sig", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be", "iso-8859-1")
    for codec in codecs:
        try:
            yield data.decode(codec)
        except (UnicodeError, LookupError, ValueError):
            continue


def reject_unsafe_xml(data: bytes) -> None:
    """Reject entity-capable XML before handing bytes to ElementTree."""

    if FORBIDDEN_XML_BYTES.search(data):
        raise CaptureError(
            "XML declarations containing DTDs or entities are forbidden",
            code="forbidden_xml_declaration",
            exit_code=3,
        )
    # The decoded pass closes the null-interleaved UTF-16/32 gap.  Codec names
    # are fixed here; no attacker-controlled codec is ever passed to decode().
    for text in _decoded_xml_candidates(data):
        if FORBIDDEN_XML_TEXT.search(text):
            raise CaptureError(
                "XML declarations containing DTDs or entities are forbidden",
                code="forbidden_xml_declaration",
                exit_code=3,
            )


def inspect_xml(data: bytes) -> XmlInventory:
    if len(data) > MAX_XML_BYTES:
        raise CaptureError(
            f"XML exceeds the {MAX_XML_BYTES}-byte capture limit",
            code="xml_too_large",
        )
    reject_unsafe_xml(data)

    all_counts: Counter[str] = Counter()
    child_counts: Counter[str] = Counter()
    root_tag: str | None = None
    root_attributes: dict[str, str] = {}
    depth = 0

    def reject_declaration(*_args: Any) -> None:
        raise CaptureError(
            "XML declarations containing DTDs or entities are forbidden",
            code="forbidden_xml_declaration",
            exit_code=3,
        )

    def reject_external_entity(*_args: Any) -> int:
        reject_declaration()
        return 0

    def start_element(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth, root_tag, root_attributes
        name = local_name(name)
        if root_tag is None:
            root_tag = name
            root_attributes = {local_name(key): value for key, value in attributes.items()}
        else:
            all_counts[name] += 1
            if depth == 1:
                child_counts[name] += 1
        depth += 1

    def end_element(_name: str) -> None:
        nonlocal depth
        depth -= 1

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_external_entity
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(data, True)
    except CaptureError:
        raise
    except (expat.ExpatError, ValueError, UnicodeError) as exc:
        raise CaptureError(f"Cannot parse DipTrace XML: {exc}", code="xml_parse_error") from exc

    if root_tag != "Source":
        raise CaptureError(
            f"Expected a <Source> root, got <{root_tag}>",
            code="not_diptrace_source",
        )
    source_type = root_attributes.get("Type")
    if source_type not in SOURCE_TYPES:
        raise CaptureError(
            f"Unsupported or missing Source/@Type: {source_type!r}",
            code="unsupported_source_type",
        )
    version = root_attributes.get("Version")
    units = root_attributes.get("Units")
    if units is not None and units not in UNITS:
        raise CaptureError(
            f"Unsupported Source/@Units: {units!r}",
            code="unsupported_document_units",
        )
    return XmlInventory(
        source_type=source_type,
        version=version,
        units=units,
        root_tag=root_tag,
        element_count=sum(all_counts.values()),
        element_counts=dict(sorted(all_counts.items())),
        direct_child_counts=dict(sorted(child_counts.items())),
    )


def _strict_json_bytes(raw: bytes, *, role: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise CaptureError(f"Invalid JSON in {role}: {exc}", code=f"{role}_invalid_json") from exc
    if not isinstance(value, dict):
        raise CaptureError(f"{role} must be a JSON object", code=f"{role}_invalid_shape")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError(f"{field} must be a non-empty string", code="invalid_manifest_field")
    return value.strip()


def validate_recipe(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "recipe_id",
        "title",
        "purpose",
        "expected_source_type",
        "required_features",
        "operator_checklist",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CaptureError(
            f"Recipe has unknown fields: {', '.join(unknown)}",
            code="invalid_recipe",
        )
    if value.get("schema_version") != RECIPE_SCHEMA:
        raise CaptureError(
            f"Recipe schema_version must be {RECIPE_SCHEMA!r}",
            code="invalid_recipe",
        )
    recipe_id = _require_text(value.get("recipe_id"), "recipe_id")
    if not SESSION_RE.fullmatch(recipe_id):
        raise CaptureError("recipe_id is not a safe slug", code="invalid_recipe")
    title = _require_text(value.get("title"), "title")
    purpose = _require_text(value.get("purpose"), "purpose")
    expected_type = value.get("expected_source_type")
    if expected_type is not None and expected_type not in SOURCE_TYPES:
        raise CaptureError("expected_source_type is invalid", code="invalid_recipe")

    features = value.get("required_features", [])
    if not isinstance(features, list) or any(
        not isinstance(item, str) or not item.strip() for item in features
    ):
        raise CaptureError("required_features must be a list of strings", code="invalid_recipe")

    checklist = value.get("operator_checklist")
    if not isinstance(checklist, list) or not checklist:
        raise CaptureError("operator_checklist must be a non-empty list", code="invalid_recipe")
    seen: set[str] = set()
    normalized_checklist: list[dict[str, Any]] = []
    for raw_item in checklist:
        if not isinstance(raw_item, dict):
            raise CaptureError("Each checklist item must be an object", code="invalid_recipe")
        if set(raw_item) - {"id", "prompt", "required", "stage"}:
            raise CaptureError("Checklist item has unknown fields", code="invalid_recipe")
        item_id = _require_text(raw_item.get("id"), "operator_checklist[].id")
        if not ITEM_RE.fullmatch(item_id) or item_id in seen:
            raise CaptureError(
                "Checklist item ids must be unique safe slugs",
                code="invalid_recipe",
            )
        seen.add(item_id)
        prompt = _require_text(raw_item.get("prompt"), "operator_checklist[].prompt")
        required = raw_item.get("required", True)
        if not isinstance(required, bool):
            raise CaptureError("Checklist required must be boolean", code="invalid_recipe")
        stage = raw_item.get("stage")
        if stage is not None and stage not in STAGES:
            raise CaptureError("Checklist stage is invalid", code="invalid_recipe")
        normalized_checklist.append(
            {"id": item_id, "prompt": prompt, "required": required, "stage": stage}
        )

    return {
        "schema_version": RECIPE_SCHEMA,
        "recipe_id": recipe_id,
        "title": title,
        "purpose": purpose,
        "expected_source_type": expected_type,
        "required_features": [item.strip() for item in features],
        "operator_checklist": normalized_checklist,
    }


def _validate_answers(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "operator_label",
        "diptrace_version",
        "diptrace_build",
        "operating_system",
        "redistribution_permitted",
        "redistribution_basis",
        "notes",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CaptureError(
            f"Answers have unknown fields: {', '.join(unknown)}",
            code="invalid_answers",
        )
    permitted = value.get("redistribution_permitted")
    if not isinstance(permitted, bool):
        raise CaptureError("redistribution_permitted must be boolean", code="invalid_answers")
    basis = value.get("redistribution_basis", "")
    if not isinstance(basis, str):
        raise CaptureError("redistribution_basis must be a string", code="invalid_answers")
    if permitted and not basis.strip():
        raise CaptureError(
            "redistribution_basis is required when redistribution is permitted",
            code="invalid_answers",
        )
    notes = value.get("notes", "")
    if not isinstance(notes, str):
        raise CaptureError("notes must be a string", code="invalid_answers")
    return {
        "operator_label": _require_text(value.get("operator_label"), "operator_label"),
        "diptrace_version": _require_text(value.get("diptrace_version"), "diptrace_version"),
        "diptrace_build": _require_text(value.get("diptrace_build"), "diptrace_build"),
        "operating_system": _require_text(value.get("operating_system"), "operating_system"),
        "redistribution_permitted": permitted,
        "redistribution_basis": basis.strip(),
        "notes": notes.strip(),
    }


def _interactive_answers() -> dict[str, Any]:
    print("Operator and environment metadata (claims remain unverified until review).")
    values: dict[str, Any] = {
        "operator_label": input("Operator label (avoid personal data): ").strip(),
        "diptrace_version": input("DipTrace version shown by the application: ").strip(),
        "diptrace_build": input("DipTrace build number: ").strip(),
        "operating_system": input("Operating system/version: ").strip(),
    }
    permission = input(
        "May this design be redistributed in the repository? [y/N]: "
    ).strip().lower()
    values["redistribution_permitted"] = permission in {"y", "yes"}
    values["redistribution_basis"] = input(
        "Redistribution basis (license/ownership; blank if not permitted): "
    ).strip()
    values["notes"] = input("Optional session notes: ").strip()
    return _validate_answers(values)


def _interactive_attestations(stage: str) -> dict[str, bool]:
    prompts = {
        "source": {
            "direct_diptrace_export": "Was this XML exported directly by DipTrace?",
            "no_programmatic_xml_generation": "Was it free of hand/MCP/programmatic XML edits?",
        },
        "open_save": {
            "opened_in_diptrace": "Was the source opened in DipTrace?",
            "saved_by_diptrace": "Was this file saved by DipTrace?",
        },
        "reexport": {
            "fresh_diptrace_export": (
                "Was this XML freshly re-exported by DipTrace after open/save?"
            ),
            "no_programmatic_xml_generation": "Was it free of hand/MCP/programmatic XML edits?",
        },
    }
    answers: dict[str, bool] = {}
    for key, prompt in prompts[stage].items():
        reply = input(f"{prompt} [y/N]: ").strip().lower()
        answers[key] = reply in {"y", "yes"}
    return validate_attestations(stage, answers)


def validate_attestations(stage: str, value: Mapping[str, Any]) -> dict[str, bool]:
    required = {
        "source": {"direct_diptrace_export", "no_programmatic_xml_generation"},
        "open_save": {"opened_in_diptrace", "saved_by_diptrace"},
        "reexport": {"fresh_diptrace_export", "no_programmatic_xml_generation"},
    }[stage]
    if set(value) != required:
        raise CaptureError(
            f"{stage} attestations must contain exactly: {', '.join(sorted(required))}",
            code="invalid_attestations",
        )
    if any(not isinstance(value[key], bool) for key in required):
        raise CaptureError("Attestation values must be boolean", code="invalid_attestations")
    if not all(value[key] for key in required):
        raise CaptureError(
            "Every stage attestation must be explicitly confirmed",
            code="attestation_not_confirmed",
        )
    return {key: bool(value[key]) for key in sorted(required)}


def _invalid_state(detail: str) -> NoReturn:
    raise CaptureError(detail, code="invalid_session_state", exit_code=3)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    if set(value) != expected:
        _invalid_state(f"{field} has missing or unknown fields")


def _state_relative_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        _invalid_state(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _invalid_state(f"{field} must be a safe relative path")
    return path


def _state_text(value: Any, *, field: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value:
        _invalid_state(f"{field} must be a non-empty string")
    return value


def _state_counter(value: Any, *, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        _invalid_state(f"{field} must be an object")
    result: dict[str, int] = {}
    for key, count in value.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            _invalid_state(f"{field} contains an invalid counter")
        result[key] = count
    return result


def _validate_state_input_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > MAX_INPUT_ARTIFACTS:
        _invalid_state(
            f"input_artifacts must contain 1-{MAX_INPUT_ARTIFACTS} metadata entries"
        )
    normalized: list[dict[str, Any]] = []
    roles: set[str] = set()
    names: set[str] = set()
    paths: set[Path] = set()
    for index, raw in enumerate(value):
        field = f"input_artifacts[{index}]"
        if not isinstance(raw, dict):
            _invalid_state(f"{field} must be an object")
        _require_exact_keys(raw, INPUT_ARTIFACT_KEYS, field=field)
        role = raw.get("role")
        if not isinstance(role, str) or ITEM_RE.fullmatch(role) is None:
            _invalid_state(f"{field}.role must be a safe lowercase slug")
        name = raw.get("name")
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 255
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in name)
        ):
            _invalid_state(f"{field}.name must be one safe basename")
        raw_path = raw.get("path")
        if not isinstance(raw_path, str) or "\\" in raw_path:
            _invalid_state(f"{field}.path must use canonical forward slashes")
        relative = _state_relative_path(raw_path, field=f"{field}.path")
        if relative.parts[0] == STORE_NAME or relative.name != name:
            _invalid_state(f"{field}.path is not a canonical private input path")
        digest = raw.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            _invalid_state(f"{field}.sha256 is invalid")
        size = raw.get("size_bytes")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_INPUT_ARTIFACT_BYTES
        ):
            _invalid_state(f"{field}.size_bytes is invalid")
        if role in roles or name in names or relative in paths:
            _invalid_state("input_artifacts contains a duplicate role, name, or path")
        roles.add(role)
        names.add(name)
        paths.add(relative)
        normalized.append(
            {
                "role": role,
                "name": name,
                "path": relative.as_posix(),
                "sha256": digest,
                "size_bytes": size,
            }
        )
    expected_order = sorted(
        normalized,
        key=lambda item: (item["role"], item["name"], item["path"]),
    )
    if normalized != expected_order:
        _invalid_state("input_artifacts must use canonical role/name/path order")
    return normalized


def validate_state(
    value: Mapping[str, Any],
    *,
    expected_session_id: str,
    expected_root: str,
) -> dict[str, Any]:
    """Validate the complete persisted v1 state before any field is consumed."""

    required = {
        "schema_version",
        "session_id",
        "status",
        "allowed_root",
        "created_at",
        "updated_at",
        "recipe",
        "operator_claims",
        "required_stages",
        "stage_sequence",
        "stages",
        "checklist",
        "events",
    }
    optional = {"candidate", "abort_reason", "input_artifacts"}
    if not required.issubset(value) or set(value) - required - optional:
        _invalid_state("Session state has missing or unknown top-level fields")
    if value.get("schema_version") != STATE_SCHEMA:
        _invalid_state("Session state schema_version is invalid")
    if value.get("session_id") != expected_session_id:
        _invalid_state("Session state id does not match its directory")
    if value.get("allowed_root") != expected_root:
        raise CaptureError(
            "Session is bound to a different allowed root",
            code="session_root_mismatch",
            exit_code=3,
        )
    status = value.get("status")
    if status not in {"active", "aborted", "candidate_ready"}:
        _invalid_state("Session status is invalid")
    _state_text(value.get("created_at"), field="created_at")
    _state_text(value.get("updated_at"), field="updated_at")

    recipe_record = value.get("recipe")
    if not isinstance(recipe_record, dict):
        _invalid_state("recipe must be an object")
    _require_exact_keys(
        recipe_record,
        {"source_path", "source_sha256", "snapshot"},
        field="recipe",
    )
    recipe_path = _state_relative_path(recipe_record.get("source_path"), field="recipe.source_path")
    if recipe_path.parts[0] == STORE_NAME:
        _invalid_state("recipe.source_path may not point into the capture store")
    recipe_sha = recipe_record.get("source_sha256")
    if not isinstance(recipe_sha, str) or SHA256_RE.fullmatch(recipe_sha) is None:
        _invalid_state("recipe.source_sha256 is invalid")
    snapshot = recipe_record.get("snapshot")
    if not isinstance(snapshot, dict):
        _invalid_state("recipe.snapshot must be an object")
    try:
        normalized_recipe = validate_recipe(snapshot)
    except CaptureError as exc:
        raise CaptureError(
            f"Session recipe snapshot is invalid: {exc}",
            code="invalid_session_state",
            exit_code=3,
        ) from exc
    if normalized_recipe != snapshot:
        _invalid_state("Session recipe snapshot is not normalized")

    operator_claims = value.get("operator_claims")
    if not isinstance(operator_claims, dict):
        _invalid_state("operator_claims must be an object")
    try:
        normalized_claims = _validate_answers(operator_claims)
    except CaptureError as exc:
        raise CaptureError(
            f"Session operator claims are invalid: {exc}",
            code="invalid_session_state",
            exit_code=3,
        ) from exc
    if normalized_claims != operator_claims:
        _invalid_state("Session operator claims are not normalized")

    if "input_artifacts" in value:
        normalized_inputs = _validate_state_input_artifacts(value["input_artifacts"])
        if normalized_inputs != value["input_artifacts"]:
            _invalid_state("input_artifacts is not normalized")

    if value.get("required_stages") != list(STAGES):
        _invalid_state("required_stages must match the capture protocol")
    sequence = value.get("stage_sequence")
    if not isinstance(sequence, list) or sequence != list(STAGES[: len(sequence)]):
        _invalid_state("stage_sequence must be an ordered prefix of the capture protocol")
    stages = value.get("stages")
    if not isinstance(stages, dict) or set(stages) != set(sequence):
        _invalid_state("stages must exactly match stage_sequence")
    if "input_artifacts" in value and "source" not in stages:
        _invalid_state("input_artifacts requires a recorded source stage")
    for stage in sequence:
        record = stages.get(stage)
        if not isinstance(record, dict):
            _invalid_state(f"stages.{stage} must be an object")
        _require_exact_keys(
            record,
            {
                "stage",
                "captured_at",
                "original_path",
                "quarantine_path",
                "sha256",
                "size_bytes",
                "xml_inventory",
                "operator_attestations",
                "operator_note",
                "warnings",
            },
            field=f"stages.{stage}",
        )
        if record.get("stage") != stage:
            _invalid_state(f"stages.{stage}.stage is inconsistent")
        _state_text(record.get("captured_at"), field=f"stages.{stage}.captured_at")
        original_path = _state_relative_path(
            record.get("original_path"),
            field=f"stages.{stage}.original_path",
        )
        if original_path.parts[0] == STORE_NAME:
            _invalid_state(f"stages.{stage}.original_path points into the capture store")
        quarantine_path = _state_relative_path(
            record.get("quarantine_path"),
            field=f"stages.{stage}.quarantine_path",
        )
        expected_prefix = Path(STORE_NAME) / "quarantine" / expected_session_id / stage
        try:
            quarantine_path.relative_to(expected_prefix)
        except ValueError:
            _invalid_state(f"stages.{stage}.quarantine_path is outside its stage area")
        digest = record.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            _invalid_state(f"stages.{stage}.sha256 is invalid")
        size = record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _invalid_state(f"stages.{stage}.size_bytes is invalid")

        inventory = record.get("xml_inventory")
        if not isinstance(inventory, dict):
            _invalid_state(f"stages.{stage}.xml_inventory must be an object")
        _require_exact_keys(
            inventory,
            {
                "source_type",
                "version",
                "units",
                "root_tag",
                "element_count",
                "element_counts",
                "direct_child_counts",
            },
            field=f"stages.{stage}.xml_inventory",
        )
        if (
            inventory.get("source_type") not in SOURCE_TYPES
            or inventory.get("root_tag") != "Source"
        ):
            _invalid_state(f"stages.{stage}.xml_inventory identity is invalid")
        if inventory.get("version") is not None and not isinstance(
            inventory.get("version"), str
        ):
            _invalid_state(f"stages.{stage}.xml_inventory.version is invalid")
        if inventory.get("units") is not None and inventory.get("units") not in UNITS:
            _invalid_state(f"stages.{stage}.xml_inventory.units is invalid")
        element_counts = _state_counter(
            inventory.get("element_counts"),
            field=f"stages.{stage}.xml_inventory.element_counts",
        )
        _state_counter(
            inventory.get("direct_child_counts"),
            field=f"stages.{stage}.xml_inventory.direct_child_counts",
        )
        element_count = inventory.get("element_count")
        if (
            not isinstance(element_count, int)
            or isinstance(element_count, bool)
            or element_count != sum(element_counts.values())
        ):
            _invalid_state(f"stages.{stage}.xml_inventory.element_count is inconsistent")
        attestations = record.get("operator_attestations")
        if not isinstance(attestations, dict):
            _invalid_state(f"stages.{stage}.operator_attestations must be an object")
        try:
            normalized_attestations = validate_attestations(stage, attestations)
        except CaptureError as exc:
            raise CaptureError(
                f"Session stage attestations are invalid: {exc}",
                code="invalid_session_state",
                exit_code=3,
            ) from exc
        if normalized_attestations != attestations:
            _invalid_state(f"stages.{stage}.operator_attestations are not normalized")
        if not isinstance(record.get("operator_note"), str):
            _invalid_state(f"stages.{stage}.operator_note must be a string")
        warnings = record.get("warnings")
        if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
            _invalid_state(f"stages.{stage}.warnings must be a list of strings")

    checklist = value.get("checklist")
    if not isinstance(checklist, dict):
        _invalid_state("checklist must be an object")
    recipe_items = {item["id"]: item for item in normalized_recipe["operator_checklist"]}
    if set(checklist) != set(recipe_items):
        _invalid_state("checklist does not match the recipe snapshot")
    for item_id, recipe_item in recipe_items.items():
        item = checklist.get(item_id)
        if not isinstance(item, dict):
            _invalid_state(f"checklist.{item_id} must be an object")
        _require_exact_keys(
            item,
            {"prompt", "required", "stage", "answer", "note", "answered_at"},
            field=f"checklist.{item_id}",
        )
        if any(item.get(key) != recipe_item[key] for key in ("prompt", "required", "stage")):
            _invalid_state(f"checklist.{item_id} does not match the recipe")
        answer = item.get("answer")
        if answer not in {"pending", "yes", "no", "not_applicable"}:
            _invalid_state(f"checklist.{item_id}.answer is invalid")
        if not isinstance(item.get("note"), str):
            _invalid_state(f"checklist.{item_id}.note must be a string")
        answered_at = item.get("answered_at")
        if answer == "pending":
            if answered_at is not None:
                _invalid_state(f"checklist.{item_id}.answered_at must be null while pending")
        else:
            _state_text(answered_at, field=f"checklist.{item_id}.answered_at")

    events = value.get("events")
    if not isinstance(events, list) or not events:
        _invalid_state("events must be a non-empty list")
    event_keys = {
        "at", "kind", "detail", "sha256", "answer", "artifacts_preserved", "trust_grant"
    }
    for event in events:
        if (
            not isinstance(event, dict)
            or set(event) - event_keys
            or not isinstance(event.get("at"), str)
            or not isinstance(event.get("kind"), str)
        ):
            _invalid_state("events contains an invalid event")

    candidate = value.get("candidate")
    if status == "candidate_ready":
        if not isinstance(candidate, dict):
            _invalid_state("candidate_ready state requires candidate metadata")
        _require_exact_keys(
            candidate,
            {"manifest_path", "manifest_sha256", "digest_path", "review_status"},
            field="candidate",
        )
        manifest_path = _state_relative_path(
            candidate.get("manifest_path"),
            field="candidate.manifest_path",
        )
        digest_path = _state_relative_path(
            candidate.get("digest_path"),
            field="candidate.digest_path",
        )
        expected_candidate_dir = Path(STORE_NAME) / "candidates"
        try:
            manifest_path.relative_to(expected_candidate_dir)
            digest_path.relative_to(expected_candidate_dir)
        except ValueError:
            _invalid_state("candidate artifacts are outside the candidates directory")
        candidate_sha = candidate.get("manifest_sha256")
        if not isinstance(candidate_sha, str) or SHA256_RE.fullmatch(candidate_sha) is None:
            _invalid_state("candidate.manifest_sha256 is invalid")
        if candidate.get("review_status") != "pending_independent_review":
            _invalid_state("candidate.review_status is invalid")
        if sequence != list(STAGES):
            _invalid_state("candidate_ready state requires all stages")
    elif candidate is not None:
        _invalid_state("candidate metadata is only valid for candidate_ready state")

    abort_reason = value.get("abort_reason")
    if status == "aborted":
        _state_text(abort_reason, field="abort_reason")
    elif abort_reason is not None:
        _invalid_state("abort_reason is only valid for aborted state")
    return dict(value)


class CaptureRepository:
    """Stateful quarantine rooted at an explicitly allowed directory."""

    def __init__(self, root: Path | str) -> None:
        candidate = Path(root).expanduser()
        try:
            self.root = candidate.resolve(strict=True)
        except OSError as exc:
            raise CaptureError(
                f"Allowed root does not exist: {candidate}",
                code="root_missing",
            ) from exc
        if not self.root.is_dir():
            raise CaptureError("Allowed root must be a directory", code="root_not_directory")
        root_metadata = os.stat(self.root, follow_symlinks=False)
        self._root_identity = (root_metadata.st_dev, root_metadata.st_ino)
        self._root_fd: int | None = None
        self.path_safety_mode = (
            "descriptor_relative_posix"
            if SECURE_DIR_FD_AVAILABLE
            else "cooperative_static_checks"
        )
        if SECURE_DIR_FD_AVAILABLE:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                expected = os.stat(self.root, follow_symlinks=False)
                root_fd = os.open(self.root, flags)
                actual = os.fstat(root_fd)
            except OSError as exc:
                raise CaptureError(
                    f"Cannot pin the allowed root safely: {exc}",
                    code="unsafe_allowed_root",
                    exit_code=3,
                ) from exc
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                os.close(root_fd)
                raise CaptureError(
                    "Allowed root changed while it was being opened",
                    code="unsafe_allowed_root",
                    exit_code=3,
                )
            self._root_fd = root_fd
        self.store = self.root / STORE_NAME
        self.sessions = self.store / "sessions"
        self.quarantine = self.store / "quarantine"
        self.candidates = self.store / "candidates"
        self._ensure_store_dirs()
        store_metadata = os.stat(self.store, follow_symlinks=False)
        self._store_identity = (store_metadata.st_dev, store_metadata.st_ino)

    def __del__(self) -> None:
        root_fd = getattr(self, "_root_fd", None)
        if root_fd is not None:
            with suppress(OSError):
                os.close(root_fd)
            self._root_fd = None

    def _ensure_store_dirs(self) -> None:
        for path in (self.store, self.sessions, self.quarantine, self.candidates):
            self._ensure_safe_directory(path, create=True)

    @staticmethod
    def _is_redirecting_path(path: Path) -> bool:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction is not None and is_junction())

    def _relative_parts(self, path: Path, *, base: Path | None = None) -> tuple[str, ...]:
        try:
            relative = path.relative_to(self.root)
            if base is not None:
                relative.relative_to(base.relative_to(self.root))
        except ValueError as exc:
            raise CaptureError(
                f"Path escapes the allowed root: {path}",
                code="path_outside_allowed_root",
                exit_code=3,
            ) from exc
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise CaptureError(
                f"Path contains an unsafe component: {path}",
                code="path_outside_allowed_root",
                exit_code=3,
            )
        return relative.parts

    @contextmanager
    def _open_safe_directory_fd(
        self,
        path: Path,
        *,
        create: bool,
        forbidden_directory_identity: tuple[int, int] | None = None,
    ) -> Iterator[int]:
        if self._root_fd is None:
            raise CaptureError(
                "Descriptor-relative path operations are unavailable",
                code="secure_path_api_unavailable",
                exit_code=3,
            )
        parts = self._relative_parts(path)
        current_fd = os.dup(self._root_fd)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    except OSError as exc:
                        raise CaptureError(
                            f"Cannot create capture directory component {part!r}: {exc}",
                            code="unsafe_store_path",
                            exit_code=3,
                        ) from exc
                try:
                    next_fd = os.open(part, flags, dir_fd=current_fd)
                except FileNotFoundError as exc:
                    raise CaptureError(
                        f"Capture directory does not exist: {path}",
                        code="capture_directory_missing",
                    ) from exc
                except OSError as exc:
                    raise CaptureError(
                        f"Capture directory component is unsafe: {part}",
                        code="unsafe_store_path",
                        exit_code=3,
                    ) from exc
                os.close(current_fd)
                current_fd = next_fd
                metadata = os.fstat(current_fd)
                if not stat.S_ISDIR(metadata.st_mode):
                    raise CaptureError(
                        f"Capture directory component is unsafe: {part}",
                        code="unsafe_store_path",
                        exit_code=3,
                    )
                if (
                    forbidden_directory_identity is not None
                    and (metadata.st_dev, metadata.st_ino)
                    == forbidden_directory_identity
                ):
                    raise CaptureError(
                        "Input artifact may not come from the capture store",
                        code="capture_store_input_forbidden",
                        exit_code=3,
                    )
            yield current_fd
        finally:
            with suppress(OSError):
                os.close(current_fd)

    def _ensure_safe_directory(self, path: Path, *, create: bool) -> Path:
        """Create/check every descendant without accepting a symlink component."""

        if self._root_fd is not None:
            with self._open_safe_directory_fd(path, create=create):
                return path
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:
            raise CaptureError(
                f"Directory escapes the allowed root: {path}",
                code="path_outside_allowed_root",
                exit_code=3,
            ) from exc
        current = self.root
        for part in relative.parts:
            current = current / part
            if create:
                current.mkdir(mode=0o700, exist_ok=True)
            if not current.exists():
                raise CaptureError(
                    f"Capture directory does not exist: {current}",
                    code="capture_directory_missing",
                )
            if self._is_redirecting_path(current) or not current.is_dir():
                raise CaptureError(
                    f"Capture directory component is unsafe: {current}",
                    code="unsafe_store_path",
                    exit_code=3,
                )
            resolved = current.resolve(strict=True)
            self._assert_within_root(resolved)
            if resolved != current:
                raise CaptureError(
                    f"Capture directory component may not redirect: {current}",
                    code="unsafe_store_path",
                    exit_code=3,
                )
        return path

    def _assert_within_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise CaptureError(
                f"Path escapes the allowed root: {path}",
                code="path_outside_allowed_root",
                exit_code=3,
            ) from exc

    def allowed_file(self, path: Path | str, *, role: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise CaptureError(
                f"{role} does not exist: {candidate}",
                code=f"{role}_missing",
            ) from exc
        self._assert_within_root(resolved)
        if not resolved.is_file():
            raise CaptureError(f"{role} must be a file", code=f"{role}_not_file")
        try:
            resolved.relative_to(self.store)
        except ValueError:
            return resolved
        raise CaptureError(
            f"{role} may not come from the capture store itself",
            code="capture_store_input_forbidden",
            exit_code=3,
        )

    def _read_root_file(self, path: Path, *, base: Path, role: str) -> bytes:
        parts = self._relative_parts(path, base=base)
        if not parts:
            raise CaptureError(f"{role} must be a file", code=f"{role}_not_file")
        if self._root_fd is None:
            if self._is_redirecting_path(path):
                raise CaptureError(
                    f"{role} may not be a symlink or junction",
                    code=f"unsafe_{role}",
                    exit_code=3,
                )
            try:
                resolved = path.resolve(strict=True)
                self._assert_within_root(resolved)
                resolved.relative_to(base)
                return resolved.read_bytes()
            except (OSError, ValueError) as exc:
                raise CaptureError(
                    f"{role} is missing or outside its allowed area",
                    code=f"unsafe_{role}",
                    exit_code=3,
                ) from exc

        parent = self.root.joinpath(*parts[:-1])
        with self._open_safe_directory_fd(parent, create=False) as parent_fd:
            flags = os.O_RDONLY | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                descriptor = os.open(parts[-1], flags, dir_fd=parent_fd)
            except OSError as exc:
                raise CaptureError(
                    f"{role} is missing or unsafe",
                    code=f"unsafe_{role}",
                    exit_code=3,
                ) from exc
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise CaptureError(
                        f"{role} must be a regular file",
                        code=f"unsafe_{role}",
                        exit_code=3,
                    )
                with os.fdopen(descriptor, "rb") as handle:
                    descriptor = -1
                    return handle.read()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

    def _store_file_exists(self, path: Path, *, base: Path, role: str) -> bool:
        parts = self._relative_parts(path, base=base)
        if not parts:
            return False
        if self._root_fd is None:
            self._ensure_safe_directory(path.parent, create=False)
            if self._is_redirecting_path(path):
                raise CaptureError(
                    f"{role} may not be a symlink or junction",
                    code=f"unsafe_{role}",
                    exit_code=3,
                )
            return path.exists()
        with self._open_safe_directory_fd(path.parent, create=False) as parent_fd:
            try:
                result = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            except OSError as exc:
                raise CaptureError(
                    f"Cannot inspect {role}: {exc}",
                    code=f"unsafe_{role}",
                    exit_code=3,
                ) from exc
            if stat.S_ISLNK(result.st_mode):
                raise CaptureError(
                    f"{role} may not be a symlink",
                    code=f"unsafe_{role}",
                    exit_code=3,
                )
            return True

    def read_allowed_file(self, path: Path | str, *, role: str) -> tuple[Path, bytes]:
        resolved = self.allowed_file(path, role=role)
        return resolved, self._read_root_file(resolved, base=self.root, role=role)

    def _private_input_path(self, path: Path | str) -> tuple[Path, Path]:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise CaptureError(
                f"Input artifact escapes the allowed root: {candidate}",
                code="path_outside_allowed_root",
                exit_code=3,
            ) from exc
        if (
            not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or "\\" in relative.as_posix()
        ):
            raise CaptureError(
                "Input artifact path must be contained outside the capture store",
                code="unsafe_input_artifact",
                exit_code=3,
            )
        self._assert_private_input_outside_store(candidate)
        return candidate, relative

    def _assert_private_input_outside_store(self, candidate: Path) -> None:
        """Verify real ancestry by filesystem identity, including case aliases on NTFS."""

        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise CaptureError(
                f"Input artifact is missing or unsafe: {candidate}",
                code="unsafe_input_artifact",
                exit_code=3,
            ) from exc
        contained = False
        for current in (resolved, *resolved.parents):
            try:
                metadata = current.stat()
            except OSError as exc:
                raise CaptureError(
                    f"Cannot verify input artifact ancestry: {exc}",
                    code="unsafe_input_artifact",
                    exit_code=3,
                ) from exc
            identity = (metadata.st_dev, metadata.st_ino)
            if identity == self._store_identity:
                raise CaptureError(
                    "Input artifact may not come from the capture store",
                    code="capture_store_input_forbidden",
                    exit_code=3,
                )
            if identity == self._root_identity:
                contained = True
                break
        if not contained:
            raise CaptureError(
                f"Input artifact escapes the allowed root: {candidate}",
                code="path_outside_allowed_root",
                exit_code=3,
            )

    @staticmethod
    def _hash_input_descriptor(
        descriptor: int,
        *,
        role: str,
    ) -> tuple[str, int, tuple[int, int]]:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CaptureError(
                f"Input artifact {role!r} must be a regular file",
                code="unsafe_input_artifact",
                exit_code=3,
            )
        if before.st_nlink != 1:
            raise CaptureError(
                f"Input artifact {role!r} may not have hard-link aliases",
                code="input_artifact_identity_conflict",
                exit_code=3,
            )
        if before.st_size > MAX_INPUT_ARTIFACT_BYTES:
            raise CaptureError(
                f"Input artifact {role!r} exceeds {MAX_INPUT_ARTIFACT_BYTES} bytes",
                code="input_artifact_too_large",
            )
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > MAX_INPUT_ARTIFACT_BYTES:
                raise CaptureError(
                    f"Input artifact {role!r} exceeds {MAX_INPUT_ARTIFACT_BYTES} bytes",
                    code="input_artifact_too_large",
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        if before_identity != after_identity or total != after.st_size:
            raise CaptureError(
                f"Input artifact {role!r} changed while it was being hashed",
                code="input_artifact_changed",
                exit_code=3,
            )
        return digest.hexdigest(), total, (after.st_dev, after.st_ino)

    def _inspect_input_artifact(
        self,
        role: str,
        path: Path | str,
    ) -> tuple[dict[str, Any], tuple[int, int]]:
        if ITEM_RE.fullmatch(role) is None:
            raise CaptureError(
                "Input artifact role must be a safe lowercase slug",
                code="invalid_input_artifact",
            )
        candidate, relative = self._private_input_path(path)
        if (
            not relative.name
            or len(relative.name) > 255
            or any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in relative.name
            )
        ):
            raise CaptureError(
                "Input artifact name must be one safe basename",
                code="invalid_input_artifact",
            )
        if self._root_fd is not None:
            with self._open_safe_directory_fd(
                candidate.parent,
                create=False,
                forbidden_directory_identity=self._store_identity,
            ) as parent_fd:
                flags = os.O_RDONLY | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                try:
                    descriptor = os.open(relative.name, flags, dir_fd=parent_fd)
                except OSError as exc:
                    raise CaptureError(
                        f"Input artifact {role!r} is missing or unsafe",
                        code="unsafe_input_artifact",
                        exit_code=3,
                    ) from exc
                try:
                    digest, size, identity = self._hash_input_descriptor(
                        descriptor,
                        role=role,
                    )
                finally:
                    os.close(descriptor)
        else:
            self._assert_private_input_outside_store(candidate)
            current = self.root
            for index, part in enumerate(relative.parts):
                current /= part
                try:
                    metadata = current.lstat()
                except OSError as exc:
                    raise CaptureError(
                        f"Input artifact {role!r} is missing or unsafe",
                        code="unsafe_input_artifact",
                        exit_code=3,
                    ) from exc
                if self._is_redirecting_path(current):
                    raise CaptureError(
                        f"Input artifact {role!r} may not use a symlink or junction",
                        code="unsafe_input_artifact",
                        exit_code=3,
                    )
                expected_type = (
                    stat.S_ISREG(metadata.st_mode)
                    if index == len(relative.parts) - 1
                    else stat.S_ISDIR(metadata.st_mode)
                )
                if not expected_type:
                    raise CaptureError(
                        f"Input artifact {role!r} has an unsafe path component",
                        code="unsafe_input_artifact",
                        exit_code=3,
                    )
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(candidate, flags)
            except OSError as exc:
                raise CaptureError(
                    f"Input artifact {role!r} is missing or unsafe",
                    code="unsafe_input_artifact",
                    exit_code=3,
                ) from exc
            try:
                digest, size, identity = self._hash_input_descriptor(
                    descriptor,
                    role=role,
                )
            finally:
                os.close(descriptor)
            self._assert_private_input_outside_store(candidate)
        return (
            {
                "role": role,
                "name": relative.name,
                "path": relative.as_posix(),
                "sha256": digest,
                "size_bytes": size,
            },
            identity,
        )

    def _capture_input_artifacts(
        self,
        specifications: Sequence[tuple[str, Path | str]],
        *,
        source: Path,
        recipe_path: Path,
    ) -> list[dict[str, Any]]:
        if len(specifications) > MAX_INPUT_ARTIFACTS:
            raise CaptureError(
                f"At most {MAX_INPUT_ARTIFACTS} input artifacts may be recorded",
                code="invalid_input_artifact",
            )
        records: list[dict[str, Any]] = []
        identities: set[tuple[int, int]] = set()
        roles: set[str] = set()
        names: set[str] = set()
        paths: set[str] = set()
        for role, path in specifications:
            record, identity = self._inspect_input_artifact(role, path)
            if (
                record["role"] in roles
                or record["name"] in names
                or record["path"] in paths
                or identity in identities
            ):
                raise CaptureError(
                    "Input artifacts must have unique roles, names, paths, and identities",
                    code="input_artifact_identity_conflict",
                )
            input_path = self.root / record["path"]
            try:
                conflicts_with_protocol = input_path.samefile(source) or input_path.samefile(
                    recipe_path
                )
            except OSError as exc:
                raise CaptureError(
                    f"Cannot verify input artifact identity: {exc}",
                    code="unsafe_input_artifact",
                    exit_code=3,
                ) from exc
            if conflicts_with_protocol:
                raise CaptureError(
                    "An input artifact may not reuse the recipe or XML stage file",
                    code="input_artifact_identity_conflict",
                )
            roles.add(record["role"])
            names.add(record["name"])
            paths.add(record["path"])
            identities.add(identity)
            records.append(record)
        return sorted(
            records,
            key=lambda item: (item["role"], item["name"], item["path"]),
        )

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        if not SESSION_RE.fullmatch(session_id):
            raise CaptureError(
                "Session id must be 1-64 lowercase slug characters",
                code="invalid_session_id",
            )
        return session_id

    def session_dir(self, session_id: str) -> Path:
        return self.sessions / self.validate_session_id(session_id)

    def state_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "state.json"

    @contextmanager
    def mutation_lock(self, session_id: str) -> Iterator[None]:
        session_dir = self._ensure_safe_directory(
            self.session_dir(session_id),
            create=True,
        )
        lock_path = session_dir / ".lock"
        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if self._root_fd is None and self._is_redirecting_path(lock_path):
            raise CaptureError(
                "Session lock may not be a symlink or junction",
                code="unsafe_session_lock",
                exit_code=3,
            )
        try:
            if self._root_fd is not None:
                with self._open_safe_directory_fd(session_dir, create=False) as session_fd:
                    descriptor = os.open(".lock", flags, 0o600, dir_fd=session_fd)
            else:
                descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise CaptureError(
                f"Cannot safely open the session lock: {exc}",
                code="unsafe_session_lock",
                exit_code=3,
            ) from exc
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise CaptureError(
                "Session lock must be a regular file",
                code="unsafe_session_lock",
                exit_code=3,
            )
        if self._root_fd is None and self._is_redirecting_path(lock_path):
            os.close(descriptor)
            raise CaptureError(
                "Session lock may not be a symlink or junction",
                code="unsafe_session_lock",
                exit_code=3,
            )
        lock_handle = os.fdopen(descriptor, "a+b")
        unlock: Any
        windows_locking = False
        try:
            try:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                def unlock() -> None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

            except ImportError:
                import msvcrt

                windows_locking = True
                lock_handle.seek(0)
                if os.fstat(lock_handle.fileno()).st_size == 0:
                    lock_handle.write(b"\0")
                    lock_handle.flush()
                lock_handle.seek(0)
                try:
                    msvcrt.locking(  # type: ignore[attr-defined]
                        lock_handle.fileno(),
                        msvcrt.LK_NBLCK,  # type: ignore[attr-defined]
                        1,
                    )
                except OSError as exc:
                    raise CaptureError(
                        "Session is locked by another capture command",
                        code="session_locked",
                        exit_code=4,
                    ) from exc

                def unlock() -> None:
                    lock_handle.seek(0)
                    msvcrt.locking(  # type: ignore[attr-defined]
                        lock_handle.fileno(),
                        msvcrt.LK_UNLCK,  # type: ignore[attr-defined]
                        1,
                    )

            except BlockingIOError as exc:
                raise CaptureError(
                    "Session is locked by another capture command",
                    code="session_locked",
                    exit_code=4,
                ) from exc
            if not windows_locking:
                lock_handle.seek(0)
                lock_handle.truncate()
                lock_handle.write(f"pid={os.getpid()}\nacquired_at={utc_now()}\n".encode())
                lock_handle.flush()
                os.fsync(lock_handle.fileno())
            yield
        finally:
            if "unlock" in locals():
                unlock()
            lock_handle.close()

    def _atomic_write(self, path: Path, data: bytes, *, exclusive: bool = False) -> None:
        self._ensure_safe_directory(path.parent, create=True)
        if self._root_fd is not None:
            parts = self._relative_parts(path)
            leaf = parts[-1]
            with self._open_safe_directory_fd(path.parent, create=False) as parent_fd:
                try:
                    existing = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    existing = None
                except OSError as exc:
                    raise CaptureError(
                        f"Cannot inspect destination {path}: {exc}",
                        code="unsafe_store_path",
                        exit_code=3,
                    ) from exc
                if existing is not None and stat.S_ISLNK(existing.st_mode):
                    raise CaptureError(
                        f"Destination may not be a symlink: {path}",
                        code="unsafe_store_path",
                        exit_code=3,
                    )
                if exclusive and existing is not None:
                    raise CaptureError(f"Refusing to overwrite {path}", code="artifact_exists")

                temp_name = f".{leaf}.{secrets.token_hex(16)}"
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                try:
                    descriptor = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    if exclusive:
                        try:
                            os.link(
                                temp_name,
                                leaf,
                                src_dir_fd=parent_fd,
                                dst_dir_fd=parent_fd,
                                follow_symlinks=False,
                            )
                        except FileExistsError as exc:
                            raise CaptureError(
                                f"Refusing to overwrite {path}",
                                code="artifact_exists",
                            ) from exc
                    else:
                        os.rename(
                            temp_name,
                            leaf,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                        )
                    os.fsync(parent_fd)
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(temp_name, dir_fd=parent_fd)
            return

        if self._is_redirecting_path(path):
            raise CaptureError(
                f"Destination may not be a symlink or junction: {path}",
                code="unsafe_store_path",
                exit_code=3,
            )
        if exclusive and path.exists():
            raise CaptureError(f"Refusing to overwrite {path}", code="artifact_exists")
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            if exclusive and path.exists():
                raise CaptureError(f"Refusing to overwrite {path}", code="artifact_exists")
            if exclusive:
                try:
                    os.link(temp_path, path, follow_symlinks=False)
                except FileExistsError as exc:
                    raise CaptureError(
                        f"Refusing to overwrite {path}",
                        code="artifact_exists",
                    ) from exc
            else:
                os.replace(temp_path, path)
        finally:
            with suppress(FileNotFoundError):
                temp_path.unlink()

    def _read_store_file(self, path: Path, *, base: Path, role: str) -> bytes:
        return self._read_root_file(path, base=base, role=role)

    def _write_state(self, state: Mapping[str, Any]) -> None:
        session_id = str(state["session_id"])
        self._atomic_write(self.state_path(session_id), canonical_json_bytes(state))

    def load_state(self, session_id: str) -> dict[str, Any]:
        session_dir = self.session_dir(session_id)
        try:
            session_dir = self._ensure_safe_directory(
                session_dir,
                create=False,
            )
        except CaptureError as exc:
            if exc.code == "capture_directory_missing":
                raise CaptureError(
                    f"Unknown session: {session_id}",
                    code="session_not_found",
                ) from exc
            raise
        path = session_dir / "state.json"
        if not self._store_file_exists(
            path,
            base=self.sessions,
            role="session_state",
        ):
            raise CaptureError(f"Unknown session: {session_id}", code="session_not_found")
        raw = self._read_store_file(path, base=self.sessions, role="session_state")
        value = _strict_json_bytes(raw, role="session_state")
        return validate_state(
            value,
            expected_session_id=session_id,
            expected_root=str(self.root),
        )

    def init_session(
        self,
        session_id: str,
        recipe_path: Path | str,
        answers: Mapping[str, Any],
    ) -> dict[str, Any]:
        session_id = self.validate_session_id(session_id)
        recipe_source, recipe_bytes = self.read_allowed_file(recipe_path, role="recipe")
        recipe = validate_recipe(_strict_json_bytes(recipe_bytes, role="recipe"))
        normalized_answers = _validate_answers(answers)
        with self.mutation_lock(session_id):
            state_path = self.state_path(session_id)
            if self._store_file_exists(
                state_path,
                base=self.sessions,
                role="session_state",
            ):
                raise CaptureError("Session already exists", code="session_exists", exit_code=4)
            now = utc_now()
            state: dict[str, Any] = {
                "schema_version": STATE_SCHEMA,
                "session_id": session_id,
                "status": "active",
                "allowed_root": str(self.root),
                "created_at": now,
                "updated_at": now,
                "recipe": {
                    "source_path": str(recipe_source.relative_to(self.root)),
                    "source_sha256": sha256_bytes(recipe_bytes),
                    "snapshot": recipe,
                },
                "operator_claims": normalized_answers,
                "required_stages": list(STAGES),
                "stage_sequence": [],
                "stages": {},
                "checklist": {
                    item["id"]: {
                        "prompt": item["prompt"],
                        "required": item["required"],
                        "stage": item["stage"],
                        "answer": "pending",
                        "note": "",
                        "answered_at": None,
                    }
                    for item in recipe["operator_checklist"]
                },
                "events": [
                    {
                        "at": now,
                        "kind": "session_initialized",
                        "detail": "Operator-supplied claims are unverified",
                    }
                ],
            }
            self._write_state(state)
            return state

    @staticmethod
    def _require_active(state: Mapping[str, Any]) -> None:
        if state.get("status") != "active":
            raise CaptureError(
                f"Session is not active (status={state.get('status')!r})",
                code="session_not_active",
                exit_code=4,
            )

    def _quarantine_stage(self, session_id: str, stage: str, source: Path, data: bytes) -> Path:
        suffix = source.suffix.lower()
        if suffix not in {".xml", ".dip", ".dch", ".eli", ".lib"}:
            suffix = ".xml"
        destination = self.quarantine / session_id / stage / f"{stage}{suffix}"
        self._ensure_safe_directory(destination.parent, create=True)
        if self._is_redirecting_path(destination):
            raise CaptureError(
                f"Quarantine destination for {stage!r} may not be a symlink",
                code="unsafe_quarantine_path",
                exit_code=3,
            )
        if self._store_file_exists(
            destination,
            base=self.quarantine,
            role="quarantine_artifact",
        ):
            existing = self._read_store_file(
                destination,
                base=self.quarantine,
                role="quarantine_artifact",
            )
            if sha256_bytes(existing) == sha256_bytes(data):
                return destination
            raise CaptureError(
                f"Stage {stage!r} has a different orphaned quarantined artifact",
                code="quarantine_conflict",
                exit_code=4,
            )
        self._atomic_write(destination, data, exclusive=True)
        return destination

    def record_stage(
        self,
        session_id: str,
        stage: str,
        source_path: Path | str,
        attestations: Mapping[str, Any],
        *,
        note: str = "",
        input_artifacts: Sequence[tuple[str, Path | str]] = (),
    ) -> dict[str, Any]:
        if stage not in STAGES:
            raise CaptureError(f"Unknown stage: {stage}", code="invalid_stage")
        if input_artifacts and stage != "source":
            raise CaptureError(
                "Input artifacts may only be bound while recording the source stage",
                code="invalid_input_artifact_stage",
            )
        normalized_attestations = validate_attestations(stage, attestations)
        source, data = self.read_allowed_file(source_path, role="stage_file")
        inventory = inspect_xml(data)
        digest = sha256_bytes(data)

        with self.mutation_lock(session_id):
            state = self.load_state(session_id)
            self._require_active(state)
            if stage in state["stages"]:
                raise CaptureError(
                    f"Stage {stage!r} is already recorded",
                    code="stage_already_recorded",
                    exit_code=4,
                )
            expected_stage = STAGES[len(state["stages"])]
            if stage != expected_stage:
                raise CaptureError(
                    f"Record stages in order; next required stage is {expected_stage!r}",
                    code="stage_out_of_order",
                    exit_code=4,
                )
            recipe_expected = state["recipe"]["snapshot"]["expected_source_type"]
            if recipe_expected is not None and inventory.source_type != recipe_expected:
                raise CaptureError(
                    f"Recipe expects {recipe_expected}, got {inventory.source_type}",
                    code="source_type_mismatch",
                )
            source_inventory = state["stages"].get("source", {}).get("xml_inventory")
            if (
                source_inventory is not None
                and inventory.source_type != source_inventory["source_type"]
            ):
                raise CaptureError(
                    "All captured stages must have the same Source/@Type",
                    code="source_type_mismatch",
                )
            for previous_stage, previous_record in state["stages"].items():
                previous_source = self.root / previous_record["original_path"]
                try:
                    same_role = source.samefile(previous_source)
                except OSError:
                    same_role = source == previous_source
                if same_role:
                    raise CaptureError(
                        f"{stage} and {previous_stage} must use different source files",
                        code="evidence_role_conflict",
                    )

            input_records = self._capture_input_artifacts(
                input_artifacts,
                source=source,
                recipe_path=self.root / state["recipe"]["source_path"],
            )
            destination = self._quarantine_stage(session_id, stage, source, data)
            warnings: list[str] = []
            if source_inventory is not None and inventory.units != source_inventory["units"]:
                warnings.append("Source/@Units changed between capture stages")

            now = utc_now()
            state["stages"][stage] = {
                "stage": stage,
                "captured_at": now,
                "original_path": str(source.relative_to(self.root)),
                "quarantine_path": str(destination.relative_to(self.root)),
                "sha256": digest,
                "size_bytes": len(data),
                "xml_inventory": inventory.as_dict(),
                "operator_attestations": normalized_attestations,
                "operator_note": note.strip(),
                "warnings": warnings,
            }
            state["stage_sequence"].append(stage)
            if input_records:
                state["input_artifacts"] = input_records
            state["updated_at"] = now
            state["events"].append(
                {"at": now, "kind": "stage_recorded", "detail": stage, "sha256": digest}
            )
            self._write_state(state)
            return dict(state["stages"][stage])

    def answer_checklist(
        self,
        session_id: str,
        item_id: str,
        answer: str,
        *,
        note: str = "",
    ) -> dict[str, Any]:
        if answer not in {"yes", "no", "not_applicable"}:
            raise CaptureError("Checklist answer is invalid", code="invalid_checklist_answer")
        with self.mutation_lock(session_id):
            state = self.load_state(session_id)
            self._require_active(state)
            item = state["checklist"].get(item_id)
            if item is None:
                raise CaptureError(
                    f"Unknown checklist item: {item_id}",
                    code="unknown_checklist_item",
                )
            item_stage = item["stage"]
            if item_stage is not None and item_stage not in state["stages"]:
                raise CaptureError(
                    f"Checklist item {item_id!r} belongs to stage {item_stage!r}, "
                    "which has not been recorded yet",
                    code="checklist_stage_not_recorded",
                    exit_code=4,
                )
            now = utc_now()
            item["answer"] = answer
            item["note"] = note.strip()
            item["answered_at"] = now
            state["updated_at"] = now
            state["events"].append(
                {
                    "at": now,
                    "kind": "checklist_answered",
                    "detail": item_id,
                    "answer": answer,
                }
            )
            self._write_state(state)
            return dict(item)

    def _artifact_integrity_errors(self, state: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        for stage, record in state["stages"].items():
            relative = record.get("quarantine_path")
            if not isinstance(relative, str):
                errors.append(f"{stage}:missing_quarantine_path")
                continue
            candidate = self.root / relative
            try:
                artifact = self._read_store_file(
                    candidate,
                    base=self.quarantine,
                    role="quarantine_artifact",
                )
                actual = sha256_bytes(artifact)
            except CaptureError:
                errors.append(f"{stage}:quarantine_artifact_missing_or_unsafe")
                continue
            if actual != record.get("sha256"):
                errors.append(f"{stage}:quarantine_sha256_mismatch")
        return errors

    def _input_artifact_integrity_errors(self, state: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        records = state.get("input_artifacts")
        if records is None:
            return errors
        assert isinstance(records, list)
        identities: set[tuple[int, int]] = set()
        for record in records:
            role = str(record["role"])
            try:
                actual, identity = self._inspect_input_artifact(role, str(record["path"]))
            except CaptureError:
                errors.append(f"input_artifact:{role}:missing_or_unsafe")
                continue
            if identity in identities:
                errors.append(f"input_artifact:{role}:identity_conflict")
            identities.add(identity)
            if actual["name"] != record["name"]:
                errors.append(f"input_artifact:{role}:name_mismatch")
            if actual["sha256"] != record["sha256"]:
                errors.append(f"input_artifact:{role}:sha256_mismatch")
            if actual["size_bytes"] != record["size_bytes"]:
                errors.append(f"input_artifact:{role}:size_mismatch")
        return errors

    def readiness(self, state: Mapping[str, Any]) -> dict[str, Any]:
        missing_stages = [stage for stage in STAGES if stage not in state["stages"]]
        pending_required = [
            item_id
            for item_id, item in state["checklist"].items()
            if item["required"] and item["answer"] != "yes"
        ]
        integrity_errors = [
            *self._artifact_integrity_errors(state),
            *self._input_artifact_integrity_errors(state),
        ]
        review_blockers: list[str] = []
        if not state["operator_claims"]["redistribution_permitted"]:
            review_blockers.append("redistribution_permission_not_granted")
        for stage, record in state["stages"].items():
            review_blockers.extend(f"{stage}:{warning}" for warning in record["warnings"])
        return {
            "ready_to_finalize": not missing_stages
            and not pending_required
            and not integrity_errors,
            "missing_stages": missing_stages,
            "pending_required_checklist": pending_required,
            "integrity_errors": integrity_errors,
            "review_blockers": review_blockers,
            "next_stage": missing_stages[0] if missing_stages else None,
        }

    def status(self, session_id: str) -> dict[str, Any]:
        state = self.load_state(session_id)
        candidate_integrity_errors: list[str] = []
        candidate = state.get("candidate")
        if isinstance(candidate, dict):
            try:
                manifest_path = self.root / candidate["manifest_path"]
                digest_path = self.root / candidate["digest_path"]
                manifest_bytes = self._read_store_file(
                    manifest_path,
                    base=self.candidates,
                    role="candidate_manifest",
                )
                digest_bytes = self._read_store_file(
                    digest_path,
                    base=self.candidates,
                    role="candidate_digest",
                )
                manifest_sha = sha256_bytes(manifest_bytes)
                expected_digest = f"{manifest_sha}  {manifest_path.name}\n"
                if manifest_sha != candidate["manifest_sha256"]:
                    candidate_integrity_errors.append("candidate_sha256_mismatch")
                if digest_bytes.decode("ascii") != expected_digest:
                    candidate_integrity_errors.append("candidate_digest_mismatch")
            except (KeyError, UnicodeError, CaptureError):
                candidate_integrity_errors.append("candidate_artifact_missing_or_invalid")
        return {
            "session_id": session_id,
            "status": state["status"],
            "recipe_id": state["recipe"]["snapshot"]["recipe_id"],
            "recorded_stages": list(state["stage_sequence"]),
            "readiness": self.readiness(state),
            "candidate": candidate,
            "candidate_integrity_errors": candidate_integrity_errors,
            "updated_at": state["updated_at"],
        }

    def resume(self, session_id: str) -> dict[str, Any]:
        with self.mutation_lock(session_id):
            state = self.load_state(session_id)
            self._require_active(state)
            now = utc_now()
            state["updated_at"] = now
            state["events"].append(
                {"at": now, "kind": "session_resumed", "detail": "State integrity checked"}
            )
            self._write_state(state)
        return self.status(session_id)

    def abort(self, session_id: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise CaptureError("Abort reason is required", code="abort_reason_required")
        with self.mutation_lock(session_id):
            state = self.load_state(session_id)
            self._require_active(state)
            now = utc_now()
            state["status"] = "aborted"
            state["abort_reason"] = reason.strip()
            state["updated_at"] = now
            state["events"].append(
                {
                    "at": now,
                    "kind": "session_aborted",
                    "detail": reason.strip(),
                    "artifacts_preserved": True,
                }
            )
            self._write_state(state)
        return self.status(session_id)

    def _bind_candidate_to_state(
        self,
        state: dict[str, Any],
        *,
        manifest_path: Path,
        manifest_sha: str,
        digest_path: Path,
        event_time: str,
        recovered: bool,
    ) -> dict[str, Any]:
        state["status"] = "candidate_ready"
        state["updated_at"] = event_time
        state["candidate"] = {
            "manifest_path": str(manifest_path.relative_to(self.root)),
            "manifest_sha256": manifest_sha,
            "digest_path": str(digest_path.relative_to(self.root)),
            "review_status": "pending_independent_review",
        }
        state["events"].append(
            {
                "at": event_time,
                "kind": "candidate_recovered" if recovered else "candidate_emitted",
                "detail": str(manifest_path.relative_to(self.root)),
                "sha256": manifest_sha,
                "trust_grant": "none",
            }
        )
        self._write_state(state)
        return dict(state["candidate"])

    def _recover_candidate(
        self,
        state: dict[str, Any],
        manifest_path: Path,
        digest_path: Path,
    ) -> dict[str, Any]:
        """Finish a finalize operation interrupted after the manifest write."""

        manifest_bytes = self._read_store_file(
            manifest_path,
            base=self.candidates,
            role="candidate_manifest",
        )
        candidate = _strict_json_bytes(manifest_bytes, role="candidate_manifest")
        required_matches = (
            candidate.get("schema_version") == CANDIDATE_SCHEMA
            and candidate.get("session_id") == state["session_id"]
            and candidate.get("authority") == "operator_supplied_unverified"
            and candidate.get("trust_grant") == "none"
            and candidate.get("candidate_only") is True
            and candidate.get("filesystem_safety")
            == {
                "mode": self.path_safety_mode,
                "race_resistant": self._root_fd is not None,
            }
            and candidate.get("recipe") == state["recipe"]
            and candidate.get("operator_claims") == state["operator_claims"]
            and candidate.get("stage_sequence") == state["stage_sequence"]
            and candidate.get("stages") == state["stages"]
            and candidate.get("checklist") == state["checklist"]
            and candidate.get("input_artifacts") == state.get("input_artifacts")
        )
        if not required_matches:
            raise CaptureError(
                "Existing candidate manifest is not bound to this session state",
                code="candidate_recovery_mismatch",
                exit_code=3,
            )
        manifest_sha = sha256_bytes(manifest_bytes)
        expected_digest = f"{manifest_sha}  {manifest_path.name}\n".encode("ascii")
        if self._store_file_exists(
            digest_path,
            base=self.candidates,
            role="candidate_digest",
        ):
            existing_digest = self._read_store_file(
                digest_path,
                base=self.candidates,
                role="candidate_digest",
            )
            if existing_digest != expected_digest:
                raise CaptureError(
                    "Existing candidate digest does not match the manifest",
                    code="candidate_digest_mismatch",
                    exit_code=3,
                )
        else:
            self._atomic_write(digest_path, expected_digest, exclusive=True)
        return self._bind_candidate_to_state(
            state,
            manifest_path=manifest_path,
            manifest_sha=manifest_sha,
            digest_path=digest_path,
            event_time=utc_now(),
            recovered=True,
        )

    def finalize(self, session_id: str) -> dict[str, Any]:
        with self.mutation_lock(session_id):
            state = self.load_state(session_id)
            manifest_path = self.candidates / f"{session_id}.candidate.json"
            digest_path = self.candidates / f"{session_id}.candidate.json.sha256"
            if state["status"] == "candidate_ready":
                input_errors = self._input_artifact_integrity_errors(state)
                if input_errors:
                    raise CaptureError(
                        "Private input artifacts changed after finalization",
                        code="input_artifact_integrity_error",
                        exit_code=3,
                    )
                manifest_bytes = self._read_store_file(
                    manifest_path,
                    base=self.candidates,
                    role="candidate_manifest",
                )
                manifest_sha = sha256_bytes(manifest_bytes)
                if manifest_sha != state["candidate"]["manifest_sha256"]:
                    raise CaptureError(
                        "Candidate manifest changed after finalization",
                        code="candidate_sha256_mismatch",
                        exit_code=3,
                    )
                expected_digest = f"{manifest_sha}  {manifest_path.name}\n"
                digest_bytes = self._read_store_file(
                    digest_path,
                    base=self.candidates,
                    role="candidate_digest",
                )
                if digest_bytes.decode("ascii") != expected_digest:
                    raise CaptureError(
                        "Candidate digest changed after finalization",
                        code="candidate_digest_mismatch",
                        exit_code=3,
                    )
                return dict(state["candidate"])
            self._require_active(state)
            readiness = self.readiness(state)
            if not readiness["ready_to_finalize"]:
                raise CaptureError(
                    "Capture is incomplete; inspect status for missing stages/checklist items",
                    code="capture_incomplete",
                    exit_code=4,
                )
            if self._store_file_exists(
                manifest_path,
                base=self.candidates,
                role="candidate_manifest",
            ):
                return self._recover_candidate(state, manifest_path, digest_path)
            now = utc_now()
            candidate: dict[str, Any] = {
                "schema_version": CANDIDATE_SCHEMA,
                "session_id": session_id,
                "created_at": now,
                "authority": "operator_supplied_unverified",
                "trust_grant": "none",
                "candidate_only": True,
                "review_status": "pending_independent_review",
                "requires_independent_review": True,
                "must_not_copy_to_acceptance_without_review": True,
                "filesystem_safety": {
                    "mode": self.path_safety_mode,
                    "race_resistant": self._root_fd is not None,
                },
                "eligible_for_registry_review": not readiness["review_blockers"],
                "review_blockers": readiness["review_blockers"],
                "recipe": state["recipe"],
                "operator_claims": state["operator_claims"],
                "stage_sequence": state["stage_sequence"],
                "stages": state["stages"],
                "checklist": state["checklist"],
                "capture_invariants": {
                    "stages_recorded_in_order": state["stage_sequence"] == list(STAGES),
                    "all_sha256_bound": all(
                        SHA256_RE.fullmatch(record["sha256"]) is not None
                        for record in state["stages"].values()
                    ),
                    "source_type_consistent": len(
                        {
                            record["xml_inventory"]["source_type"]
                            for record in state["stages"].values()
                        }
                    )
                    == 1,
                    "artifacts_quarantined": True,
                    "trust_promoted_by_capture_tool": False,
                },
            }
            if state.get("input_artifacts"):
                candidate["input_artifacts"] = state["input_artifacts"]
            manifest_bytes = canonical_json_bytes(candidate)
            self._atomic_write(manifest_path, manifest_bytes, exclusive=True)
            manifest_sha = sha256_bytes(manifest_bytes)
            self._atomic_write(
                digest_path,
                f"{manifest_sha}  {manifest_path.name}\n".encode("ascii"),
                exclusive=True,
            )
            return self._bind_candidate_to_state(
                state,
                manifest_path=manifest_path,
                manifest_sha=manifest_sha,
                digest_path=digest_path,
                event_time=now,
                recovered=False,
            )


def _load_json_within(repository: CaptureRepository, path: str, *, role: str) -> dict[str, Any]:
    _resolved, raw = repository.read_allowed_file(path, role=role)
    return _strict_json_bytes(raw, role=role)


def _print_result(value: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
        return
    status = value.get("status")
    if status is not None:
        print(f"Session {value.get('session_id')}: {status}")
        readiness = value.get("readiness")
        if isinstance(readiness, dict):
            if readiness.get("next_stage"):
                print(f"Next stage: {readiness['next_stage']}")
            pending = readiness.get("pending_required_checklist", [])
            if pending:
                print(f"Required checklist items: {', '.join(pending)}")
            blockers = readiness.get("review_blockers", [])
            if blockers:
                print(f"Review blockers: {len(blockers)}")
        return
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _add_common(command: argparse.ArgumentParser) -> None:
    command.add_argument("--root", required=True, help="Allowed capture root")
    command.add_argument("--session", required=True, help="Safe capture session id")
    command.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def _parse_input_artifact_specs(values: Sequence[str]) -> list[tuple[str, str]]:
    specifications: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise CaptureError(
                "--input-artifact must use ROLE=PATH",
                code="invalid_input_artifact",
            )
        role, path = value.split("=", 1)
        if ITEM_RE.fullmatch(role) is None or not path:
            raise CaptureError(
                "--input-artifact must use a safe lowercase ROLE and non-empty PATH",
                code="invalid_input_artifact",
            )
        specifications.append((role, path))
    return specifications


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect operator-supplied DipTrace XML into quarantine and emit a "
            "review-only candidate manifest. This command never grants fixture trust."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a resumable capture session")
    _add_common(init)
    init.add_argument("--recipe", required=True, help="Recipe JSON inside the allowed root")
    init.add_argument("--answers", help="Non-interactive answers JSON inside the allowed root")
    init.add_argument("--non-interactive", action="store_true")

    record = subparsers.add_parser("record", help="Validate and quarantine the next stage")
    _add_common(record)
    record.add_argument("--stage", choices=STAGES, required=True)
    record.add_argument("--file", required=True, help="Stage file inside the allowed root")
    record.add_argument("--attestations", help="Non-interactive attestation JSON")
    record.add_argument("--note", default="")
    record.add_argument(
        "--input-artifact",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help=(
            "Bind private source-input metadata by role; repeatable and valid only "
            "for --stage source. Bytes remain at PATH and are never quarantined."
        ),
    )
    record.add_argument("--non-interactive", action="store_true")

    check = subparsers.add_parser("check", help="Answer one recipe checklist item")
    _add_common(check)
    check.add_argument("--item", required=True)
    check.add_argument("--answer", choices=("yes", "no", "not_applicable"), required=True)
    check.add_argument("--note", default="")

    for name, help_text in (
        ("status", "Show progress and the next required action"),
        ("resume", "Validate persistent state and resume after interruption"),
        ("finalize", "Emit a review-only candidate manifest"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        _add_common(command)

    abort = subparsers.add_parser("abort", help="Abort without deleting captured evidence")
    _add_common(abort)
    abort.add_argument("--reason")
    abort.add_argument("--non-interactive", action="store_true")
    return parser


def run_cli(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    repository = CaptureRepository(args.root)

    if args.command == "init":
        if args.non_interactive:
            if not args.answers:
                raise CaptureError(
                    "--answers is required with --non-interactive",
                    code="answers_required",
                )
            answers = _load_json_within(repository, args.answers, role="answers")
        else:
            if args.answers:
                raise CaptureError(
                    "--answers requires --non-interactive",
                    code="unexpected_answers",
                )
            answers = _interactive_answers()
        result = repository.init_session(args.session, args.recipe, answers)
        _print_result(repository.status(args.session), as_json=args.json)
        return 0

    if args.command == "record":
        if args.non_interactive:
            if not args.attestations:
                raise CaptureError(
                    "--attestations is required with --non-interactive",
                    code="attestations_required",
                )
            attestations = _load_json_within(
                repository, args.attestations, role="attestations"
            )
        else:
            if args.attestations:
                raise CaptureError(
                    "--attestations requires --non-interactive",
                    code="unexpected_attestations",
                )
            attestations = _interactive_attestations(args.stage)
        result = repository.record_stage(
            args.session,
            args.stage,
            args.file,
            attestations,
            note=args.note,
            input_artifacts=_parse_input_artifact_specs(args.input_artifact),
        )
        _print_result(result, as_json=args.json)
        return 0

    if args.command == "check":
        result = repository.answer_checklist(
            args.session,
            args.item,
            args.answer,
            note=args.note,
        )
        _print_result(result, as_json=args.json)
        return 0

    if args.command == "status":
        _print_result(repository.status(args.session), as_json=args.json)
        return 0

    if args.command == "resume":
        _print_result(repository.resume(args.session), as_json=args.json)
        return 0

    if args.command == "abort":
        reason = args.reason
        if args.non_interactive and not reason:
            raise CaptureError(
                "--reason is required with --non-interactive",
                code="abort_reason_required",
            )
        if not args.non_interactive and reason is None:
            reason = input("Reason for abort (artifacts will be preserved): ").strip()
        _print_result(repository.abort(args.session, reason or ""), as_json=args.json)
        return 0

    if args.command == "finalize":
        result = repository.finalize(args.session)
        _print_result(result, as_json=args.json)
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


def main() -> NoReturn:
    try:
        exit_code = run_cli()
    except CaptureError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": str(exc)}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(exc.exit_code) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
