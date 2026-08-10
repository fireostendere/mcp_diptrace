from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import StrictModel
from .geometry import Point, distance
from .operations import AddWireOperation, WireEndpoint
from .services.schematic_wire_quality import (
    _existing_wire_segments,
    _intentional_wire_touches,
    _part_obstacles,
    _quality,
    _simplify_points,
    _text_obstacles,
    _wire_anchor,
    clean_schematic_wire_operation,
)
from .xml_document import DipTraceDocument

_EPS = 1e-9
FeedbackKind = Literal[
    "none",
    "open_routing_corridor",
    "move_endpoint_blocks_closer",
    "repack_endpoint_blocks",
]


class SchematicWirePlannerConfig(StrictModel):
    max_detour_ratio: float = Field(default=2.5, ge=1.0, le=100.0)
    max_bends: int = Field(default=6, ge=0, le=1_000)
    require_zero_obstacle_hits: bool = True
    require_zero_overlaps: bool = True
    require_zero_crossings: bool = True
    require_zero_self_intersections: bool = True
    require_orthogonal: bool = True


class SchematicWireMetrics(StrictModel):
    obstacle_hits: int = Field(ge=0)
    overlaps: int = Field(ge=0)
    crossings: int = Field(ge=0)
    self_intersections: int = Field(ge=0)
    diagonals: int = Field(ge=0)
    bends: int = Field(ge=0)
    length_mm: float = Field(ge=0.0)
    direct_distance_mm: float = Field(ge=0.0)
    detour_ratio: float = Field(ge=1.0)
    quality_key: list[float] = Field(min_length=7, max_length=7)


class SchematicWireCandidate(StrictModel):
    source: Literal["supplied", "cleaned"]
    operation: AddWireOperation
    metrics: SchematicWireMetrics


class SchematicPlacementFeedback(StrictModel):
    required: bool
    kind: FeedbackKind
    endpoint_part_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SchematicWirePlan(StrictModel):
    original: SchematicWireCandidate
    selected: SchematicWireCandidate
    improved: bool
    accept_route: bool
    placement_feedback: SchematicPlacementFeedback
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _normalized_points(
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
) -> list[Point]:
    points = _simplify_points([Point(item.x, item.y) for item in operation.points])
    if len(points) < 2:
        return points
    points[0] = _wire_anchor(snapshot, operation.start, points[0])
    points[-1] = _wire_anchor(snapshot, operation.end, points[-1])
    return _simplify_points(points)


def measure_schematic_wire_operation(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
) -> SchematicWireMetrics:
    """Measure one authored-wire candidate without mutating the document or snapshot."""
    points = _normalized_points(snapshot, operation)
    if len(points) < 2:
        return SchematicWireMetrics(
            obstacle_hits=0,
            overlaps=0,
            crossings=0,
            self_intersections=0,
            diagonals=0,
            bends=0,
            length_mm=0.0,
            direct_distance_mm=0.0,
            detour_ratio=1.0,
            quality_key=[0.0] * 7,
        )
    start, end = points[0], points[-1]
    obstacles = [
        *_part_obstacles(snapshot, operation),
        *_text_obstacles(document, operation.sheet),
    ]
    existing = _existing_wire_segments(snapshot, operation.sheet)
    touches = _intentional_wire_touches(operation, start, end)
    quality = _quality(points, obstacles, existing, touches)
    direct_distance = distance(start, end)
    detour_ratio = (
        max(1.0, quality.length / direct_distance)
        if direct_distance > _EPS
        else 1.0
    )
    return SchematicWireMetrics(
        obstacle_hits=quality.obstacle_hits,
        overlaps=quality.overlaps,
        crossings=quality.crossings,
        self_intersections=quality.self_intersections,
        diagonals=quality.diagonals,
        bends=quality.bends,
        length_mm=quality.length,
        direct_distance_mm=direct_distance,
        detour_ratio=detour_ratio,
        quality_key=[
            float(quality.obstacle_hits),
            float(quality.overlaps),
            float(quality.crossings),
            float(quality.self_intersections),
            float(quality.diagonals),
            float(quality.bends),
            quality.length,
        ],
    )


def _endpoint_part_ids(snapshot: DocumentSnapshot, endpoint: WireEndpoint) -> list[str]:
    if endpoint.type != "Pin" or snapshot.schematic is None:
        return []
    if endpoint.part_id is not None:
        return sorted(
            part.stable_id
            for part in snapshot.schematic.parts
            if endpoint.part_id in {part.stable_id, part.xml_id or ""}
        )
    assert endpoint.refdes is not None
    return sorted(
        part.stable_id
        for part in snapshot.schematic.parts
        if (part.refdes or "").casefold() == endpoint.refdes.casefold()
    )


def _feedback(
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    metrics: SchematicWireMetrics,
    config: SchematicWirePlannerConfig,
) -> SchematicPlacementFeedback:
    reasons: list[str] = []
    hard_geometry_problem = False
    if config.require_zero_obstacle_hits and metrics.obstacle_hits:
        reasons.append(f"route still intersects {metrics.obstacle_hits} visual obstacle(s)")
        hard_geometry_problem = True
    if config.require_zero_overlaps and metrics.overlaps:
        reasons.append(f"route still overlaps {metrics.overlaps} existing wire segment(s)")
        hard_geometry_problem = True
    if config.require_zero_crossings and metrics.crossings:
        reasons.append(f"route still crosses {metrics.crossings} existing wire segment(s)")
        hard_geometry_problem = True
    if config.require_zero_self_intersections and metrics.self_intersections:
        reasons.append(
            f"route still contains {metrics.self_intersections} self-intersection(s)"
        )
        hard_geometry_problem = True
    if config.require_orthogonal and metrics.diagonals:
        reasons.append(f"route still contains {metrics.diagonals} diagonal segment(s)")
        hard_geometry_problem = True

    detour_problem = metrics.detour_ratio > config.max_detour_ratio + _EPS
    bend_problem = metrics.bends > config.max_bends
    if detour_problem:
        reasons.append(
            f"route detour ratio {metrics.detour_ratio:.3g} exceeds "
            f"{config.max_detour_ratio:.3g}"
        )
    if bend_problem:
        reasons.append(f"route has {metrics.bends} bends, above limit {config.max_bends}")

    if hard_geometry_problem:
        kind: FeedbackKind = "open_routing_corridor"
    elif detour_problem:
        kind = "move_endpoint_blocks_closer"
    elif bend_problem:
        kind = "repack_endpoint_blocks"
    else:
        kind = "none"

    endpoint_part_ids = sorted(
        {
            *_endpoint_part_ids(snapshot, operation.start),
            *_endpoint_part_ids(snapshot, operation.end),
        }
    )
    return SchematicPlacementFeedback(
        required=bool(reasons),
        kind=kind,
        endpoint_part_ids=endpoint_part_ids,
        reasons=reasons,
    )


def plan_schematic_wire_candidate(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    *,
    config: SchematicWirePlannerConfig | None = None,
) -> SchematicWirePlan:
    """Return a non-mutating wire candidate and explicit placement feedback.

    The existing bounded wire cleaner remains the route generator. This planner exposes
    its result as data, measures both the supplied and selected route, and decides whether
    the selected route is acceptable under explicit readability thresholds. It does not
    apply the operation and it does not move schematic parts implicitly.
    """
    config = config or SchematicWirePlannerConfig()
    original_metrics = measure_schematic_wire_operation(document, snapshot, operation)
    cleaned_operation = clean_schematic_wire_operation(document, snapshot, operation)
    cleaned_metrics = measure_schematic_wire_operation(
        document,
        snapshot,
        cleaned_operation,
    )

    original_key = tuple(original_metrics.quality_key)
    cleaned_key = tuple(cleaned_metrics.quality_key)
    if cleaned_key <= original_key:
        selected_source: Literal["supplied", "cleaned"] = "cleaned"
        selected_operation = cleaned_operation
        selected_metrics = cleaned_metrics
    else:
        selected_source = "supplied"
        selected_operation = operation
        selected_metrics = original_metrics

    original = SchematicWireCandidate(
        source="supplied",
        operation=operation,
        metrics=original_metrics,
    )
    selected = SchematicWireCandidate(
        source=selected_source,
        operation=selected_operation,
        metrics=selected_metrics,
    )
    feedback = _feedback(snapshot, selected_operation, selected_metrics, config)
    improved = (
        selected.operation.model_dump(mode="json")
        != operation.model_dump(mode="json")
    )
    warnings: list[str] = []
    if snapshot.schematic is None:
        warnings.append("Snapshot has no normalized schematic model; route quality is partial.")
    if math.isclose(selected_metrics.direct_distance_mm, 0.0, abs_tol=_EPS):
        warnings.append(
            "Wire endpoints collapse to the same point; detour ratio is not meaningful."
        )

    return SchematicWirePlan(
        original=original,
        selected=selected,
        improved=improved,
        accept_route=not feedback.required,
        placement_feedback=feedback,
        assumptions=[
            "The existing deterministic wire cleaner is the route candidate generator.",
            "Component and text bounds are conservative visual obstacles.",
            "Placement feedback is advisory and never mutates symbol placement implicitly.",
        ],
        warnings=warnings,
        limitations=[
            "Exact schematic pin graphics and pin-facing geometry are not normalized.",
            "Placement feedback identifies affected endpoint parts and repair intent, "
            "not a final move coordinate.",
            "The planner evaluates one authored connection at a time; sheet-level net "
            "ordering is a later phase.",
        ],
    )
