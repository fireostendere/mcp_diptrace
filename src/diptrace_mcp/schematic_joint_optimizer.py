from __future__ import annotations

import copy
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot, stable_id
from .domain import ObjectRecord, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import BBox, Point, distance
from .operations import AddWireOperation, WireEndpoint, WirePathPoint
from .schematic_layout import NetRole, infer_schematic_design_intent
from .schematic_optimizer import SchematicPlacementCandidate
from .schematic_pin_geometry import (
    ResolvedSchematicPinGeometry,
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .schematic_wire_planner import (
    SchematicWirePlan,
    SchematicWirePlannerConfig,
    plan_schematic_wire_candidate,
)
from .xml_document import DipTraceDocument

_EPS = 1e-9
EndpointGeometrySource = Literal[
    "embedded_pin",
    "provided_pin",
    "external_pin",
    "fallback_part_anchor",
]


class SchematicJointRouteConfig(StrictModel):
    max_edges: int = Field(default=128, ge=1, le=2_048)
    append_completed_nets_as_obstacles: bool = True
    allow_existing_wires: bool = False
    include_ground_nets: bool = False
    include_power_nets: bool = True
    wire_planner: SchematicWirePlannerConfig = Field(
        default_factory=SchematicWirePlannerConfig
    )


class SchematicJointRouteMetrics(StrictModel):
    routed_edge_count: int = Field(ge=0)
    accepted_route_count: int = Field(ge=0)
    rejected_route_count: int = Field(ge=0)
    skipped_net_group_count: int = Field(ge=0)
    exact_pin_endpoint_count: int = Field(ge=0)
    fallback_anchor_endpoint_count: int = Field(ge=0)
    obstacle_hits: int = Field(ge=0)
    overlaps: int = Field(ge=0)
    crossings: int = Field(ge=0)
    self_intersections: int = Field(ge=0)
    diagonals: int = Field(ge=0)
    bends: int = Field(ge=0)
    length_mm: float = Field(ge=0.0)
    detour_excess: float = Field(ge=0.0)
    rank_key: list[float] = Field(min_length=8, max_length=8)


class SchematicJointRouteEdge(StrictModel):
    net_id: str
    net_name: str = ""
    sheet: int = Field(ge=0)
    start_pin_id: str
    end_pin_id: str
    start_geometry_source: EndpointGeometrySource
    end_geometry_source: EndpointGeometrySource
    plan: SchematicWirePlan


class SchematicPlacementRouteScore(StrictModel):
    candidate_id: str
    placement_total_score: float = Field(ge=0.0)
    metrics: SchematicJointRouteMetrics
    edges: list[SchematicJointRouteEdge] = Field(default_factory=list)
    joint_rank_key: list[float] = Field(min_length=10, max_length=10)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _VirtualEndpoint:
    pin: ObjectRecord
    part: ObjectRecord
    pin_index: int
    point: Point
    source: EndpointGeometrySource


def _pin_index(pin: ObjectRecord) -> int | None:
    raw = pin.xml_id or ""
    _, separator, suffix = raw.rpartition(":")
    if not separator:
        return None
    try:
        value = int(suffix)
    except ValueError:
        return None
    return value if value >= 0 else None


def _sheet(part: ObjectRecord) -> int | None:
    raw = str(part.attributes.get("sheet", "0"))
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _translate_bbox(box: dict[str, float], dx: float, dy: float) -> dict[str, float]:
    bbox = BBox(**box)
    return BBox(
        bbox.min_x + dx,
        bbox.min_y + dy,
        bbox.max_x + dx,
        bbox.max_y + dy,
    ).as_dict()


def _virtualize_snapshot(
    snapshot: DocumentSnapshot,
    placements: dict[str, dict[str, float]],
) -> tuple[DocumentSnapshot, list[str]]:
    virtual = copy.deepcopy(snapshot)
    warnings: list[str] = []
    if virtual.schematic is None:
        return virtual, ["Snapshot has no schematic model."]
    parts = {part.stable_id: part for part in virtual.schematic.parts}
    for part_id, raw_target in sorted(placements.items()):
        part = parts.get(part_id)
        if part is None:
            warnings.append(f"Placement references missing part {part_id}.")
            continue
        target = Point(float(raw_target["x"]), float(raw_target["y"]))
        previous = Point(**part.position) if part.position is not None else None
        if previous is not None and part.bbox is not None:
            part.bbox = _translate_bbox(
                part.bbox,
                target.x - previous.x,
                target.y - previous.y,
            )
        elif previous is None and part.bbox is not None:
            warnings.append(
                f"Part {part_id} has a bounding box but no source position; its virtual "
                "obstacle could not be translated."
            )
        part.position = target.as_dict()
        object_record = virtual.objects.get(part_id)
        if object_record is not None and object_record is not part:
            object_record.position = dict(part.position)
            object_record.bbox = dict(part.bbox) if part.bbox is not None else None
    return virtual, warnings


def _resolution_source(
    geometry: ResolvedSchematicPinGeometry,
    resolution: SchematicPinGeometryResolution,
) -> EndpointGeometrySource:
    if resolution.library_source == "embedded_design_cache":
        return "embedded_pin"
    if resolution.library_source == "external_fallback":
        return "external_pin"
    return "provided_pin"


def _endpoint_point(
    pin: ObjectRecord,
    part: ObjectRecord,
    original_part: ObjectRecord,
    resolved: ResolvedSchematicPinGeometry | None,
    resolution: SchematicPinGeometryResolution,
) -> tuple[Point | None, EndpointGeometrySource]:
    if part.position is None:
        return None, "fallback_part_anchor"
    candidate_center = Point(**part.position)
    if (
        resolved is not None
        and resolved.absolute_position is not None
        and original_part.position is not None
    ):
        original_center = Point(**original_part.position)
        original_pin = Point(**resolved.absolute_position)
        return (
            Point(
                candidate_center.x + original_pin.x - original_center.x,
                candidate_center.y + original_pin.y - original_center.y,
            ),
            _resolution_source(resolved, resolution),
        )
    return candidate_center, "fallback_part_anchor"


def _virtual_endpoints(
    original: DocumentSnapshot,
    virtual: DocumentSnapshot,
    resolution: SchematicPinGeometryResolution,
) -> tuple[dict[tuple[str, int], list[_VirtualEndpoint]], list[str]]:
    assert original.schematic is not None
    assert virtual.schematic is not None
    original_parts = {part.stable_id: part for part in original.schematic.parts}
    virtual_parts = {part.stable_id: part for part in virtual.schematic.parts}
    resolved_by_pin = {item.pin_id: item for item in resolution.pins}
    groups: dict[tuple[str, int], list[_VirtualEndpoint]] = defaultdict(list)
    warnings: list[str] = []
    for pin in sorted(virtual.schematic.pins, key=lambda item: item.stable_id):
        if pin.net_id is None or pin.parent_id is None:
            continue
        pin_index = _pin_index(pin)
        original_part = original_parts.get(pin.parent_id)
        part = virtual_parts.get(pin.parent_id)
        if pin_index is None or original_part is None or part is None:
            warnings.append(f"Pin {pin.stable_id} could not be mapped to a virtual endpoint.")
            continue
        sheet = _sheet(part)
        if sheet is None:
            warnings.append(f"Part {part.stable_id} has an invalid schematic sheet index.")
            continue
        point, source = _endpoint_point(
            pin,
            part,
            original_part,
            resolved_by_pin.get(pin.stable_id),
            resolution,
        )
        if point is None:
            warnings.append(f"Pin {pin.stable_id} has no usable virtual coordinate.")
            continue
        groups[(pin.net_id, sheet)].append(
            _VirtualEndpoint(
                pin=pin,
                part=part,
                pin_index=pin_index,
                point=point,
                source=source,
            )
        )
    return groups, warnings


def _mst_endpoint_edges(
    endpoints: list[_VirtualEndpoint],
) -> list[tuple[_VirtualEndpoint, _VirtualEndpoint]]:
    ordered = sorted(endpoints, key=lambda item: item.pin.stable_id)
    if len(ordered) < 2:
        return []
    by_id = {item.pin.stable_id: item for item in ordered}
    remaining = set(by_id)
    first_id = min(remaining)
    remaining.remove(first_id)
    connected = {first_id}
    edges: list[tuple[_VirtualEndpoint, _VirtualEndpoint]] = []
    while remaining:
        first_pin_id, second_pin_id = min(
            (
                (connected_id, remaining_id)
                for connected_id in sorted(connected)
                for remaining_id in sorted(remaining)
            ),
            key=lambda pair: (
                distance(by_id[pair[0]].point, by_id[pair[1]].point),
                pair[0],
                pair[1],
            ),
        )
        edges.append((by_id[first_pin_id], by_id[second_pin_id]))
        connected.add(second_pin_id)
        remaining.remove(second_pin_id)
    return edges


def _initial_points(start: Point, end: Point) -> list[WirePathPoint]:
    if math.isclose(start.x, end.x, abs_tol=_EPS) or math.isclose(
        start.y, end.y, abs_tol=_EPS
    ):
        return [WirePathPoint(x=start.x, y=start.y), WirePathPoint(x=end.x, y=end.y)]
    return [
        WirePathPoint(x=start.x, y=start.y),
        WirePathPoint(x=end.x, y=start.y),
        WirePathPoint(x=end.x, y=end.y),
    ]


def _net_names(snapshot: DocumentSnapshot) -> dict[str, str]:
    assert snapshot.schematic is not None
    result: dict[str, str] = {}
    for net in snapshot.schematic.nets:
        key = net.net_id or net.xml_id
        if key is not None:
            result[key] = net.net_name or net.name or net.label or ""
    return result


def _net_roles(snapshot: DocumentSnapshot) -> dict[str, NetRole]:
    assert snapshot.schematic is not None
    intent = infer_schematic_design_intent(snapshot)
    by_stable_id = {item.net_id: item.role for item in intent.nets}
    result: dict[str, NetRole] = {}
    for net in snapshot.schematic.nets:
        key = net.net_id or net.xml_id
        role = by_stable_id.get(net.stable_id)
        if key is not None and role is not None:
            result[key] = role
    return result


def _append_completed_net_routes(
    snapshot: DocumentSnapshot,
    edge_plans: list[tuple[str, int, SchematicWirePlan]],
) -> None:
    if snapshot.schematic is None:
        return
    for index, (net_id, sheet, plan) in enumerate(edge_plans):
        operation = plan.selected.operation
        stable = stable_id(
            "wire",
            "virtual-schematic-route",
            net_id,
            str(sheet),
            str(len(snapshot.schematic.wires)),
            str(index),
            operation.net,
        )
        record = ObjectRecord(
            stable_id=stable,
            kind="wire",
            label=f"virtual {operation.net} route",
            net_id=net_id,
            net_name=operation.net,
            attributes={
                "sheet": str(sheet),
                "points": [point.model_dump(mode="json") for point in operation.points],
            },
            relationships={"net": []},
            geometry_source="virtual-route-candidate",
            confidence=0.8,
        )
        snapshot.schematic.wires.append(record)
        snapshot.objects[stable] = record


def _route_rank_key(
    *,
    rejected: int,
    obstacle_hits: int,
    overlaps: int,
    crossings: int,
    self_intersections: int,
    diagonals: int,
    bends: int,
    length_mm: float,
) -> list[float]:
    return [
        float(rejected),
        float(obstacle_hits),
        float(overlaps),
        float(crossings),
        float(self_intersections),
        float(diagonals),
        float(bends),
        length_mm,
    ]


def score_schematic_placement_candidate_routes(
    document: DipTraceDocument,
    candidate: SchematicPlacementCandidate,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicJointRouteConfig | None = None,
) -> SchematicPlacementRouteScore:
    """Score one placement candidate with bounded pin-aware wire candidates.

    This function never writes XML. It clones the normalized snapshot, translates part
    positions/bounds to the candidate placement, derives virtual pin endpoints, and asks the
    existing wire planner to score deterministic MST connections on each included sheet-local
    net. Completed nets may be added only to the cloned snapshot so later nets see crossing
    pressure from already selected candidates.
    """
    config = config or SchematicJointRouteConfig()
    original = build_snapshot(document)
    if original.schematic is None:
        raise CapabilityUnavailableError("Joint schematic route scoring requires a schematic")
    if original.schematic.wires and not config.allow_existing_wires:
        raise CapabilityUnavailableError(
            "Joint placement route scoring currently requires an unwired schematic"
        )
    pin_geometry = pin_geometry or resolve_document_schematic_pin_geometry(document)
    virtual, warnings = _virtualize_snapshot(original, candidate.placements)
    groups, endpoint_warnings = _virtual_endpoints(original, virtual, pin_geometry)
    warnings.extend(endpoint_warnings)
    net_names = _net_names(original)
    net_roles = _net_roles(original)

    route_groups: list[
        tuple[tuple[str, int], list[tuple[_VirtualEndpoint, _VirtualEndpoint]]]
    ] = []
    skipped_net_groups = 0
    for key, endpoints in sorted(groups.items(), key=lambda item: item[0]):
        net_id, _sheet_index = key
        role = net_roles.get(net_id, "unknown")
        if role == "ground" and not config.include_ground_nets:
            skipped_net_groups += 1
            continue
        if role == "power" and not config.include_power_nets:
            skipped_net_groups += 1
            continue
        route_groups.append((key, _mst_endpoint_edges(endpoints)))
    planned_edge_total = sum(len(edges) for _key, edges in route_groups)
    if skipped_net_groups:
        warnings.append(
            f"Skipped {skipped_net_groups} sheet-local net group(s) by configured "
            "ground/power routing policy."
        )

    edge_results: list[SchematicJointRouteEdge] = []
    exact_endpoints = 0
    fallback_endpoints = 0
    accepted = 0
    rejected = 0
    obstacle_hits = 0
    overlaps = 0
    crossings = 0
    self_intersections = 0
    diagonals = 0
    bends = 0
    length_mm = 0.0
    detour_excess = 0.0
    edge_budget = config.max_edges

    for (net_id, sheet), endpoint_edges in route_groups:
        net_edge_plans: list[tuple[str, int, SchematicWirePlan]] = []
        for start, end in endpoint_edges:
            if edge_budget <= 0:
                break
            edge_budget -= 1
            net_name = net_names.get(net_id, net_id)
            operation = AddWireOperation(
                net=net_name,
                sheet=sheet,
                points=_initial_points(start.point, end.point),
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
                document,
                virtual,
                operation,
                config=config.wire_planner,
            )
            wire_metrics = plan.selected.metrics
            edge_results.append(
                SchematicJointRouteEdge(
                    net_id=net_id,
                    net_name=net_name,
                    sheet=sheet,
                    start_pin_id=start.pin.stable_id,
                    end_pin_id=end.pin.stable_id,
                    start_geometry_source=start.source,
                    end_geometry_source=end.source,
                    plan=plan,
                )
            )
            for source in (start.source, end.source):
                if source == "fallback_part_anchor":
                    fallback_endpoints += 1
                else:
                    exact_endpoints += 1
            accepted += int(plan.accept_route)
            rejected += int(not plan.accept_route)
            obstacle_hits += wire_metrics.obstacle_hits
            overlaps += wire_metrics.overlaps
            crossings += wire_metrics.crossings
            self_intersections += wire_metrics.self_intersections
            diagonals += wire_metrics.diagonals
            bends += wire_metrics.bends
            length_mm += wire_metrics.length_mm
            detour_excess += max(0.0, wire_metrics.detour_ratio - 1.0)
            net_edge_plans.append((net_id, sheet, plan))
        if config.append_completed_nets_as_obstacles:
            _append_completed_net_routes(virtual, net_edge_plans)
        if edge_budget <= 0:
            break

    if len(edge_results) < planned_edge_total:
        warnings.append(
            f"Route scoring stopped at max_edges={config.max_edges}; remaining "
            "connections were not evaluated."
        )

    rank_key = _route_rank_key(
        rejected=rejected,
        obstacle_hits=obstacle_hits,
        overlaps=overlaps,
        crossings=crossings,
        self_intersections=self_intersections,
        diagonals=diagonals,
        bends=bends,
        length_mm=length_mm,
    )
    joint_metrics = SchematicJointRouteMetrics(
        routed_edge_count=len(edge_results),
        accepted_route_count=accepted,
        rejected_route_count=rejected,
        skipped_net_group_count=skipped_net_groups,
        exact_pin_endpoint_count=exact_endpoints,
        fallback_anchor_endpoint_count=fallback_endpoints,
        obstacle_hits=obstacle_hits,
        overlaps=overlaps,
        crossings=crossings,
        self_intersections=self_intersections,
        diagonals=diagonals,
        bends=bends,
        length_mm=length_mm,
        detour_excess=detour_excess,
        rank_key=rank_key,
    )
    joint_rank_key = [
        *rank_key[:6],
        candidate.total_score,
        rank_key[6],
        rank_key[7],
        float(fallback_endpoints),
    ]
    return SchematicPlacementRouteScore(
        candidate_id=candidate.candidate_id,
        placement_total_score=candidate.total_score,
        metrics=joint_metrics,
        edges=edge_results,
        joint_rank_key=joint_rank_key,
        assumptions=[
            "Candidate movement is simulated in a deep-copied normalized snapshot only.",
            "Resolved pin offsets are translated with the part; part rotation is preserved.",
            "Each included sheet-local net is decomposed into deterministic endpoint MST edges.",
            "Ground nets are excluded from wire-MST scoring by default; power nets are "
            "included unless configured otherwise.",
            "Completed prior nets may be exposed as virtual wire obstacles to later nets.",
            "Hard route-quality terms are ranked before the existing placement score.",
        ],
        warnings=sorted(set(warnings + pin_geometry.warnings)),
        limitations=[
            "Unresolved pin geometry falls back explicitly to the candidate part anchor.",
            "Same-net MST edges are planned independently before that net is added as a "
            "virtual obstacle, so same-net junction topology is not globally optimized.",
            "Text obstacles still come from the source document and are not repositioned.",
            "Net-role policy controls wire scoring only; it does not author power symbols "
            "or net labels.",
            "This layer scores candidates only; it does not apply placement or wire edits.",
        ],
    )


def rank_schematic_placement_candidates_with_routes(
    document: DipTraceDocument,
    candidates: list[SchematicPlacementCandidate],
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicJointRouteConfig | None = None,
) -> list[SchematicPlacementRouteScore]:
    """Return placement candidates re-ranked by bounded real route evidence."""
    if not candidates:
        return []
    pin_geometry = pin_geometry or resolve_document_schematic_pin_geometry(document)
    scores = [
        score_schematic_placement_candidate_routes(
            document,
            candidate,
            pin_geometry=pin_geometry,
            config=config,
        )
        for candidate in candidates
    ]
    return sorted(
        scores,
        key=lambda item: (tuple(item.joint_rank_key), item.candidate_id),
    )
