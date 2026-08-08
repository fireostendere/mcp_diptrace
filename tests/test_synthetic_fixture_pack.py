from __future__ import annotations

import json
from pathlib import Path

from diptrace_mcp.synthetic_fixture_pack import (
    build_synthetic_fixture_bytes,
    synthetic_fixture_manifest,
    validate_synthetic_fixture_pack,
    write_synthetic_fixture_pack,
)


def test_synthetic_pack_is_deterministic_and_explicitly_unverified(tmp_path: Path) -> None:
    first = build_synthetic_fixture_bytes()
    second = build_synthetic_fixture_bytes()
    assert first == second
    manifest = synthetic_fixture_manifest(first)
    assert manifest["diptrace_verified"] is False
    assert "diptrace_roundtrip_verified" in manifest["non_claims"]
    assert all(item["diptrace_verified"] is False for item in manifest["files"])


def test_written_pack_validates_and_manifest_hashes_bind_files(tmp_path: Path) -> None:
    manifest = write_synthetic_fixture_pack(tmp_path)
    result = validate_synthetic_fixture_pack(tmp_path)
    assert result == {
        "ok": True,
        "errors": [],
        "file_count": 6,
        "diptrace_verified": False,
    }
    disk_manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert disk_manifest == manifest


def test_tampering_is_detected(tmp_path: Path) -> None:
    write_synthetic_fixture_pack(tmp_path)
    (tmp_path / "pattern_library.xml").write_text("<tampered/>", encoding="utf-8")
    result = validate_synthetic_fixture_pack(tmp_path)
    assert result["ok"] is False
    assert "sha256:pattern_library.xml" in result["errors"]
