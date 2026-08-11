from __future__ import annotations

import math
from collections import Counter
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import StrictModel
from .geometry import Point
from .schematic_joint_optimizer import (
    SchematicJointRouteConfig,
    SchematicPlacementRouteScore,
    score_schematic_placement_candidate_routes,
)
from .schematic_layout import (
    BoundReferenceMotif,
    ReferenceMotif,
    ReferenceMotifConstraint,
    SchematicDesignIntent,
    infer_schematic_design_intent,
)
from .schematic_optimizer import (
    SchematicOptimizerConfig,
    SchematicPlacementCandidate,
    generate_schematic_placement_candidates,
)
from .xml_document import DipTraceDocument

MotifRelation = Literal[
    "near",
    "left_of",
    "right_of",
    "above",
    "below",
    "same_row",
    "same_column",
]


class SchematicCongestionConfig(StrictModel):
    cell_size_mm: float = Field(default=20.0, gt=0.0, le=500.0)
    hotspot_occupancy: int = Field(default=3, ge=2, le=100)
    neighbor_radius_cells: int = Field(default=1, ge=0, le=8)
    hotspot_weight: float = Field(default=250.0, ge=0.0)
    local_pressure_weight: float = Field(default=15.0, ge=0.0)
    compactness_weight: float = Field(default=0.01, ge=0.0)


class SchematicCongestionMetrics(StrictModel):
    occupied_cell_count: int = Field(ge=0)
    hotspot_cell_count: int = Field(ge=0)
    max_cell_occupancy: int = Field(ge=0)
    local_pressure: float = Field(ge=0.0)
    span_area_mm2: float = Field(ge=0.0)
    penalty: float = Field(ge=0.0)


class SchematicEnsembleConfig(StrictModel):
    optimizer: SchematicOptimizerConfig = Field(default_factory=SchematicOptimizerConfig)
    route: SchematicJointRouteConfig = Field(default_factory=SchematicJointRouteConfig)
    congestion: SchematicCongestionConfig = Field(
        default_factory=SchematicCongestionConfig
    )
    infer_builtin_motifs: bool = True
    max_ranked_candidates: int = Field(default=12, ge=1, le=64)


class SchematicEnsembleCandidate(StrictModel):
    candidate: SchematicPlacementCandidate
    route_score: SchematicPlacementRouteScore
    congestion: SchematicCongestionMetrics
    inferred_motif_count: int = Field(ge=0)
    rank_key: list[float] = Field(min_length=12, max_length=12)


class SchematicEnsembleResult(StrictModel):
    selected: SchematicEnsembleCandidate
    candidates: list[SchematicEnsembleCandidate] = Field(default_factory=list)
    inferred_motifs: list[BoundReferenceMotif] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _binding_motif(
    *,
    name: str,
    source: str,
    first_id: str,
    second_id: str,
    relation: MotifRelation,
    max_distance_mm: float | None = None,
    tolerance_mm: float = 2.5,
    weight: float = 1.0,
) -> BoundReferenceMotif:
    return BoundReferenceMotif(
        motif=ReferenceMotif(
            name=name,
            source=source,
            source_kind="builtin",
            confidence=0.65,
            constraints=[
                ReferenceMotifConstraint(
                    first_key="first",
                    second_key="second",
                    relation=relation,
                    max_distance_mm=max_distance_mm,
                    tolerance_mm=tolerance_mm,
                    weight=weight,
                )
            ],
        ),
        bindings={"first": first_id, "second": second_id},
    )


def infer_builtin_schematic_motifs(
    snapshot: DocumentSnapshot,
    intent: SchematicDesignIntent | None = None,
) -> list[BoundReferenceMotif]:
    """Infer conservative project-local readability motifs from existing intent.

    These motifs are explicitly labelled ``builtin``. They are layout heuristics,
    not claims that a datasheet or reference design was consulted.
    """

    if snapshot.schematic is None:
        return []
    intent = intent or infer_schematic_design_intent(snapshot)
    part_roles = {item.part_id: item.role for item in intent.parts}
    motifs: list[BoundReferenceMotif] = []
    seen: set[tuple[str, str, MotifRelation]] = set()

    def add(
        first: str,
        second: str,
        relation: MotifRelation,
        *,
        distance_mm: float | None = None,
    ) -> None:
        key = (first, second, relation)
        if first == second or key in seen:
            return
        seen.add(key)
        motifs.append(
            _binding_motif(
                name=f"builtin:{relation}:{first[:12]}:{second[:12]}",
                source="DipTrace MCP deterministic schematic readability heuristic",
                first_id=first,
                second_id=second,
                relation=relation,
                max_distance_mm=distance_mm,
            )
        )

    for block in intent.blocks:
        anchors = sorted(block.anchor_part_ids)
        supports = sorted(block.support_part_ids)
        for anchor in anchors:
            for support in supports[:8]:
                add(anchor, support, "near", distance_mm=35.0)

        connectors = sorted(
            part_id
            for part_id in block.member_part_ids
            if part_roles.get(part_id) == "connector"
        )
        functional = sorted(
            part_id
            for part_id in block.member_part_ids
            if part_roles.get(part_id) in {"active", "power_control", "control"}
        )
        for connector in connectors:
            for target in functional[:4]:
                add(connector, target, "left_of")

        timing = sorted(
            part_id
            for part_id in block.member_part_ids
            if part_roles.get(part_id) == "timing"
        )
        for timing_part in timing:
            for anchor in anchors[:2]:
                add(timing_part, anchor, "near", distance_mm=25.0)

        protection = sorted(
            part_id
            for part_id in block.member_part_ids
            if part_roles.get(part_id) == "protection"
        )
        for protection_part in protection:
            for connector in connectors[:2]:
                add(protection_part, connector, "near", distance_mm=25.0)

    return motifs


def analyze_schematic_candidate_congestion(
    candidate: SchematicPlacementCandidate,
    config: SchematicCongestionConfig | None = None,
) -> SchematicCongestionMetrics:
    config = config or SchematicCongestionConfig()
    points = {
        part_id: Point(float(raw["x"]), float(raw["y"]))
        for part_id, raw in candidate.placements.items()
    }
    if not points:
        return SchematicCongestionMetrics(
            occupied_cell_count=0,
            hotspot_cell_count=0,
            max_cell_occupancy=0,
            local_pressure=0.0,
            span_area_mm2=0.0,
            penalty=0.0,
        )

    cells = Counter(
        (
            math.floor(point.x / config.cell_size_mm),
            math.floor(point.y / config.cell_size_mm),
        )
        for point in points.values()
    )
    hotspot_count = sum(
        occupancy >= config.hotspot_occupancy for occupancy in cells.values()
    )
    max_occupancy = max(cells.values(), default=0)

    pressure = 0.0
    radius = config.neighbor_radius_cells
    for (cell_x, cell_y), occupancy in sorted(cells.items()):
        neighbor_population = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                neighbor_population += cells.get((cell_x + dx, cell_y + dy), 0)
        pressure += occupancy * neighbor_population
    pressure /= 2.0

    xs = [point.x for point in points.values()]
    ys = [point.y for point in points.values()]
    span_area = max(0.0, max(xs) - min(xs)) * max(0.0, max(ys) - min(ys))
    penalty = (
        hotspot_count * config.hotspot_weight
        + pressure * config.local_pressure_weight
        + span_area * config.compactness_weight
    )
    return SchematicCongestionMetrics(
        occupied_cell_count=len(cells),
        hotspot_cell_count=hotspot_count,
        max_cell_occupancy=max_occupancy,
        local_pressure=pressure,
        span_area_mm2=span_area,
        penalty=penalty,
    )


def _ensemble_rank_key(
    route: SchematicPlacementRouteScore,
    congestion: SchematicCongestionMetrics,
    candidate: SchematicPlacementCandidate,
) -> list[float]:
    metrics = route.metrics
    return [
        float(metrics.rejected_route_count),
        float(metrics.obstacle_hits),
        float(metrics.overlaps),
        float(metrics.crossings),
        float(metrics.self_intersections),
        float(metrics.diagonals),
        float(congestion.hotspot_cell_count),
        float(congestion.max_cell_occupancy),
        congestion.local_pressure,
        congestion.penalty,
        candidate.total_score,
        metrics.length_mm,
    ]


def rank_schematic_ensemble(
    document: DipTraceDocument,
    *,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicEnsembleConfig | None = None,
) -> SchematicEnsembleResult:
    """Generate placement candidates and rank with motifs, routing, congestion."""

    config = config or SchematicEnsembleConfig()
    snapshot = build_snapshot(document)
    intent = infer_schematic_design_intent(snapshot, motifs=motifs)
    inferred = (
        infer_builtin_schematic_motifs(snapshot, intent)
        if config.infer_builtin_motifs
        else []
    )
    effective_motifs = [*(motifs or []), *inferred]
    candidates = generate_schematic_placement_candidates(
        snapshot,
        intent=intent,
        motifs=effective_motifs,
        config=config.optimizer,
    )
    ranked: list[SchematicEnsembleCandidate] = []
    for candidate in candidates[: config.max_ranked_candidates]:
        route = score_schematic_placement_candidate_routes(
            document,
            candidate,
            config=config.route,
        )
        congestion = analyze_schematic_candidate_congestion(
            candidate,
            config.congestion,
        )
        ranked.append(
            SchematicEnsembleCandidate(
                candidate=candidate,
                route_score=route,
                congestion=congestion,
                inferred_motif_count=len(inferred),
                rank_key=_ensemble_rank_key(route, congestion, candidate),
            )
        )
    if not ranked:
        raise ValueError("No schematic ensemble candidate could be generated")
    ranked.sort(key=lambda item: (tuple(item.rank_key), item.candidate.candidate_id))
    return SchematicEnsembleResult(
        selected=ranked[0],
        candidates=ranked,
        inferred_motifs=inferred,
        assumptions=[
            (
                "Builtin motifs are conservative readability heuristics derived only "
                "from normalized part/block roles; they never masquerade as datasheet "
                "evidence."
            ),
            (
                "Routing defects remain lexicographically dominant over congestion "
                "and compactness."
            ),
            (
                "Congestion is a bounded placement-grid pressure estimate, not a "
                "physical field model."
            ),
        ],
        limitations=[
            (
                "Text and pin-facing geometry remain governed by the existing layout "
                "and wire planners."
            ),
            (
                "The ensemble is deterministic and bounded; it does not claim a "
                "global optimum."
            ),
        ],
    )
