from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, field_validator

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, QuerySelector, StrictModel
from .errors import (
    CapabilityUnavailableError,
    LockedObjectError,
    ObjectNotFoundError,
    PlacementError,
    ScopeRequiredError,
)
from .geometry import BBox, Point, distance, point_in_polygon
from .operations import (
    MoveComponentsOperation,
    RotateComponentsOperation,
    SemanticOperation,
    SetComponentSideOperation,
)

Side = Literal["Top", "Bottom"]


class PlacementWeights(StrictModel):
    overlap: float = Field(default=1_000_000.0, ge=0.0)
    containment: float = Field(default=1_000_000.0, ge=0.0)
    keepout: float = Field(default=1_000_000.0, ge=0.0)
    wirelength: float = Field(default=1.0, ge=0.0)
    movement: float = Field(default=0.25, ge=0.0)
    rotation: float = Field(default=0.01, ge=0.0)
    side_change: float = Field(default=5.0, ge=0.0)


class PlacementConfig(StrictModel):
    selector: QuerySelector = Field(default_factory=QuerySelector)
    region: dict[str, float] | None = None
    allowed_sides: list[Literal["Top", "Bottom"]] = Field(default_factory=list)
    allowed_rotations: list[float] = Field(default_factory=list, max_length=16)
    grid: float = Field(default=0.5, gt=0.0, le=100.0)
    search_steps: int = Field(default=8, ge=1, le=100)
    max_candidates_per_component: int = Field(default=256, ge=1, le=512)
    spacing: float = Field(default=0.2, ge=0.0, le=100.0)
    board_edge_clearance: float = Field(default=0.5, ge=0.0, le=100.0)
    deterministic_seed: int = 0
    time_budget_ms: int = Field(default=5_000, ge=100, le=30_000)
    respect_keepouts: bool = True
    weights: PlacementWeights = Field(default_factory=PlacementWeights)

    @field_validator("region")
    @classmethod
    def validate_region(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        return ObjectRecord.validate_bbox(value)

    @field_validator("allowed_rotations")
    @classmethod
    def normalize_rotations(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("allowed rotations must be finite")
        return sorted({value % 360.0 for value in values})


@dataclass(frozen=True, slots=True)
class PlacementPlanningResult:
    operations: list[SemanticOperation]
    changed_ids: list[str]
    unresolved: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    score: dict[str, float]
    metrics: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


class PlacementProposal(StrictModel):
    object_id: str
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    side: Side | None = None
    rotation_deg: float | None = Field(default=None, allow_inf_nan=False)


@dataclass(frozen=True, slots=True)
class _Placed:
    object_id: str
    side: Side
    position: Point
    rotation_deg: float
    bbox: BBox


def analyze_placement(
    snapshot: DocumentSnapshot,
    selector: QuerySelector | None = None,
    *,
    spacing: float = 0.2,
    board_edge_clearance: float = 0.5,
) -> dict[str, Any]:
    config = PlacementConfig(
        selector=selector or QuerySelector(),
        spacing=spacing,
        board_edge_clearance=board_edge_clearance,
    )
    all_records = _components(snapshot)
    records = all_records
    if selector is not None and not selector.is_empty():
        selected_ids = {
            item.stable_id for item in snapshot.select(selector, kinds={"component"})
        }
        records = [item for item in records if item.stable_id in selected_ids]
    placements = {item.stable_id: _current_placement(item) for item in all_records}
    score, violations = score_placements(snapshot, placements, config)
    return {
        "component_count": len(records),
        "score": score,
        "violations": violations,
        "locked_count": sum(item.locked for item in records),
        "geometry_confidence": min((item.confidence for item in records), default=1.0),
    }


def generate_placement_candidates(
    snapshot: DocumentSnapshot,
    config: PlacementConfig,
) -> list[dict[str, Any]]:
    targets = _select_targets(snapshot, config)
    occupied = [
        _current_placement(item)
        for item in _components(snapshot)
        if item.stable_id not in {target.stable_id for target in targets}
    ]
    return [
        {
            "object_id": target.stable_id,
            "candidates": _evaluate_candidates(snapshot, target, occupied, config),
        }
        for target in targets
    ]


def plan_component_placement(
    snapshot: DocumentSnapshot,
    config: PlacementConfig,
) -> PlacementPlanningResult:
    started = time.monotonic()
    deadline = started + config.time_budget_ms / 1_000.0
    targets = _select_targets(snapshot, config)
    target_ids = {item.stable_id for item in targets}
    occupied = [
        _current_placement(item)
        for item in _components(snapshot)
        if item.stable_id not in target_ids
    ]
    placements = {
        item.stable_id: _current_placement(item) for item in _components(snapshot)
    }
    operations: list[SemanticOperation] = []
    changed_ids: list[str] = []
    unresolved: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []

    ordered_targets = sorted(targets, key=lambda item: item.stable_id)
    budget_exhausted = False
    for target_index, target in enumerate(ordered_targets):
        if time.monotonic() >= deadline:
            budget_exhausted = True
            unresolved.extend(
                {
                    "object_id": pending.stable_id,
                    "reason": "time_budget_exhausted",
                }
                for pending in ordered_targets[target_index:]
            )
            break
        current = _current_placement(target)
        if target.locked:
            legal, reasons = _static_legality(snapshot, current, config)
            for obstacle in occupied:
                if obstacle.side == current.side and current.bbox.overlap_area(
                    obstacle.bbox.expand(config.spacing)
                ) > 0:
                    legal = False
                    reasons.append(f"component_spacing:{obstacle.object_id}")
            if not legal:
                unresolved.append(
                    {
                        "object_id": target.stable_id,
                        "reason": "locked_component_illegal",
                        "details": reasons,
                    }
                )
            occupied.append(current)
            candidate_results.append(
                {
                    "object_id": target.stable_id,
                    "status": "locked_unchanged",
                    "legal": legal,
                    "reasons": reasons,
                }
            )
            continue
        evaluated = _evaluate_candidates(snapshot, target, occupied, config)
        legal_candidates = [candidate for candidate in evaluated if candidate["legal"]]
        if not legal_candidates:
            occupied.append(current)
            unresolved.append(
                {
                    "object_id": target.stable_id,
                    "reason": "no_legal_candidate",
                    "candidate_count": len(evaluated),
                }
            )
            candidate_results.append(
                {
                    "object_id": target.stable_id,
                    "status": "unresolved",
                    "evaluated": evaluated,
                }
            )
            continue
        chosen = min(
            legal_candidates,
            key=lambda item: (
                item["score"]["total"],
                item["position"]["x"],
                item["position"]["y"],
                item["side"],
                item["rotation_deg"],
            ),
        )
        placed = _placed_from_candidate(target.stable_id, chosen)
        occupied.append(placed)
        placements[target.stable_id] = placed
        changed = _placement_changed(current, placed)
        candidate_results.append(
            {
                "object_id": target.stable_id,
                "status": "move" if changed else "keep",
                "chosen": chosen,
                "evaluated_count": len(evaluated),
            }
        )
        if not changed:
            continue
        selector = QuerySelector(ids=[target.stable_id])
        if placed.side != current.side:
            operations.append(SetComponentSideOperation(selector=selector, side=placed.side))
        if not math.isclose(placed.rotation_deg, current.rotation_deg, abs_tol=1e-9):
            operations.append(
                RotateComponentsOperation(
                    selector=selector,
                    angle_deg=placed.rotation_deg,
                    mode="absolute",
                )
            )
        if placed.position != current.position:
            operations.append(
                MoveComponentsOperation(
                    selector=selector,
                    absolute_x=placed.position.x,
                    absolute_y=placed.position.y,
                )
            )
        changed_ids.append(target.stable_id)

    score, violations = score_placements(snapshot, placements, config)
    return PlacementPlanningResult(
        operations=operations,
        changed_ids=changed_ids,
        unresolved=unresolved,
        candidates=candidate_results,
        score=score,
        metrics={
            "target_count": len(targets),
            "changed_count": len(changed_ids),
            "locked_count": sum(item.locked for item in targets),
            "unresolved_count": len(unresolved),
            "remaining_violation_count": len(violations),
            "remaining_violations": violations,
            "elapsed_ms": (time.monotonic() - started) * 1_000.0,
            "time_budget_exhausted": budget_exhausted,
        },
        assumptions=[
            "This is a deterministic incremental greedy placer, not a global optimizer.",
            "All geometry and score distances use normalized millimetres.",
            "Ratsnest cost uses component anchors because exact pad geometry is incomplete.",
        ],
        warnings=[],
        limitations=[
            "Component bounds are estimated when body/courtyard geometry is absent.",
            "Thermal, functional-block, decoupling and assembly-access terms are not yet scored.",
        ],
    )


def score_placements(
    snapshot: DocumentSnapshot,
    placements: dict[str, _Placed],
    config: PlacementConfig,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    overlap_area = 0.0
    containment_count = 0
    keepout_area = 0.0
    placed = sorted(placements.values(), key=lambda item: item.object_id)
    for index, item in enumerate(placed):
        legal, reasons = _static_legality(snapshot, item, config)
        if not legal:
            for reason in reasons:
                violations.append({"object_id": item.object_id, "reason": reason})
                if reason.startswith("containment") or reason == "board_outline_missing":
                    containment_count += 1
                elif reason.startswith("keepout"):
                    keepout_area += item.bbox.area
        for other in placed[index + 1 :]:
            if item.side != other.side:
                continue
            area = item.bbox.overlap_area(other.bbox.expand(config.spacing))
            if area > 0:
                overlap_area += area
                violations.append(
                    {
                        "object_ids": [item.object_id, other.object_id],
                        "reason": "component_spacing",
                        "overlap_area_mm2": area,
                    }
                )
    wirelength = _ratsnest_wirelength(snapshot, placements)
    movement = 0.0
    rotation = 0.0
    side_changes = 0.0
    by_id = {item.stable_id: item for item in _components(snapshot)}
    for object_id, placement in placements.items():
        original = by_id.get(object_id)
        if original is None or original.position is None:
            continue
        movement += distance(Point(**original.position), placement.position)
        rotation += _angle_delta(original.rotation_deg, placement.rotation_deg)
        side_changes += float((original.side or "Top") != placement.side)
    contributions = {
        "overlap": overlap_area * config.weights.overlap,
        "containment": containment_count * config.weights.containment,
        "keepout": keepout_area * config.weights.keepout,
        "wirelength": wirelength * config.weights.wirelength,
        "movement": movement * config.weights.movement,
        "rotation": rotation * config.weights.rotation,
        "side_change": side_changes * config.weights.side_change,
    }
    return {
        **contributions,
        "total": sum(contributions.values()),
        "raw_overlap_area_mm2": overlap_area,
        "raw_wirelength_mm": wirelength,
        "raw_movement_mm": movement,
    }, violations


def score_placement_proposal(
    snapshot: DocumentSnapshot,
    proposals: list[PlacementProposal],
    config: PlacementConfig,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    records = {item.stable_id: item for item in _components(snapshot)}
    placements = {
        object_id: _current_placement(record) for object_id, record in records.items()
    }
    for proposal in proposals:
        try:
            record = records[proposal.object_id]
        except KeyError as exc:
            raise ObjectNotFoundError(
                f"Placement object was not found: {proposal.object_id}",
                object_ids=[proposal.object_id],
            ) from exc
        current = placements[proposal.object_id]
        point = Point(proposal.x, proposal.y)
        side = proposal.side or current.side
        rotation = (
            proposal.rotation_deg % 360.0
            if proposal.rotation_deg is not None
            else current.rotation_deg
        )
        candidate = _Placed(
            proposal.object_id,
            side,
            point,
            rotation,
            _transformed_bbox(current, point, rotation),
        )
        if record.locked and _placement_changed(current, candidate):
            raise LockedObjectError(
                f"Placement proposal moves locked component: {record.label}",
                object_ids=[record.stable_id],
            )
        placements[proposal.object_id] = candidate
    return score_placements(snapshot, placements, config)


def _components(snapshot: DocumentSnapshot) -> list[ObjectRecord]:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Placement requires a PCB document")
    return [
        item
        for item in snapshot.board.components
        if item.position is not None and item.bbox is not None
    ]


def _select_targets(
    snapshot: DocumentSnapshot,
    config: PlacementConfig,
) -> list[ObjectRecord]:
    if config.selector.is_empty():
        raise ScopeRequiredError("Placement planning requires an explicit component selector")
    targets = snapshot.select(config.selector, kinds={"component"})
    targets = [item for item in targets if item.position is not None and item.bbox is not None]
    if len(targets) > 50:
        raise PlacementError(
            "Incremental placement is limited to 50 components per plan",
            details={"matched_count": len(targets), "limit": 50},
            object_ids=[item.stable_id for item in targets[:50]],
        )
    return targets


def _current_placement(record: ObjectRecord) -> _Placed:
    if record.position is None or record.bbox is None:
        raise ValueError(f"Component has incomplete placement geometry: {record.stable_id}")
    return _Placed(
        object_id=record.stable_id,
        side="Bottom" if record.side == "Bottom" else "Top",
        position=Point(**record.position),
        rotation_deg=record.rotation_deg % 360.0,
        bbox=BBox(**record.bbox),
    )


def _candidate_positions(current: Point, config: PlacementConfig) -> list[Point]:
    offsets = [(0, 0)]
    for radius in range(1, config.search_steps + 1):
        for dx in range(-radius, radius + 1):
            offsets.append((dx, -radius))
            offsets.append((dx, radius))
        for dy in range(-radius + 1, radius):
            offsets.append((-radius, dy))
            offsets.append((radius, dy))
    points: list[Point] = []
    seen: set[tuple[float, float]] = set()
    for dx, dy in offsets:
        point = Point(
            round((current.x + dx * config.grid) / config.grid) * config.grid,
            round((current.y + dy * config.grid) / config.grid) * config.grid,
        )
        key = (round(point.x, 9), round(point.y, 9))
        if key not in seen:
            seen.add(key)
            points.append(point)
        if len(points) >= config.max_candidates_per_component:
            break
    return points


def _evaluate_candidates(
    snapshot: DocumentSnapshot,
    target: ObjectRecord,
    occupied: list[_Placed],
    config: PlacementConfig,
) -> list[dict[str, Any]]:
    current = _current_placement(target)
    sides: list[Side] = config.allowed_sides or [current.side]
    rotations = config.allowed_rotations or [current.rotation_deg]
    evaluated: list[dict[str, Any]] = []
    for point in _candidate_positions(current.position, config):
        for side in sides:
            for rotation in rotations:
                box = _transformed_bbox(current, point, rotation)
                candidate = _Placed(target.stable_id, side, point, rotation, box)
                legal, reasons = _static_legality(snapshot, candidate, config)
                overlap_area = 0.0
                for obstacle in occupied:
                    if obstacle.side != side:
                        continue
                    overlap_area += box.overlap_area(obstacle.bbox.expand(config.spacing))
                if overlap_area > 0:
                    reasons.append("component_spacing")
                    legal = False
                raw_wirelength = _candidate_wirelength(snapshot, target, point)
                containment_count = sum(
                    reason.startswith("containment") or reason == "board_outline_missing"
                    for reason in reasons
                )
                keepout_count = sum(reason.startswith("keepout") for reason in reasons)
                score = {
                    "overlap": overlap_area * config.weights.overlap,
                    "containment": containment_count * config.weights.containment,
                    "keepout": keepout_count * config.weights.keepout,
                    "wirelength": raw_wirelength * config.weights.wirelength,
                    "movement": distance(current.position, point) * config.weights.movement,
                    "rotation": _angle_delta(current.rotation_deg, rotation)
                    * config.weights.rotation,
                    "side_change": float(current.side != side) * config.weights.side_change,
                }
                score["total"] = sum(score.values())
                evaluated.append(
                    {
                        "position": point.as_dict(),
                        "side": side,
                        "rotation_deg": rotation,
                        "bbox": box.as_dict(),
                        "legal": legal,
                        "reasons": reasons,
                        "score": score,
                    }
                )
    return evaluated


def _transformed_bbox(current: _Placed, point: Point, rotation: float) -> BBox:
    radians = math.radians(rotation - current.rotation_deg)
    width = abs(current.bbox.width * math.cos(radians)) + abs(
        current.bbox.height * math.sin(radians)
    )
    height = abs(current.bbox.width * math.sin(radians)) + abs(
        current.bbox.height * math.cos(radians)
    )
    return BBox(
        point.x - width / 2.0,
        point.y - height / 2.0,
        point.x + width / 2.0,
        point.y + height / 2.0,
    )


def _static_legality(
    snapshot: DocumentSnapshot,
    candidate: _Placed,
    config: PlacementConfig,
) -> tuple[bool, list[str]]:
    assert snapshot.board is not None
    reasons: list[str] = []
    expanded = candidate.bbox.expand(config.board_edge_clearance)
    if config.region is not None and not BBox(**config.region).contains_bbox(expanded):
        reasons.append("containment:requested_region")
    outline = snapshot.board.outline
    if outline is None:
        reasons.append("board_outline_missing")
    else:
        polygon = [Point(**item) for item in outline.get("points", [])]
        corners = (
            Point(expanded.min_x, expanded.min_y),
            Point(expanded.min_x, expanded.max_y),
            Point(expanded.max_x, expanded.min_y),
            Point(expanded.max_x, expanded.max_y),
        )
        if not all(point_in_polygon(point, polygon) for point in corners):
            reasons.append("containment:board_outline")
    if config.respect_keepouts:
        for keepout in snapshot.board.keepouts:
            if keepout.bbox is None:
                continue
            if candidate.bbox.overlap_area(BBox(**keepout.bbox)) > 0:
                reasons.append(f"keepout:{keepout.stable_id}")
    return not reasons, reasons


def _ratsnest_wirelength(
    snapshot: DocumentSnapshot,
    placements: dict[str, _Placed],
) -> float:
    assert snapshot.board is not None
    by_xml_id = {
        item.xml_id: placements.get(item.stable_id, _current_placement(item))
        for item in _components(snapshot)
        if item.xml_id is not None
    }
    total = 0.0
    for ratline in snapshot.board.ratlines:
        attributes = ratline.get("attributes", {})
        first = by_xml_id.get(attributes.get("Comp1"))
        second = by_xml_id.get(attributes.get("Comp2"))
        if first is not None and second is not None:
            total += distance(first.position, second.position)
    return total


def _candidate_wirelength(
    snapshot: DocumentSnapshot,
    target: ObjectRecord,
    point: Point,
) -> float:
    assert snapshot.board is not None
    by_xml_id = {item.xml_id: item for item in _components(snapshot) if item.xml_id is not None}
    total = 0.0
    for ratline in snapshot.board.ratlines:
        attributes = ratline.get("attributes", {})
        if target.xml_id not in {attributes.get("Comp1"), attributes.get("Comp2")}:
            continue
        other_xml_id = (
            attributes.get("Comp2")
            if attributes.get("Comp1") == target.xml_id
            else attributes.get("Comp1")
        )
        other = by_xml_id.get(other_xml_id)
        if other is not None and other.position is not None:
            total += distance(point, Point(**other.position))
    return total


def _angle_delta(first: float, second: float) -> float:
    return abs((second - first + 180.0) % 360.0 - 180.0)


def _placed_from_candidate(object_id: str, candidate: dict[str, Any]) -> _Placed:
    side: Side = "Bottom" if candidate["side"] == "Bottom" else "Top"
    return _Placed(
        object_id=object_id,
        side=side,
        position=Point(**candidate["position"]),
        rotation_deg=float(candidate["rotation_deg"]),
        bbox=BBox(**candidate["bbox"]),
    )


def _placement_changed(before: _Placed, after: _Placed) -> bool:
    return (
        before.position != after.position
        or before.side != after.side
        or not math.isclose(before.rotation_deg, after.rotation_deg, abs_tol=1e-9)
    )
