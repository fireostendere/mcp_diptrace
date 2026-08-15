from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.routing as routing_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import RoutingError
from diptrace_mcp.multirouter import synthesize_routes_with_retry
from diptrace_mcp.pcb_autorouter import (
    PCBRouterConfig,
    plan_pcb_routes,
    resolve_trace_width,
)
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.routing import RouteConnectionConfig, synthesize_route_min_vias
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str = "pcb.xml") -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def _top_barrier() -> DipTraceDocument:
    original = _load()
    root = ET.fromstring(original.raw_bytes)
    nets = root.find("./Board/Nets")
    assert nets is not None
    net = ET.SubElement(nets, "Net", {"Id": "2", "NetClass": "0", "Locked": "N"})
    ET.SubElement(net, "Name").text = "TOP_BARRIER"
    ET.SubElement(net, "Pads")
    trace = ET.SubElement(ET.SubElement(net, "Traces"), "Trace", {"Id": "0"})
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
            "ViaStyle": "-1",
        },
    )
    return DipTraceDocument.from_bytes(Path("barrier.dip"), ET.tostring(root))


def _block_board() -> DipTraceDocument:
    original = _load("pcb_patterns.xml")
    root = ET.fromstring(original.raw_bytes)
    board = root.find("./Board")
    assert board is not None
    nets = board.find("./Nets")
    ratlines = board.find("./Ratlines")
    assert nets is not None and ratlines is not None
    net = ET.SubElement(nets, "Net", {"Id": "0", "NetClass": "0", "Locked": "N"})
    ET.SubElement(net, "Name").text = "CTRL"
    pads = ET.SubElement(net, "Pads")
    ET.SubElement(pads, "Item", {"Comp": "0", "Pad": "1"})
    ET.SubElement(pads, "Item", {"Comp": "2", "Pad": "0"})
    ET.SubElement(net, "Traces")
    ET.SubElement(
        ratlines,
        "Ratline",
        {
            "Id": "0",
            "Hidden": "N",
            "X1": "11.1",
            "Y1": "10",
            "X2": "19",
            "Y2": "20",
            "Comp1": "0",
            "Pad1": "1",
            "Comp2": "2",
            "Pad2": "0",
        },
    )
    return DipTraceDocument.from_bytes(Path("blocks.dip"), ET.tostring(root))


def test_multirouter_proves_minimum_via_budget() -> None:
    document = _top_barrier()
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    net = next(item for item in snapshot.board.nets if item.name == "VCC")
    start, end = net.relationships["endpoints"]

    result = synthesize_routes_with_retry(
        document,
        [
            RouteConnectionConfig(
                net=net.stable_id,
                start_object_id=start,
                end_object_id=end,
                layer="Top",
                start_layer="Top",
                end_layer="Top",
                preferred_layers=["Top", "Bottom"],
                width=0.25,
                clearance=0.2,
                via_style="Default",
                max_vias=2,
                max_detour=6.0,
                time_budget_ms=30_000,
            )
        ],
        ripup_retry=False,
    )

    route = result.routed[0]
    assert route.metrics["minimum_via_count"] == 2
    assert [item["max_vias"] for item in route.metrics["via_budget_attempts"]] == [0, 1, 2]
    assert route.metrics["via_budget_attempts"][-1]["status"] == "routed"


def test_minimum_via_search_does_not_repeat_resource_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.board is not None
    net = next(item for item in snapshot.board.nets if item.name == "VCC")
    start, end = net.relationships["endpoints"]
    attempts: list[int] = []

    def exhaust(_snapshot: object, config: RouteConnectionConfig) -> None:
        attempts.append(config.max_vias)
        raise RoutingError("Local routing node budget exhausted")

    monkeypatch.setattr(routing_module, "synthesize_route", exhaust)
    with pytest.raises(RoutingError, match="node budget exhausted"):
        synthesize_route_min_vias(
            snapshot,
            RouteConnectionConfig(
                net=net.stable_id,
                start_object_id=start,
                end_object_id=end,
                layer="Top",
                preferred_layers=["Top", "Bottom"],
                width=0.25,
                via_style="Default",
                max_vias=2,
            ),
        )

    assert attempts == [0]


def test_trace_width_resolver_promotes_exported_default_to_mandatory_minimum() -> None:
    document = _load()
    root = ET.fromstring(document.raw_bytes)
    routing = root.find("./Board/Settings/Routing")
    prop = root.find("./Board/NetClasses/NetClass/LayProperties/LayProperty")
    assert routing is not None and prop is not None
    routing.set("TraceWidth", "0.1")
    prop.set("Width", "0.1")
    prop.set("MinWidth", "0.3")
    snapshot = build_snapshot(DipTraceDocument.from_bytes(Path("width.dip"), ET.tostring(root)))
    assert snapshot.board is not None
    net = next(item for item in snapshot.board.nets if item.name == "VCC")

    resolution = resolve_trace_width(snapshot, net, ["Top"])

    assert resolution.effective_width_mm == pytest.approx(0.3)
    assert resolution.minimum_width_mm == pytest.approx(0.3)
    assert resolution.promoted_to_minimum is True


def test_board_planner_moves_functional_block_only_when_route_score_improves() -> None:
    document = _block_board()
    overrides = PCBIntentOverrides(
        components=[PCBComponentOverride(selector="J1", mechanical_anchor=True)],
        nets=[
            PCBNetOverride(
                selector="CTRL",
                constraints=PCBElectricalConstraints(
                    trace_width_mm=0.4,
                    max_vias=0,
                ),
            )
        ],
    )

    plan = plan_pcb_routes(
        document,
        overrides=overrides,
        config=PCBRouterConfig(
            routing_layers=["Top"],
            max_vias_per_connection=0,
            max_detour=10.0,
            component_move_penalty_mm=1.0,
        ),
    )

    assert plan.selected_candidate == "block_placement"
    assert plan.changed_component_ids
    assert [item.kind for item in plan.operations] == ["move_components", "add_trace"]
    assert plan.width_resolutions[0].effective_width_mm == pytest.approx(0.4)
    candidates = {item["name"]: item for item in plan.metrics["candidates"]}
    assert (
        candidates["block_placement"]["length_mm"] < candidates["existing_placement"]["length_mm"]
    )

    applied = apply_semantic_operations(document, plan.operations)
    routed = build_snapshot(applied.document)
    assert routed.board is not None
    assert len(routed.board.traces) == 1
