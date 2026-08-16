from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import BBox, Point, distance, point_in_polygon
from .pcb_design_intent import PCBDesignIntent, build_pcb_design_intent
from .pcb_physical import PCBPhysicalAnalysis, analyze_pcb_physics
from .pcb_physics_knowledge import PCBPhysicsPrinciple, pcb_physics_principles


class PCBQualityConfig(StrictModel):
    compact_edge_margin_mm: float = Field(default=0.5, ge=0.0, le=25.0)
    stitching_pitch_mm: float = Field(default=2.0, gt=0.0, le=25.0)
    stitching_coverage_radius_mm: float = Field(default=2.85, gt=0.0, le=50.0)
    stitching_obstacle_clearance_mm: float = Field(default=0.3, ge=0.0, le=10.0)
    require_two_layer_ground_pours: bool = True


class PCBQualityFinding(StrictModel):
    code: str
    category: Literal[
        "geometry",
        "ground",
        "return_path",
        "power_integrity",
        "signal_integrity",
        "thermal",
        "silkscreen",
        "manufacturing",
    ]
    severity: Literal["error", "warning", "info"]
    message: str
    object_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, float | int | str | bool | None] = Field(default_factory=dict)


class PCBQualityReview(StrictModel):
    score: float = Field(ge=0.0)
    hard_error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    board_area_mm2: float = Field(ge=0.0)
    occupied_area_mm2: float = Field(ge=0.0)
    occupied_ratio: float = Field(ge=0.0, le=1.0)
    center_offset_mm: float = Field(ge=0.0)
    alignment_penalty_mm: float = Field(ge=0.0)
    hot_loop_span_mm: float = Field(ge=0.0)
    decoupling_span_mm: float = Field(ge=0.0)
    ground_pour_layer_count: int = Field(ge=0)
    ground_stitching_via_count: int = Field(ge=0)
    stitching_sample_count: int = Field(ge=0)
    stitching_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    maximum_stitching_gap_mm: float | None = Field(default=None, ge=0.0)
    silkscreen_violation_count: int = Field(ge=0)
    findings: list[PCBQualityFinding] = Field(default_factory=list)
    physics_principles: list[PCBPhysicsPrinciple] = Field(default_factory=list)
    review_priorities: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _combined_box(records: list[ObjectRecord]) -> BBox | None:
    boxes = [BBox(**item.bbox) for item in records if item.bbox is not None]
    if not boxes:
        return None
    return BBox(
        min(item.min_x for item in boxes),
        min(item.min_y for item in boxes),
        max(item.max_x for item in boxes),
        max(item.max_y for item in boxes),
    )


def _layer_name(snapshot: DocumentSnapshot, layer_id: str | None) -> str:
    if snapshot.board is None or layer_id is None:
        return ""
    match = next(
        (item for item in snapshot.board.layers if str(item.get("id", "")) == layer_id),
        None,
    )
    return str(match.get("name", layer_id)) if match is not None else layer_id


def _ground_net_names(intent: PCBDesignIntent) -> set[str]:
    return {item.name.casefold() for item in intent.nets if "ground" in item.roles and item.name}


def _alignment_penalty(snapshot: DocumentSnapshot, intent: PCBDesignIntent) -> float:
    assert snapshot.board is not None
    records = {item.stable_id: item for item in snapshot.board.components}
    component_intent = {item.component_id: item for item in intent.components}
    groups: dict[tuple[str, str, str], list[ObjectRecord]] = defaultdict(list)
    for component_id, item in records.items():
        classified = component_intent.get(component_id)
        if classified is None or item.position is None:
            continue
        pattern = str(item.attributes.get("pattern_style") or item.name or "")
        groups[(classified.block_id, classified.role, pattern)].append(item)
    penalty = 0.0
    for group in groups.values():
        if len(group) != 2:
            continue
        first, second = sorted(group, key=lambda item: item.stable_id)
        assert first.position is not None and second.position is not None
        penalty += min(
            abs(first.position["x"] - second.position["x"]),
            abs(first.position["y"] - second.position["y"]),
        )
    return penalty


def _component_span(
    ids: list[str],
    components: dict[str, ObjectRecord],
) -> float:
    points: list[Point] = []
    for item in ids:
        component = components.get(item)
        if component is not None and component.position is not None:
            points.append(Point(**component.position))
    if len(points) < 2:
        return 0.0
    return max(distance(first, second) for first in points for second in points)


def _physical_spans(
    snapshot: DocumentSnapshot,
    physical: PCBPhysicalAnalysis,
) -> tuple[float, float, list[str]]:
    assert snapshot.board is not None
    components = {item.stable_id: item for item in snapshot.board.components}
    hot_loop = math.fsum(
        _component_span(
            [*item.converter_component_ids, *item.support_component_ids],
            components,
        )
        for item in physical.hot_loop_candidates
    )
    decoupling = 0.0
    unknowns: list[str] = []
    for rail in physical.pdn_rails:
        if not rail.source_component_ids:
            unknowns.append(f"PDN source direction is unknown for {rail.name or rail.net_id}.")
            continue
        for capacitor in rail.decoupling_component_ids:
            decoupling += min(
                (
                    _component_span([capacitor, source], components)
                    for source in rail.source_component_ids
                ),
                default=0.0,
            )
        if rail.current_a is None:
            unknowns.append(
                f"Rail current is unknown for {rail.name or rail.net_id}; "
                "copper loss and via capacity are not scored."
            )
    return hot_loop, decoupling, unknowns


def _free_stitching_samples(
    snapshot: DocumentSnapshot,
    config: PCBQualityConfig,
) -> list[Point]:
    assert snapshot.board is not None
    outline = snapshot.board.outline
    if outline is None:
        return []
    polygon = [Point(**item) for item in outline.get("points", [])]
    if len(polygon) < 3:
        return []
    box = BBox(**outline["bbox"])
    obstacles = [
        BBox(**item.bbox).expand(config.stitching_obstacle_clearance_mm)
        for item in (
            snapshot.board.components
            + snapshot.board.pads
            + snapshot.board.holes
            + snapshot.board.traces
            + snapshot.board.keepouts
            + [
                text
                for text in snapshot.board.texts
                if "Silk" in (text.layer or "") and text.attributes.get("Show", "Show") != "Hide"
            ]
        )
        if item.bbox is not None
    ]
    xs = int(math.floor(box.width / config.stitching_pitch_mm)) + 1
    ys = int(math.floor(box.height / config.stitching_pitch_mm)) + 1
    if xs * ys > 4_096:
        return []
    result: list[Point] = []
    for x_index in range(xs + 1):
        x = min(box.max_x, box.min_x + x_index * config.stitching_pitch_mm)
        for y_index in range(ys + 1):
            y = min(box.max_y, box.min_y + y_index * config.stitching_pitch_mm)
            point = Point(x, y)
            if point_in_polygon(point, polygon) and not any(
                obstacle.contains_point(point) for obstacle in obstacles
            ):
                result.append(point)
    return result


def _stitching_coverage(
    snapshot: DocumentSnapshot,
    physical: PCBPhysicalAnalysis,
    config: PCBQualityConfig,
) -> tuple[int, int, float | None, float | None]:
    assert snapshot.board is not None
    via_by_id = {item.stable_id: item for item in snapshot.board.vias}
    ground_vias = [
        via_by_id[item.via_id]
        for item in physical.via_roles
        if "ground_stitching_via" in item.roles
        and item.via_id in via_by_id
        and via_by_id[item.via_id].position is not None
    ]
    samples = _free_stitching_samples(snapshot, config)
    if not samples:
        return len(ground_vias), 0, None, None
    if not ground_vias:
        return 0, len(samples), 0.0, None
    gaps = [
        min(distance(sample, Point(**via.position)) for via in ground_vias if via.position)
        for sample in samples
    ]
    covered = sum(gap <= config.stitching_coverage_radius_mm for gap in gaps)
    return len(ground_vias), len(samples), covered / len(samples), max(gaps)


def _silkscreen_violations(snapshot: DocumentSnapshot) -> tuple[int, list[str]]:
    assert snapshot.board is not None
    violations: set[tuple[str, str]] = set()
    for text in snapshot.board.texts:
        if (
            text.bbox is None
            or "Silk" not in (text.layer or "")
            or text.attributes.get("Show", "Show") == "Hide"
        ):
            continue
        text_box = BBox(**text.bbox)
        obstacles = [
            item
            for item in (
                snapshot.board.components
                + snapshot.board.pads
                + snapshot.board.holes
                + snapshot.board.vias
            )
            if item.bbox is not None
            and item.stable_id != text.parent_id
            and (item.side is None or text.side is None or item.side == text.side)
        ]
        for obstacle in obstacles:
            assert obstacle.bbox is not None
            if text_box.overlap_area(BBox(**obstacle.bbox)) > 0.0:
                violations.add((text.stable_id, obstacle.stable_id))
    ids = sorted({item for pair in violations for item in pair})
    return len(violations), ids


def review_pcb_quality(
    snapshot: DocumentSnapshot,
    *,
    intent: PCBDesignIntent | None = None,
    physical: PCBPhysicalAnalysis | None = None,
    config: PCBQualityConfig | None = None,
) -> PCBQualityReview:
    """Score exported geometry and known physics without inventing missing facts."""

    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB quality review requires a PCB document")
    config = config or PCBQualityConfig()
    intent = intent or build_pcb_design_intent(snapshot)
    physical = physical or analyze_pcb_physics(
        snapshot,
        intent=intent,
        stitching_radius_mm=config.stitching_coverage_radius_mm,
    )
    outline = snapshot.board.outline
    outline_box = BBox(**outline["bbox"]) if outline is not None else None
    occupied = _combined_box(
        snapshot.board.components
        + snapshot.board.holes
        + snapshot.board.keepouts
        + snapshot.board.testpoints
    )
    board_area = outline_box.area if outline_box is not None else 0.0
    occupied_area = occupied.area if occupied is not None else 0.0
    occupied_ratio = min(1.0, occupied_area / board_area) if board_area > 0.0 else 0.0
    center_offset = (
        distance(outline_box.center, occupied.center)
        if outline_box is not None and occupied is not None
        else 0.0
    )
    alignment = _alignment_penalty(snapshot, intent)
    hot_loop, decoupling, unknowns = _physical_spans(snapshot, physical)
    ground_names = _ground_net_names(intent)
    ground_pours = [
        item
        for item in snapshot.board.copper_pours
        if (item.net_name or "").casefold() in ground_names
    ]
    ground_layers = {_layer_name(snapshot, item.layer).casefold() for item in ground_pours}
    via_count, sample_count, coverage, maximum_gap = _stitching_coverage(snapshot, physical, config)
    silk_count, silk_ids = _silkscreen_violations(snapshot)
    findings: list[PCBQualityFinding] = []

    if outline_box is None:
        findings.append(
            PCBQualityFinding(
                code="board_outline_missing",
                category="geometry",
                severity="error",
                message="Board outline is unavailable; compactness and containment are unproven.",
            )
        )
    elif occupied is not None:
        expected = occupied.expand(config.compact_edge_margin_mm)
        wasted_area = max(0.0, board_area - expected.area)
        if wasted_area > max(25.0, expected.area * 0.35):
            findings.append(
                PCBQualityFinding(
                    code="board_not_compact",
                    category="geometry",
                    severity="warning",
                    message=(
                        "The outline contains substantial area outside occupied "
                        "geometry and the configured margin."
                    ),
                    evidence={"unused_area_mm2": wasted_area, "occupied_ratio": occupied_ratio},
                )
            )
        if center_offset > config.compact_edge_margin_mm:
            findings.append(
                PCBQualityFinding(
                    code="layout_off_center",
                    category="geometry",
                    severity="warning",
                    message="Occupied component geometry is not centered in the board outline.",
                    evidence={"center_offset_mm": center_offset},
                )
            )

    if alignment > 0.01:
        findings.append(
            PCBQualityFinding(
                code="repeated_parts_not_aligned",
                category="geometry",
                severity="info",
                message="A repeated two-part group is not aligned on either principal axis.",
                evidence={"alignment_penalty_mm": alignment},
            )
        )

    copper_layer_names = {
        str(item.get("name", "")).casefold()
        for item in snapshot.board.layers
        if str(item.get("type", "")).casefold() in {"signal", "plane", "copper", ""}
    }
    ordinary_two_layer = {"top", "bottom"}.issubset(copper_layer_names) and len(
        [name for name in copper_layer_names if name]
    ) <= 2
    if config.require_two_layer_ground_pours and ordinary_two_layer:
        missing = {"top", "bottom"} - ground_layers
        if missing:
            findings.append(
                PCBQualityFinding(
                    code="two_layer_ground_pour_missing",
                    category="ground",
                    severity="error",
                    message=f"Ground pour is missing on: {', '.join(sorted(missing))}.",
                    evidence={"ground_pour_layer_count": len(ground_layers)},
                )
            )
    if ground_pours and any(
        str(item.attributes.get("Spoke", "")).casefold() != "4 spoke" for item in ground_pours
    ):
        findings.append(
            PCBQualityFinding(
                code="ground_thermal_not_four_spoke",
                category="manufacturing",
                severity="warning",
                message="At least one GND pour does not request a four-spoke thermal relief.",
            )
        )
    if sample_count and (coverage or 0.0) < 0.9:
        findings.append(
            PCBQualityFinding(
                code="ground_stitching_sparse_regions",
                category="return_path",
                severity="warning",
                message=(
                    "Some free board regions are farther from GND stitching than "
                    "the configured coverage radius."
                ),
                evidence={
                    "coverage_ratio": coverage,
                    "maximum_gap_mm": maximum_gap,
                    "target_radius_mm": config.stitching_coverage_radius_mm,
                },
            )
        )
    if silk_count:
        findings.append(
            PCBQualityFinding(
                code="silkscreen_mounting_overlap",
                category="silkscreen",
                severity="error",
                message="Visible silkscreen overlaps another component, pad, hole, or via.",
                object_ids=silk_ids,
                evidence={"violation_count": silk_count},
            )
        )

    return_issues = (
        physical.return_path.get("analysis", {}).get("issues", [])
        if isinstance(physical.return_path.get("analysis"), dict)
        else []
    )
    if return_issues:
        findings.append(
            PCBQualityFinding(
                code="return_path_issues",
                category="return_path",
                severity="warning",
                message="Reference-sensitive routes have bounded return-path findings.",
                evidence={"issue_count": len(return_issues)},
            )
        )
    switch_names = {
        item.name.casefold() for item in intent.nets if "switching_node" in item.roles and item.name
    }
    broad_switch_pours = [
        item
        for item in snapshot.board.copper_pours
        if (item.net_name or "").casefold() in switch_names
    ]
    if broad_switch_pours:
        findings.append(
            PCBQualityFinding(
                code="switch_node_broad_copper",
                category="signal_integrity",
                severity="warning",
                message=(
                    "A switching node is assigned a copper pour; verify that "
                    "high-dV/dt copper area is intentionally minimized."
                ),
                object_ids=[item.stable_id for item in broad_switch_pours],
            )
        )

    score = math.fsum(
        (
            max(0.0, 1.0 - occupied_ratio) * 10.0,
            center_offset,
            alignment,
            hot_loop * 2.0,
            decoupling * 1.5,
            (1.0 - (coverage or 0.0)) * 25.0 if sample_count else 10.0,
            silk_count * 100.0,
            len(return_issues) * 25.0,
            len(broad_switch_pours) * 25.0,
        )
    )
    priorities = [
        item.code
        for item in sorted(
            findings,
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}[item.severity],
                item.code,
            ),
        )
    ]
    return PCBQualityReview(
        score=score,
        hard_error_count=sum(item.severity == "error" for item in findings),
        warning_count=sum(item.severity == "warning" for item in findings),
        board_area_mm2=board_area,
        occupied_area_mm2=occupied_area,
        occupied_ratio=occupied_ratio,
        center_offset_mm=center_offset,
        alignment_penalty_mm=alignment,
        hot_loop_span_mm=hot_loop,
        decoupling_span_mm=decoupling,
        ground_pour_layer_count=len(ground_layers),
        ground_stitching_via_count=via_count,
        stitching_sample_count=sample_count,
        stitching_coverage_ratio=coverage,
        maximum_stitching_gap_mm=maximum_gap,
        silkscreen_violation_count=silk_count,
        findings=findings,
        physics_principles=pcb_physics_principles(),
        review_priorities=priorities,
        unknowns=sorted(set(unknowns)),
        assumptions=[
            "Known geometry and explicit electrical constraints dominate reviewer preference.",
            (
                "High-di/dt loop and decoupling scores use component-span proxies "
                "only when topology identifies the participating parts."
            ),
            (
                "Silkscreen may cross solder-masked traces; traces are deliberately "
                "not silkscreen obstacles."
            ),
        ],
        limitations=[
            (
                "Copper-pour boundaries and thermal attributes are intent, not "
                "authoritative native refill geometry."
            ),
            (
                "No field, PI, EMC, thermal, or manufacturing sign-off is inferred "
                "from this bounded score."
            ),
            (
                "Unknown current, material, edge-rate, enclosure, and airflow facts "
                "remain explicit unknowns."
            ),
        ],
    )
