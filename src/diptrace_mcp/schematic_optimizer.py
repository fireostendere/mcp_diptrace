from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, field_validator

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import Point, distance
from .operations import MoveComponentsOperation, SemanticOperation
from .schematic_layout import (
    BlockRole,
    BoundReferenceMotif,
    SchematicDesignIntent,
    SchematicLayoutAnalysis,
    SchematicPlacementConfig,
    analyze_schematic_layout,
    infer_schematic_design_intent,
)

_EPS = 1e-9
LocalStyle = Literal["support_right", "support_below", "support_balanced"]
OrderStrategy = Literal["role_then_id", "connector_flow", "connectivity_degree"]


def _default_local_styles() -> list[LocalStyle]:
    return ["support_right", "support_below", "support_balanced"]


def _default_order_strategies() -> list[OrderStrategy]:
    return ["role_then_id", "connector_flow", "connectivity_degree"]


class SchematicOptimizerWeights(StrictModel):
    layout_score: float = Field(default=1.0, ge=0.0)
    estimated_interconnect: float = Field(default=0.5, ge=0.0)
    estimated_crossing: float = Field(default=750.0, ge=0.0)
    backward_connector_flow: float = Field(default=200.0, ge=0.0)
    movement: float = Field(default=0.02, ge=0.0)


class SchematicOptimizerConfig(StrictModel):
    placement: SchematicPlacementConfig = Field(default_factory=SchematicPlacementConfig)
    optimizer_weights: SchematicOptimizerWeights = Field(
        default_factory=SchematicOptimizerWeights
    )
    max_candidates: int = Field(default=12, ge=1, le=64)
    row_width_scales: list[float] = Field(
        default_factory=lambda: [0.75, 1.0, 1.25], min_length=1, max_length=8
    )
    local_styles: list[LocalStyle] = Field(
        default_factory=_default_local_styles,
        min_length=1,
        max_length=3,
    )
    order_strategies: list[OrderStrategy] = Field(
        default_factory=_default_order_strategies,
        min_length=1,
        max_length=3,
    )
    include_power_in_interconnect_estimate: bool = True

    @field_validator("row_width_scales")
    @classmethod
    def validate_row_width_scales(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) or value <= 0.0 or value > 4.0 for value in values):
            raise ValueError("row_width_scales must be finite and in (0, 4]")
        return sorted(set(values))


class SchematicPlacementCandidate(StrictModel):
    candidate_id: str
    order_strategy: OrderStrategy
    local_style: LocalStyle
    row_width_mm: float = Field(gt=0.0)
    placements: dict[str, dict[str, float]] = Field(default_factory=dict)
    estimated_interconnect_length_mm: float = Field(ge=0.0)
    estimated_crossing_count: int = Field(ge=0)
    backward_connector_flow_count: int = Field(ge=0)
    movement_mm: float = Field(ge=0.0)
    score_terms: dict[str, float] = Field(default_factory=dict)
    total_score: float = Field(ge=0.0)
    layout: SchematicLayoutAnalysis
    unresolved: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SchematicOptimizationPlan:
    selected: SchematicPlacementCandidate
    candidates: list[SchematicPlacementCandidate]
    operations: list[SemanticOperation]
    changed_part_ids: list[str]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True, slots=True)
class _BlockSlice:
    key: str
    role: BlockRole
    block_id: str
    sheet: str
    anchor_part_ids: tuple[str, ...]
    member_part_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _EstimatedSegment:
    net_id: str
    start: Point
    end: Point


def _require_unwired_schematic(
    snapshot: DocumentSnapshot,
    config: SchematicOptimizerConfig,
) -> None:
    if snapshot.schematic is None:
        raise CapabilityUnavailableError("Schematic optimization requires a schematic document")
    if len(snapshot.schematic.parts) > config.placement.max_parts:
        raise CapabilityUnavailableError(
            f"Schematic optimization is limited to {config.placement.max_parts} parts"
        )
    if snapshot.schematic.wires and not config.placement.allow_existing_wires:
        raise CapabilityUnavailableError(
            "Joint optimization of an already-wired schematic is not enabled yet"
        )


def _part_sheet(part: ObjectRecord) -> str:
    return str(part.attributes.get("sheet", "0"))


def _split_blocks_by_sheet(
    snapshot: DocumentSnapshot,
    intent: SchematicDesignIntent,
) -> list[_BlockSlice]:
    assert snapshot.schematic is not None
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    slices: list[_BlockSlice] = []
    for block in intent.blocks:
        by_sheet: dict[str, list[str]] = defaultdict(list)
        for part_id in block.member_part_ids:
            part = parts_by_id.get(part_id)
            if part is not None:
                by_sheet[_part_sheet(part)].append(part_id)
        for sheet, members in sorted(by_sheet.items()):
            member_set = set(members)
            anchors = tuple(
                sorted(part_id for part_id in block.anchor_part_ids if part_id in member_set)
            )
            key = f"{block.block_id}@{sheet}"
            slices.append(
                _BlockSlice(
                    key=key,
                    role=block.role,
                    block_id=block.block_id,
                    sheet=sheet,
                    anchor_part_ids=anchors,
                    member_part_ids=tuple(sorted(members)),
                )
            )
    return slices


def _part_to_slice(slices: list[_BlockSlice]) -> dict[str, str]:
    return {
        part_id: block_slice.key
        for block_slice in slices
        for part_id in block_slice.member_part_ids
    }


def _slice_graph(
    intent: SchematicDesignIntent,
    slices: list[_BlockSlice],
) -> dict[tuple[str, str], float]:
    part_to_slice = _part_to_slice(slices)
    weights: dict[tuple[str, str], float] = defaultdict(float)
    for net in intent.nets:
        slice_ids = sorted(
            {
                part_to_slice[part_id]
                for part_id in net.part_ids
                if part_id in part_to_slice
            }
        )
        if len(slice_ids) < 2:
            continue
        if net.role in {"ground", "power"}:
            edge_weight = 0.2
        elif net.role in {"clock", "reset", "interface"}:
            edge_weight = 2.0
        else:
            edge_weight = 1.0
        for index, first in enumerate(slice_ids):
            for second in slice_ids[index + 1 :]:
                weights[(first, second)] += edge_weight
    return dict(weights)


def _degree_map(
    slices: list[_BlockSlice],
    graph: dict[tuple[str, str], float],
) -> dict[str, float]:
    degree = {item.key: 0.0 for item in slices}
    for (first, second), weight in graph.items():
        degree[first] += weight
        degree[second] += weight
    return degree


def _edge_weight(
    graph: dict[tuple[str, str], float],
    first: str,
    second: str,
) -> float:
    key = tuple(sorted((first, second)))
    return graph.get((key[0], key[1]), 0.0)


def _order_slices(
    slices: list[_BlockSlice],
    graph: dict[tuple[str, str], float],
    strategy: OrderStrategy,
) -> list[_BlockSlice]:
    role_rank: dict[BlockRole, int] = {
        "connector": 0,
        "power": 1,
        "functional": 2,
        "generic": 3,
    }
    degree = _degree_map(slices, graph)
    if strategy == "role_then_id":
        return sorted(slices, key=lambda item: (item.sheet, role_rank[item.role], item.key))
    if strategy == "connectivity_degree":
        return sorted(
            slices,
            key=lambda item: (
                item.sheet,
                0 if item.role == "connector" else 1,
                -degree[item.key],
                role_rank[item.role],
                item.key,
            ),
        )

    result: list[_BlockSlice] = []
    for sheet in sorted({item.sheet for item in slices}):
        remaining = {item.key: item for item in slices if item.sheet == sheet}
        seeds = sorted(
            remaining.values(),
            key=lambda item: (
                0 if item.role == "connector" else 1,
                -degree[item.key],
                role_rank[item.role],
                item.key,
            ),
        )
        if not seeds:
            continue
        current = seeds[0]
        while remaining:
            if current.key in remaining:
                result.append(current)
                remaining.pop(current.key)
            if not remaining:
                break
            current = min(
                remaining.values(),
                key=lambda item: (
                    -_edge_weight(graph, result[-1].key, item.key),
                    0 if item.role == "connector" else 1,
                    -degree[item.key],
                    role_rank[item.role],
                    item.key,
                ),
            )
    return result


def _snap(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _local_layout(
    block_slice: _BlockSlice,
    config: SchematicPlacementConfig,
    style: LocalStyle,
) -> tuple[dict[str, Point], float, float]:
    placements: dict[str, Point] = {}
    anchors = list(block_slice.anchor_part_ids)
    anchor_set = set(anchors)
    supports = [part_id for part_id in block_slice.member_part_ids if part_id not in anchor_set]
    for index, part_id in enumerate(anchors):
        placements[part_id] = Point(0.0, index * config.anchor_gap_y_mm)

    if not anchors:
        columns = max(1, math.ceil(math.sqrt(max(1, len(supports)))))
        for index, part_id in enumerate(supports):
            placements[part_id] = Point(
                (index % columns) * config.member_gap_x_mm,
                (index // columns) * config.member_gap_y_mm,
            )
        rows = max(1, math.ceil(max(1, len(supports)) / columns))
        return (
            placements,
            max(config.member_gap_x_mm, columns * config.member_gap_x_mm),
            max(config.member_gap_y_mm, rows * config.member_gap_y_mm),
        )

    anchor_height = max(config.anchor_gap_y_mm, len(anchors) * config.anchor_gap_y_mm)
    if style == "support_right":
        for index, part_id in enumerate(supports):
            row = index % 4
            column = index // 4
            placements[part_id] = Point(
                config.member_gap_x_mm * (1 + column),
                row * config.member_gap_y_mm,
            )
        width = config.member_gap_x_mm * (1 + max(1, math.ceil(len(supports) / 4)))
        height = max(anchor_height, config.member_gap_y_mm * max(1, min(4, len(supports))))
        return placements, width, height

    if style == "support_below":
        for index, part_id in enumerate(supports):
            column = index % 4
            row = index // 4
            placements[part_id] = Point(
                column * config.member_gap_x_mm,
                anchor_height + row * config.member_gap_y_mm,
            )
        width = config.member_gap_x_mm * max(1, min(4, len(supports)))
        height = anchor_height + config.member_gap_y_mm * max(
            1, math.ceil(len(supports) / 4)
        )
        return placements, width, height

    left = supports[::2]
    right = supports[1::2]
    for index, part_id in enumerate(left):
        placements[part_id] = Point(-config.member_gap_x_mm, index * config.member_gap_y_mm)
    for index, part_id in enumerate(right):
        placements[part_id] = Point(config.member_gap_x_mm, index * config.member_gap_y_mm)
    height = max(
        anchor_height,
        config.member_gap_y_mm * max(1, len(left), len(right)),
    )
    return placements, config.member_gap_x_mm * 3.0, height


def _pack_candidate(
    snapshot: DocumentSnapshot,
    ordered_slices: list[_BlockSlice],
    config: SchematicPlacementConfig,
    *,
    row_width: float,
    local_style: LocalStyle,
) -> tuple[dict[str, Point], list[dict[str, Any]]]:
    assert snapshot.schematic is not None
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    placements: dict[str, Point] = {}
    unresolved: list[dict[str, Any]] = []
    by_sheet: dict[str, list[_BlockSlice]] = defaultdict(list)
    for block_slice in ordered_slices:
        by_sheet[block_slice.sheet].append(block_slice)

    for sheet in sorted(by_sheet):
        cursor_x = config.origin_x_mm
        cursor_y = config.origin_y_mm
        row_height = 0.0
        for block_slice in by_sheet[sheet]:
            local, width, height = _local_layout(block_slice, config, local_style)
            if (
                cursor_x > config.origin_x_mm
                and cursor_x + width - config.origin_x_mm > row_width
            ):
                cursor_x = config.origin_x_mm
                cursor_y += row_height + config.block_gap_y_mm
                row_height = 0.0
            for part_id, offset in local.items():
                part = parts_by_id.get(part_id)
                if part is None:
                    unresolved.append({"part_id": part_id, "reason": "part_missing"})
                    continue
                if part.locked:
                    if part.position is None:
                        unresolved.append(
                            {"part_id": part_id, "reason": "locked_position_missing"}
                        )
                        continue
                    placements[part_id] = Point(**part.position)
                    continue
                placements[part_id] = Point(
                    _snap(cursor_x + offset.x, config.grid_mm),
                    _snap(cursor_y + offset.y, config.grid_mm),
                )
            cursor_x += width + config.block_gap_x_mm
            row_height = max(row_height, height)
    return placements, unresolved


def _mst_edges(part_ids: list[str], placements: dict[str, Point]) -> list[tuple[str, str]]:
    remaining = sorted(part_id for part_id in part_ids if part_id in placements)
    if len(remaining) < 2:
        return []
    connected = {remaining.pop(0)}
    edges: list[tuple[str, str]] = []
    while remaining:
        first, second = min(
            (
                (connected_id, remaining_id)
                for connected_id in sorted(connected)
                for remaining_id in remaining
            ),
            key=lambda pair: (
                distance(placements[pair[0]], placements[pair[1]]),
                pair[0],
                pair[1],
            ),
        )
        edges.append((first, second))
        connected.add(second)
        remaining.remove(second)
    return edges


def _orientation(first: Point, second: Point, third: Point) -> float:
    return (second.x - first.x) * (third.y - first.y) - (
        second.y - first.y
    ) * (third.x - first.x)


def _proper_intersection(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> bool:
    if any(
        math.isclose(first.x, second.x, abs_tol=_EPS)
        and math.isclose(first.y, second.y, abs_tol=_EPS)
        for first in (first_start, first_end)
        for second in (second_start, second_end)
    ):
        return False
    a = _orientation(first_start, first_end, second_start)
    b = _orientation(first_start, first_end, second_end)
    c = _orientation(second_start, second_end, first_start)
    d = _orientation(second_start, second_end, first_end)
    return ((a > _EPS and b < -_EPS) or (a < -_EPS and b > _EPS)) and (
        (c > _EPS and d < -_EPS) or (c < -_EPS and d > _EPS)
    )


def _l_segments(start: Point, end: Point, horizontal_first: bool) -> list[tuple[Point, Point]]:
    if math.isclose(start.x, end.x, abs_tol=_EPS) or math.isclose(
        start.y, end.y, abs_tol=_EPS
    ):
        return [(start, end)]
    corner = Point(end.x, start.y) if horizontal_first else Point(start.x, end.y)
    return [(start, corner), (corner, end)]


def _crossing_count(
    candidate: list[tuple[Point, Point]],
    existing: list[_EstimatedSegment],
) -> int:
    return sum(
        _proper_intersection(start, end, segment.start, segment.end)
        for start, end in candidate
        for segment in existing
    )


def _estimate_interconnect(
    intent: SchematicDesignIntent,
    placements: dict[str, Point],
    *,
    include_power: bool,
) -> tuple[float, int]:
    total_length = 0.0
    segments: list[_EstimatedSegment] = []
    crossings = 0
    for net in sorted(intent.nets, key=lambda item: item.net_id):
        if net.role == "ground":
            continue
        if net.role == "power" and not include_power:
            continue
        net_weight = 0.2 if net.role == "power" else 1.0
        for first_id, second_id in _mst_edges(net.part_ids, placements):
            start = placements[first_id]
            end = placements[second_id]
            horizontal_first = _l_segments(start, end, True)
            vertical_first = _l_segments(start, end, False)
            first_crossings = _crossing_count(horizontal_first, segments)
            second_crossings = _crossing_count(vertical_first, segments)
            chosen = horizontal_first if first_crossings <= second_crossings else vertical_first
            crossings += min(first_crossings, second_crossings)
            total_length += net_weight * sum(distance(first, second) for first, second in chosen)
            segments.extend(
                _EstimatedSegment(net.net_id, first, second) for first, second in chosen
            )
    return total_length, crossings


def _backward_connector_flow(
    intent: SchematicDesignIntent,
    slices: list[_BlockSlice],
    placements: dict[str, Point],
) -> int:
    part_to_slice = _part_to_slice(slices)
    slice_roles = {item.key: item.role for item in slices}
    part_x: dict[str, float] = {
        part_id: point.x for part_id, point in placements.items()
    }
    violations = 0
    for net in intent.nets:
        block_ids = {
            part_to_slice[part_id]
            for part_id in net.part_ids
            if part_id in part_to_slice and part_id in part_x
        }
        connectors = {item for item in block_ids if slice_roles[item] == "connector"}
        others = block_ids - connectors
        for connector in connectors:
            connector_members = [
                part_id
                for part_id, slice_id in part_to_slice.items()
                if slice_id == connector and part_id in part_x
            ]
            if not connector_members:
                continue
            connector_x = sum(part_x[item] for item in connector_members) / len(connector_members)
            for other in others:
                other_members = [
                    part_id
                    for part_id, slice_id in part_to_slice.items()
                    if slice_id == other and part_id in part_x
                ]
                if not other_members:
                    continue
                other_x = sum(part_x[item] for item in other_members) / len(other_members)
                if connector_x > other_x + _EPS:
                    violations += 1
    return violations


def _movement(snapshot: DocumentSnapshot, placements: dict[str, Point]) -> float:
    assert snapshot.schematic is not None
    total = 0.0
    for part in snapshot.schematic.parts:
        target = placements.get(part.stable_id)
        if target is None or part.position is None:
            continue
        total += distance(Point(**part.position), target)
    return total


def _candidate_id(
    strategy: OrderStrategy,
    style: LocalStyle,
    row_width: float,
    placements: dict[str, Point],
) -> str:
    digest_input = [strategy, style, f"{row_width:.9g}"]
    digest_input.extend(
        f"{part_id}:{point.x:.9g}:{point.y:.9g}"
        for part_id, point in sorted(placements.items())
    )
    digest = hashlib.sha256("\0".join(digest_input).encode("utf-8")).hexdigest()[:16]
    return f"schematic-placement-{digest}"


def generate_schematic_placement_candidates(
    snapshot: DocumentSnapshot,
    *,
    intent: SchematicDesignIntent | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicOptimizerConfig | None = None,
) -> list[SchematicPlacementCandidate]:
    config = config or SchematicOptimizerConfig()
    _require_unwired_schematic(snapshot, config)
    assert snapshot.schematic is not None
    intent = intent or infer_schematic_design_intent(snapshot, motifs=motifs)
    slices = _split_blocks_by_sheet(snapshot, intent)
    graph = _slice_graph(intent, slices)
    candidates: list[SchematicPlacementCandidate] = []
    seen_layouts: set[tuple[tuple[str, float, float], ...]] = set()

    combinations = [
        (strategy, style, config.placement.target_row_width_mm * scale)
        for strategy in config.order_strategies
        for style in config.local_styles
        for scale in config.row_width_scales
    ]
    for strategy, style, row_width in combinations:
        if len(candidates) >= config.max_candidates:
            break
        ordered = _order_slices(slices, graph, strategy)
        placements, unresolved = _pack_candidate(
            snapshot,
            ordered,
            config.placement,
            row_width=row_width,
            local_style=style,
        )
        identity = tuple(
            (part_id, round(point.x, 9), round(point.y, 9))
            for part_id, point in sorted(placements.items())
        )
        if identity in seen_layouts:
            continue
        seen_layouts.add(identity)
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
        candidates.append(
            SchematicPlacementCandidate(
                candidate_id=_candidate_id(strategy, style, row_width, placements),
                order_strategy=strategy,
                local_style=style,
                row_width_mm=row_width,
                placements={part_id: point.as_dict() for part_id, point in placements.items()},
                estimated_interconnect_length_mm=estimated_length,
                estimated_crossing_count=estimated_crossings,
                backward_connector_flow_count=backward_flow,
                movement_mm=movement_mm,
                score_terms=terms,
                total_score=sum(terms.values()),
                layout=layout,
                unresolved=unresolved,
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            item.total_score,
            item.estimated_crossing_count,
            item.estimated_interconnect_length_mm,
            item.candidate_id,
        ),
    )


def plan_optimized_schematic_placement(
    snapshot: DocumentSnapshot,
    *,
    intent: SchematicDesignIntent | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicOptimizerConfig | None = None,
) -> SchematicOptimizationPlan:
    config = config or SchematicOptimizerConfig()
    _require_unwired_schematic(snapshot, config)
    assert snapshot.schematic is not None
    candidates = generate_schematic_placement_candidates(
        snapshot,
        intent=intent,
        motifs=motifs,
        config=config,
    )
    if not candidates:
        raise CapabilityUnavailableError("No schematic placement candidate could be generated")
    selected = candidates[0]
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    operations: list[SemanticOperation] = []
    changed: list[str] = []
    for part_id, raw_point in sorted(selected.placements.items()):
        part = parts_by_id.get(part_id)
        if part is None or part.position is None or part.locked:
            continue
        target = Point(**raw_point)
        current = Point(**part.position)
        if math.isclose(current.x, target.x, abs_tol=_EPS) and math.isclose(
            current.y, target.y, abs_tol=_EPS
        ):
            continue
        operations.append(
            MoveComponentsOperation(
                selector=QuerySelector(ids=[part_id]),
                absolute_x=target.x,
                absolute_y=target.y,
            )
        )
        changed.append(part_id)
    return SchematicOptimizationPlan(
        selected=selected,
        candidates=candidates,
        operations=operations,
        changed_part_ids=changed,
        assumptions=[
            "The optimizer compares bounded deterministic placement candidates; "
            "it does not claim a global optimum.",
            "Future interconnect cost is estimated with part-anchor Manhattan trees because "
            "exact schematic pin geometry is not normalized.",
            "Connector-left-to-right flow is a soft readability convention, "
            "not an electrical rule.",
        ],
        warnings=list(selected.layout.warnings),
        limitations=[
            "The optimizer currently targets unwired schematics; existing-wire "
            "co-optimization is Phase 30 work.",
            "Estimated crossings are based on deterministic Manhattan L-routes, "
            "not final DipTrace wire geometry.",
            "Automatic symbol rotation remains disabled until trustworthy pin-facing "
            "geometry is available.",
        ],
    )
