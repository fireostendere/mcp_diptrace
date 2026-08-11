from __future__ import annotations

from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_candidate_ensemble import (
    PCBEnsembleConfig,
    build_pcb_candidate_ensemble,
)
from diptrace_mcp.pcb_joint_optimizer import candidate_selection_key
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot():
    return build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))


def test_pcb_candidate_ensemble_generates_distinct_engineering_profiles() -> None:
    result = build_pcb_candidate_ensemble(_snapshot())

    profiles = {item.profile for item in result.candidates}
    assert profiles == {
        "balanced",
        "critical_nets",
        "noise_aware",
        "support_compact",
        "existing_board",
    }
    assert result.selection.candidate_count == len(result.candidates)
    assert result.selected_profile in profiles
    assert result.limitations
    assert all(item.routing_unknown_count >= 0 for item in result.candidates)


def test_pcb_candidate_ensemble_uses_existing_hard_first_generation_d_selector() -> None:
    result = build_pcb_candidate_ensemble(_snapshot())
    ranked = sorted(
        (item.optimization for item in result.candidates),
        key=candidate_selection_key,
    )

    assert result.selection.ranking == [item.candidate_id for item in ranked]
    assert result.selection.selected.candidate_id == ranked[0].candidate_id


def test_pcb_candidate_ensemble_is_deterministic_and_deduplicates_profiles() -> None:
    config = PCBEnsembleConfig(
        profiles=["balanced", "balanced", "noise_aware"],
        include_existing_board=False,
    )
    first = build_pcb_candidate_ensemble(_snapshot(), config=config)
    second = build_pcb_candidate_ensemble(_snapshot(), config=config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [item.profile for item in first.candidates] == ["balanced", "noise_aware"]
