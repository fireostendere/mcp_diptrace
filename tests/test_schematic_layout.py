from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.schematic_layout as layout
from diptrace_mcp.adapters import DocumentSnapshot, build_snapshot, stable_id
from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.geometry import Point
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


def _part(
    snapshot: DocumentSnapshot,
    refdes: str,
    part_name: str | None = None,
) -> ObjectRecord:
    schematic = snapshot.schematic
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


def test_layout_analysis_penalizes_objects_outside_centered_sheet_bounds() -> None:
    original = _load()
    root = ET.fromstring(original.raw_bytes)
    sheet = root.find("./Schematic/SheetSettings/Sheets/Sheet")
    assert sheet is not None
    sheet.find("./Id").text = "17"  # type: ignore[union-attr]
    for name, value in (
        ("SheetWidth", "100"),
        ("SheetHeight", "80"),
        ("LeftMargin", "10"),
        ("TopMargin", "10"),
        ("RightMargin", "10"),
        ("BottomMargin", "10"),
    ):
        ET.SubElement(sheet, name).text = value
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    snapshot.schematic.wires = [
        ObjectRecord(
            stable_id=stable_id("wire", "sheet-boundary"),
            kind="wire",
            attributes={
                "sheet": "0",
                "points": [{"x": 0.0, "y": 0.0}, {"x": 41.0, "y": 0.0}],
            },
        )
    ]

    analysis = analyze_schematic_layout(snapshot)

    assert analysis.metrics.sheet_containment_violation_count == 2
    assert analysis.metrics.score_terms["sheet_containment"] == 20_000.0


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


def _synthetic_part(refdes: str, *, name: str = "", value: str = "") -> ObjectRecord:
    return ObjectRecord(
        stable_id=stable_id("part", "role", refdes, name, value),
        kind="part",
        refdes=refdes,
        name=name or None,
        value=value or None,
    )


def _synthetic_net(name: str) -> ObjectRecord:
    return ObjectRecord(
        stable_id=stable_id("net", "role", name or "unnamed"),
        kind="net",
        name=name or None,
    )


def test_role_inference_covers_supported_part_and_net_classes() -> None:
    part_cases = {
        "J1": ("connector", ""),
        "U1": ("power_control", "BUCK REGULATOR"),
        "IC2": ("active", "MCU"),
        "Q1": ("active", "MOSFET"),
        "Y1": ("timing", "CRYSTAL"),
        "D1": ("protection", "TVS"),
        "SW1": ("control", "BUTTON"),
        "R1": ("support", ""),
        "Z1": ("other", "mystery"),
    }
    for refdes, (expected, name) in part_cases.items():
        assert layout._part_role(_synthetic_part(refdes, name=name)).role == expected

    net_cases = {
        "": "unknown",
        "GND": "ground",
        "+3V3": "power",
        "SYS_CLK": "clock",
        "NRST": "reset",
        "USB_D+": "interface",
        "DATA": "signal",
    }
    for name, expected in net_cases.items():
        assert layout._net_role(_synthetic_net(name), []).role == expected

    assert layout._block_role({"connector", "active"}) == "connector"
    assert layout._block_role({"power_control"}) == "power"
    assert layout._block_role({"active"}) == "functional"
    assert layout._block_role(set()) == "generic"


def test_reference_motif_constraint_validation_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="endpoints must be different"):
        ReferenceMotifConstraint(
            first_key="same",
            second_key="same",
            relation="left_of",
        )
    with pytest.raises(ValueError, match="requires max_distance_mm"):
        ReferenceMotifConstraint(
            first_key="a",
            second_key="b",
            relation="near",
        )


def test_motif_relation_error_covers_every_supported_relation() -> None:
    first = Point(10.0, 20.0)
    second = Point(20.0, 30.0)
    cases = [
        ("near", {"max_distance_mm": 5.0}, pytest.approx(9.1421356237)),
        ("left_of", {"tolerance_mm": 0.0}, 0.0),
        ("right_of", {"tolerance_mm": 0.0}, 10.0),
        ("above", {"tolerance_mm": 0.0}, 0.0),
        ("below", {"tolerance_mm": 0.0}, 10.0),
        ("same_row", {"tolerance_mm": 2.0}, 8.0),
        ("same_column", {"tolerance_mm": 2.0}, 8.0),
    ]
    for relation, extra, expected in cases:
        constraint = ReferenceMotifConstraint(
            first_key="a",
            second_key="b",
            relation=relation,
            **extra,
        )
        assert layout._motif_relation_error(first, second, constraint) == expected


def test_wire_metric_helpers_cover_overlap_bends_shared_endpoints_and_same_net() -> None:
    wires = [
        ObjectRecord(
            stable_id=stable_id("wire", "metrics", "a"),
            kind="wire",
            net_name="A",
            attributes={"points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]},
        ),
        ObjectRecord(
            stable_id=stable_id("wire", "metrics", "b"),
            kind="wire",
            net_name="B",
            attributes={"points": [{"x": 5, "y": 0}, {"x": 15, "y": 0}]},
        ),
        ObjectRecord(
            stable_id=stable_id("wire", "metrics", "c"),
            kind="wire",
            net_name="A",
            attributes={"points": [{"x": 0, "y": 10}, {"x": 10, "y": 0}]},
        ),
        ObjectRecord(
            stable_id=stable_id("wire", "metrics", "d"),
            kind="wire",
            net_name="D",
            attributes={"points": [{"x": 10, "y": 10}, {"x": 20, "y": 20}]},
        ),
    ]
    overlap, crossings, diagonals, bends, total, points = layout._wire_metrics(wires)
    assert overlap >= 1
    assert crossings == 2
    assert diagonals == 2
    assert bends == 1
    assert total > 0
    assert points

    assert (
        layout._wire_points(
            ObjectRecord(
                stable_id=stable_id("wire", "metrics", "invalid"),
                kind="wire",
                attributes={"points": "not-a-list"},
            )
        )
        == []
    )


def test_wire_metrics_do_not_compare_different_sheets() -> None:
    wires = [
        ObjectRecord(
            stable_id=stable_id("wire", "sheet-0"),
            kind="wire",
            net_name="A",
            attributes={"sheet": "0", "points": [{"x": 0, "y": 5}, {"x": 10, "y": 5}]},
        ),
        ObjectRecord(
            stable_id=stable_id("wire", "sheet-1"),
            kind="wire",
            net_name="B",
            attributes={"sheet": "1", "points": [{"x": 5, "y": 0}, {"x": 5, "y": 10}]},
        ),
    ]

    overlap, crossings, *_ = layout._wire_metrics(wires)

    assert overlap == 0
    assert crossings == 0


def test_part_overlap_uses_body_bounds_not_pin_envelopes() -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.schematic is not None
    intent = infer_schematic_design_intent(snapshot)
    snapshot.schematic.parts = [
        ObjectRecord(
            stable_id=stable_id("part", "body-a"),
            kind="part",
            refdes="A",
            position={"x": 2.0, "y": 2.0},
            bbox={"min_x": 0.0, "min_y": 0.0, "max_x": 8.0, "max_y": 4.0},
            attributes={
                "sheet": "0",
                "body_bbox": {"min_x": 0.0, "min_y": 0.0, "max_x": 4.0, "max_y": 4.0},
            },
        ),
        ObjectRecord(
            stable_id=stable_id("part", "body-b"),
            kind="part",
            refdes="B",
            position={"x": 8.0, "y": 2.0},
            bbox={"min_x": 2.0, "min_y": 0.0, "max_x": 10.0, "max_y": 4.0},
            attributes={
                "sheet": "0",
                "body_bbox": {"min_x": 6.0, "min_y": 0.0, "max_x": 10.0, "max_y": 4.0},
            },
        ),
    ]
    snapshot.schematic.wires = []

    analysis = analyze_schematic_layout(snapshot, intent=intent)

    assert analysis.metrics.part_overlap_count == 0
