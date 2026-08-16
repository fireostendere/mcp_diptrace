from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.copper_pours import add_copper_pours
from diptrace_mcp.pcb_quality import review_pcb_quality
from diptrace_mcp.pcb_whole_board import (
    PCBWholeBoardConfig,
    compact_rectangular_board_outline,
    optimize_pcb_whole_board,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _document() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "pcb.xml", MAX_BYTES)


def _ground_document() -> DipTraceDocument:
    document = _document()
    root = ET.fromstring(document.raw_bytes)
    name = root.find("./Board/Nets/Net[@Id='0']/Name")
    assert name is not None
    name.text = "GND"
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def test_quality_review_exposes_physics_unknowns_and_hard_ground_rule() -> None:
    review = review_pcb_quality(build_snapshot(_document()))

    assert review.hard_error_count >= 1
    assert "two_layer_ground_pour_missing" in review.review_priorities
    assert review.unknowns
    assert {item.principle_id for item in review.physics_principles} == {
        "continuous_reference_plane",
        "minimize_high_didt_loop",
        "short_decoupling_loop",
    }


def test_ground_pours_thermals_and_dense_stitching_improve_quality() -> None:
    result = add_copper_pours(
        _ground_document(),
        net="GND",
        layers=("Top", "Bottom"),
        stitch_pitch_mm=2.0,
    )

    review = review_pcb_quality(build_snapshot(result.document))

    assert review.ground_pour_layer_count == 2
    assert review.ground_stitching_via_count == result.stitch_via_count
    assert review.stitching_coverage_ratio is not None
    assert "two_layer_ground_pour_missing" not in review.review_priorities
    assert "ground_thermal_not_four_spoke" not in review.review_priorities


def test_rectangular_outline_compaction_centers_occupied_geometry() -> None:
    compacted, changed, before, after = compact_rectangular_board_outline(_document())

    assert changed is True
    assert before is not None and after is not None
    assert (after["max_x"] - after["min_x"]) < (before["max_x"] - before["min_x"])
    snapshot = build_snapshot(compacted)
    assert snapshot.board is not None and snapshot.board.outline is not None
    assert snapshot.board.outline["bbox"] == after


def test_whole_board_pipeline_routes_compacts_and_repairs_silkscreen() -> None:
    result = optimize_pcb_whole_board(
        _document(),
        config=PCBWholeBoardConfig(add_two_layer_ground=False),
    )

    assert result.routing.routing.routed
    assert result.outline_changed is True
    assert "add_trace" in result.stage_operation_kinds
    assert "compact_board_outline" in result.stage_operation_kinds
    assert result.quality.board_area_mm2 < 1_500.0
    assert result.quality.physics_principles


def test_guarded_whole_board_plan_binds_preview_identity_and_stale_sha(tmp_path: Path) -> None:
    import pytest

    from diptrace_mcp.backups import BackupStore
    from diptrace_mcp.config import Settings
    from diptrace_mcp.errors import Sha256MismatchError
    from diptrace_mcp.pcb_whole_board import (
        apply_pcb_whole_board_plan_guarded,
        plan_pcb_whole_board_guarded,
    )
    from diptrace_mcp.plans import PlanStore
    from diptrace_mcp.policy import Policy

    target = tmp_path / "pcb.xml"
    target.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state = tmp_path / "state"
    plans = PlanStore(state)
    backups = BackupStore(state)
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=state,
    )
    policy = Policy("automation")
    document = DipTraceDocument.load(target, MAX_BYTES)
    planned = plan_pcb_whole_board_guarded(
        document,
        plans,
        config=PCBWholeBoardConfig(add_two_layer_ground=False),
    )
    assert planned["plan_identity_sha256"]
    assert planned["candidate_sha256"]
    assert planned["resources"]
    if planned["hard_error_count"] == 0 and not planned["no_changes"]:
        preview = apply_pcb_whole_board_plan_guarded(
            plans,
            backups,
            policy,
            settings,
            planned["plan"]["plan_id"],
            dry_run=True,
            expected_sha256=document.sha256,
        )
        assert preview["candidate_sha256"] == planned["candidate_sha256"]
        assert preview["plan_identity_sha256"] == planned["plan_identity_sha256"]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(Sha256MismatchError):
        apply_pcb_whole_board_plan_guarded(
            plans,
            backups,
            policy,
            settings,
            planned["plan"]["plan_id"],
            dry_run=True,
            expected_sha256=document.sha256,
        )
