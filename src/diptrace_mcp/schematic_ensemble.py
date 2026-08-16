from __future__ import annotations

import math
import re
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
from .schematic_placement_repair import (
    SchematicPlacementRepairConfig,
    repair_schematic_placement_from_route_feedback,
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
    repair_iterations: int = Field(default=2, ge=0, le=8)
    repair_seed_count: int = Field(default=2, ge=0, le=8)


class SchematicEnsembleCandidate(StrictModel):
    candidate: SchematicPlacementCandidate
    route_score: SchematicPlacementRouteScore
    congestion: SchematicCongestionMetrics
    inferred_motif_count: int = Field(ge=0)
    rank_key: list[float] = Field(min_length=12, max_length=12)
    repair_iteration_count: int = Field(default=0, ge=0)
    objective_history: list[list[float]] = Field(default_factory=list)


class SchematicNetStrategy(StrictModel):
    net_id: str
    name: str | None = None
    role: str
    endpoint_count: int = Field(ge=0)
    sheets: list[int] = Field(default_factory=list)
    strategy: Literal["wire", "net_label", "bus", "power_symbol"]
    routing_priority: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


class SchematicInterconnectPlan(StrictModel):
    scheduled_nets: list[SchematicNetStrategy] = Field(default_factory=list)
    bus_groups: dict[str, list[str]] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class SchematicEnsembleResult(StrictModel):
    selected: SchematicEnsembleCandidate
    candidates: list[SchematicEnsembleCandidate] = Field(default_factory=list)
    inferred_motifs: list[BoundReferenceMotif] = Field(default_factory=list)
    interconnect_plan: SchematicInterconnectPlan
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


_BUS_MEMBER_RE = re.compile(r"^(.+?)(?:\[?\d+\]?)$")


def plan_schematic_interconnect(
    snapshot: DocumentSnapshot,
    intent: SchematicDesignIntent,
) -> SchematicInterconnectPlan:
    """Choose a deterministic wire/label/bus policy and global net order."""

    if snapshot.schematic is None:
        raise ValueError("Schematic interconnect planning requires a schematic document")
    net_records = {item.stable_id: item for item in snapshot.schematic.nets}
    parts = {item.stable_id: item for item in snapshot.schematic.parts}
    bus_members: dict[str, list[str]] = {}
    for net in intent.nets:
        if not net.name:
            continue
        match = _BUS_MEMBER_RE.fullmatch(net.name)
        if match:
            bus_members.setdefault(match.group(1), []).append(net.net_id)
    bus_groups = {name: sorted(ids) for name, ids in sorted(bus_members.items()) if len(ids) >= 3}
    bus_ids = {net_id for ids in bus_groups.values() for net_id in ids}
    role_priority = {
        "clock": 100,
        "reset": 90,
        "interface": 80,
        "signal": 60,
        "power": 40,
        "ground": 30,
        "unknown": 10,
    }
    strategies: list[SchematicNetStrategy] = []
    for net in intent.nets:
        record = net_records.get(net.net_id)
        xml_id = record.xml_id if record is not None else None
        endpoint_count = sum(pin.net_id == xml_id for pin in snapshot.schematic.pins)
        sheets = sorted(
            {
                int(str(parts[part_id].attributes.get("sheet", "0")))
                for part_id in net.part_ids
                if part_id in parts and str(parts[part_id].attributes.get("sheet", "0")).isdigit()
            }
        )
        reasons: list[str] = []
        if net.net_id in bus_ids:
            strategy: Literal["wire", "net_label", "bus", "power_symbol"] = "bus"
            reasons.append("three or more indexed sibling nets form a bus family")
        elif net.role in {"power", "ground"}:
            strategy = "power_symbol"
            reasons.append("power/ground symbols avoid long global supply wires")
        elif len(sheets) > 1 or endpoint_count > 4:
            strategy = "net_label"
            reasons.append("multi-sheet or high-fanout connectivity favors labels")
        else:
            strategy = "wire"
            reasons.append("bounded sheet-local connectivity remains readable as wires")
        priority = role_priority.get(net.role, 0) + min(endpoint_count, 20)
        strategies.append(
            SchematicNetStrategy(
                net_id=net.net_id,
                name=net.name,
                role=net.role,
                endpoint_count=endpoint_count,
                sheets=sheets,
                strategy=strategy,
                routing_priority=priority,
                reasons=reasons,
            )
        )
    strategies.sort(key=lambda item: (-item.routing_priority, item.name or "", item.net_id))
    return SchematicInterconnectPlan(
        scheduled_nets=strategies,
        bus_groups=bus_groups,
        assumptions=[
            "Critical clocks/resets/interfaces are scheduled before ordinary signals.",
            "Labels and buses are a readability plan; electrical connectivity remains net-based.",
        ],
    )


def _ranked_candidate(
    document: DipTraceDocument,
    candidate: SchematicPlacementCandidate,
    *,
    inferred_motif_count: int,
    config: SchematicEnsembleConfig,
    repair_iteration_count: int = 0,
    objective_history: list[list[float]] | None = None,
) -> SchematicEnsembleCandidate:
    route = score_schematic_placement_candidate_routes(
        document,
        candidate,
        config=config.route,
    )
    congestion = analyze_schematic_candidate_congestion(candidate, config.congestion)
    rank_key = _ensemble_rank_key(route, congestion, candidate)
    return SchematicEnsembleCandidate(
        candidate=candidate,
        route_score=route,
        congestion=congestion,
        inferred_motif_count=inferred_motif_count,
        rank_key=rank_key,
        repair_iteration_count=repair_iteration_count,
        objective_history=[*(objective_history or []), rank_key],
    )


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
    ranked = [
        _ranked_candidate(
            document,
            candidate,
            inferred_motif_count=len(inferred),
            config=config,
        )
        for candidate in candidates[: config.max_ranked_candidates]
    ]
    if not ranked:
        raise ValueError("No schematic ensemble candidate could be generated")
    ranked.sort(key=lambda item: (tuple(item.rank_key), item.candidate.candidate_id))
    repair_config = SchematicPlacementRepairConfig(
        optimizer=config.optimizer,
        joint_route=config.route,
    )
    for index in range(min(config.repair_seed_count, len(ranked))):
        current = ranked[index]
        for iteration in range(config.repair_iterations):
            repair = repair_schematic_placement_from_route_feedback(
                document,
                current.candidate,
                intent=intent,
                motifs=effective_motifs,
                config=repair_config,
            )
            if not repair.improved or repair.selected is None:
                break
            repaired = _ranked_candidate(
                document,
                repair.selected.candidate,
                inferred_motif_count=len(inferred),
                config=config,
                repair_iteration_count=iteration + 1,
                objective_history=current.objective_history,
            )
            if tuple(repaired.rank_key) >= tuple(current.rank_key):
                break
            current = repaired
        ranked[index] = current
    ranked.sort(key=lambda item: (tuple(item.rank_key), item.candidate.candidate_id))
    interconnect = plan_schematic_interconnect(snapshot, intent)
    return SchematicEnsembleResult(
        selected=ranked[0],
        candidates=ranked,
        inferred_motifs=inferred,
        interconnect_plan=interconnect,
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
            (
                "The top bounded candidates receive generate-score-repair iterations "
                "with explicit objective history and deterministic stopping."
            ),
        ],
        limitations=[
            (
                "Automatic label/bus output is a strategy plan; authoring remains "
                "subject to the existing semantic transaction path."
            ),
            (
                "The ensemble is deterministic and bounded; it does not claim a "
                "global optimum."
            ),
        ],
    )
