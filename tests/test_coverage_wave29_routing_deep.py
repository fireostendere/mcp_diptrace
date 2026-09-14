from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp import placement
from diptrace_mcp import routing_compiler as compiler
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.errors import GeometryError, RoutingError
from diptrace_mcp.geometry import Point
from diptrace_mcp.operations import (
    AddDifferentialPairRouteOperation,
    AddViaOperation,
    DifferentialPairCenterPoint,
    TracePathPoint,
)
from diptrace_mcp.pcb_autorouter import PCBRouterConfig, _connections, resolve_trace_width
from diptrace_mcp.pcb_routing_policy import compile_pcb_routing_policy
from diptrace_mcp.placement import (
    PlacementConfig,
    PlacementProposal,
    analyze_placement,
    generate_placement_candidates,
    plan_component_placement,
    score_placement_proposal,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _document(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def test_add_via_inserts_and_rejects_final_point() -> None:
    document = _document("pcb.xml")
    trace = build_snapshot(document).board.traces[0]  # type: ignore[union-attr]
    result = apply_semantic_operations(
        document,
        [
            AddViaOperation(
                trace_id=trace.stable_id,
                x=12.5,
                y=10,
                via_style="Default",
                layer_before="Top",
                layer_after="Bottom",
            )
        ],
    )
    assert result.previews[0]["after"]["inserted_point"] is True

    inserted = build_snapshot(result.document).board.traces[0]  # type: ignore[union-attr]
    with pytest.raises(GeometryError, match="final trace point"):
        apply_semantic_operations(
            result.document,
            [
                AddViaOperation(
                    trace_id=inserted.stable_id,
                    x=20,
                    y=10,
                    via_style="Default",
                    layer_before="Bottom",
                    layer_after="Top",
                )
            ],
        )


def test_differential_pair_route_compiles_fresh_segment() -> None:
    source = _document("diff_pair_pcb.xml")
    root = ET.fromstring(source.raw_bytes)
    segments = root.find("./Board/DifferentialPairs/DifferentialPair/Segments")
    assert segments is not None
    segments.clear()
    document = DipTraceDocument.from_bytes(Path("diff.xml"), ET.tostring(root))
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    pair = snapshot.board.differential_pairs[0]
    pads = {pad.net_id: [] for pad in snapshot.board.pads}
    for pad in snapshot.board.pads:
        pads[pad.net_id].append(pad)
    positive, negative = snapshot.board.nets[:2]
    operation = AddDifferentialPairRouteOperation(
        pair=pair.stable_id,
        positive_net=positive.stable_id,
        negative_net=negative.stable_id,
        positive_start_object_id=pads["0"][0].stable_id,
        positive_end_object_id=pads["0"][1].stable_id,
        negative_start_object_id=pads["1"][0].stable_id,
        negative_end_object_id=pads["1"][1].stable_id,
        positive_points=[TracePathPoint(x=1, y=2), TracePathPoint(x=11, y=2)],
        negative_points=[TracePathPoint(x=1, y=2.35), TracePathPoint(x=10.8, y=2.35)],
        center_points=[
            DifferentialPairCenterPoint(
                x=1, y=2.175, layer="Top", positive_dx=0, positive_dy=-0.175,
                negative_dx=0, negative_dy=0.175,
            ),
            DifferentialPairCenterPoint(
                x=10.8, y=2.175, layer="Top", positive_dx=0, positive_dy=-0.175,
                negative_dx=0, negative_dy=0.175,
            ),
        ],
        start_pad_point_id="0",
        end_pad_point_id="1",
        layer="Top",
        width=0.2,
    )
    result = apply_semantic_operations(document, [operation])
    assert len(build_snapshot(result.document).board.differential_pairs[0].segments) == 1  # type: ignore[union-attr]


def test_autorouter_width_and_connection_guards() -> None:
    document = _document("pcb.xml")
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    net = snapshot.board.nets[0]
    with pytest.raises(RoutingError, match="At least one"):
        resolve_trace_width(snapshot, net, [])
    with pytest.raises(RoutingError, match="positive finite"):
        resolve_trace_width(snapshot, net, ["Top"], requested=0)
    width = resolve_trace_width(snapshot, net, ["Top"], requested=0.25)
    assert width.effective_width_mm == pytest.approx(0.25)

    connections, widths, warnings = _connections(
        snapshot, compile_pcb_routing_policy(snapshot), PCBRouterConfig(nets=[net.name or ""])
    )
    assert len(connections) == len(widths) == 1
    assert warnings == []
    with pytest.raises(RoutingError, match="No matching"):
        _connections(
            snapshot, compile_pcb_routing_policy(snapshot), PCBRouterConfig(nets=["missing"])
        )


def test_path_and_width_rare_guards() -> None:
    document = _document("pcb.xml")
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    net = snapshot.board.nets[0]
    cases = (
        ([Point(-1, 1), Point(1, 1)], ["0"], [0.25], [None], "leaves"),
        ([Point(1, 1), Point(2, 1)], ["0"], [0.25], ["0"], "final"),
        (
            [Point(1, 1), Point(2, 1), Point(3, 1)],
            ["0", "1"],
            [0.25, 0.25],
            [None, None],
            "require a via",
        ),
        (
            [Point(1, 1), Point(2, 1), Point(3, 1)],
            ["0", "0"],
            [0.25, 0.25],
            ["0", None],
            "must change",
        ),
        (
            [Point(1, 1), Point(2, 1), Point(3, 1)],
            ["0", "1"],
            [0.25, 0.25],
            ["missing", None],
            "unavailable",
        ),
        ([Point(1, 1), Point(2, 1)], ["0"], [0.01], [None], "below"),
        ([Point(1, 1), Point(1, 1)], ["0"], [0.25], [None], "zero length"),
    )
    for points, layers, widths, styles, message in cases:
        with pytest.raises(GeometryError, match=message):
            compiler._validate_path(document, snapshot, net, points, layers, widths, styles, None)

    root = ET.fromstring(_document("diff_pair_pcb.xml").raw_bytes)
    for prop in root.findall("./Board/NetClasses/NetClass/LayProperties/LayProperty"):
        prop.attrib.pop("Width", None)
        prop.attrib.pop("MinWidth", None)
        prop.attrib.pop("MaxWidth", None)
    stackup = build_snapshot(DipTraceDocument.from_bytes(Path("stackup.xml"), ET.tostring(root)))
    resolution = resolve_trace_width(stackup, stackup.board.nets[0], ["Top"])  # type: ignore[union-attr]
    assert resolution.effective_source == "stackup_default"

    root = ET.fromstring(document.raw_bytes)
    prop = root.find("./Board/NetClasses/NetClass/LayProperties/LayProperty")
    assert prop is not None
    prop.set("MinWidth", "3")
    prop.set("MaxWidth", "2")
    impossible = build_snapshot(DipTraceDocument.from_bytes(Path("rules.xml"), ET.tostring(root)))
    with pytest.raises(RoutingError, match="no legal intersection"):
        resolve_trace_width(impossible, impossible.board.nets[0], ["Top"])  # type: ignore[union-attr]
    with pytest.raises(RoutingError, match="exceeds"):
        resolve_trace_width(snapshot, net, ["Top"], requested=3)

    trace = snapshot.board.traces[0]
    for x, y, message, allow_via_in_pad in (
        (10, 10, "first ignored", True),
        (15, 15, "not on", False),
    ):
        with pytest.raises(GeometryError, match=message):
            apply_semantic_operations(
                document,
                [
                    AddViaOperation(
                        trace_id=trace.stable_id,
                        x=x,
                        y=y,
                        via_style="Default",
                        allow_via_in_pad=allow_via_in_pad,
                    )
                ],
            )

    snapshot.board.keepouts = [
        ObjectRecord(
            stable_id="keepout_0000000000000000",
            kind="keepout",
            bbox={"min_x": 1.5, "min_y": 0.5, "max_x": 2.5, "max_y": 1.5},
        )
    ]
    with pytest.raises(GeometryError, match="keepout"):
        compiler._validate_path(
            document,
            snapshot,
            net,
            [Point(1, 1), Point(3, 1)],
            ["0"],
            [0.25],
            [None],
            None,
        )


def test_placement_no_candidate_and_time_budget_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = build_snapshot(_document("pcb.xml"))
    component = snapshot.board.components[0]  # type: ignore[union-attr]
    blocked = plan_component_placement(
        snapshot,
        PlacementConfig(
            selector={"ids": [component.stable_id]},
            region={"min_x": 100, "min_y": 100, "max_x": 101, "max_y": 101},
        ),
    )
    assert blocked.unresolved[0]["reason"] == "no_legal_candidate"

    ticks = iter((0.0, 1.0, 1.0))
    monkeypatch.setattr(placement.time, "monotonic", lambda: next(ticks))
    expired = plan_component_placement(
        snapshot,
        PlacementConfig(selector={"ids": [component.stable_id]}, time_budget_ms=100),
    )
    assert expired.metrics["time_budget_exhausted"] is True


def test_placement_scope_proposal_and_candidate_guards() -> None:
    snapshot = build_snapshot(_document("pcb.xml"))
    component = snapshot.board.components[0]  # type: ignore[union-attr]
    with pytest.raises(Exception, match="explicit component selector"):
        plan_component_placement(snapshot, PlacementConfig())
    with pytest.raises(Exception, match="Placement object was not found"):
        score_placement_proposal(
            snapshot, [PlacementProposal(object_id="missing", x=0, y=0)], PlacementConfig()
        )

    component.locked = True
    with pytest.raises(Exception, match="locked component"):
        score_placement_proposal(
            snapshot,
            [PlacementProposal(object_id=component.stable_id, x=component.position["x"] + 1, y=0)],
            PlacementConfig(),
        )
    component.locked = False
    candidates = generate_placement_candidates(
        snapshot,
        PlacementConfig(
            selector={"ids": [component.stable_id]},
            allowed_sides=["Bottom"],
            allowed_rotations=[90],
            max_candidates_per_component=1,
        ),
    )
    assert candidates[0]["candidates"][0]["side"] == "Bottom"
    moved = plan_component_placement(
        snapshot,
        PlacementConfig(
            selector={"ids": [component.stable_id]},
            allowed_sides=["Bottom"],
            allowed_rotations=[90],
            board_edge_clearance=0,
        ),
    )
    assert moved.changed_ids == [component.stable_id]


def test_autorouter_connection_skips_and_placement_keepout() -> None:
    snapshot = build_snapshot(_document("pcb.xml"))
    assert snapshot.board is not None
    ratline = snapshot.board.ratlines[0]
    other_net = next(pad for pad in snapshot.board.pads if pad.net_id != "0")
    bad_net = {
        **ratline,
        "endpoints": [ratline["endpoints"][0], {"pad_id": other_net.stable_id}],
    }
    snapshot.board.ratlines = [{"endpoints": [{}]}, bad_net, ratline, ratline]
    connections, _, _ = _connections(
        snapshot, compile_pcb_routing_policy(snapshot), PCBRouterConfig()
    )
    assert len(connections) == 1

    component = snapshot.board.components[0]
    snapshot.board.keepouts = [
        ObjectRecord(
            stable_id="keepout_1111111111111111",
            kind="keepout",
            bbox=component.bbox,
        )
    ]
    report = analyze_placement(snapshot)
    assert any(item["reason"].startswith("keepout:") for item in report["violations"])


def test_placement_analysis_scores_static_guards() -> None:
    snapshot = build_snapshot(_document("pcb.xml"))
    assert snapshot.board is not None
    first, second = snapshot.board.components[:2]
    report = analyze_placement(snapshot)
    assert report["component_count"] == 2
    score, violations = score_placement_proposal(
        snapshot,
        [
            PlacementProposal(
                object_id=first.stable_id, x=second.position["x"], y=second.position["y"]
            )  # type: ignore[index]
        ],
        PlacementConfig(region={"min_x": 0, "min_y": 0, "max_x": 5, "max_y": 5}),
    )
    assert score["total"] > 0
    assert {item["reason"] for item in violations} & {
        "component_spacing",
        "containment:requested_region",
    }
