from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import CapabilityUnavailableError, EditError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"
COPIED = ("pcb.xml", "schematic.xml", "pattern_library.xml")


def _service(tmp_path: Path) -> tuple[DipTraceService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in COPIED:
        shutil.copyfile(FIXTURES / name, workspace / name)
    return (
        DipTraceService(
            Settings(
                workspace=workspace,
                allowed_roots=(workspace,),
                state_dir=tmp_path / "state",
                max_document_bytes=10_000_000,
            )
        ),
        workspace,
    )


def test_rank_schematic_placement_candidates_selects_ranked_candidate(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.rank_schematic_placement_candidates(str(workspace / "schematic.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["selected"]["candidate"]["candidate_id"]
    assert payload["candidates"]
    ranked = [
        (tuple(item["rank_key"]), item["candidate"]["candidate_id"])
        for item in payload["candidates"]
    ]
    assert ranked == sorted(ranked)
    assert (
        payload["candidates"][0]["candidate"]["candidate_id"]
        == payload["selected"]["candidate"]["candidate_id"]
    )
    assert any(
        "builtin" in limitation for limitation in result["limitations"]
    )


def test_plan_and_apply_schematic_placement_repair_round_trip(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    path = str(workspace / "schematic.xml")
    original_sha = service.document_info(path)["result"]["sha256"]

    plan_response = service.plan_schematic_placement_repair(path)
    plan = plan_response["result"]["plan"]
    assert plan["plan_type"] == "schematic_placement_repair"
    assert plan["operations"]
    assert plan_response["ok"] is True

    dry_run = service.apply_schematic_placement_repair_plan(plan["plan_id"], dry_run=True)
    assert dry_run["ok"] is True

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True
    assert committed["result"]["changed_ids"]

    updated_info = service.document_info(path)
    assert updated_info["result"]["sha256"] != original_sha


def test_plan_schematic_placement_repair_honours_operator_moves(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    path = str(workspace / "schematic.xml")

    with pytest.raises(EditError, match="unknown part"):
        service.plan_schematic_placement_repair(
            path, moves=[{"part": "X9", "x_mm": 1.0, "y_mm": 2.0}]
        )


def test_plan_schematic_placement_repair_requires_schematic_document(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    with pytest.raises(CapabilityUnavailableError):
        service.plan_schematic_placement_repair(str(workspace / "pcb.xml"))


def test_compare_pcb_placement_candidates_ranks_profiles(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.compare_pcb_placement_candidates(str(workspace / "pcb.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["selected_profile"]
    assert {item["profile"] for item in payload["candidates"]} >= {payload["selected_profile"]}
    assert payload["limitations"]


def test_recommend_patterns_applies_hard_filters(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.recommend_patterns(
        {"pad_count": 2},
        str(workspace / "pattern_library.xml"),
        limit=5,
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["total_patterns"] >= 1
    assert len(payload["candidates"]) <= 5
    for candidate in payload["candidates"]:
        assert candidate["features"]["pad_count"] == 2


def test_recommend_patterns_requires_library_document(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    with pytest.raises(CapabilityUnavailableError):
        service.recommend_patterns({"pad_count": 2}, str(workspace / "pcb.xml"))


def test_analyze_release_readiness_reports_dfm_findings(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.analyze_release_readiness(str(workspace / "pcb.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"]
    assert isinstance(payload["findings"], list)
    assert payload["metrics"]
