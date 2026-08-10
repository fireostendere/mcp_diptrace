from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_design_intent import (
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.pcb_routing_policy import (
    PCBRouteObservation,
    compile_pcb_routing_policy,
    evaluate_route_observation,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot(name: str = "pcb.xml"):
    return build_snapshot(DipTraceDocument.load(FIXTURES / name, 10_000_000))


def _policy_by_name(result, name: str):
    return next(item for item in result.policies if item.name == name)


def test_generation_c_compiles_differential_constraints_and_reference_policy() -> None:
    result = compile_pcb_routing_policy(_snapshot("diff_pair_pcb.xml"))

    plus = _policy_by_name(result, "USB_D+")
    minus = _policy_by_name(result, "USB_D-")
    for policy in (plus, minus):
        assert "differential" in policy.roles
        assert policy.max_length_mm == pytest.approx(10.0)
        assert policy.max_skew_mm == pytest.approx(0.25)
        assert policy.reference_plane_required is True
        assert policy.reference_candidates
        assert all(item.preliminary_only for item in policy.reference_candidates)
    assert result.route_order.index(plus.net_id) < len(result.route_order)
    assert result.route_order.index(minus.net_id) < len(result.route_order)


def test_generation_c_preserves_explicit_router_constraints_without_inventing_width() -> None:
    overrides = PCBIntentOverrides(
        nets=[
            PCBNetOverride(
                selector="SIGNAL",
                roles=["clock"],
                constraints=PCBElectricalConstraints(
                    edge_rate_ns=1.0,
                    target_impedance_ohm=50.0,
                    impedance_tolerance_percent=10.0,
                    max_length_mm=20.0,
                    max_skew_mm=0.5,
                    max_vias=2,
                    preferred_layers=["Top"],
                    forbidden_layers=["Bottom"],
                    minimum_spacing_mm=0.25,
                    stub_sensitive=True,
                    shielding_preferred=True,
                ),
            )
        ]
    )

    result = compile_pcb_routing_policy(_snapshot(), overrides=overrides)
    policy = _policy_by_name(result, "SIGNAL")

    assert policy.trace_width_mm is None
    assert policy.minimum_spacing_mm == pytest.approx(0.25)
    assert policy.preferred_layers == ["Top"]
    assert policy.forbidden_layers == ["Bottom"]
    assert policy.max_vias == 2
    assert policy.target_impedance_ohm == pytest.approx(50.0)
    assert policy.impedance_tolerance_percent == pytest.approx(10.0)
    assert policy.max_length_mm == pytest.approx(20.0)
    assert policy.stub_sensitive is True
    assert policy.shielding_preferred is True


def test_generation_c_route_order_is_deterministic_and_engineering_weighted() -> None:
    overrides = PCBIntentOverrides(
        nets=[
            PCBNetOverride(
                selector="SIGNAL",
                roles=["clock"],
                constraints=PCBElectricalConstraints(edge_rate_ns=1.0),
            )
        ]
    )
    first = compile_pcb_routing_policy(_snapshot(), overrides=overrides)
    second = compile_pcb_routing_policy(_snapshot(), overrides=overrides)
    signal = _policy_by_name(first, "SIGNAL")
    vcc = _policy_by_name(first, "VCC")

    assert first.route_order == second.route_order
    assert signal.priority > vcc.priority
    assert first.route_order.index(signal.net_id) < first.route_order.index(vcc.net_id)


def test_generation_c_evaluates_observed_si_constraints_and_requests_feedback() -> None:
    overrides = PCBIntentOverrides(
        nets=[
            PCBNetOverride(
                selector="SIGNAL",
                roles=["clock"],
                constraints=PCBElectricalConstraints(
                    edge_rate_ns=1.0,
                    target_impedance_ohm=50.0,
                    impedance_tolerance_percent=5.0,
                    max_length_mm=10.0,
                    max_skew_mm=0.1,
                    max_vias=1,
                    forbidden_layers=["Bottom"],
                    stub_sensitive=True,
                ),
            )
        ]
    )
    compiled = compile_pcb_routing_policy(_snapshot(), overrides=overrides)
    policy = _policy_by_name(compiled, "SIGNAL")
    component_ids = next(
        net.component_ids for net in compiled.intent.nets if net.net_id == policy.net_id
    )

    evaluation = evaluate_route_observation(
        policy,
        PCBRouteObservation(
            net_id=policy.net_id,
            length_mm=12.0,
            via_count=3,
            used_layers=["Top", "Bottom"],
            maintained_reference=False,
            impedance_ohm=60.0,
            skew_mm=0.2,
            stub_length_mm=1.0,
            parallel_exposure_mm=4.0,
        ),
        component_ids=component_ids,
    )
    checks = {item.key: item for item in evaluation.checks}

    for key in (
        "max_length",
        "via_budget",
        "forbidden_layers",
        "reference_continuity",
        "impedance",
        "skew",
        "stub",
    ):
        assert checks[key].status == "fail"
    assert checks["parallel_exposure"].status == "pass"
    assert evaluation.hard_failures == 7
    assert evaluation.placement_feedback.severity == "strong"
    assert evaluation.placement_feedback.action == "bounded_endpoint_move_candidate"
    assert evaluation.placement_feedback.component_ids == sorted(component_ids)


def test_generation_c_keeps_unobserved_or_unconstrained_checks_unknown() -> None:
    compiled = compile_pcb_routing_policy(_snapshot())
    policy = _policy_by_name(compiled, "SIGNAL")
    evaluation = evaluate_route_observation(
        policy,
        PCBRouteObservation(net_id=policy.net_id),
    )
    checks = {item.key: item for item in evaluation.checks}

    assert policy.trace_width_mm is None
    assert checks["max_length"].status == "unknown"
    assert checks["via_budget"].status == "unknown"
    assert checks["impedance"].status == "unknown"
    assert checks["parallel_exposure"].status == "unknown"
    assert evaluation.placement_feedback.action == "none"


def test_generation_c_copper_strategy_preserves_unknown_current_and_refill_boundary() -> None:
    result = compile_pcb_routing_policy(_snapshot())
    vcc = next(item for item in result.copper_strategies if item.name == "VCC")
    signal = next(item for item in result.copper_strategies if item.name == "SIGNAL")

    assert vcc.strategy == "local_plane_or_pour_candidate"
    assert vcc.current_a is None
    assert vcc.requires_refill_evidence is True
    assert any("current is unknown" in item for item in vcc.reasons)
    assert signal.strategy == "trace"
    assert signal.requires_refill_evidence is False


def test_generation_c_rejects_observation_for_wrong_net() -> None:
    result = compile_pcb_routing_policy(_snapshot())
    policy = _policy_by_name(result, "SIGNAL")

    with pytest.raises(ValueError, match="net_id does not match"):
        evaluate_route_observation(
            policy,
            PCBRouteObservation(net_id="wrong-net"),
        )
