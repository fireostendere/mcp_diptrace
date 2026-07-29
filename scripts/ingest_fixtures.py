#!/usr/bin/env python3
"""Validate captured DipTrace evidence and produce a non-mutating ingest plan.

The repository has a code-reviewed, package-owned trust registry, but its
production file currently has no approved entries.  This command deliberately
has no apply implementation: it validates candidate integrity, inspects the
embedded registry, and reports deterministic destinations/conflicts, but never
writes a fixture or grants a validation level.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from capture_diptrace_evidence import (
    CANDIDATE_SCHEMA,
    INPUT_ARTIFACT_KEYS,
    ITEM_RE,
    MAX_INPUT_ARTIFACT_BYTES,
    MAX_INPUT_ARTIFACTS,
    MAX_XML_BYTES,
    SOURCE_TYPES,
    STAGES,
    STORE_NAME,
    CaptureError,
    _validate_answers,
    canonical_json_bytes,
    inspect_xml,
    sha256_bytes,
    validate_attestations,
    validate_recipe,
)

from diptrace_mcp.provenance_registry import TrustedProvenanceRegistry

PLAN_SCHEMA = "diptrace-ingest-plan-v1"
PENDING_RECEIPT_SCHEMA = "diptrace-ingest-pending-v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_DIGEST_BYTES = 512
MAX_DESTINATION_ENTRIES = 10_000
SECURE_CONFINED_OPEN_AVAILABLE = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
)
INGEST_PATH_SAFETY_MODE = (
    "descriptor_relative_posix"
    if SECURE_CONFINED_OPEN_AVAILABLE
    else "cooperative_identity_checks"
)
SESSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
FIXTURE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_SUFFIXES = {
    "DipTrace-PCB": frozenset({".xml", ".dip"}),
    "DipTrace-Schematic": frozenset({".xml", ".dch"}),
    "DipTrace-ComponentLibrary": frozenset({".xml", ".eli"}),
    "DipTrace-PatternLibrary": frozenset({".xml", ".lib"}),
}
TOP_LEVEL_KEYS = {
    "schema_version",
    "session_id",
    "created_at",
    "authority",
    "trust_grant",
    "candidate_only",
    "review_status",
    "requires_independent_review",
    "must_not_copy_to_acceptance_without_review",
    "filesystem_safety",
    "eligible_for_registry_review",
    "review_blockers",
    "recipe",
    "operator_claims",
    "stage_sequence",
    "stages",
    "checklist",
    "capture_invariants",
}
OPTIONAL_TOP_LEVEL_KEYS = {"input_artifacts"}
STAGE_KEYS = {
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
}
INVENTORY_KEYS = {
    "source_type",
    "version",
    "units",
    "root_tag",
    "element_count",
    "element_counts",
    "direct_child_counts",
}
CHECKLIST_KEYS = {"prompt", "required", "stage", "answer", "note", "answered_at"}
CAPTURE_INVARIANT_KEYS = {
    "stages_recorded_in_order",
    "all_sha256_bound",
    "source_type_consistent",
    "artifacts_quarantined",
    "trust_promoted_by_capture_tool",
}
SYNTHETIC_SESSION = "ci-synthetic-stand-in"
SYNTHETIC_FIXTURE_ID = "ci-synthetic-stand-in"
SYNTHETIC_TIMESTAMP = "2000-01-01T00:00:00Z"


class IngestError(Exception):
    """A typed, fail-closed ingest error."""

    def __init__(self, message: str, *, code: str, exit_code: int = 3) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


@dataclass(frozen=True)
class Artifact:
    role: str
    relative_path: Path
    sha256: str
    source_type: str


@dataclass(frozen=True)
class InputArtifact:
    role: str
    name: str
    relative_path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ValidatedCandidate:
    manifest: dict[str, Any]
    manifest_relative_path: Path
    manifest_bytes: bytes
    manifest_sha256: str
    digest_bytes: bytes
    artifacts: tuple[Artifact, ...]
    input_artifacts: tuple[InputArtifact, ...]


def _fail(message: str, code: str) -> NoReturn:
    raise IngestError(message, code=code)


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], *, field: str) -> None:
    if set(value) != keys:
        missing = sorted(keys - set(value))
        unknown = sorted(set(value) - keys)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unknown:
            detail.append(f"unknown={','.join(unknown)}")
        _fail(f"{field} has invalid fields ({'; '.join(detail)})", "candidate_schema_invalid")


def _require_nonempty_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{field} must be a non-empty string", "candidate_schema_invalid")
    return value


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256", "candidate_schema_invalid")
    return value


def _safe_relative_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"{field} must be a non-empty relative path", "unsafe_candidate_path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{field} must be a contained relative path", "unsafe_candidate_path")
    if os.name != "nt" and "\\" in value:
        _fail(f"{field} uses a foreign path separator", "unsafe_candidate_path")
    return path


def _strict_json(raw: bytes, *, role: str) -> dict[str, Any]:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{role} contains duplicate key {key!r}", "candidate_invalid_json")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=object_hook)
    except IngestError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IngestError(
            f"{role} is not strict UTF-8 JSON: {exc}",
            code="candidate_invalid_json",
        ) from exc
    if not isinstance(value, dict):
        _fail(f"{role} must contain one JSON object", "candidate_invalid_json")
    return value


def _existing_root(value: str | Path, *, role: str) -> Path:
    path = Path(value)
    try:
        if path.is_symlink():
            _fail(f"{role} may not be a symlink", "unsafe_root")
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise IngestError(f"Cannot resolve {role}: {exc}", code="unsafe_root") from exc
    if not resolved.is_dir():
        _fail(f"{role} must be an existing directory", "unsafe_root")
    return resolved


def _is_redirecting_path(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _path_snapshot(
    root: Path,
    relative: Path,
    *,
    role: str,
    forbidden_directory_identity: tuple[int, int] | None,
) -> tuple[tuple[int, int, int], ...]:
    """Snapshot a cooperative path walk used where descriptor-relative open is unavailable."""

    snapshots: list[tuple[int, int, int]] = []
    current = root
    paths = (
        root,
        *(
            root / Path(*relative.parts[:index])
            for index in range(1, len(relative.parts) + 1)
        ),
    )
    for index, current in enumerate(paths):
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise IngestError(f"Cannot read {role}: {exc}", code="candidate_file_missing") from exc
        if _is_redirecting_path(current):
            _fail(f"{role} contains a symlink or junction", "unsafe_candidate_path")
        is_final = index == len(paths) - 1
        if not is_final and not stat.S_ISDIR(metadata.st_mode):
            _fail(f"{role} has a non-directory parent", "unsafe_candidate_path")
        identity = (metadata.st_dev, metadata.st_ino)
        if (
            forbidden_directory_identity is not None
            and not is_final
            and identity == forbidden_directory_identity
        ):
            _fail(f"{role} points into the capture store", "candidate_role_conflict")
        snapshots.append((metadata.st_dev, metadata.st_ino, metadata.st_mode))
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise IngestError(f"{role} escapes the capture root", code="unsafe_candidate_path") from exc
    return tuple(snapshots)


def _open_confined_descriptor(
    root: Path,
    relative: Path,
    *,
    role: str,
    forbidden_directory_identity: tuple[int, int] | None,
) -> tuple[int, tuple[tuple[int, int, int], ...] | None]:
    if not relative.parts:
        _fail(f"{role} must be a file", "unsafe_candidate_path")
    file_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    file_flags |= getattr(os, "O_CLOEXEC", 0)
    if SECURE_CONFINED_OPEN_AVAILABLE:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory_flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            expected_root = os.stat(root, follow_symlinks=False)
            current_fd = os.open(root, directory_flags)
        except OSError as exc:
            raise IngestError(f"Cannot pin capture root: {exc}", code="unsafe_root") from exc
        try:
            actual_root = os.fstat(current_fd)
            if (expected_root.st_dev, expected_root.st_ino) != (
                actual_root.st_dev,
                actual_root.st_ino,
            ):
                _fail("Capture root changed while it was opened", "unsafe_root")
            for part in relative.parts[:-1]:
                try:
                    next_fd = os.open(part, directory_flags, dir_fd=current_fd)
                except FileNotFoundError as exc:
                    raise IngestError(
                        f"Cannot read {role}: {exc}",
                        code="candidate_file_missing",
                    ) from exc
                except OSError as exc:
                    raise IngestError(
                        f"{role} contains an unsafe directory component: {exc}",
                        code="unsafe_candidate_path",
                    ) from exc
                os.close(current_fd)
                current_fd = next_fd
                metadata = os.fstat(current_fd)
                if not stat.S_ISDIR(metadata.st_mode):
                    _fail(f"{role} has a non-directory parent", "unsafe_candidate_path")
                if (
                    forbidden_directory_identity is not None
                    and (metadata.st_dev, metadata.st_ino) == forbidden_directory_identity
                ):
                    _fail(f"{role} points into the capture store", "candidate_role_conflict")
            try:
                descriptor = os.open(
                    relative.parts[-1],
                    file_flags | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
            except FileNotFoundError as exc:
                raise IngestError(
                    f"Cannot read {role}: {exc}",
                    code="candidate_file_missing",
                ) from exc
            except OSError as exc:
                raise IngestError(
                    f"Cannot open {role}: {exc}",
                    code="unsafe_candidate_path",
                ) from exc
            return descriptor, None
        finally:
            with suppress(OSError):
                os.close(current_fd)

    before_paths = _path_snapshot(
        root,
        relative,
        role=role,
        forbidden_directory_identity=forbidden_directory_identity,
    )
    try:
        descriptor = os.open(root / relative, file_flags | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise IngestError(f"Cannot open {role}: {exc}", code="candidate_file_missing") from exc
    return descriptor, before_paths


def _read_confined_file(
    root: Path,
    relative: Path,
    *,
    role: str,
    max_bytes: int,
    reject_hardlinks: bool = False,
    seen_identities: set[tuple[int, int]] | None = None,
    forbidden_directory_identity: tuple[int, int] | None = None,
) -> bytes:
    descriptor, before_paths = _open_confined_descriptor(
        root,
        relative,
        role=role,
        forbidden_directory_identity=forbidden_directory_identity,
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{role} must be a regular file", "unsafe_candidate_path")
        if reject_hardlinks and before.st_nlink != 1:
            _fail(f"{role} has a hard-link alias", "candidate_role_conflict")
        identity = (before.st_dev, before.st_ino)
        if seen_identities is not None and identity in seen_identities:
            _fail(f"{role} reuses another filesystem object", "candidate_role_conflict")
        if before.st_size > max_bytes:
            _fail(f"{role} exceeds the {max_bytes}-byte limit", "candidate_file_too_large")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if before_paths is not None:
            after_paths = _path_snapshot(
                root,
                relative,
                role=role,
                forbidden_directory_identity=forbidden_directory_identity,
            )
            if before_paths != after_paths:
                _fail(f"{role} path changed while it was being read", "candidate_file_changed")
    finally:
        os.close(descriptor)
    if len(data) > max_bytes:
        _fail(f"{role} exceeds the {max_bytes}-byte limit", "candidate_file_too_large")
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    )
    if (
        identity_before != identity_after
        or len(data) != after.st_size
        or (reject_hardlinks and after.st_nlink != 1)
    ):
        _fail(f"{role} changed while it was being read", "candidate_file_changed")
    if seen_identities is not None:
        seen_identities.add((after.st_dev, after.st_ino))
    return data


def _record_confined_identity_if_present(
    root: Path,
    relative: Path,
    *,
    role: str,
    identities: set[tuple[int, int]],
) -> None:
    try:
        descriptor, before_paths = _open_confined_descriptor(
            root,
            relative,
            role=role,
            forbidden_directory_identity=None,
        )
    except IngestError as exc:
        if exc.code == "candidate_file_missing":
            return
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{role} must be a regular file", "unsafe_candidate_path")
        if before_paths is not None:
            after_paths = _path_snapshot(
                root,
                relative,
                role=role,
                forbidden_directory_identity=None,
            )
            if before_paths != after_paths:
                _fail(f"{role} path changed while it was inspected", "candidate_file_changed")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(f"{role} changed while it was inspected", "candidate_file_changed")
        identities.add((after.st_dev, after.st_ino))
    finally:
        os.close(descriptor)


def _validate_recipe_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("recipe must be an object", "candidate_schema_invalid")
    _require_exact_keys(
        value,
        {"source_path", "source_sha256", "snapshot"},
        field="recipe",
    )
    source_path = _safe_relative_path(value["source_path"], field="recipe.source_path")
    if source_path.parts[0] == STORE_NAME:
        _fail("recipe.source_path may not point into the capture store", "unsafe_candidate_path")
    _require_sha256(value["source_sha256"], field="recipe.source_sha256")
    snapshot = value["snapshot"]
    if not isinstance(snapshot, dict):
        _fail("recipe.snapshot must be an object", "candidate_schema_invalid")
    try:
        normalized = validate_recipe(snapshot)
    except CaptureError as exc:
        raise IngestError(
            f"recipe.snapshot is invalid: {exc}",
            code="candidate_schema_invalid",
        ) from exc
    if normalized != snapshot:
        _fail("recipe.snapshot is not normalized", "candidate_schema_invalid")
    return normalized


def _validate_checklist(value: Any, recipe: Mapping[str, Any]) -> None:
    if not isinstance(value, dict):
        _fail("checklist must be an object", "candidate_schema_invalid")
    expected = {item["id"]: item for item in recipe["operator_checklist"]}
    if set(value) != set(expected):
        _fail("checklist does not match the recipe", "candidate_schema_invalid")
    for item_id, recipe_item in expected.items():
        record = value[item_id]
        if not isinstance(record, dict):
            _fail(f"checklist.{item_id} must be an object", "candidate_schema_invalid")
        _require_exact_keys(record, CHECKLIST_KEYS, field=f"checklist.{item_id}")
        for key in ("prompt", "required", "stage"):
            if record[key] != recipe_item[key]:
                _fail(
                    f"checklist.{item_id}.{key} does not match the recipe",
                    "candidate_schema_invalid",
                )
        answer = record["answer"]
        if answer not in {"yes", "no", "not_applicable"}:
            _fail(
                f"checklist.{item_id} is not answered",
                "candidate_review_incomplete",
            )
        if record["required"] and answer != "yes":
            _fail(
                f"required checklist item {item_id!r} is not confirmed",
                "candidate_review_incomplete",
            )
        if not isinstance(record["note"], str):
            _fail(f"checklist.{item_id}.note must be text", "candidate_schema_invalid")
        _require_nonempty_text(
            record["answered_at"],
            field=f"checklist.{item_id}.answered_at",
        )


def _validate_counter(value: Any, *, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        _fail(f"{field} must be an object", "candidate_schema_invalid")
    result: dict[str, int] = {}
    for key, count in value.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            _fail(f"{field} contains an invalid count", "candidate_schema_invalid")
        result[key] = count
    return result


def _validate_stored_inventory(value: Any, *, stage: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"stages.{stage}.xml_inventory must be an object", "candidate_schema_invalid")
    _require_exact_keys(value, INVENTORY_KEYS, field=f"stages.{stage}.xml_inventory")
    if value["source_type"] not in SOURCE_TYPES or value["root_tag"] != "Source":
        _fail(f"stages.{stage} has invalid XML identity", "candidate_schema_invalid")
    if value["version"] is not None and not isinstance(value["version"], str):
        _fail(f"stages.{stage} has invalid XML version", "candidate_schema_invalid")
    if value["units"] not in {"mm", "inch", "mil", None}:
        _fail(f"stages.{stage} has invalid XML units", "candidate_schema_invalid")
    counts = _validate_counter(
        value["element_counts"],
        field=f"stages.{stage}.xml_inventory.element_counts",
    )
    _validate_counter(
        value["direct_child_counts"],
        field=f"stages.{stage}.xml_inventory.direct_child_counts",
    )
    count = value["element_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count != sum(counts.values()):
        _fail(f"stages.{stage} has inconsistent element_count", "candidate_schema_invalid")
    return dict(value)


def _validate_stage(
    capture_root: Path,
    session_id: str,
    stage: str,
    value: Any,
    *,
    protocol_identities: set[tuple[int, int]],
) -> Artifact:
    if not isinstance(value, dict):
        _fail(f"stages.{stage} must be an object", "candidate_schema_invalid")
    _require_exact_keys(value, STAGE_KEYS, field=f"stages.{stage}")
    if value["stage"] != stage:
        _fail(f"stages.{stage}.stage is inconsistent", "candidate_schema_invalid")
    _require_nonempty_text(value["captured_at"], field=f"stages.{stage}.captured_at")
    original = _safe_relative_path(
        value["original_path"],
        field=f"stages.{stage}.original_path",
    )
    if original.parts[0] == STORE_NAME:
        _fail(
            f"stages.{stage}.original_path points into the capture store",
            "unsafe_candidate_path",
        )
    quarantine = _safe_relative_path(
        value["quarantine_path"],
        field=f"stages.{stage}.quarantine_path",
    )
    expected_parent = Path(STORE_NAME) / "quarantine" / session_id / stage
    if quarantine.parent != expected_parent:
        _fail(
            f"stages.{stage}.quarantine_path is outside its exact role directory",
            "unsafe_candidate_path",
        )
    expected_sha = _require_sha256(value["sha256"], field=f"stages.{stage}.sha256")
    size = value["size_bytes"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        _fail(f"stages.{stage}.size_bytes is invalid", "candidate_schema_invalid")
    stored_inventory = _validate_stored_inventory(value["xml_inventory"], stage=stage)
    try:
        attestations = validate_attestations(stage, value["operator_attestations"])
    except CaptureError as exc:
        raise IngestError(
            f"stages.{stage}.operator_attestations are invalid: {exc}",
            code="candidate_schema_invalid",
        ) from exc
    if attestations != value["operator_attestations"]:
        _fail(
            f"stages.{stage}.operator_attestations are not normalized",
            "candidate_schema_invalid",
        )
    if not isinstance(value["operator_note"], str):
        _fail(f"stages.{stage}.operator_note must be text", "candidate_schema_invalid")
    if value["warnings"] != []:
        _fail(f"stages.{stage} has unresolved warnings", "candidate_review_blocked")

    data = _read_confined_file(
        capture_root,
        quarantine,
        role=f"{stage} quarantine artifact",
        max_bytes=MAX_XML_BYTES,
        seen_identities=protocol_identities,
    )
    actual_sha = sha256_bytes(data)
    if actual_sha != expected_sha:
        _fail(f"stages.{stage} SHA-256 does not match", "candidate_artifact_sha256_mismatch")
    if len(data) != size:
        _fail(f"stages.{stage} byte size does not match", "candidate_artifact_size_mismatch")
    try:
        actual_inventory = inspect_xml(data).as_dict()
    except CaptureError as exc:
        raise IngestError(
            f"stages.{stage} is not safe DipTrace XML: {exc}",
            code="candidate_artifact_invalid",
        ) from exc
    if actual_inventory != stored_inventory:
        _fail(
            f"stages.{stage} XML inventory does not match captured metadata",
            "candidate_inventory_mismatch",
        )
    source_type = actual_inventory["source_type"]
    if quarantine.suffix.lower() not in ALLOWED_SUFFIXES[source_type]:
        _fail(
            f"stages.{stage} suffix is invalid for {source_type}",
            "candidate_artifact_invalid",
        )
    return Artifact(
        role=stage,
        relative_path=quarantine,
        sha256=actual_sha,
        source_type=source_type,
    )


def _validate_input_artifacts(
    capture_root: Path,
    value: Any,
    *,
    forbidden_paths: set[Path],
    protocol_identities: set[tuple[int, int]],
    store_identity: tuple[int, int],
) -> tuple[InputArtifact, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value or len(value) > MAX_INPUT_ARTIFACTS:
        _fail(
            f"input_artifacts must contain 1-{MAX_INPUT_ARTIFACTS} metadata entries",
            "candidate_schema_invalid",
        )
    artifacts: list[InputArtifact] = []
    roles: set[str] = set()
    names: set[str] = set()
    paths: set[Path] = set()
    identities: set[tuple[int, int]] = set()
    for index, raw in enumerate(value):
        field = f"input_artifacts[{index}]"
        if not isinstance(raw, dict):
            _fail(f"{field} must be an object", "candidate_schema_invalid")
        _require_exact_keys(raw, INPUT_ARTIFACT_KEYS, field=field)
        role = raw["role"]
        if not isinstance(role, str) or ITEM_RE.fullmatch(role) is None:
            _fail(f"{field}.role must be a safe lowercase slug", "candidate_schema_invalid")
        name = raw["name"]
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
            _fail(f"{field}.name must be one safe basename", "candidate_schema_invalid")
        raw_path = raw["path"]
        if not isinstance(raw_path, str) or "\\" in raw_path:
            _fail(f"{field}.path must use canonical forward slashes", "unsafe_candidate_path")
        relative = _safe_relative_path(raw_path, field=f"{field}.path")
        if raw_path != relative.as_posix() or relative.name != name:
            _fail(
                f"{field}.path is not a canonical private input path",
                "unsafe_candidate_path",
            )
        expected_sha = _require_sha256(raw["sha256"], field=f"{field}.sha256")
        size = raw["size_bytes"]
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_INPUT_ARTIFACT_BYTES
        ):
            _fail(f"{field}.size_bytes is invalid", "candidate_schema_invalid")
        if role in roles or name in names or relative in paths:
            _fail(
                "input_artifacts contains a duplicate role, name, or path",
                "candidate_role_conflict",
            )
        if relative in forbidden_paths:
            _fail(
                f"{field}.path reuses a recipe or XML stage path",
                "candidate_role_conflict",
            )
        identities_before = set(protocol_identities)
        data = _read_confined_file(
            capture_root,
            relative,
            role=f"private input artifact {role}",
            max_bytes=MAX_INPUT_ARTIFACT_BYTES,
            reject_hardlinks=True,
            seen_identities=protocol_identities,
            forbidden_directory_identity=store_identity,
        )
        new_identities = protocol_identities - identities_before
        if len(new_identities) != 1:
            _fail(f"{field}.path identity is ambiguous", "candidate_role_conflict")
        identity = next(iter(new_identities))
        if identity in identities:
            _fail(
                f"{field}.path reuses another private input identity",
                "candidate_role_conflict",
            )
        actual_sha = sha256_bytes(data)
        if actual_sha != expected_sha:
            _fail(
                f"input_artifacts role {role!r} SHA-256 does not match",
                "candidate_artifact_sha256_mismatch",
            )
        if len(data) != size:
            _fail(
                f"input_artifacts role {role!r} byte size does not match",
                "candidate_artifact_size_mismatch",
            )
        roles.add(role)
        names.add(name)
        paths.add(relative)
        identities.add(identity)
        artifacts.append(
            InputArtifact(
                role=role,
                name=name,
                relative_path=relative,
                sha256=actual_sha,
                size_bytes=size,
            )
        )
    expected_order = sorted(
        artifacts,
        key=lambda item: (item.role, item.name, item.relative_path.as_posix()),
    )
    if artifacts != expected_order:
        _fail("input_artifacts is not in canonical order", "candidate_not_canonical")
    return tuple(artifacts)


def validate_candidate(capture_root: Path, manifest_relative: Path) -> ValidatedCandidate:
    expected_candidates = Path(STORE_NAME) / "candidates"
    if manifest_relative.parent != expected_candidates:
        _fail(
            "Candidate manifest must be in the capture candidates directory",
            "unsafe_candidate_path",
        )
    if not manifest_relative.name.endswith(".candidate.json"):
        _fail("Candidate manifest name must end in .candidate.json", "unsafe_candidate_path")

    protocol_identities: set[tuple[int, int]] = set()
    manifest_bytes = _read_confined_file(
        capture_root,
        manifest_relative,
        role="candidate manifest",
        max_bytes=MAX_MANIFEST_BYTES,
        seen_identities=protocol_identities,
    )
    manifest_sha = sha256_bytes(manifest_bytes)
    digest_relative = manifest_relative.with_name(manifest_relative.name + ".sha256")
    digest_bytes = _read_confined_file(
        capture_root,
        digest_relative,
        role="candidate digest",
        max_bytes=MAX_DIGEST_BYTES,
        seen_identities=protocol_identities,
    )
    expected_digest = f"{manifest_sha}  {manifest_relative.name}\n".encode("ascii")
    if digest_bytes != expected_digest:
        _fail("Detached candidate digest does not match the manifest", "candidate_digest_mismatch")

    manifest = _strict_json(manifest_bytes, role="candidate manifest")
    if canonical_json_bytes(manifest) != manifest_bytes:
        _fail("Candidate manifest is not in canonical capture form", "candidate_not_canonical")
    manifest_keys = set(manifest)
    if not TOP_LEVEL_KEYS.issubset(manifest_keys) or (
        manifest_keys - TOP_LEVEL_KEYS - OPTIONAL_TOP_LEVEL_KEYS
    ):
        missing = sorted(TOP_LEVEL_KEYS - manifest_keys)
        unknown = sorted(manifest_keys - TOP_LEVEL_KEYS - OPTIONAL_TOP_LEVEL_KEYS)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unknown:
            detail.append(f"unknown={','.join(unknown)}")
        _fail(
            f"candidate has invalid fields ({'; '.join(detail)})",
            "candidate_schema_invalid",
        )
    if manifest["schema_version"] != CANDIDATE_SCHEMA:
        _fail("Candidate schema_version is unsupported", "candidate_schema_invalid")
    session_id = manifest["session_id"]
    if not isinstance(session_id, str) or SESSION_RE.fullmatch(session_id) is None:
        _fail("Candidate session_id is invalid", "candidate_schema_invalid")
    if manifest_relative.name != f"{session_id}.candidate.json":
        _fail("Candidate filename does not match session_id", "candidate_schema_invalid")
    _require_nonempty_text(manifest["created_at"], field="created_at")
    constants = {
        "authority": "operator_supplied_unverified",
        "trust_grant": "none",
        "candidate_only": True,
        "review_status": "pending_independent_review",
        "requires_independent_review": True,
        "must_not_copy_to_acceptance_without_review": True,
    }
    for field, expected in constants.items():
        if manifest[field] != expected:
            _fail(f"Candidate trust boundary field {field!r} changed", "candidate_trust_boundary")
    filesystem_safety = manifest["filesystem_safety"]
    if not isinstance(filesystem_safety, dict):
        _fail("filesystem_safety must be an object", "candidate_schema_invalid")
    _require_exact_keys(
        filesystem_safety,
        {"mode", "race_resistant"},
        field="filesystem_safety",
    )
    if (
        filesystem_safety["mode"],
        filesystem_safety["race_resistant"],
    ) not in {
        ("descriptor_relative_posix", True),
        ("cooperative_static_checks", False),
    }:
        _fail("filesystem_safety is invalid", "candidate_schema_invalid")
    if manifest["eligible_for_registry_review"] is not True or manifest["review_blockers"] != []:
        _fail("Candidate has unresolved review blockers", "candidate_review_blocked")

    recipe = _validate_recipe_record(manifest["recipe"])
    claims = manifest["operator_claims"]
    if not isinstance(claims, dict):
        _fail("operator_claims must be an object", "candidate_schema_invalid")
    try:
        normalized_claims = _validate_answers(claims)
    except Exception as exc:
        raise IngestError(
            f"operator_claims are invalid: {exc}",
            code="candidate_schema_invalid",
        ) from exc
    if normalized_claims != claims:
        _fail("operator_claims are not normalized", "candidate_schema_invalid")
    if claims["redistribution_permitted"] is not True:
        _fail("Redistribution permission is not granted", "redistribution_not_permitted")
    if re.match(r"^5\.3(?:\.|$)", claims["diptrace_version"]) is None:
        _fail(
            "Candidate was not captured with reported DipTrace 5.3",
            "unsupported_diptrace_version",
        )

    if manifest["stage_sequence"] != list(STAGES):
        _fail("Candidate stage_sequence is incomplete or out of order", "candidate_schema_invalid")
    stages = manifest["stages"]
    if not isinstance(stages, dict) or set(stages) != set(STAGES):
        _fail("Candidate stages are incomplete", "candidate_schema_invalid")
    artifacts = tuple(
        _validate_stage(
            capture_root,
            session_id,
            stage,
            stages[stage],
            protocol_identities=protocol_identities,
        )
        for stage in STAGES
    )
    if len({artifact.relative_path for artifact in artifacts}) != len(STAGES):
        _fail("Candidate roles reuse a quarantine path", "candidate_role_conflict")
    if len({artifact.source_type for artifact in artifacts}) != 1:
        _fail("Candidate roles have different source types", "candidate_source_type_mismatch")
    artifact_identities = {
        (
            (capture_root / artifact.relative_path).stat().st_dev,
            (capture_root / artifact.relative_path).stat().st_ino,
        )
        for artifact in artifacts
    }
    if len(artifact_identities) != len(STAGES):
        _fail("Candidate roles reuse one filesystem object", "candidate_role_conflict")
    if len({stages[stage]["original_path"] for stage in STAGES}) != len(STAGES):
        _fail("Candidate roles reuse an original path", "candidate_role_conflict")
    expected_source_type = recipe["expected_source_type"]
    if expected_source_type is not None and artifacts[0].source_type != expected_source_type:
        _fail("Candidate source type does not match its recipe", "candidate_source_type_mismatch")

    recipe_source = _safe_relative_path(
        manifest["recipe"]["source_path"],
        field="recipe.source_path",
    )
    stage_originals = {
        stage: _safe_relative_path(
            stages[stage]["original_path"],
            field=f"stages.{stage}.original_path",
        )
        for stage in STAGES
    }
    forbidden_paths = {
        manifest_relative,
        digest_relative,
        recipe_source,
        *stage_originals.values(),
        *(artifact.relative_path for artifact in artifacts),
    }
    _record_confined_identity_if_present(
        capture_root,
        recipe_source,
        role="recipe source",
        identities=protocol_identities,
    )
    for stage, original in stage_originals.items():
        _record_confined_identity_if_present(
            capture_root,
            original,
            role=f"{stage} original stage file",
            identities=protocol_identities,
        )
    store_path = capture_root / STORE_NAME
    try:
        store_metadata = store_path.lstat()
    except OSError as exc:
        raise IngestError(
            f"Cannot inspect capture store: {exc}",
            code="unsafe_candidate_path",
        ) from exc
    if _is_redirecting_path(store_path) or not stat.S_ISDIR(store_metadata.st_mode):
        _fail("Capture store is redirected or not a directory", "unsafe_candidate_path")
    store_identity = (store_metadata.st_dev, store_metadata.st_ino)
    input_artifacts = _validate_input_artifacts(
        capture_root,
        manifest.get("input_artifacts"),
        forbidden_paths=forbidden_paths,
        protocol_identities=protocol_identities,
        store_identity=store_identity,
    )

    _validate_checklist(manifest["checklist"], recipe)
    invariants = manifest["capture_invariants"]
    if not isinstance(invariants, dict):
        _fail("capture_invariants must be an object", "candidate_schema_invalid")
    _require_exact_keys(invariants, CAPTURE_INVARIANT_KEYS, field="capture_invariants")
    if invariants != {
        "stages_recorded_in_order": True,
        "all_sha256_bound": True,
        "source_type_consistent": True,
        "artifacts_quarantined": True,
        "trust_promoted_by_capture_tool": False,
    }:
        _fail("Candidate capture invariants are not satisfied", "candidate_trust_boundary")
    return ValidatedCandidate(
        manifest=manifest,
        manifest_relative_path=manifest_relative,
        manifest_bytes=manifest_bytes,
        manifest_sha256=manifest_sha,
        digest_bytes=digest_bytes,
        artifacts=artifacts,
        input_artifacts=input_artifacts,
    )


def _destination_root(value: str | Path) -> tuple[Path, bool]:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not current.exists():
            continue
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise IngestError(
                f"Cannot inspect destination root: {exc}",
                code="unsafe_destination_root",
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("Destination root contains a symlink", "unsafe_destination_root")
    existed = path.exists()
    if existed and not path.is_dir():
        _fail("Destination root must be a directory", "unsafe_destination_root")
    return path.resolve(strict=False), existed


def _planned_files(candidate: ValidatedCandidate, fixture_id: str) -> list[dict[str, str]]:
    planned: list[dict[str, str]] = []
    for artifact in candidate.artifacts:
        filename = f"{artifact.role}{artifact.relative_path.suffix.lower()}"
        destination = PurePosixPath(fixture_id) / filename
        planned.append(
            {
                "role": artifact.role,
                "destination": str(destination),
                "sha256": artifact.sha256,
            }
        )
    evidence_root = PurePosixPath(fixture_id) / "evidence"
    planned.extend(
        [
            {
                "role": "candidate_manifest",
                "destination": str(evidence_root / candidate.manifest_relative_path.name),
                "sha256": candidate.manifest_sha256,
            },
            {
                "role": "candidate_digest",
                "destination": str(
                    evidence_root / f"{candidate.manifest_relative_path.name}.sha256"
                ),
                "sha256": sha256_bytes(candidate.digest_bytes),
            },
        ]
    )
    return planned


def _existing_destination_entries(root: Path, fixture_id: str) -> list[Path]:
    target = root / fixture_id
    if not target.exists() and not target.is_symlink():
        return []
    if target.is_symlink() or not target.is_dir():
        return [Path(fixture_id)]
    result: list[Path] = []
    pending = [target]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise IngestError(
                f"Cannot inspect destination: {exc}",
                code="unsafe_destination_root",
            ) from exc
        for child in children:
            relative = child.relative_to(root)
            result.append(relative)
            if len(result) > MAX_DESTINATION_ENTRIES:
                _fail("Destination contains too many entries to review", "destination_too_large")
            try:
                metadata = child.lstat()
            except OSError as exc:
                raise IngestError(
                    f"Cannot inspect destination entry: {exc}",
                    code="unsafe_destination_root",
                ) from exc
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                pending.append(child)
    return result


def build_plan(
    candidate: ValidatedCandidate,
    *,
    destination_root: Path,
    destination_root_exists: bool,
    fixture_id: str,
    synthetic: bool,
) -> dict[str, Any]:
    if FIXTURE_ID_RE.fullmatch(fixture_id) is None:
        _fail("fixture_id must be a safe lowercase slug", "invalid_fixture_id")
    planned = _planned_files(candidate, fixture_id)
    planned_paths = {Path(item["destination"]) for item in planned}
    planned_directories = {
        parent
        for path in planned_paths
        for parent in path.parents
        if parent != Path(".")
    }
    conflicts: list[dict[str, str]] = []
    statuses: list[dict[str, str]] = []

    existing = (
        _existing_destination_entries(destination_root, fixture_id)
        if destination_root_exists
        else []
    )
    existing_files = {path for path in existing if (destination_root / path).is_file()}
    for item in planned:
        relative = Path(item["destination"])
        target = destination_root / relative
        status = "create"
        if target.exists() or target.is_symlink():
            try:
                metadata = target.lstat()
            except OSError as exc:
                raise IngestError(
                    f"Cannot inspect planned destination: {exc}",
                    code="unsafe_destination_root",
                ) from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                status = "conflict"
                conflicts.append(
                    {
                        "destination": item["destination"],
                        "reason": "existing_destination_is_not_a_regular_file",
                    }
                )
            else:
                limit = {
                    "candidate_manifest": MAX_MANIFEST_BYTES,
                    "candidate_digest": MAX_DIGEST_BYTES,
                }.get(item["role"], MAX_XML_BYTES)
                actual = sha256_bytes(
                    _read_confined_file(
                        destination_root,
                        relative,
                        role=f"existing destination {item['destination']}",
                        max_bytes=limit,
                    )
                )
                if actual == item["sha256"]:
                    status = "identical"
                else:
                    status = "conflict"
                    conflicts.append(
                        {
                            "destination": item["destination"],
                            "reason": "existing_sha256_mismatch",
                        }
                    )
        statuses.append({**item, "status": status})

    for relative in sorted(existing_files - planned_paths, key=lambda item: item.as_posix()):
        conflicts.append(
            {
                "destination": PurePosixPath(*relative.parts).as_posix(),
                "reason": "unplanned_existing_file",
            }
        )
    for relative in existing:
        target = destination_root / relative
        if target.is_symlink():
            conflicts.append(
                {
                    "destination": PurePosixPath(*relative.parts).as_posix(),
                    "reason": "existing_symlink",
                }
            )
        elif target.is_dir() and relative not in planned_directories:
            conflicts.append(
                {
                    "destination": PurePosixPath(*relative.parts).as_posix(),
                    "reason": "unplanned_existing_directory",
                }
            )

    try:
        registry_report = TrustedProvenanceRegistry.load_embedded().report()
    except ValueError as exc:
        raise IngestError(
            f"Embedded trusted provenance registry is invalid: {exc}",
            code="trusted_registry_invalid",
        ) from exc
    trusted_entry_count = registry_report["trusted_entry_count"]
    if not isinstance(trusted_entry_count, int):
        _fail("Embedded registry reported an invalid entry count", "trusted_registry_invalid")

    receipt = {
        "schema_version": PENDING_RECEIPT_SCHEMA,
        "candidate_sha256": candidate.manifest_sha256,
        "authority": "operator_supplied_unverified",
        "trust_grant": "none",
        "validation_level_granted": None,
        "fixture_id": fixture_id,
        "artifacts": [
            {
                "role": artifact.role,
                "sha256": artifact.sha256,
                "source_type": artifact.source_type,
            }
            for artifact in candidate.artifacts
        ],
        "input_artifacts": [
            {
                "role": artifact.role,
                "name": artifact.name,
                "path": artifact.relative_path.as_posix(),
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            }
            for artifact in candidate.input_artifacts
        ],
    }
    # Hashing the never-written receipt makes the plan reproducible without
    # presenting it as a provenance sidecar or registry entry.
    receipt_sha = sha256_bytes(canonical_json_bytes(receipt))
    return {
        "schema_version": PLAN_SCHEMA,
        "mode": "synthetic_dry_run" if synthetic else "candidate_dry_run",
        "dry_run": True,
        "synthetic": synthetic,
        "candidate": {
            "session_id": candidate.manifest["session_id"],
            "manifest_sha256": candidate.manifest_sha256,
            "source_type": candidate.artifacts[0].source_type,
            "authority": "operator_supplied_unverified",
            "trust_grant": "none",
            "input_artifacts": [
                {
                    "role": artifact.role,
                    "name": artifact.name,
                    "path": artifact.relative_path.as_posix(),
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in candidate.input_artifacts
            ],
        },
        "validation": {
            "strict_manifest_shape": True,
            "detached_digest_matches": True,
            "paths_contained": True,
            "filesystem_safety": {
                "mode": INGEST_PATH_SAFETY_MODE,
                "race_resistant": SECURE_CONFINED_OPEN_AVAILABLE,
            },
            "artifact_hashes_match": True,
            "input_artifact_hashes_match": True,
            "input_artifacts_metadata_only": True,
            "xml_inventories_match": True,
            "source_type_consistent": True,
            "redistribution_permitted": True,
        },
        "destination": {
            "fixture_id": fixture_id,
            "files": statuses,
            "conflicts": [
                {"destination": destination, "reason": reason}
                for destination, reason in sorted(
                    {
                        (item["destination"], item["reason"])
                        for item in conflicts
                    }
                )
            ],
            "pending_receipt_sha256": receipt_sha,
        },
        "ready_for_independent_review": not conflicts,
        "apply_available": False,
        "apply_unavailable_reason": "fixture_apply_not_implemented",
        "trust": {
            "trusted_registry_exists": True,
            "trusted_registry_checked": True,
            "trusted_registry_entry_count": trusted_entry_count,
            "reviewed_ingest_authorization": "none",
            "trust_promoted": False,
            "validation_level_granted": None,
        },
    }


def _synthetic_xml(stage: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Source Type="DipTrace-PCB" Version="5.3.0.1" Units="mm">'
        f"<Components><Component Id=\"1\"><Name>{stage}</Name></Component></Components>"
        "</Source>"
    ).encode()


def create_synthetic_candidate(root: Path) -> Path:
    """Create an ephemeral schema-complete stand-in for the CI dry-run."""

    recipe_snapshot = {
        "schema_version": "diptrace-capture-recipe-v1",
        "recipe_id": "ci-synthetic-ingest",
        "title": "Synthetic ingest validator stand-in",
        "purpose": "Exercise candidate validation without claiming DipTrace provenance.",
        "expected_source_type": "DipTrace-PCB",
        "required_features": ["temporary synthetic XML shape"],
        "operator_checklist": [
            {
                "id": "synthetic_stand_in",
                "prompt": "Confirm this is only the CI synthetic stand-in.",
                "required": True,
                "stage": "source",
            }
        ],
    }
    recipe_bytes = canonical_json_bytes(recipe_snapshot)
    (root / "synthetic-recipe.json").write_bytes(recipe_bytes)
    stages: dict[str, Any] = {}
    for stage in STAGES:
        data = _synthetic_xml(stage)
        relative = (
            Path(STORE_NAME)
            / "quarantine"
            / SYNTHETIC_SESSION
            / stage
            / f"{stage}.xml"
        )
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        stages[stage] = {
            "stage": stage,
            "captured_at": SYNTHETIC_TIMESTAMP,
            "original_path": f"synthetic-input/{stage}.xml",
            "quarantine_path": str(relative),
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "xml_inventory": inspect_xml(data).as_dict(),
            "operator_attestations": {
                "source": {
                    "direct_diptrace_export": True,
                    "no_programmatic_xml_generation": True,
                },
                "open_save": {
                    "opened_in_diptrace": True,
                    "saved_by_diptrace": True,
                },
                "reexport": {
                    "fresh_diptrace_export": True,
                    "no_programmatic_xml_generation": True,
                },
            }[stage],
            "operator_note": "Synthetic CI shape only; not an operator attestation.",
            "warnings": [],
        }
    manifest: dict[str, Any] = {
        "schema_version": CANDIDATE_SCHEMA,
        "session_id": SYNTHETIC_SESSION,
        "created_at": SYNTHETIC_TIMESTAMP,
        "authority": "operator_supplied_unverified",
        "trust_grant": "none",
        "candidate_only": True,
        "review_status": "pending_independent_review",
        "requires_independent_review": True,
        "must_not_copy_to_acceptance_without_review": True,
        "filesystem_safety": {
            "mode": "cooperative_static_checks",
            "race_resistant": False,
        },
        "eligible_for_registry_review": True,
        "review_blockers": [],
        "recipe": {
            "source_path": "synthetic-recipe.json",
            "source_sha256": sha256_bytes(recipe_bytes),
            "snapshot": recipe_snapshot,
        },
        "operator_claims": {
            "operator_label": "ci-synthetic-not-an-operator",
            "diptrace_version": "5.3.0.synthetic-stand-in",
            "diptrace_build": "synthetic-not-a-build",
            "operating_system": "temporary-ci-stand-in",
            "redistribution_permitted": True,
            "redistribution_basis": "Generated temporarily; never eligible for fixture trust.",
            "notes": "No human or DipTrace provenance is claimed.",
        },
        "stage_sequence": list(STAGES),
        "stages": stages,
        "checklist": {
            "synthetic_stand_in": {
                "prompt": "Confirm this is only the CI synthetic stand-in.",
                "required": True,
                "stage": "source",
                "answer": "yes",
                "note": "Set by the synthetic harness, not a human.",
                "answered_at": SYNTHETIC_TIMESTAMP,
            }
        },
        "capture_invariants": {
            "stages_recorded_in_order": True,
            "all_sha256_bound": True,
            "source_type_consistent": True,
            "artifacts_quarantined": True,
            "trust_promoted_by_capture_tool": False,
        },
    }
    manifest_bytes = canonical_json_bytes(manifest)
    candidate_relative = (
        Path(STORE_NAME) / "candidates" / f"{SYNTHETIC_SESSION}.candidate.json"
    )
    candidate_path = root / candidate_relative
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(manifest_bytes)
    manifest_sha = sha256_bytes(manifest_bytes)
    candidate_path.with_name(candidate_path.name + ".sha256").write_bytes(
        f"{manifest_sha}  {candidate_path.name}\n".encode("ascii")
    )
    return candidate_relative


def synthetic_plan() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="diptrace-ingest-synthetic-") as temporary:
        root = Path(temporary)
        capture_root = root / "capture"
        destination_root = root / "stand-in-destination"
        capture_root.mkdir()
        destination_root.mkdir()
        candidate_relative = create_synthetic_candidate(capture_root)
        candidate = validate_candidate(capture_root, candidate_relative)
        return build_plan(
            candidate,
            destination_root=destination_root,
            destination_root_exists=True,
            fixture_id=SYNTHETIC_FIXTURE_ID,
            synthetic=True,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a captured DipTrace evidence candidate and show a dry-run ingest plan. "
            "The embedded trust registry is inspected, but fixture apply is not implemented."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate and print a plan")
    mode.add_argument("--apply", action="store_true", help="Reserved; currently fails closed")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run a temporary, trust-neutral CI stand-in (requires --dry-run)",
    )
    parser.add_argument("--capture-root", help="Explicit root produced by the capture workflow")
    parser.add_argument(
        "--candidate",
        help="Candidate manifest path relative to --capture-root",
    )
    parser.add_argument("--destination-root", help="Prospective fixture destination root")
    parser.add_argument("--fixture-id", help="Safe prospective fixture directory name")
    parser.add_argument("--json", action="store_true", help="Print the complete JSON plan")
    return parser


def _print_plan(plan: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False))
        return
    destination = plan["destination"]
    assert isinstance(destination, dict)
    conflicts = destination["conflicts"]
    assert isinstance(conflicts, list)
    print(
        f"Validated candidate {plan['candidate']['session_id']}; "
        f"{len(destination['files'])} files planned, {len(conflicts)} conflicts."
    )
    print(f"Apply unavailable: {plan['apply_unavailable_reason']}")
    for item in destination["files"]:
        print(f"{item['status']:>9}  {item['destination']}  {item['sha256']}")
    for conflict in conflicts:
        print(f" conflict  {conflict['destination']}: {conflict['reason']}")


def run_cli(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if args.apply:
        _fail(
            "Fixture apply is not implemented; the existing trusted registry cannot authorize "
            "this command to write acceptance fixtures",
            "fixture_apply_not_implemented",
        )
    if not args.dry_run:
        _fail("Choose --dry-run; no mutation mode is available", "execution_mode_required")
    if args.synthetic:
        supplied = {
            "--capture-root": args.capture_root,
            "--candidate": args.candidate,
            "--destination-root": args.destination_root,
            "--fixture-id": args.fixture_id,
        }
        conflicts = [flag for flag, value in supplied.items() if value is not None]
        if conflicts:
            _fail(
                f"--synthetic may not be combined with {', '.join(conflicts)}",
                "synthetic_argument_conflict",
            )
        plan = synthetic_plan()
    else:
        required = {
            "--capture-root": args.capture_root,
            "--candidate": args.candidate,
            "--destination-root": args.destination_root,
            "--fixture-id": args.fixture_id,
        }
        missing = [flag for flag, value in required.items() if value is None]
        if missing:
            _fail(f"Missing required arguments: {', '.join(missing)}", "missing_argument")
        capture_root = _existing_root(args.capture_root, role="capture root")
        candidate_relative = _safe_relative_path(args.candidate, field="--candidate")
        destination_root, existed = _destination_root(args.destination_root)
        candidate = validate_candidate(capture_root, candidate_relative)
        plan = build_plan(
            candidate,
            destination_root=destination_root,
            destination_root_exists=existed,
            fixture_id=args.fixture_id,
            synthetic=False,
        )
    _print_plan(plan, as_json=args.json)
    conflicts = plan["destination"]["conflicts"]
    return 4 if conflicts else 0


def main() -> NoReturn:
    try:
        exit_code = run_cli()
    except IngestError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": str(exc)}},
                sort_keys=True,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(exc.exit_code) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
