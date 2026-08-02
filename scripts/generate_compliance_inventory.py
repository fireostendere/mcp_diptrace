#!/usr/bin/env python3
"""Generate deterministic dependency inventory, CycloneDX SBOM, and notices."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import tomllib

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "compliance"
INVENTORY_PATH = OUTPUT_DIR / "dependency-inventory.json"
SBOM_PATH = OUTPUT_DIR / "sbom.cdx.json"
NOTICES_PATH = OUTPUT_DIR / "THIRD_PARTY_NOTICES.md"

KNOWN_LICENSES = {
    "hatchling": "MIT",
    "hypothesis": "MPL-2.0",
    "jsonschema": "MIT",
    "mcp": "MIT",
    "mypy": "MIT",
    "pydantic": "MIT",
    "pyinstaller": "GPL-2.0-or-later WITH Bootloader-exception",
    "pytest": "MIT",
    "pytest-cov": "MIT",
    "pyyaml": "MIT",
    "ruff": "MIT",
    "shapely": "BSD-3-Clause",
    "typing-extensions": "PSF-2.0",
}
COPyleft = {"hypothesis", "pyinstaller"}
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise ValueError(f"cannot parse dependency requirement: {requirement!r}")
    return match.group(1)


def _project_metadata() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


def _groups(metadata: dict[str, Any]) -> dict[str, list[str]]:
    project = metadata["project"]
    optional = project.get("optional-dependencies", {})
    return {
        "runtime": list(project.get("dependencies", [])),
        "geometry": list(optional.get("geometry", [])),
        "bridge": list(optional.get("bridge", [])),
        "development": list(optional.get("dev", [])),
        "build": list(metadata["build-system"].get("requires", [])),
    }


def _dependency_records(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    by_name: dict[str, str] = {}
    for group, requirements in _groups(metadata).items():
        for requirement in requirements:
            name = _requirement_name(requirement)
            normalized = _normalize_name(name)
            grouped[normalized].add(group)
            by_name[normalized] = name

    records: list[dict[str, Any]] = []
    for normalized in sorted(grouped):
        license_name = KNOWN_LICENSES.get(normalized, "UNKNOWN")
        declared_requirements = {
            requirement
            for group, requirements in _groups(metadata).items()
            if group in grouped[normalized]
            for requirement in requirements
            if _normalize_name(_requirement_name(requirement)) == normalized
        }
        records.append(
            {
                "name": by_name[normalized],
                "normalized_name": normalized,
                "declared_groups": sorted(grouped[normalized]),
                "declared_requirements": sorted(declared_requirements),
                "version": None,
                "purl": f"pkg:pypi/{normalized}",
                "license": license_name,
                "license_basis": (
                    "engineering mapping from project metadata; human verification required"
                ),
                "copyleft_or_special_terms": normalized in COPyleft,
                "human_review_required": True,
            }
        )
    return records


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _date_time(inspected_date: str) -> str:
    date.fromisoformat(inspected_date)
    return f"{inspected_date}T00:00:00Z"


def _build_outputs(inspected_commit: str, inspected_date: str) -> dict[str, str]:
    metadata = _project_metadata()
    project = metadata["project"]
    records = _dependency_records(metadata)
    groups = {
        group: sorted(_requirement_name(requirement) for requirement in requirements)
        for group, requirements in _groups(metadata).items()
    }
    unresolved = sorted(
        record["name"] for record in records if record["license"] == "UNKNOWN"
    )
    special_terms = sorted(
        record["name"] for record in records if record["copyleft_or_special_terms"]
    )
    inventory: dict[str, Any] = {
        "schema_version": 1,
        "generated_by": "scripts/generate_compliance_inventory.py",
        "inspected_commit": inspected_commit,
        "inspected_date": inspected_date,
        "project": {
            "name": project["name"],
            "version": project["version"],
            "license": project["license"],
        },
        "resolution": {
            "kind": "declarative-direct-dependency-inventory",
            "source": "pyproject.toml",
            "resolved_versions": "not embedded; resolve in a clean release environment",
            "transitive_dependencies": "not enumerated by this deterministic source inventory",
        },
        "groups": groups,
        "components": records,
        "human_review_required": {
            "unknown_license_metadata": unresolved,
            "copyleft_or_special_terms": special_terms,
            "bundled_native_libraries": [
                "Windows PyInstaller bridge bundle must be inspected per release"
            ],
            "reference_materials": [
                "Verbatim external documentation extracts are removed; the replacement inventory "
                "contains project-authored fixture observations only"
            ],
        },
    }

    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://github.com/fireostendere/mcp_diptrace/compliance/{inspected_commit}/{inspected_date}",
    )
    project_ref = f"pkg:pypi/{_normalize_name(project['name'])}@{project['version']}"
    sbom_components: list[dict[str, Any]] = []
    for record in records:
        license_value = record["license"]
        license_entry: dict[str, Any]
        if license_value == "UNKNOWN":
            license_entry = {"license": {"name": "UNKNOWN"}}
        elif " WITH " in license_value:
            license_entry = {"expression": license_value}
        else:
            license_entry = {"license": {"id": license_value}}
        sbom_components.append(
            {
                "type": "library",
                "bom-ref": record["purl"],
                "name": record["name"],
                "purl": record["purl"],
                "scope": "required" if "runtime" in record["declared_groups"] else "optional",
                "licenses": [license_entry],
                "properties": [
                    {
                        "name": "diptrace-mcp:declared-groups",
                        "value": ",".join(record["declared_groups"]),
                    },
                    {"name": "diptrace-mcp:license-review", "value": "human_review_required"},
                ],
            }
        )
    sbom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": _date_time(inspected_date),
            "tools": [{"vendor": "DipTrace MCP", "name": "generate_compliance_inventory.py"}],
            "component": {
                "type": "application",
                "bom-ref": project_ref,
                "name": project["name"],
                "version": project["version"],
                "purl": project_ref,
                "licenses": [{"license": {"id": project["license"]}}],
            },
            "properties": [
                {"name": "diptrace-mcp:inspected-commit", "value": inspected_commit},
                {"name": "diptrace-mcp:inspection-date", "value": inspected_date},
                {"name": "diptrace-mcp:resolution", "value": inventory["resolution"]["kind"]},
            ],
        },
        "components": sbom_components,
        "dependencies": [
            {
                "ref": project_ref,
                "dependsOn": [
                    record["purl"]
                    for record in records
                    if "runtime" in record["declared_groups"]
                ],
            }
        ],
    }

    notice_lines = [
        "# Third-party notices",
        "",
        "This file is a reproducible engineering inventory of direct dependencies declared by",
        "`pyproject.toml`. It is not legal advice and does not conclude that a release is cleared",
        "for redistribution. Verify each dependency's current license text, notices, transitive",
        "dependencies, and any bundled native library before publishing an artifact.",
        "",
        f"Inventory binding: commit `{inspected_commit}`, inspected date `{inspected_date}`.",
        "",
        "The Python wheel declares dependencies but does not vendor them. The Windows bridge is a",
        "PyInstaller bundle and requires a separate per-build contents and notice review.",
        "",
        "| Dependency | Declared groups | Declared requirement(s) | "
        "License metadata used by this inventory | Review |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        notice_lines.append(
            "| `{name}` | {groups} | {requirements} | `{license}` | human review required |".format(
                name=record["name"],
                groups=", ".join(record["declared_groups"]),
                requirements="; ".join(record["declared_requirements"]),
                license=record["license"],
            )
        )
    notice_lines.extend(
        [
            "",
            "## Open review items",
            "",
            "- Resolve unknown or incomplete license metadata from authoritative upstream files.",
            "- Review `hypothesis` and the PyInstaller licensing/bootloader exception "
            "before any bundled release.",
            "- Inspect the actual Windows bridge bundle and record all bundled native "
            "libraries and notices.",
            "- Keep any external documentation material outside release archives; the replacement "
            "factual inventory is project-authored observation data and is not a normative source.",
        ]
    )

    return {
        INVENTORY_PATH.name: json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        SBOM_PATH.name: json.dumps(sbom, indent=2, sort_keys=True) + "\n",
        NOTICES_PATH.name: "\n".join(notice_lines) + "\n",
    }


def _existing_binding() -> tuple[str, str]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return str(payload["inspected_commit"]), str(payload["inspected_date"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--inspected-commit")
    parser.add_argument("--inspected-date")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.check:
        inspected_commit, inspected_date = _existing_binding()
    else:
        inspected_commit = args.inspected_commit or _git_head()
        inspected_date = args.inspected_date or date.today().isoformat()
    outputs = _build_outputs(inspected_commit, inspected_date)
    if args.check:
        mismatches = [
            name
            for name, expected in outputs.items()
            if not (OUTPUT_DIR / name).is_file()
            or (OUTPUT_DIR / name).read_text(encoding="utf-8") != expected
        ]
        if mismatches:
            print("FAIL: generated compliance outputs differ: " + ", ".join(mismatches))
            return 1
        print("OK: compliance inventory, SBOM, and notices are deterministic")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (OUTPUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(outputs)} compliance outputs bound to {inspected_commit} / {inspected_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
