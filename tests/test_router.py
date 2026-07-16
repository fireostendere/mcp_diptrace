from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import CapabilityUnavailableError, RoutingError
from diptrace_mcp.geometry import distance
from diptrace_mcp.routing import (
    DifferentialPairRouteConfig,
    RouteConnectionConfig,
    synthesize_differential_pair_route,
    synthesize_route,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _document_with_keepout() -> DipTraceDocument:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    shapes = root.find("./Board/Shapes")
    assert shapes is not None
    keepout = ET.SubElement(
        shapes,
        "Shape",
        {
            "Id": "1",
            "Type": "Polygon",
            "Layer": "Route Keepout",
            "Locked": "N",
            "Selected": "N",
        },
    )
    points = ET.SubElement(keepout, "Points")
    for x, y in ((14, 8), (16, 8), (16, 10), (14, 10)):
        ET.SubElement(points, "Point", {"X": str(x), "Y": str(y)})
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _document_with_top_layer_barrier() -> DipTraceDocument:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    nets = root.find("./Board/Nets")
    assert nets is not None
    net = ET.SubElement(nets, "Net", {"Id": "2", "NetClass": "0", "Locked": "N"})
    ET.SubElement(net, "Name").text = "TOP_BARRIER"
    ET.SubElement(net, "Pads")
    traces = ET.SubElement(net, "Traces")
    trace = ET.SubElement(
        traces,
        "Trace",
        {
            "Id": "0",
            "Connected1": "Free",
            "Connected2": "Free",
            "Group": "-1",
            "PairSeparateTrace": "-1",
            "Selected": "N",
        },
    )
    points = ET.SubElement(trace, "Points")
    ET.SubElement(points, "Point", {"Id": "0", "X": "15", "Y": "0.5"})
    ET.SubElement(
        points,
        "Point",
        {
            "Id": "1",
            "X": "15",
            "Y": "29.5",
            "Lay": "0",
            "Width": "0.5",
            "Jumper": "0",
            "Arc": "N",
            "ViaStyle": "-1",
            "Selected": "N",
        },
    )
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _four_layer_document(*, lay1: str | None, lay2: str | None) -> DipTraceDocument:
    original = _document_with_top_layer_barrier()
    root = ET.fromstring(original.raw_bytes)
    layers = root.find("./Board/CopperLayers")
    style = root.find("./Board/ViaStyles/ViaStyle[@Id='0']")
    assert layers is not None and style is not None
    bottom = layers.find("./Lay[@Id='1']")
    assert bottom is not None
    bottom_index = list(layers).index(bottom)
    for offset, (layer_id, name) in enumerate((("2", "Inner 1"), ("3", "Inner 2"))):
        layer = ET.Element("Lay", {"Id": layer_id, "Type": "Signal"})
        ET.SubElement(layer, "Name").text = name
        layers.insert(bottom_index + offset, layer)
    style.attrib.pop("Diameter", None)
    style.attrib.pop("Hole", None)
    style.set("Size", "0.6")
    style.set("HoleSize", "0.3")
    if lay1 is not None:
        style.set("Lay1", lay1)
    if lay2 is not None:
        style.set("Lay2", lay2)
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _document_with_unrouted_diff_pair_and_top_barrier() -> DipTraceDocument:
    original = _document_with_top_layer_barrier()
    root = ET.fromstring(original.raw_bytes)
    for layer_rule in root.findall("./Board/NetClasses/NetClass/LayProperties/LayProperty"):
        layer_rule.set("DifClearance", "0.75")
    signal_traces = root.find("./Board/Nets/Net[@Id='1']/Traces")
    assert signal_traces is not None
    for trace in list(signal_traces):
        signal_traces.remove(trace)
    ratlines = root.find("./Board/Ratlines")
    assert ratlines is not None
    ET.SubElement(
        ratlines,
        "Ratline",
        {
            "Id": "1",
            "Hidden": "N",
            "X1": "10",
            "Y1": "10",
            "X2": "20",
            "Y2": "10",
            "Comp1": "0",
            "Pad1": "1",
            "Comp2": "1",
            "Pad2": "1",
        },
    )
    pairs = root.find("./Board/DifferentialPairs")
    assert pairs is not None
    pair = ET.SubElement(
        pairs,
        "DifferentialPair",
        {
            "Id": "0",
            "NetClass": "0",
            "PosNet": "0",
            "NegNet": "1",
            "RouteMode": "Dont Route",
            "AutoPadPoints": "N",
            "CustomColor": "N",
            "TraceColor": "0",
        },
    )
    ET.SubElement(pair, "Name").text = "PAIR"
    pad_points = ET.SubElement(pair, "PadPoints")
    ET.SubElement(
        pad_points,
        "PadPoint",
        {"Id": "0", "PosComp": "0", "PosPad": "0", "NegComp": "0", "NegPad": "1"},
    )
    ET.SubElement(
        pad_points,
        "PadPoint",
        {"Id": "1", "PosComp": "1", "PosPad": "0", "NegComp": "1", "NegPad": "1"},
    )
    ET.SubElement(pair, "Segments")
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _config(snapshot_document: DipTraceDocument) -> RouteConnectionConfig:
    snapshot = build_snapshot(snapshot_document)
    assert snapshot.board is not None
    net = next(item for item in snapshot.board.nets if item.name == "VCC")
    start, end = net.relationships["endpoints"]
    return RouteConnectionConfig(
        net=net.stable_id,
        start_object_id=start,
        end_object_id=end,
        layer="Top",
        width=0.25,
        clearance=0.2,
        grid=0.5,
    )


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_router_synthesizes_direct_45_degree_compatible_path() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    result = synthesize_route(build_snapshot(document), _config(document))

    assert [point.as_dict() for point in result.points] == [
        {"x": 10.0, "y": 9.0},
        {"x": 20.0, "y": 9.0},
    ]
    assert result.metrics["bend_count"] == 0
    assert result.metrics["detour"] == 1


def test_router_avoids_keepout_deterministically_and_compiles() -> None:
    document = _document_with_keepout()
    config = _config(document)
    first = synthesize_route(build_snapshot(document), config)
    second = synthesize_route(build_snapshot(document), config)

    assert first.points == second.points
    assert len(first.points) > 2
    assert first.metrics["detour"] > 1
    for start, end in zip(first.points, first.points[1:], strict=False):
        dx = abs(end.x - start.x)
        dy = abs(end.y - start.y)
        assert dx == 0 or dy == 0 or math.isclose(dx, dy)

    applied = apply_semantic_operations(document, [first.operation])
    snapshot = build_snapshot(applied.document)
    assert snapshot.board is not None
    vcc = next(item for item in snapshot.board.nets if item.name == "VCC")
    assert vcc.attributes["trace_count"] == 1
    routed_trace = next(item for item in snapshot.board.traces if item.net_name == "VCC")
    assert routed_trace.attributes["length_mm"] == first.metrics["length_mm"]


def test_multilayer_router_inserts_valid_vias_and_roundtrips() -> None:
    document = _document_with_top_layer_barrier()
    base = _config(document)
    config = base.model_copy(
        update={
            "preferred_layers": ["Top", "Bottom"],
            "start_layer": "Top",
            "end_layer": "Top",
            "via_style": "Default",
            "max_vias": 2,
            "max_detour": 6.0,
        }
    )
    route = synthesize_route(build_snapshot(document), config)

    assert route.metrics["via_count"] == 2
    assert route.metrics["layer_sequence"] == ["0", "1", "0"]
    via_points = [point for point in route.operation.points if point.via_style]
    assert len(via_points) == 2
    assert all(point.via_style == "0" for point in via_points)

    applied = apply_semantic_operations(document, [route.operation])
    snapshot = build_snapshot(applied.document)
    assert snapshot.board is not None
    vcc_trace = next(item for item in snapshot.board.traces if item.net_name == "VCC")
    assert vcc_trace.attributes["segment_layers"] == [
        point.layer or route.operation.layer for point in route.operation.points[1:]
    ]
    assert len(vcc_trace.relationships["vias"]) == 2


def test_documented_via_style_geometry_and_span_are_normalized() -> None:
    snapshot = build_snapshot(_four_layer_document(lay1="0", lay2="1"))
    assert snapshot.board is not None

    style = snapshot.board.via_styles[0]
    assert style.diameter_mm == pytest.approx(0.6)
    assert style.hole_mm == pytest.approx(0.3)
    assert style.layer_start_id == "0"
    assert style.layer_end_id == "1"
    assert style.span_layer_ids == ["0", "2", "3", "1"]
    assert style.span_source == "explicit"


def test_multilayer_router_rejects_transition_outside_blind_via_span() -> None:
    document = _four_layer_document(lay1="0", lay2="2")
    config = _config(document).model_copy(
        update={
            "preferred_layers": ["Top", "Bottom"],
            "start_layer": "Top",
            "end_layer": "Bottom",
            "via_style": "Default",
            "max_vias": 1,
        }
    )

    with pytest.raises(RoutingError, match="cannot connect the endpoint routing layers"):
        synthesize_route(build_snapshot(document), config)


def test_multilayer_router_rejects_unknown_span_on_four_layer_board() -> None:
    document = _four_layer_document(lay1=None, lay2=None)
    config = _config(document).model_copy(
        update={
            "preferred_layers": ["Top", "Bottom"],
            "via_style": "Default",
            "max_vias": 2,
        }
    )

    with pytest.raises(CapabilityUnavailableError, match="span is omitted"):
        synthesize_route(build_snapshot(document), config)

    capabilities = get_capabilities(document)
    assert capabilities.read_capabilities["multilayer_local_routing"] is False
    assert capabilities.experimental_capabilities["automatic_via_routing"] is False
    assert any(
        reason["feature"] == "automatic_via_routing"
        and "Lay1/Lay2" in reason["message"]
        for reason in capabilities.reasons_unavailable
    )


def test_coupled_diff_pair_router_inserts_symmetric_vias_atomically() -> None:
    document = _document_with_unrouted_diff_pair_and_top_barrier()
    route = synthesize_differential_pair_route(
        build_snapshot(document),
        DifferentialPairRouteConfig(
            pair="PAIR",
            layer="Top",
            preferred_layers=["Top", "Bottom"],
            width=0.25,
            gap=0.75,
            clearance=0.2,
            grid=0.5,
            via_style="Default",
            max_vias=2,
            max_detour=6.0,
        ),
    )

    assert route.metrics["via_count_per_net"] == 2
    assert route.metrics["symmetric_via_count"] == 4
    assert route.metrics["layer_sequence"] == ["0", "1", "0"]
    assert route.metrics["absolute_skew_mm"] == pytest.approx(0.0)
    assert all(
        distance(positive, negative) == pytest.approx(1.0)
        for positive, negative in zip(
            route.positive_points, route.negative_points, strict=True
        )
    )

    applied = apply_semantic_operations(document, [route.operation])
    snapshot = build_snapshot(applied.document)
    assert snapshot.board is not None
    pair = snapshot.board.differential_pairs[0]
    assert len(pair.segments) == 1
    positive = next(item for item in snapshot.board.traces if item.net_name == "VCC")
    negative = next(item for item in snapshot.board.traces if item.net_name == "SIGNAL")
    assert len(positive.relationships["vias"]) == 2
    assert len(negative.relationships["vias"]) == 2
    positive_vias = [snapshot.get_object(item).position for item in positive.relationships["vias"]]
    negative_vias = [snapshot.get_object(item).position for item in negative.relationships["vias"]]
    assert [item["x"] for item in positive_vias if item] == [
        item["x"] for item in negative_vias if item
    ]


def test_route_plan_commit_review_details_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    source = FIXTURES.joinpath("pcb.xml").read_bytes()
    board.write_bytes(source)
    service = _service(workspace, tmp_path / "state")

    unrouted = service.list_unrouted_connections(str(board))
    assert unrouted["result"]["matched_count"] == 1
    assert unrouted["result"]["items"][0]["net"] == "VCC"
    assert unrouted["result"]["items"][0]["ratline_length_mm"] == 10

    planned = service.plan_route_nets(
        ["VCC"], layer="Top", width=0.25, path=str(board)
    )
    plan = planned["result"]["plan"]
    assert plan["metrics"]["connection_count"] == 1
    assert plan["metrics"]["total_length_mm"] == 10
    assert len(planned["resources"]) == 4

    committed = service.apply_route_plan(plan["plan_id"], dry_run=False)
    assert committed["transaction"]["status"] == "committed"
    details = service.get_route_details(net="VCC", path=str(board))
    assert details["result"]["trace_count"] == 1
    assert details["result"]["total_length_mm"] == 10
    review = service.run_review(str(board), profile="connectivity", categories={"connectivity"})
    assert review["result"]["summary"]["finding_count"] == 0

    service.rollback_transaction(
        committed["transaction"]["txid"],
        committed["transaction"]["committed_sha256"],
    )
    assert board.read_bytes() == source


def test_diff_pair_plan_commit_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "pair.xml"
    source = _document_with_unrouted_diff_pair_and_top_barrier().raw_bytes
    board.write_bytes(source)
    service = _service(workspace, tmp_path / "state")

    planned = service.plan_diff_pair_route(
        "PAIR",
        layer="Top",
        preferred_layers=["Top", "Bottom"],
        width=0.25,
        gap=0.75,
        clearance=0.2,
        grid=0.5,
        via_style="Default",
        max_vias=2,
        max_detour=6.0,
        path=str(board),
    )
    plan = planned["result"]["plan"]
    assert plan["plan_type"] == "diff_pair_route"
    assert plan["metrics"]["symmetric_via_count"] == 4
    assert len(planned["resources"]) == 4

    committed = service.apply_route_plan(plan["plan_id"], dry_run=False)
    assert committed["transaction"]["status"] == "committed"
    root = ET.fromstring(board.read_bytes())
    assert len(root.findall("./Board/DifferentialPairs/DifferentialPair/Segments/Segment")) == 1
    assert len(root.findall("./Board/Nets/Net/Traces/Trace/Points/Point[@ViaStyle='0']")) == 4

    service.rollback_transaction(
        committed["transaction"]["txid"],
        committed["transaction"]["committed_sha256"],
    )
    assert board.read_bytes() == source
