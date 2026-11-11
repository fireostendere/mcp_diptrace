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


def test_bom_grouping_keeps_parts_with_different_supplier_codes_apart() -> None:
    from diptrace_mcp.bom import group_bom
    from diptrace_mcp.domain import BomRecord

    def cap(refdes: str, lcsc: str) -> BomRecord:
        return BomRecord(
            stable_id=refdes,
            refdes=[refdes],
            quantity=1,
            value="100nF",
            pattern="C0603",
            fields={"LCSC": lcsc},
        )

    grouped = group_bom([cap("C1", "C14663"), cap("C2", "C1591"), cap("C3", "C14663")])
    assert sorted(item.refdes for item in grouped) == [["C1", "C3"], ["C2"]]


def test_unrouted_net_has_no_length(tmp_path: Path) -> None:
    result = _call(tmp_path, "measure_net_lengths", {"path": "pcb.xml", "nets": ["VCC"]})
    measurement = result["result"]["measurements"][0]
    assert measurement["routed_length_status"] == "unavailable"
    assert "net_unrouted" in measurement["routed_length_unavailable_reasons"]


def test_every_tool_declares_its_side_effects(listed_tools: dict[str, Any]) -> None:
    hints = {name: tool.annotations for name, tool in listed_tools.items()}
    assert all(item is not None and item.readOnlyHint is not None for item in hints.values())
    assert hints["list_nets"].readOnlyHint is True
    assert hints["move_components"].readOnlyHint is False
    assert hints["move_components"].destructiveHint is False
    assert hints["delete_trace"].destructiveHint is True
    assert hints["pipeline_source_component"].openWorldHint is True
    assert "selector" in listed_tools["delete_wire"].inputSchema["required"]
    assert "selector" not in listed_tools["query_objects"].inputSchema.get("required", [])


def test_unknown_arguments_are_refused(tmp_path: Path) -> None:
    result = _call(tmp_path, "get_document_info", {"path": "pcb.xml", "bogus": 1})
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert "bogus" in result["error"]["message"]


def test_read_tools_report_ok(tmp_path: Path) -> None:
    assert _call(tmp_path, "summarize_design", {"path": "pcb.xml"})["ok"] is True
    assert _call(tmp_path, "list_nets", {"path": "pcb.xml"})["ok"] is True


def test_sync_commit_requires_the_previewed_schematic_sha(tmp_path: Path) -> None:
    arguments = {"schematic_path": "schematic.xml", "pcb_path": "pcb.xml", "dry_run": False}
    result = _call(tmp_path, "sync_schematic_to_pcb", {**arguments, "expected_sha256": "0" * 64})
    assert result["error"]["code"] == "SAFETY_GATE"
    result = _call(
        tmp_path,
        "sync_schematic_to_pcb",
        {**arguments, "expected_sha256": "0" * 64, "expected_schematic_sha256": "1" * 64},
    )
    assert result["error"]["code"] == "CONFLICT"


def test_testpoint_readers_refuse_a_schematic(tmp_path: Path) -> None:
    assert _call(tmp_path, "list_testpoints", {"path": "schematic.xml"})["ok"] is False
