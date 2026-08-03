#!/usr/bin/env python3
"""Build, compare, install, and smoke-test artifacts from a clean checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local" / "open-source-readiness" / "deep-audit" / "clean-room"
_BANNED_NAME_PARTS = (
    ".local",
    "docs/announcements",
    "application_draft",
    "permission_request",
    "forum_post",
    "forum_announcement",
    "reference/diptrace-xml/extracted_text",
    "reference/diptrace-xml/sources",
    "private/",
    "scancode-results",
    "release-dist",
)
_PLACEHOLDER_USERS = {
    "...",
    "<user>",
    "alice",
    "maintainer",
    "name",
    "operator",
    "private-owner",
    "test-user",
    "user",
    "username",
    "you",
}


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    private_root = (ROOT / ".local" / "open-source-readiness").resolve()
    if resolved != private_root and private_root not in resolved.parents:
        raise ValueError("clean-room output must remain below .local/open-source-readiness")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _run(command: list[str], cwd: Path, output: Path, name: str) -> int:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    (output / f"{name}.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (output / f"{name}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    return completed.returncode


def _archive_members(path: Path) -> Iterator[tuple[str, bytes]]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    yield info.filename, archive.read(info)
    else:
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                if member.isfile():
                    handle = archive.extractfile(member)
                    if handle is not None:
                        yield member.name, handle.read()


def _archive_audit(path: Path) -> dict[str, Any]:
    names: list[str] = []
    name_hits: list[str] = []
    content_hits: list[str] = []
    local_markers = {
        str(Path.home()).replace("\\", "/").rstrip("/"),
        str(ROOT).replace("\\", "/").rstrip("/"),
    }
    for name, content in _archive_members(path):
        folded = name.casefold()
        names.append(name)
        if any(part.casefold() in folded for part in _BANNED_NAME_PARTS):
            name_hits.append(name)
        text = content.decode("utf-8", errors="ignore")
        if any(marker and marker in text for marker in local_markers):
            content_hits.append(name)
        windows_users = re.findall(r"[A-Za-z]:\\Users\\([A-Za-z0-9._-]+)", text)
        unix_users = re.findall(r"/mnt/c/Users/([A-Za-z0-9._-]+)", text)
        personal_users = [
            user
            for user in windows_users + unix_users
            if user.casefold() not in _PLACEHOLDER_USERS
        ]
        if personal_users:
            content_hits.append(name)
    return {
        "artifact": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "member_count": len(names),
        "banned_member_names": sorted(set(name_hits)),
        "absolute_workstation_path_members": sorted(set(content_hits)),
        "ok": not name_hits and not content_hits,
    }


def _wheel_members(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: hashlib.sha256(archive.read(info)).hexdigest()
            for info in archive.infolist()
            if not info.is_dir()
        }


def _extract_sdist(path: Path, destination: Path) -> Path:
    with tarfile.open(path, "r:*") as archive:
        root_names = {Path(member.name).parts[0] for member in archive.getmembers() if member.name}
        if len(root_names) != 1:
            raise RuntimeError("sdist has no single top-level directory")
        root = root_names.pop()
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError("unsafe sdist member path")
        archive.extractall(destination)
    return destination / root


def _venv_python(path: Path) -> Path:
    return path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(source: Path, output: Path) -> tuple[dict[str, Any], int]:
    source = source.resolve()
    output = _safe_output(output)
    summary: dict[str, Any] = {
        "source": "clean checkout",
        "source_commit": "unknown",
        "status": "tool_failure",
        "stages": {},
        "artifacts": [],
        "excluded_content_check": "not run",
    }
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
    )
    summary["clean_checkout"] = not bool(status.stdout.strip())
    if not summary["clean_checkout"]:
        (output / "clean-checkout-status.txt").write_text(status.stdout, encoding="utf-8")
        summary["status"] = "dirty_checkout"
        (output / "clean-room-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary, 3
    summary["source_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True, check=True
    ).stdout.strip()

    direct = output / "direct"
    rebuilt = output / "rebuilt"
    direct.mkdir(exist_ok=True)
    rebuilt.mkdir(exist_ok=True)
    build_code = _run(
        [sys.executable, "-m", "hatchling", "build", "-d", str(direct)],
        source,
        output,
        "build-direct",
    )
    summary["stages"]["build_direct"] = build_code
    if build_code != 0:
        (output / "clean-room-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary, 3

    wheels = sorted(direct.glob("*.whl"))
    sdists = sorted(direct.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        summary["stages"]["artifact_discovery"] = "expected one wheel and one sdist"
        (output / "clean-room-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary, 3
    wheel, sdist = wheels[0], sdists[0]
    for artifact in (wheel, sdist):
        summary["artifacts"].append(_archive_audit(artifact))

    allowlist_code = _run(
        [
            sys.executable,
            "scripts/audit_release_artifacts.py",
            "--dist-dir",
            str(direct),
            "--check-allowlist",
        ],
        source,
        output,
        "release-allowlist",
    )
    summary["stages"]["release_allowlist"] = allowlist_code

    with tempfile.TemporaryDirectory(prefix="diptrace-sdist-") as extracted_dir:
        extracted = _extract_sdist(sdist, Path(extracted_dir))
        rebuild_code = _run(
            [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(rebuilt)],
            extracted,
            output,
            "build-from-sdist",
        )
    summary["stages"]["build_from_sdist"] = rebuild_code
    rebuilt_wheels = sorted(rebuilt.glob("*.whl"))
    if rebuild_code == 0 and len(rebuilt_wheels) == 1:
        direct_members = _wheel_members(wheel)
        rebuilt_members = _wheel_members(rebuilt_wheels[0])
        differences = sorted(
            name
            for name in set(direct_members) | set(rebuilt_members)
            if direct_members.get(name) != rebuilt_members.get(name)
        )
        summary["wheel_member_comparison"] = {
            "direct": wheel.name,
            "rebuilt": rebuilt_wheels[0].name,
            "same_members_and_sha256": not differences,
            "differences": differences,
        }

    with tempfile.TemporaryDirectory(prefix="diptrace-clean-install-") as environment_dir:
        environment = Path(environment_dir)
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = _venv_python(environment)
        install_code = _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                str(wheel),
            ],
            source,
            output,
            "install-wheel",
        )
        summary["stages"]["clean_install"] = install_code
        if install_code == 0:
            summary["stages"]["cli_help"] = _run(
                [str(python.parent / "diptrace-mcp"), "--help"], source, output, "cli-help"
            )
            summary["stages"]["mcp_stdio_smoke"] = _run(
                [
                    str(python),
                    str(source / "scripts" / "mcp_smoke.py"),
                    "--transport",
                    "stdio",
                    "--workspace",
                    str(source / "tests" / "fixtures"),
                    "--document",
                    "pcb.xml",
                ],
                source,
                output,
                "mcp-stdio-smoke",
            )

    passed = (
        summary["clean_checkout"]
        and all(stage == 0 for stage in summary["stages"].values() if isinstance(stage, int))
        and all(item["ok"] for item in summary["artifacts"])
        and summary.get("wheel_member_comparison", {}).get("same_members_and_sha256", False)
    )
    summary["excluded_content_check"] = (
        "pass" if all(item["ok"] for item in summary["artifacts"]) else "fail"
    )
    summary["status"] = "clean" if passed else "failed"
    (output / "clean-room-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary, 0 if passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary, code = run(args.source, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
