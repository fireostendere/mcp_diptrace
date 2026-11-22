from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server


@pytest.fixture
def client(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("schematic.xml", "pcb.xml"):
        shutil.copy(Path(__file__).parent / "fixtures" / name, workspace / name)
    server = create_server(Settings(
        workspace=workspace, allowed_roots=(workspace,), state_dir=tmp_path / "state",
        active_policy="read_only",
    ))

    def call(name="plan_add_wire", **kwargs):
        response = asyncio.run(server.call_tool(name, kwargs))
        return response[1] if isinstance(response, tuple) else response.structuredContent

    return workspace, server, call


def _arguments():
    return dict(path="schematic.xml", net="VCC",
                points=[{"x": 60, "y": 50}, {"x": 70, "y": 60}],
                start={"type": "Free"}, end={"type": "Free"})


def test_plan_add_wire_is_deterministic_read_only_and_add_wire_compatible(client):
    workspace, server, call = client
    before = (workspace / "schematic.xml").read_bytes()
    first = call(**_arguments())
    assert first["ok"] is True
    assert first == call(**_arguments())
    plan = first["result"]
    assert plan["accept_route"] is True
    assert plan["selected"]["metrics"]["diagonals"] == 0
    assert len(plan["selected"]["operation"]["points"]) >= 3
    from diptrace_mcp.operations import AddWireOperation
    AddWireOperation.model_validate(plan["selected"]["operation"])
    arguments = dict(plan["selected"]["operation"])
    arguments.pop("kind")
    arguments.pop("pin_escape_policy")
    # Write previews retain their independent policy guard; planning works read-only.
    from diptrace_mcp.service import DipTraceService
    editor = DipTraceService(Settings(
        workspace=workspace, allowed_roots=(workspace,),
        state_dir=workspace.parent / "preview-state", active_policy="interactive_edit",
    ))
    preview = editor.add_wire(path="schematic.xml", **arguments)
    assert preview["ok"] is True
    assert first["transaction"] is None
    assert (workspace / "schematic.xml").read_bytes() == before
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert tools["plan_add_wire"].annotations.readOnlyHint is True


def test_plan_add_wire_resolves_valid_pin_and_reports_candidate(client):
    workspace, _, call = client
    before = (workspace / "schematic.xml").read_bytes()
    result = call(**(_arguments() | {
        "start": {"type": "Pin", "refdes": "R1", "pin": 0},
    }))
    assert result["ok"] is True
    assert result["result"]["selected"]["operation"]["start"]["refdes"] == "R1"
    assert "placement_feedback" in result["result"]
    assert (workspace / "schematic.xml").read_bytes() == before


@pytest.mark.parametrize("change", [
    {"path": "pcb.xml"}, {"net": "missing"}, {"sheet": 999},
    {"points": [{"x": 1, "y": 2}]},
    {"points": [{"x": float("inf"), "y": 0}, {"x": 1, "y": 2}]},
    {"start": {"type": "Pin", "refdes": "missing", "pin": 0}},
    {"start": {"type": "Pin", "refdes": "R1", "pin": 999}},
    {"start": {"type": "Wire", "wire_id": "missing"}},
    {"start": {"type": "Pin", "refdes": "R1", "pin": 1}},
])
def test_plan_add_wire_refuses_invalid_input_without_mutation(client, change):
    workspace, _, call = client
    before = (workspace / "schematic.xml").read_bytes()
    assert call(**(_arguments() | change))["ok"] is False
    assert (workspace / "schematic.xml").read_bytes() == before


def test_plan_add_wire_refuses_path_outside_allowed_roots(client, tmp_path):
    _, _, call = client
    outside = tmp_path / "outside.xml"
    shutil.copy(Path(__file__).parent / "fixtures/schematic.xml", outside)
    assert call(**(_arguments() | {"path": str(outside)}))["ok"] is False
