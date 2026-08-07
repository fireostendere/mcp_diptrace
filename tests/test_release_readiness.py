from __future__ import annotations

from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.release_readiness import run_release_readiness
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_release_readiness_reports_automatable_and_manual_boundaries() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    report = run_release_readiness(snapshot)

    assert report["status"] in {"blocked", "review", "informational"}
    assert report["metrics"]["components"] >= 1
    assert "dft_explicit_testpoint_coverage" in report["metrics"]
    assert report["manual_gates"]
    assert any("fabrication/assembly" in item for item in report["manual_gates"])
    assert any("deterministic heuristics" in item for item in report["limitations"])


def test_release_readiness_detects_duplicate_refdes() -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes()
    marker = b"<RefDes>U1</RefDes>"
    assert marker in raw
    mutated = raw.replace(marker, b"<RefDes>R1</RefDes>", 1)
    snapshot = build_snapshot(DipTraceDocument.from_bytes(Path("duplicate.dip"), mutated))

    report = run_release_readiness(snapshot)

    assert report["status"] == "blocked"
    assert report["metrics"]["duplicate_refdes_count"] == 1
    assert any(item["check_id"] == "release.duplicate_refdes" for item in report["findings"])


def test_release_readiness_is_not_applicable_to_schematic() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000))
    report = run_release_readiness(snapshot)
    assert report["status"] == "not_applicable"
    assert report["findings"] == []
