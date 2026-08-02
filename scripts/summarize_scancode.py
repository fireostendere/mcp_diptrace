#!/usr/bin/env python3
"""Turn ScanCode JSON into a path-safe, non-legal summary."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any


def _safe_path(value: object) -> str:
    return str(value or "").replace("\\", "/").lstrip("/")


def summarize(source: Path) -> dict[str, Any]:
    data = json.loads(source.read_text(encoding="utf-8"))
    files = data.get("files", []) if isinstance(data, dict) else []
    file_items = [
        item for item in files if isinstance(item, dict) and item.get("type") == "file"
    ]
    licenses: collections.Counter[str] = collections.Counter()
    packages: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in file_items:
        expressions = item.get("license_expressions") or []
        if not expressions:
            expressions = [
                detection.get("license_expression_spdx")
                for detection in item.get("license_detections", [])
                if isinstance(detection, dict) and detection.get("license_expression_spdx")
            ]
        if not expressions:
            missing.append(_safe_path(item.get("path")))
        for expression in expressions:
            licenses[str(expression)] += 1
        package_data = item.get("package_data")
        if isinstance(package_data, list):
            packages.extend(
                {"name": p.get("name"), "version": p.get("version"), "purl": p.get("purl")}
                for p in package_data
                if isinstance(p, dict)
            )
    return {
        "tool": "ScanCode Toolkit",
        "input": source.name,
        "file_count": len(file_items),
        "license_expression_counts": dict(sorted(licenses.items())),
        "package_count": len(packages),
        "packages": packages,
        "files_without_license_expression_count": len(missing),
        "files_without_license_expression": sorted(path for path in missing if path)[:100],
        "legal_clearance": False,
        "human_review_required": True,
        "disclaimer": "Automated identification is not a legal opinion or license clearance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.source)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
