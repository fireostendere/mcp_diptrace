from pathlib import Path

import pytest

from diptrace_mcp.config import PolicyProfile, Settings
from diptrace_mcp.errors import PolicyDeniedError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path, profile: PolicyProfile) -> DipTraceService:
    workspace = tmp_path / profile
    workspace.mkdir()
    (workspace / "board.xml").write_bytes((FIXTURES / "pcb.xml").read_bytes())
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=tmp_path / f"state-{profile}",
            active_policy=profile,
        )
    )


def test_review_policy_allows_preview_but_denies_commit(tmp_path: Path) -> None:
    service = _service(tmp_path, "review")

    preview = service.move_components(
        {"refdes": ["R1"]}, dx=1.0, path="board.xml", dry_run=True
    )
    tx = preview["transaction"]

    with pytest.raises(PolicyDeniedError) as error:
        service.commit_transaction(tx["txid"], tx["source_sha256"])

    assert error.value.payload.code == "policy_denied"
    assert service.get_capabilities("board.xml")["policy"]["allows_commit"] is False


def test_read_only_policy_denies_semantic_preview(tmp_path: Path) -> None:
    service = _service(tmp_path, "read_only")

    with pytest.raises(PolicyDeniedError) as error:
        service.move_components(
            {"refdes": ["R1"]}, dx=1.0, path="board.xml", dry_run=True
        )

    assert error.value.payload.details["active_profile"] == "read_only"
