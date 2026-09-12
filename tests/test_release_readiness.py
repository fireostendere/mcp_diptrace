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



def test_readiness_uses_bom_population_and_manufacturer_aliases() -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes().replace(
        b"<RefDes>R1</RefDes>",
        b"<RefDes>R1</RefDes><AddFields><AddField><Name>Populate</Name>"
        b"<Text>no</Text></AddField></AddFields>",
    ).replace(
        b"<RefDes>U1</RefDes>",
        b"<RefDes>U1</RefDes><AddFields><AddField><Name>mfr</Name>"
        b"<Text>Synthetic</Text></AddField><AddField><Name>MPN</Name>"
        b"<Text>TEST-1</Text></AddField></AddFields>",
    )
    snapshot = build_snapshot(DipTraceDocument.from_bytes(Path("test.xml"), raw))
    report = run_release_readiness(snapshot)
    assert report["metrics"]["populated_components"] == 1
    assert report["metrics"]["missing_procurement_identity_count"] == 0


def test_readiness_blocks_unidentified_assembly_component() -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes().replace(b"<RefDes>R1</RefDes>", b"<RefDes />")
    snapshot = build_snapshot(DipTraceDocument.from_bytes(Path("test.xml"), raw))
    report = run_release_readiness(snapshot)
    assert report["status"] == "blocked"
    assert any(item["check_id"] == "release.missing_refdes" for item in report["findings"])
