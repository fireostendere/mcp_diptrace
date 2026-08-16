from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.geometry import Point
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_atomic_reroute import (
    _intentional_junctions,
    _points_via_preserved_junction,
    plan_atomic_schematic_placement_reroute,
)
from diptrace_mcp.schematic_joint_optimizer import (
    SchematicJointRouteConfig,
    score_schematic_placement_candidate_routes,
)
from diptrace_mcp.schematic_optimizer import generate_schematic_placement_candidates
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _document_with_embedded_library() -> DipTraceDocument:
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)
    library = DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)
    root = ET.fromstring(schematic.raw_bytes)
    existing = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert existing is not None
    index = list(root).index(existing)
    root.remove(existing)
    root.insert(index, ET.fromstring(library.raw_bytes))
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return DipTraceDocument.from_bytes(schematic.path, raw)


def _part_id(document: DipTraceDocument, xml_id: str) -> str:
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    return next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == xml_id)


def _wired_document() -> DipTraceDocument:
    document = _document_with_embedded_library()
    operations = [
        AddWireOperation(
            net="VCC",
            sheet=0,
            points=[
                {"x": 10.0, "y": 20.0},
                {"x": 20.0, "y": 20.0},
                {"x": 30.0, "y": 20.0},
            ],
            start={"type": "Pin", "refdes": "R1", "pin": 0},
            end={"type": "Pin", "part_id": _part_id(document, "1"), "pin": 0},
        ),
        AddWireOperation(
            net="SIGNAL",
            sheet=0,
            points=[
                {"x": 10.0, "y": 20.0},
                {"x": 25.0, "y": 20.0},
                {"x": 40.0, "y": 20.0},
            ],
            start={"type": "Pin", "refdes": "R1", "pin": 1},
            end={"type": "Pin", "part_id": _part_id(document, "2"), "pin": 0},
        ),
    ]
    return apply_semantic_operations(document, operations).document


def _candidate_for_move(
    document: DipTraceDocument,
    *,
    xml_id: str,
    dx: float = 0.0,
    dy: float = 0.0,
):
    source = _document_with_embedded_library()
    source_snapshot = build_snapshot(source)
    candidates = generate_schematic_placement_candidates(source_snapshot)
    assert candidates
    candidate = candidates[0].model_copy(deep=True)
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    for part in snapshot.schematic.parts:
        assert part.position is not None
        candidate.placements[part.stable_id] = dict(part.position)
    target = next(part for part in snapshot.schematic.parts if part.xml_id == xml_id)
    assert target.position is not None
    candidate.placements[target.stable_id] = {
        "x": target.position["x"] + dx,
        "y": target.position["y"] + dy,
    }
    return candidate, target.stable_id


def test_atomic_reroute_replaces_only_nets_touched_by_moved_part() -> None:
    document = _wired_document()
    before = build_snapshot(document)
    assert before.schematic is not None
    signal_wire = next(wire for wire in before.schematic.wires if wire.net_name == "SIGNAL")
    candidate, moved_id = _candidate_for_move(document, xml_id="1", dx=8.0)

    plan = plan_atomic_schematic_placement_reroute(document, candidate)

    assert plan.moved_part_ids == [moved_id]
    assert [item.net_name for item in plan.affected_net_groups] == ["VCC"]
    assert len(plan.deleted_wire_ids) == 1
    assert plan.added_wire_count == 1
    assert plan.affected_net_groups[0].quality_feedback
    assert any("readability feedback" in item for item in plan.warnings)
    assert [operation.kind for operation in plan.operations] == [
        "delete_wire",
        "move_components",
        "add_wire",
    ]

    applied = apply_semantic_operations(document, plan.operations).document
    after = build_snapshot(applied)
    assert after.schematic is not None
    moved = next(part for part in after.schematic.parts if part.stable_id == moved_id)
    assert moved.position is not None
    assert moved.position["x"] == pytest.approx(38.0)
    assert {wire.net_name for wire in after.schematic.wires} == {"VCC", "SIGNAL"}
    after_signal = next(wire for wire in after.schematic.wires if wire.net_name == "SIGNAL")
    assert after_signal.stable_id == signal_wire.stable_id


def test_intentional_degree_three_junction_is_reused_with_bounded_detour() -> None:
    snapshot = SimpleNamespace(
        schematic=SimpleNamespace(
            wires=[
                SimpleNamespace(
                    stable_id="horizontal",
                    attributes={
                        "points": [
                            {"x": 0.0, "y": 0.0},
                            {"x": 10.0, "y": 0.0},
                            {"x": 20.0, "y": 0.0},
                        ]
                    },
                ),
                SimpleNamespace(
                    stable_id="branch",
                    attributes={
                        "points": [
                            {"x": 10.0, "y": 0.0},
                            {"x": 10.0, "y": 10.0},
                        ]
                    },
                ),
            ]
        )
    )

    junctions = _intentional_junctions(snapshot, ["horizontal", "branch"])
    points, used = _points_via_preserved_junction(
        Point(0.0, 0.0),
        Point(20.0, 0.0),
        junctions,
        maximum_detour_ratio=2.5,
    )

    assert junctions == [Point(10.0, 0.0)]
    assert used == Point(10.0, 0.0)
    assert any(item.x == 10.0 and item.y == 0.0 for item in points)


def test_atomic_reroute_rebuilds_all_explicit_wire_groups_for_multi_net_part() -> None:
    document = _wired_document()
    candidate, moved_id = _candidate_for_move(document, xml_id="0", dy=10.0)

    plan = plan_atomic_schematic_placement_reroute(document, candidate)

    assert plan.moved_part_ids == [moved_id]
    assert [item.net_name for item in plan.affected_net_groups] == ["VCC", "SIGNAL"]
    assert len(plan.deleted_wire_ids) == 2
    assert plan.added_wire_count == 2
    assert any(item.quality_feedback for item in plan.affected_net_groups)
    assert [item.kind for item in plan.operations].count("delete_wire") == 2
    assert [item.kind for item in plan.operations].count("move_components") == 1
    assert [item.kind for item in plan.operations].count("add_wire") == 2

    result = apply_semantic_operations(document, plan.operations).document
    snapshot = build_snapshot(result)
    assert snapshot.schematic is not None
    assert len(snapshot.schematic.wires) == 2
    assert {wire.net_name for wire in snapshot.schematic.wires} == {"VCC", "SIGNAL"}


def test_atomic_reroute_is_non_mutating_until_semantic_batch_is_applied() -> None:
    document = _wired_document()
    before = document.raw_bytes
    candidate, _moved_id = _candidate_for_move(document, xml_id="1", dx=5.0)

    plan_atomic_schematic_placement_reroute(document, candidate)

    assert document.raw_bytes == before


def test_atomic_reroute_fails_closed_for_unresolved_affected_endpoints() -> None:
    document = _wired_document()
    root = ET.fromstring(document.raw_bytes)
    part = root.find("./Schematic/Components/Part[@Id='0']")
    assert part is not None
    first_pin = part.find("./Pins/Pin")
    assert first_pin is not None
    first_pin.set("NetId", "-1")
    vcc_pins = root.find("./Schematic/Nets/Net[@Id='0']/Pins")
    assert vcc_pins is not None
    item = vcc_pins.find("./Item[@Part='0'][@Pin='0']")
    assert item is not None
    vcc_pins.remove(item)
    unresolved = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    candidate, _moved_id = _candidate_for_move(unresolved, xml_id="1", dx=5.0)

    with pytest.raises(CapabilityUnavailableError, match="at least two resolvable endpoints"):
        plan_atomic_schematic_placement_reroute(unresolved, candidate)


def test_atomic_reroute_fails_closed_for_locked_moved_part() -> None:
    document = _wired_document()
    root = ET.fromstring(document.raw_bytes)
    part = root.find("./Schematic/Components/Part[@Id='1']")
    assert part is not None
    part.set("Locked", "Y")
    locked = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    candidate, _moved_id = _candidate_for_move(locked, xml_id="1", dx=5.0)

    with pytest.raises(CapabilityUnavailableError, match="locked part"):
        plan_atomic_schematic_placement_reroute(locked, candidate)


def test_scorer_and_reroute_model_same_affected_wire_geometry() -> None:
    """The joint route scorer must score the same world the reroute will apply:
    affected wires removed, unaffected nets untouched and kept as obstacles."""
    document = _wired_document()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None

    candidate, moved_id = _candidate_for_move(document, xml_id="2", dy=20.0)
    plan = plan_atomic_schematic_placement_reroute(document, candidate)

    signal_wires = sorted(
        wire.stable_id for wire in snapshot.schematic.wires if wire.net_name == "SIGNAL"
    )
    vcc_wires = sorted(
        wire.stable_id for wire in snapshot.schematic.wires if wire.net_name == "VCC"
    )
    # The moved part touches only SIGNAL: only SIGNAL wires are replaced.
    assert plan.moved_part_ids == [moved_id]
    assert plan.deleted_wire_ids == signal_wires
    assert not set(vcc_wires).intersection(plan.deleted_wire_ids)

    score = score_schematic_placement_candidate_routes(
        document,
        candidate,
        config=SchematicJointRouteConfig(allow_existing_wires=True),
    )
    signal_net_id = next(
        wire.net_id for wire in snapshot.schematic.wires if wire.net_name == "SIGNAL"
    )
    vcc_net_id = next(wire.net_id for wire in snapshot.schematic.wires if wire.net_name == "VCC")
    edge_groups = {(edge.net_id, edge.sheet) for edge in score.edges}
    assert (signal_net_id, 0) in edge_groups
    assert (vcc_net_id, 0) not in edge_groups

    # The wire planner scored the SIGNAL replacement against the preserved VCC
    # geometry: unaffected wires remain as obstacles in the scored snapshot.
    assert score.edges


def test_scorer_produces_no_phantom_feedback_on_current_wired_layout() -> None:
    document = _wired_document()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None

    current_layout, _moved = _candidate_for_move(document, xml_id="2")
    score = score_schematic_placement_candidate_routes(
        document,
        current_layout,
        config=SchematicJointRouteConfig(allow_existing_wires=True),
    )

    # No moved parts -> no affected groups -> no hypothetical replacement
    # routes scored against the schematic's own preserved wires.
    assert score.edges == []
    assert score.metrics.rejected_route_count == 0
