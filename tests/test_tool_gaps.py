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
from diptrace_mcp.external_adapters import ExternalJobManager
from diptrace_mcp.server import create_server
from diptrace_mcp.services.context import DocumentGateway, DocumentTarget
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


@pytest.mark.parametrize('suffix', ['.dch', '.dip'])
def test_native_binary_export_guarded_without_xml_parse(tmp_path, monkeypatch, suffix):
    monkeypatch.setattr(ExternalJobManager, '_launch_worker', lambda self, record, **kwargs: record)
    client = _Client(tmp_path)
    (client.workspace / ('binary' + suffix)).write_bytes(b'\x00binary, not XML')
    result = client.call('run_native_check', check='xml_export', path='binary' + suffix,
                         diptrace_root=str(tmp_path))
    assert result['ok'] is True
    assert result['document']['source_type'].startswith('native-')
    assert result['document']['version'] == 'unknown'
    command = result['job']['command']
    assert Path(command[command.index('--project') + 1]).read_bytes() == b'\x00binary, not XML'
    outside = tmp_path / ('outside' + suffix)
    outside.write_bytes(b'\x00binary')
    denied = client.call('run_native_check', check='xml_export', path=str(outside),
                         diptrace_root=str(tmp_path))
    assert denied['ok'] is False
    xml = client.call('run_native_check', check='xml_export', path='board.dipxml',
                      diptrace_root=str(tmp_path))
    assert xml['ok'] is False


def test_native_check_rejects_live_target_before_parsing(tmp_path, monkeypatch):
    client = _Client(tmp_path)
    monkeypatch.setattr(DocumentGateway, 'resolve_target',
                        lambda *args: DocumentTarget(client.workspace / 'missing.dip', 'live'))
    result = client.call('run_native_check', check='xml_export', path='missing.dip',
                         diptrace_root=str(tmp_path))
    assert result['ok'] is False
    assert 'live session' in result['error']['message']


@pytest.mark.parametrize(('check', 'path', 'hashes'), [
    ('schematic_acceptance', 'schematic.xml', ['a' * 64, 'b' * 64]),
    ('schematic_erc', 'schematic.xml', ['a' * 64]),
    ('xml_export', 'native.dch', ['a' * 64]),
])
def test_public_native_check_forwards_only_explicit_approvals(
    tmp_path, monkeypatch, check, path, hashes,
):
    monkeypatch.setattr(ExternalJobManager, '_launch_worker', lambda self, record, **kw: record)
    client = _Client(tmp_path)
    (client.workspace / 'native.dch').write_bytes(b'not XML')
    result = client.call('run_native_check', check=check, path=path,
                         diptrace_root=str(tmp_path), startup_dialog_sha256=hashes)
    assert result['ok'] is True
    command = result['job']['command']
    assert command[-len(hashes) * 2:] == [
        arg for digest in hashes for arg in ('--startup-dialog-sha256', digest)]
    omitted = client.call('run_native_check', check=check, path=path, diptrace_root=str(tmp_path))
    assert '--startup-dialog-sha256' not in omitted['job']['command']


@pytest.mark.parametrize(('check', 'path', 'hashes'), [
    ('schematic_erc', 'schematic.xml', ['A' * 64]),
    ('schematic_erc', 'schematic.xml', [123]),
    ('schematic_erc', 'schematic.xml', ['a' * 64] * 9),
    ('schematic_erc', 'schematic.xml', 'a' * 64),
    ('pcb_acceptance', 'board.dipxml', ['a' * 64]),
    ('xml_export', 'native.dch', ['a' * 64, 'b' * 64]),
])
def test_public_native_check_rejects_invalid_or_unsupported_approvals(
    tmp_path, monkeypatch, check, path, hashes,
):
    monkeypatch.setattr(ExternalJobManager, '_launch_worker',
                        lambda *args, **kw: pytest.fail('must not launch'))
    client = _Client(tmp_path)
    (client.workspace / 'native.dch').write_bytes(b'not XML')
    result = client.call('run_native_check', check=check, path=path,
                         diptrace_root=str(tmp_path), startup_dialog_sha256=hashes)
    assert result['ok'] is False


@pytest.mark.skipif(sys.platform == "win32", reason="would start the real helper on Windows")
def test_native_check_job_records_the_helper_verdict(tmp_path: Path) -> None:
    client = _Client(tmp_path)
    (client.workspace / "native.dip").write_bytes(b"not a real native board")
    started = client.call(
        "run_native_check",
        check="xml_export",
        path="native.dip",
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
    assert status['result']['execution_status'] == 'finished'
    assert status['result']['acceptance_decision'] == 'not_evaluated'
    assert 'log.txt' in status['result']['output_files']
    log = Path(status['result']['output_directory']) / 'log.txt'
    assert 'native XML export requires Windows' in log.read_text()


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
