#!/usr/bin/env python3
"""Audit declared dependency groups with pip-audit without changing dependencies."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local" / "open-source-readiness" / "deep-audit"


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    private_root = DEFAULT_OUTPUT.resolve()
    if resolved != private_root and private_root not in resolved.parents:
        raise ValueError(
            "dependency audit output must remain below .local/open-source-readiness/deep-audit"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _requirement_names(requirements: list[str]) -> set[str]:
    names: set[str] = set()
    for requirement in requirements:
        name = requirement.split("[", 1)[0]
        for separator in ("<", ">", "=", "!", "~", ";", " "):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def _groups(project: dict[str, Any]) -> dict[str, list[str]]:
    metadata = project["project"]
    optional = metadata.get("optional-dependencies", {})
    runtime = list(metadata.get("dependencies", []))
    build = list(project.get("build-system", {}).get("requires", []))
    return {
        "runtime": runtime,
        "geometry": runtime + list(optional.get("geometry", [])),
        "build": build,
        "pyinstaller": runtime + list(optional.get("bridge", [])),
        "development": runtime + list(optional.get("dev", [])),
    }


def _parse_report(path: Path, direct: set[str], group: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    dependencies = data.get("dependencies", []) if isinstance(data, dict) else []
    packages: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    if isinstance(dependencies, list):
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                continue
            name = str(dependency.get("name", ""))
            normalized = name.lower().replace("_", "-")
            packages.append(
                {
                    "name": name,
                    "version": dependency.get("version"),
                    "direct": normalized in direct,
                }
            )
            vulnerabilities = dependency.get("vulns", [])
            if isinstance(vulnerabilities, list):
                for vulnerability in vulnerabilities:
                    if not isinstance(vulnerability, dict):
                        continue
                    findings.append(
                        {
                            "package": name,
                            "installed_version": dependency.get("version"),
                            "advisory": vulnerability.get("id") or vulnerability.get("aliases"),
                            "affected_usage": "direct" if normalized in direct else "transitive",
                            "available_fix": vulnerability.get("fix_versions", []),
                            "direct_or_transitive": (
                                "direct" if normalized in direct else "transitive"
                            ),
                            "decision": "HUMAN ACTION REQUIRED",
                            "group": group,
                        }
                    )
    return {"packages": packages, "findings": findings}


def run(output: Path) -> tuple[dict[str, Any], int]:
    output = _safe_output(output)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    pip_audit = os.environ.get("PIP_AUDIT_BIN") or shutil.which("pip-audit")
    if not pip_audit:
        summary = {"status": "tool_unavailable", "tool": "pip-audit"}
        (output / "dependency-audit-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary, 3

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = _groups(project)
    summary: dict[str, Any] = {
        "tool": "pip-audit",
        "tool_version": subprocess.run(
            [pip_audit, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "pyproject": "pyproject.toml",
        "groups": {},
        "status": "clean",
        "finding_count": 0,
        "dependency_changes": "none; this script never invokes pip-audit --fix",
    }
    failures = 0
    with tempfile.TemporaryDirectory(prefix="diptrace-dependency-audit-") as temporary:
        temporary_root = Path(temporary)
        for group, requirements in groups.items():
            requirement_file = temporary_root / f"{group}.txt"
            requirement_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
            report_path = raw / f"pip-audit-{group}.json"
            command = [
                pip_audit,
                "-r",
                str(requirement_file),
                "--format",
                "json",
                "--progress-spinner",
                "off",
                "--output",
                str(report_path),
            ]
            completed = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, check=False
            )
            (raw / f"pip-audit-{group}.stdout.txt").write_text(
                completed.stdout, encoding="utf-8"
            )
            (raw / f"pip-audit-{group}.stderr.txt").write_text(
                completed.stderr, encoding="utf-8"
            )
            parsed = _parse_report(report_path, _requirement_names(requirements), group)
            result = {
                "status": completed.returncode,
                "declared_requirements": requirements,
                "direct_packages": sorted(_requirement_names(requirements)),
                **parsed,
            }
            summary["groups"][group] = result
            summary["finding_count"] += len(parsed["findings"])
            if completed.returncode not in (0, 1):
                failures += 1

    if summary["finding_count"]:
        summary["status"] = "findings"
    elif failures:
        summary["status"] = "tool_failure"
    (output / "dependency-audit-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary, 2 if summary["finding_count"] else (3 if failures else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary, code = run(args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
