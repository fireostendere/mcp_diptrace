from __future__ import annotations

from pathlib import Path

import pytest

import diptrace_mcp.schematic_layout as layout
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.geometry import Point
from diptrace_mcp.schematic_layout import (
    BoundReferenceMotif,
    ReferenceMotif,
    ReferenceMotifConstraint,
    SchematicFunctionalBlock,
    SchematicPlacementConfig,
    analyze_schematic_layout,
    infer_schematic_design_intent,
    plan_schematic_placement,
    score_reference_motif,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot():
    return build_snapshot(DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000))


def _motif() -> ReferenceMotif:
    return ReferenceMotif(
        name="coverage motif",
        source="test",
        source_kind="project",
        constraints=[
            ReferenceMotifConstraint(
                first_key="a",
                second_key="b",
                relation="near",
                max_distance_mm=1.0,
                weight=2.0,
            )
        ],
    )


def test_reference_motif_reports_unbound_missing_and_position_missing() -> None:
    snapshot = _snapshot()
    assert snapshot.schematic is not None
    first, second = snapshot.schematic.parts[:2]

    unbound = score_reference_motif(snapshot, BoundReferenceMotif(motif=_motif(), bindings={}))
    assert unbound["violations"][0]["reason"] == "unbound_motif_key"

    missing = score_reference_motif(
        snapshot,
        BoundReferenceMotif(
            motif=_motif(),
            bindings={"a": first.stable_id, "b": "part_ffffffffffffffff"},
        ),
    )
    assert missing["violations"][0]["reason"] == "bound_part_missing"

    snapshot.schematic.parts = [
        first.model_copy(update={"position": None}),
        *snapshot.schematic.parts[1:],
    ]
    no_position = score_reference_motif(
        snapshot,
        BoundReferenceMotif(
            motif=_motif(),
            bindings={"a": first.stable_id, "b": second.stable_id},
        ),
    )
    assert no_position["violations"][0]["reason"] == "position_missing"


def test_analysis_scores_hypothetical_overlap_and_warns_with_existing_wires() -> None:
    snapshot = _snapshot()
    assert snapshot.schematic is not None
    first, second = snapshot.schematic.parts[:2]
    snapshot.schematic.wires = [
        snapshot.schematic.nets[0].model_copy(
            update={
                "stable_id": "wire_0123456789abcdef",
                "kind": "wire",
                "net_name": "SIGNAL",
                "attributes": {"points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}]},
            }
        )
    ]
    placements = {
        first.stable_id: Point(20.0, 20.0),
        second.stable_id: Point(20.0, 20.0),
    }

    analysis = analyze_schematic_layout(snapshot, placements=placements)

    assert analysis.metrics.part_overlap_count >= 1
    assert analysis.metrics.density_ratio >= 0.0
    assert any("current coordinates" in warning for warning in analysis.warnings)


def test_local_block_layout_covers_anchored_and_generic_wrapping() -> None:
    config = SchematicPlacementConfig(member_gap_x_mm=10.0, member_gap_y_mm=5.0)
    anchored = SchematicFunctionalBlock(
        block_id="anchored",
        role="functional",
        anchor_part_ids=["a"],
        member_part_ids=["a", "s1", "s2", "s3", "s4", "s5"],
        support_part_ids=["s1", "s2", "s3", "s4", "s5"],
        confidence=1.0,
    )
    generic = SchematicFunctionalBlock(
        block_id="generic",
        role="generic",
        member_part_ids=["g1", "g2", "g3", "g4", "g5"],
        confidence=0.5,
    )

    anchored_positions, anchored_width, anchored_height = layout._local_block_layout(
        anchored, config
    )
    generic_positions, generic_width, generic_height = layout._local_block_layout(generic, config)

    assert anchored_positions["s5"].x > anchored_positions["s1"].x
    assert generic_positions["g5"].x > generic_positions["g1"].x
    assert anchored_width > 0 and anchored_height > 0
    assert generic_width > 0 and generic_height > 0


def test_placement_limits_and_unresolved_members_are_reported() -> None:
    snapshot = _snapshot()
    assert snapshot.schematic is not None

    with pytest.raises(CapabilityUnavailableError, match="limited to 1 parts"):
        plan_schematic_placement(snapshot, config=SchematicPlacementConfig(max_parts=1))

    intent = infer_schematic_design_intent(snapshot)
    first_block = intent.blocks[0]
    intent.blocks[0] = first_block.model_copy(
        update={"member_part_ids": [*first_block.member_part_ids, "part_ffffffffffffffff"]}
    )

    plan = plan_schematic_placement(snapshot, intent=intent)

    assert {item["reason"] for item in plan.unresolved} >= {"part_missing"}
