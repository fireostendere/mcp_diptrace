from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import ObjectRecord, StrictModel
from .geometry import Point
from .schematic_joint_optimizer import (
    SchematicJointRouteConfig,
    SchematicPlacementRouteScore,
    score_schematic_placement_candidate_routes,
)
from .schematic_layout import (
    BoundReferenceMotif,
    SchematicDesignIntent,
    analyze_schematic_layout,
    infer_schematic_design_intent,
)
from .schematic_optimizer import (
    SchematicOptimizerConfig,
    SchematicPlacementCandidate,
    _backward_connector_flow,
    _candidate_id,
    _estimate_interconnect,
    _movement,
    _split_blocks_by_sheet,
)
from .schematic_pin_geometry import (
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .schematic_wire_planner import FeedbackKind
from .xml_document import DipTraceDocument

_EPS = 1e-9
RepairMoveKind = Literal[
    "move_start_toward_end",
    "move_end_toward_start",
    "move_pair_toward",
    "align_start_row",
    "align_end_row",
    "align_start_column",
    "align_end_column",
    "offset_start_corridor",
    "offset_end_corridor",
    "split_corridor",
]


class SchematicPlacementRepairConfig(StrictModel):
    max_feedback_edges: int = Field(default=8, ge=1, le=128)
    max_candidates: int = Field(default=24, ge=1, le=256)
    translation_step_mm: float = Field(default=10.0, gt=0.0, le=500.0)
    max_translation_mm: float = Field(default=80.0, gt=0.0, le=2_000.0)
    reject_new_part_overlaps: bool = True
    fixed_part_ids: tuple[str, ...] = Field(default_factory=tuple)
    optimizer: SchematicOptimizerConfig = Field(default_factory=SchematicOptimizerConfig)
    joint_route: SchematicJointRouteConfig = Field(default_factory=SchematicJointRouteConfig)


class SchematicPlacementRepairAction(StrictModel):
    feedback_kind: FeedbackKind
    move_kind: RepairMoveKind
    source_net_id: str
    source_net_name: str = ""
    source_start_pin_id: str
    source_end_pin_id: str
    moved_group_ids: list[str] = Field(default_factory=list)
    moved_part_ids: list[str] = Field(default_factory=list)
    group_deltas_mm: dict[str, dict[str, float]] = Field(default_factory=dict)


class SchematicPlacementRepairCandidate(StrictModel):
    candidate: SchematicPlacementCandidate
    route_score: SchematicPlacementRouteScore
    action: SchematicPlacementRepairAction
    improves_base: bool


class SchematicPlacementRepairResult(StrictModel):
    base_candidate: SchematicPlacementCandidate
    base_score: SchematicPlacementRouteScore
    candidates: list[SchematicPlacementRepairCandidate] = Field(default_factory=list)
    selected: SchematicPlacementRepairCandidate | None = None
    improved: bool
    feedback_edge_count: int = Field(ge=0)
    generated_candidate_count: int = Field(ge=0)
    rejected_overlap_candidate_count: int = Field(ge=0)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _RepairGroup:
    group_id: str
    part_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RepairProposal:
    feedback_kind: FeedbackKind
    move_kind: RepairMoveKind
    source_net_id: str
    source_net_name: str
    source_start_pin_id: str
    source_end_pin_id: str
    deltas: tuple[tuple[_RepairGroup, Point], ...]


def _point_map(candidate: SchematicPlacementCandidate) -> dict[str, Point]:
    return {
        part_id: Point(float(raw["x"]), float(raw["y"]))
        for part_id, raw in candidate.placements.items()
    }


def rescore_schematic_placement_candidate(
    snapshot: DocumentSnapshot,
    candidate: SchematicPlacementCandidate,
    *,
    intent: SchematicDesignIntent | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicOptimizerConfig | None = None,
) -> SchematicPlacementCandidate:
    """Recompute first-stage metrics after hypothetical placement geometry changes."""
    if snapshot.schematic is None:
        raise ValueError("Schematic placement candidate re-scoring requires a schematic")
    config = config or SchematicOptimizerConfig()
    intent = intent or infer_schematic_design_intent(snapshot, motifs=motifs)
    placements = _point_map(candidate)
    slices = _split_blocks_by_sheet(snapshot, intent)
    layout = analyze_schematic_layout(
        snapshot,
        intent=intent,
        placements=placements,
        motifs=motifs,
        weights=config.placement.weights,
    )
    estimated_length, estimated_crossings = _estimate_interconnect(
        intent,
        placements,
        include_power=config.include_power_in_interconnect_estimate,
    )
    backward_flow = _backward_connector_flow(intent, slices, placements)
    movement_mm = _movement(snapshot, placements)
    terms = {
        "layout": layout.metrics.score * config.optimizer_weights.layout_score,
        "estimated_interconnect": estimated_length
        * config.optimizer_weights.estimated_interconnect,
        "estimated_crossing": estimated_crossings
        * config.optimizer_weights.estimated_crossing,
        "backward_connector_flow": backward_flow
        * config.optimizer_weights.backward_connector_flow,
        "movement": movement_mm * config.optimizer_weights.movement,
    }
    return SchematicPlacementCandidate(
        candidate_id=_candidate_id(
            candidate.order_strategy,
            candidate.local_style,
            candidate.row_width_mm,
            placements,
        ),
        order_strategy=candidate.order_strategy,
        local_style=candidate.local_style,
        row_width_mm=candidate.row_width_mm,
        placements={part_id: point.as_dict() for part_id, point in placements.items()},
        estimated_interconnect_length_mm=estimated_length,
        estimated_crossing_count=estimated_crossings,
        backward_connector_flow_count=backward_flow,
        movement_mm=movement_mm,
        score_terms=terms,
        total_score=sum(terms.values()),
        layout=layout,
        unresolved=list(candidate.unresolved),
    )


def _block_maps(
    intent: SchematicDesignIntent,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    part_to_block: dict[str, str] = {}
    block_members: dict[str, tuple[str, ...]] = {}
    for block in intent.blocks:
        members = tuple(sorted(set(block.member_part_ids)))
        block_members[block.block_id] = members
        for part_id in members:
            part_to_block.setdefault(part_id, block.block_id)
    return part_to_block, block_members


def _repair_groups(
    start_part_id: str,
    end_part_id: str,
    *,
    part_to_block: dict[str, str],
    block_members: dict[str, tuple[str, ...]],
) -> tuple[_RepairGroup, _RepairGroup, bool]:
    start_block = part_to_block.get(start_part_id)
    end_block = part_to_block.get(end_part_id)
    same_block = start_block is not None and start_block == end_block
    if same_block:
        return (
            _RepairGroup(f"part:{start_part_id}", (start_part_id,)),
            _RepairGroup(f"part:{end_part_id}", (end_part_id,)),
            True,
        )
    start_members = (
        block_members.get(start_block, (start_part_id,))
        if start_block is not None
        else (start_part_id,)
    )
    end_members = (
        block_members.get(end_block, (end_part_id,))
        if end_block is not None
        else (end_part_id,)
    )
    return (
        _RepairGroup(start_block or f"part:{start_part_id}", start_members),
        _RepairGroup(end_block or f"part:{end_part_id}", end_members),
        False,
    )


def _movable_group(
    group: _RepairGroup,
    *,
    parts_by_id: dict[str, ObjectRecord],
    placements: dict[str, Point],
    fixed_part_ids: frozenset[str] = frozenset(),
) -> bool:
    if not group.part_ids:
        return False
    for part_id in group.part_ids:
        part = parts_by_id.get(part_id)
        if part is None or part.locked or part_id not in placements:
            return False
        if part_id in fixed_part_ids:
            return False
    return True


def _snap_delta(value: float, grid: float) -> float:
    snapped = round(value / grid) * grid
    return 0.0 if math.isclose(snapped, 0.0, abs_tol=_EPS) else snapped


def _bounded_delta(dx: float, dy: float, *, grid: float, maximum: float) -> Point | None:
    delta = Point(_snap_delta(dx, grid), _snap_delta(dy, grid))
    if math.isclose(delta.x, 0.0, abs_tol=_EPS) and math.isclose(
        delta.y, 0.0, abs_tol=_EPS
    ):
        return None
    if math.hypot(delta.x, delta.y) > maximum + _EPS:
        return None
    return delta


def _step_toward(
    start: Point,
    end: Point,
    step: float,
    grid: float,
    maximum: float,
) -> Point | None:
    dx = (
        0.0
        if math.isclose(start.x, end.x, abs_tol=_EPS)
        else math.copysign(step, end.x - start.x)
    )
    dy = (
        0.0
        if math.isclose(start.y, end.y, abs_tol=_EPS)
        else math.copysign(step, end.y - start.y)
    )
    return _bounded_delta(dx, dy, grid=grid, maximum=maximum)


def _append_single(
    proposals: list[_RepairProposal],
    *,
    feedback_kind: FeedbackKind,
    move_kind: RepairMoveKind,
    net_id: str,
    net_name: str,
    start_pin_id: str,
    end_pin_id: str,
    group: _RepairGroup,
    delta: Point | None,
) -> None:
    if delta is None:
        return
    proposals.append(
        _RepairProposal(
            feedback_kind=feedback_kind,
            move_kind=move_kind,
            source_net_id=net_id,
            source_net_name=net_name,
            source_start_pin_id=start_pin_id,
            source_end_pin_id=end_pin_id,
            deltas=((group, delta),),
        )
    )


def _append_pair(
    proposals: list[_RepairProposal],
    *,
    feedback_kind: FeedbackKind,
    move_kind: RepairMoveKind,
    net_id: str,
    net_name: str,
    start_pin_id: str,
    end_pin_id: str,
    start_group: _RepairGroup,
    start_delta: Point | None,
    end_group: _RepairGroup,
    end_delta: Point | None,
) -> None:
    if start_delta is None or end_delta is None:
        return
    proposals.append(
        _RepairProposal(
            feedback_kind=feedback_kind,
            move_kind=move_kind,
            source_net_id=net_id,
            source_net_name=net_name,
            source_start_pin_id=start_pin_id,
            source_end_pin_id=end_pin_id,
            deltas=((start_group, start_delta), (end_group, end_delta)),
        )
    )


def _edge_proposals(
    *,
    feedback_kind: FeedbackKind,
    net_id: str,
    net_name: str,
    start_pin_id: str,
    end_pin_id: str,
    start_anchor: Point,
    end_anchor: Point,
    start_group: _RepairGroup,
    end_group: _RepairGroup,
    start_movable: bool,
    end_movable: bool,
    config: SchematicPlacementRepairConfig,
) -> list[_RepairProposal]:
    proposals: list[_RepairProposal] = []
    grid = config.optimizer.placement.grid_mm
    step = max(grid, _snap_delta(config.translation_step_mm, grid))
    maximum = config.max_translation_mm
    align_start_row = _bounded_delta(
        0.0,
        end_anchor.y - start_anchor.y,
        grid=grid,
        maximum=maximum,
    )
    align_end_row = _bounded_delta(
        0.0,
        start_anchor.y - end_anchor.y,
        grid=grid,
        maximum=maximum,
    )
    align_start_column = _bounded_delta(
        end_anchor.x - start_anchor.x,
        0.0,
        grid=grid,
        maximum=maximum,
    )
    align_end_column = _bounded_delta(
        start_anchor.x - end_anchor.x,
        0.0,
        grid=grid,
        maximum=maximum,
    )
    start_alignment_moves: tuple[tuple[RepairMoveKind, Point | None], ...] = (
        ("align_start_row", align_start_row),
        ("align_start_column", align_start_column),
    )
    end_alignment_moves: tuple[tuple[RepairMoveKind, Point | None], ...] = (
        ("align_end_row", align_end_row),
        ("align_end_column", align_end_column),
    )

    if feedback_kind in {"move_endpoint_blocks_closer", "repack_endpoint_blocks"}:
        if start_movable:
            _append_single(
                proposals,
                feedback_kind=feedback_kind,
                move_kind="move_start_toward_end",
                net_id=net_id,
                net_name=net_name,
                start_pin_id=start_pin_id,
                end_pin_id=end_pin_id,
                group=start_group,
                delta=_step_toward(
                    start_anchor,
                    end_anchor,
                    step,
                    grid,
                    maximum,
                ),
            )
            for move_kind, delta in start_alignment_moves:
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind=move_kind,
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=start_group,
                    delta=delta,
                )
        if end_movable:
            _append_single(
                proposals,
                feedback_kind=feedback_kind,
                move_kind="move_end_toward_start",
                net_id=net_id,
                net_name=net_name,
                start_pin_id=start_pin_id,
                end_pin_id=end_pin_id,
                group=end_group,
                delta=_step_toward(
                    end_anchor,
                    start_anchor,
                    step,
                    grid,
                    maximum,
                ),
            )
            for move_kind, delta in end_alignment_moves:
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind=move_kind,
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=end_group,
                    delta=delta,
                )
        if start_movable and end_movable:
            _append_pair(
                proposals,
                feedback_kind=feedback_kind,
                move_kind="move_pair_toward",
                net_id=net_id,
                net_name=net_name,
                start_pin_id=start_pin_id,
                end_pin_id=end_pin_id,
                start_group=start_group,
                start_delta=_step_toward(
                    start_anchor,
                    end_anchor,
                    step,
                    grid,
                    maximum,
                ),
                end_group=end_group,
                end_delta=_step_toward(
                    end_anchor,
                    start_anchor,
                    step,
                    grid,
                    maximum,
                ),
            )

    if feedback_kind == "open_routing_corridor":
        separation_x = end_anchor.x - start_anchor.x
        separation_y = end_anchor.y - start_anchor.y
        if abs(separation_x) >= abs(separation_y):
            positive = _bounded_delta(0.0, step, grid=grid, maximum=maximum)
            negative = _bounded_delta(0.0, -step, grid=grid, maximum=maximum)
        else:
            positive = _bounded_delta(step, 0.0, grid=grid, maximum=maximum)
            negative = _bounded_delta(-step, 0.0, grid=grid, maximum=maximum)
        if start_movable:
            for delta in (positive, negative):
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind="offset_start_corridor",
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=start_group,
                    delta=delta,
                )
        if end_movable:
            for delta in (positive, negative):
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind="offset_end_corridor",
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=end_group,
                    delta=delta,
                )
        if start_movable and end_movable:
            for start_delta, end_delta in (
                (positive, negative),
                (negative, positive),
            ):
                _append_pair(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind="split_corridor",
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    start_group=start_group,
                    start_delta=start_delta,
                    end_group=end_group,
                    end_delta=end_delta,
                )
        if start_movable:
            for move_kind, delta in start_alignment_moves:
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind=move_kind,
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=start_group,
                    delta=delta,
                )
        if end_movable:
            for move_kind, delta in end_alignment_moves:
                _append_single(
                    proposals,
                    feedback_kind=feedback_kind,
                    move_kind=move_kind,
                    net_id=net_id,
                    net_name=net_name,
                    start_pin_id=start_pin_id,
                    end_pin_id=end_pin_id,
                    group=end_group,
                    delta=delta,
                )
    return proposals


def _apply_proposal(
    base: SchematicPlacementCandidate,
    proposal: _RepairProposal,
    *,
    grid: float,
) -> tuple[dict[str, dict[str, float]], list[str]] | None:
    placements = _point_map(base)
    moved: set[str] = set()
    for group, delta in proposal.deltas:
        for part_id in group.part_ids:
            current = placements.get(part_id)
            if current is None:
                return None
            placements[part_id] = Point(
                round((current.x + delta.x) / grid) * grid,
                round((current.y + delta.y) / grid) * grid,
            )
            moved.add(part_id)
    if not moved:
        return None
    raw = {part_id: point.as_dict() for part_id, point in placements.items()}
    if raw == base.placements:
        return None
    return raw, sorted(moved)


def _placement_identity(
    placements: dict[str, dict[str, float]],
) -> tuple[tuple[str, float, float], ...]:
    return tuple(
        (part_id, round(float(raw["x"]), 9), round(float(raw["y"]), 9))
        for part_id, raw in sorted(placements.items())
    )


def _proposal_action(
    proposal: _RepairProposal,
    moved_part_ids: list[str],
) -> SchematicPlacementRepairAction:
    return SchematicPlacementRepairAction(
        feedback_kind=proposal.feedback_kind,
        move_kind=proposal.move_kind,
        source_net_id=proposal.source_net_id,
        source_net_name=proposal.source_net_name,
        source_start_pin_id=proposal.source_start_pin_id,
        source_end_pin_id=proposal.source_end_pin_id,
        moved_group_ids=sorted(group.group_id for group, _delta in proposal.deltas),
        moved_part_ids=moved_part_ids,
        group_deltas_mm={
            group.group_id: delta.as_dict() for group, delta in proposal.deltas
        },
    )


def repair_schematic_placement_from_route_feedback(
    document: DipTraceDocument,
    base_candidate: SchematicPlacementCandidate,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    intent: SchematicDesignIntent | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicPlacementRepairConfig | None = None,
) -> SchematicPlacementRepairResult:
    """Generate and score one bounded, non-mutating placement-repair iteration."""
    config = config or SchematicPlacementRepairConfig()
    snapshot = build_snapshot(document)
    if snapshot.schematic is None:
        raise ValueError("Schematic placement repair requires a schematic document")
    intent = intent or infer_schematic_design_intent(snapshot, motifs=motifs)
    pin_geometry = pin_geometry or resolve_document_schematic_pin_geometry(document)
    base_candidate = rescore_schematic_placement_candidate(
        snapshot,
        base_candidate,
        intent=intent,
        motifs=motifs,
        config=config.optimizer,
    )
    base_score = score_schematic_placement_candidate_routes(
        document,
        base_candidate,
        pin_geometry=pin_geometry,
        config=config.joint_route,
    )
    feedback_edges = sorted(
        (
            edge
            for edge in base_score.edges
            if edge.plan.placement_feedback.required
        ),
        key=lambda edge: (
            tuple(-value for value in edge.plan.selected.metrics.quality_key),
            edge.net_id,
            edge.start_pin_id,
            edge.end_pin_id,
        ),
    )[: config.max_feedback_edges]

    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    part_to_block, block_members = _block_maps(intent)
    base_points = _point_map(base_candidate)
    fixed_part_ids = frozenset(config.fixed_part_ids)
    proposals: list[_RepairProposal] = []
    warnings: list[str] = []
    locked_feedback = 0
    fixed_feedback = 0

    for edge in feedback_edges:
        operation = edge.plan.selected.operation
        start_part_id = operation.start.part_id
        end_part_id = operation.end.part_id
        if start_part_id is None or end_part_id is None or len(operation.points) < 2:
            warnings.append(
                f"Feedback edge {edge.net_id}:{edge.start_pin_id}->{edge.end_pin_id} "
                "has no stable endpoint part IDs or route anchors."
            )
            continue
        if start_part_id == end_part_id:
            warnings.append(
                f"Feedback edge {edge.net_id}:{edge.start_pin_id}->{edge.end_pin_id} "
                "has both endpoints on one part; translation cannot improve relative "
                "pin geometry."
            )
            continue
        start_group, end_group, _same_block = _repair_groups(
            start_part_id,
            end_part_id,
            part_to_block=part_to_block,
            block_members=block_members,
        )
        start_movable = _movable_group(
            start_group,
            parts_by_id=parts_by_id,
            placements=base_points,
            fixed_part_ids=fixed_part_ids,
        )
        end_movable = _movable_group(
            end_group,
            parts_by_id=parts_by_id,
            placements=base_points,
            fixed_part_ids=fixed_part_ids,
        )
        if not start_movable and not end_movable:
            if fixed_part_ids & (
                set(start_group.part_ids) | set(end_group.part_ids)
            ):
                fixed_feedback += 1
            else:
                locked_feedback += 1
            continue
        proposals.extend(
            _edge_proposals(
                feedback_kind=edge.plan.placement_feedback.kind,
                net_id=edge.net_id,
                net_name=edge.net_name,
                start_pin_id=edge.start_pin_id,
                end_pin_id=edge.end_pin_id,
                start_anchor=Point(operation.points[0].x, operation.points[0].y),
                end_anchor=Point(operation.points[-1].x, operation.points[-1].y),
                start_group=start_group,
                end_group=end_group,
                start_movable=start_movable,
                end_movable=end_movable,
                config=config,
            )
        )

    if locked_feedback:
        warnings.append(
            f"Skipped {locked_feedback} feedback edge(s) because both candidate repair "
            "groups contain locked or unresolved parts."
        )
    if fixed_feedback:
        warnings.append(
            f"Skipped {fixed_feedback} feedback edge(s) because both candidate repair "
            "groups contain operator-fixed parts that must not move."
        )
    if not feedback_edges:
        warnings.append("Base route score requires no placement repair.")

    seen: set[tuple[tuple[str, float, float], ...]] = {
        _placement_identity(base_candidate.placements)
    }
    repair_candidates: list[SchematicPlacementRepairCandidate] = []
    rejected_overlaps = 0
    generated = 0
    grid = config.optimizer.placement.grid_mm
    base_overlap_count = base_candidate.layout.metrics.part_overlap_count

    for proposal in proposals:
        if generated >= config.max_candidates:
            break
        applied = _apply_proposal(base_candidate, proposal, grid=grid)
        if applied is None:
            continue
        placements, moved_part_ids = applied
        identity = _placement_identity(placements)
        if identity in seen:
            continue
        seen.add(identity)
        generated += 1
        draft = base_candidate.model_copy(deep=True)
        draft.placements = placements
        candidate = rescore_schematic_placement_candidate(
            snapshot,
            draft,
            intent=intent,
            motifs=motifs,
            config=config.optimizer,
        )
        if (
            config.reject_new_part_overlaps
            and candidate.layout.metrics.part_overlap_count > base_overlap_count
        ):
            rejected_overlaps += 1
            continue
        route_score = score_schematic_placement_candidate_routes(
            document,
            candidate,
            pin_geometry=pin_geometry,
            config=config.joint_route,
        )
        repair_candidates.append(
            SchematicPlacementRepairCandidate(
                candidate=candidate,
                route_score=route_score,
                action=_proposal_action(proposal, moved_part_ids),
                improves_base=(
                    tuple(route_score.joint_rank_key) < tuple(base_score.joint_rank_key)
                ),
            )
        )

    repair_candidates = sorted(
        repair_candidates,
        key=lambda item: (
            tuple(item.route_score.joint_rank_key),
            item.candidate.candidate_id,
            item.action.move_kind,
        ),
    )
    selected = next((item for item in repair_candidates if item.improves_base), None)
    if feedback_edges and not repair_candidates:
        warnings.append("No bounded non-overlapping placement repair candidate was produced.")
    elif feedback_edges and selected is None:
        warnings.append(
            "Bounded placement repair candidates did not improve the joint route rank."
        )

    return SchematicPlacementRepairResult(
        base_candidate=base_candidate,
        base_score=base_score,
        candidates=repair_candidates,
        selected=selected,
        improved=selected is not None,
        feedback_edge_count=len(feedback_edges),
        generated_candidate_count=generated,
        rejected_overlap_candidate_count=rejected_overlaps,
        assumptions=[
            "Repair proposals are generated only from explicit wire-planner placement "
            "feedback.",
            "Different functional blocks move as rigid groups; feedback within one block "
            "uses endpoint-part local moves so internal packing can improve.",
            "Axis-alignment repairs use the actual routed pin anchors when available.",
            "Locked parts and operator-fixed placements are immutable repair constraints; "
            "a group containing one is never moved as a whole or in part.",
            "Every unique repair geometry counts against max_candidates before placement "
            "and route scoring, including candidates later rejected for overlap.",
            "Every retained repair candidate is re-scored by both placement metrics and "
            "the joint pin-aware route scorer before selection.",
        ],
        warnings=sorted(set(warnings)),
        limitations=[
            "One repair iteration changes geometry for one feedback edge at a time; "
            "multi-edge compound repair belongs in the later bounded improve loop.",
            "Rigid block translation does not yet re-pack all members of a functional block.",
            "The repair search does not rotate symbols while host angle semantics remain "
            "evidence-gated.",
            "This layer is non-mutating and does not yet compose placement moves with "
            "selective wire replacement in a transaction.",
        ],
    )
