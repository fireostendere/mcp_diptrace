#!/usr/bin/env python3
"""Audit acceptance-seed declarations without writing or granting trust.

The committed v2 fixture manifest and the existing ``FixtureManifest`` model
are the provenance records checked here.  Passing this audit proves only that
the declared files are internally consistent, byte-bound, and parse as their
declared source types.  It never registers a fixture, changes a sidecar, or
promotes a validation level.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from diptrace_mcp.domain import FixtureManifest, FixtureValidationLevel
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.provenance_registry import TrustedProvenanceRegistry
from diptrace_mcp.specctra import _SExprParser, parse_ses
from diptrace_mcp.xml_document import DipTraceDocument

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "acceptance" / "diptrace_5_3" / "seeds"
)
DEFAULT_SCHEMA = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "diptrace_5_3" / "manifest.schema.json"
)
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 128 * 1024 * 1024
MAX_SEEDS = 1024
MAX_ERRORS = 64
MAX_ERROR_CHARS = 1024
_XML_SOURCE_TYPES = frozenset(
    {
        "DipTrace-PCB",
        "DipTrace-Schematic",
        "DipTrace-ComponentLibrary",
        "DipTrace-PatternLibrary",
    }
)
_SPECCTRA_SOURCE_TYPES = frozenset({"Specctra-DSN", "Specctra-SES"})
_DATA_SUFFIXES = frozenset({".xml", ".dsn", ".ses"})
_IGNORED_NAMES = frozenset({".gitkeep"})
_IGNORED_SUFFIXES = frozenset({".md"})
_STALE_SIDECAR_WARNING = (
    "Per-file .provenance.json sidecars are not used as authority by this audit. "
    "The protected seeds/README sidecar procedure predates the committed v2 "
    "manifest authority boundary; follow docs/ACCEPTANCE_SEED_AUDIT.md instead."
)


class SeedAuditError(ValueError):
    """The seed directory cannot be audited safely or consistently."""


@dataclass(frozen=True)
class AuditedSeed:
    """One manifest entry whose bytes and actual source type were checked."""

    path: str
    sha256: str
    source_type: str
    validation_level: str
    provenance: str
    size_bytes: int

    def as_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "provenance": self.provenance,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "source_type": self.source_type,
            "validation_level": self.validation_level,
        }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SeedAuditError(f"JSON object contains duplicate key {key!r}")
        result[key] = value
    return result


def _strict_json_bytes(data: bytes, *, role: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SeedAuditError(f"{role} must be UTF-8 without undecodable bytes") from exc
    if text.startswith("\ufeff"):
        raise SeedAuditError(f"{role} must be UTF-8 without a BOM")
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise SeedAuditError(
            f"{role} is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except RecursionError as exc:
        raise SeedAuditError(f"{role} exceeds the supported JSON nesting depth") from exc


def _read_bounded(path: Path, *, limit: int, role: str) -> bytes:
    try:
        path_metadata = path.lstat()
    except OSError as exc:
        raise SeedAuditError(f"cannot stat {role}: {exc}") from exc
    if stat.S_ISLNK(path_metadata.st_mode) or not stat.S_ISREG(path_metadata.st_mode):
        raise SeedAuditError(f"{role} must be a real regular file")
    if path_metadata.st_size > limit:
        raise SeedAuditError(f"{role} exceeds the {limit}-byte audit limit")

    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SeedAuditError(f"cannot open {role}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SeedAuditError(f"{role} must be a regular file")
        if before.st_size > limit:
            raise SeedAuditError(f"{role} exceeds the {limit}-byte audit limit")

        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise SeedAuditError(f"cannot read {role}: {exc}") from exc
    finally:
        os.close(descriptor)

    if len(data) > limit:
        raise SeedAuditError(f"{role} exceeds the {limit}-byte audit limit")
    stable_identity = (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    stable_metadata = (
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_size,
        after.st_mtime_ns,
    )
    if not stable_identity or not stable_metadata or len(data) != after.st_size:
        raise SeedAuditError(f"{role} changed while it was being audited")
    return data


def _safe_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise SeedAuditError(f"seed root is unavailable: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SeedAuditError("seed root must be a real directory, not a link or file")
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise SeedAuditError(f"cannot resolve seed root: {exc}") from exc


def _canonical_relative_path(raw_path: str) -> PurePosixPath:
    if (
        not raw_path
        or "\\" in raw_path
        or any(ord(character) < 32 for character in raw_path)
    ):
        raise SeedAuditError(f"unsafe fixture path {raw_path!r}")
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or path.as_posix() != raw_path
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SeedAuditError(f"fixture path is not canonical and relative: {raw_path!r}")
    return path


def _safe_fixture_path(root: Path, relative: PurePosixPath) -> Path:
    candidate = root.joinpath(*relative.parts)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except OSError as exc:
            raise SeedAuditError(f"fixture {relative.as_posix()} is unavailable: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise SeedAuditError(f"fixture path contains a symbolic link: {relative.as_posix()}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise SeedAuditError(f"fixture escapes the seed root: {relative.as_posix()}") from exc
    if not candidate.is_file():
        raise SeedAuditError(f"fixture is not a regular file: {relative.as_posix()}")
    return candidate


def _iter_tree_files(root: Path) -> Iterable[Path]:
    def fail_walk(error: OSError) -> None:
        raise SeedAuditError(f"cannot inspect seed tree: {error}") from error

    for directory, directory_names, file_names in os.walk(
        root,
        followlinks=False,
        onerror=fail_walk,
    ):
        directory_path = Path(directory)
        for name in tuple(directory_names):
            candidate = directory_path / name
            try:
                if candidate.is_symlink():
                    raise SeedAuditError(
                        f"seed tree contains a linked directory: "
                        f"{candidate.relative_to(root).as_posix()}"
                    )
            except OSError as exc:
                raise SeedAuditError(f"cannot inspect seed directory {candidate}: {exc}") from exc
        for name in file_names:
            candidate = directory_path / name
            try:
                metadata = candidate.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    raise SeedAuditError(
                        f"seed tree contains a linked file: "
                        f"{candidate.relative_to(root).as_posix()}"
                    )
                if not stat.S_ISREG(metadata.st_mode):
                    raise SeedAuditError(
                        f"seed tree contains a non-regular file: "
                        f"{candidate.relative_to(root).as_posix()}"
                    )
            except OSError as exc:
                raise SeedAuditError(f"cannot inspect seed file {candidate}: {exc}") from exc
            yield candidate


def _runtime_files(root: Path) -> tuple[PurePosixPath, ...]:
    paths: list[PurePosixPath] = []
    for candidate in _iter_tree_files(root):
        relative = PurePosixPath(candidate.relative_to(root).as_posix())
        if (
            relative.name in _IGNORED_NAMES
            or relative.suffix.casefold() in _IGNORED_SUFFIXES
            or relative.name == MANIFEST_NAME
            or relative.name.endswith(".provenance.json")
        ):
            continue
        paths.append(relative)
    return tuple(sorted(paths))


def _validate_schema(manifest: object, schema: object) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise SeedAuditError("fixture manifest schema must be a JSON object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SeedAuditError(f"fixture manifest schema is invalid: {exc.message}") from exc
    try:
        validator = Draft202012Validator(schema)
        failures = sorted(
            validator.iter_errors(manifest),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except RecursionError as exc:
        raise SeedAuditError("manifest exceeds the supported schema nesting depth") from exc
    if failures:
        messages: list[str] = []
        for failure in failures[:MAX_ERRORS]:
            location = "/".join(str(part) for part in failure.absolute_path) or "<root>"
            message = f"{location}: {failure.message}"
            messages.append(message[:MAX_ERROR_CHARS])
        if len(failures) > MAX_ERRORS:
            messages.append(f"{len(failures) - MAX_ERRORS} additional schema errors omitted")
        raise SeedAuditError("manifest schema validation failed: " + "; ".join(messages))
    if not isinstance(manifest, dict):
        raise SeedAuditError("fixture manifest must be a JSON object")
    return manifest


def _fixture_manifest_record(
    entry: dict[str, Any],
    manifest: dict[str, Any],
) -> FixtureManifest:
    redistribution = manifest["redistribution"]
    return FixtureManifest(
        provenance=entry["provenance"],
        validation_level=FixtureValidationLevel(entry["validation_level"]),
        diptrace_version=entry.get("diptrace_version"),
        diptrace_build=entry.get("diptrace_build"),
        source_format_version=entry.get("format_version"),
        source_sha256=entry["sha256"],
        reexport_sha256=entry.get("reexport_sha256"),
        diptrace_opened=entry.get("diptrace_opened", False),
        diptrace_saved=entry.get("diptrace_saved", False),
        diptrace_reexported=entry.get("diptrace_reexported", False),
        roundtrip_verified=entry.get("roundtrip_verified", False),
        semantic_comparison_passed=entry.get("semantic_comparison_passed"),
        redistribution_permitted=redistribution["permitted"],
        redistribution_basis=redistribution["basis"],
        authoring_method=entry["provenance"],
        known_limitations=entry.get("known_limitations", []),
    )


def _actual_source_type(path: Path, data: bytes, declared: str) -> tuple[str, str | None]:
    if declared in _XML_SOURCE_TYPES:
        try:
            document = DipTraceDocument.from_bytes(path, data)
        except DocumentError as exc:
            raise SeedAuditError(f"{path.name} is not valid DipTrace XML: {exc}") from exc
        return document.source_type, document.version
    if declared == "Specctra-SES":
        try:
            parse_ses(data, max_bytes=MAX_DOCUMENT_BYTES)
        except DocumentError as exc:
            raise SeedAuditError(f"{path.name} is not a valid Specctra SES file: {exc}") from exc
        return "Specctra-SES", None
    if declared == "Specctra-DSN":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SeedAuditError(f"{path.name} Specctra DSN must be UTF-8 text") from exc
        try:
            roots = _SExprParser(text, max_tokens=2_000_000, max_depth=128).parse()
        except DocumentError as exc:
            raise SeedAuditError(f"{path.name} is not valid Specctra syntax: {exc}") from exc
        if (
            len(roots) != 1
            or not isinstance(roots[0], list)
            or not roots[0]
            or roots[0][0] != "pcb"
        ):
            raise SeedAuditError(f"{path.name} is not a Specctra DSN pcb scope")
        return "Specctra-DSN", None
    if declared in _SPECCTRA_SOURCE_TYPES:
        raise SeedAuditError(f"unsupported Specctra source type {declared!r}")
    raise SeedAuditError(f"unsupported source type {declared!r}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _base_report(root: Path) -> dict[str, object]:
    return {
        "errors": [],
        "manifest_path": None,
        "registry_consulted": False,
        "registry_entry_count": 0,
        "registry_match": False,
        "root": str(root),
        "seed_count": 0,
        "seeds": [],
        "sidecar_authority_used": False,
        "status": "no_seeds",
        "trust_promoted": False,
        "warnings": [_STALE_SIDECAR_WARNING],
        "written": False,
    }


def _consult_registry(report: dict[str, object]) -> None:
    """Record the real embedded registry state without inferring seed authority."""

    try:
        registry = TrustedProvenanceRegistry.load_embedded()
    except ValueError as exc:
        raise SeedAuditError(f"embedded trusted registry is invalid: {exc}") from exc
    report["registry_consulted"] = True
    report["registry_entry_count"] = registry.entry_count


def audit_seed_root(root: Path, *, schema_path: Path = DEFAULT_SCHEMA) -> dict[str, object]:
    """Return a deterministic read-only audit report or raise ``SeedAuditError``."""

    safe_root = _safe_root(root)
    report = _base_report(safe_root)
    _consult_registry(report)
    manifest_path = safe_root / MANIFEST_NAME
    runtime_files = _runtime_files(safe_root)
    if not manifest_path.exists():
        candidate_data = [
            path for path in runtime_files if path.suffix.casefold() in _DATA_SUFFIXES
        ]
        if candidate_data or runtime_files:
            paths = ", ".join(path.as_posix() for path in runtime_files[:8])
            raise SeedAuditError(
                f"seed data exists without {MANIFEST_NAME}: {paths}"
            )
        return report
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SeedAuditError(f"{MANIFEST_NAME} must be a real regular file")

    manifest_data = _strict_json_bytes(
        _read_bounded(manifest_path, limit=MAX_MANIFEST_BYTES, role=MANIFEST_NAME),
        role=MANIFEST_NAME,
    )
    schema_data = _strict_json_bytes(
        _read_bounded(schema_path, limit=MAX_MANIFEST_BYTES, role="manifest schema"),
        role="manifest schema",
    )
    manifest = _validate_schema(manifest_data, schema_data)
    entries = manifest["fixtures"]
    if not isinstance(entries, list):
        raise SeedAuditError("manifest fixtures must be an array")
    if len(entries) > MAX_SEEDS:
        raise SeedAuditError(f"manifest contains more than {MAX_SEEDS} seed entries")

    audited: list[AuditedSeed] = []
    seen_paths: set[PurePosixPath] = set()
    seen_file_identities: set[tuple[int, int]] = set()
    difference_links: list[tuple[PurePosixPath, PurePosixPath]] = []
    outer_diptrace = manifest["diptrace"]
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise SeedAuditError(f"fixtures[{index}] must be an object")
        entry: dict[str, Any] = raw_entry
        relative = _canonical_relative_path(entry["path"])
        if relative in seen_paths:
            raise SeedAuditError(f"duplicate fixture path: {relative.as_posix()}")
        seen_paths.add(relative)
        difference = entry.get("difference_from")
        if isinstance(difference, dict):
            referenced = _canonical_relative_path(difference["path"])
            if referenced == relative:
                raise SeedAuditError(
                    f"difference_from for {relative.as_posix()} references itself"
                )
            difference_links.append((relative, referenced))
        candidate = _safe_fixture_path(safe_root, relative)
        metadata = candidate.stat()
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in seen_file_identities:
            raise SeedAuditError(
                f"fixture aliases another manifest file: {relative.as_posix()}"
            )
        seen_file_identities.add(identity)
        data = _read_bounded(
            candidate,
            limit=MAX_DOCUMENT_BYTES,
            role=f"fixture {relative.as_posix()}",
        )
        actual_sha = _sha256(data)
        if actual_sha != entry["sha256"]:
            raise SeedAuditError(
                f"SHA-256 mismatch for {relative.as_posix()}: "
                f"expected {entry['sha256']}, got {actual_sha}"
            )

        try:
            _fixture_manifest_record(entry, manifest)
        except ValueError as exc:
            raise SeedAuditError(
                f"provenance invariants failed for {relative.as_posix()}: {exc}"
            ) from exc

        actual_source_type, actual_format_version = _actual_source_type(
            candidate, data, entry["source_type"]
        )
        if actual_source_type != entry["source_type"]:
            raise SeedAuditError(
                f"source type mismatch for {relative.as_posix()}: "
                f"manifest declares {entry['source_type']!r}, "
                f"file contains {actual_source_type!r}"
            )
        declared_format_version = entry.get("format_version")
        if (
            declared_format_version is not None
            and actual_format_version is not None
            and declared_format_version != actual_format_version
        ):
            raise SeedAuditError(
                f"format version mismatch for {relative.as_posix()}: "
                f"manifest declares {declared_format_version!r}, "
                f"file contains {actual_format_version!r}"
            )
        entry_diptrace_version = entry.get("diptrace_version")
        if (
            entry_diptrace_version is not None
            and entry_diptrace_version != outer_diptrace["version"]
        ):
            raise SeedAuditError(
                f"DipTrace version mismatch for {relative.as_posix()}: "
                "entry and manifest-wide provenance differ"
            )
        entry_build = entry.get("diptrace_build")
        if entry_build is not None and entry_build != outer_diptrace["build"]:
            raise SeedAuditError(
                f"DipTrace build mismatch for {relative.as_posix()}: "
                "entry and manifest-wide provenance differ"
            )
        audited.append(
            AuditedSeed(
                path=relative.as_posix(),
                sha256=actual_sha,
                source_type=actual_source_type,
                validation_level=entry["validation_level"],
                provenance=entry["provenance"],
                size_bytes=len(data),
            )
        )

    for source, referenced in difference_links:
        if referenced not in seen_paths:
            raise SeedAuditError(
                f"difference_from for {source.as_posix()} references an unlisted fixture: "
                f"{referenced.as_posix()}"
            )

    listed = set(seen_paths)
    unlisted = [path for path in runtime_files if path not in listed]
    if unlisted:
        paths = ", ".join(path.as_posix() for path in unlisted[:8])
        raise SeedAuditError(f"unlisted runtime file(s) in seed root: {paths}")

    report.update(
        {
            "manifest_path": MANIFEST_NAME,
            "seed_count": len(audited),
            "seeds": [seed.as_json() for seed in sorted(audited, key=lambda item: item.path)],
            "status": "valid" if audited else "no_seeds",
        }
    )
    return report


def _error_report(root: Path, error: SeedAuditError) -> dict[str, object]:
    report = _base_report(root)
    report["errors"] = [str(error)[:MAX_ERROR_CHARS]]
    report["status"] = "invalid"
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"seed directory to audit (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=f"committed v2 fixture schema (default: {DEFAULT_SCHEMA})",
    )
    arguments = parser.parse_args(argv)
    try:
        report = audit_seed_root(arguments.root, schema_path=arguments.schema)
    except SeedAuditError as exc:
        report = _error_report(arguments.root, exc)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
