#!/usr/bin/env python3
"""Validate version-bearing release metadata against one committed manifest."""
from __future__ import annotations

import json
import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PUBLISHED_STATUS = "published-unsigned-development-release"
CANDIDATE_STATUS = "release-candidate"


def _valid_sha_map(value: object) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and all(
            isinstance(name, str)
            and bool(name)
            and isinstance(digest, str)
            and HEX64.fullmatch(digest) is not None
            for name, digest in value.items()
        )
    )


def main() -> int:
    release = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    version = release["version"]
    status = release.get("release_status")
    failures: list[str] = []

    if status not in {CANDIDATE_STATUS, PUBLISHED_STATUS}:
        failures.append(f"release.json: unsupported release_status {status!r}")
    if release.get("tag") != f"v{version}":
        failures.append("release.json: tag does not match version")

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

    if status == PUBLISHED_STATUS:
        for key in ("github_release_id", "github_release_workflow_run", "pypi_workflow_run"):
            if not isinstance(release.get(key), int) or release[key] <= 0:
                failures.append(f"release.json: published release requires positive integer {key}")
        for key in ("validated_candidate_sha", "tag_target_sha", "tag_object_sha"):
            value = release.get(key)
            if not isinstance(value, str) or HEX40.fullmatch(value) is None:
                failures.append(f"release.json: published release requires 40-hex {key}")
        if not isinstance(release.get("published_at"), str) or not release["published_at"]:
            failures.append("release.json: published release requires published_at")
        if not _valid_sha_map(release.get("assets")):
            failures.append("release.json: published release requires SHA-256 asset map")
        if not _valid_sha_map(release.get("pypi_artifacts")):
            failures.append("release.json: published release requires SHA-256 PyPI artifact map")

        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        if f"version `{version}` is the current published" not in readme:
            failures.append("README does not identify the current version as published")
        if "release candidate — not yet published" in release_doc.lower():
            failures.append("release record still claims the published version is not published")
        if "status: **published" not in release_doc.lower():
            failures.append("release record does not contain a published status marker")
        if f"v{version}` is the current published" not in roadmap:
            failures.append("ROADMAP does not identify the current version as published")

        generic_workflows = (
            ROOT / ".github/workflows/pypi.yml",
            ROOT / ".github/workflows/release.yml",
        )
        for path in generic_workflows:
            if not path.is_file():
                failures.append(f"{path.relative_to(ROOT)}: reusable release workflow is missing")
        for path in (
            ROOT / f".github/workflows/tag-v{version}-on-main.yml",
            ROOT / f".github/workflows/release-v{version}.yml",
        ):
            if path.exists():
                failures.append(
                    f"{path.relative_to(ROOT)}: completed version-specific publication workflow remains"
                )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"OK: release metadata is aligned at {version} ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
