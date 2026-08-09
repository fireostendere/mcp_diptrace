from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_optimizer import (
    SchematicOptimizerConfig,
    generate_schematic_placement_candidates,
    plan_optimized_schematic_placement,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _load() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)


def test_candidate_generation_is_deterministic_and_ranked() -> None:
    snapshot = build_snapshot(_load())

    first = generate_schematic_placement_candidates(snapshot)
    second = generate_schematic_placement_candidates(snapshot)

    assert len(first) >= 2
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert [item.total_score for item in first] == sorted(item.total_score for item in first)
    assert first[0].estimated_interconnect_length_mm > 0
    assert all(item.placements for item in first)


def test_optimizer_selects_best_candidate_and_replays_operations() -> None:
    document = _load()
    snapshot = build_snapshot(document)

    plan = plan_optimized_schematic_placement(snapshot)

    assert plan.selected.candidate_id == plan.candidates[0].candidate_id
    assert plan.selected.total_score == min(item.total_score for item in plan.candidates)
    assert plan.operations

    applied = apply_semantic_operations(document, plan.operations)
    after = build_snapshot(applied.document)
    for part_id in plan.changed_part_ids:
        expected = plan.selected.placements[part_id]
        actual = after.get_object(part_id).position
        assert actual is not None
        assert actual["x"] == pytest.approx(expected["x"])
        assert actual["y"] == pytest.approx(expected["y"])


def test_optimizer_honors_candidate_limit_and_grid() -> None:
    snapshot = build_snapshot(_load())
    config = SchematicOptimizerConfig(max_candidates=2)

    candidates = generate_schematic_placement_candidates(snapshot, config=config)

    assert 1 <= len(candidates) <= 2
    grid = config.placement.grid_mm
    for candidate in candidates:
        for point in candidate.placements.values():
            assert point["x"] / grid == pytest.approx(round(point["x"] / grid))
            assert point["y"] / grid == pytest.approx(round(point["y"] / grid))


def test_locked_part_is_not_moved() -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.schematic is not None
    locked = snapshot.schematic.parts[0]
    assert locked.position is not None
    locked.locked = True

    plan = plan_optimized_schematic_placement(snapshot)

    assert locked.stable_id not in plan.changed_part_ids
    assert plan.selected.placements[locked.stable_id] == locked.position


def test_optimizer_refuses_existing_wires_until_joint_reroute_exists() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    u1_power = next(
        part
        for part in snapshot.schematic.parts
        if part.refdes == "U1" and part.attributes.get("part_name") == "Power"
    )
    wired = apply_semantic_operations(
        document,
        [
            AddWireOperation(
                net="VCC",
                sheet=0,
                points=[{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 20.0}],
                start={"type": "Pin", "refdes": "R1", "pin": 0},
                end={"type": "Pin", "part_id": u1_power.stable_id, "pin": 0},
            )
        ],
    )

    with pytest.raises(CapabilityUnavailableError, match="already-wired schematic"):
        plan_optimized_schematic_placement(build_snapshot(wired.document))
