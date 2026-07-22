from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.errors import (
    ConnectivityRegressionError,
    DrcRegressionError,
    GeometryError,
)
from diptrace_mcp.operations import (
    AddTraceOperation,
    AddViaOperation,
    DeleteTraceOperation,
    DeleteViaOperation,
    MoveViaOperation,
    ReplaceTraceOperation,
    SetTraceWidthOperation,
    SetViaStyleOperation,
    TracePathPoint,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)


def _four_layer_blind_via_document() -> DipTraceDocument:
    document = _load()
    root = ET.fromstring(document.raw_bytes)
    layers = root.find("./Board/CopperLayers")
    style = root.find("./Board/ViaStyles/ViaStyle[@Id='0']")
    assert layers is not None and style is not None
    bottom = layers.find("./Lay[@Id='1']")
    assert bottom is not None
    bottom_index = list(layers).index(bottom)
    for offset, (layer_id, name) in enumerate((("2", "Inner 1"), ("3", "Inner 2"))):
        layer = ET.Element("Lay", {"Id": layer_id, "Type": "Signal"})
        ET.SubElement(layer, "Name").text = name
        layers.insert(bottom_index + offset, layer)
    style.set("Lay1", "0")
    style.set("Lay2", "2")
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _vcc_endpoints(document: DipTraceDocument) -> tuple[str, str]:
    snapshot = build_snapshot(document)
    net = next(item for item in snapshot.board.nets if item.name == "VCC")  # type: ignore[union-attr]
    endpoints = net.relationships["endpoints"]
    return endpoints[0], endpoints[1]


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_adapter_normalizes_ratline_pad_anchors_and_via_style_geometry() -> None:
    snapshot = build_snapshot(_load())
    assert snapshot.board is not None
    vcc = next(item for item in snapshot.board.nets if item.name == "VCC")
    pads = [snapshot.get_object(item) for item in vcc.relationships["endpoints"]]

    assert [pad.position for pad in pads] == [{"x": 10.0, "y": 9.0}, {"x": 20.0, "y": 9.0}]
    assert all(pad.net_name == "VCC" for pad in pads)
    assert all(pad.geometry_source == "xml-ratline-endpoint" for pad in pads)
    via = snapshot.board.vias[0]
    assert via.attributes["diameter_mm"] == pytest.approx(0.6)
    assert via.attributes["hole_mm"] == pytest.approx(0.3)
    assert via.bbox == {"min_x": 14.7, "min_y": 9.7, "max_x": 15.3, "max_y": 10.3}


def test_add_trace_compiles_official_endpoint_and_point_structure() -> None:
    document = _load()
    start, end = _vcc_endpoints(document)
    result = apply_semantic_operations(
        document,
        [
            AddTraceOperation(
                net="VCC",
                start_object_id=start,
                end_object_id=end,
                points=[TracePathPoint(x=10, y=9), TracePathPoint(x=20, y=9)],
                layer="Top",
                width=0.25,
            )
        ],
    )

    root = ET.fromstring(result.raw_bytes)
    trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
    assert trace is not None
    assert trace.attrib == {
        "Id": "0",
        "Connected1": "Pad",
        "Object1": "0",
        "SubObject1": "0",
        "Point1": "-1",
        "Connected2": "Pad",
        "Object2": "1",
        "SubObject2": "0",
        "Point2": "-1",
        "Group": "-1",
        "PairSeparateTrace": "-1",
        "Selected": "N",
    }
    points = trace.findall("./Points/Point")
    assert points[0].attrib == {"Id": "0", "X": "10", "Y": "9"}
    assert points[1].get("Lay") == "0"
    assert points[1].get("Width") == "0.25"
    assert points[1].get("ViaStyle") == "-1"
    assert root.find("./Board/FutureExtension[@Vendor='fixture']") is not None
    assert root.findall("./Board/Ratlines/Ratline") == []
    reparsed = build_snapshot(result.document)
    vcc = next(item for item in reparsed.board.nets if item.name == "VCC")  # type: ignore[union-attr]
    assert vcc.attributes["trace_count"] == 1


def test_add_trace_rejects_layer_change_without_via() -> None:
    document = _load()
    start, end = _vcc_endpoints(document)
    with pytest.raises(GeometryError, match="layer changes require a via"):
        apply_semantic_operations(
            document,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(x=14, y=9, layer="Top"),
                        TracePathPoint(x=20, y=9, layer="Bottom"),
                    ],
                    layer="Top",
                    width=0.25,
                )
            ],
        )


def test_add_trace_rejects_via_style_outside_exported_span() -> None:
    document = _four_layer_blind_via_document()
    start, end = _vcc_endpoints(document)

    with pytest.raises(GeometryError, match="does not span the requested layer transition"):
        apply_semantic_operations(
            document,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(
                            x=15,
                            y=9,
                            layer="Top",
                            via_style="Default",
                        ),
                        TracePathPoint(x=20, y=9, layer="Bottom"),
                    ],
                    layer="Top",
                    width=0.25,
                )
            ],
        )


def test_replace_preserves_endpoints_and_delete_requires_explicit_regression() -> None:
    document = _load()
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]
    replacement = ReplaceTraceOperation(
        trace_id=trace.stable_id,
        points=[
            TracePathPoint(x=10, y=10),
            TracePathPoint(x=10, y=12),
            TracePathPoint(x=20, y=12),
            TracePathPoint(x=20, y=10),
        ],
        layer="Top",
        width=0.25,
    )
    result = apply_semantic_operations(document, [replacement])
    replaced = ET.fromstring(result.raw_bytes).find(
        "./Board/Nets/Net[@Id='1']/Traces/Trace"
    )
    assert replaced is not None
    assert replaced.get("Connected1") == "Pad"
    assert len(replaced.findall("./Points/Point")) == 4

    with pytest.raises(ConnectivityRegressionError):
        apply_semantic_operations(
            document,
            [DeleteTraceOperation(selector=QuerySelector(ids=[trace.stable_id]))],
        )
    deleted = apply_semantic_operations(
        document,
        [
            DeleteTraceOperation(
                selector=QuerySelector(ids=[trace.stable_id]),
                allow_connectivity_regression=True,
            )
        ],
    )
    assert not build_snapshot(deleted.document).board.traces  # type: ignore[union-attr]


def test_trace_width_checks_exported_drc_minimum() -> None:
    snapshot = build_snapshot(_load())
    trace = snapshot.board.traces[0]  # type: ignore[union-attr]
    with pytest.raises(GeometryError):
        apply_semantic_operations(
            _load(),
            [
                SetTraceWidthOperation(
                    selector=QuerySelector(ids=[trace.stable_id]),
                    width=0.1,
                )
            ],
        )


def test_via_insert_move_style_and_delete_roundtrip() -> None:
    document = _load()
    trace = build_snapshot(document).board.traces[0]  # type: ignore[union-attr]
    inserted = apply_semantic_operations(
        document,
        [
            AddViaOperation(
                trace_id=trace.stable_id,
                x=12.5,
                y=10,
                via_style="Default",
                layer_before="Top",
                layer_after="Bottom",
            )
        ],
    )
    snapshot = build_snapshot(inserted.document)
    assert snapshot.board is not None
    via = next(item for item in snapshot.board.vias if item.position == {"x": 12.5, "y": 10.0})
    # The inserted transition makes the old ViaStyle point same-layer metadata, so only
    # one physical via remains until the inserted transition is deleted.
    assert len(snapshot.board.vias) == 1

    moved = apply_semantic_operations(
        inserted.document,
        [
            MoveViaOperation(
                selector=QuerySelector(ids=[via.stable_id]),
                absolute_x=12.5,
                absolute_y=10.5,
            ),
            SetViaStyleOperation(
                selector=QuerySelector(ids=[via.stable_id]),
                via_style="Default",
            ),
        ],
    )
    moved_snapshot = build_snapshot(moved.document)
    moved_via = next(
        item for item in moved_snapshot.board.vias if item.position == {"x": 12.5, "y": 10.5}  # type: ignore[union-attr]
    )
    deleted = apply_semantic_operations(
        moved.document,
        [DeleteViaOperation(selector=QuerySelector(ids=[moved_via.stable_id]))],
    )
    assert len(build_snapshot(deleted.document).board.vias) == 1  # type: ignore[union-attr]


def test_add_trace_service_preview_commit_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    source = FIXTURES.joinpath("pcb.xml").read_bytes()
    board.write_bytes(source)
    service = _service(workspace, tmp_path / "state")
    start, end = _vcc_endpoints(DipTraceDocument.load(board, 10_000_000))

    preview = service.add_trace(
        net="VCC",
        start_object_id=start,
        end_object_id=end,
        points=[{"x": 10, "y": 9}, {"x": 20, "y": 9}],
        layer="Top",
        width=0.25,
        path=str(board),
    )
    transaction = preview["transaction"]
    assert transaction["status"] == "validated"
    assert transaction["validation_before"]["review_errors"]["connectivity"] == 1
    assert transaction["validation_after_preview"]["review_errors"].get(
        "connectivity", 0
    ) == 0

    committed = service.commit_transaction(transaction["txid"], transaction["source_sha256"])
    assert committed["transaction"]["status"] == "committed"
    assert ET.fromstring(board.read_bytes()).find(
        "./Board/Nets/Net[@Id='0']/Traces/Trace"
    ) is not None
    service.rollback_transaction(
        transaction["txid"], committed["transaction"]["committed_sha256"]
    )
    assert board.read_bytes() == source


def test_semantic_safety_gate_rejects_new_component_overlap(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes(FIXTURES.joinpath("pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")

    with pytest.raises(DrcRegressionError):
        service.move_components(
            {"refdes": ["R1"]},
            absolute_x=20,
            absolute_y=10,
            path=str(board),
        )
