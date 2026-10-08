from __future__ import annotations

# ruff: noqa: E501
from types import SimpleNamespace

import pytest

from diptrace_mcp import schematic_atomic_reroute as atomic
from diptrace_mcp import schematic_ensemble as ensemble
from diptrace_mcp import schematic_joint_optimizer as joint
from diptrace_mcp import schematic_layout as layout
from diptrace_mcp import schematic_optimizer as optimizer
from diptrace_mcp import schematic_pin_geometry as pins
from diptrace_mcp import schematic_topology as topology
from diptrace_mcp import schematic_wire_planner as planner
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.geometry import Point
from diptrace_mcp.services import schematic_wire_quality as quality


def test_optimizer_graph_orders_and_geometry_helpers_cover_weighted_paths() -> None:
    slices = [
        optimizer._BlockSlice("a", "connector", "a", "0", ("a",), ("a",)),
        optimizer._BlockSlice("b", "functional", "b", "0", ("b",), ("b",)),
        optimizer._BlockSlice("c", "generic", "c", "1", ("c",), ("c",)),
    ]
    intent = SimpleNamespace(
        nets=[
            SimpleNamespace(part_ids=["a", "b"], role="interface"),
            SimpleNamespace(part_ids=["b", "c"], role="power"),
            SimpleNamespace(part_ids=["a", "c"], role="signal"),
        ]
    )
    graph = optimizer._slice_graph(intent, slices)
    assert graph == {("a", "b"): 2.0, ("a", "c"): 1.0, ("b", "c"): 0.2}
    assert optimizer._degree_map(slices, graph)["b"] == 2.2
    assert optimizer._edge_weight(graph, "c", "b") == 0.2
    assert optimizer._edge_weight(graph, "a", "missing") == 0.0
    assert [x.key for x in optimizer._order_slices(slices, graph, "role_then_id")] == ["a", "b", "c"]
    assert [x.key for x in optimizer._order_slices(slices, graph, "connectivity_degree")] == ["a", "b", "c"]
    assert optimizer._proper_intersection(Point(0, 0), Point(2, 2), Point(0, 2), Point(2, 0))
    assert not optimizer._proper_intersection(Point(0, 0), Point(2, 0), Point(2, 0), Point(3, 0))
    assert optimizer._mst_edges(["b", "a", "c"], {"a": Point(0, 0), "b": Point(1, 0), "c": Point(4, 0)}) == [("a", "b"), ("b", "c")]


def test_atomic_junction_helpers_preserve_or_refuse_structure() -> None:
    start, end = Point(0, 0), Point(10, 0)
    points, selected = atomic._points_via_preserved_junction(start, end, [Point(5, 3)], maximum_detour_ratio=2)
    assert selected == Point(5, 3)
    assert [(x.x, x.y) for x in points] == [(0, 0), (5, 0), (5, 3), (10, 3), (10, 0)]
    fallback, selected = atomic._points_via_preserved_junction(start, end, [Point(5, 30)], maximum_detour_ratio=2)
    assert selected is None and len(fallback) == 2
    points, junctions = atomic._points_via_proven_junctions(start, end, [Point(3, 2), Point(7, 2)], maximum_detour_ratio=2)
    assert junctions == [Point(3, 2), Point(7, 2)] and len(points) == 6
    with pytest.raises(CapabilityUnavailableError, match="detour"):
        atomic._points_via_proven_junctions(start, end, [Point(5, 30)], maximum_detour_ratio=2)


def test_topology_primitives_and_errors_are_conservative() -> None:
    assert topology._wire_points("not a list") == []
    assert topology._wire_points([{}, {"x": "bad", "y": 1}]) == []
    assert not topology._connected({})
    assert topology._nearest_node(Point(0, 0), {(1.0, 0.0): Point(1, 0)}, 0.1) is None
    assert topology._nearest_node(Point(0, 0), {(1.0, 0.0): Point(1, 0), (-1.0, 0.0): Point(-1, 0)}, 2) is None
    node_points = {(0.0, 0.0): Point(0, 0), (2.0, 0.0): Point(2, 0)}
    assert topology._nearest_node(Point(.1, 0), node_points, .5) == (0.0, 0.0)
    with pytest.raises(CapabilityUnavailableError, match="requires"):
        topology.build_proven_schematic_topology(SimpleNamespace(schematic=None), [], SimpleNamespace(pins=[]))


def test_wire_quality_primitives_measure_real_route_defects() -> None:
    segment = quality._Segment(Point(0, 0), Point(4, 0))
    vertical = quality._Segment(Point(2, -1), Point(2, 1))
    overlap = quality._Segment(Point(2, 0), Point(6, 0))
    box = quality.BBox(1, -1, 3, 1)
    assert quality._collinear_overlap_length(segment, overlap) == 2
    assert quality._collinear_overlap_length(segment, vertical) == 0
    assert quality._segment_hits_box(vertical, box)
    assert quality._bounded_axis([0, 1, 1, 4], 2, 3) == [0, 1, 4]
    route = [Point(0, 0), Point(2, 0), Point(2, 2), Point(0, 2), Point(0, 0)]
    measured = quality._quality(route, [box], [vertical, overlap], ())
    assert measured.obstacle_hits and measured.overlaps and measured.bends == 3


def test_wire_planner_feedback_reports_hard_and_soft_failures() -> None:
    metrics = planner.SchematicWireMetrics(obstacle_hits=1, overlaps=1, crossings=1, self_intersections=1, diagonals=1, bends=9, length_mm=10, direct_distance_mm=2, detour_ratio=5, quality_key=[1, 1, 1, 1, 1, 9, 10])
    operation = SimpleNamespace(start=SimpleNamespace(type="Free"), end=SimpleNamespace(type="Free"))
    snapshot = SimpleNamespace(schematic=None)
    feedback = planner._feedback(snapshot, operation, metrics, planner.SchematicWirePlannerConfig(max_bends=2, max_detour_ratio=2))
    assert feedback.required and feedback.kind == "open_routing_corridor"
    assert len(feedback.reasons) == 7


def test_joint_small_helpers_cover_virtual_endpoint_resolution() -> None:
    pin = SimpleNamespace(stable_id="p", parent_id="part", xml_id="P:2", attributes={"pinIndex": "2"})
    assert joint._pin_index(pin) == 2
    assert joint._sheet(SimpleNamespace(attributes={"sheet": "3"})) == 3
    assert joint._sheet(SimpleNamespace(attributes={"sheet": "bad"})) is None
    assert joint._resolution_source(None, SimpleNamespace(library_source="embedded_design_cache")) == "embedded_pin"
    assert joint._resolution_source(None, SimpleNamespace(library_source="external_fallback")) == "external_pin"


def test_pin_geometry_identifier_and_validation_failures_are_explicit() -> None:
    assert pins._pin_index(SimpleNamespace(xml_id=None)) is None
    assert pins._pin_index(SimpleNamespace(xml_id="x:no")) is None
    assert pins._pin_index(SimpleNamespace(xml_id="x:-1")) is None
    assert pins._pin_index(SimpleNamespace(xml_id="x:3")) == 3
    assert pins._component_part_index(SimpleNamespace(attributes={"component_part": "bad"})) is None
    assert pins._component_part_index(SimpleNamespace(attributes={"component_part": "-1"})) is None
    assert pins._component_part_index(SimpleNamespace(attributes={"component_part": " 2 "})) == 2
    assert pins._refdes_prefix(None) == ""
    assert pins._refdes_prefix("123") == ""
    assert pins._refdes_prefix("U12") == "u"


def test_layout_wire_metrics_and_overlap_helpers_handle_sheet_and_net_rules() -> None:
    def wire(name: str, net: str, sheet: str, points: list[dict[str, float]]) -> SimpleNamespace:
        return SimpleNamespace(net_name=net, attributes={"sheet": sheet, "points": points}, stable_id=name)

    wires = [
        wire("a", "A", "0", [{"x": 0, "y": 0}, {"x": 4, "y": 0}]),
        wire("b", "B", "0", [{"x": 2, "y": -1}, {"x": 2, "y": 1}]),
        wire("c", "C", "0", [{"x": 1, "y": 0}, {"x": 3, "y": 0}]),
        wire("d", "D", "1", [{"x": 2, "y": -1}, {"x": 2, "y": 1}]),
    ]
    overlaps, crossings, diagonals, bends, length, points = layout._wire_metrics(wires)
    assert (overlaps, crossings, diagonals, bends, round(length), len(points)) == (1, 2, 0, 0, 10, 8)
    assert layout._collinear_overlap_length(layout._Segment(Point(0, 0), Point(2, 2)), layout._Segment(Point(1, 1), Point(3, 3))) == 0


def test_topology_builder_rejects_malformed_disconnected_and_free_leaves() -> None:
    resolution = SimpleNamespace(pins=[])
    schematic = SimpleNamespace(wires=[SimpleNamespace(stable_id="bad", attributes={"points": []})], pins=[])
    with pytest.raises(CapabilityUnavailableError, match="complete"):
        topology.build_proven_schematic_topology(SimpleNamespace(schematic=schematic), ["bad"], resolution)
    disconnected = SimpleNamespace(wires=[
        SimpleNamespace(stable_id="a", attributes={"points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}]}),
        SimpleNamespace(stable_id="b", attributes={"points": [{"x": 1, "y": 0}, {"x": 1, "y": 1}]}),
        SimpleNamespace(stable_id="c", attributes={"points": [{"x": 3, "y": 0}, {"x": 4, "y": 0}]}),
    ], pins=[])
    with pytest.raises(CapabilityUnavailableError, match="disconnected"):
        topology.build_proven_schematic_topology(SimpleNamespace(schematic=disconnected), ["a", "b", "c"], resolution)


def test_wire_quality_axis_trimming_and_anchor_fallbacks_are_deterministic() -> None:
    values = list(range(100))
    bounded = quality._bounded_axis(values, 48.2, 51.8)
    assert len(bounded) == quality._MAX_AXIS_COORDINATES
    assert 48.2 in bounded and 51.8 in bounded
    endpoint = SimpleNamespace(type="Free")
    assert quality._wire_anchor(SimpleNamespace(schematic=None), endpoint, Point(4, 5)) == Point(4, 5)


def test_joint_endpoint_and_virtualization_error_paths_are_explicit() -> None:
    original = SimpleNamespace(stable_id="p", position={"x": 1, "y": 2})
    moved = SimpleNamespace(stable_id="p", position={"x": 5, "y": 7})
    resolved = SimpleNamespace(absolute_position={"x": 2, "y": 4})
    point, source = joint._endpoint_point(None, moved, original, resolved, SimpleNamespace(library_source="provided"))
    assert point == Point(6, 9) and source == "provided_pin"
    assert joint._endpoint_point(None, SimpleNamespace(position=None), original, resolved, SimpleNamespace(library_source="provided"))[0] is None
    bad_pin = SimpleNamespace(stable_id="bad", net_id="N", parent_id="p", xml_id="bad")
    groups, warnings = joint._virtual_endpoints(
        SimpleNamespace(schematic=SimpleNamespace(parts=[original], pins=[])),
        SimpleNamespace(schematic=SimpleNamespace(parts=[moved], pins=[bad_pin])),
        SimpleNamespace(pins=[]),
    )
    assert not groups and warnings == ["Pin bad could not be mapped to a virtual endpoint."]


def test_ensemble_builtin_motifs_reject_empty_and_deduplicate() -> None:
    assert ensemble.infer_builtin_schematic_motifs(SimpleNamespace(schematic=None)) == []
    motif = ensemble._binding_motif(name="x", source="s", first_id="a", second_id="b", relation="near", max_distance_mm=3)
    assert motif.bindings == {"first": "a", "second": "b"}
    intent = SimpleNamespace(
        parts=[
            SimpleNamespace(part_id="a", role="active"), SimpleNamespace(part_id="s", role="passive"),
            SimpleNamespace(part_id="j", role="connector"), SimpleNamespace(part_id="t", role="timing"),
            SimpleNamespace(part_id="p", role="protection"),
        ],
        blocks=[SimpleNamespace(anchor_part_ids=["a"], support_part_ids=["s"], member_part_ids=["a", "j", "t", "p"])],
    )
    motifs = ensemble.infer_builtin_schematic_motifs(SimpleNamespace(schematic=object()), intent)
    assert {item.motif.name.split(":")[1] for item in motifs} == {"near", "left_of"}


def test_quality_text_and_existing_wire_helpers_fail_closed() -> None:
    document = SimpleNamespace(units="mm")
    assert quality._xml_mm(document, None) is None
    assert quality._xml_mm(document, "bad") is None
    assert quality._xml_mm(document, "3") == 3
    snapshot = SimpleNamespace(schematic=SimpleNamespace(wires=[
        SimpleNamespace(attributes={"sheet": "0", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}),
        SimpleNamespace(attributes={"sheet": "bad", "points": []}),
    ]))
    assert len(quality._existing_wire_segments(snapshot, 0)) == 1


def test_quality_part_obstacles_and_pin_envelopes_respect_endpoints() -> None:
    start = SimpleNamespace(type="Pin", part_id="a", refdes=None, pin=1)
    end = SimpleNamespace(type="Free", part_id=None, refdes=None, pin=None)
    operation = SimpleNamespace(sheet=0, start=start, end=end)
    parts = [
        SimpleNamespace(stable_id="a", xml_id="a", refdes="A", attributes={"sheet": "0"}, bbox={"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1}),
        SimpleNamespace(stable_id="b", xml_id="b", refdes="B", attributes={"sheet": "0"}, bbox={"min_x": 2, "min_y": 2, "max_x": 3, "max_y": 3}),
        SimpleNamespace(stable_id="c", xml_id="c", refdes="C", attributes={"sheet": "1"}, bbox=None),
    ]
    snapshot = SimpleNamespace(schematic=SimpleNamespace(parts=parts))
    assert len(quality._part_obstacles(snapshot, operation)) == 1
    envelopes = quality._endpoint_pin_envelopes(snapshot, operation, {("a", 1): Point(0, 0), ("a", 2): Point(1, 1)})
    assert len(envelopes) == 2
