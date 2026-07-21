from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.multirouter import synthesize_routes_with_retry
from diptrace_mcp.routing import RouteConnectionConfig
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _two_net_document(
    signal_y: float = 11.0,
    signal_x1: float = 10.0,
    signal_x2: float = 20.0,
) -> DipTraceDocument:
    """pcb.xml with SIGNAL unrouted and a ratline for its endpoints."""

    original = DipTraceDocument.load(FIXTURES / "pcb.xml", MAX_BYTES)
    root = ET.fromstring(original.raw_bytes)
    signal = root.find("./Board/Nets/Net[@Id='1']")
    assert signal is not None
    traces = signal.find("./Traces")
    assert traces is not None
    for trace in list(traces):
        traces.remove(trace)
    ratlines = root.find("./Board/Ratlines")
    assert ratlines is not None
    ET.SubElement(
        ratlines,
        "Ratline",
        {
            "Id": "1",
            "Hidden": "N",
            "X1": str(signal_x1),
            "Y1": str(signal_y),
            "X2": str(signal_x2),
            "Y2": str(signal_y),
            "Comp1": "0",
            "Pad1": "1",
            "Comp2": "1",
            "Pad2": "1",
        },
    )
    return DipTraceDocument.from_bytes(
        original.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def _configs(
    document: DipTraceDocument, *, signal_detour: float = 3.0
) -> list[RouteConnectionConfig]:
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    configs: list[RouteConnectionConfig] = []
    for name, detour in (("VCC", 3.0), ("SIGNAL", signal_detour)):
        net = next(item for item in snapshot.board.nets if item.name == name)
        start, end = net.relationships["endpoints"]
        configs.append(
            RouteConnectionConfig(
                net=net.stable_id,
                start_object_id=start,
                end_object_id=end,
                layer="Top",
                width=0.25,
                clearance=0.2,
                grid=0.5,
                max_detour=detour,
            )
        )
    return configs


def test_sequential_multiroute_routes_all_connections() -> None:
    document = _two_net_document()
    result = synthesize_routes_with_retry(document, _configs(document), ripup_retry=False)

    assert result.metrics["routed_count"] == 2
    assert result.failed == []
    assert result.ripups == []
    assert len(result.operations) == 2
    # Operations replay cleanly through the transactional path.
    from diptrace_mcp.semantic_compiler import apply_semantic_operations

    applied = apply_semantic_operations(document, result.operations)
    snapshot = build_snapshot(applied.document)
    assert snapshot.board is not None
    assert len(snapshot.board.traces) == 2
    net_names = {record.net_name for record in snapshot.board.traces}
    assert net_names == {"VCC", "SIGNAL"}


def test_ripup_retry_recovers_blocked_connection() -> None:
    # SIGNAL endpoints sit on the VCC corridor (middle section, same y) and
    # the connection allows no detour; VCC keeps enough room to re-route
    # around the restored SIGNAL trace.
    document = _two_net_document(signal_y=9.0, signal_x1=12.0, signal_x2=18.0)
    configs = _configs(document, signal_detour=1.0)
    vcc_id, signal_id = (config.net for config in configs)

    without_retry = synthesize_routes_with_retry(document, configs, ripup_retry=False)
    assert without_retry.metrics["routed_count"] == 1
    assert without_retry.failed[0]["net"] == signal_id

    with_retry = synthesize_routes_with_retry(
        document, configs, ripup_retry=True, max_ripup_attempts=4
    )
    assert with_retry.failed == []
    assert with_retry.metrics["routed_count"] == 2
    assert len(with_retry.ripups) == 1
    assert with_retry.ripups[0]["ripped_net"] == vcc_id
    # add(VCC) + add(SIGNAL fails) -> rip VCC + add(SIGNAL) + re-add(VCC)
    kinds = [operation.kind for operation in with_retry.operations]
    assert kinds == ["add_trace", "delete_trace", "add_trace", "add_trace"]

    from diptrace_mcp.semantic_compiler import apply_semantic_operations

    applied = apply_semantic_operations(document, with_retry.operations)
    snapshot = build_snapshot(applied.document)
    assert snapshot.board is not None
    assert len(snapshot.board.traces) == 2
    assert {record.net_name for record in snapshot.board.traces} == {"VCC", "SIGNAL"}


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
        )
    )


def test_route_connections_service_transaction(tmp_path: Path) -> None:
    target = tmp_path / "board.dip"
    document = _two_net_document()
    target.write_bytes(document.raw_bytes)
    service = _service(tmp_path, tmp_path / ".state")
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    connections: list[dict[str, object]] = []
    for name in ("VCC", "SIGNAL"):
        net = next(item for item in snapshot.board.nets if item.name == name)
        start, end = net.relationships["endpoints"]
        connections.append(
            {
                "net": net.stable_id,
                "start_object_id": start,
                "end_object_id": end,
                "layer": "Top",
                "width": 0.25,
                "clearance": 0.2,
                "grid": 0.5,
            }
        )
    preview = service.route_connections(connections, path="board.dip", dry_run=True)
    assert preview["routing"]["routed_count"] == 2
    txid = preview["transaction"]["txid"]
    committed = service.route_connections(
        connections,
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["transaction"]["expected_sha256"],
        txid=txid,
    )
    assert committed["transaction"]["status"] == "committed"
    model = service.board_model("board.dip")
    assert len(model["result"]["traces"]) == 2
