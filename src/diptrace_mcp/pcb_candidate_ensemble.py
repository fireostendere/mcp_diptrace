from __future__ import annotations

from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import StrictModel
from .errors import CapabilityUnavailableError
from .pcb_design_intent import PCBDesignIntent, PCBIntentOverrides, build_pcb_design_intent
from .pcb_joint_optimizer import (
    PCBHardViolations,
    PCBOptimizationCandidate,
    PCBOptimizationResult,
    PCBSoftScore,
    select_pcb_candidate,
)
from .pcb_physical import PCBPhysicalAnalysis, analyze_pcb_physics
from .pcb_placement import (
    PCBPlacementV2Analysis,
    PCBPlacementV2Config,
    PCBPlacementV2Plan,
    PCBPlacementV2Weights,
    analyze_pcb_placement_v2,
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
    score_terms: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class PCBEnsembleResult(StrictModel):
    selected_profile: str
    selection: PCBOptimizationResult
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


def _geometry_hard(analysis: PCBPlacementV2Analysis) -> PCBHardViolations:
    mechanical = 0
    drc = 0
    for item in analysis.geometry_violations:
        text = " ".join(str(value) for value in item.values()).casefold()
        if "outline" in text or "contain" in text or "board" in text or "keepout" in text:
            mechanical += 1
        else:
            drc += 1
    return PCBHardViolations(mechanical=mechanical, drc=drc)


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
    analysis: PCBPlacementV2Analysis,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
) -> PCBSoftScore:
    score = analysis.score
    unknown_routing = _routing_unknown_count(routing)
    return PCBSoftScore(
        placement=score.geometry + score.block_cohesion + score.support_adjacency,
        routing=score.critical_connection,
        vias=float(unknown_routing),
        signal_integrity=score.noise_coupling,
        power_integrity=float(len(physical.pdn_rails) + len(physical.warnings)),
        return_path=float(
            sum(1 for item in routing.policies if item.reference_plane_required)
        ),
        emi_risk=score.noise_coupling + float(len(physical.noise_pairs)),
        thermal_risk=float(len(physical.hot_loop_candidates)),
        manufacturing=0.0,
    )


def _candidate_from_analysis(
    profile: str,
    analysis: PCBPlacementV2Analysis,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
    *,
    changed_component_ids: list[str],
    before_score: float,
    source: Literal["internal", "existing_board"] = "internal",
    warnings: list[str] | None = None,
) -> PCBEnsembleCandidate:
    assumptions = [
        "Generation A candidate geometry comes from the bounded pcb_placement planner or the "
        "existing board baseline.",
        "Generation B/C score terms are conservative evidence proxies; unknown physical facts "
        "remain visible and are not promoted to solver truth.",
    ]
    optimization = PCBOptimizationCandidate(
        candidate_id=f"pcb-ensemble:{profile}",
        source=source,
        hard=_geometry_hard(analysis),
        soft=_soft_score(analysis, physical, routing),
        plan_refs=[f"placement-profile:{profile}"],
        assumptions=assumptions,
        warnings=sorted(set(warnings or [])),
    )
    terms = analysis.score.model_dump(mode="json")
    return PCBEnsembleCandidate(
        profile=profile,
        optimization=optimization,
        changed_component_ids=list(changed_component_ids),
        placement_score_before=before_score,
        placement_score_after=analysis.score.total,
        physical_warning_count=len(physical.warnings),
        routing_unknown_count=_routing_unknown_count(routing),
        score_terms={
            key: float(value)
            for key, value in terms.items()
            if key != "total"
        },
        assumptions=assumptions,
    )


def _candidate_from_plan(
    profile: str,
    plan: PCBPlacementV2Plan,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
) -> PCBEnsembleCandidate:
    return _candidate_from_analysis(
        profile,
        plan.after,
        physical,
        routing,
        changed_component_ids=plan.changed_component_ids,
        before_score=plan.before.score.total,
        warnings=[*plan.warnings, *physical.warnings, *routing.warnings],
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

    baseline = analyze_pcb_placement_v2(
        snapshot,
        intent=intent,
        config=config.placement,
    )
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
        candidates.append(_candidate_from_plan(profile, plan, physical, routing))

    if config.include_existing_board:
        candidates.append(
            _candidate_from_analysis(
                "existing_board",
                baseline,
                physical,
                routing,
                changed_component_ids=[],
                before_score=baseline.score.total,
                source="existing_board",
                warnings=[*baseline.warnings, *physical.warnings, *routing.warnings],
            )
        )

    if not candidates:
        raise CapabilityUnavailableError("PCB candidate ensemble produced no candidates")
    selection = select_pcb_candidate([item.optimization for item in candidates])
    selected_profile = next(
        item.profile
        for item in candidates
        if item.optimization.candidate_id == selection.selected.candidate_id
    )
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
