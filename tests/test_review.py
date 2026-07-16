from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.geometry_backend import shapely_available
from diptrace_mcp.review import registry, run_checks
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_registry_runs_real_board_connectivity_checks() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    findings, metrics, skipped, count = run_checks(build_snapshot(document))

    assert count == 16
    assert skipped == [
        {"check_id": "pcb.trace_board_edge", "reason": "trace_to_board_rules_unavailable"},
        {
            "check_id": "pcb.thermal_metadata",
            "reason": "explicit_component_power_metadata_unavailable",
        },
    ]
    codes = [finding.check_id for finding in findings]
    assert "pcb.unrouted_net" in codes
    unrouted = next(item for item in findings if item.check_id == "pcb.unrouted_net")
    assert unrouted.severity == "error"
    assert unrouted.net_ids
    assert metrics["pcb.unrouted_net"]["nets_checked"] == 2
    assert "pcb.component_overlap" in registry.ids()


def test_capabilities_are_derived_from_review_registry() -> None:
    capabilities = get_capabilities()

    assert capabilities.registered_checks == registry.ids()
    assert capabilities.read_capabilities["structured_findings"] is True


def test_component_overlap_finding_is_geometry_backed() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='1']")
    assert component is not None
    component.set("X", "10.2")
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, _, _, _ = run_checks(
        build_snapshot(document), categories={"placement"}
    )
    overlap = next(item for item in findings if item.check_id == "pcb.component_overlap")
    assert overlap.severity == "error"
    assert len(overlap.object_ids) == 2
    assert overlap.bbox is not None
    assert overlap.confidence == 0.55


def test_trace_clearance_uses_segment_geometry_and_drc_rule() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    traces = root.find("./Board/Nets/Net[@Id='0']/Traces")
    assert traces is not None
    trace = ET.SubElement(traces, "Trace", {"Id": "0", "Selected": "N"})
    points = ET.SubElement(trace, "Points")
    ET.SubElement(points, "Point", {"Id": "0", "X": "10", "Y": "10.3"})
    ET.SubElement(
        points,
        "Point",
        {
            "Id": "1",
            "X": "20",
            "Y": "10.3",
            "Lay": "0",
            "Width": "0.25",
            "ViaStyle": "-1",
        },
    )
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, metrics, _, _ = run_checks(
        build_snapshot(document), categories={"clearance"}
    )
    violation = next(item for item in findings if item.check_id == "pcb.trace_clearance")
    assert violation.measured == pytest.approx(0.05)
    assert violation.required == pytest.approx(0.2)
    assert violation.delta == pytest.approx(-0.15)
    assert violation.layer == "0"
    assert metrics["pcb.trace_clearance"]["candidate_pairs_checked"] >= 1


@pytest.mark.skipif(not shapely_available(), reason="geometry extra is not installed")
def test_spatial_drc_uses_transformed_exact_pad_geometry() -> None:
    document = DipTraceDocument.load(FIXTURES / "exact_geometry_pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    obstacle = next(item for item in snapshot.board.pads if item.net_name == "OBSTACLE")

    assert obstacle.geometry is not None
    assert obstacle.geometry.kind == "rectangle"
    assert obstacle.geometry.rotation_deg == pytest.approx(45.0)
    assert obstacle.bbox is not None
    assert obstacle.bbox["max_x"] - obstacle.bbox["min_x"] == pytest.approx(
        1.979898987, rel=1e-6
    )

    findings, metrics, _, _ = run_checks(snapshot, categories={"clearance"})
    violation = next(
        item for item in findings if item.check_id == "pcb.trace_object_clearance"
    )
    assert violation.measured == pytest.approx(0.0)
    assert violation.required == pytest.approx(0.2)
    assert violation.rule_source.endswith("TraceToPad")
    assert metrics["pcb.trace_object_clearance"]["geometry_backend"] == "shapely_geos"


def test_erc_reports_unconnected_pin_not_intentional_no_connect() -> None:
    document = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    findings, metrics, _, count = run_checks(build_snapshot(document))

    assert count == 5
    unconnected = [
        item for item in findings if item.check_id == "schematic.unconnected_pin"
    ]
    assert len(unconnected) == 1
    assert unconnected[0].object_ids
    assert metrics["schematic.unconnected_pin"]["pins_checked"] == 6


def test_review_service_persists_report_and_resources(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    shutil.copyfile(FIXTURES / "pcb.xml", board)
    service = _service(workspace, tmp_path / "state")

    result = service.run_review(str(board), profile="board_review")
    summary = result["result"]["summary"]
    assert summary["finding_count"] == 8
    assert summary["by_severity"]["error"] == 1
    assert summary["completeness"] == 14 / 17
    assert result["result"]["skipped_checks"] == [
        {"check_id": "pcb.trace_board_edge", "reason": "trace_to_board_rules_unavailable"},
        {
            "check_id": "pcb.thermal_metadata",
            "reason": "explicit_component_power_metadata_unavailable",
        },
        {"check_id": "pcb.silk_to_pad", "reason": "pad_geometry_unavailable"}
    ]
    report_id = summary["report_id"]
    finding_id = next(
        item["finding_id"]
        for item in result["result"]["findings"]
        if item["check_id"] == "pcb.unrouted_net"
    )

    stored = service.get_findings(report_id)
    assert any(item["finding_id"] == finding_id for item in stored["findings"])
    assert service.get_finding(finding_id)["finding"]["check_id"] == "pcb.unrouted_net"
    resource = service.review_resource(report_id)
    assert report_id in resource
    assert "pcb.unrouted_net" in resource
