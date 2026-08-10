from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path) -> tuple[DipTraceService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("pcb.xml", "schematic.xml"):
        shutil.copyfile(FIXTURES / name, workspace / name)
    return (
        DipTraceService(
            Settings(
                workspace=workspace,
                allowed_roots=(workspace,),
                state_dir=tmp_path / "state",
                max_document_bytes=10_000_000,
            )
        ),
        workspace,
    )


def test_routing_read_guards_filters_and_detail_errors(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")
    schematic = str(workspace / "schematic.xml")

    with pytest.raises(DocumentError, match="Unrouted connections"):
        service.list_unrouted_connections(schematic)
    with pytest.raises(DocumentError, match="exactly one"):
        service.get_route_details(path=board)
    with pytest.raises(DocumentError, match="exactly one"):
        service.get_route_details(trace_id="x", net="VCC", path=board)
    with pytest.raises(DocumentError, match="Route details"):
        service.get_route_details(net="VCC", path=schematic)
    with pytest.raises(DocumentError, match="Unique net"):
        service.get_route_details(net="does-not-exist", path=board)

    filtered = service.list_unrouted_connections(board, nets=["does-not-exist"])
    assert filtered["result"]["matched_count"] == 0

    components = service.query_objects(
        board,
        selector={"kinds": ["component"]},
        limit=1,
    )
    component_id = components["result"]["items"][0]["stable_id"]
    with pytest.raises(DocumentError, match="not a trace"):
        service.get_route_details(trace_id=component_id, path=board)


def test_direct_route_connection_and_route_net_dry_run(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")
    unrouted = service.list_unrouted_connections(board, nets=["VCC"])
    item = unrouted["result"]["items"][0]
    start = item["endpoints"][0]["pad_id"]
    end = item["endpoints"][1]["pad_id"]

    direct = service.route_connection(
        net=item["net_id"],
        start_object_id=start,
        end_object_id=end,
        layer="Top",
        width=0.25,
        clearance=None,
        preferred_layers=["Top"],
        path=board,
        dry_run=True,
    )
    assert direct["written"] is False
    assert direct["routing"]["metrics"]["length_mm"] > 0
    assert direct["clearance_rule_status"]
    assert "netclass_rules_ignored" in direct

    whole_net = service.route_net(
        "VCC",
        layer="Top",
        width=0.25,
        clearance=None,
        preferred_layers=["Top"],
        path=board,
        dry_run=True,
    )
    assert whole_net["written"] is False
    assert whole_net["routing"]["connection_count"] == 1
    assert whole_net["clearance_rule_status"]["per_route"]

    with pytest.raises(DocumentError, match="No exported unrouted connection"):
        service.route_net(
            "SIGNAL",
            layer="Top",
            width=0.25,
            path=board,
            dry_run=True,
        )


def test_route_details_by_trace_and_net_after_preview_application(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board_path = workspace / "pcb.xml"
    board = str(board_path)
    unrouted = service.list_unrouted_connections(board, nets=["VCC"])
    item = unrouted["result"]["items"][0]

    committed = service.route_connection(
        net=item["net_id"],
        start_object_id=item["endpoints"][0]["pad_id"],
        end_object_id=item["endpoints"][1]["pad_id"],
        layer="Top",
        width=0.25,
        path=board,
        dry_run=False,
        expected_sha256=service.document_info(board)["document"]["sha256"],
    )
    assert committed["written"] is True

    traces = service.query_objects(
        board,
        selector={"kinds": ["trace"]},
        limit=10,
    )
    trace_id = next(
        value["stable_id"]
        for value in traces["result"]["items"]
        if value.get("net_name") == "VCC"
    )
    by_trace = service.get_route_details(trace_id=trace_id, path=board)
    by_net = service.get_route_details(net="VCC", path=board)
    assert by_trace["result"]["trace_count"] == 1
    assert by_net["result"]["total_length_mm"] > 0
    assert by_net["result"]["per_layer_length_mm"]
