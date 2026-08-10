from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import StrictModel
from .errors import CapabilityUnavailableError
from .pcb_design_intent import (
    PCBDesignIntent,
    PCBIntentOverrides,
    PCBNetIntent,
    build_pcb_design_intent,
)
from .pcb_physical import PCBPhysicalAnalysis, analyze_pcb_physics


class PCBLayerReferencePolicy(StrictModel):
    signal_layer: str
    reference_layers: list[str] = Field(default_factory=list)
    structure: Literal["microstrip", "symmetric_stripline"]
    confidence: Literal["low", "high"] = "low"
    preliminary_only: bool = True


class PCBNetRoutingPolicy(StrictModel):
    net_id: str
    name: str | None = None
    roles: list[str] = Field(default_factory=list)
    priority: int = Field(ge=0, le=1000)
    criticality: int = Field(ge=0, le=100)
    trace_width_mm: float | None = None
    minimum_spacing_mm: float | None = None
    preferred_layers: list[str] = Field(default_factory=list)
    forbidden_layers: list[str] = Field(default_factory=list)
    max_vias: int | None = None
    via_penalty: int = Field(ge=0, le=100)
    target_impedance_ohm: float | None = None
    impedance_tolerance_percent: float | None = None
    max_length_mm: float | None = None
    max_skew_mm: float | None = None
    reference_plane_required: bool = False
    reference_net: str | None = None
    reference_candidates: list[PCBLayerReferencePolicy] = Field(default_factory=list)
    stub_sensitive: bool = False
    shielding_preferred: bool = False
    reasons: list[str] = Field(default_factory=list)


class PCBCopperStrategy(StrictModel):
    net_id: str
    name: str | None = None
    strategy: Literal[
        "trace",
        "local_copper_minimized",
        "local_plane_or_pour_candidate",
        "continuous_plane_preferred",
        "chassis_or_shield",
        "kelvin_candidate",
        "explicit_star",
        "unknown",
    ]
    current_a: float | None = None
    requires_refill_evidence: bool = False
    reasons: list[str] = Field(default_factory=list)


class PCBRoutingPolicySet(StrictModel):
    intent: PCBDesignIntent
    physical: PCBPhysicalAnalysis
    policies: list[PCBNetRoutingPolicy] = Field(default_factory=list)
    route_order: list[str] = Field(default_factory=list)
    copper_strategies: list[PCBCopperStrategy] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


CheckStatus = Literal["pass", "fail", "unknown"]


class PCBRouteObservation(StrictModel):
    net_id: str
    length_mm: float | None = Field(default=None, ge=0.0)
    via_count: int | None = Field(default=None, ge=0)
    used_layers: list[str] = Field(default_factory=list)
    maintained_reference: bool | None = None
    impedance_ohm: float | None = Field(default=None, gt=0.0)
    skew_mm: float | None = Field(default=None, ge=0.0)
    stub_length_mm: float | None = Field(default=None, ge=0.0)
    parallel_exposure_mm: float | None = Field(default=None, ge=0.0)


class PCBSICheck(StrictModel):
    key: str
    status: CheckStatus
    actual: Any = None
    limit: Any = None
    reason: str


class PCBPlacementFeedback(StrictModel):
    net_id: str
    component_ids: list[str] = Field(default_factory=list)
    severity: Literal["none", "consider", "strong"] = "none"
    reasons: list[str] = Field(default_factory=list)
    action: Literal["none", "bounded_endpoint_move_candidate"] = "none"


class PCBRouteEvaluation(StrictModel):
    net_id: str
    checks: list[PCBSICheck] = Field(default_factory=list)
    hard_failures: int = Field(ge=0)
    placement_feedback: PCBPlacementFeedback
    observations_used: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


_ROLE_BONUS: dict[str, int] = {
    "switching_node": 180,
    "rf": 170,
    "differential": 150,
    "clock": 140,
    "precision_analog": 130,
    "reference": 130,
    "current_sense": 125,
    "feedback": 115,
    "high_current_power": 110,
    "analog": 70,
    "power": 60,
    "reset": 30,
    "control": 20,
    "digital": 15,
    "ground": 10,
    "shield": 10,
    "unknown": 0,
}


def _require_board(snapshot: DocumentSnapshot) -> None:
    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB routing policy requires a PCB document")


def _priority(net: PCBNetIntent) -> int:
    role_bonus = max((_ROLE_BONUS.get(role, 0) for role in net.roles), default=0)
    constraint_bonus = 0
    constraints = net.constraints
    if constraints.target_impedance_ohm is not None:
        constraint_bonus += 80
    if constraints.max_skew_mm is not None:
        constraint_bonus += 70
    if constraints.max_length_mm is not None:
        constraint_bonus += 50
    if constraints.max_vias is not None:
        constraint_bonus += 30
    if constraints.edge_rate_ns is not None:
        constraint_bonus += 60
    if constraints.signal_frequency_hz is not None:
        constraint_bonus += 40
    return min(1000, net.criticality * 5 + role_bonus + constraint_bonus)


def _reference_policies(physical: PCBPhysicalAnalysis) -> list[PCBLayerReferencePolicy]:
    return [
        PCBLayerReferencePolicy(
            signal_layer=item.signal_layer,
            reference_layers=list(item.reference_layers),
            structure=item.structure,
            confidence=item.reference_plane_confidence,
            preliminary_only=item.preliminary_only,
        )
        for item in physical.reference_candidates
    ]


def _policy_for_net(
    net: PCBNetIntent,
    references: list[PCBLayerReferencePolicy],
) -> PCBNetRoutingPolicy:
    constraints = net.constraints
    preferred = list(dict.fromkeys(constraints.preferred_layers))
    forbidden = list(dict.fromkeys(constraints.forbidden_layers))
    applicable_references = [
        item
        for item in references
        if not preferred or item.signal_layer in preferred
    ]
    reasons = [
        "Priority is deterministic from Generation A criticality, roles and explicit constraints.",
        "Physical routing limits are copied from explicit/exported facts; missing width/clearance is not invented.",
    ]
    if net.reference_plane_required:
        reasons.append(
            "Reference candidates come from Generation B exported-stackup analysis and remain preliminary."
        )
    return PCBNetRoutingPolicy(
        net_id=net.net_id,
        name=net.name,
        roles=list(net.roles),
        priority=_priority(net),
        criticality=net.criticality,
        trace_width_mm=None,
        minimum_spacing_mm=constraints.minimum_spacing_mm,
        preferred_layers=preferred,
        forbidden_layers=forbidden,
        max_vias=constraints.max_vias,
        via_penalty=net.via_penalty,
        target_impedance_ohm=constraints.target_impedance_ohm,
        impedance_tolerance_percent=constraints.impedance_tolerance_percent,
        max_length_mm=constraints.max_length_mm,
        max_skew_mm=constraints.max_skew_mm,
        reference_plane_required=net.reference_plane_required,
        reference_net=constraints.reference_net,
        reference_candidates=applicable_references,
        stub_sensitive=constraints.stub_sensitive,
        shielding_preferred=constraints.shielding_preferred,
        reasons=reasons,
    )


def _topology_strategy(intent: PCBDesignIntent, net_id: str) -> str | None:
    match = next(
        (item for item in intent.power_ground if item.net_id == net_id),
        None,
    )
    return match.strategy if match is not None else None


def _rail_current(physical: PCBPhysicalAnalysis, net_id: str) -> float | None:
    match = next((item for item in physical.pdn_rails if item.net_id == net_id), None)
    return match.current_a if match is not None else None


def _copper_strategy(
    net: PCBNetIntent,
    intent: PCBDesignIntent,
    physical: PCBPhysicalAnalysis,
) -> PCBCopperStrategy:
    topology = _topology_strategy(intent, net.net_id)
    current = _rail_current(physical, net.net_id)
    if topology in {
        "local_copper_minimized",
        "local_plane_or_pour_candidate",
        "continuous_plane_preferred",
        "chassis_or_shield",
        "kelvin_candidate",
        "explicit_star",
    }:
        strategy = topology
    elif {"power", "high_current_power"}.intersection(net.roles):
        strategy = "local_plane_or_pour_candidate"
    else:
        strategy = "trace"
    requires_refill = strategy in {
        "local_plane_or_pour_candidate",
        "continuous_plane_preferred",
        "chassis_or_shield",
        "explicit_star",
    }
    reasons = ["Strategy preserves Generation A return/power topology intent."]
    if current is None and {"power", "high_current_power"}.intersection(net.roles):
        reasons.append(
            "Rail current is unknown; strategy is a topology candidate, not a current-capacity conclusion."
        )
    if requires_refill:
        reasons.append(
            "Any poured/plane result requires authoritative DipTrace refill and geometry evidence before acceptance."
        )
    return PCBCopperStrategy(
        net_id=net.net_id,
        name=net.name,
        strategy=strategy,
        current_a=current,
        requires_refill_evidence=requires_refill,
        reasons=reasons,
    )


def compile_pcb_routing_policy(
    snapshot: DocumentSnapshot,
    *,
    overrides: PCBIntentOverrides | None = None,
    intent: PCBDesignIntent | None = None,
    physical: PCBPhysicalAnalysis | None = None,
) -> PCBRoutingPolicySet:
    """Compile Generation C router policy without creating or mutating routes."""

    _require_board(snapshot)
    intent = intent or build_pcb_design_intent(snapshot, overrides)
    physical = physical or analyze_pcb_physics(snapshot, intent=intent)
    references = _reference_policies(physical)
    policies = [_policy_for_net(net, references) for net in intent.nets]
    route_order = [
        item.net_id
        for item in sorted(
            policies,
            key=lambda item: (-item.priority, item.net_id),
        )
    ]
    return PCBRoutingPolicySet(
        intent=intent,
        physical=physical,
        policies=sorted(policies, key=lambda item: item.net_id),
        route_order=route_order,
        copper_strategies=sorted(
            [_copper_strategy(net, intent, physical) for net in intent.nets],
            key=lambda item: item.net_id,
        ),
        assumptions=[
            "Generation C policy is compiled from A/B evidence and does not itself mutate traces, vias or pours.",
            "Unknown trace width, spacing, impedance or timing facts remain unknown unless supplied/exported.",
            "Existing routing compiler and semantic transaction path remain authoritative for actual edits.",
        ],
        warnings=sorted(set([*intent.warnings, *physical.warnings])),
        limitations=[
            "Route ordering is engineering priority, not proof of global routing optimality.",
            "Reference candidates are preliminary until board-specific copper/refill and solver evidence exists.",
            "Copper strategy is intent; native pour refill/island/thermal behavior is not synthesized here.",
        ],
    )


def _check(
    key: str,
    *,
    actual: Any,
    limit: Any,
    failed: bool | None,
    pass_reason: str,
    fail_reason: str,
    unknown_reason: str,
) -> PCBSICheck:
    if failed is None:
        return PCBSICheck(
            key=key,
            status="unknown",
            actual=actual,
            limit=limit,
            reason=unknown_reason,
        )
    return PCBSICheck(
        key=key,
        status="fail" if failed else "pass",
        actual=actual,
        limit=limit,
        reason=fail_reason if failed else pass_reason,
    )


def evaluate_route_observation(
    policy: PCBNetRoutingPolicy,
    observation: PCBRouteObservation,
    *,
    component_ids: list[str] | None = None,
) -> PCBRouteEvaluation:
    """Evaluate supplied route observations; absence of observations stays unknown."""

    if observation.net_id != policy.net_id:
        raise ValueError("route observation net_id does not match routing policy")
    checks: list[PCBSICheck] = []
    checks.append(
        _check(
            "max_length",
            actual=observation.length_mm,
            limit=policy.max_length_mm,
            failed=(
                observation.length_mm > policy.max_length_mm
                if observation.length_mm is not None and policy.max_length_mm is not None
                else None
            ),
            pass_reason="Observed route length is within the explicit maximum.",
            fail_reason="Observed route length exceeds the explicit maximum.",
            unknown_reason="Length or explicit maximum is unavailable.",
        )
    )
    checks.append(
        _check(
            "via_budget",
            actual=observation.via_count,
            limit=policy.max_vias,
            failed=(
                observation.via_count > policy.max_vias
                if observation.via_count is not None and policy.max_vias is not None
                else None
            ),
            pass_reason="Observed via count is within the explicit budget.",
            fail_reason="Observed via count exceeds the explicit budget.",
            unknown_reason="Via count or explicit via budget is unavailable.",
        )
    )
    forbidden_used = sorted(set(observation.used_layers).intersection(policy.forbidden_layers))
    checks.append(
        PCBSICheck(
            key="forbidden_layers",
            status="fail" if forbidden_used else "pass",
            actual=forbidden_used,
            limit=policy.forbidden_layers,
            reason=(
                "Observed route uses a forbidden layer."
                if forbidden_used
                else "No observed used layer is explicitly forbidden."
            ),
        )
    )
    reference_failed: bool | None
    if not policy.reference_plane_required:
        reference_failed = False
    elif observation.maintained_reference is None:
        reference_failed = None
    else:
        reference_failed = not observation.maintained_reference
    checks.append(
        _check(
            "reference_continuity",
            actual=observation.maintained_reference,
            limit=policy.reference_plane_required,
            failed=reference_failed,
            pass_reason="Observed reference continuity satisfies the policy requirement.",
            fail_reason="Observed route breaks the required continuous reference.",
            unknown_reason="Reference continuity was not observed for a reference-sensitive net.",
        )
    )
    impedance_failed: bool | None = None
    tolerance = policy.impedance_tolerance_percent
    target = policy.target_impedance_ohm
    if observation.impedance_ohm is not None and target is not None and tolerance is not None:
        impedance_failed = abs(observation.impedance_ohm - target) > target * tolerance / 100.0
    checks.append(
        _check(
            "impedance",
            actual=observation.impedance_ohm,
            limit={"target_ohm": target, "tolerance_percent": tolerance},
            failed=impedance_failed,
            pass_reason="Observed impedance is inside the explicit tolerance.",
            fail_reason="Observed impedance is outside the explicit tolerance.",
            unknown_reason="Observed impedance, target or tolerance is unavailable.",
        )
    )
    checks.append(
        _check(
            "skew",
            actual=observation.skew_mm,
            limit=policy.max_skew_mm,
            failed=(
                observation.skew_mm > policy.max_skew_mm
                if observation.skew_mm is not None and policy.max_skew_mm is not None
                else None
            ),
            pass_reason="Observed skew is within the explicit maximum.",
            fail_reason="Observed skew exceeds the explicit maximum.",
            unknown_reason="Observed skew or explicit maximum is unavailable.",
        )
    )
    stub_failed: bool | None
    if not policy.stub_sensitive:
        stub_failed = False
    elif observation.stub_length_mm is None:
        stub_failed = None
    else:
        stub_failed = observation.stub_length_mm > 0.0
    checks.append(
        _check(
            "stub",
            actual=observation.stub_length_mm,
            limit=0.0 if policy.stub_sensitive else None,
            failed=stub_failed,
            pass_reason="No disallowed stub was observed.",
            fail_reason="A stub was observed on a stub-sensitive net.",
            unknown_reason="Stub exposure was not observed for a stub-sensitive net.",
        )
    )
    parallel_status: CheckStatus = (
        "unknown" if observation.parallel_exposure_mm is None else "pass"
    )
    checks.append(
        PCBSICheck(
            key="parallel_exposure",
            status=parallel_status,
            actual=observation.parallel_exposure_mm,
            limit=None,
            reason=(
                "Parallel exposure was measured; no universal numeric crosstalk limit is invented."
                if observation.parallel_exposure_mm is not None
                else "Parallel route exposure was not observed."
            ),
        )
    )
    hard_failures = sum(item.status == "fail" for item in checks)
    strong = any(
        item.key in {"reference_continuity", "via_budget"} and item.status == "fail"
        for item in checks
    )
    consider = hard_failures > 0
    feedback = PCBPlacementFeedback(
        net_id=policy.net_id,
        component_ids=sorted(set(component_ids or [])),
        severity="strong" if strong else ("consider" if consider else "none"),
        reasons=[
            item.reason
            for item in checks
            if item.status == "fail"
        ],
        action=(
            "bounded_endpoint_move_candidate" if consider and component_ids else "none"
        ),
    )
    observations_used = [
        key
        for key, value in {
            "length_mm": observation.length_mm,
            "via_count": observation.via_count,
            "used_layers": observation.used_layers,
            "maintained_reference": observation.maintained_reference,
            "impedance_ohm": observation.impedance_ohm,
            "skew_mm": observation.skew_mm,
            "stub_length_mm": observation.stub_length_mm,
            "parallel_exposure_mm": observation.parallel_exposure_mm,
        }.items()
        if value not in (None, [])
    ]
    return PCBRouteEvaluation(
        net_id=policy.net_id,
        checks=checks,
        hard_failures=hard_failures,
        placement_feedback=feedback,
        observations_used=observations_used,
        limitations=[
            "The evaluator checks supplied observations; it does not infer hidden trace geometry.",
            "Crosstalk/parallel exposure has no invented universal pass/fail threshold.",
        ],
    )
