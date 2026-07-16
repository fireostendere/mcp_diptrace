from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.operations import MoveComponentsOperation
from diptrace_mcp.placement import (
    PlacementConfig,
    PlacementProposal,
    generate_placement_candidates,
    plan_component_placement,
    score_placement_proposal,
)
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _overlapping_board(*, locked: bool = False) -> bytes:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='1']")
    assert component is not None
    component.set("X", "10.2")
    component.set("Locked", "Y" if locked else "N")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_local_placer_legalizes_overlap_with_score_breakdown(tmp_path: Path) -> None:
    board = tmp_path / "board.xml"
    board.write_bytes(_overlapping_board())
    snapshot = build_snapshot(DipTraceDocument.load(board, 10_000_000))
    config = PlacementConfig(
        selector=QuerySelector(refdes=["U1"]),
        grid=0.5,
        search_steps=5,
    )

    candidates = generate_placement_candidates(snapshot, config)
    planned = plan_component_placement(snapshot, config)

    assert len(candidates) == 1
    assert any(candidate["legal"] for candidate in candidates[0]["candidates"])
    assert planned.metrics["changed_count"] == 1
    assert planned.metrics["remaining_violation_count"] == 0
    assert planned.unresolved == []
    assert len(planned.operations) == 1
    assert isinstance(planned.operations[0], MoveComponentsOperation)
    assert set(planned.score) >= {
        "overlap",
        "containment",
        "keepout",
        "wirelength",
        "movement",
        "rotation",
        "side_change",
        "total",
    }


def test_locked_illegal_component_is_unresolved_and_not_moved(tmp_path: Path) -> None:
    board = tmp_path / "board.xml"
    board.write_bytes(_overlapping_board(locked=True))
    snapshot = build_snapshot(DipTraceDocument.load(board, 10_000_000))

    planned = plan_component_placement(
        snapshot,
        PlacementConfig(selector=QuerySelector(refdes=["U1"])),
    )

    assert planned.operations == []
    assert planned.unresolved[0]["reason"] == "locked_component_illegal"
    assert planned.candidates[0]["status"] == "locked_unchanged"


def test_score_proposal_rejects_overlap_with_large_penalty(tmp_path: Path) -> None:
    board = tmp_path / "board.xml"
    board.write_bytes(FIXTURES.joinpath("pcb.xml").read_bytes())
    snapshot = build_snapshot(DipTraceDocument.load(board, 10_000_000))
    component = next(item for item in snapshot.board.components if item.refdes == "U1")  # type: ignore[union-attr]

    score, violations = score_placement_proposal(
        snapshot,
        [PlacementProposal(object_id=component.stable_id, x=10.2, y=10)],
        PlacementConfig(),
    )

    assert score["overlap"] > 0
    assert any(item["reason"] == "component_spacing" for item in violations)


def test_placement_plan_commit_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    source = _overlapping_board()
    board.write_bytes(source)
    service = _service(workspace, tmp_path / "state")

    planned = service.plan_component_placement(
        {"refdes": ["U1"]},
        str(board),
        grid=0.5,
        search_steps=5,
    )
    plan = planned["result"]["plan"]
    assert plan["metrics"]["validation"] == {
        "placement_errors_before": 1,
        "placement_errors_after": 0,
        "no_new_placement_errors": True,
    }

    committed = service.apply_component_placement_plan(plan["plan_id"], dry_run=False)
    assert committed["transaction"]["status"] == "committed"
    root = ET.fromstring(board.read_bytes())
    component = root.find("./Board/Components/Component[@Id='1']")
    assert component is not None
    assert component.get("X") != "10.2"

    service.rollback_transaction(
        committed["transaction"]["txid"],
        committed["transaction"]["committed_sha256"],
    )
    assert board.read_bytes() == source
