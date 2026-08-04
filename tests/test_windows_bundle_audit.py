from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_windows_bundle import REQUIRED, BundleAuditError, audit_bundle


def _make_bundle(root: Path) -> Path:
    for relative in REQUIRED:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text("[]", encoding="utf-8")
        else:
            path.write_bytes(relative.encode("utf-8"))
    inventory = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "artifact-inventory.json":
            continue
        inventory.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (root / "artifact-inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    return root


def _write_checksums(root: Path) -> Path:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "SHA256SUMS.txt":
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
    checksum = root / "SHA256SUMS.txt"
    checksum.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum


def test_bundle_audit_checks_required_files_and_exact_sha_manifest(tmp_path: Path) -> None:
    root = _make_bundle(tmp_path / "bundle")
    checksum = _write_checksums(root)
    report = audit_bundle(root, checksum)
    assert report["checksums_verified"] is True


def test_bundle_audit_rejects_forbidden_pdf(tmp_path: Path) -> None:
    root = _make_bundle(tmp_path / "bundle")
    forbidden = root / "reference" / "source.pdf"
    forbidden.parent.mkdir()
    forbidden.write_bytes(b"forbidden")
    with pytest.raises(BundleAuditError, match="forbidden"):
        audit_bundle(root)


def test_bundle_audit_rejects_checksum_drift(tmp_path: Path) -> None:
    root = _make_bundle(tmp_path / "bundle")
    checksum = _write_checksums(root)
    (root / REQUIRED[0]).write_bytes(b"changed")
    with pytest.raises(BundleAuditError, match="mismatch"):
        audit_bundle(root, checksum)


def test_bundle_audit_rejects_inventory_drift(tmp_path: Path) -> None:
    root = _make_bundle(tmp_path / "bundle")
    inventory = json.loads((root / "artifact-inventory.json").read_text(encoding="utf-8"))
    inventory[0]["bytes"] += 1
    (root / "artifact-inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(BundleAuditError, match="hash/size mismatch"):
        audit_bundle(root)
