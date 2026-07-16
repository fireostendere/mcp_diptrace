from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.bom import extract_bom, group_bom, review_bom
from diptrace_mcp.config import Settings
from diptrace_mcp.design_compare import compare_schematic_to_pcb
from diptrace_mcp.return_path import analyze_plane_continuity, analyze_return_path
from diptrace_mcp.review import run_checks
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_copper_pour_and_return_path_use_exported_geometry() -> None:
    document = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    assert snapshot.board is not None
    assert len(snapshot.board.copper_pours) == 1
    pour = snapshot.board.copper_pours[0]
    assert pour.net_name == "GND"
    assert pour.attributes["poured"] is True
    plane = analyze_plane_continuity(snapshot)
    assert plane["items"][0]["boundary_area_mm2"] > 180
    result = analyze_return_path(snapshot, nets=["USB_D+"], reference_nets=["GND"])
    assert result.segment_count == 1
    assert result.issues == []
    assert result.confidence == "low"


def test_return_path_reports_missing_reference_pour_without_false_full_wave_claim() -> None:
    original = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    pour = root.find("./Board/CopperPours/CopperPour")
    assert pour is not None
    pour.set("Poured", "N")
    document = DipTraceDocument.from_bytes(
        original.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )

    result = analyze_return_path(
        build_snapshot(document), nets=["USB_D+"], reference_nets=["GND"]
    )

    assert result.issues[0].issue_type == "unreferenced_segment"
    assert "not a full-wave" in result.assumptions[-1]


def test_advanced_review_checks_diff_pair_and_manufacturing_rules() -> None:
    document = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    findings, metrics, skipped, count = run_checks(build_snapshot(document))

    assert count == 16
    assert metrics["pcb.differential_pair_rules"]["pairs_checked"] == 1
    assert metrics["pcb.stackup_completeness"]["completeness"] == "complete"
    assert not any(item.check_id.startswith("diff_pair.") for item in findings)
    assert {item["check_id"] for item in skipped} >= {
        "pcb.min_trace_width",
        "pcb.via_drill_annular_ring",
        "pcb.trace_board_edge",
    }


def test_bom_deduplicates_schematic_units_and_groups_exact_identity() -> None:
    schematic = build_snapshot(
        DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    )
    records = extract_bom(schematic)

    assert len(records) == 2
    u1 = next(item for item in records if item.refdes == ["U1"])
    assert len(u1.source_object_ids) == 2
    assert review_bom(records)["finding_count"] >= 1
    assert sum(item.quantity for item in group_bom(records)) == 2


def test_schematic_pcb_comparison_is_structured() -> None:
    schematic = build_snapshot(
        DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    )
    pcb = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))

    result = compare_schematic_to_pcb(schematic, pcb)

    assert result["components"]["schematic_count"] == 2
    assert result["components"]["pcb_count"] == 2
    assert result["difference_count"] >= 1
    assert result["confidence"] == "medium"


def test_advanced_service_contract(tmp_path: Path) -> None:
    service = DipTraceService(
        Settings(workspace=FIXTURES, allowed_roots=(FIXTURES,), state_dir=tmp_path)
    )

    bom = service.get_bom("schematic.xml", grouped=False)
    comparison = service.compare_schematic_to_pcb("schematic.xml", "pcb.xml")
    pours = service.list_copper_pours("diff_pair_pcb.xml")
    return_path = service.analyze_return_path(
        "diff_pair_pcb.xml", nets=["USB_D+"], reference_nets=["GND"]
    )

    assert bom["result"]["record_count"] == 2
    assert comparison["result"]["difference_count"] >= 1
    assert pours["result"]["matched_count"] == 1
    assert return_path["result"]["issues"] == []
