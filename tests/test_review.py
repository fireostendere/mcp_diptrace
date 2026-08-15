from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.review as review_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.geometry_backend import shapely_available
from diptrace_mcp.review import registry, run_checks
from diptrace_mcp.routing import RouteConnectionConfig, synthesize_route
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
    assert "pcb.net_without_traces" in codes
    without_traces = next(item for item in findings if item.check_id == "pcb.net_without_traces")
    assert without_traces.severity == "error"
    assert without_traces.net_ids
    assert metrics["pcb.net_without_traces"]["nets_checked"] == 2
    assert "pcb.component_overlap" in registry.ids()


def test_poured_net_is_not_reported_as_unrouted_and_hidden_silk_is_ignored() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    pours = root.find("./Board/CopperPours")
    if pours is None:
        board = root.find("./Board")
        assert board is not None
        pours = ET.SubElement(board, "CopperPours")
    pour = ET.SubElement(
        pours,
        "CopperPour",
        {"Id": "0", "NetId": "0", "Lay": "0", "Poured": "Y"},
    )
    points = ET.SubElement(pour, "Points")
    for x, y in ((0, 0), (30, 0), (30, 30), (0, 30)):
        ET.SubElement(points, "Point", {"X": str(x), "Y": str(y)})
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, metrics, _, _ = run_checks(
        build_snapshot(document), categories={"connectivity", "silkscreen"}
    )

    assert not any(item.check_id == "pcb.net_without_traces" for item in findings)
    assert metrics["pcb.silk_overlap"]["texts_checked"] == 2


def test_degenerate_trace_check_does_not_claim_connectivity_analysis() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    points = root.find("./Board/Nets/Net/Traces/Trace/Points")
    assert points is not None
    for point in list(points)[1:]:
        points.remove(point)
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, metrics, _, _ = run_checks(build_snapshot(document), categories={"connectivity"})

    finding = next(item for item in findings if item.check_id == "pcb.degenerate_trace_path")
    assert "dangling" not in finding.title.lower()
    assert finding.object_ids
    assert metrics["pcb.degenerate_trace_path"]["traces_checked"] >= 1


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

    findings, _, _, _ = run_checks(build_snapshot(document), categories={"placement"})
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

    findings, metrics, _, _ = run_checks(build_snapshot(document), categories={"clearance"})
    violation = next(item for item in findings if item.check_id == "pcb.trace_clearance")
    assert violation.measured == pytest.approx(0.05)
    assert violation.required == pytest.approx(0.2)
    assert violation.delta == pytest.approx(-0.15)
    assert violation.layer == "0"
    assert metrics["pcb.trace_clearance"]["candidate_pairs_checked"] >= 1


def _trace_pair_snapshot(
    *,
    unresolved_net_id: str | None = "__keep__",
    unknown_class: bool = False,
    remove_rules: bool = False,
    add_second_unresolved: bool = False,
) -> object:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    traces = root.find("./Board/Nets/Net[@Id='0']/Traces")
    assert traces is not None

    def add_trace(trace_id: str, y: str) -> None:
        trace = ET.SubElement(traces, "Trace", {"Id": trace_id, "Selected": "N"})
        points = ET.SubElement(trace, "Points")
        ET.SubElement(
            points,
            "Point",
            {"Id": "0", "X": "10", "Y": y, "Lay": "0", "Width": "0.25"},
        )
        ET.SubElement(
            points,
            "Point",
            {"Id": "1", "X": "20", "Y": y, "Lay": "0", "Width": "0.25"},
        )

    add_trace("review-pair", "10.3")
    if add_second_unresolved:
        add_trace("review-unresolved", "10.6")
    if unknown_class:
        net = root.find("./Board/Nets/Net[@Id='0']")
        assert net is not None
        net.set("NetClass", "does-not-exist")
    if remove_rules:
        for item in root.findall("./Board/DRC/LayClearances/LayClearance"):
            item.attrib.pop("TraceToTrace", None)
        for item in root.findall("./Board/NetClasses/NetClass/LayProperties/LayProperty"):
            item.attrib.pop("Clearance", None)

    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    added = next(
        item for item in snapshot.board.traces if item.attributes.get("Id") == "review-pair"
    )
    if unresolved_net_id != "__keep__":
        added.net_id = unresolved_net_id
    if add_second_unresolved:
        extra = next(
            item
            for item in snapshot.board.traces
            if item.attributes.get("Id") == "review-unresolved"
        )
        extra.net_id = None
    return snapshot


def _write_unresolved_trace_document(path: Path) -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    nets = root.find("./Board/Nets")
    assert nets is not None
    net = ET.SubElement(nets, "Net", {"Name": "UNRESOLVED"})
    traces = ET.SubElement(net, "Traces")
    trace = ET.SubElement(traces, "Trace", {"Id": "unresolved", "Selected": "N"})
    points = ET.SubElement(trace, "Points")
    for point_id, x in enumerate(("10", "20")):
        ET.SubElement(
            points,
            "Point",
            {
                "Id": str(point_id),
                "X": x,
                "Y": "10.3",
                "Lay": "0",
                "Width": "0.25",
            },
        )
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def test_trace_clearance_partial_reason_reaches_review_report(tmp_path: Path) -> None:
    path = tmp_path / "unresolved.xml"
    _write_unresolved_trace_document(path)

    result = _service(tmp_path, tmp_path / "state").run_review(
        "unresolved.xml",
        profile="drc_partial",
        categories={"clearance"},
    )

    assert result["clearance_review_complete"] is False
    assert result["netclass_rules_ignored"] is True
    assert result["result"]["skipped_reasons"][0]["check_id"] == "pcb.trace_clearance"
    assert result["result"]["skipped_reasons"][0]["reason"]["reason_code"] == (
        "trace_net_unresolved"
    )
    assert result["result"]["metrics"]["pcb.trace_clearance"]["evaluated_pairs"] == 0


@pytest.mark.parametrize("unresolved_net_id", [None, "does-not-exist"])
def test_trace_clearance_discloses_unresolved_owning_net(
    unresolved_net_id: str | None,
) -> None:
    snapshot = _trace_pair_snapshot(unresolved_net_id=unresolved_net_id)

    findings, metrics, skipped, _ = run_checks(snapshot, categories={"clearance"})

    trace_metrics = metrics["pcb.trace_clearance"]
    assert findings == []
    assert skipped == [{"check_id": "pcb.trace_clearance", "reason": "trace_clearance_partial"}]
    assert trace_metrics["candidate_pairs_checked"] == 1
    assert trace_metrics["evaluated_pairs"] == 0
    assert trace_metrics["skipped_unresolved_net_pairs"] == 1
    assert trace_metrics["skipped_clearance_resolution_pairs"] == 0
    assert trace_metrics["clearance_review_complete"] is False
    assert trace_metrics["warning_codes"] == ["trace_net_unresolved"]
    assert trace_metrics["skipped_pair_reasons"][0]["reason_code"] == ("trace_net_unresolved")
    assert metrics["clearance_review_complete"] is False
    assert trace_metrics["clearance_rule_status"]["netclass_rules_ignored"] is False
    assert metrics["netclass_rules_ignored"] is True
    assert metrics["clearance_rule_status"]["partial_review"] is True


def test_trace_clearance_discloses_unknown_netclass_and_does_not_find_violation() -> None:
    snapshot = _trace_pair_snapshot(unknown_class=True)

    findings, metrics, skipped, _ = run_checks(snapshot, categories={"clearance"})

    trace_metrics = metrics["pcb.trace_clearance"]
    assert findings == []
    assert skipped == [{"check_id": "pcb.trace_clearance", "reason": "trace_clearance_partial"}]
    assert trace_metrics["candidate_pairs_checked"] == 1
    assert trace_metrics["evaluated_pairs"] == 0
    assert trace_metrics["skipped_unresolved_net_pairs"] == 0
    assert trace_metrics["skipped_clearance_resolution_pairs"] == 1
    assert trace_metrics["warning_codes"] == ["trace_netclass_unresolved"]
    assert trace_metrics["clearance_review_complete"] is False


def test_trace_clearance_reports_whole_check_skip_when_rules_are_absent() -> None:
    snapshot = _trace_pair_snapshot(remove_rules=True)

    findings, metrics, skipped, _ = run_checks(snapshot, categories={"clearance"})

    trace_metrics = metrics["pcb.trace_clearance"]
    assert findings == []
    assert skipped == [
        {
            "check_id": "pcb.trace_clearance",
            "reason": "trace_clearance_rules_unavailable",
        }
    ]
    assert trace_metrics["candidate_pairs_checked"] == 0
    assert trace_metrics["candidate_pairs_not_enumerated"] is True
    assert trace_metrics["evaluated_pairs"] == 0
    assert trace_metrics["skipped_clearance_resolution_pairs"] == 0
    assert trace_metrics["skipped_pair_reasons_total"] == 1
    assert trace_metrics["skipped_pair_reasons_truncated"] is False
    assert trace_metrics["warning_codes"] == ["trace_clearance_rules_unavailable"]
    assert trace_metrics["skipped_pair_reasons"] == [
        {
            "reason_code": "trace_clearance_rules_unavailable",
            "scope": "check",
        }
    ]
    assert metrics["netclass_rules_ignored"] is False
    assert metrics["clearance_review_complete"] is False


def test_trace_clearance_reports_evaluated_and_skipped_pairs_together() -> None:
    snapshot = _trace_pair_snapshot(add_second_unresolved=True)

    findings, metrics, skipped, _ = run_checks(snapshot, categories={"clearance"})

    trace_metrics = metrics["pcb.trace_clearance"]
    assert any(item.check_id == "pcb.trace_clearance" for item in findings)
    assert skipped == [{"check_id": "pcb.trace_clearance", "reason": "trace_clearance_partial"}]
    assert trace_metrics["candidate_pairs_checked"] >= 2
    assert trace_metrics["evaluated_pairs"] >= 1
    assert trace_metrics["skipped_unresolved_net_pairs"] >= 1
    assert trace_metrics["clearance_review_complete"] is False


def test_trace_clearance_bounds_skipped_pair_reason_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_module, "MAX_SKIPPED_PAIR_REASONS", 1)
    snapshot = _trace_pair_snapshot(add_second_unresolved=True)

    _, metrics, _, _ = run_checks(snapshot, categories={"clearance"})

    trace_metrics = metrics["pcb.trace_clearance"]
    assert trace_metrics["skipped_pair_reasons_total"] > 1
    assert len(trace_metrics["skipped_pair_reasons"]) == 1
    assert trace_metrics["skipped_pair_reasons_truncated"] is True
    assert trace_metrics["clearance_review_complete"] is False


def test_router_and_trace_review_use_the_same_netclass_clearance() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    property_element = root.find("./Board/NetClasses/NetClass[@Id='0']/LayProperties/LayProperty")
    assert property_element is not None
    property_element.set("Clearance", "0.45")
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
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    vcc = next(item for item in snapshot.board.nets if item.name == "VCC")
    start, end = vcc.relationships["endpoints"]
    route = synthesize_route(
        snapshot,
        RouteConnectionConfig(
            net=vcc.stable_id,
            start_object_id=start,
            end_object_id=end,
            layer="Top",
            width=0.25,
            clearance=None,
        ),
    )

    findings, metrics, _, _ = run_checks(snapshot, categories={"clearance"})

    violation = next(item for item in findings if item.check_id == "pcb.trace_clearance")
    assert route.clearance_resolution["effective_clearance_mm"] == pytest.approx(0.45)
    assert route.metrics["effective_rule_source"] == "netclass_and_board"
    assert violation.required == pytest.approx(0.45)
    assert metrics["pcb.trace_clearance"]["clearance_rule_status"]["netclass_rules_applied"] is True
    assert violation.rule_source == "netclass_and_board"
    assert violation.required_clearance_mm == pytest.approx(0.45)
    assert violation.requested_clearance_mm is None
    assert violation.effective_clearance_mm == pytest.approx(0.45)
    assert violation.clearance_rule_status is not None
    assert violation.clearance_rule_status["effective_rule_source"] == ("netclass_and_board")
    assert {item["kind"] for item in violation.rule_sources} == {"board_default", "netclass"}


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
    assert obstacle.bbox["max_x"] - obstacle.bbox["min_x"] == pytest.approx(1.979898987, rel=1e-6)

    findings, metrics, _, _ = run_checks(snapshot, categories={"clearance"})
    violation = next(item for item in findings if item.check_id == "pcb.trace_object_clearance")
    assert violation.measured == pytest.approx(0.0)
    assert violation.required == pytest.approx(0.2)
    assert violation.rule_source.endswith("TraceToPad")
    assert metrics["pcb.trace_object_clearance"]["geometry_backend"] == "shapely_geos"


def test_erc_reports_unconnected_pin_not_intentional_no_connect() -> None:
    document = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    findings, metrics, _, count = run_checks(build_snapshot(document))

    assert count == 5
    unconnected = [item for item in findings if item.check_id == "schematic.unconnected_pin"]
    assert len(unconnected) == 1
    assert unconnected[0].object_ids
    assert metrics["schematic.unconnected_pin"]["pins_checked"] == 6


def test_erc_does_not_require_values_on_net_ports() -> None:
    original = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    library = root.find("./Library")
    part = root.find("./Schematic/Components/Part[@Id='0']")
    assert library is not None and part is not None
    components = ET.SubElement(library, "Components")
    component = ET.SubElement(components, "Component", {"ComponentStyle": "CompType0"})
    ET.SubElement(component, "Part", {"Id": "0", "PartType": "Net Port"})
    value = part.find("./Value")
    assert value is not None
    value.text = ""
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    findings, _, _, _ = run_checks(build_snapshot(document), categories={"metadata"})

    assert not [item for item in findings if item.check_id == "schematic.missing_value"]


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
    assert summary["completeness"] == 14 / 16
    assert result["result"]["skipped_checks"] == [
        {"check_id": "pcb.trace_board_edge", "reason": "trace_to_board_rules_unavailable"},
        {
            "check_id": "pcb.thermal_metadata",
            "reason": "explicit_component_power_metadata_unavailable",
        },
        {"check_id": "pcb.silk_to_pad", "reason": "not_implemented"},
    ]
    report_id = summary["report_id"]
    finding_id = next(
        item["finding_id"]
        for item in result["result"]["findings"]
        if item["check_id"] == "pcb.net_without_traces"
    )

    stored = service.get_findings(report_id)
    assert any(item["finding_id"] == finding_id for item in stored["findings"])
    assert service.get_finding(finding_id)["finding"]["check_id"] == "pcb.net_without_traces"
    resource = service.review_resource(report_id)
    assert report_id in resource
    assert "pcb.net_without_traces" in resource


def test_review_discloses_unimplemented_silk_to_pad_with_pad_geometry(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    shutil.copyfile(FIXTURES / "exact_geometry_pcb.xml", board)
    service = _service(workspace, tmp_path / "state")

    result = service.run_review(str(board), profile="board_review")

    assert "pcb.silk_to_pad" not in registry.ids()
    assert {"check_id": "pcb.silk_to_pad", "reason": "not_implemented"} in result["result"][
        "skipped_checks"
    ]
