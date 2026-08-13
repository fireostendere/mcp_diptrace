from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp.adapters import build_snapshot, stable_id
from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.geometry import Point
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_wire_planner import plan_schematic_wire_candidate
from diptrace_mcp.services import schematic_wire_quality
from diptrace_mcp.services.schematic_wire_quality import clean_schematic_wire_operation
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _load() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)


def test_cleanup_rejects_reroute_that_reenters_endpoint_symbol(monkeypatch) -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.schematic is not None
    part = next(item for item in snapshot.schematic.parts if item.refdes == "R1")
    obstacle = ObjectRecord(
        stable_id=stable_id("part", "test", "obstacle"),
        kind="part",
        refdes="U2",
        bbox={"min_x": -1.0, "min_y": 19.0, "max_x": 1.0, "max_y": 21.0},
        attributes={"sheet": 0},
    )
    snapshot.schematic.parts = [part, obstacle]
    snapshot.objects[obstacle.stable_id] = obstacle
    monkeypatch.setattr(
        schematic_wire_quality,
        "resolve_document_schematic_pin_geometry",
        lambda _: SimpleNamespace(
            pins=[
                SimpleNamespace(
                    part_id=part.stable_id,
                    pin_index=index,
                    absolute_position={"x": x, "y": y},
                )
                for index, (x, y) in enumerate(
                    ((8.0, 20.0), (12.0, 18.0), (8.0, 22.0), (12.0, 22.0))
                )
            ]
        ),
    )
    monkeypatch.setattr(
        schematic_wire_quality,
        "_route",
        lambda *_: [
            Point(8.0, 20.0),
            Point(12.0, 20.0),
            Point(12.0, 30.0),
            Point(-10.0, 30.0),
            Point(-10.0, 20.0),
        ],
    )
    operation = AddWireOperation(
        net="VCC",
        points=[{"x": 8.0, "y": 20.0}, {"x": -10.0, "y": 20.0}],
        start={"type": "Pin", "refdes": "R1", "pin": 0},
        end={"type": "Free"},
    )

    cleaned = clean_schematic_wire_operation(_load(), snapshot, operation)

    assert cleaned.points == operation.points


def test_planner_is_non_mutating_and_routes_around_component_obstacles() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    before_wire_count = len(document.container.findall(".//Wire"))
    operation = AddWireOperation(
        net="VCC",
        sheet=0,
        points=[{"x": 0.0, "y": 20.0}, {"x": 50.0, "y": 20.0}],
        start={"type": "Free"},
        end={"type": "Free"},
    )

    plan = plan_schematic_wire_candidate(document, snapshot, operation)

    assert plan.original.metrics.obstacle_hits > 0
    assert plan.selected.metrics.obstacle_hits == 0
    assert plan.selected.metrics.diagonals == 0
    assert plan.improved is True
    assert plan.accept_route is True
    assert len(document.container.findall(".//Wire")) == before_wire_count
    assert snapshot.schematic is not None
    assert snapshot.schematic.wires == []


def test_planner_measures_and_removes_crossing_pressure() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    snapshot.schematic.wires = [
        ObjectRecord(
            stable_id=stable_id("wire", "test", "existing"),
            kind="wire",
            net_name="SIGNAL",
            attributes={
                "sheet": 0,
                "points": [
                    {"x": 25.0, "y": 0.0},
                    {"x": 25.0, "y": 40.0},
                ],
            },
        )
    ]
    operation = AddWireOperation(
        net="VCC",
        sheet=0,
        points=[{"x": 0.0, "y": 10.0}, {"x": 50.0, "y": 10.0}],
        start={"type": "Free"},
        end={"type": "Free"},
    )

    plan = plan_schematic_wire_candidate(document, snapshot, operation)

    assert plan.original.metrics.crossings >= 1
    assert plan.selected.metrics.crossings == 0
    assert plan.selected.metrics.quality_key < plan.original.metrics.quality_key


def test_cleaner_preserves_simple_crossing_instead_of_adding_three_bend_hook() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    snapshot.schematic.parts = []
    for name, points in {
        "crossing": [{"x": 20.0, "y": 0.0}, {"x": 20.0, "y": 20.0}],
        "target": [
            {"x": 35.0, "y": 0.0},
            {"x": 40.0, "y": 0.0},
            {"x": 40.0, "y": 20.0},
        ],
    }.items():
        wire = ObjectRecord(
            stable_id=stable_id("wire", "test", name),
            kind="wire",
            net_name=name,
            attributes={"sheet": 0, "points": points},
        )
        snapshot.schematic.wires.append(wire)
        snapshot.objects[wire.stable_id] = wire
    target = snapshot.schematic.wires[-1]
    operation = AddWireOperation(
        net="BRANCH",
        points=[{"x": 0.0, "y": 10.0}, {"x": 40.0, "y": 10.0}],
        start={"type": "Free"},
        end={"type": "Wire", "wire_id": target.stable_id, "point_index": 2},
    )

    cleaned = clean_schematic_wire_operation(document, snapshot, operation)

    assert cleaned.points == operation.points


def test_clean_but_pathological_detour_returns_placement_feedback() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    operation = AddWireOperation(
        net="VCC",
        sheet=0,
        points=[
            {"x": 0.0, "y": 50.0},
            {"x": 0.0, "y": 100.0},
            {"x": 50.0, "y": 100.0},
            {"x": 50.0, "y": 50.0},
        ],
        start={"type": "Free"},
        end={"type": "Free"},
    )

    plan = plan_schematic_wire_candidate(document, snapshot, operation)

    assert plan.improved is False
    assert plan.selected.metrics.detour_ratio == pytest.approx(3.0)
    assert plan.accept_route is False
    assert plan.placement_feedback.required is True
    assert plan.placement_feedback.kind == "move_endpoint_blocks_closer"
    assert any("detour ratio" in reason for reason in plan.placement_feedback.reasons)


def test_feedback_resolves_multipart_pin_endpoints_to_stable_part_ids() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    u1_parts = [part for part in snapshot.schematic.parts if part.refdes == "U1"]
    assert len(u1_parts) == 2
    operation = AddWireOperation(
        net="VCC",
        sheet=0,
        points=[
            {"x": 10.0, "y": 20.0},
            {"x": 10.0, "y": 100.0},
            {"x": 30.0, "y": 100.0},
            {"x": 30.0, "y": 20.0},
        ],
        start={"type": "Pin", "refdes": "R1", "pin": 0},
        end={"type": "Pin", "refdes": "U1", "pin": 0},
    )

    plan = plan_schematic_wire_candidate(document, snapshot, operation)

    assert plan.placement_feedback.required is True
    assert plan.placement_feedback.endpoint_part_ids == sorted(
        [r1.stable_id, *(part.stable_id for part in u1_parts)]
    )
