#!/usr/bin/env python3
"""Run redacted secret scans over the tracked tree and reachable Git history.

Raw reports are deliberately written only below ``.local/open-source-readiness``.
The committed result is a sanitized count and rule/plugin summary; it never
contains secret values, fingerprints, absolute paths, usernames, or raw scanner
output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local" / "open-source-readiness" / "deep-audit"
CONFIG = ROOT / "scripts" / "gitleaks.toml"


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    private_root = DEFAULT_OUTPUT.resolve()
    if resolved != private_root and private_root not in resolved.parents:
        raise ValueError(
            "raw audit output must remain below .local/open-source-readiness/deep-audit"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _run(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> int:
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        completed = subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr, check=False)
    return completed.returncode


def _run_json_stdout(
    command: list[str], *, cwd: Path, report_path: Path, stderr_path: Path
) -> int:
    with report_path.open("w", encoding="utf-8") as report, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        completed = subprocess.run(command, cwd=cwd, stdout=report, stderr=stderr, check=False)
    return completed.returncode


def _tracked_stage(destination: Path) -> int:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    count = 0
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8")
        if relative == ".local" or relative.startswith(".local/"):
            continue
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        count += 1
    return count


def _reachable_history_stage(destination: Path) -> int:
    completed = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    objects: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        sha, _, path = line.partition(" ")
        if len(sha) == 40 and path and path != ".local" and not path.startswith(".local/"):
            objects.setdefault(sha, path)

    requests = "".join(f"{sha}\n" for sha in objects).encode("ascii")
    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        check=True,
        input=requests,
        capture_output=True,
    )
    output = completed.stdout
    offset = 0
    count = 0
    for sha, relative in objects.items():
        header_end = output.index(b"\n", offset)
        header = output[offset:header_end].split()
        if len(header) != 3 or header[0].decode("ascii") != sha:
            raise RuntimeError(f"unexpected cat-file response for {sha}")
        size = int(header[2])
        payload_start = header_end + 1
        blob = output[payload_start : payload_start + size]
        offset = payload_start + size + 1
        if header[1] != b"blob":
            continue
        target = destination / sha / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        count += 1
    return count


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _relative_path(value: object) -> str:
    text = str(value or "")
    root_text = str(ROOT).replace("\\", "/")
    text = text.replace("\\", "/")
    if text.startswith(root_text + "/"):
        text = text.removeprefix(root_text + "/")
    current_match = re.search(r"/(?:current)/(.+)$", text)
    if current_match:
        return current_match.group(1)
    history_match = re.search(r"/history/[0-9a-f]{40}/(.+)$", text)
    if history_match:
        return history_match.group(1)
    if re.match(r"^(?:/|[A-Za-z]:/)", text):
        return "<absolute-path>"
    return text.lstrip("/")


def _gitleaks_summary(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    findings = data if isinstance(data, list) else []
    rules = Counter()
    paths: set[str] = set()
    for item in findings:
        if not isinstance(item, dict):
            continue
        rules[str(item.get("RuleID") or item.get("Description") or "unknown")] += 1
        paths.add(_relative_path(item.get("File")))
    return {
        "scanner": "gitleaks",
        "report": path.name,
        "finding_count": len(findings),
        "rules": dict(sorted(rules.items())),
        "paths": sorted(path for path in paths if path),
    }


def _detect_secrets_summary(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    results = data.get("results", {}) if isinstance(data, dict) else {}
    if not isinstance(results, dict):
        results = {}
    plugins = Counter()
    paths: set[str] = set()
    finding_count = 0
    for raw_path, items in results.items():
        if not isinstance(items, list):
            continue
        paths.add(_relative_path(raw_path))
        finding_count += len(items)
        for item in items:
            if isinstance(item, dict):
                plugins[str(item.get("type") or "unknown")] += 1
    return {
        "scanner": "detect-secrets",
        "report": path.name,
        "finding_count": finding_count,
        "plugins": dict(sorted(plugins.items())),
        "paths": sorted(path for path in paths if path),
    }


def _tool_path(name: str) -> str:
    value = os.environ.get(name.upper().replace("-", "_") + "_BIN")
    if value:
        return value
    executable = shutil.which(name)
    if executable:
        return executable
    raise FileNotFoundError(f"required audit tool is unavailable: {name}")


def run(output: Path) -> tuple[dict[str, Any], int]:
    output = _safe_output(output)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    summary: dict[str, Any] = {
        "scope": {
            "current_tree": "git ls-files only",
            "reachable_history": "git rev-list --objects --all",
            "excluded": [".local/"],
        },
        "tools": {},
        "scans": [],
    }
    failures = 0
    findings = 0

    try:
        gitleaks = _tool_path("gitleaks")
        completed = subprocess.run(
            [gitleaks, "version"], capture_output=True, text=True, check=True
        )
        summary["tools"]["gitleaks"] = completed.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        summary["tools"]["gitleaks"] = f"unavailable: {exc}"
        failures += 1
        gitleaks = ""

    try:
        detect_secrets = _tool_path("detect-secrets")
        completed = subprocess.run(
            [detect_secrets, "--version"], capture_output=True, text=True, check=True
        )
        summary["tools"]["detect-secrets"] = completed.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        summary["tools"]["detect-secrets"] = f"unavailable: {exc}"
        failures += 1
        detect_secrets = ""

    with tempfile.TemporaryDirectory(prefix="diptrace-secret-audit-") as temporary:
        temporary_root = Path(temporary)
        current = temporary_root / "current"
        history = temporary_root / "history"
        current.mkdir()
        history.mkdir()
        summary["scope"]["tracked_file_count"] = _tracked_stage(current)
        summary["scope"]["reachable_blob_count"] = _reachable_history_stage(history)

        if gitleaks:
            scans = (
                (
                    "gitleaks_current",
                    [
                        gitleaks,
                        "dir",
                        "--no-banner",
                        "--redact",
                        "--config",
                        str(CONFIG),
                        "--report-format",
                        "json",
                        "--report-path",
                        str(raw / "gitleaks-current.json"),
                        "--exit-code",
                        "0",
                        str(current),
                    ],
                    raw / "gitleaks-current.json",
                ),
                (
                    "gitleaks_history",
                    [
                        gitleaks,
                        "git",
                        "--no-banner",
                        "--redact",
                        "--config",
                        str(CONFIG),
                        "--log-opts=--all",
                        "--report-format",
                        "json",
                        "--report-path",
                        str(raw / "gitleaks-history.json"),
                        "--exit-code",
                        "0",
                        str(ROOT),
                    ],
                    raw / "gitleaks-history.json",
                ),
            )
            for name, command, location in scans:
                code = _run(
                    command,
                    cwd=ROOT,
                    stdout_path=raw / f"{name}.stdout.txt",
                    stderr_path=raw / f"{name}.stderr.txt",
                )
                if code != 0:
                    failures += 1
                report = _gitleaks_summary(location)
                summary["scans"].append({"command": "gitleaks", "status": code, **report})
                findings += int(report["finding_count"])

        if detect_secrets:
            for name, directory, report_name in (
                ("detect-secrets_current", current, "detect-secrets-current.json"),
                ("detect-secrets_history", history, "detect-secrets-history.json"),
            ):
                report_path = raw / report_name
                code = _run_json_stdout(
                    [
                        detect_secrets,
                        "scan",
                        "--all-files",
                        "--exclude-files",
                        r"(^|/)\.local(/|$)",
                        "--exclude-files",
                        r"(^|/)\.git(/|$)",
                        str(directory),
                    ],
                    cwd=ROOT,
                    report_path=report_path,
                    stderr_path=raw / f"{name}.stderr.txt",
                )
                if code != 0:
                    failures += 1
                report = _detect_secrets_summary(report_path)
                summary["scans"].append(
                    {"command": "detect-secrets", "status": code, **report}
                )
                findings += int(report["finding_count"])

    summary["finding_count"] = findings
    summary["status"] = "findings" if findings else ("tool_failure" if failures else "clean")
    summary_path = output / "secret-scan-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary, 2 if findings else (3 if failures else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary, code = run(args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
