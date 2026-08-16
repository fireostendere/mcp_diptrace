from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, QuerySelector, StrictModel
from .errors import CapabilityUnavailableError, PlacementError
from .geometry import BBox, Point, distance
from .operations import MoveComponentsOperation, SemanticOperation
from .pcb_design_intent import PCBDesignIntent, PCBIntentOverrides, build_pcb_design_intent
from .placement import PlacementConfig, PlacementProposal, score_placement_proposal


class PCBPlacementV2Weights(StrictModel):
    geometry: float = Field(default=1.0, ge=0.0)
    block_cohesion: float = Field(default=0.6, ge=0.0)
    support_adjacency: float = Field(default=1.5, ge=0.0)
    critical_connection: float = Field(default=0.8, ge=0.0)
    noise_coupling: float = Field(default=2.0, ge=0.0)
    compactness: float = Field(default=0.02, ge=0.0)
    centering: float = Field(default=1.0, ge=0.0)
    symmetry: float = Field(default=0.5, ge=0.0)
    hot_loop: float = Field(default=1.5, ge=0.0)


class PCBPlacementV2Config(StrictModel):
    grid_mm: float = Field(default=0.5, gt=0.0, le=25.0)
    search_radius_steps: int = Field(default=8, ge=1, le=100)
    max_candidates_per_component: int = Field(default=160, ge=4, le=1_000)
    max_components: int = Field(default=200, ge=1, le=2_000)
    spacing_mm: float = Field(default=0.2, ge=0.0, le=100.0)
    board_edge_clearance_mm: float = Field(default=0.5, ge=0.0, le=100.0)
    weights: PCBPlacementV2Weights = Field(default_factory=PCBPlacementV2Weights)


class PCBPlacementV2Score(StrictModel):
    geometry: float = Field(ge=0.0)
    block_cohesion: float = Field(ge=0.0)
    support_adjacency: float = Field(ge=0.0)
    critical_connection: float = Field(ge=0.0)
    noise_coupling: float = Field(ge=0.0)
    compactness: float = Field(ge=0.0)
    centering: float = Field(ge=0.0)
    symmetry: float = Field(ge=0.0)
    hot_loop: float = Field(ge=0.0)
    total: float = Field(ge=0.0)


class PCBPlacementV2Analysis(StrictModel):
    intent: PCBDesignIntent
    score: PCBPlacementV2Score
    geometry_violations: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PCBPlacementV2Plan:
    operations: list[SemanticOperation]
    proposals: list[PlacementProposal]
    before: PCBPlacementV2Analysis
    after: PCBPlacementV2Analysis
    changed_component_ids: list[str]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


def _require_board(snapshot: DocumentSnapshot) -> None:
    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB placement v2 requires a PCB document")


def _components(snapshot: DocumentSnapshot) -> dict[str, ObjectRecord]:
    assert snapshot.board is not None
    return {
        item.stable_id: item
        for item in snapshot.board.components
        if item.position is not None and item.bbox is not None
    }


def _base_config(config: PCBPlacementV2Config) -> PlacementConfig:
    return PlacementConfig(
        spacing=config.spacing_mm,
        board_edge_clearance=config.board_edge_clearance_mm,
    )


def _positions(
    components: dict[str, ObjectRecord],
    proposals: list[PlacementProposal],
) -> dict[str, Point]:
    by_id = {item.object_id: item for item in proposals}
    result: dict[str, Point] = {}
    for component_id, component in components.items():
        proposal = by_id.get(component_id)
        if proposal is not None:
            result[component_id] = Point(proposal.x, proposal.y)
        elif component.position is not None:
            result[component_id] = Point(**component.position)
    return result


def _electrical_terms(
    intent: PCBDesignIntent,
    positions: dict[str, Point],
) -> dict[str, float]:
    components = {item.component_id: item for item in intent.components}
    block_cohesion = 0.0
    support_adjacency = 0.0
    critical_connection = 0.0
    noise_coupling = 0.0

    for block in intent.blocks:
        anchor = positions.get(block.anchor_component_id)
        if anchor is None:
            continue
        for component_id in block.member_component_ids:
            point = positions.get(component_id)
            if point is not None and component_id != block.anchor_component_id:
                block_cohesion += distance(anchor, point)
        for component_id in block.support_component_ids:
            point = positions.get(component_id)
            component = components.get(component_id)
            if point is not None and component is not None:
                support_adjacency += (
                    distance(anchor, point) * component.placement_priority / 100.0
                )

    for net in intent.nets:
        points = [positions[item] for item in net.component_ids if item in positions]
        if len(points) < 2:
            continue
        center = Point(
            math.fsum(point.x for point in points) / len(points),
            math.fsum(point.y for point in points) / len(points),
        )
        critical_connection += (
            math.fsum(distance(point, center) for point in points)
            * net.criticality
            / 100.0
        )

    ordered = [item for item in intent.components if item.component_id in positions]
    for index, first in enumerate(ordered):
        first_point = positions[first.component_id]
        for second in ordered[index + 1 :]:
            second_point = positions[second.component_id]
            risk = max(
                first.noise_emission * second.noise_sensitivity,
                second.noise_emission * first.noise_sensitivity,
            )
            if risk < 4_900:
                continue
            noise_coupling += (
                risk
                / 10_000.0
                / max(distance(first_point, second_point), 0.5)
            )

    return {
        "block_cohesion": block_cohesion,
        "support_adjacency": support_adjacency,
        "critical_connection": critical_connection,
        "noise_coupling": noise_coupling,
    }


def _layout_terms(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
    components: dict[str, ObjectRecord],
    positions: dict[str, Point],
) -> dict[str, float]:
    assert snapshot.board is not None
    boxes: list[tuple[str, Any]] = []
    for component_id, component in components.items():
        if component.bbox is None or component.position is None or component_id not in positions:
            continue
        original = Point(**component.position)
        target = positions[component_id]
        boxes.append(
            (
                component_id,
                BBox(**component.bbox).translate(
                    target.x - original.x,
                    target.y - original.y,
                ),
            )
        )
    occupied = (
        BBox(
            min(box.min_x for _component_id, box in boxes),
            min(box.min_y for _component_id, box in boxes),
            max(box.max_x for _component_id, box in boxes),
            max(box.max_y for _component_id, box in boxes),
        )
        if boxes
        else None
    )
    outline = snapshot.board.outline
    board_center = (
        BBox(**outline["bbox"]).center
        if outline is not None and outline.get("bbox")
        else occupied.center
        if occupied is not None
        else Point(0.0, 0.0)
    )

    component_intents = {item.component_id: item for item in intent.components}
    symmetry_groups: dict[tuple[str, str, str], list[str]] = {}
    for component_id, component in components.items():
        classified = component_intents.get(component_id)
        if classified is None or component_id not in positions:
            continue
        pattern = str(component.attributes.get("pattern_style") or component.name or "")
        symmetry_groups.setdefault((classified.block_id, classified.role, pattern), []).append(
            component_id
        )
    symmetry = 0.0
    for ids in symmetry_groups.values():
        if len(ids) != 2:
            continue
        first, second = (positions[item] for item in sorted(ids))
        symmetry += min(abs(first.x - second.x), abs(first.y - second.y))

    hot_loop = 0.0
    for net in intent.nets:
        if "switching_node" not in net.roles:
            continue
        points = [positions[item] for item in net.component_ids if item in positions]
        if len(points) >= 2:
            hot_loop += max(distance(first, second) for first in points for second in points)
    return {
        "compactness": occupied.area if occupied is not None else 0.0,
        "centering": distance(occupied.center, board_center) if occupied is not None else 0.0,
        "symmetry": symmetry,
        "hot_loop": hot_loop,
    }


def _score(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
    proposals: list[PlacementProposal],
    config: PCBPlacementV2Config,
) -> tuple[PCBPlacementV2Score, dict[str, float], list[dict[str, Any]]]:
    geometry, violations = score_placement_proposal(
        snapshot,
        proposals,
        _base_config(config),
    )
    components = _components(snapshot)
    positions = _positions(components, proposals)
    electrical = _electrical_terms(intent, positions)
    layout = _layout_terms(snapshot, intent, components, positions)
    weighted = {
        "geometry": geometry["total"] * config.weights.geometry,
        "block_cohesion": (
            electrical["block_cohesion"] * config.weights.block_cohesion
        ),
        "support_adjacency": (
            electrical["support_adjacency"] * config.weights.support_adjacency
        ),
        "critical_connection": (
            electrical["critical_connection"] * config.weights.critical_connection
        ),
        "noise_coupling": (
            electrical["noise_coupling"] * config.weights.noise_coupling
        ),
        "compactness": layout["compactness"] * config.weights.compactness,
        "centering": layout["centering"] * config.weights.centering,
        "symmetry": layout["symmetry"] * config.weights.symmetry,
        "hot_loop": layout["hot_loop"] * config.weights.hot_loop,
    }
    return (
        PCBPlacementV2Score(**weighted, total=math.fsum(weighted.values())),
        geometry,
        violations,
    )


def analyze_pcb_placement_v2(
    snapshot: DocumentSnapshot,
    *,
    intent: PCBDesignIntent | None = None,
    overrides: PCBIntentOverrides | None = None,
    config: PCBPlacementV2Config | None = None,
    proposals: list[PlacementProposal] | None = None,
) -> PCBPlacementV2Analysis:
    _require_board(snapshot)
    config = config or PCBPlacementV2Config()
    intent = intent or build_pcb_design_intent(snapshot, overrides)
    score, _geometry, violations = _score(snapshot, intent, proposals or [], config)
    return PCBPlacementV2Analysis(
        intent=intent,
        score=score,
        geometry_violations=violations,
        assumptions=[
            (
                "Generation A uses deterministic geometry, compactness, symmetry and "
                "electrical-intent proxies, not a field or thermal solver."
            ),
            (
                "Existing placement geometry/DRC legality remains authoritative for "
                "overlap, outline and keepouts."
            ),
        ],
        warnings=list(intent.warnings),
        limitations=[
            "Component movement preserves the existing side and rotation.",
            (
                "Decoupling and power-loop terms are connectivity/proximity proxies "
                "until pad-level current paths are modeled in Generation B."
            ),
            (
                "Noise separation uses intent risk and distance only; coupling "
                "geometry and frequency overlap are deferred to Generation B."
            ),
        ],
    )


def _connected_points(
    component_id: str,
    intent: PCBDesignIntent,
    positions: dict[str, Point],
) -> list[tuple[Point, float]]:
    result: list[tuple[Point, float]] = []
    for net in intent.nets:
        if component_id not in net.component_ids:
            continue
        weight = max(0.1, net.criticality / 100.0)
        for other_id in net.component_ids:
            if other_id != component_id and other_id in positions:
                result.append((positions[other_id], weight))
    return result


def _desired_point(
    component_id: str,
    intent: PCBDesignIntent,
    positions: dict[str, Point],
) -> Point:
    component = next(
        item for item in intent.components if item.component_id == component_id
    )
    if component.anchor_component_id and component.anchor_component_id in positions:
        return positions[component.anchor_component_id]
    connected = _connected_points(component_id, intent, positions)
    if not connected:
        return positions[component_id]
    weight_sum = math.fsum(weight for _point, weight in connected)
    return Point(
        math.fsum(point.x * weight for point, weight in connected) / weight_sum,
        math.fsum(point.y * weight for point, weight in connected) / weight_sum,
    )


def _snap(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _candidate_points(
    current: Point,
    desired: Point,
    config: PCBPlacementV2Config,
) -> list[Point]:
    grid = config.grid_mm
    seeds = [
        current,
        Point(_snap(desired.x, grid), _snap(desired.y, grid)),
        Point(
            _snap((current.x + desired.x) / 2.0, grid),
            _snap((current.y + desired.y) / 2.0, grid),
        ),
    ]
    result: list[Point] = []
    seen: set[tuple[float, float]] = set()

    def add(point: Point) -> None:
        key = (round(point.x, 9), round(point.y, 9))
        if key not in seen and len(result) < config.max_candidates_per_component:
            seen.add(key)
            result.append(point)

    for seed in seeds:
        add(seed)
    center = seeds[1]
    for radius in range(1, config.search_radius_steps + 1):
        for dx in range(-radius, radius + 1):
            add(Point(center.x + dx * grid, center.y - radius * grid))
            add(Point(center.x + dx * grid, center.y + radius * grid))
        for dy in range(-radius + 1, radius):
            add(Point(center.x - radius * grid, center.y + dy * grid))
            add(Point(center.x + radius * grid, center.y + dy * grid))
        if len(result) >= config.max_candidates_per_component:
            break
    return result


def _hard_geometry_score(geometry: dict[str, float]) -> float:
    return geometry["overlap"] + geometry["containment"] + geometry["keepout"]


def plan_pcb_placement_v2(
    snapshot: DocumentSnapshot,
    *,
    overrides: PCBIntentOverrides | None = None,
    config: PCBPlacementV2Config | None = None,
) -> PCBPlacementV2Plan:
    _require_board(snapshot)
    assert snapshot.board is not None
    config = config or PCBPlacementV2Config()
    components = _components(snapshot)
    if len(components) > config.max_components:
        raise PlacementError(
            "PCB placement v2 component count exceeds the deterministic bound",
            details={
                "component_count": len(components),
                "max_components": config.max_components,
            },
            object_ids=sorted(components)[: config.max_components],
        )
    intent = build_pcb_design_intent(snapshot, overrides)
    component_intents = {item.component_id: item for item in intent.components}
    before = analyze_pcb_placement_v2(snapshot, intent=intent, config=config)
    proposals: dict[str, PlacementProposal] = {}

    support_roles = {"support", "power_support", "timing", "protection"}
    movable = [
        component
        for component in components.values()
        if not component.locked
        and not component_intents[component.stable_id].mechanical_anchor
    ]
    movable.sort(
        key=lambda item: (
            component_intents[item.stable_id].role in support_roles,
            -component_intents[item.stable_id].placement_priority,
            item.stable_id,
        )
    )

    for component in movable:
        assert component.position is not None
        current = Point(**component.position)
        existing = list(proposals.values())
        positions = _positions(components, existing)
        desired = _desired_point(component.stable_id, intent, positions)
        current_score, current_geometry, _ = _score(
            snapshot,
            intent,
            existing,
            config,
        )
        current_hard = _hard_geometry_score(current_geometry)
        best_score = current_score
        best: PlacementProposal | None = None

        for point in _candidate_points(current, desired, config):
            candidate = PlacementProposal(
                object_id=component.stable_id,
                x=point.x,
                y=point.y,
            )
            candidate_map = dict(proposals)
            candidate_map[component.stable_id] = candidate
            score, geometry, _violations = _score(
                snapshot,
                intent,
                list(candidate_map.values()),
                config,
            )
            if _hard_geometry_score(geometry) > current_hard + 1e-9:
                continue
            if score.total + 1e-9 < best_score.total:
                best_score = score
                best = candidate

        if best is None:
            continue
        if math.isclose(best.x, current.x, abs_tol=1e-9) and math.isclose(
            best.y,
            current.y,
            abs_tol=1e-9,
        ):
            continue
        proposals[component.stable_id] = best

    proposal_list = [proposals[key] for key in sorted(proposals)]
    after = analyze_pcb_placement_v2(
        snapshot,
        intent=intent,
        config=config,
        proposals=proposal_list,
    )
    if after.score.total > before.score.total + 1e-9:
        raise PlacementError(
            "PCB placement v2 refused a score regression",
            details={"before": before.score.total, "after": after.score.total},
        )

    operations: list[SemanticOperation] = [
        MoveComponentsOperation(
            selector=QuerySelector(ids=[proposal.object_id]),
            absolute_x=proposal.x,
            absolute_y=proposal.y,
        )
        for proposal in proposal_list
    ]
    return PCBPlacementV2Plan(
        operations=operations,
        proposals=proposal_list,
        before=before,
        after=after,
        changed_component_ids=[item.object_id for item in proposal_list],
        assumptions=[
            (
                "Mechanical anchors and locked components are fixed before electrical "
                "placement."
            ),
            (
                "Main functional anchors are considered before their local support "
                "components."
            ),
            (
                "Every candidate is scored against existing placement legality and "
                "may not increase hard geometry penalties."
            ),
        ],
        warnings=list(intent.warnings),
        limitations=list(after.limitations),
    )
