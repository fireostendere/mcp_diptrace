from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.provenance_registry import TrustedProvenanceRegistry
from scripts.audit_acceptance_seeds import (
    DEFAULT_ROOT,
    SeedAuditError,
    audit_seed_root,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_acceptance_seeds.py"
DOC = ROOT / "docs" / "ACCEPTANCE_SEED_AUDIT.md"
SYNTHETIC_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Source Type="DipTrace-PCB" Version="5.3.0.0" Units="mm"><Board/></Source>\n'
)


def _manifest(
    fixture_path: str = "board.xml",
    *,
    fixture_bytes: bytes = SYNTHETIC_XML,
    source_type: str = "DipTrace-PCB",
) -> dict[str, Any]:
    return {
        "schema_version": "diptrace-fixture-manifest-v2",
        "diptrace": {
            "version": "5.3.0.0",
            "build": "synthetic-stand-in-not-a-real-build",
            "operating_system": "synthetic-test-environment",
        },
        "redistribution": {
            "permitted": True,
            "basis": "Temporary synthetic stand-in generated outside the acceptance tree.",
        },
        "fixtures": [
            {
                "path": fixture_path,
                "source_type": source_type,
                "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
                "validation_level": "synthetic_parser_only",
                "provenance": "synthetic_test_stand_in_not_diptrace_evidence",
                "units": "mm",
                "workflow": "Temporary auditor contract test; DipTrace was not involved.",
                "purpose": "Exercise manifest/path/hash/source-type validation only.",
                "format_version": "5.3.0.0",
            }
        ],
    }


def _write_stand_in(root: Path) -> None:
    root.mkdir()
    (root / "board.xml").write_bytes(SYNTHETIC_XML)
    (root / "manifest.json").write_text(
        json.dumps(_manifest(), indent=2) + "\n",
        encoding="utf-8",
    )


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_cli(seed_root: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(seed_root)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _documented_stand_in_code() -> str:
    documentation = DOC.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- SYNTHETIC_STANDIN_PY_BEGIN -->\n"
        r"```python\n(?P<code>.*?)```\n"
        r"<!-- SYNTHETIC_STANDIN_PY_END -->",
        documentation,
        re.DOTALL,
    )
    assert match is not None
    return match.group("code")


def test_default_acceptance_seed_directory_reports_zero_seeds() -> None:
    before = _tree_snapshot(DEFAULT_ROOT)

    report = audit_seed_root(DEFAULT_ROOT)

    assert report["status"] == "no_seeds"
    assert report["seed_count"] == 0
    assert report["seeds"] == []
    assert report["trust_promoted"] is False
    assert report["registry_consulted"] is True
    assert report["registry_match"] is False
    assert report["registry_entry_count"] == TrustedProvenanceRegistry.load_embedded().entry_count
    assert report["written"] is False
    assert _tree_snapshot(DEFAULT_ROOT) == before


def test_documented_synthetic_stand_in_procedure_runs_outside_acceptance_tree(
    tmp_path: Path,
) -> None:
    seed_root = tmp_path / "stand-in"
    environment = dict(os.environ)
    environment["SEED_AUDIT_STANDIN_ROOT"] = str(seed_root)
    generated = subprocess.run(
        [sys.executable, "-c", _documented_stand_in_code()],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert generated.returncode == 0, generated.stderr
    assert Path(generated.stdout.strip()) == seed_root
    before = _tree_snapshot(seed_root)

    completed = _run_cli(seed_root)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "valid"
    assert report["seed_count"] == 1
    assert report["seeds"][0]["source_type"] == "DipTrace-PCB"
    assert report["seeds"][0]["validation_level"] == "synthetic_parser_only"
    assert report["trust_promoted"] is False
    assert report["registry_consulted"] is True
    assert report["registry_match"] is False
    assert report["registry_entry_count"] == TrustedProvenanceRegistry.load_embedded().entry_count
    assert report["sidecar_authority_used"] is False
    assert report["written"] is False
    assert _tree_snapshot(seed_root) == before
    documentation = DOC.read_text(encoding="utf-8")
    assert "synthetic_test_stand_in_not_diptrace_evidence" in documentation
    assert "python scripts/audit_acceptance_seeds.py --root" in documentation


def test_audit_rejects_tampered_seed_sha(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    _write_stand_in(seed_root)
    (seed_root / "board.xml").write_bytes(SYNTHETIC_XML + b" ")

    with pytest.raises(SeedAuditError, match="SHA-256 mismatch"):
        audit_seed_root(seed_root)


def test_audit_rejects_manifest_path_traversal_without_reading_outside_root(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "board.xml"
    outside.write_bytes(SYNTHETIC_XML)
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    manifest = _manifest("../board.xml")
    (seed_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    completed = _run_cli(seed_root)

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["status"] == "invalid"
    assert report["trust_promoted"] is False
    assert "schema validation failed" in report["errors"][0]
    assert outside.read_bytes() == SYNTHETIC_XML


def test_audit_rejects_declared_source_type_mismatch(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "board.xml").write_bytes(SYNTHETIC_XML)
    (seed_root / "manifest.json").write_text(
        json.dumps(_manifest(source_type="DipTrace-Schematic")),
        encoding="utf-8",
    )

    with pytest.raises(SeedAuditError, match="source type mismatch"):
        audit_seed_root(seed_root)


def test_audit_rejects_duplicate_fixture_paths_even_if_entries_differ(
    tmp_path: Path,
) -> None:
    seed_root = tmp_path / "seeds"
    _write_stand_in(seed_root)
    manifest = _manifest()
    duplicate = dict(manifest["fixtures"][0])
    duplicate["purpose"] = "A second declaration for the same path."
    manifest["fixtures"].append(duplicate)
    (seed_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SeedAuditError, match="duplicate fixture path"):
        audit_seed_root(seed_root)


def test_audit_rejects_escaping_difference_reference(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    _write_stand_in(seed_root)
    manifest = _manifest()
    manifest["fixtures"][0]["difference_from"] = {
        "path": "../outside.xml",
        "single_change": "Synthetic path-safety test only.",
    }
    (seed_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SeedAuditError, match="not canonical and relative"):
        audit_seed_root(seed_root)


def test_audit_rejects_unlisted_runtime_file(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    _write_stand_in(seed_root)
    (seed_root / "extra.xml").write_bytes(SYNTHETIC_XML)

    with pytest.raises(SeedAuditError, match="unlisted runtime file"):
        audit_seed_root(seed_root)


def test_audit_rejects_seed_data_without_manifest(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "board.xml").write_bytes(SYNTHETIC_XML)

    with pytest.raises(SeedAuditError, match="exists without manifest.json"):
        audit_seed_root(seed_root)


def test_audit_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "manifest.json").write_text(
        '{"schema_version":"diptrace-fixture-manifest-v2",'
        '"schema_version":"diptrace-fixture-manifest-v2"}',
        encoding="utf-8",
    )

    with pytest.raises(SeedAuditError, match="duplicate key"):
        audit_seed_root(seed_root)


def test_audit_rejects_linked_fixture(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    outside = tmp_path / "outside.xml"
    outside.write_bytes(SYNTHETIC_XML)
    try:
        (seed_root / "board.xml").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"platform cannot create a test symlink: {exc}")
    (seed_root / "manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")

    with pytest.raises(SeedAuditError, match="linked file"):
        audit_seed_root(seed_root)
