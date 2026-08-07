from __future__ import annotations

import json
from pathlib import Path

from diptrace_mcp.manual_acceptance import (
    MANUAL_GATES,
    validate_manual_acceptance_pack,
    write_manual_acceptance_pack,
)


def test_manual_matrix_contains_only_external_or_human_categories() -> None:
    allowed = {"windows", "diptrace", "client", "distribution", "legal", "optional_external"}
    assert MANUAL_GATES
    assert {gate.category for gate in MANUAL_GATES} <= allowed
    assert len({gate.gate_id for gate in MANUAL_GATES}) == len(MANUAL_GATES)
    assert all(gate.action for gate in MANUAL_GATES)
    assert all(gate.required_evidence for gate in MANUAL_GATES)


def test_prepared_pack_starts_with_only_manual_pending_gates(tmp_path: Path) -> None:
    write_manual_acceptance_pack(tmp_path, version="0.2.1", commit="a" * 40)
    record = json.loads((tmp_path / "manual_acceptance.json").read_text(encoding="utf-8"))
    assert record["release_version"] == "0.2.1"
    assert {item["status"] for item in record["results"]} == {"pending"}
    assert "manual-only acceptance" in (tmp_path / "MANUAL_ACCEPTANCE.md").read_text(
        encoding="utf-8"
    )

    result = validate_manual_acceptance_pack(tmp_path)
    assert result["ok"] is False
    assert result["evidence_errors"] == []
    assert result["pending_blocking_gate_ids"]


def test_pass_requires_real_evidence_reference(tmp_path: Path) -> None:
    write_manual_acceptance_pack(tmp_path, version="0.2.1", commit="b" * 40)
    path = tmp_path / "manual_acceptance.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    first = next(item for item in record["results"] if item["gate_id"] == "diptrace_current_pcb_roundtrip")
    first["status"] = "pass"
    first["observed_version"] = "DipTrace 5.x"
    first["evidence_files"] = ["evidence/pcb.txt"]
    path.write_text(json.dumps(record), encoding="utf-8")

    result = validate_manual_acceptance_pack(tmp_path)
    assert any("missing evidence file" in item for item in result["evidence_errors"])


def test_evidence_paths_cannot_escape_pack(tmp_path: Path) -> None:
    write_manual_acceptance_pack(tmp_path, version="0.2.1", commit="c" * 40)
    path = tmp_path / "manual_acceptance.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    first = next(item for item in record["results"] if item["gate_id"] == "diptrace_current_pcb_roundtrip")
    first.update(
        {
            "status": "pass",
            "observed_version": "DipTrace 5.x",
            "evidence_files": ["../outside.txt"],
        }
    )
    path.write_text(json.dumps(record), encoding="utf-8")
    result = validate_manual_acceptance_pack(tmp_path)
    assert any("escapes acceptance directory" in item for item in result["evidence_errors"])
