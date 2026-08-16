from __future__ import annotations

import hashlib
import json
from pathlib import Path

from diptrace_mcp.evidence_report import build_evidence_report, render_evidence_report_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate(root: Path, *, tamper_reexport: bool = False) -> Path:
    source = (FIXTURES / "pcb.xml").read_bytes()
    open_save = source
    reexport = source.replace(b"10k", b"11k", 1)
    payloads = {"source": source, "open_save": open_save, "reexport": reexport}
    stages = {}
    for stage, payload in payloads.items():
        relative = Path(".diptrace-capture") / "quarantine" / "session-1" / stage / f"{stage}.xml"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        stages[stage] = {
            "stage": stage,
            "quarantine_path": relative.as_posix(),
            "sha256": _sha(payload),
            "operator_attestations": {"confirmed": True},
            "warnings": [],
        }
    if tamper_reexport:
        (root / stages["reexport"]["quarantine_path"]).write_bytes(b"tampered")
    candidate = {
        "schema_version": "diptrace-capture-candidate-v1",
        "session_id": "session-1",
        "authority": "operator_supplied_unverified",
        "trust_grant": "none",
        "candidate_only": True,
        "review_status": "pending_independent_review",
        "eligible_for_registry_review": True,
        "review_blockers": [],
        "recipe": {"snapshot": {"recipe_id": "report-test"}},
        "operator_claims": {"diptrace_version": "5.3.0.3"},
        "stages": stages,
        "checklist": {
            "opened": {"required": True, "answer": "yes"},
            "visual": {"required": False, "answer": "not_applicable"},
        },
    }
    path = root / ".diptrace-capture" / "candidates" / "session-1.candidate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    return path


def test_evidence_report_verifies_hashes_and_semantic_deltas(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)

    report = build_evidence_report(candidate, tmp_path)

    assert report.report_status == "complete_review_only"
    assert report.trust_grant == "none"
    assert all(item.integrity == "verified" for item in report.stages)
    comparisons = {(item.first_stage, item.second_stage): item for item in report.comparisons}
    assert comparisons[("source", "open_save")].delta is not None
    assert comparisons[("source", "open_save")].delta.semantic_equal is True
    assert comparisons[("source", "open_save")].connectivity_equal is True
    assert comparisons[("source", "reexport")].delta is not None
    assert comparisons[("source", "reexport")].delta.semantic_equal is False
    assert comparisons[("source", "reexport")].connectivity_equal is True
    assert report.summary["connectivity_changed_pairs"] == []
    assert all(item.domain_summary["kind"] == "pcb" for item in report.stages)
    assert report.summary["all_required_checklist_yes"] is True


def test_evidence_report_detects_post_capture_artifact_tamper(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path, tamper_reexport=True)

    report = build_evidence_report(candidate, tmp_path)

    assert report.report_status == "integrity_failure"
    reexport = next(item for item in report.stages if item.stage == "reexport")
    assert reexport.integrity == "mismatch"
    assert "reexport" in report.summary["integrity_failures"]


def test_evidence_report_markdown_is_deterministic_and_never_claims_pass(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    report = build_evidence_report(candidate, tmp_path)

    first = render_evidence_report_markdown(report)
    second = render_evidence_report_markdown(report)

    assert first == second
    assert "Trust grant: `none`" in first
    assert "does not grant provenance trust" in first
    assert "**PASS**" not in first
