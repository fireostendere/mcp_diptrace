from __future__ import annotations

import pytest

from diptrace_mcp.physics_estimates import (
    LossBudgetRequest,
    PhysicsSourceReference,
    ThermalEstimateRequest,
    TraceResistanceRequest,
    ViaResistanceRequest,
    VoltageDropRequest,
    estimate_first_order_temperature,
    estimate_loss_budget,
    estimate_trace_dc_resistance,
    estimate_via_dc_resistance,
    estimate_voltage_drop,
)


def _source() -> PhysicsSourceReference:
    return PhysicsSourceReference(
        source_id="reviewed-source",
        revision="rev-a",
        locator="page 7, equation 2",
        sha256="a" * 64,
        conditions="values supplied for the exact reviewed material/process",
    )


def test_missing_physical_fact_stays_unknown_without_typical_default() -> None:
    result = estimate_trace_dc_resistance(
        TraceResistanceRequest(length_mm=100.0, width_mm=0.25)
    )

    assert result.status == "unknown"
    assert set(result.missing_inputs) == {
        "resistivity_ohm_m",
        "source",
        "thickness_mm",
    }
    assert result.value is None
    assert any("No typical/default" in item for item in result.limitations)


def test_trace_via_drop_loss_and_thermal_are_bounded_and_sourced() -> None:
    source = _source()
    trace = estimate_trace_dc_resistance(
        TraceResistanceRequest(
            length_mm=100.0,
            width_mm=0.25,
            thickness_mm=0.035,
            resistivity_ohm_m=1.68e-8,
            source=source,
        )
    )
    assert trace.status == "estimated" and trace.value is not None
    assert trace.value == pytest.approx(0.192, rel=0.02)
    assert trace.source == source
    assert "width_plus_1pct_relative_output" in trace.sensitivity

    via = estimate_via_dc_resistance(
        ViaResistanceRequest(
            barrel_length_mm=1.6,
            finished_diameter_mm=0.3,
            plating_thickness_mm=0.025,
            resistivity_ohm_m=1.68e-8,
            source=source,
        )
    )
    assert via.status == "estimated" and via.value is not None

    drop = estimate_voltage_drop(
        VoltageDropRequest(
            resistance_ohm=trace.value + via.value,
            current_a=1.0,
            source=source,
        )
    )
    assert drop.value == pytest.approx(trace.value + via.value)

    loss = estimate_loss_budget(
        LossBudgetRequest(stage_losses_db=[0.5, 1.25, 0.25], source=source)
    )
    assert loss.value == pytest.approx(2.0)
    assert loss.method_id == "explicit_db_stage_sum"

    thermal = estimate_first_order_temperature(
        ThermalEstimateRequest(
            power_w=2.0,
            theta_c_per_w=15.0,
            ambient_c=25.0,
            source=source,
        )
    )
    assert thermal.value == pytest.approx(55.0)
    assert thermal.solver_kind == "analytical"
    assert any("M8" in item for item in thermal.limitations)


def test_explicit_extreme_via_geometry_is_not_replaced_by_typical_limits() -> None:
    result = estimate_via_dc_resistance(
        ViaResistanceRequest(
            barrel_length_mm=1.6,
            finished_diameter_mm=0.1,
            plating_thickness_mm=0.2,
            resistivity_ohm_m=1.68e-8,
            source=_source(),
        )
    )

    assert result.status == "estimated"
    assert result.value is not None and result.value > 0.0
    assert result.missing_inputs == []
    assert any("plating nonuniformity" in item for item in result.limitations)
