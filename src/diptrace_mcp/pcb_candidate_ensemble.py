from __future__ import annotations

from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import StrictModel
from .errors import CapabilityUnavailableError
from .pcb_design_intent import (
    PCBDesignIntent,
    PCBIntentOverrides,
    build_pcb_design_intent,
)
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
from .pcb_quality import PCBQualityReview, review_pcb_quality
from .pcb_routing_policy import PCBRoutingPolicySet, compile_pcb_routing_policy
from .semantic_compiler import apply_semantic_operations

PCBEnsembleProfile = Literal[
    "balanced",
    "critical_nets",
    "noise_aware",
    "support_compact",
]


def _default_profiles() -> list[PCBEnsembleProfile]:
    return ["balanced", "critical_nets", "noise_aware", "support_compact"]


class PCBEnsembleConfig(StrictModel):
    profiles: list[PCBEnsembleProfile] = Field(
        default_factory=_default_profiles,
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
    quality: PCBQualityReview
    score_terms: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class PCBEnsembleResult(StrictModel):
    selected_profile: str
    selection: PCBOptimizationResult
    candidates: list[PCBEnsembleCandidate] = Field(default_factory=list)
    intent: PCBDesignIntent
    physical: PCBPhysicalAnalysis
    routing_policy: PCBRoutingPolicySet
    selected_quality: PCBQualityReview
    limitations: list[str] = Field(default_factory=list)


def _weights(
    profile: PCBEnsembleProfile,
    base: PCBPlacementV2Weights,
) -> PCBPlacementV2Weights:
    values = base.model_dump()
    if profile == "critical_nets":
        values["critical_connection"] *= 2.5
        values["block_cohesion"] *= 1.25
    elif profile == "noise_aware":
        values["noise_coupling"] *= 3.0
        values["critical_connection"] *= 1.25
        values["hot_loop"] *= 2.0
    elif profile == "support_compact":
        values["support_adjacency"] *= 2.75
        values["block_cohesion"] *= 1.75
        values["compactness"] *= 2.0
        values["centering"] *= 1.5
        values["symmetry"] *= 2.0
    return PCBPlacementV2Weights.model_validate(values)


def pcb_placement_profile_config(
    profile: PCBEnsembleProfile,
    base: PCBPlacementV2Config,
) -> PCBPlacementV2Config:
    values = base.model_dump()
    values["weights"] = _weights(profile, base.weights).model_dump()
    return PCBPlacementV2Config.model_validate(values)


def _geometry_hard(
    analysis: PCBPlacementV2Analysis,
    quality: PCBQualityReview,
) -> PCBHardViolations:
    mechanical = 0
    drc = 0
    return_path = 0
    manufacturing = 0
    for item in analysis.geometry_violations:
        text = " ".join(str(value) for value in item.values()).casefold()
        if (
            "outline" in text
            or "contain" in text
            or "board" in text
            or "keepout" in text
        ):
            mechanical += 1
        else:
            drc += 1
    for finding in quality.findings:
        if finding.severity != "error":
            continue
        if finding.category == "geometry":
            mechanical += 1
        elif finding.category in {"ground", "return_path"}:
            return_path += 1
        elif finding.category in {"manufacturing", "silkscreen"}:
            manufacturing += 1
        else:
            drc += 1
    return PCBHardViolations(
        mechanical=mechanical,
        drc=drc,
        reference_path=return_path,
        manufacturing=manufacturing,
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
    analysis: PCBPlacementV2Analysis,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
    quality: PCBQualityReview,
) -> PCBSoftScore:
    score = analysis.score
    unknown_routing = _routing_unknown_count(routing)
    return PCBSoftScore(
        placement=(
            score.geometry
            + score.block_cohesion
            + score.support_adjacency
            + score.compactness
            + score.centering
            + score.symmetry
            + quality.center_offset_mm
            + quality.alignment_penalty_mm
            + max(0.0, 1.0 - quality.occupied_ratio) * 10.0
        ),
        routing=score.critical_connection,
        vias=float(unknown_routing)
        + (
            (1.0 - quality.stitching_coverage_ratio) * 10.0
            if quality.stitching_coverage_ratio is not None
            else 5.0
        ),
        signal_integrity=score.noise_coupling,
        power_integrity=(
            quality.decoupling_span_mm + float(len(physical.pdn_rails) + len(physical.warnings))
        ),
        return_path=float(sum(1 for item in routing.policies if item.reference_plane_required))
        + float(sum(item.category == "return_path" for item in quality.findings)),
        emi_risk=(
            score.noise_coupling
            + score.hot_loop
            + quality.hot_loop_span_mm
            + float(len(physical.noise_pairs))
        ),
        thermal_risk=float(len(physical.hot_loop_candidates)),
        manufacturing=float(quality.silkscreen_violation_count),
    )


def _candidate_from_analysis(
    profile: str,
    analysis: PCBPlacementV2Analysis,
    physical: PCBPhysicalAnalysis,
    routing: PCBRoutingPolicySet,
    quality: PCBQualityReview,
    *,
    changed_component_ids: list[str],
    before_score: float,
    source: Literal["internal", "existing_board"] = "internal",
    warnings: list[str] | None = None,
) -> PCBEnsembleCandidate:
    assumptions = [
        (
            "Generation A candidate geometry comes from the bounded pcb_placement "
            "planner or the existing board baseline."
        ),
        (
            "Generation B/C score terms are conservative evidence proxies; unknown "
            "physical facts remain visible and are not promoted to solver truth."
        ),
    ]
    optimization = PCBOptimizationCandidate(
        candidate_id=f"pcb-ensemble:{profile}",
        source=source,
        hard=_geometry_hard(analysis, quality),
        soft=_soft_score(analysis, physical, routing, quality),
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
        quality=quality,
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
    quality: PCBQualityReview,
) -> PCBEnsembleCandidate:
    return _candidate_from_analysis(
        profile,
        plan.after,
        physical,
        routing,
        quality,
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

    Candidate generation is real: every non-baseline candidate comes from the
    existing bounded Generation-A placement planner. Generation B/C data contributes
    conservative score terms, and the existing Generation-D hard-first selector
    chooses the winner.
    """

    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB candidate ensemble requires a PCB document")
    config = config or PCBEnsembleConfig()
    intent = build_pcb_design_intent(snapshot, overrides)
    physical = analyze_pcb_physics(snapshot, intent=intent)
    routing = compile_pcb_routing_policy(
        snapshot,
        intent=intent,
        physical=physical,
    )

    baseline = analyze_pcb_placement_v2(
        snapshot,
        intent=intent,
        config=config.placement,
    )
    baseline_quality = review_pcb_quality(
        snapshot,
        intent=intent,
        physical=physical,
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
            config=pcb_placement_profile_config(profile, config.placement),
        )
        candidate_document = apply_semantic_operations(
            snapshot.document,
            plan.operations,
        ).document
        candidate_snapshot = build_snapshot(candidate_document)
        candidate_intent = build_pcb_design_intent(candidate_snapshot, overrides)
        candidate_physical = analyze_pcb_physics(
            candidate_snapshot,
            intent=candidate_intent,
        )
        candidate_routing = compile_pcb_routing_policy(
            candidate_snapshot,
            intent=candidate_intent,
            physical=candidate_physical,
        )
        quality = review_pcb_quality(
            candidate_snapshot,
            intent=candidate_intent,
            physical=candidate_physical,
        )
        candidates.append(
            _candidate_from_plan(
                profile,
                plan,
                candidate_physical,
                candidate_routing,
                quality,
            )
        )

    if config.include_existing_board:
        candidates.append(
            _candidate_from_analysis(
                "existing_board",
                baseline,
                physical,
                routing,
                baseline_quality,
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
    selected_quality = next(
        item.quality
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
        selected_quality=selected_quality,
        limitations=[
            (
                "Generation-D selection compares bounded candidate plans; it does not "
                "claim global placement/routing optimality."
            ),
            (
                "SI/PI/thermal/EMI score terms are conservative proxies from exported "
                "facts and normalized topology, not field-solver or manufacturing "
                "sign-off."
            ),
            (
                "The selected placement plan still requires the normal semantic "
                "transaction, DRC/review, and claim-specific real-DipTrace evidence "
                "before production acceptance."
            ),
        ],
    )
