from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import Sha256MismatchError
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.silkscreen import SilkscreenPlanConfig, plan_silkscreen
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _dense_silk_bytes() -> bytes:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='1']")
    assert component is not None
    component.set("X", "10")
    component.set("Locked", "Y")
    marking = ET.SubElement(component, "RefDesMarking")
    ET.SubElement(
        marking,
        "Silk",
        {
            "Show": "Show",
            "Align": "Position",
            "Horz": "Center",
            "Vert": "Center",
            "X": "0",
            "Y": "-1.5",
            "Angle": "0",
        },
    )
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


def test_planner_moves_collision_and_never_moves_locked_label(tmp_path: Path) -> None:
    board = tmp_path / "board.xml"
    board.write_bytes(_dense_silk_bytes())
    snapshot = build_snapshot(DipTraceDocument.load(board, 10_000_000))

    result = plan_silkscreen(snapshot, SilkscreenPlanConfig())

    assert result.metrics == {
        "selected_count": 2,
        "movable_count": 1,
        "locked_count": 1,
        "changed_count": 1,
        "unresolved_count": 0,
        "fixed_obstacle_count": 2,
    }
    assert len(result.operations) == 1
    locked = next(item for item in result.candidates if item["status"] == "locked_unchanged")
    assert locked["legal"] is True
    moved = next(item for item in result.candidates if item["status"] == "move")
    assert moved["chosen"]["legal"] is True
    assert result.score["total"] > 0


def test_silkscreen_plan_preview_commit_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    source = _dense_silk_bytes()
    board.write_bytes(source)
    service = _service(workspace, tmp_path / "state")

    planned = service.plan_silkscreen(str(board))
    plan = planned["result"]["plan"]
    plan_id = plan["plan_id"]
    assert plan["metrics"]["changed_count"] == 1
    assert len(planned["resources"]) == 4
    preview_svg = service.plan_resource(plan_id, "preview.svg")
    assert hashlib.sha256(preview_svg.encode()).hexdigest() == (
        "e36821bd3abf5575f5dd2bcc46a24c23b6591266b15d8a1f3e1ea26d32d69d27"
    )
    assert '"candidates"' in service.plan_resource(plan_id, "preview.json")

    committed = service.apply_silkscreen_plan(plan_id, dry_run=False)
    assert committed["transaction"]["status"] == "committed"
    assert committed["plan"]["status"] == "committed"
    committed_sha = committed["transaction"]["committed_sha256"]

    root = ET.fromstring(board.read_bytes())
    movable = root.find("./Board/Components/Component[@Id='0']/RefDesMarking/Silk")
    locked = root.find("./Board/Components/Component[@Id='1']/RefDesMarking/Silk")
    assert movable is not None and locked is not None
    assert (movable.get("X"), movable.get("Y")) != ("0", "-1.5")
    assert (locked.get("X"), locked.get("Y")) == ("0", "-1.5")

    rolled_back = service.rollback_transaction(
        committed["transaction"]["txid"], committed_sha
    )
    assert rolled_back["result"]["document_restored"] is True
    assert board.read_bytes() == source


def test_silkscreen_plan_rejects_stale_document(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes(_dense_silk_bytes())
    service = _service(workspace, tmp_path / "state")
    plan_id = service.plan_silkscreen(str(board))["result"]["plan"]["plan_id"]

    original = DipTraceDocument.load(board, 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    value = root.find("./Board/Components/Component[@Id='0']/Value")
    assert value is not None
    value.text = "12k"
    board.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))

    with pytest.raises(Sha256MismatchError):
        service.apply_silkscreen_plan(plan_id)
    assert service.plans.read(plan_id).status == "obsolete"
