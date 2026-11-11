"""Tools added for the gaps the skills used to work around (review G1-G12)."""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server
from diptrace_mcp.xml_document import DipTraceDocument

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
BOARD = ROOT / "attiny85-arduino-clone/attiny85-arduino-clone-pcb.dipxml"


class _Client:
    def __init__(self, tmp_path: Path, **settings: Any) -> None:
        self.workspace = tmp_path / "ws"
        self.workspace.mkdir(parents=True)
        shutil.copyfile(BOARD, self.workspace / "board.dipxml")
        shutil.copyfile(FIXTURES / "schematic.xml", self.workspace / "schematic.xml")
        self.server = create_server(
            Settings(
                workspace=self.workspace,
                allowed_roots=(self.workspace,),
                state_dir=tmp_path / "state",
                **settings,
            )
        )

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = asyncio.run(self.server.call_tool(tool, arguments))
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def commit(self, tool: str, path: str, **arguments: Any) -> dict[str, Any]:
        sha = self.call("get_document_info", path=path)["document"]["sha256"]
        return self.call(tool, path=path, dry_run=False, expected_sha256=sha, **arguments)

    def board(self) -> Any:
        document = DipTraceDocument.load(self.workspace / "board.dipxml", 1 << 27)
        return build_snapshot(document).board


def test_copper_pours_are_deleted_and_recreated_with_stitching(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    assert len(client.board().copper_pours) == 2
    stitched = len(client.board().vias)

    assert client.commit("delete_copper_pours", "board.dipxml", net="GND")["written"] is True
    assert client.board().copper_pours == []
    unstitched = len(client.board().vias)
    assert unstitched < stitched  # the net's free stitching vias went with it

    added = client.commit("add_copper_pours", "board.dipxml", net="GND", stitch_pitch_mm=2.0)
    assert added["written"] is True
    assert any("native" in item for item in added["limitations"])
    board = client.board()
    assert {pour.attributes["Spoke"] for pour in board.copper_pours} == {"4 spoke"}
    assert len(board.copper_pours) == 2
    assert len(board.vias) > unstitched


def test_delete_copper_pours_reports_a_missing_pour(tmp_path: Path) -> None:
    result = _Client(tmp_path).call("delete_copper_pours", path="board.dipxml", net="VBUS")
    assert result["error"]["code"] == "OBJECT_NOT_FOUND"


def test_delete_parts_removes_an_unwired_part_and_its_net_membership(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    parts = client.call(
        "query_objects", path="schematic.xml", selector={"refdes": ["R1"]}, offset=0, limit=5
    )["result"]["items"]
    selector = {"ids": [item["stable_id"] for item in parts if item["kind"] == "part"]}

    assert client.commit("delete_parts", "schematic.xml", selector=selector)["written"] is True

    text = (client.workspace / "schematic.xml").read_text(encoding="utf-8")
    assert "<RefDes>R1</RefDes>" not in text
    assert 'Item Part="0"' not in text


def test_delete_net_labels_removes_only_the_annotation(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    assert client.commit("add_net_label", "schematic.xml", net="VCC", x=10, y=10)["written"]
    assert client.commit("delete_net_labels", "schematic.xml", net="VCC")["written"] is True
    again = client.call("delete_net_labels", path="schematic.xml", net="VCC")
    assert again["error"]["code"] == "OBJECT_NOT_FOUND"
    nets = client.call("list_nets", path="schematic.xml")
    assert "VCC" in str(nets)


def test_quality_gate_tool_reports_a_missing_handoff(tmp_path: Path) -> None:
    result = _Client(tmp_path).call("run_quality_gate", project_dir=".")
    assert result["status"] == "BLOCKED"
    assert "no PCB_BUILD.md" in result["blocked"][0]


def test_native_check_obeys_policy_and_document_kind(tmp_path: Path) -> None:
    arguments = {"check": "pcb_acceptance", "diptrace_root": str(tmp_path)}
    denied = _Client(tmp_path / "a", active_policy="read_only").call(
        "run_native_check", path="board.dipxml", **arguments
    )
    assert denied["error"]["code"] == "SAFETY_GATE"
    wrong = _Client(tmp_path / "b").call("run_native_check", path="schematic.xml", **arguments)
    assert wrong["ok"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="would start the real helper on Windows")
def test_native_check_job_records_the_helper_verdict(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    started = client.call(
        "run_native_check",
        check="xml_export",
        path="board.dipxml",
        diptrace_root=str(tmp_path / "no-diptrace-here"),
        timeout_seconds=30,
    )
    jobid = started["job"]["jobid"]
    for _ in range(300):
        status = client.call("get_job_status", jobid=jobid)["result"]["job"]
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.2)
    assert status["status"] == "completed"
    assert status["result"]["helper_passed"] is False  # there is no DipTrace to drive


def test_board_outline_is_replaced_only_when_everything_stays_inside(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    too_small = [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}, {"x": 0, "y": 5}]
    refused = client.call("set_board_outline", path="board.dipxml", points=too_small)
    assert refused["ok"] is False

    assert client.commit("delete_copper_pours", "board.dipxml", net="GND")["written"] is True
    larger = [{"x": -1, "y": -1}, {"x": 44, "y": -1}, {"x": 44, "y": 15}, {"x": -1, "y": 15}]
    assert client.commit("set_board_outline", "board.dipxml", points=larger)["written"] is True
    assert client.board().outline["bbox"] == {
        "min_x": -1.0,
        "min_y": -1.0,
        "max_x": 44.0,
        "max_y": 15.0,
    }
