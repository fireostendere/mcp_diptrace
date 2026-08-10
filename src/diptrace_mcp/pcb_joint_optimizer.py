from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from .domain import StrictModel


class PCBHardViolations(StrictModel):
    safety: int = Field(default=0, ge=0)
    mechanical: int = Field(default=0, ge=0)
    connectivity: int = Field(default=0, ge=0)
    drc: int = Field(default=0, ge=0)
    reference_path: int = Field(default=0, ge=0)
    manufacturing: int = Field(default=0, ge=0)

    def vector(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.safety,
            self.mechanical,
            self.connectivity,
            self.drc,
            self.reference_path,
            self.manufacturing,
        )

    def total(self) -> int:
        return sum(self.vector())


class PCBSoftScore(StrictModel):
    placement: float = Field(default=0.0, ge=0.0)
    routing: float = Field(default=0.0, ge=0.0)
    vias: float = Field(default=0.0, ge=0.0)
    signal_integrity: float = Field(default=0.0, ge=0.0)
    power_integrity: float = Field(default=0.0, ge=0.0)
    return_path: float = Field(default=0.0, ge=0.0)
    emi_risk: float = Field(default=0.0, ge=0.0)
    thermal_risk: float = Field(default=0.0, ge=0.0)
    manufacturing: float = Field(default=0.0, ge=0.0)

    def total(self) -> float:
        return math.fsum(
            (
                self.placement,
                self.routing,
                self.vias,
                self.signal_integrity,
                self.power_integrity,
                self.return_path,
                self.emi_risk,
                self.thermal_risk,
                self.manufacturing,
            )
        )


CandidateSource = Literal[
    "internal",
    "existing_board",
    "local_router",
    "external_router",
    "external_solver",
    "operator",
]


class PCBOptimizationCandidate(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=256)
    source: CandidateSource = "internal"
    hard: PCBHardViolations = Field(default_factory=PCBHardViolations)
    soft: PCBSoftScore = Field(default_factory=PCBSoftScore)
    plan_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PCBOptimizationResult(StrictModel):
    selected: PCBOptimizationCandidate
    ranking: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=1)
    selection_key: list[float | int | str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PCBBenchmarkFamily(StrictModel):
    family_id: str
    description: str
    trap_goals: list[str] = Field(default_factory=list)
    acceptance: Literal["synthetic_regression_only"] = "synthetic_regression_only"
    requires_real_diptrace_acceptance: bool = True


_BENCHMARKS: tuple[PCBBenchmarkFamily, ...] = (
    PCBBenchmarkFamily(
        family_id="mcu_decoupling_crystal",
        description="MCU with local decoupling and crystal/timing support",
        trap_goals=[
            "decoupling proximity",
            "crystal loop compactness",
            "reference continuity",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="regulator_power",
        description="LDO and switching-regulator placement/routing",
        trap_goals=[
            "switch-node confinement",
            "hot-loop compactness",
            "power distribution",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="adc_mixed_signal",
        description="ADC/sensor mixed analog and digital design",
        trap_goals=[
            "precision-net protection",
            "continuous reference",
            "aggressor separation",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="current_sense",
        description="Current-shunt and precision-sense topology",
        trap_goals=[
            "Kelvin candidate preservation",
            "high-current versus sense separation",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="high_speed_differential",
        description="USB and other controlled high-speed differential links",
        trap_goals=[
            "pair symmetry",
            "skew and via budget",
            "reference continuity",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="ethernet_can_interface",
        description="Ethernet/CAN/interface blocks and connectors",
        trap_goals=[
            "connector flow",
            "critical-net ordering",
            "return transitions",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="rf_antenna",
        description="RF module, matching network and antenna region",
        trap_goals=[
            "RF path priority",
            "matching-network compactness",
            "keepout/reference discipline",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="high_current_power",
        description="Higher-current power distribution",
        trap_goals=[
            "current-aware copper strategy",
            "power-via capacity evidence boundary",
        ],
    ),
    PCBBenchmarkFamily(
        family_id="multilayer_controlled_impedance",
        description="Multilayer controlled-impedance routing",
        trap_goals=[
            "stackup/reference selection",
            "impedance evidence provenance",
            "layer-transition return path",
        ],
    ),
)


def _validate_candidate(candidate: PCBOptimizationCandidate) -> None:
    values = (
        candidate.soft.placement,
        candidate.soft.routing,
        candidate.soft.vias,
        candidate.soft.signal_integrity,
        candidate.soft.power_integrity,
        candidate.soft.return_path,
        candidate.soft.emi_risk,
        candidate.soft.thermal_risk,
        candidate.soft.manufacturing,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("candidate soft scores must be finite")


def candidate_selection_key(
    candidate: PCBOptimizationCandidate,
) -> tuple[int, int, int, int, int, int, float, str]:
    """Return a deterministic lexicographic key with hard violations dominant."""

    _validate_candidate(candidate)
    return (*candidate.hard.vector(), candidate.soft.total(), candidate.candidate_id)


def select_pcb_candidate(
    candidates: list[PCBOptimizationCandidate],
    *,
    max_candidates: int = 128,
) -> PCBOptimizationResult:
    """Select the best bounded whole-board candidate without applying any edit."""

    if max_candidates < 1 or max_candidates > 10_000:
        raise ValueError("max_candidates must be between 1 and 10000")
    if not candidates:
        raise ValueError("at least one PCB optimization candidate is required")
    if len(candidates) > max_candidates:
        raise ValueError("PCB optimization candidate count exceeds the bounded limit")
    ids = [item.candidate_id for item in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("PCB optimization candidate_id values must be unique")
    ranked = sorted(candidates, key=candidate_selection_key)
    selected = ranked[0]
    key = candidate_selection_key(selected)
    return PCBOptimizationResult(
        selected=selected,
        ranking=[item.candidate_id for item in ranked],
        candidate_count=len(ranked),
        selection_key=[*key[:-1], key[-1]],
        assumptions=[
            (
                "Hard safety/mechanical/connectivity/DRC/reference/manufacturing "
                "violations are lexicographically dominant over every soft metric."
            ),
            (
                "Soft score remains decomposed; the total is only a deterministic "
                "tie-break among candidates with identical hard-violation vectors."
            ),
            (
                "External routers and solvers are candidate/evidence sources only and "
                "cannot bypass the normal preview, SHA, policy, transaction or review path."
            ),
        ],
        limitations=[
            (
                "Selection compares supplied candidate metrics; it does not manufacture "
                "missing SI/PI/thermal/EMC evidence."
            ),
            (
                "The optimizer returns a candidate and plan references only; applying "
                "semantic operations remains an application-layer responsibility."
            ),
            (
                "A synthetic benchmark PASS is not real DipTrace copper-refill, plane, "
                "via-structure or native round-trip acceptance."
            ),
        ],
    )


def pcb_benchmark_catalog() -> list[PCBBenchmarkFamily]:
    """Return the deterministic Generation D engineering-trap benchmark catalog."""

    return [item.model_copy(deep=True) for item in _BENCHMARKS]
