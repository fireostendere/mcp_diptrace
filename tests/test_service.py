import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import XmlEdit

FIXTURES = Path(__file__).parent / "fixtures"


def settings(workspace: Path, state: Path) -> Settings:
    return Settings(
        workspace=workspace,
        allowed_roots=(workspace,),
        state_dir=state,
        max_document_bytes=10_000_000,
        max_scan_files=100,
    )


def test_scan_and_two_step_offline_edit(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = project / "board.dip"
    document.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(settings(project, tmp_path / "state"))

    scanned = service.scan_documents()
    preview = service.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="47k",
            )
        ],
        path="board.dip",
    )

    assert scanned["documents"][0]["type"] == "DipTrace-PCB"
    assert preview["written"] is False
    assert b"<Value>10k</Value>" in document.read_bytes()

    with pytest.raises(EditError, match="expected_sha256"):
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component[RefDes='R1']/Value",
                    value="47k",
                )
            ],
            path="board.dip",
            dry_run=False,
        )

    committed = service.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="47k",
            )
        ],
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["before_sha256"],
    )

    assert committed["written"] is True
    assert b"<Value>47k</Value>" in document.read_bytes()
    assert Path(committed["backup"]).is_file()


def test_semantic_move_value_and_rollback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    document = project / "board.dip"
    document.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(settings(project, tmp_path / "state"))

    move_preview = service.move_components(
        selector={"refdes": ["R1"]},
        dx=5.0,
        dy=0.0,
        path="board.dip",
        dry_run=True,
    )
    move_txid = move_preview["transaction"]["txid"]
    assert move_preview["ok"] is True
    assert move_preview["transaction"]["status"] == "validated"

    moved = service.move_components(
        selector={"refdes": ["R1"]},
        dx=5.0,
        dy=0.0,
        path="board.dip",
        dry_run=False,
        expected_sha256=move_preview["transaction"]["expected_sha256"],
        txid=move_txid,
    )
    assert moved["transaction"]["status"] == "committed"
    moved_component = ET.fromstring(document.read_bytes()).find(
        "./Board/Components/Component[@Id='0']"
    )
    assert moved_component is not None
    assert moved_component.get("X") == "15"

    rollback = service.rollback_transaction(
        move_txid,
        expected_sha256=moved["transaction"]["committed_sha256"],
    )
    assert rollback["transaction"]["status"] == "rolled_back"
    restored_component = ET.fromstring(document.read_bytes()).find(
        "./Board/Components/Component[@Id='0']"
    )
    assert restored_component is not None
    assert restored_component.get("X") == "10"

    value_preview = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        path="board.dip",
        dry_run=True,
    )
    value_txid = value_preview["transaction"]["txid"]
    committed = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        path="board.dip",
        dry_run=False,
        expected_sha256=value_preview["transaction"]["expected_sha256"],
        txid=value_txid,
    )
    assert committed["transaction"]["status"] == "committed"
    assert b"<Value>47k</Value>" in document.read_bytes()


def test_scan_skips_symlink_outside_allowed_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.xml"
    outside.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    link = project / "outside.xml"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    service = DipTraceService(settings(project, tmp_path / "state"))

    assert service.scan_documents()["documents"] == []
