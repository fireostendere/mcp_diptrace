#!/usr/bin/env python3
"""Normalize a pyi-archive_viewer listing without retaining machine paths."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _member_from_line(line: str) -> str | None:
    value = line.strip()
    if not value or value.startswith("(") or value.startswith("Contents"):
        return None
    match = re.search(r"([A-Za-z0-9_.+/-]+(?:\\[A-Za-z0-9_.+ -]+)*)$", value)
    return match.group(1).replace("\\", "/") if match else None


def summarize(source: Path) -> dict[str, Any]:
    members: set[str] = set()
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        member = _member_from_line(line)
        if member and "/" not in member and "\\" not in member and len(member) > 180:
            continue
        if member:
            members.add(member)
    native = sorted(
        member
        for member in members
        if Path(member).suffix.lower() in {".dll", ".pyd", ".so", ".dylib"}
    )
    metadata = sorted(
        member
        for member in members
        if ".dist-info" in member
        or ".egg-info" in member
        or member.lower().endswith(("license", "copying", "notice"))
    )
    modules = sorted(
        member
        for member in members
        if member.endswith((".py", ".pyc", ".pyd")) and member not in native
    )
    expected = set(native) | set(metadata) | set(modules)
    return {
        "tool": "PyInstaller pyi-archive_viewer",
        "input": source.name,
        "member_count": len(members),
        "python_modules": modules,
        "dll_or_native_files": native,
        "embedded_metadata_and_licenses": metadata,
        "unexpected_files": sorted(members - expected),
        "ordering": "lexicographically normalized",
        "signed": False,
        "legal_clearance": False,
        "human_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.source)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
