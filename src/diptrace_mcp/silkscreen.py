from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import BBox, Point, distance, point_in_polygon
from .operations import MoveBoardTextsOperation, SemanticOperation


class SilkscreenPlanConfig(StrictModel):
    selector: QuerySelector = Field(default_factory=QuerySelector)
    clearance: float = Field(default=0.2, ge=0.0, le=10.0)
    board_edge_clearance: float = Field(default=0.2, ge=0.0, le=10.0)
    grid: float = Field(default=0.25, gt=0.0, le=10.0)
    search_steps: int = Field(default=4, ge=1, le=20)
    include_board_texts: bool = False
    avoid_component_bodies: bool = False
    movement_weight: float = Field(default=1.0, ge=0.0, le=1_000.0)
    association_weight: float = Field(default=0.25, ge=0.0, le=1_000.0)
    orientation_weight: float = Field(default=2.0, ge=0.0, le=1_000.0)


@dataclass(frozen=True, slots=True)
class SilkscreenPlanningResult:
    operations: list[SemanticOperation]
    changed_ids: list[str]
    unresolved: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    score: dict[str, float]
    metrics: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True, slots=True)
class _Obstacle:
    object_id: str
    side: str | None
    bbox: BBox
    kind: str


def plan_silkscreen(
    snapshot: DocumentSnapshot,
    config: SilkscreenPlanConfig,
) -> SilkscreenPlanningResult:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Silkscreen planning requires a PCB document")
    allowed_kinds = {"component_text"}
    if config.include_board_texts:
        allowed_kinds.add("board_text")
    selected = snapshot.select(config.selector, kinds=allowed_kinds)
    selected = [
        item
        for item in selected
        if "Silk" in (item.layer or "")
        and item.position is not None
        and item.bbox is not None
        and item.attributes.get("Show", "Show") != "Hide"
    ]
    selected_ids = {item.stable_id for item in selected}
    movable = [item for item in selected if not item.locked]
    locked = [item for item in selected if item.locked]

    obstacles = _fixed_obstacles(snapshot, selected_ids, config)
    occupied: list[_Obstacle] = list(obstacles)
    unresolved: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []
    operations: list[SemanticOperation] = []
    changed_ids: list[str] = []
    score_totals = {
        "movement": 0.0,
        "association": 0.0,
        "orientation": 0.0,
        "total": 0.0,
    }

    for item in sorted(locked, key=lambda record: record.stable_id):
        assert item.bbox is not None
        legal, reasons = _candidate_is_legal(
            BBox(**item.bbox),
            item.side,
            [obstacle for obstacle in occupied if obstacle.object_id != item.stable_id],
            snapshot,
            config,
        )
        candidate_results.append(
            {
                "object_id": item.stable_id,
                "status": "locked_unchanged",
                "position": item.position,
                "legal": legal,
                "reasons": reasons,
            }
        )
        if not legal:
            unresolved.append(
                {
                    "object_id": item.stable_id,
                    "reason": "locked_label_illegal",
                    "details": reasons,
                }
            )

    for item in sorted(movable, key=lambda record: record.stable_id):
        assert item.position is not None and item.bbox is not None
        current = Point(**item.position)
        current_box = BBox(**item.bbox)
        parent = snapshot.objects.get(item.parent_id or "")
        evaluated: list[dict[str, Any]] = []
        for point in _candidate_points(item, parent, config):
            candidate_box = current_box.translate(point.x - current.x, point.y - current.y)
            legal, reasons = _candidate_is_legal(
                candidate_box, item.side, occupied, snapshot, config
            )
            breakdown = _candidate_score(item, point, parent, config)
            evaluated.append(
                {
                    "position": point.as_dict(),
                    "bbox": candidate_box.as_dict(),
                    "legal": legal,
                    "reasons": reasons,
                    "score": breakdown,
                }
            )
        legal_candidates = [candidate for candidate in evaluated if candidate["legal"]]
        if not legal_candidates:
            unresolved.append(
                {
                    "object_id": item.stable_id,
                    "reason": "no_legal_candidate",
                    "candidate_count": len(evaluated),
                }
            )
            candidate_results.append(
                {
                    "object_id": item.stable_id,
                    "status": "unresolved",
                    "evaluated": evaluated,
                }
            )
            occupied.append(_Obstacle(item.stable_id, item.side, current_box, item.kind))
            continue
        chosen = min(
            legal_candidates,
            key=lambda candidate: (
                candidate["score"]["total"],
                candidate["position"]["x"],
                candidate["position"]["y"],
            ),
        )
        chosen_point = Point(**chosen["position"])
        chosen_box = BBox(**chosen["bbox"])
        moved = not (
            math.isclose(chosen_point.x, current.x, abs_tol=1e-9)
            and math.isclose(chosen_point.y, current.y, abs_tol=1e-9)
        )
        candidate_results.append(
            {
                "object_id": item.stable_id,
                "status": "move" if moved else "keep",
                "chosen": chosen,
                "evaluated_count": len(evaluated),
            }
        )
        if moved:
            operations.append(
                MoveBoardTextsOperation(
                    selector=QuerySelector(ids=[item.stable_id]),
                    absolute_x=chosen_point.x,
                    absolute_y=chosen_point.y,
                )
            )
            changed_ids.append(item.stable_id)
        for key in score_totals:
            score_totals[key] += float(chosen["score"][key])
        occupied.append(_Obstacle(item.stable_id, item.side, chosen_box, item.kind))

    missing_pad_geometry = not any(record.bbox for record in snapshot.board.pads)
    limitations = [
        "Text extents are deterministic approximations derived from exported text attributes."
    ]
    if missing_pad_geometry:
        limitations.append(
            "Pad and mask-opening obstacles are unavailable in this document export."
        )
    if not config.avoid_component_bodies:
        limitations.append("Component-body obstacles were disabled by the request.")
    return SilkscreenPlanningResult(
        operations=operations,
        changed_ids=changed_ids,
        unresolved=unresolved,
        candidates=candidate_results,
        score=score_totals,
        metrics={
            "selected_count": len(selected),
            "movable_count": len(movable),
            "locked_count": len(locked),
            "changed_count": len(changed_ids),
            "unresolved_count": len(unresolved),
            "fixed_obstacle_count": len(obstacles),
        },
        assumptions=[
            "Candidate generation is deterministic and uses normalized millimetres.",
            "Label rotations are preserved; the planner does not silently rotate or hide text.",
            "Candidate legality is checked against same-side axis-aligned obstacle bounds.",
        ],
        warnings=[],
        limitations=limitations,
    )


def _fixed_obstacles(
    snapshot: DocumentSnapshot,
    selected_ids: set[str],
    config: SilkscreenPlanConfig,
) -> list[_Obstacle]:
    assert snapshot.board is not None
    obstacles: list[_Obstacle] = []
    for item in snapshot.board.texts:
        if item.bbox is None or "Silk" not in (item.layer or ""):
            continue
        if item.stable_id in selected_ids and not item.locked:
            continue
        obstacles.append(_Obstacle(item.stable_id, item.side, BBox(**item.bbox), item.kind))
    for item in [*snapshot.board.pads, *snapshot.board.holes, *snapshot.board.testpoints]:
        if item.bbox is not None:
            obstacles.append(_Obstacle(item.stable_id, item.side, BBox(**item.bbox), item.kind))
    if config.avoid_component_bodies:
        for item in snapshot.board.components:
            if item.bbox is not None:
                obstacles.append(
                    _Obstacle(item.stable_id, item.side, BBox(**item.bbox), item.kind)
                )
    return obstacles


def _candidate_points(
    item: ObjectRecord,
    parent: ObjectRecord | None,
    config: SilkscreenPlanConfig,
) -> list[Point]:
    assert item.position is not None and item.bbox is not None
    current = Point(**item.position)
    text_box = BBox(**item.bbox)
    points = [current]
    directions = (
        (0.0, 1.0),
        (1.0, 0.0),
        (0.0, -1.0),
        (-1.0, 0.0),
        (1.0, 1.0),
        (1.0, -1.0),
        (-1.0, -1.0),
        (-1.0, 1.0),
    )
    if parent is not None and parent.bbox is not None:
        anchor = BBox(**parent.bbox)
        base_x = anchor.width / 2.0 + text_box.width / 2.0 + config.clearance
        base_y = anchor.height / 2.0 + text_box.height / 2.0 + config.clearance
        center = anchor.center
    else:
        base_x = text_box.width + config.clearance
        base_y = text_box.height + config.clearance
        center = current
    for step in range(config.search_steps):
        extra = step * config.grid
        for direction_x, direction_y in directions:
            x = center.x + direction_x * (base_x + extra)
            y = center.y + direction_y * (base_y + extra)
            points.append(
                Point(
                    round(x / config.grid) * config.grid,
                    round(y / config.grid) * config.grid,
                )
            )
    unique: dict[tuple[float, float], Point] = {}
    for point in points:
        unique[(round(point.x, 9), round(point.y, 9))] = point
    return list(unique.values())


def _candidate_is_legal(
    candidate: BBox,
    side: str | None,
    obstacles: list[_Obstacle],
    snapshot: DocumentSnapshot,
    config: SilkscreenPlanConfig,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    outline = snapshot.board.outline if snapshot.board is not None else None
    if outline is None:
        reasons.append("board_outline_missing")
    else:
        polygon = [Point(**point) for point in outline.get("points", [])]
        edge_box = candidate.expand(config.board_edge_clearance)
        corners = (
            Point(edge_box.min_x, edge_box.min_y),
            Point(edge_box.min_x, edge_box.max_y),
            Point(edge_box.max_x, edge_box.min_y),
            Point(edge_box.max_x, edge_box.max_y),
        )
        if not all(point_in_polygon(point, polygon) for point in corners):
            reasons.append("board_edge_clearance")
    for obstacle in obstacles:
        if side is not None and obstacle.side is not None and side != obstacle.side:
            continue
        if candidate.overlap_area(obstacle.bbox.expand(config.clearance)) > 0.0:
            reasons.append(f"overlap:{obstacle.object_id}")
    return not reasons, reasons


def _candidate_score(
    item: ObjectRecord,
    point: Point,
    parent: ObjectRecord | None,
    config: SilkscreenPlanConfig,
) -> dict[str, float]:
    assert item.position is not None
    movement = distance(Point(**item.position), point) * config.movement_weight
    association = 0.0
    if parent is not None and parent.position is not None:
        association = distance(Point(**parent.position), point) * config.association_weight
    angle = item.rotation_deg % 360.0
    readable_delta = min(abs(angle), abs(angle - 180.0), abs(angle - 360.0))
    orientation = (readable_delta / 180.0) * config.orientation_weight
    return {
        "movement": movement,
        "association": association,
        "orientation": orientation,
        "total": movement + association + orientation,
    }
