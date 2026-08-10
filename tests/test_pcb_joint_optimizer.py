from __future__ import annotations

import math

import pytest

from diptrace_mcp.pcb_joint_optimizer import (
    PCBHardViolations,
    PCBOptimizationCandidate,
    PCBSoftScore,
    candidate_selection_key,
    pcb_benchmark_catalog,
    select_pcb_candidate,
)


def _candidate(
    candidate_id: str,
    *,
    hard: PCBHardViolations | None = None,
    soft: PCBSoftScore | None = None,
    plan_refs: list[str] | None = None,
) -> PCBOptimizationCandidate:
    return PCBOptimizationCandidate(
        candidate_id=candidate_id,
        hard=hard or PCBHardViolations(),
        soft=soft or PCBSoftScore(),
        plan_refs=plan_refs or [],
    )


def test_generation_d_zero_hard_violations_beat_any_soft_score() -> None:
    clean_but_expensive = _candidate(
        "clean",
        soft=PCBSoftScore(
            placement=1000.0,
            routing=1000.0,
            signal_integrity=1000.0,
            power_integrity=1000.0,
        ),
    )
    pretty_but_drc_broken = _candidate(
        "broken",
        hard=PCBHardViolations(drc=1),
        soft=PCBSoftScore(placement=0.0, routing=0.0),
    )

    result = select_pcb_candidate([pretty_but_drc_broken, clean_but_expensive])

    assert result.selected.candidate_id == "clean"
    assert result.ranking[0] == "clean"
    assert result.selected.hard.total() == 0


def test_generation_d_hard_violation_categories_are_lexicographically_dominant() -> None:
    mechanical = _candidate(
        "mechanical",
        hard=PCBHardViolations(mechanical=1),
    )
    safety = _candidate(
        "safety",
        hard=PCBHardViolations(safety=1),
    )

    result = select_pcb_candidate([safety, mechanical])

    assert result.selected.candidate_id == "mechanical"
    assert candidate_selection_key(mechanical) < candidate_selection_key(safety)


def test_generation_d_soft_score_is_decomposed_and_breaks_equal_hard_ties() -> None:
    better = _candidate(
        "better",
        soft=PCBSoftScore(
            placement=1.0,
            routing=2.0,
            vias=3.0,
            signal_integrity=4.0,
            power_integrity=5.0,
            return_path=6.0,
            emi_risk=7.0,
            thermal_risk=8.0,
            manufacturing=9.0,
        ),
    )
    worse = _candidate(
        "worse",
        soft=PCBSoftScore(routing=100.0),
    )

    assert better.soft.total() == pytest.approx(45.0)
    result = select_pcb_candidate([worse, better])
    assert result.selected.candidate_id == "better"


def test_generation_d_tie_break_is_deterministic_by_candidate_id() -> None:
    result = select_pcb_candidate([_candidate("zeta"), _candidate("alpha")])

    assert result.ranking == ["alpha", "zeta"]
    assert result.selected.candidate_id == "alpha"


def test_generation_d_preserves_plan_references_without_applying_them() -> None:
    candidate = _candidate(
        "plan",
        plan_refs=["placement-plan:abc", "routing-plan:def"],
    )

    result = select_pcb_candidate([candidate])

    assert result.selected.plan_refs == ["placement-plan:abc", "routing-plan:def"]
    assert any("application-layer responsibility" in item for item in result.limitations)


def test_generation_d_bounds_candidate_count_and_requires_unique_ids() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_pcb_candidate([])
    with pytest.raises(ValueError, match="bounded limit"):
        select_pcb_candidate([_candidate("a"), _candidate("b")], max_candidates=1)
    with pytest.raises(ValueError, match="must be unique"):
        select_pcb_candidate([_candidate("same"), _candidate("same")])
    for value in (0, 10_001):
        with pytest.raises(ValueError, match="between 1 and 10000"):
            select_pcb_candidate([_candidate("a")], max_candidates=value)


def test_generation_d_rejects_nonfinite_soft_scores() -> None:
    candidate = _candidate(
        "nonfinite",
        soft=PCBSoftScore(routing=math.inf),
    )

    with pytest.raises(ValueError, match="must be finite"):
        select_pcb_candidate([candidate])


def test_generation_d_benchmark_catalog_covers_engineering_traps_without_claiming_native_acceptance() -> None:
    catalog = pcb_benchmark_catalog()
    ids = {item.family_id for item in catalog}

    assert {
        "mcu_decoupling_crystal",
        "regulator_power",
        "adc_mixed_signal",
        "current_sense",
        "high_speed_differential",
        "ethernet_can_interface",
        "rf_antenna",
        "high_current_power",
        "multilayer_controlled_impedance",
    }.issubset(ids)
    assert all(item.acceptance == "synthetic_regression_only" for item in catalog)
    assert all(item.requires_real_diptrace_acceptance for item in catalog)
