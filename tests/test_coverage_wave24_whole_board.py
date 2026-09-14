from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import pcb_whole_board as whole
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError, Sha256MismatchError
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURE = Path(__file__).parent / "fixtures" / "pcb.xml"


def _context(tmp_path: Path):
    target = tmp_path / "board.xml"
    target.write_bytes(FIXTURE.read_bytes())
    document = DipTraceDocument.load(target, 10_000_000)
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    (plan_dir / "candidate.xml").write_bytes(document.raw_bytes)
    config = whole.PCBWholeBoardConfig()
    stages: list[str] = []
    identity = whole._whole_board_plan_identity(
        whole._whole_board_identity_payload(
            source_sha256=document.sha256,
            candidate_sha256=document.sha256,
            config=config,
            stage_operation_kinds=stages,
        )
    )
    plan = SimpleNamespace(
        plan_type="pcb_whole_board",
        target_path=str(target),
        source_sha256=document.sha256,
        transaction_id=None,
        status="ready",
        config=config.model_dump(mode="json"),
        metrics={
            "candidate_sha256": document.sha256,
            "plan_identity_sha256": identity,
            "stage_operation_kinds": stages,
            "quality": {"hard_error_count": 0},
        },
        model_dump=lambda **_kwargs: {"plan_id": "plan"},
    )
    store = SimpleNamespace(
        read=lambda _plan_id: plan,
        plan_dir=lambda _plan_id: plan_dir,
        update=lambda *_args, **_kwargs: plan,
    )
    policy = SimpleNamespace(require_write=lambda **_kwargs: None)
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
        max_document_bytes=10_000_000,
    )
    return target, plan_dir, plan, store, policy, settings


def test_whole_board_dry_run_and_fail_closed_matrix(tmp_path: Path) -> None:
    target, plan_dir, plan, store, policy, settings = _context(tmp_path)
    result = whole.apply_pcb_whole_board_plan_guarded(
        store, SimpleNamespace(), policy, settings, "plan", dry_run=True
    )
    assert result["ok"] and result["changed"]

    plan.plan_type = "other"
    with pytest.raises(EditError, match="Unexpected plan type"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")
    plan.plan_type = "pcb_whole_board"

    with pytest.raises(Sha256MismatchError, match="Provided SHA"):
        whole.apply_pcb_whole_board_plan_guarded(
            store,
            SimpleNamespace(),
            policy,
            settings,
            "plan",
            expected_sha256="0" * 64,
        )
    plan.status = "noop"
    assert not whole.apply_pcb_whole_board_plan_guarded(
        store, SimpleNamespace(), policy, settings, "plan"
    )["changed"]
    plan.status = "ready"

    candidate = plan_dir / "candidate.xml"
    candidate.unlink()
    with pytest.raises(EditError, match="unavailable"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")
    candidate.write_bytes(target.read_bytes())

    plan.metrics["candidate_sha256"] = "0" * 64
    with pytest.raises(Sha256MismatchError, match="candidate"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")
    plan.metrics["candidate_sha256"] = plan.source_sha256

    plan.metrics["plan_identity_sha256"] = "0" * 64
    with pytest.raises(Sha256MismatchError, match="identity"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")
    config = whole.PCBWholeBoardConfig.model_validate(plan.config)
    plan.metrics["plan_identity_sha256"] = whole._whole_board_plan_identity(
        whole._whole_board_identity_payload(
            source_sha256=plan.source_sha256,
            candidate_sha256=plan.source_sha256,
            config=config,
            stage_operation_kinds=[],
        )
    )
    plan.metrics["quality"] = {"hard_error_count": 1}
    with pytest.raises(EditError, match="hard quality"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")


def test_whole_board_detects_obsolete_source(tmp_path: Path) -> None:
    target, _plan_dir, _plan, store, policy, settings = _context(tmp_path)
    target.write_bytes(target.read_bytes().replace(b"10k", b"11k", 1))
    with pytest.raises(Sha256MismatchError, match="Document changed"):
        whole.apply_pcb_whole_board_plan_guarded(store, SimpleNamespace(), policy, settings, "plan")
