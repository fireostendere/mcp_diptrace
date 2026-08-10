#!/usr/bin/env python3
"""Validate version-bearing release metadata against one committed manifest."""
from __future__ import annotations

import json
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    version = release["version"]
    failures: list[str] = []
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    smithery_project = tomllib.loads(
        (ROOT / "packaging/smithery/pyproject.toml").read_text(encoding="utf-8")
    )
    smithery_manifest = json.loads(
        (ROOT / "packaging/smithery/manifest.json").read_text(encoding="utf-8")
    )
    checks = {
        "pyproject.toml": pyproject["project"]["version"],
        "packaging/smithery/pyproject.toml": smithery_project["project"]["version"],
        "packaging/smithery/manifest.json": smithery_manifest["version"],
    }
    for name, actual in checks.items():
        if actual != version:
            failures.append(f"{name}: {actual!r} != release.json {version!r}")
    release_doc = (ROOT / f"docs/releases/v{version}.md").read_text(encoding="utf-8")
    if f"Version: `{version}`" not in release_doc:
        failures.append("release record does not match release.json version")
    roadmap = (ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8").lower()
    if f"source/package version is `{version}`" not in roadmap:
        failures.append("ROADMAP source/package version is stale")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"OK: release metadata is aligned at {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
