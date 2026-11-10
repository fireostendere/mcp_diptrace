"""The pipeline tools write files, so they obey the same roots and policy as other writes."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"


def _call(tmp_path: Path, tool: str, arguments: dict[str, Any], **settings: Any) -> dict[str, Any]:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    for name in ("pcb.xml", "pcb_4layer.xml", "schematic.xml"):
        shutil.copyfile(FIXTURES / name, workspace / name)
    server = create_server(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=tmp_path / "state",
            **settings,
        )
    )
    result = asyncio.run(server.call_tool(tool, arguments))
    return result[1] if isinstance(result, tuple) else result.structuredContent


NATIVEIZE = {"input_path": "pcb.xml", "template_path": "pcb_4layer.xml"}


def test_nativeize_refuses_output_outside_allowed_roots(tmp_path: Path) -> None:
    outside = tmp_path / "outside.xml"
    result = _call(
        tmp_path, "pipeline_nativeize_document", {**NATIVEIZE, "output_path": str(outside)}
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "SAFETY_GATE"
    assert not outside.exists()


def test_nativeize_refuses_to_overwrite(tmp_path: Path) -> None:
    result = _call(
        tmp_path, "pipeline_nativeize_document", {**NATIVEIZE, "output_path": "schematic.xml"}
    )
    assert result["error"]["code"] == "CONFLICT"
    assert (tmp_path / "ws/schematic.xml").read_bytes() == (FIXTURES / "schematic.xml").read_bytes()


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("pipeline_nativeize_document", {**NATIVEIZE, "output_path": "out.xml"}),
        ("pipeline_render_board_preview", {"pcb_path": "pcb.xml", "output_dir": "."}),
        ("pipeline_source_component", {"mpn_or_code": "C1234", "output_dir": "vendor"}),
    ],
)
def test_read_only_policy_denies_pipeline_writes(
    tmp_path: Path, tool: str, arguments: dict[str, Any]
) -> None:
    result = _call(tmp_path, tool, arguments, active_policy="read_only")
    assert result["error"]["code"] == "SAFETY_GATE"
    assert sorted(p.name for p in (tmp_path / "ws").iterdir()) == [
        "pcb.xml",
        "pcb_4layer.xml",
        "schematic.xml",
    ]


def test_run_review_refuses_a_board_profile_on_a_schematic(tmp_path: Path) -> None:
    result = _call(tmp_path, "run_review", {"profile": "dfm_basic", "path": "schematic.xml"})
    assert result["ok"] is False
    result = _call(tmp_path, "run_review", {"profile": "erc_basic", "path": "pcb.xml"})
    assert result["ok"] is False


def test_scan_lists_native_xml_extensions(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    shutil.copyfile(FIXTURES / "pcb.xml", workspace / "board.dipxml")
    result = _call(tmp_path, "scan_diptrace_documents", {})
    assert "board.dipxml" in str(result)
