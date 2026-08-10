from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.schematic_placement_repair as repair_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.geometry import Point
from diptrace_mcp.schematic_joint_optimizer import SchematicJointRouteConfig
from diptrace_mcp.schematic_optimizer import generate_schematic_placement_candidates
from diptrace_mcp.schematic_placement_repair import (
    SchematicPlacementRepairConfig,
    _apply_proposal,
    _bounded_delta,
    _edge_proposals,
    _movable_group,
    _repair_groups,
    _RepairGroup,
    _RepairProposal,
    _step_toward,
    repair_schematic_placement_from_route_feedback,
    rescore_schematic_placement_candidate,
)
from diptrace_mcp.schematic_wire_planner import SchematicWirePlannerConfig
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


def _document_with_all_parts_locked() -> DipTraceDocument:
    document = _document_with_embedded_library()
    root = ET.fromstring(document.raw_bytes)
    parts = root.findall("./Schematic/Components/Part")
    assert parts
    for part in parts:
        part.set("Locked", "Y")
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return DipTraceDocument.from_bytes(document.path, raw)


def _diagonal_signal_candidate(document: DipTraceDocument):
    snapshot = build_snapshot(document)
    candidate = generate_schematic_placement_candidates(snapshot)[0].model_copy(deep=True)
    assert snapshot.schematic is not None
    signal_net = next(
        net for net in snapshot.schematic.nets if (net.net_name or net.name) == "SIGNAL"
    )
    pin_by_id = {pin.stable_id: pin for pin in snapshot.schematic.pins}
    owners = sorted(
        {
            pin_by_id[endpoint_id].parent_id
            for endpoint_id in signal_net.relationships.get("endpoints", [])
            if endpoint_id in pin_by_id and pin_by_id[endpoint_id].parent_id is not None
        }
    )
    assert len(owners) == 2
    candidate.placements[owners[0]] = {"x": 200.0, "y": 200.0}
    candidate.placements[owners[1]] = {"x": 280.0, "y": 240.0}
    return rescore_schematic_placement_candidate(snapshot, candidate)


def _repair_config(*, max_candidates: int = 24) -> SchematicPlacementRepairConfig:
    return SchematicPlacementRepairConfig(
        max_candidates=max_candidates,
        translation_step_mm=10.0,
        max_translation_mm=100.0,
        joint_route=SchematicJointRouteConfig(
            include_power_nets=False,
            wire_planner=SchematicWirePlannerConfig(max_bends=0),
        ),
    )


def _permissive_repair_config() -> SchematicPlacementRepairConfig:
    return SchematicPlacementRepairConfig(
        joint_route=SchematicJointRouteConfig(
            include_power_nets=False,
            wire_planner=SchematicWirePlannerConfig(
                max_detour_ratio=100.0,
                max_bends=1_000,
                require_zero_obstacle_hits=False,
                require_zero_overlaps=False,
                require_zero_crossings=False,
                require_zero_self_intersections=False,
                require_orthogonal=False,
            ),
        )
    )


def test_rescore_recomputes_candidate_metrics_without_mutating_inputs() -> None:
    document = _document_with_embedded_library()
    snapshot = build_snapshot(document)
    candidate = generate_schematic_placement_candidates(snapshot)[0]
    draft = candidate.model_copy(deep=True)
    part_id = sorted(draft.placements)[0]
    before_document = snapshot.document.raw_bytes
    assert snapshot.schematic is not None
    before_schematic = snapshot.schematic.model_dump(mode="json")
    before_objects = {
        object_id: record.model_dump(mode="json")
        for object_id, record in snapshot.objects.items()
    }
    before_candidate = draft.model_dump(mode="json")
    draft.placements[part_id] = {
        "x": float(draft.placements[part_id]["x"]) + 100.0,
        "y": float(draft.placements[part_id]["y"]) + 75.0,
    }
    before_rescore = draft.model_dump(mode="json")

    rescored = rescore_schematic_placement_candidate(snapshot, draft)

    assert rescored.candidate_id != candidate.candidate_id
    assert rescored.placements == draft.placements
    assert rescored.total_score == sum(rescored.score_terms.values())
    assert rescored.movement_mm != candidate.movement_mm
    assert snapshot.document.raw_bytes == before_document
    assert snapshot.schematic.model_dump(mode="json") == before_schematic
    assert {
        object_id: record.model_dump(mode="json")
        for object_id, record in snapshot.objects.items()
    } == before_objects
    assert draft.model_dump(mode="json") == before_rescore
    assert before_candidate != before_rescore


def test_rescore_rejects_non_schematic_snapshot() -> None:
    document = _document_with_embedded_library()
    candidate = generate_schematic_placement_candidates(build_snapshot(document))[0]
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", MAX_BYTES)

    with pytest.raises(ValueError, match="requires a schematic"):
        rescore_schematic_placement_candidate(build_snapshot(pcb), candidate)


def test_repair_rejects_non_schematic_document() -> None:
    document = _document_with_embedded_library()
    candidate = generate_schematic_placement_candidates(build_snapshot(document))[0]
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", MAX_BYTES)

    with pytest.raises(ValueError, match="requires a schematic document"):
        repair_schematic_placement_from_route_feedback(pcb, candidate)


def test_feedback_repair_finds_better_axis_aligned_candidate() -> None:
    document = _document_with_embedded_library()
    before_raw = document.raw_bytes
    base = _diagonal_signal_candidate(document)

    result = repair_schematic_placement_from_route_feedback(
        document,
        base,
        config=_repair_config(),
    )

    assert result.base_score.metrics.routed_edge_count == 1
    assert result.base_score.metrics.rejected_route_count == 1
    assert result.feedback_edge_count == 1
    assert result.candidates
    assert result.improved is True
    assert result.selected is not None
    assert result.selected.improves_base is True
    assert tuple(result.selected.route_score.joint_rank_key) < tuple(
        result.base_score.joint_rank_key
    )
    assert result.selected.route_score.metrics.rejected_route_count == 0
    assert result.selected.action.move_kind in {
        "align_start_row",
        "align_end_row",
        "align_start_column",
        "align_end_column",
    }
    assert document.raw_bytes == before_raw


def test_feedback_repair_is_deterministic_and_strictly_bounded() -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)
    config = _repair_config(max_candidates=5)

    first = repair_schematic_placement_from_route_feedback(document, base, config=config)
    second = repair_schematic_placement_from_route_feedback(document, base, config=config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first.candidates) <= 5
    assert len(first.candidates) <= first.generated_candidate_count <= 5


def test_candidate_budget_counts_overlap_rejections(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)
    config = _repair_config(max_candidates=2)
    real_rescore = repair_module.rescore_schematic_placement_candidate
    calls = 0

    def force_repair_overlap(*args, **kwargs):
        nonlocal calls
        rescored = real_rescore(*args, **kwargs)
        calls += 1
        if calls > 1:
            rescored.layout.metrics.part_overlap_count += 1
        return rescored

    monkeypatch.setattr(
        repair_module,
        "rescore_schematic_placement_candidate",
        force_repair_overlap,
    )

    result = repair_schematic_placement_from_route_feedback(document, base, config=config)

    assert result.generated_candidate_count == 2
    assert result.rejected_overlap_candidate_count == 2
    assert result.candidates == []
    assert any("No bounded non-overlapping" in warning for warning in result.warnings)


def test_repair_action_deltas_respect_configured_translation_bound() -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)
    config = _repair_config()
    config.translation_step_mm = 7.5
    config.max_translation_mm = 12.0

    result = repair_schematic_placement_from_route_feedback(document, base, config=config)

    assert result.candidates
    for candidate in result.candidates:
        for raw_delta in candidate.action.group_deltas_mm.values():
            assert math.hypot(float(raw_delta["x"]), float(raw_delta["y"])) <= 12.0 + 1e-9


def test_repair_reports_when_no_feedback_is_required() -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)

    result = repair_schematic_placement_from_route_feedback(
        document,
        base,
        config=_permissive_repair_config(),
    )

    assert result.feedback_edge_count == 0
    assert result.generated_candidate_count == 0
    assert result.candidates == []
    assert result.improved is False
    assert "Base route score requires no placement repair." in result.warnings


def test_repair_reports_when_candidates_do_not_improve_joint_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)
    config = _repair_config(max_candidates=4)
    fixed_score = repair_module.score_schematic_placement_candidate_routes(
        document,
        base,
        config=config.joint_route,
    )
    assert any(edge.plan.placement_feedback.required for edge in fixed_score.edges)

    monkeypatch.setattr(
        repair_module,
        "score_schematic_placement_candidate_routes",
        lambda *args, **kwargs: fixed_score.model_copy(deep=True),
    )

    result = repair_schematic_placement_from_route_feedback(document, base, config=config)

    assert result.candidates
    assert result.selected is None
    assert result.improved is False
    assert all(not candidate.improves_base for candidate in result.candidates)
    assert any("did not improve the joint route rank" in warning for warning in result.warnings)


def test_repair_reports_when_both_endpoint_groups_are_locked() -> None:
    document = _document_with_all_parts_locked()
    base = _diagonal_signal_candidate(document)

    result = repair_schematic_placement_from_route_feedback(
        document,
        base,
        config=_repair_config(),
    )

    assert result.feedback_edge_count == 1
    assert result.generated_candidate_count == 0
    assert result.candidates == []
    assert any("locked or unresolved parts" in warning for warning in result.warnings)


def test_group_and_delta_helpers_cover_fail_closed_boundaries() -> None:
    same_start, same_end, same_block = _repair_groups(
        "A",
        "B",
        part_to_block={"A": "block", "B": "block"},
        block_members={"block": ("A", "B")},
    )
    assert same_block is True
    assert same_start == _RepairGroup("part:A", ("A",))
    assert same_end == _RepairGroup("part:B", ("B",))

    start, end, same_block = _repair_groups(
        "A",
        "B",
        part_to_block={"A": "left"},
        block_members={"left": ("A", "A2")},
    )
    assert same_block is False
    assert start == _RepairGroup("left", ("A", "A2"))
    assert end == _RepairGroup("part:B", ("B",))

    assert _bounded_delta(0.1, 0.1, grid=1.0, maximum=10.0) is None
    assert _bounded_delta(10.0, 10.0, grid=1.0, maximum=12.0) is None
    bounded = _bounded_delta(4.6, 0.0, grid=1.0, maximum=10.0)
    assert bounded is not None and bounded.as_dict() == {"x": 5.0, "y": 0.0}
    toward = _step_toward(Point(0.0, 0.0), Point(0.0, 20.0), 5.0, 1.0, 10.0)
    assert toward is not None and toward.as_dict() == {"x": 0.0, "y": 5.0}

    snapshot = build_snapshot(_document_with_embedded_library())
    assert snapshot.schematic is not None
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    placements = {
        part.stable_id: Point(**part.position)
        for part in snapshot.schematic.parts
        if part.position is not None
    }
    first_part_id = sorted(parts_by_id)[0]
    assert _movable_group(
        _RepairGroup("empty", ()),
        parts_by_id=parts_by_id,
        placements=placements,
    ) is False
    assert _movable_group(
        _RepairGroup("missing", ("missing",)),
        parts_by_id=parts_by_id,
        placements=placements,
    ) is False
    assert _movable_group(
        _RepairGroup("placed", (first_part_id,)),
        parts_by_id=parts_by_id,
        placements=placements,
    ) is True
    placements.pop(first_part_id)
    assert _movable_group(
        _RepairGroup("unplaced", (first_part_id,)),
        parts_by_id=parts_by_id,
        placements=placements,
    ) is False


def test_corridor_proposals_cover_both_axes_and_mobility_sides() -> None:
    config = _repair_config()
    config.translation_step_mm = 5.0
    start_group = _RepairGroup("start", ("A",))
    end_group = _RepairGroup("end", ("B",))

    horizontal = _edge_proposals(
        feedback_kind="open_routing_corridor",
        net_id="N1",
        net_name="SIGNAL",
        start_pin_id="PA",
        end_pin_id="PB",
        start_anchor=Point(0.0, 0.0),
        end_anchor=Point(20.0, 5.0),
        start_group=start_group,
        end_group=end_group,
        start_movable=True,
        end_movable=True,
        config=config,
    )
    horizontal_kinds = {proposal.move_kind for proposal in horizontal}
    assert {
        "offset_start_corridor",
        "offset_end_corridor",
        "split_corridor",
        "align_start_row",
        "align_end_row",
    } <= horizontal_kinds
    split = next(proposal for proposal in horizontal if proposal.move_kind == "split_corridor")
    assert all(math.isclose(delta.x, 0.0) for _group, delta in split.deltas)

    vertical = _edge_proposals(
        feedback_kind="open_routing_corridor",
        net_id="N2",
        net_name="SIGNAL2",
        start_pin_id="PC",
        end_pin_id="PD",
        start_anchor=Point(0.0, 0.0),
        end_anchor=Point(5.0, 20.0),
        start_group=start_group,
        end_group=end_group,
        start_movable=False,
        end_movable=True,
        config=config,
    )
    assert vertical
    assert all(
        proposal.move_kind in {
            "offset_end_corridor",
            "align_end_row",
            "align_end_column",
        }
        for proposal in vertical
    )
    offset = next(
        proposal for proposal in vertical if proposal.move_kind == "offset_end_corridor"
    )
    assert all(math.isclose(delta.y, 0.0) for _group, delta in offset.deltas)

    assert (
        _edge_proposals(
            feedback_kind="none",
            net_id="N3",
            net_name="QUIET",
            start_pin_id="PE",
            end_pin_id="PF",
            start_anchor=Point(0.0, 0.0),
            end_anchor=Point(10.0, 10.0),
            start_group=start_group,
            end_group=end_group,
            start_movable=True,
            end_movable=True,
            config=config,
        )
        == []
    )


def test_apply_proposal_fails_closed_for_missing_or_noop_groups() -> None:
    document = _document_with_embedded_library()
    base = _diagonal_signal_candidate(document)
    part_id = sorted(base.placements)[0]

    missing = _RepairProposal(
        feedback_kind="open_routing_corridor",
        move_kind="offset_start_corridor",
        source_net_id="N",
        source_net_name="SIGNAL",
        source_start_pin_id="P1",
        source_end_pin_id="P2",
        deltas=((_RepairGroup("missing", ("missing",)), Point(1.0, 0.0)),),
    )
    assert _apply_proposal(base, missing, grid=1.0) is None

    empty = missing.__class__(
        feedback_kind="open_routing_corridor",
        move_kind="offset_start_corridor",
        source_net_id="N",
        source_net_name="SIGNAL",
        source_start_pin_id="P1",
        source_end_pin_id="P2",
        deltas=((_RepairGroup("empty", ()), Point(1.0, 0.0)),),
    )
    assert _apply_proposal(base, empty, grid=1.0) is None

    noop = missing.__class__(
        feedback_kind="open_routing_corridor",
        move_kind="offset_start_corridor",
        source_net_id="N",
        source_net_name="SIGNAL",
        source_start_pin_id="P1",
        source_end_pin_id="P2",
        deltas=((_RepairGroup("part", (part_id,)), Point(0.0, 0.0)),),
    )
    assert _apply_proposal(base, noop, grid=1.0) is None
