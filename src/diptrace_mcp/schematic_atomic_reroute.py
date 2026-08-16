from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import build_snapshot
from .domain import QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import Point, distance
from .operations import (
    AddWireOperation,
    DeleteWireOperation,
    RotateComponentsOperation,
    SemanticOperation,
    WireEndpoint,
    WirePathPoint,
)
from .schematic_joint_optimizer import (
    _affected_groups,
    _append_completed_net_routes,
    _initial_points,
    _moved_parts,
    _mst_endpoint_edges,
    _net_names,
    _remove_affected_wires,
    _virtual_endpoints,
    _virtualize_snapshot,
)
from .schematic_optimizer import SchematicPlacementCandidate
from .schematic_pin_geometry import (
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .schematic_rotation import SchematicRotationCandidate
from .schematic_topology import (
    build_proven_schematic_topology,
    topology_junction_path,
)
from .schematic_wire_planner import (
    SchematicWirePlannerConfig,
    plan_schematic_wire_candidate,
)
from .xml_document import DipTraceDocument

_EPS = 1e-9


class SchematicAtomicRerouteConfig(StrictModel):
    """Bounds and policy for one placement/rotation + affected-wire transaction."""

    max_moved_parts: int = Field(default=256, ge=1, le=10_000)
    max_affected_net_groups: int = Field(default=256, ge=1, le=10_000)
    max_deleted_wires: int = Field(default=2_048, ge=1, le=50_000)
    max_added_wires: int = Field(default=2_048, ge=1, le=50_000)
    include_unwired_affected_nets: bool = False
    preserve_intentional_junctions: bool = True
    preserve_proven_topology: bool = True
    topology_match_tolerance_mm: float = Field(default=0.5, gt=0.0, le=10.0)
    maximum_junction_detour_ratio: float = Field(default=2.5, ge=1.0, le=20.0)
    minimum_rotation_pin_confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    wire_planner: SchematicWirePlannerConfig = Field(
        default_factory=SchematicWirePlannerConfig
    )


class SchematicAffectedNetGroup(StrictModel):
    net_id: str
    net_name: str
    sheet: int = Field(ge=0)
    moved_part_ids: list[str] = Field(default_factory=list)
    pin_ids: list[str] = Field(default_factory=list)
    deleted_wire_ids: list[str] = Field(default_factory=list)
    replacement_edge_count: int = Field(ge=0)
    preserved_junction_count: int = Field(default=0, ge=0)
    quality_feedback: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SchematicAtomicReroutePlan:
    """Typed, non-mutating plan ready for the existing semantic transaction path."""

    operations: list[SemanticOperation]
    moved_part_ids: list[str]
    deleted_wire_ids: list[str]
    added_wire_count: int
    affected_net_groups: list[SchematicAffectedNetGroup]
    warnings: list[str]
    limitations: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "operations": [item.model_dump(mode="json") for item in self.operations],
            "moved_part_ids": list(self.moved_part_ids),
            "deleted_wire_ids": list(self.deleted_wire_ids),
            "added_wire_count": self.added_wire_count,
            "affected_net_groups": [
                item.model_dump(mode="json") for item in self.affected_net_groups
            ],
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def _readability_feedback(
    *,
    net_name: str,
    sheet: int,
    route_index: int,
    plan: Any,
) -> str:
    reasons = list(plan.placement_feedback.reasons)
    if not reasons:
        metrics = plan.selected.metrics
        reasons = [
            f"obstacle_hits={metrics.obstacle_hits}",
            f"overlaps={metrics.overlaps}",
            f"crossings={metrics.crossings}",
            f"self_intersections={metrics.self_intersections}",
            f"diagonals={metrics.diagonals}",
            f"bends={metrics.bends}",
            f"detour_ratio={metrics.detour_ratio:.3g}",
        ]
    return (
        f"Selective reroute readability feedback for {net_name!r} on sheet {sheet}, "
        f"replacement edge {route_index}: {'; '.join(reasons)}. Connectivity-safe "
        "replacement is retained for the atomic transaction; readability remains "
        "explicit review/repair feedback."
    )


def _intentional_junctions(snapshot: Any, wire_ids: list[str]) -> list[Point]:
    """Legacy single-junction detector retained for focused compatibility tests."""

    if snapshot.schematic is None:
        return []
    selected_ids = set(wire_ids)
    selected = {
        item.stable_id: item
        for item in snapshot.schematic.wires
        if item.stable_id in selected_ids
    }
    degree: dict[tuple[float, float], int] = {}
    for wire in selected.values():
        points = [Point(**item) for item in wire.attributes.get("points", [])]
        for first, second in zip(points, points[1:], strict=False):
            for point in (first, second):
                key = (round(point.x, 9), round(point.y, 9))
                degree[key] = degree.get(key, 0) + 1
    return [Point(*key) for key, value in sorted(degree.items()) if value >= 3]


def _points_via_preserved_junction(
    start: Point,
    end: Point,
    junctions: list[Point],
    *,
    maximum_detour_ratio: float,
) -> tuple[list[WirePathPoint], Point | None]:
    """Legacy bounded single-junction path helper."""

    if not junctions:
        return _initial_points(start, end), None
    junction = min(
        junctions,
        key=lambda item: (distance(start, item) + distance(item, end), item.x, item.y),
    )
    direct = max(distance(start, end), _EPS)
    detour = distance(start, junction) + distance(junction, end)
    if detour > direct * maximum_detour_ratio:
        return _initial_points(start, end), None
    raw = [
        start,
        Point(junction.x, start.y),
        junction,
        Point(end.x, junction.y),
        end,
    ]
    points: list[WirePathPoint] = []
    for point in raw:
        if (
            points
            and math.isclose(points[-1].x, point.x, abs_tol=_EPS)
            and math.isclose(points[-1].y, point.y, abs_tol=_EPS)
        ):
            continue
        points.append(WirePathPoint(x=point.x, y=point.y))
    return points, junction


def _points_via_proven_junctions(
    start: Point,
    end: Point,
    junctions: list[Point],
    *,
    maximum_detour_ratio: float,
) -> tuple[list[WirePathPoint], list[Point]]:
    """Connect endpoints through every proven original junction in path order."""

    if not junctions:
        return _initial_points(start, end), []
    direct = max(distance(start, end), _EPS)
    chain = [start, *junctions, end]
    detour = sum(
        distance(first, second)
        for first, second in zip(chain, chain[1:], strict=False)
    )
    if detour > direct * maximum_detour_ratio:
        raise CapabilityUnavailableError(
            "Proven schematic topology exceeds the bounded junction detour; refusing "
            "to drop or rewrite its branch structure"
        )

    raw: list[Point] = [start]
    cursor = start
    for target in [*junctions, end]:
        if not math.isclose(cursor.x, target.x, abs_tol=_EPS) and not math.isclose(
            cursor.y,
            target.y,
            abs_tol=_EPS,
        ):
            raw.append(Point(target.x, cursor.y))
        raw.append(target)
        cursor = target

    points: list[WirePathPoint] = []
    for point in raw:
        if (
            points
            and math.isclose(points[-1].x, point.x, abs_tol=_EPS)
            and math.isclose(points[-1].y, point.y, abs_tol=_EPS)
        ):
            continue
        points.append(WirePathPoint(x=point.x, y=point.y))
    return points, list(junctions)


def plan_atomic_schematic_placement_reroute(
    document: DipTraceDocument,
    candidate: SchematicPlacementCandidate | None,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    source_pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicAtomicRerouteConfig | None = None,
    forced_affected_part_ids: list[str] | None = None,
    additional_part_operations: list[SemanticOperation] | None = None,
    planning_document: DipTraceDocument | None = None,
) -> SchematicAtomicReroutePlan:
    """Plan one all-or-nothing placement/rotation and selective affected-net reroute.

    The function is deliberately non-mutating. It returns ordinary semantic
    operations in dependency-safe order: delete affected wire geometry, move/rotate
    parts, then author replacement wires. Passing the complete list to the existing
    semantic-operations transaction path keeps every change under the same
    SHA/preview/commit boundary.

    ``source_pin_geometry`` proves the original hand-authored topology. ``pin_geometry``
    describes the target geometry after any hypothetical rotation. Keeping those two
    coordinate spaces separate prevents a rotated candidate from being used as proof
    of the original wire graph.
    """

    config = config or SchematicAtomicRerouteConfig()
    snapshot = build_snapshot(document)
    if snapshot.schematic is None:
        raise CapabilityUnavailableError(
            "Atomic schematic placement/reroute requires a schematic document"
        )

    planning_document = planning_document or document
    planning_snapshot = build_snapshot(planning_document)
    if planning_snapshot.schematic is None:
        raise CapabilityUnavailableError(
            "Atomic schematic reroute planning document has no schematic model"
        )

    if candidate is None:
        placements = {
            part.stable_id: dict(part.position)
            for part in planning_snapshot.schematic.parts
            if part.position is not None
        }
        moved_part_ids: list[str] = []
        move_operations: list[SemanticOperation] = []
    else:
        placements = candidate.placements
        moved_part_ids, raw_move_operations = _moved_parts(snapshot, candidate)
        move_operations = list(raw_move_operations)

    forced = sorted(set(forced_affected_part_ids or []))
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    for part_id in forced:
        part = parts_by_id.get(part_id)
        if part is None:
            raise CapabilityUnavailableError(
                f"Atomic schematic reroute references missing forced part {part_id}"
            )
        if part.locked:
            raise CapabilityUnavailableError(
                f"Atomic schematic reroute refuses to mutate locked part {part_id}"
            )

    moved_part_ids = sorted(set(moved_part_ids) | set(forced))
    part_operations = [*move_operations, *(additional_part_operations or [])]
    if not moved_part_ids:
        return SchematicAtomicReroutePlan(
            operations=[],
            moved_part_ids=[],
            deleted_wire_ids=[],
            added_wire_count=0,
            affected_net_groups=[],
            warnings=["Candidate does not move or rotate any schematic part."],
            limitations=[],
        )
    if len(moved_part_ids) > config.max_moved_parts:
        raise CapabilityUnavailableError(
            f"Atomic reroute moved/rotated-part count exceeds {config.max_moved_parts}"
        )

    group_state = _affected_groups(
        snapshot,
        moved_part_ids,
        include_unwired=config.include_unwired_affected_nets,
    )
    if len(group_state) > config.max_affected_net_groups:
        raise CapabilityUnavailableError(
            "Atomic reroute affected-net-group count exceeds the configured bound"
        )

    deleted_wire_ids = sorted(
        {
            wire_id
            for state in group_state.values()
            for wire_id in state["deleted_wire_ids"]
        }
    )
    if len(deleted_wire_ids) > config.max_deleted_wires:
        raise CapabilityUnavailableError(
            f"Atomic reroute would replace more than {config.max_deleted_wires} wires"
        )

    delete_operations: list[SemanticOperation] = [
        DeleteWireOperation(selector=QuerySelector(ids=[wire_id]))
        for wire_id in deleted_wire_ids
    ]
    if not group_state:
        return SchematicAtomicReroutePlan(
            operations=[*part_operations],
            moved_part_ids=moved_part_ids,
            deleted_wire_ids=[],
            added_wire_count=0,
            affected_net_groups=[],
            warnings=[
                (
                    "Moved/rotated parts touch no explicit wire geometry under the "
                    "current selective-reroute policy."
                )
            ],
            limitations=[
                (
                    "Unwired affected nets are preserved as connectivity-only nets "
                    "unless include_unwired_affected_nets is enabled."
                )
            ],
        )

    source_pin_geometry = source_pin_geometry or resolve_document_schematic_pin_geometry(
        document
    )
    pin_geometry = pin_geometry or source_pin_geometry
    virtual, virtualization_warnings = _virtualize_snapshot(
        planning_snapshot,
        placements,
    )
    affected_keys = set(group_state)
    _remove_affected_wires(virtual, affected_keys)
    endpoint_groups, endpoint_warnings = _virtual_endpoints(
        snapshot,
        virtual,
        pin_geometry,
    )
    net_names = _net_names(snapshot)

    add_operations: list[SemanticOperation] = []
    reports: list[SchematicAffectedNetGroup] = []
    warnings = [
        *virtualization_warnings,
        *endpoint_warnings,
        *source_pin_geometry.warnings,
        *pin_geometry.warnings,
    ]

    for net_id, sheet in sorted(affected_keys):
        endpoints = endpoint_groups.get((net_id, sheet), [])
        if len(endpoints) < 2:
            raise CapabilityUnavailableError(
                f"Affected net {net_names.get(net_id, net_id)!r} on sheet {sheet} "
                "does not have at least two resolvable endpoints; refusing "
                "destructive reroute"
            )
        edges = _mst_endpoint_edges(endpoints)
        if len(add_operations) + len(edges) > config.max_added_wires:
            raise CapabilityUnavailableError(
                f"Atomic reroute would author more than {config.max_added_wires} wires"
            )
        net_name = net_names.get(net_id, net_id)
        group_plans = []
        group_quality_feedback: list[str] = []
        state = group_state[(net_id, sheet)]
        topology = (
            build_proven_schematic_topology(
                snapshot,
                state["deleted_wire_ids"],
                source_pin_geometry,
                match_tolerance_mm=config.topology_match_tolerance_mm,
            )
            if config.preserve_intentional_junctions and config.preserve_proven_topology
            else None
        )
        used_junctions: set[tuple[float, float]] = set()
        for route_index, (start, end) in enumerate(edges, 1):
            if topology is not None:
                proven_junctions = topology_junction_path(
                    topology,
                    start.pin.stable_id,
                    end.pin.stable_id,
                )
                points, preserved_junctions = _points_via_proven_junctions(
                    start.point,
                    end.point,
                    proven_junctions,
                    maximum_detour_ratio=config.maximum_junction_detour_ratio,
                )
            else:
                points = _initial_points(start.point, end.point)
                preserved_junctions = []
            for preserved_junction in preserved_junctions:
                used_junctions.add(
                    (round(preserved_junction.x, 9), round(preserved_junction.y, 9))
                )

            operation = AddWireOperation(
                net=net_name,
                sheet=sheet,
                points=points,
                start=WireEndpoint(
                    type="Pin",
                    part_id=start.part.stable_id,
                    pin=start.pin_index,
                ),
                end=WireEndpoint(
                    type="Pin",
                    part_id=end.part.stable_id,
                    pin=end.pin_index,
                ),
            )
            plan = plan_schematic_wire_candidate(
                planning_document,
                virtual,
                operation,
                config=config.wire_planner,
            )
            if not plan.accept_route:
                feedback = _readability_feedback(
                    net_name=net_name,
                    sheet=sheet,
                    route_index=route_index,
                    plan=plan,
                )
                group_quality_feedback.append(feedback)
                warnings.append(feedback)
            add_operations.append(plan.selected.operation)
            group_plans.append((net_id, sheet, plan))
            _append_completed_net_routes(virtual, [(net_id, sheet, plan)])

        pin_ids = sorted(item.pin.stable_id for item in endpoints)
        reports.append(
            SchematicAffectedNetGroup(
                net_id=net_id,
                net_name=net_name,
                sheet=sheet,
                moved_part_ids=sorted(state["moved_part_ids"]),
                pin_ids=pin_ids,
                deleted_wire_ids=sorted(state["deleted_wire_ids"]),
                replacement_edge_count=len(group_plans),
                preserved_junction_count=len(used_junctions),
                quality_feedback=group_quality_feedback,
            )
        )

    operations: list[SemanticOperation] = [
        *delete_operations,
        *part_operations,
        *add_operations,
    ]
    return SchematicAtomicReroutePlan(
        operations=operations,
        moved_part_ids=moved_part_ids,
        deleted_wire_ids=deleted_wire_ids,
        added_wire_count=len(add_operations),
        affected_net_groups=reports,
        warnings=sorted(set(warnings)),
        limitations=[
            (
                "Selective reroute replaces explicit wire geometry only on "
                "sheet-local nets touched by moved/rotated parts; unaffected wire "
                "geometry is left byte-semantically untouched by the plan."
            ),
            (
                "Affected endpoint pairs remain deterministic, while every junction "
                "on an unambiguous existing acyclic wire graph is preserved in original "
                "path order. Cyclic, free-leaf, incomplete or ambiguous hand-authored "
                "topology is refused instead of being rewritten as an MST."
            ),
            (
                "Unresolved or insufficient endpoints remain fail-closed. Readability "
                "threshold failures from the wire planner are surfaced as explicit "
                "quality feedback and do not by themselves discard an otherwise "
                "connectivity-safe replacement."
            ),
            (
                "The planner is non-mutating. Atomicity is provided when the complete "
                "returned operation list is previewed/committed through the existing "
                "guarded semantic transaction path."
            ),
        ],
    )


def plan_atomic_schematic_rotation_reroute(
    document: DipTraceDocument,
    rotation: SchematicRotationCandidate,
    *,
    config: SchematicAtomicRerouteConfig | None = None,
) -> SchematicAtomicReroutePlan:
    """Plan one confidence-gated cardinal rotation and affected-wire rebuild.

    Rotation remains opt-in package logic until manual gate M2 validates the exact
    symbol/editor path. This function therefore prepares an atomic semantic batch but
    does not enable or apply rotation automatically.
    """

    config = config or SchematicAtomicRerouteConfig()
    snapshot = build_snapshot(document)
    if snapshot.schematic is None:
        raise CapabilityUnavailableError("Rotation reroute requires a schematic document")
    part = next(
        (item for item in snapshot.schematic.parts if item.stable_id == rotation.part_id),
        None,
    )
    if part is None:
        raise CapabilityUnavailableError("Rotation candidate references a missing part")
    if part.locked:
        raise CapabilityUnavailableError("Rotation reroute refuses a locked part")
    if not math.isclose(
        float(part.rotation_deg),
        rotation.source_angle_deg,
        abs_tol=1e-6,
    ):
        raise CapabilityUnavailableError(
            "Rotation candidate source angle is stale; regenerate candidates"
        )
    if rotation.pin_geometry_confidence < config.minimum_rotation_pin_confidence:
        raise CapabilityUnavailableError(
            "Rotation candidate does not meet the configured pin-geometry confidence"
        )
    if math.isclose(
        rotation.source_angle_deg % 360.0,
        float(rotation.target_angle_deg),
        abs_tol=1e-6,
    ):
        return SchematicAtomicReroutePlan(
            operations=[],
            moved_part_ids=[],
            deleted_wire_ids=[],
            added_wire_count=0,
            affected_net_groups=[],
            warnings=["Rotation candidate keeps the source angle."],
            limitations=["No mutation was planned."],
        )

    operation = RotateComponentsOperation(
        selector=QuerySelector(ids=[rotation.part_id]),
        angle_deg=float(rotation.target_angle_deg),
        mode="absolute",
        allowed_angles=[0.0, 90.0, 180.0, 270.0],
    )

    from .semantic_compiler import apply_semantic_operations

    source_geometry = resolve_document_schematic_pin_geometry(document)
    rotated_document = apply_semantic_operations(document, [operation]).document
    rotated_geometry = resolve_document_schematic_pin_geometry(rotated_document)

    source_part_pins = [
        pin for pin in snapshot.schematic.pins if pin.parent_id == rotation.part_id
    ]
    target_resolved = [
        item for item in rotated_geometry.pins if item.part_id == rotation.part_id
    ]
    if len(target_resolved) != len(source_part_pins) or any(
        item.absolute_position is None
        or item.absolute_orientation_deg is None
        or item.confidence < config.minimum_rotation_pin_confidence
        for item in target_resolved
    ):
        raise CapabilityUnavailableError(
            "Rotation reroute cannot prove complete target pin geometry; refusing "
            "wire deletion"
        )

    return plan_atomic_schematic_placement_reroute(
        document,
        None,
        pin_geometry=rotated_geometry,
        source_pin_geometry=source_geometry,
        config=config,
        forced_affected_part_ids=[rotation.part_id],
        additional_part_operations=[operation],
        planning_document=rotated_document,
    )
