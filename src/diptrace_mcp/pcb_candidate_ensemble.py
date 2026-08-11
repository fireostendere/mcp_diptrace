from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import StrictModel
from .errors import CapabilityUnavailableError
from .pcb_design_intent import PCBDesignIntent, PCBIntentOverrides, build_pcb_design_intent
from .pcb_joint_optimizer import (
    PCBHardViolations,
    PCBOptimizationCandidate,
    PCBOptimizationSelection,
    PCBSoftScore,
    select_pcb_candidate,
)
from .pcb_physical import PCBPhysicalAnalysis, analyze_pcb_physics
from .pcb_placement import (
    PCBPlacementV2Config,
    PCBPlacementV2Plan,
    PCBPlacementV2Weights,
    plan_pcb_placement_v2,
)
from .pcb_routing_policy import PCBRoutingPolicySet, compile_pcb_routing_policy

PCBEnsembleProfile = Literal[
    "balanced",
    "critical_nets",
    "noise_aware",
    "support_compact",
]


class PCBEnsembleConfig(StrictModel):
    profiles: list[PCBEnsembleProfile] = Field(
        default_factory=lambda: [
            "balanced",
            "critical_nets",
            "noise_aware",
            "support_compact",
        ],
        min_length=1,
        max_length=8,
    )
    placement: PCBPlacementV2Config = Field(default_factory=PCBPlacementV2Config)
    include_existing_board: bool = True


class PCBEnsembleCandidate(StrictModel):
    profile: str
    optimization: PCBOptimizationCandidate
    changed_component_ids: list[str] = Field(default_factory=list)
    placement_score_before: float = Field(ge=0.0)
    placement_score_after: float = Field(ge=0.0)
    physical_warning_count: int = Field(ge=0)
    routing_unknown_count: int = Field(ge=0)
    assumptions: list[str] = Field(default_factory=list)


class PCBEnsembleResult(StrictModel):
    selected_profile: str
    selection: PCBOptimizationSelection
    candidates: list[PCBEnsembleCandidate] = Field(default_factory=list)
    intent: PCBDesignIntent
    physical: PCBPhysicalAnalysis
    routing_policy: PCBRoutingPolicySet
    limitations: list[str] = Field(default_factory=list)


def _weights(profile: PCBEnsembleProfile, base: PCBPlacementV2Weights) -> PCBPlacementV2Weights:
    values = base.model_dump()
    if profile == "critical_nets":
        values["critical_connection"] *= 2.5
        values["block_cohesion"] *= 1.25
    elif profile == "noise_aware":
        values["noise_coupling"] *= 3.0
        values["critical_connection"] *= 1.25
    elif profile == "support_compact":
        values["support_adjacency"] *= 2.75
        values["block_cohesion"] *= 1.75
    return PCBPlacementV2Weights.model_validate(values)


def _profile_config(
    profile: PCBEnsembleProfile,
    base: PCBPlacementV2Config,
) -> PCBPlacementV2Config:
    values = base.model_dump()
    values["weights"] = _weights(profile, base.weights).model_dump()
    return PCBPlacementV2Config.model_validate(values)


def _geometry_hard(plan: PCBPlacementV2Plan) -> PCBHardViolations:
    counts = {
        "overlap": 0,
        "courtyard": 0,
        "keepout": 0,
        "outline": 0,
    }
    for item in plan.after.geometry_violations:
        text = " ".join(str(value) for value in item.values()).casefold()
        if "keepout" in text:
            counts["keepout"] += 1
        elif "outline" in text or "contain" in text or "board" in text:
            counts["outline"] += 1
        elif "courtyard" in text:
            counts["courtyard"] += 1
        else:
            counts["overlap"] += 1
    return PCBHardViolations(
        overlap_count=counts["overlap"],
        courtyard_collision_count=counts["courtyard"],
        keepout_violation_count=counts["keepout"],
        outline_violation_count=counts["outline"],
    )


def _routing_unknown_count(policy: PCBRoutingPolicySet) -> int:
    count = 0
    for item in policy.policies:
        if item.trace_width_mm is None:
            count += 1
        if item.reference_plane_required and not item.reference_candidates:
            count += 1
        if item.target_impedance_ohm is not None and not item.reference_candidates:
            count += 1
    return count


def _soft_score(
    plan: PCBPlacementV2Plan,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
) -> PCBSoftScore:
    score = plan.after.score
    unknown_routing = _routing_unknown_count(routing)
    return PCBSoftScore(
        estimated_routed_length_mm=score.critical_connection,
        via_penalty=float(unknown_routing),
        si_penalty=score.noise_coupling,
        pi_penalty=float(len(physical.pdn_rails) + len(physical.warnings)),
        thermal_penalty=float(len(physical.hot_loop_candidates)),
        emi_penalty=score.noise_coupling + float(len(physical.noise_pairs)),
        congestion_penalty=score.geometry + score.block_cohesion,
        soft_constraint_penalty=score.support_adjacency,
    )


def _candidate(
    profile: str,
    plan: PCBPlacementV2Plan,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
) -> PCBEnsembleCandidate:
    hard = _geometry_hard(plan)
    soft = _soft_score(plan, physical, routing)
    optimization = PCBOptimizationCandidate(
        candidate_id=f"pcb-ensemble:{profile}",
        source="internal",
        hard=hard,
        soft=soft,
        metrics={
            "profile": profile,
            "changed_component_count": len(plan.changed_component_ids),
            "placement_score_before": plan.before.score.total,
            "placement_score_after": plan.after.score.total,
            "routing_unknown_count": _routing_unknown_count(routing),
            "physical_warning_count": len(physical.warnings),
            "score_terms": plan.after.score.model_dump(mode="json"),
        },
        assumptions=[
            "Generation A placement candidates are actual bounded move proposals from pcb_placement.",
            "Generation B/C penalties are conservative evidence proxies; unknown physical facts "
            "remain visible and are not promoted to solver truth.",
        ],
        warnings=sorted(set([*plan.warnings, *physical.warnings, *routing.warnings])),
    )
    return PCBEnsembleCandidate(
        profile=profile,
        optimization=optimization,
        changed_component_ids=list(plan.changed_component_ids),
        placement_score_before=plan.before.score.total,
        placement_score_after=plan.after.score.total,
        physical_warning_count=len(physical.warnings),
        routing_unknown_count=_routing_unknown_count(routing),
        assumptions=list(optimization.assumptions),
    )


def build_pcb_candidate_ensemble(
    snapshot: DocumentSnapshot,
    *,
    overrides: PCBIntentOverrides | None = None,
    config: PCBEnsembleConfig | None = None,
) -> PCBEnsembleResult:
    """Generate and rank bounded Generation A-D placement candidates.

    Candidate generation is real: every non-baseline candidate comes from the existing bounded
    Generation-A placement planner. Generation B/C data contributes conservative score terms, and
    the existing Generation-D hard-first selector chooses the winner.
    """

    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB candidate ensemble requires a PCB document")
    config = config or PCBEnsembleConfig()
    intent = build_pcb_design_intent(snapshot, overrides)
    physical = analyze_pcb_physics(snapshot, intent=intent)
    routing = compile_pcb_routing_policy(snapshot, intent=intent, physical=physical)

    candidates: list[PCBEnsembleCandidate] = []
    seen_profiles: set[str] = set()
    for profile in config.profiles:
        if profile in seen_profiles:
            continue
        seen_profiles.add(profile)
        plan = plan_pcb_placement_v2(
            snapshot,
            overrides=overrides,
            config=_profile_config(profile, config.placement),
        )
        candidates.append(_candidate(profile, plan, physical, routing))

    if config.include_existing_board:
        base_plan = plan_pcb_placement_v2(
            snapshot,
            overrides=overrides,
            config=PCBPlacementV2Config.model_validate(
                {
                    **config.placement.model_dump(),
                    "search_radius_steps": 1,
                    "max_candidates_per_component": 4,
                }
            ),
        )
        existing = _candidate("existing_board", base_plan, physical, routing)
        existing.optimization.candidate_id = "pcb-ensemble:existing_board"
        candidates.append(existing)

    if not candidates:
        raise CapabilityUnavailableError("PCB candidate ensemble produced no candidates")
    selection = select_pcb_candidate([item.optimization for item in candidates])
    selected_profile = next(
        item.profile
        for item in candidates
        if item.optimization.candidate_id == selection.selected.candidate_id
    )
    if not math.isfinite(selection.selected.soft.total):
        raise CapabilityUnavailableError("PCB candidate ensemble produced a non-finite score")
    return PCBEnsembleResult(
        selected_profile=selected_profile,
        selection=selection,
        candidates=candidates,
        intent=intent,
        physical=physical,
        routing_policy=routing,
        limitations=[
            "Generation-D selection compares bounded candidate plans; it does not claim global "
            "placement/routing optimality.",
            "SI/PI/thermal/EMI score terms are conservative proxies from exported facts and "
            "normalized topology, not field-solver or manufacturing sign-off.",
            "The selected placement plan still requires the normal semantic transaction, DRC/review, "
            "and claim-specific real-DipTrace evidence before production acceptance.",
        ],
    )
