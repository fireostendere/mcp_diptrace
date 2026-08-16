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
    result = analyze_return_path(
        snapshot,
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=["GND"],
    )
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
        build_snapshot(document),
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=["GND"],
    )

    assert result.issues[0].issue_type == "unreferenced_segment"
    assert "not a full-wave" in result.assumptions[-1]


def test_reference_net_stable_identity_wins_over_duplicate_name() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000))
    assert snapshot.board is not None
    reference = next(net for net in snapshot.board.nets if net.name == "GND")
    duplicate = reference.model_copy(update={"stable_id": "duplicate_gnd", "xml_id": "99"})
    snapshot.board.nets.append(duplicate)
    snapshot.objects[duplicate.stable_id] = duplicate

    result = analyze_return_path(
        snapshot,
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=[reference.stable_id],
    )

    assert result.issues == []


def test_equal_rank_reference_layers_are_reported_unknown() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000))
    assert snapshot.board is not None
    top, dielectric, bottom = snapshot.board.stackup.layers
    right_dielectric = dielectric.model_copy(update={"index": 3})
    right_plane = bottom.model_copy(
        update={"index": 4, "layer_id": "2", "layer_name": "Other plane"}
    )
    snapshot.board.stackup.layers = [
        bottom.model_copy(update={"index": 0}),
        dielectric.model_copy(update={"index": 1}),
        top.model_copy(update={"index": 2}),
        right_dielectric,
        right_plane,
    ]

    result = analyze_return_path(
        snapshot,
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=["GND"],
    )

    assert result.issues
    assert all(item.issue_type == "reference_unknown" for item in result.issues)
    assert "More than one" in result.issues[0].explanation


def test_observed_layer_change_is_not_hidden_when_normalized_via_is_missing() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000))
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]
    trace.attributes["points"] = [
        {"x": 1.0, "y": 2.0},
        {"x": 6.0, "y": 2.0},
        {"x": 11.0, "y": 2.0},
    ]
    trace.attributes["segment_layers"] = ["0", "1"]

    result = analyze_return_path(
        snapshot,
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=["GND"],
    )

    assert result.transition_count == 1
    assert {(item["check_id"], item["reason"]) for item in result.skipped} >= {
        ("return_path.layer_transition", "normalized_signal_via_missing")
    }
    assert any(item.issue_type == "transition_without_return_via" for item in result.issues)


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
        "pcb.differential_pair_rules",
    }
    assert metrics["pcb.differential_pair_rules"]["skipped_checks"]


def test_bom_deduplicates_schematic_units_and_groups_exact_identity() -> None:
    schematic = build_snapshot(DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000))
    records = extract_bom(schematic)

    assert len(records) == 2
    u1 = next(item for item in records if item.refdes == ["U1"])
    assert len(u1.source_object_ids) == 2
    assert review_bom(records)["finding_count"] >= 1
    assert sum(item.quantity for item in group_bom(records)) == 2


def test_schematic_pcb_comparison_is_structured() -> None:
    schematic = build_snapshot(DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000))
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
        "diff_pair_pcb.xml",
        stitching_radius_mm=2.0,
        nets=["USB_D+"],
        reference_nets=["GND"],
    )

    assert bom["result"]["record_count"] == 2
    assert comparison["result"]["difference_count"] >= 1
    assert pours["result"]["matched_count"] == 1
    assert return_path["result"]["issues"] == []


def test_partial_differential_pair_checks_reduce_review_completeness(
    tmp_path: Path,
) -> None:
    service = DipTraceService(
        Settings(workspace=FIXTURES, allowed_roots=(FIXTURES,), state_dir=tmp_path)
    )

    review = service.run_review("diff_pair_pcb.xml", profile="default")

    assert review["result"]["summary"]["completeness"] < 1.0
    assert {item["check_id"] for item in review["result"]["skipped_checks"]} >= {
        "pcb.differential_pair_rules"
    }


def test_partial_differential_pair_review_keeps_evaluated_findings() -> None:
    original = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    net_class = root.find("./Board/NetClasses/NetClass")
    assert net_class is not None
    net_class.set("Tolerance", "0.01")
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, metrics, skipped, _count = run_checks(build_snapshot(document))

    assert any(finding.check_id == "diff_pair.length_tolerance" for finding in findings)
    assert metrics["pcb.differential_pair_rules"]["skipped_checks"]
    assert {item["check_id"] for item in skipped} >= {"pcb.differential_pair_rules"}


def test_provider_neutral_reviewer_harness_scores_stored_responses() -> None:
    from diptrace_mcp.advanced_review import (
        ReviewerEvaluationCase,
        ReviewerEvaluationResponse,
        build_reviewer_evaluation_report,
    )

    case = ReviewerEvaluationCase(
        case_id="pcb-hard-001",
        domain="pcb",
        input_sha256="a" * 64,
        ground_truth_status="approved_m11",
        expected_hard_findings=["plane-gap"],
        known_facts={"voltage_v": 3.3},
        required_unknowns=["load_current_a"],
        allowed_source_ids=["rule-pack-1"],
        acceptable_rankings=[["candidate-b", "candidate-a"]],
        connectivity_sha256="b" * 64,
    )
    response = ReviewerEvaluationResponse(
        case_id=case.case_id,
        hard_findings=["plane-gap"],
        facts={"voltage_v": 3.3},
        unknowns=["load_current_a"],
        source_ids=["rule-pack-1"],
        candidate_ranking=["candidate-b", "candidate-a"],
        output_connectivity_sha256="b" * 64,
    )
    report = build_reviewer_evaluation_report(
        [case],
        [response],
        model="stored-fixture",
        provider="offline",
        prompt_version="p1",
        rule_pack_version="r1",
    )
    assert report.metrics["hard_failure_recall"] == 1.0
    assert report.metrics["invented_facts"] == 0
    assert report.metrics["connectivity_regressions"] == 0
    assert report.ranking_stability == 1.0
    assert report.adjudications[0].passed is True


def test_reviewer_harness_blocks_unapproved_ground_truth() -> None:
    import pytest

    from diptrace_mcp.advanced_review import (
        ReviewerEvaluationCase,
        ReviewerEvaluationResponse,
        adjudicate_reviewer_response,
    )

    case = ReviewerEvaluationCase(
        case_id="pending",
        domain="schematic",
        input_sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="M11-approved"):
        adjudicate_reviewer_response(
            case,
            ReviewerEvaluationResponse(case_id="pending"),
        )
