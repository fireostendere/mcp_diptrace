from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot, stable_id
from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_layout import (
    BoundReferenceMotif,
    ReferenceMotif,
    ReferenceMotifConstraint,
    analyze_schematic_layout,
    infer_schematic_design_intent,
    plan_schematic_placement,
    score_reference_motif,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _load() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)


def _part(snapshot: object, refdes: str, part_name: str | None = None) -> ObjectRecord:
    schematic = getattr(snapshot, "schematic")
    assert schematic is not None
    matches = [
        item
        for item in schematic.parts
        if item.refdes == refdes
        and (part_name is None or item.attributes.get("part_name") == part_name)
    ]
    assert len(matches) == 1
    return matches[0]


def test_intent_groups_support_part_with_multipart_anchor() -> None:
    snapshot = build_snapshot(_load())
    intent = infer_schematic_design_intent(snapshot)

    r1 = _part(snapshot, "R1")
    u1_power = _part(snapshot, "U1", "Power")
    u1_gpio = _part(snapshot, "U1", "GPIO")
    block = next(item for item in intent.blocks if u1_power.stable_id in item.anchor_part_ids)

    assert set(block.anchor_part_ids) == {u1_power.stable_id, u1_gpio.stable_id}
    assert r1.stable_id in block.support_part_ids
    assert {item.name: item.role for item in intent.nets} == {
        "VCC": "power",
        "SIGNAL": "signal",
    }


def test_layout_analysis_exposes_decomposed_baseline_metrics() -> None:
    analysis = analyze_schematic_layout(build_snapshot(_load()))

    assert analysis.metrics.part_count == 3
    assert analysis.metrics.block_count == 1
    assert analysis.metrics.wire_count == 0
    assert analysis.metrics.part_overlap_count == 0
    assert analysis.metrics.wire_crossing_count == 0
    assert analysis.metrics.occupied_area_mm2 > 0
    assert analysis.metrics.score == pytest.approx(sum(analysis.metrics.score_terms.values()))


def test_first_pass_placement_is_deterministic_and_replayable() -> None:
    document = _load()
    snapshot = build_snapshot(document)

    first = plan_schematic_placement(snapshot)
    second = plan_schematic_placement(snapshot)

    assert [item.model_dump(mode="json") for item in first.operations] == [
        item.model_dump(mode="json") for item in second.operations
    ]
    assert first.after.metrics.mean_block_span_mm <= first.before.metrics.mean_block_span_mm
    assert first.operations

    applied = apply_semantic_operations(document, first.operations)
    after_snapshot = build_snapshot(applied.document)
    for part_id in first.changed_part_ids:
        expected = first.placements[part_id]
        actual = after_snapshot.get_object(part_id).position
        assert actual is not None
        assert actual["x"] == pytest.approx(expected.x)
        assert actual["y"] == pytest.approx(expected.y)


def test_first_pass_placement_refuses_existing_wires() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    u1_power = _part(snapshot, "U1", "Power")
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

    with pytest.raises(CapabilityUnavailableError, match="existing wires"):
        plan_schematic_placement(build_snapshot(wired.document))


def test_reference_motif_scores_relative_relationships() -> None:
    snapshot = build_snapshot(_load())
    r1 = _part(snapshot, "R1")
    u1_power = _part(snapshot, "U1", "Power")

    good = BoundReferenceMotif(
        motif=ReferenceMotif(
            name="support-left-of-anchor",
            source="test fixture",
            source_kind="project",
            constraints=[
                ReferenceMotifConstraint(
                    first_key="support",
                    second_key="anchor",
                    relation="left_of",
                    tolerance_mm=0.0,
                )
            ],
        ),
        bindings={"support": r1.stable_id, "anchor": u1_power.stable_id},
    )
    bad = BoundReferenceMotif(
        motif=ReferenceMotif(
            name="support-right-of-anchor",
            source="test fixture",
            source_kind="project",
            constraints=[
                ReferenceMotifConstraint(
                    first_key="support",
                    second_key="anchor",
                    relation="right_of",
                    tolerance_mm=0.0,
                )
            ],
        ),
        bindings={"support": r1.stable_id, "anchor": u1_power.stable_id},
    )

    assert score_reference_motif(snapshot, good)["violation_count"] == 0
    assert score_reference_motif(snapshot, bad)["violation_count"] == 1


def test_layout_analysis_counts_crossing_between_different_nets() -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.schematic is not None
    snapshot.schematic.wires = [
        ObjectRecord(
            stable_id=stable_id("wire", "test", "one"),
            kind="wire",
            net_name="A",
            attributes={
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 10.0},
                ]
            },
        ),
        ObjectRecord(
            stable_id=stable_id("wire", "test", "two"),
            kind="wire",
            net_name="B",
            attributes={
                "points": [
                    {"x": 0.0, "y": 10.0},
                    {"x": 10.0, "y": 0.0},
                ]
            },
        ),
    ]

    analysis = analyze_schematic_layout(snapshot)

    assert analysis.metrics.wire_crossing_count == 1
    assert analysis.metrics.diagonal_segment_count == 2
