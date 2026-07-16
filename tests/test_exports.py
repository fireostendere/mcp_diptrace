from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path, raw: bytes | None = None) -> DipTraceService:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "board.xml").write_bytes(raw or (FIXTURES / "pcb.xml").read_bytes())
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=tmp_path / "state",
            max_document_bytes=10_000_000,
        )
    )


def test_bom_export_is_bounded_and_does_not_disclose_state_path(tmp_path: Path) -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes().replace(b"<Value>10k</Value>", b"<Value>=cmd</Value>")
    service = _service(tmp_path, raw)

    result = service.export_bom("board.xml")
    record = result["result"]["export"]
    export_id = record["export_id"]

    assert result["ok"] is True
    assert all(uri.startswith(f"diptrace://export/{export_id}/") for uri in result["resources"])
    assert str(tmp_path) not in str(record)
    assert "'=cmd" in service.export_resource(export_id, "bom.csv")
    assert service.list_exports()["result"]["matched_count"] == 1


def test_release_manifest_is_explicitly_not_native_fabrication(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.export_fabrication_outputs("board.xml")
    manifest = result["result"]["export"]["manifest"]

    assert manifest["kind"] == "fabrication_manifest"
    assert "gerber" in manifest["not_generated"]
    assert any("not fabrication-ready" in item for item in result["limitations"])

    with pytest.raises(CapabilityUnavailableError):
        service.export_fabrication_outputs("board.xml", request_native_outputs=True)
