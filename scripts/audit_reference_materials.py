#!/usr/bin/env python3
"""Inventory a local reference-material directory without copying source bytes.

The default intentionally hashes only small documentation files and a deterministic,
size-stratified sample of legacy DipTrace libraries. It does not recursively hash every
library and it never emits file contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOCUMENT_EXTENSIONS = {".docx", ".md", ".pdf"}
LIBRARY_EXTENSIONS = {".eli", ".lib"}
DEFAULT_SAMPLE_PER_KIND = 12
SAMPLE_SEED = "mcp-diptrace-reference-material-audit-v1"
READ_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class FileEntry:
    relative_path: str
    path: Path
    size_bytes: int
    extension: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_files(root: Path) -> tuple[list[FileEntry], list[str]]:
    entries: list[FileEntry] = []
    skipped_symlinks: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            skipped_symlinks.append(relative)
            continue
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            FileEntry(
                relative_path=relative,
                path=path,
                size_bytes=stat.st_size,
                extension=path.suffix.lower(),
            )
        )
    return entries, skipped_symlinks


def _rank(seed: str, entry: FileEntry) -> str:
    value = f"{seed}\0{entry.relative_path}\0{entry.size_bytes}".encode()
    return hashlib.sha256(value).hexdigest()


def _stratified_sample(
    entries: Sequence[FileEntry],
    *,
    sample_count: int,
    seed: str = SAMPLE_SEED,
) -> list[FileEntry]:
    """Select endpoints plus deterministic members of equal-count size strata."""
    ordered = sorted(entries, key=lambda item: (item.size_bytes, item.relative_path))
    if sample_count >= len(ordered):
        return ordered
    if sample_count <= 0:
        return []
    if sample_count == 1:
        return [min(ordered, key=lambda item: _rank(seed, item))]

    chosen = {ordered[0], ordered[-1]}
    strata = max(sample_count - 2, 0)
    for index in range(strata):
        start = index * len(ordered) // strata
        end = (index + 1) * len(ordered) // strata
        bucket = ordered[start:end]
        if bucket:
            chosen.add(min(bucket, key=lambda item: _rank(f"{seed}:{index}", item)))

    if len(chosen) < sample_count:
        remaining = (entry for entry in ordered if entry not in chosen)
        chosen.update(
            sorted(remaining, key=lambda item: _rank(f"{seed}:fill", item))[
                : sample_count - len(chosen)
            ]
        )
    return sorted(chosen, key=lambda item: (item.size_bytes, item.relative_path))


def _magic_label(path: Path) -> str:
    with path.open("rb") as stream:
        prefix = stream.read(8)
    if prefix.startswith(b"\x06DTELIB"):
        return "legacy_component_library_binary"
    if prefix.startswith(b"\x06DTCLIB"):
        return "legacy_pattern_library_binary"
    if prefix.startswith((b"<?xml", b"\xef\xbb\xbf<?xml")):
        return "xml_text"
    return f"unknown:{prefix.hex()}"


def _summaries(entries: Iterable[FileEntry]) -> dict[str, dict[str, int]]:
    by_extension: dict[str, list[FileEntry]] = defaultdict(list)
    for entry in entries:
        by_extension[entry.extension or "<none>"].append(entry)
    return {
        extension: {
            "count": len(group),
            "bytes": sum(entry.size_bytes for entry in group),
            "min_bytes": min(entry.size_bytes for entry in group),
            "max_bytes": max(entry.size_bytes for entry in group),
        }
        for extension, group in sorted(by_extension.items())
    }


def build_inventory(root: Path, *, sample_per_kind: int) -> dict[str, Any]:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"Reference-material root is not a directory: {root}")
    entries, skipped_symlinks = _safe_files(resolved)
    documents = [entry for entry in entries if entry.extension in DOCUMENT_EXTENSIONS]
    libraries = [entry for entry in entries if entry.extension in LIBRARY_EXTENSIONS]
    classified = {*documents, *libraries}
    other_entries = [entry for entry in entries if entry not in classified]

    document_records = [
        {
            "path": entry.relative_path,
            "size_bytes": entry.size_bytes,
            "sha256": _sha256(entry.path),
        }
        for entry in documents
    ]

    library_records: dict[str, dict[str, Any]] = {}
    hashed_library_count = 0
    for extension in sorted(LIBRARY_EXTENSIONS):
        population = [entry for entry in libraries if entry.extension == extension]
        sample = _stratified_sample(
            population,
            sample_count=sample_per_kind,
            seed=f"{SAMPLE_SEED}:{extension}",
        )
        magic_counts: dict[str, int] = defaultdict(int)
        for entry in population:
            magic_counts[_magic_label(entry.path)] += 1
        library_records[extension] = {
            "population_count": len(population),
            "population_bytes": sum(entry.size_bytes for entry in population),
            "population_magic_counts": dict(sorted(magic_counts.items())),
            "sampling": {
                "method": (
                    "smallest and largest plus deterministic selections from "
                    "equal-count size strata"
                ),
                "seed": f"{SAMPLE_SEED}:{extension}",
                "requested_count": sample_per_kind,
                "actual_count": len(sample),
            },
            "sample": [
                {
                    "path": entry.relative_path,
                    "size_bytes": entry.size_bytes,
                    "sha256": _sha256(entry.path),
                    "magic": _magic_label(entry.path),
                }
                for entry in sample
            ],
        }
        hashed_library_count += len(sample)

    return {
        "schema_version": 1,
        "scope": {
            "root_name": resolved.name,
            "file_count": len(entries),
            "bytes": sum(entry.size_bytes for entry in entries),
            "documentation_file_count": len(documents),
            "documentation_bytes": sum(entry.size_bytes for entry in documents),
            "legacy_library_file_count": len(libraries),
            "legacy_library_bytes": sum(entry.size_bytes for entry in libraries),
            "other_file_count": len(other_entries),
            "other_bytes": sum(entry.size_bytes for entry in other_entries),
            "skipped_symlinks": skipped_symlinks,
        },
        "by_extension": _summaries(entries),
        "documentation": document_records,
        "legacy_library_samples": library_records,
        "disclosure": {
            "all_legacy_libraries_hashed": hashed_library_count == len(libraries),
            "source_bytes_embedded": False,
            "source_paths_are_relative": True,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Local, uncommitted reference-material directory to inventory",
    )
    parser.add_argument(
        "--sample-per-kind",
        type=int,
        default=DEFAULT_SAMPLE_PER_KIND,
        help="Number of .eli and .lib files to hash (default: 12 each)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.sample_per_kind < 0:
        raise SystemExit("--sample-per-kind must be non-negative")
    print(
        json.dumps(
            build_inventory(args.root, sample_per_kind=args.sample_per_kind),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
