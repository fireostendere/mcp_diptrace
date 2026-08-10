from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.pcb_physical import analyze_pcb_physics
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot(name: str):
    return build_snapshot(DipTraceDocument.load(FIXTURES / name, 10_000_000))


def test_generation_b_uses_exported_stackup_without_promoting_solver_trust() -> None:
    analysis = analyze_pcb_physics(_snapshot("diff_pair_pcb.xml"))

    assert analysis.reference_candidates
    assert all(item.preliminary_only for item in analysis.reference_candidates)
    assert all(item.evidence == "exported_stackup" for item in analysis.reference_candidates)
    assert any("field-solver" in item for item in analysis.assumptions)


def test_generation_b_pdn_preserves_unknown_current_and_source_direction() -> None:
    analysis = analyze_pcb_physics(_snapshot("pcb.xml"))
    vcc = next(item for item in analysis.pdn_rails if item.name == "VCC")

    assert vcc.current_a is None
    assert vcc.current_density_known is False
    assert vcc.voltage_drop_known is False
    assert vcc.power_via_capacity_required is False
    assert vcc.source_component_ids == []
    assert any("current is unknown" in item for item in vcc.warnings)
    assert any("source direction remains unresolved" in item for item in vcc.warnings)


def test_generation_b_uses_operator_current_and_converter_facts_conservatively() -> None:
    overrides = PCBIntentOverrides(
        components=[PCBComponentOverride(selector="U1", role="power_converter")],
        nets=[
            PCBNetOverride(
                selector="VCC",
                roles=["power"],
                constraints=PCBElectricalConstraints(current_a=1.25),
            )
        ],
    )

    analysis = analyze_pcb_physics(_snapshot("pcb.xml"), overrides=overrides)
    vcc = next(item for item in analysis.pdn_rails if item.name == "VCC")
    u1_id = next(item.component_id for item in analysis.intent.components if item.refdes == "U1")

    assert vcc.current_a == pytest.approx(1.25)
    assert vcc.source_component_ids == [u1_id]
    assert vcc.power_via_capacity_required is True
    assert vcc.current_density_known is False
    assert vcc.voltage_drop_known is False


def test_generation_b_return_path_targets_reference_sensitive_nets() -> None:
    analysis = analyze_pcb_physics(_snapshot("diff_pair_pcb.xml"))
    names = {
        item.net_id: item.name
        for item in analysis.intent.nets
    }
    targets = analysis.return_path["target_net_ids"]

    assert targets
    assert {names[item] for item in targets}.issuperset({"USB_D+", "USB_D-"})
    assert analysis.return_path["analysis"] is not None


def test_generation_b_noise_requires_explicit_timing_evidence() -> None:
    baseline = analyze_pcb_physics(_snapshot("pcb.xml"))
    assert baseline.noise_pairs == []

    overrides = PCBIntentOverrides(
        nets=[
            PCBNetOverride(
                selector="SIGNAL",
                roles=["clock"],
                constraints=PCBElectricalConstraints(edge_rate_ns=1.0),
            ),
            PCBNetOverride(
                selector="VCC",
                roles=["analog", "precision_analog"],
                constraints=PCBElectricalConstraints(signal_frequency_hz=1_000_000.0),
            ),
        ]
    )
    analysis = analyze_pcb_physics(_snapshot("pcb.xml"), overrides=overrides)

    assert analysis.noise_pairs
    pair = analysis.noise_pairs[0]
    assert pair.timing_evidence
    assert pair.risk_score >= 0.0
    assert any("not asserted" in item for item in pair.reasons)


def test_generation_b_via_roles_never_invent_capacity_or_fence_roles() -> None:
    analysis = analyze_pcb_physics(_snapshot("diff_pair_pcb.xml"))

    allowed = {
        "signal_via",
        "power_via",
        "ground_stitching_via",
        "return_transition_candidate",
        "differential_transition_member",
        "thermal_via",
    }
    assert all(set(item.roles).issubset(allowed) for item in analysis.via_roles)
    assert all("via_fence" not in item.roles for item in analysis.via_roles)
    assert any("current capacity" in item for item in analysis.limitations)


def test_generation_b_rejects_nonfinite_or_nonpositive_stitching_radius() -> None:
    snapshot = _snapshot("pcb.xml")
    for value in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite and positive"):
            analyze_pcb_physics(snapshot, stitching_radius_mm=value)
