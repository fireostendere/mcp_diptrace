from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import AmbiguousSelectorError, EditError, ObjectNotFoundError
from diptrace_mcp.operations import (
    AddNetLabelOperation,
    AddSheetOperation,
    AddWireOperation,
    ClearPanelizationOperation,
    ConnectPinsOperation,
    DeleteWireOperation,
    DisconnectPinsOperation,
    PlacePartOperation,
    SetPanelizationOperation,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, MAX_BYTES)


def _load_bytes(raw: bytes) -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path("memory.xml"), raw)


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
        )
    )


def test_add_sheet_compiles_official_structure() -> None:
    result = apply_semantic_operations(
        _load("schematic.xml"), [AddSheetOperation(name="Power")]
    )
    root = ET.fromstring(result.raw_bytes)
    sheets = root.findall("./Schematic/SheetSettings/Sheets/Sheet")
    assert [sheet.findtext("./Name") for sheet in sheets] == ["Main", "Power"]
    assert sheets[1].findtext("./Id") == "1"
    assert sheets[1].findtext("./Type") == "Normal"
    snapshot = build_snapshot(result.document)
    assert snapshot.schematic is not None
    assert len(snapshot.schematic.sheets) == 2


def test_add_sheet_rejects_duplicate_name() -> None:
    with pytest.raises(AmbiguousSelectorError):
        apply_semantic_operations(_load("schematic.xml"), [AddSheetOperation(name="main")])


def test_place_part_compiles_official_structure() -> None:
    result = apply_semantic_operations(
        _load("schematic.xml"),
        [
            PlacePartOperation(
                component_style="CompType9",
                refdes="R9",
                name="RES_0603",
                value="4k7",
                x=55.0,
                y=30.0,
                pin_count=2,
            )
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    part = root.findall("./Schematic/Components/Part")[-1]
    assert part.get("Id") == "3"
    assert part.get("ComponentStyle") == "CompType9"
    assert part.get("Sheet") == "0"
    assert part.get("X") == "55"
    assert part.get("Y") == "30"
    assert part.findtext("./RefDes") == "R9"
    assert part.findtext("./Value") == "4k7"
    pins = part.findall("./Pins/Pin")
    assert len(pins) == 2
    assert all(pin.get("NetId") == "-1" for pin in pins)
    snapshot = build_snapshot(result.document)
    assert snapshot.schematic is not None
    assert len(snapshot.schematic.parts) == 4
    assert len(snapshot.schematic.pins) == 8


def test_place_part_rejects_duplicate_refdes() -> None:
    with pytest.raises(AmbiguousSelectorError):
        apply_semantic_operations(
            _load("schematic.xml"),
            [
                PlacePartOperation(
                    component_style="CompType9",
                    refdes="r1",
                    x=0.0,
                    y=0.0,
                    pin_count=2,
                )
            ],
        )


def test_place_part_requires_known_sheet() -> None:
    with pytest.raises(ObjectNotFoundError):
        apply_semantic_operations(
            _load("schematic.xml"),
            [
                PlacePartOperation(
                    component_style="CompType9",
                    refdes="R9",
                    x=0.0,
                    y=0.0,
                    pin_count=2,
                    sheet=7,
                )
            ],
        )


def test_connect_pins_creates_net_and_cross_references() -> None:
    result = apply_semantic_operations(
        _load("schematic.xml"),
        [
            PlacePartOperation(
                component_style="CompType9",
                refdes="R9",
                x=50.0,
                y=40.0,
                pin_count=2,
            ),
            ConnectPinsOperation(
                net="GND",
                pins=[{"refdes": "R9", "pin": 0}, {"refdes": "R1", "pin": 0}],
                allow_reconnect=True,
            ),
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    net = root.find("./Schematic/Nets/Net[Name='GND']")
    assert net is not None
    assert net.get("Id") == "2"
    items = net.findall("./Pins/Item")
    assert {(item.get("Part"), item.get("Pin")) for item in items} == {("3", "0"), ("0", "0")}
    r9 = root.findall("./Schematic/Components/Part")[-1]
    assert r9.findall("./Pins/Pin")[0].get("NetId") == "2"
    # R1 pin 0 moved from VCC (net 0) to GND: VCC must not reference it anymore.
    vcc = root.find("./Schematic/Nets/Net[@Id='0']")
    assert vcc is not None
    assert [(i.get("Part"), i.get("Pin")) for i in vcc.findall("./Pins/Item")] == [("1", "0")]
    snapshot = build_snapshot(result.document)
    assert snapshot.schematic is not None
    assert len(snapshot.schematic.nets) == 3


def test_connect_pins_conflict_without_reconnect_flag() -> None:
    with pytest.raises(EditError, match="allow_reconnect"):
        apply_semantic_operations(
            _load("schematic.xml"),
            [
                ConnectPinsOperation(
                    net="NEWNET", pins=[{"refdes": "R1", "pin": 0}]
                )
            ],
        )


def test_disconnect_pins_clears_net_and_items() -> None:
    document = _load("schematic.xml")
    snapshot = build_snapshot(document)
    pin_ids = [
        record.stable_id
        for record in snapshot.objects.values()
        if record.kind == "pin" and record.refdes == "U1"
    ]
    result = apply_semantic_operations(
        document, [DisconnectPinsOperation(selector={"ids": pin_ids})]
    )
    root = ET.fromstring(result.raw_bytes)
    u1a = root.findall("./Schematic/Components/Part")[1]
    assert all(pin.get("NetId") == "-1" for pin in u1a.findall("./Pins/Pin"))
    vcc = root.find("./Schematic/Nets/Net[@Id='0']")
    assert vcc is not None
    assert [(i.get("Part"), i.get("Pin")) for i in vcc.findall("./Pins/Item")] == [("0", "0")]


def _u1_power_part_id() -> str:
    snapshot = build_snapshot(_load("schematic.xml"))
    for record in snapshot.objects.values():
        if (
            record.kind == "part"
            and record.refdes == "U1"
            and record.name == "TEST_MCU"
            and record.attributes.get("part_name") == "Power"
        ):
            return record.stable_id
    # Fallback: the part whose XML Id is "1" per the fixture layout.
    for record in snapshot.objects.values():
        if record.kind == "part" and record.refdes == "U1" and record.xml_id == "1":
            return record.stable_id
    raise AssertionError("U1 Power part not found in the fixture")


def _wired_document() -> DipTraceDocument:
    result = apply_semantic_operations(
        _load("schematic.xml"),
        [
            AddWireOperation(
                net="VCC",
                sheet=0,
                points=[{"x": 10.0, "y": 20.0}, {"x": 10.0, "y": 30.0}, {"x": 30.0, "y": 30.0}],
                start={"type": "Pin", "refdes": "R1", "pin": 0},
                end={"type": "Pin", "part_id": _u1_power_part_id(), "pin": 0},
            )
        ],
    )
    return result.document


def test_add_wire_compiles_official_structure() -> None:
    document = _wired_document()
    root = ET.fromstring(document.raw_bytes)
    wire = root.find("./Schematic/Nets/Net[@Id='0']/Wires/Wire")
    assert wire is not None
    assert wire.attrib == {
        "Id": "0",
        "Sheet": "0",
        "Connected1": "Pin",
        "Bus1": "-1",
        "Object1": "0",
        "SubObject1": "0",
        "Connected2": "Pin",
        "Bus2": "-1",
        "Object2": "1",
        "SubObject2": "0",
        "HiddenPower": "N",
        "CanUnhide": "N",
        "Arrows": "None",
        "Group": "-1",
        "Selected": "N",
    }
    points = wire.findall("./Points/Point")
    assert [(p.get("X"), p.get("Y"), p.get("Dir")) for p in points] == [
        ("10", "20", "-1"),
        ("10", "30", "1"),
        ("30", "30", "0"),
    ]
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    assert len(snapshot.schematic.wires) == 1
    wire_record = snapshot.schematic.wires[0]
    assert wire_record.net_name == "VCC"
    assert wire_record.attributes["point_count"] == 3


def test_add_wire_rejects_pin_of_another_net() -> None:
    with pytest.raises(EditError, match="does not belong"):
        apply_semantic_operations(
            _load("schematic.xml"),
            [
                AddWireOperation(
                    net="VCC",
                    points=[{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 0.0}],
                    start={"type": "Pin", "refdes": "R1", "pin": 1},  # SIGNAL, not VCC
                    end={"type": "Free"},
                )
            ],
        )


def test_wire_to_wire_connection_uses_point_index() -> None:
    first = _wired_document()
    result = apply_semantic_operations(
        first,
        [
            AddWireOperation(
                net="VCC",
                points=[{"x": 10.0, "y": 25.0}, {"x": 40.0, "y": 25.0}],
                start={"type": "Wire", "wire_id": _wire_id(first), "point_index": 1},
                end={"type": "Free"},
            )
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    wires = root.findall("./Schematic/Nets/Net[@Id='0']/Wires/Wire")
    assert len(wires) == 2
    assert wires[1].get("Connected1") == "Wire"
    assert wires[1].get("Object1") == "0"
    assert wires[1].get("SubObject1") == "1"


def _wire_id(document: DipTraceDocument) -> str:
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None and snapshot.schematic.wires
    return snapshot.schematic.wires[0].stable_id


def test_delete_wire_removes_element_and_keeps_connectivity() -> None:
    document = _wired_document()
    wire_id = _wire_id(document)
    result = apply_semantic_operations(
        document, [DeleteWireOperation(selector={"ids": [wire_id]})]
    )
    root = ET.fromstring(result.raw_bytes)
    assert root.find("./Schematic/Nets/Net[@Id='0']/Wires/Wire") is None
    vcc = root.find("./Schematic/Nets/Net[@Id='0']")
    assert vcc is not None
    assert len(vcc.findall("./Pins/Item")) == 2  # pin connectivity untouched
    snapshot = build_snapshot(result.document)
    assert snapshot.schematic is not None
    assert snapshot.schematic.wires == []


def test_add_net_label_compiles_text_shape_bound_to_net() -> None:
    result = apply_semantic_operations(
        _load("schematic.xml"),
        [AddNetLabelOperation(net="VCC", x=12.0, y=22.0)],
    )
    root = ET.fromstring(result.raw_bytes)
    shape = root.find("./Schematic/Shapes/Shape")
    assert shape is not None
    assert shape.get("Type") == "Text"
    assert shape.get("NetId") == "0"
    assert shape.get("BusId") == "-1"
    assert shape.find("./Points/Point").get("X") == "12"  # type: ignore[union-attr]
    assert shape.findtext("./TextLines/TextLine") == "VCC"


def test_full_schematic_authoring_flow_via_service(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    service.create_document("schematic", "project/main.dch", sheets=["Main"])
    placed = service.place_part(
        "CompType0", "R1", 20.0, 20.0, pin_count=2, value="10k",
        name="RES_0603", path="project/main.dch", dry_run=True,
    )
    txid = placed["transaction"]["txid"]
    sha = placed["transaction"]["expected_sha256"]
    committed = service.place_part(
        "CompType0", "R1", 20.0, 20.0, pin_count=2, value="10k",
        name="RES_0603", path="project/main.dch", dry_run=False,
        expected_sha256=sha, txid=txid,
    )
    assert committed["transaction"]["status"] == "committed"
    service.place_part(
        "CompType0", "R2", 40.0, 20.0, pin_count=2, value="10k",
        name="RES_0603", path="project/main.dch", dry_run=False,
        expected_sha256=service.document_info("project/main.dch")["result"]["sha256"],
    )
    connected = service.connect_pins(
        "GND",
        [{"refdes": "R1", "pin": 1}, {"refdes": "R2", "pin": 0}],
        path="project/main.dch",
        dry_run=False,
        expected_sha256=service.document_info("project/main.dch")["result"]["sha256"],
    )
    assert connected["transaction"]["status"] == "committed"
    wired = service.add_wire(
        "GND",
        [{"x": 22.5, "y": 20.0}, {"x": 22.5, "y": 25.0}, {"x": 37.5, "y": 25.0}],
        {"type": "Pin", "refdes": "R1", "pin": 1},
        {"type": "Pin", "refdes": "R2", "pin": 0},
        path="project/main.dch",
        dry_run=False,
        expected_sha256=service.document_info("project/main.dch")["result"]["sha256"],
    )
    assert wired["transaction"]["status"] == "committed"
    labeled = service.add_net_label(
        "GND", 22.5, 25.0, path="project/main.dch", dry_run=False,
        expected_sha256=service.document_info("project/main.dch")["result"]["sha256"],
    )
    assert labeled["transaction"]["status"] == "committed"
    model = service.schematic_model("project/main.dch")
    result = model["result"]
    assert len(result["parts"]) == 2
    assert len(result["nets"]) == 1
    assert result["nets"][0]["name"] == "GND"
    assert len(result["wires"]) == 1


def test_set_panelization_compiles_official_structure(tmp_path: Path) -> None:
    target = tmp_path / "board.dip"
    shutil.copy(FIXTURES / "pcb.xml", target)
    service = _service(tmp_path, tmp_path / ".state")
    preview = service.set_panelization(
        {
            "panel_type": "V-Scoring",
            "columns": 3,
            "rows": 2,
            "column_spacing": 0.0,
            "row_spacing": 1.0,
            "rail_left": 5.0,
            "rail_bottom": 5.0,
        },
        path="board.dip",
        dry_run=True,
    )
    txid = preview["transaction"]["txid"]
    committed = service.set_panelization(
        {
            "panel_type": "V-Scoring",
            "columns": 3,
            "rows": 2,
            "column_spacing": 0.0,
            "row_spacing": 1.0,
            "rail_left": 5.0,
            "rail_bottom": 5.0,
        },
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["transaction"]["expected_sha256"],
        txid=txid,
    )
    assert committed["transaction"]["status"] == "committed"
    root = ET.fromstring(target.read_bytes())
    board = root.find("./Board")
    assert board is not None
    children = [child.tag for child in board]
    assert children.index("Panel") == children.index("BoardOutline") + 1
    panel = board.find("./Panel")
    assert panel is not None
    assert panel.get("Type") == "V-Scoring"
    assert panel.get("Columns") == "3"
    assert panel.get("Rows") == "2"
    assert panel.get("RailShow") == "Y"
    assert panel.get("RailLeft") == "5"
    assert panel.get("TabsDone") == "N"
    cleared = service.clear_panelization(
        path="board.dip",
        dry_run=False,
        expected_sha256=service.document_info("board.dip")["result"]["sha256"],
    )
    assert cleared["transaction"]["status"] == "committed"
    assert ET.fromstring(target.read_bytes()).find("./Board/Panel") is None


def test_clear_panelization_without_panel_fails() -> None:
    with pytest.raises(ObjectNotFoundError):
        apply_semantic_operations(_load("pcb.xml"), [ClearPanelizationOperation()])


def test_panelization_update_resets_manual_tabs(tmp_path: Path) -> None:
    raw = _load("pcb.xml").raw_bytes.replace(
        b"<ConnectivityCheck",
        b'<Panel Type="V-Scoring" Columns="2" Rows="1" TabsDone="Y">'
        b"<HorzTabsX><Item>10</Item></HorzTabsX></Panel>"
        b"<ConnectivityCheck",
    )
    document = _load_bytes(raw)
    result = apply_semantic_operations(
        document, [SetPanelizationOperation(columns=4, rows=3)]
    )
    root = ET.fromstring(result.raw_bytes)
    panel = root.find("./Board/Panel")
    assert panel is not None
    assert panel.get("Columns") == "4"
    assert panel.get("TabsDone") == "N"
    assert panel.find("./HorzTabsX") is None
