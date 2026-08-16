from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from .domain import StrictModel


class PhysicsSourceReference(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    revision: str = Field(min_length=1, max_length=256)
    locator: str = Field(min_length=1, max_length=2_048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    conditions: str = Field(min_length=1, max_length=2_048)


class PhysicsEstimate(StrictModel):
    schema_version: Literal["diptrace-bounded-physics-v1"] = "diptrace-bounded-physics-v1"
    status: Literal["estimated", "unknown"]
    quantity: str
    value: float | None = None
    unit: str
    method_id: str
    method_version: str = "1"
    solver_kind: Literal["analytical"] = "analytical"
    exact_inputs: dict[str, float | str | list[float] | None] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    sensitivity: dict[str, float] = Field(default_factory=dict)
    source: PhysicsSourceReference | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TraceResistanceRequest(StrictModel):
    length_mm: float | None = Field(default=None, gt=0.0)
    width_mm: float | None = Field(default=None, gt=0.0)
    thickness_mm: float | None = Field(default=None, gt=0.0)
    resistivity_ohm_m: float | None = Field(default=None, gt=0.0)
    source: PhysicsSourceReference | None = None


class ViaResistanceRequest(StrictModel):
    barrel_length_mm: float | None = Field(default=None, gt=0.0)
    finished_diameter_mm: float | None = Field(default=None, gt=0.0)
    plating_thickness_mm: float | None = Field(default=None, gt=0.0)
    resistivity_ohm_m: float | None = Field(default=None, gt=0.0)
    source: PhysicsSourceReference | None = None


class VoltageDropRequest(StrictModel):
    resistance_ohm: float | None = Field(default=None, ge=0.0)
    current_a: float | None = Field(default=None, ge=0.0)
    source: PhysicsSourceReference | None = None


class LossBudgetRequest(StrictModel):
    stage_losses_db: list[float] | None = None
    source: PhysicsSourceReference | None = None


class ThermalEstimateRequest(StrictModel):
    power_w: float | None = Field(default=None, ge=0.0)
    theta_c_per_w: float | None = Field(default=None, gt=0.0)
    ambient_c: float | None = None
    source: PhysicsSourceReference | None = None


def _unknown(
    *,
    quantity: str,
    unit: str,
    method_id: str,
    exact_inputs: dict[str, float | str | list[float] | None],
    missing: list[str],
    source: PhysicsSourceReference | None,
) -> PhysicsEstimate:
    return PhysicsEstimate(
        status="unknown",
        quantity=quantity,
        unit=unit,
        method_id=method_id,
        exact_inputs=exact_inputs,
        missing_inputs=sorted(missing),
        source=source,
        limitations=[
            "No typical/default electrical or material value is substituted for missing input.",
            "Analytical estimate is not an ngspice/openEMS result and does not grant M8 sign-off.",
        ],
    )


def _source_missing(source: PhysicsSourceReference | None) -> list[str]:
    return [] if source is not None else ["source"]


def estimate_trace_dc_resistance(request: TraceResistanceRequest) -> PhysicsEstimate:
    inputs = request.model_dump(mode="json", exclude={"source"})
    missing = [name for name, value in inputs.items() if value is None] + _source_missing(
        request.source
    )
    if missing:
        return _unknown(
            quantity="trace_dc_resistance",
            unit="ohm",
            method_id="uniform_rectangular_conductor_rho_l_over_a",
            exact_inputs=inputs,
            missing=missing,
            source=request.source,
        )
    assert request.length_mm is not None
    assert request.width_mm is not None
    assert request.thickness_mm is not None
    assert request.resistivity_ohm_m is not None
    length_m = request.length_mm * 1e-3
    area_m2 = request.width_mm * 1e-3 * request.thickness_mm * 1e-3
    value = request.resistivity_ohm_m * length_m / area_m2
    return PhysicsEstimate(
        status="estimated",
        quantity="trace_dc_resistance",
        value=value,
        unit="ohm",
        method_id="uniform_rectangular_conductor_rho_l_over_a",
        exact_inputs=inputs,
        source=request.source,
        sensitivity={
            "length_plus_1pct_relative_output": 0.01,
            "width_plus_1pct_relative_output": (1.0 / 1.01) - 1.0,
            "thickness_plus_1pct_relative_output": (1.0 / 1.01) - 1.0,
            "resistivity_plus_1pct_relative_output": 0.01,
        },
        assumptions=["Uniform rectangular conductor cross-section and DC current density."],
        limitations=[
            (
                "Does not model skin/proximity effect, etch profile, plating variation "
                "or self-heating."
            ),
            (
                "Source applicability requires M3 and physical correlation, when "
                "claimed, requires M8."
            ),
        ],
    )


def estimate_via_dc_resistance(request: ViaResistanceRequest) -> PhysicsEstimate:
    inputs = request.model_dump(mode="json", exclude={"source"})
    missing = [name for name, value in inputs.items() if value is None] + _source_missing(
        request.source
    )
    if missing:
        return _unknown(
            quantity="via_dc_resistance",
            unit="ohm",
            method_id="cylindrical_plated_barrel_rho_l_over_a",
            exact_inputs=inputs,
            missing=missing,
            source=request.source,
        )
    assert request.barrel_length_mm is not None
    assert request.finished_diameter_mm is not None
    assert request.plating_thickness_mm is not None
    assert request.resistivity_ohm_m is not None
    outer = request.finished_diameter_mm + 2.0 * request.plating_thickness_mm
    area_mm2 = math.pi / 4.0 * (outer**2 - request.finished_diameter_mm**2)
    value = request.resistivity_ohm_m * (request.barrel_length_mm * 1e-3) / (
        area_mm2 * 1e-6
    )
    return PhysicsEstimate(
        status="estimated",
        quantity="via_dc_resistance",
        value=value,
        unit="ohm",
        method_id="cylindrical_plated_barrel_rho_l_over_a",
        exact_inputs=inputs,
        source=request.source,
        sensitivity={
            "length_plus_1pct_relative_output": 0.01,
            "resistivity_plus_1pct_relative_output": 0.01,
        },
        assumptions=["Uniform annular barrel plating and DC current density."],
        limitations=[
            (
                "Does not model capture-pad spreading resistance, current crowding or "
                "plating nonuniformity."
            ),
            (
                "Source applicability requires M3 and physical correlation, when "
                "claimed, requires M8."
            ),
        ],
    )


def estimate_voltage_drop(request: VoltageDropRequest) -> PhysicsEstimate:
    inputs = request.model_dump(mode="json", exclude={"source"})
    missing = [name for name, value in inputs.items() if value is None] + _source_missing(
        request.source
    )
    if missing:
        return _unknown(
            quantity="voltage_drop",
            unit="V",
            method_id="ohms_law_v_equals_ir",
            exact_inputs=inputs,
            missing=missing,
            source=request.source,
        )
    assert request.resistance_ohm is not None and request.current_a is not None
    value = request.resistance_ohm * request.current_a
    return PhysicsEstimate(
        status="estimated",
        quantity="voltage_drop",
        value=value,
        unit="V",
        method_id="ohms_law_v_equals_ir",
        exact_inputs=inputs,
        source=request.source,
        sensitivity={
            "resistance_plus_1pct_relative_output": 0.01,
            "current_plus_1pct_relative_output": 0.01,
        },
        assumptions=[
            "DC or quasi-static current represented by the supplied current value."
        ],
        limitations=[
            "Does not infer transient current, resistance or temperature dependence."
        ],
    )


def estimate_loss_budget(request: LossBudgetRequest) -> PhysicsEstimate:
    losses = request.stage_losses_db
    inputs: dict[str, float | str | list[float] | None] = {"stage_losses_db": losses}
    missing = ([] if losses else ["stage_losses_db"]) + _source_missing(request.source)
    if missing:
        return _unknown(
            quantity="aggregate_loss",
            unit="dB",
            method_id="explicit_db_stage_sum",
            exact_inputs=inputs,
            missing=missing,
            source=request.source,
        )
    assert losses is not None
    return PhysicsEstimate(
        status="estimated",
        quantity="aggregate_loss",
        value=sum(losses),
        unit="dB",
        method_id="explicit_db_stage_sum",
        exact_inputs=inputs,
        source=request.source,
        assumptions=[
            "Each supplied stage loss uses compatible dB reference and sign convention."
        ],
        limitations=["No stage loss is inferred from geometry or material memory."],
    )


def estimate_first_order_temperature(request: ThermalEstimateRequest) -> PhysicsEstimate:
    inputs = request.model_dump(mode="json", exclude={"source"})
    missing = [name for name, value in inputs.items() if value is None] + _source_missing(
        request.source
    )
    if missing:
        return _unknown(
            quantity="first_order_temperature",
            unit="degC",
            method_id="ambient_plus_power_times_theta",
            exact_inputs=inputs,
            missing=missing,
            source=request.source,
        )
    assert request.power_w is not None
    assert request.theta_c_per_w is not None
    assert request.ambient_c is not None
    value = request.ambient_c + request.power_w * request.theta_c_per_w
    return PhysicsEstimate(
        status="estimated",
        quantity="first_order_temperature",
        value=value,
        unit="degC",
        method_id="ambient_plus_power_times_theta",
        exact_inputs=inputs,
        source=request.source,
        sensitivity={
            "power_plus_1pct_delta_c": request.power_w
            * 0.01
            * request.theta_c_per_w,
            "theta_plus_1pct_delta_c": request.power_w
            * request.theta_c_per_w
            * 0.01,
        },
        assumptions=[
            "Supplied theta is applicable to the exact assembly and operating conditions."
        ],
        limitations=[
            (
                "First-order estimate only; no enclosure airflow, spreading or "
                "nonlinear material model."
            ),
            "Thermal performance claims require M8 measurement/correlation.",
        ],
    )
