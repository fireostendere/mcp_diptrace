"""Audit an extracted Windows portable bundle without executing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = (
    "app/diptrace_mcp_server.exe",
    "bridge/diptrace_mcp_bridge.exe",
    "tools/diptrace_mcp_configure/diptrace_mcp_configure.exe",
    "settings-templates/pcb.settings.xml",
    "settings-templates/schematic.settings.xml",
    "settings-templates/component.settings.xml",
    "settings-templates/pattern.settings.xml",
    "tools/settings/pcb.settings.xml",
    "tools/settings/schematic.settings.xml",
    "tools/settings/component.settings.xml",
    "tools/settings/pattern.settings.xml",
    "tools/install_plugin.ps1",
    "tools/uninstall_plugin.ps1",
    "LICENSE",
    "README_FIRST.txt",
    "VERSION",
    "artifact-inventory.json",
)
FORBIDDEN = re.compile(
    r"(?i)(^|/)(?:\.git|tests?|private|source(?:_pdfs?)?|extracted_text)(?:/|$)|\.pdf$"
)


class BundleAuditError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def audit_bundle(root: Path, checksum_file: Path | None = None) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise BundleAuditError(f"bundle root is not a directory: {root}")
    paths = list(root.rglob("*"))
    symlinks = sorted(_relative(root, path) for path in paths if path.is_symlink())
    if symlinks:
        raise BundleAuditError(f"symbolic links are forbidden in Windows bundle: {symlinks}")
    files = {_relative(root, path): path for path in paths if path.is_file()}
    forbidden = sorted(path for path in files if FORBIDDEN.search(path))
    if forbidden:
        raise BundleAuditError(f"forbidden bundle files: {forbidden}")
    missing = sorted(path for path in REQUIRED if path not in files)
    if missing:
        raise BundleAuditError(f"required bundle files are missing: {missing}")
    try:
        manifest = json.loads(files["artifact-inventory.json"].read_text(encoding="utf-8"))
        if not isinstance(manifest, list):
            raise TypeError
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise BundleAuditError("artifact-inventory.json is invalid") from exc
    inventory_paths: dict[str, dict[str, object]] = {}
    for item in manifest:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise BundleAuditError("artifact-inventory.json contains an invalid item")
        relative = item["path"]
        if relative in inventory_paths or relative in {"artifact-inventory.json", "SHA256SUMS.txt"}:
            raise BundleAuditError(
                f"artifact-inventory.json contains duplicate/reserved path: {relative}"
            )
        if (
            relative not in files
            or not isinstance(item.get("bytes"), int)
            or not isinstance(item.get("sha256"), str)
        ):
            raise BundleAuditError(
                f"artifact-inventory.json does not describe a regular bundle file: {relative}"
            )
        if item["bytes"] != files[relative].stat().st_size or item["sha256"].lower() != _sha256(
            files[relative]
        ):
            raise BundleAuditError(f"artifact-inventory.json hash/size mismatch: {relative}")
        inventory_paths[relative] = item
    expected_inventory_paths = set(files) - {"artifact-inventory.json", "SHA256SUMS.txt"}
    if set(inventory_paths) != expected_inventory_paths:
        raise BundleAuditError("artifact-inventory.json does not cover exactly the staged files")
    if checksum_file is not None:
        checksum_lines = [
            line.strip()
            for line in checksum_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        expected: dict[str, str] = {}
        for line in checksum_lines:
            digest, relative = line.split(maxsplit=1)
            relative = relative.removeprefix("*")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", digest) or relative in expected:
                raise BundleAuditError(f"invalid SHA256SUMS line: {line}")
            expected[relative] = digest.lower()
        actual_paths = set(files) - {"SHA256SUMS.txt"}
        if set(expected) != actual_paths:
            raise BundleAuditError("SHA256SUMS.txt does not cover exactly the extracted files")
        mismatches = sorted(path for path in actual_paths if _sha256(files[path]) != expected[path])
        if mismatches:
            raise BundleAuditError(f"SHA-256 mismatch: {mismatches}")
    return {
        "root": str(root),
        "files": len(files),
        "required_files": len(REQUIRED),
        "checksums_verified": checksum_file is not None,
        "geometry_bundle": any(
            (root / relative).exists()
            for relative in ("app/shapely", "app/_internal/shapely")
        ),
        "forbidden_files": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sha256", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        report = audit_bundle(args.root, args.sha256)
    except (OSError, ValueError) as exc:
        if args.as_json:
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"Windows bundle audit failed: {exc}")
        return 1
    if args.as_json:
        print(json.dumps({"ok": True, **report}, sort_keys=True))
    else:
        print(
            "Windows bundle audit passed: "
            f"{report['files']} files; checksums={report['checksums_verified']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
