from __future__ import annotations

import math
from typing import Any, Literal

from .domain import ImpedanceInput, ImpedanceResult, StackupModel
from .errors import CapabilityUnavailableError, InsufficientStackupDataError

_FREE_SPACE_IMPEDANCE_OHM = 376.730313668


def _sech(value: float) -> float:
    return 1.0 / math.cosh(value)


def _air_impedance(normalized_width: float) -> float:
    factor = 6.0 + (2.0 * math.pi - 6.0) * math.exp(
        -(30.666 / normalized_width) ** 0.7528
    )
    return _FREE_SPACE_IMPEDANCE_OHM / (2.0 * math.pi) * math.log(
        factor / normalized_width + math.sqrt(1.0 + (2.0 / normalized_width) ** 2)
    )


def _effective_dielectric_constant(normalized_width: float, er: float) -> float:
    u = normalized_width
    a = (
        1.0
        + math.log((u**4 + (u / 52.0) ** 2) / (u**4 + 0.432)) / 49.0
        + math.log(1.0 + (u / 18.1) ** 3) / 18.7
    )
    b = 0.564 * ((er - 0.9) / (er + 3.0)) ** 0.053
    return float(
        (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 + 10.0 / u) ** (-a * b)
    )


def _filling_factor(normalized_width: float, er: float) -> float:
    effective = _effective_dielectric_constant(normalized_width, er)
    return (2.0 * effective - er - 1.0) / (er - 1.0)


def _microstrip_quasi_static(values: ImpedanceInput) -> tuple[float, float]:
    u = values.width_mm / values.dielectric_height_mm
    if values.copper_thickness_mm > 0:
        normalized_thickness = values.copper_thickness_mm / values.dielectric_height_mm
        coth = 1.0 / math.tanh(math.sqrt(6.517 * u))
        delta_u_air = normalized_thickness / math.pi * math.log(
            1.0 + 4.0 * math.e / (normalized_thickness * coth * coth)
        )
        delta_u_dielectric = 0.5 * delta_u_air * (
            1.0 + _sech(math.sqrt(values.dielectric_constant - 1.0))
        )
        u_air = u + delta_u_air
        u_dielectric = u + delta_u_dielectric
    else:
        u_air = u
        u_dielectric = u
    effective_er_uncorrected = _effective_dielectric_constant(
        u_dielectric, values.dielectric_constant
    )
    air_impedance_dielectric_width = _air_impedance(u_dielectric)
    impedance = air_impedance_dielectric_width / math.sqrt(effective_er_uncorrected)
    corrected_effective_er = effective_er_uncorrected * (
        _air_impedance(u_air) / air_impedance_dielectric_width
    ) ** 2
    return impedance, corrected_effective_er


def _coupled_microstrip_quasi_static(
    values: ImpedanceInput,
) -> tuple[float, float, dict[str, float]]:
    assert values.gap_mm is not None
    u = values.width_mm / values.dielectric_height_mm
    g = values.gap_mm / values.dielectric_height_mm
    er = values.dielectric_constant

    m = (
        0.2175
        + (4.113 + (20.36 / g) ** 6.0) ** -0.251
        + math.log(g**10.0 / (1.0 + (g / 13.8) ** 10.0)) / 323.0
    )
    alpha = 0.5 * math.exp(-g)
    psi = 1.0 + g / 1.45 + g**2.09 / 3.95
    phi = 0.8645 * u**0.172
    p_even = phi / (psi * (alpha * u**m + (1.0 - alpha) * u**-m))

    n = (
        1.0 / 17.7
        + math.exp(-6.424 - 0.76 * math.log(g) - (g / 0.23) ** 5.0)
    ) * math.log((10.0 + 68.3 * g**2.0) / (1.0 + 32.5 * g**3.093))
    beta = (
        0.2306
        + math.log(g**10.0 / (1.0 + (g / 3.73) ** 10.0)) / 301.8
        + math.log(1.0 + 0.646 * g**1.175) / 5.3
    )
    theta = 1.729 + 1.175 * math.log(
        1.0 + 0.627 / (g + 0.327 * g**2.17)
    )
    p_odd = p_even - theta / psi * math.exp(beta * u**-n * math.log(u))

    correction_r = 1.0 + 0.15 * (
        1.0 - math.exp(1.0 - (er - 1.0) ** 2.0 / 8.2) / (1.0 + g**-6.0)
    )
    f_odd_base = 1.0 - math.exp(
        -0.179 * g**0.15
        - 0.328 * g**correction_r / math.log(math.e + (g / 7.0) ** 2.8)
    )
    q = math.exp(-1.366 - g)
    p = math.exp(-0.745 * g**0.295) / math.cosh(g**0.68)
    f_odd = f_odd_base * math.exp(
        p * math.log(u) + q * math.sin(math.pi * math.log10(u))
    )

    mu = g * math.exp(-g) + u * (20.0 + g**2.0) / (10.0 + g**2.0)
    f_even = _filling_factor(mu, er)
    single_effective_er = _effective_dielectric_constant(u, er)
    even_effective_er = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * f_even
    odd_effective_er = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * f_odd
    single_impedance = _air_impedance(u) / math.sqrt(single_effective_er)
    even_impedance = single_impedance / (
        1.0 - single_impedance * p_even / _FREE_SPACE_IMPEDANCE_OHM
    )
    odd_impedance = single_impedance / (
        1.0 - single_impedance * p_odd / _FREE_SPACE_IMPEDANCE_OHM
    )
    return (
        2.0 * odd_impedance,
        odd_effective_er,
        {
            "even_mode_impedance_ohm": even_impedance,
            "odd_mode_impedance_ohm": odd_impedance,
            "even_mode_effective_dielectric_constant": even_effective_er,
            "odd_mode_effective_dielectric_constant": odd_effective_er,
        },
    )


def _estimate(values: ImpedanceInput) -> tuple[float, float]:
    if values.structure == "microstrip":
        return _microstrip_quasi_static(values)
    if values.structure == "differential_microstrip":
        impedance, effective_er, _modal = _coupled_microstrip_quasi_static(values)
        return impedance, effective_er
    raise CapabilityUnavailableError(
        "A verified symmetric-stripline implementation is not enabled; use an external "
        "field solver.",
        details={
            "structure": values.structure,
            "implemented_structures": ["microstrip", "differential_microstrip"],
        },
    )


def _sensitivity(values: ImpedanceInput) -> dict[str, float]:
    result: dict[str, float] = {}
    fields = ["width_mm", "dielectric_height_mm", "dielectric_constant"]
    if values.structure == "differential_microstrip":
        fields.append("gap_mm")
    for field_name in fields:
        raw_value = getattr(values, field_name)
        assert raw_value is not None
        value = float(raw_value)
        lower = values.model_copy(update={field_name: value * 0.99})
        upper = values.model_copy(update={field_name: value * 1.01})
        lower_impedance, _ = _estimate(lower)
        upper_impedance, _ = _estimate(upper)
        result[field_name] = (upper_impedance - lower_impedance) / 2.0
    if values.copper_thickness_mm > 0:
        value = values.copper_thickness_mm
        lower = values.model_copy(update={"copper_thickness_mm": value * 0.99})
        upper = values.model_copy(update={"copper_thickness_mm": value * 1.01})
        lower_impedance, _ = _estimate(lower)
        upper_impedance, _ = _estimate(upper)
        result["copper_thickness_mm"] = (upper_impedance - lower_impedance) / 2.0
    return result


def calculate_impedance(values: ImpedanceInput) -> ImpedanceResult:
    impedance, effective_er = _estimate(values)
    normalized_width = values.width_mm / values.dielectric_height_mm
    warnings: list[str] = []
    modal: dict[str, float] = {}
    if values.structure == "differential_microstrip":
        assert values.gap_mm is not None
        normalized_gap = values.gap_mm / values.dielectric_height_mm
        within_validity = 0.1 <= normalized_width <= 10.0 and normalized_gap >= 0.01
        if not within_validity:
            warnings.append(
                "Width/height or gap/height is outside the published coupled-model range."
            )
        _impedance, _effective_er, modal = _coupled_microstrip_quasi_static(values)
        if values.copper_thickness_mm > 0.0:
            warnings.append(
                "Finite copper thickness is not included by this coupled Hammerstad-Jensen "
                "implementation."
            )
        method = "Hammerstad-Jensen quasi-static parallel coupled microstrip (zero thickness)"
        validity: dict[str, Any] = {
            "normalized_width": normalized_width,
            "normalized_gap": normalized_gap,
            "published_range": {
                "min_width_over_height": 0.1,
                "max_width_over_height": 10.0,
                "min_gap_over_height": 0.01,
            },
            "inside_published_range": within_validity,
            **modal,
        }
        assumptions = [
            "Symmetric parallel edge-coupled microstrips over one continuous ideal plane.",
            "Differential impedance is twice the odd-mode characteristic impedance.",
            "Zero conductor thickness, homogeneous isotropic dielectric and quasi-static mode.",
            "No solder mask, roughness, etch trapezoid or frequency dispersion.",
        ]
    else:
        within_validity = 0.01 <= normalized_width <= 100.0
        if not within_validity:
            warnings.append(
                "Width/height is outside the published 0.01..100 effective-permittivity "
                "validation range."
            )
        method = "Hammerstad-Jensen quasi-static microstrip with finite-thickness correction"
        validity = {
            "normalized_width": normalized_width,
            "published_effective_er_range": {
                "min_width_over_height": 0.01,
                "max": 100.0,
            },
            "inside_published_range": within_validity,
        }
        assumptions = [
            "Homogeneous isotropic dielectric with the supplied relative permittivity.",
            "Continuous ideal reference plane at the supplied dielectric height.",
            "No solder mask correction, roughness, etch trapezoid or frequency dispersion.",
        ]
    if values.copper_thickness_mm > values.width_mm / 2.0:
        warnings.append("Copper thickness exceeds half the trace width.")
    if values.copper_thickness_mm > values.dielectric_height_mm / 4.0:
        warnings.append("Copper thickness is large relative to dielectric height.")
    if values.frequency_hz not in {None, 0.0}:
        warnings.append(
            "Frequency dispersion, conductor roughness, loss and radiation are not included."
        )
    delta = impedance - values.target_ohm if values.target_ohm is not None else None
    within_tolerance = None
    if delta is not None and values.tolerance_ohm is not None:
        within_tolerance = abs(delta) <= values.tolerance_ohm
    confidence: Literal["low", "medium", "high"] = (
        "medium" if within_validity and not warnings else "low"
    )
    return ImpedanceResult(
        structure=values.structure,
        estimated_impedance_ohm=impedance,
        effective_dielectric_constant=effective_er,
        method=method,
        inputs=values,
        confidence=confidence,
        delta_to_target_ohm=delta,
        within_tolerance=within_tolerance,
        sensitivity_ohm_per_percent=_sensitivity(values),
        assumptions=assumptions,
        warnings=warnings,
        validity=validity,
    )


def synthesize_microstrip_width(
    *,
    target_ohm: float,
    copper_thickness_mm: float,
    dielectric_height_mm: float,
    dielectric_constant: float,
    minimum_width_mm: float,
    maximum_width_mm: float,
    tolerance_ohm: float = 0.01,
    max_iterations: int = 100,
) -> dict[str, Any]:
    if minimum_width_mm <= 0 or maximum_width_mm <= minimum_width_mm:
        raise ValueError("width bounds must satisfy 0 < minimum < maximum")

    def evaluate(width: float) -> ImpedanceResult:
        return calculate_impedance(
            ImpedanceInput(
                structure="microstrip",
                width_mm=width,
                copper_thickness_mm=copper_thickness_mm,
                dielectric_height_mm=dielectric_height_mm,
                dielectric_constant=dielectric_constant,
                target_ohm=target_ohm,
                tolerance_ohm=tolerance_ohm,
                source="synthesis",
            )
        )

    lower_result = evaluate(minimum_width_mm)
    upper_result = evaluate(maximum_width_mm)
    if not (
        upper_result.estimated_impedance_ohm
        <= target_ohm
        <= lower_result.estimated_impedance_ohm
    ):
        raise InsufficientStackupDataError(
            "Target impedance is outside the requested width search interval.",
            details={
                "target_ohm": target_ohm,
                "minimum_width_impedance_ohm": lower_result.estimated_impedance_ohm,
                "maximum_width_impedance_ohm": upper_result.estimated_impedance_ohm,
            },
        )
    low = minimum_width_mm
    high = maximum_width_mm
    result = lower_result
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        width = (low + high) / 2.0
        result = evaluate(width)
        error = result.estimated_impedance_ohm - target_ohm
        if abs(error) <= tolerance_ohm:
            break
        if error > 0:
            low = width
        else:
            high = width
    return {
        "width_mm": result.inputs.width_mm,
        "iterations": iterations,
        "result": result.model_dump(mode="json"),
        "search_interval_mm": {"minimum": minimum_width_mm, "maximum": maximum_width_mm},
    }


def analyze_stackup(stackup: StackupModel) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    limitations: list[str] = []
    if stackup.source == "missing":
        return {
            "stackup": stackup.model_dump(mode="json"),
            "microstrip_candidates": [],
            "limitations": ["LayerStackItems are missing."],
        }
    for index, layer in enumerate(stackup.layers):
        if layer.material.material_type not in {"conductor", "plane"}:
            continue
        directions: list[int] = []
        if index == 0:
            directions.append(1)
        if index == len(stackup.layers) - 1:
            directions.append(-1)
        if not directions:
            limitations.append(
                f"{layer.layer_name or layer.layer_id}: internal stripline needs a verified "
                "stripline model or field solver."
            )
            continue
        for direction in directions:
            dielectric_layers: list[Any] = []
            cursor = index + direction
            while 0 <= cursor < len(stackup.layers):
                candidate = stackup.layers[cursor]
                if candidate.material.material_type == "dielectric":
                    dielectric_layers.append(candidate)
                    cursor += direction
                    continue
                if candidate.material.material_type in {"conductor", "plane"}:
                    break
                cursor += direction
            if not dielectric_layers or not (0 <= cursor < len(stackup.layers)):
                limitations.append(
                    f"{layer.layer_name or layer.layer_id}: no dielectric/reference layer "
                    "sequence is available."
                )
                continue
            dielectric_constants = {
                item.material.dielectric_constant
                for item in dielectric_layers
                if item.material.dielectric_constant is not None
            }
            if len(dielectric_constants) != 1 or any(
                item.material.thickness_mm is None for item in dielectric_layers
            ):
                limitations.append(
                    f"{layer.layer_name or layer.layer_id}: dielectric thickness/Dk is "
                    "missing or heterogeneous."
                )
                continue
            reference = stackup.layers[cursor]
            candidates.append(
                {
                    "signal_layer": layer.layer_name or layer.layer_id,
                    "reference_layer": reference.layer_name or reference.layer_id,
                    "copper_thickness_mm": layer.material.thickness_mm,
                    "dielectric_height_mm": sum(
                        item.material.thickness_mm or 0.0 for item in dielectric_layers
                    ),
                    "dielectric_constant": next(iter(dielectric_constants)),
                    "reference_plane_confidence": (
                        "high" if reference.material.material_type == "plane" else "low"
                    ),
                    "preliminary_only": True,
                }
            )
    return {
        "stackup": stackup.model_dump(mode="json"),
        "microstrip_candidates": candidates,
        "limitations": limitations,
    }
