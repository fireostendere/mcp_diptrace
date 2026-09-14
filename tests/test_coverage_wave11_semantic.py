from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import semantic_compiler as compiler
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import ObjectRecord, QuerySelector
from diptrace_mcp.errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    EditError,
    LockedObjectError,
    ObjectNotFoundError,
    ScopeRequiredError,
)
from diptrace_mcp.geometry import Point
from diptrace_mcp.operations import (
    AddNetLabelOperation,
    AddTestpointOperation,
    AddWireOperation,
    AssignNetsToClassOperation,
    WireEndpoint,
)
from diptrace_mcp.scaffolding import build_pcb_document
from diptrace_mcp.synchronization import ComponentSyncMapping, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def _record(kind: str, suffix: str = "0", **values: object) -> ObjectRecord:
    return ObjectRecord(stable_id=f"{kind}_{suffix * 16}", kind=kind, **values)


def _sync_operation():
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    mappings = [
        ComponentSyncMapping(
            refdes="R1",
            pattern_style="PatType0",
            pin_map=[
                {"part_id": "0", "pin": 0, "pad_number": "1"},
                {"part_id": "0", "pin": 1, "pad_number": "2"},
            ],
        ),
        ComponentSyncMapping(
            refdes="U1",
            pattern_style="PatType1",
            pin_map=[
                {"part_id": "1", "pin": 0, "pad_number": "1"},
                {"part_id": "2", "pin": 0, "pad_number": "2"},
            ],
        ),
    ]
    operation = build_sync_plan(
        schematic,
        pcb,
        mappings=mappings,
        pattern_documents=[_load("pattern_library.xml")],
    ).operation
    return pcb, operation


def test_semantic_entry_and_shared_helper_guards() -> None:
    pcb = _load("pcb.xml")
    schematic = _load("schematic.xml")
    with pytest.raises(EditError, match="At least one"):
        compiler.apply_semantic_operations(pcb, [])
    with pytest.raises(ScopeRequiredError):
        compiler._select_records(SimpleNamespace(), QuerySelector(), {"component"})
    empty_snapshot = SimpleNamespace(select=lambda *_args, **_kwargs: [])
    with pytest.raises(ObjectNotFoundError):
        compiler._select_records(
            empty_snapshot,
            QuerySelector(ids=["component_0000000000000000"]),
            {"component"},
        )

    element = ET.Element("Part")
    with pytest.raises(EditError, match="has no X"):
        compiler._coordinate_mm(pcb, element, "X")
    element.set("X", "bad")
    with pytest.raises(EditError, match="Invalid X"):
        compiler._coordinate_mm(pcb, element, "X")
    with pytest.raises(CapabilityUnavailableError, match="schematic"):
        compiler._require_schematic(pcb, "Feature")
    with pytest.raises(CapabilityUnavailableError, match="PCB"):
        compiler._require_pcb(schematic, "Feature")
    with pytest.raises(ObjectNotFoundError, match="Sheet"):
        compiler._require_sheet(schematic, 99)

    locked = _record("component", locked=True, label="U1")
    with pytest.raises(LockedObjectError):
        compiler._ensure_unlocked(locked, False)
    with pytest.raises(EditError, match="Cannot resolve XML"):
        compiler._resolved_element(SimpleNamespace(elements={}), locked)
    with pytest.raises(LockedObjectError, match="reconciliation"):
        compiler._require_reconciliation_unlocked(
            ET.Element("Component", {"Locked": "Y"}), "component", allow_locked=False
        )


def test_semantic_metadata_and_coordinate_helpers() -> None:
    element = ET.Element("Component", {"Angle": "1"})
    compiler._set_angle_attribute(element, 0)
    assert "Angle" not in element.attrib
    assert compiler._set_additional_fields(element, {}) == ({}, 0)
    fields = ET.SubElement(element, "AddFields")
    existing = ET.SubElement(fields, "AddField")
    ET.SubElement(existing, "Name").text = "empty"
    before, patches = compiler._set_additional_fields(element, {"empty": "value"})
    assert before == {"empty": ""} and patches == 1

    orphan = _record("component_text")
    with pytest.raises(EditError, match="no parent"):
        compiler._board_to_component_local(SimpleNamespace(), orphan, Point(0, 0))
    parent = _record("component", "1", position=None)
    child = orphan.model_copy(update={"parent_id": parent.stable_id})
    with pytest.raises(EditError, match="no position"):
        compiler._board_to_component_local(
            SimpleNamespace(get_object=lambda _value: parent), child, Point(0, 0)
        )

    first = _record("component", refdes="TP1")
    second = _record("component", "1", refdes="TP2")
    snapshot = SimpleNamespace(objects={first.stable_id: first, second.stable_id: second})
    assert compiler._next_testpoint_refdes(snapshot) == "TP3"
    with pytest.raises(AmbiguousSelectorError, match="unique"):
        compiler._validate_refdes_change(snapshot, [first, second], "TP9")


def test_testpoint_position_and_lookup_failures() -> None:
    point = Point(5, 5)
    with pytest.raises(EditError, match="outline"):
        compiler._require_testpoint_position(SimpleNamespace(board=None), point, 1)
    board = SimpleNamespace(
        outline={"points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]}
    )
    with pytest.raises(EditError, match="outside"):
        compiler._require_testpoint_position(
            SimpleNamespace(board=board, objects={}), Point(20, 20), 1
        )

    document = _load("pcb.xml")
    with pytest.raises(ObjectNotFoundError, match="Net class"):
        compiler._find_net_class(document, "missing")
    duplicate = ET.fromstring(document.raw_bytes)
    classes = duplicate.find("./Board/NetClasses")
    assert classes is not None
    classes.append(ET.fromstring(ET.tostring(classes[0])))
    duplicate_document = DipTraceDocument.from_bytes(
        document.path, ET.tostring(duplicate, encoding="utf-8", xml_declaration=True)
    )
    with pytest.raises(AmbiguousSelectorError, match="ambiguous"):
        compiler._find_net_class(duplicate_document, "Default")


def test_semantic_operation_error_paths_and_sparse_testpoint_creation() -> None:
    pcb = _load("pcb.xml")
    schematic = _load("schematic.xml")
    with pytest.raises(CapabilityUnavailableError, match="PCB"):
        compiler.apply_semantic_operations(
            schematic,
            [AddTestpointOperation(net="VCC", x=1, y=1, pad_diameter=1)],
        )
    with pytest.raises(ObjectNotFoundError, match="Net was not found"):
        compiler.apply_semantic_operations(
            pcb,
            [AddTestpointOperation(net="missing", x=1, y=1, pad_diameter=1)],
        )
    with pytest.raises(ObjectNotFoundError, match="Net class"):
        compiler.apply_semantic_operations(
            pcb,
            [
                AssignNetsToClassOperation(
                    selector=QuerySelector(names=["VCC"]), class_name="missing"
                )
            ],
        )
    with pytest.raises(ObjectNotFoundError, match="Net was not found"):
        compiler.apply_semantic_operations(
            schematic,
            [AddNetLabelOperation(net="missing", x=1, y=1)],
        )
    with pytest.raises(ObjectNotFoundError, match="Net was not found"):
        compiler.apply_semantic_operations(
            schematic,
            [
                AddWireOperation(
                    net="missing",
                    points=[{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                    start=WireEndpoint(type="Free"),
                    end=WireEndpoint(type="Free"),
                )
            ],
        )

    root = ET.fromstring(pcb.raw_bytes)
    components = root.find("./Board/Components")
    assert components is not None
    root.find("./Board").remove(components)  # type: ignore[union-attr]
    library = root.find("./Library[@Type='DipTrace-PatternLibrary']")
    assert library is not None
    root.remove(library)
    sparse = DipTraceDocument.from_bytes(
        pcb.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    result = compiler.apply_semantic_operations(
        sparse,
        [AddTestpointOperation(net="VCC", x=5, y=5, pad_diameter=1, hole_diameter=0.4)],
    )
    assert result.patch_count == 6


def test_sync_endpoint_resolution_guards() -> None:
    with pytest.raises(ObjectNotFoundError, match="component"):
        compiler._sync_endpoint({}, "U1", "1")
    component = ET.Element("Component", {"Id": "1"})
    ET.SubElement(ET.SubElement(component, "Pads"), "Pad", {"Id": "1", "Number": "1"})
    with pytest.raises(EditError, match="unique pad"):
        compiler._sync_endpoint({"u1": component}, "U1", "2")
    key, pad = compiler._sync_endpoint({"u1": component}, "U1", "1")
    assert key == ("1", "1") and pad.get("Number") == "1"


def test_real_snapshot_helper_identity() -> None:
    snapshot = build_snapshot(_load("pcb.xml"))
    assert compiler._next_testpoint_refdes(snapshot).startswith("TP")


def test_sync_repairs_pattern_defaults_and_missing_component_container() -> None:
    pcb, operation = _sync_operation()
    synced = compiler.apply_semantic_operations(pcb, [operation]).document
    root = ET.fromstring(synced.raw_bytes)
    pattern = root.find(
        "./Library[@Type='DipTrace-ComponentLibrary']/Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern"
    )
    board = root.find("./Board")
    components = root.find("./Board/Components")
    assert pattern is not None and board is not None and components is not None
    pattern.set("Id", "99")
    for name in ("LockTypeChange", "Float1", "Float2", "Float3", "Int1", "Int2"):
        pattern.attrib.pop(name, None)
    board.remove(components)
    damaged = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    repaired = compiler.apply_semantic_operations(damaged, [operation])
    repaired_root = ET.fromstring(repaired.raw_bytes)
    repaired_pattern = repaired_root.find(
        "./Library[@Type='DipTrace-ComponentLibrary']/Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern"
    )
    assert repaired_pattern is not None and repaired_pattern.get("Id") == "0"
    assert repaired_root.findall("./Board/Components/Component")


def test_sync_rejects_invalid_library_definitions_and_duplicate_refdes() -> None:
    pcb, operation = _sync_operation()
    for update, message in (
        ({"pad_style_xml": ["<Pattern/>"]}, "invalid PadStyle"),
        ({"pattern_xml": ["<PadStyle/>"]}, "invalid Pattern"),
    ):
        with pytest.raises(EditError, match=message):
            compiler.apply_semantic_operations(pcb, [operation.model_copy(update=update)])

    synced = compiler.apply_semantic_operations(pcb, [operation]).document
    root = ET.fromstring(synced.raw_bytes)
    components = root.find("./Board/Components")
    existing = root.find("./Board/Components/Component")
    assert components is not None and existing is not None
    components.append(deepcopy(existing))
    duplicate = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    with pytest.raises(AmbiguousSelectorError, match="duplicate RefDes"):
        compiler.apply_semantic_operations(duplicate, [operation])


def test_sync_reconnects_unrouted_endpoint_and_repairs_pad_membership() -> None:
    pcb, operation = _sync_operation()
    synced = compiler.apply_semantic_operations(pcb, [operation]).document
    root = ET.fromstring(synced.raw_bytes)
    nets = root.findall("./Board/Nets/Net")
    assert len(nets) >= 2
    source_pads = nets[0].find("./Pads")
    target_pads = nets[1].find("./Pads")
    assert source_pads is not None and target_pads is not None
    endpoint = source_pads.find("./Item")
    assert endpoint is not None
    source_pads.remove(endpoint)
    target_pads.append(endpoint)
    for component_pad in root.findall("./Board/Components/Component/Pads/Pad"):
        component_pad.attrib.pop("InternalConnection", None)
        component_pad.set("NetId", "-1")
    moved = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    with pytest.raises(EditError, match="allow_reconnect"):
        compiler.apply_semantic_operations(moved, [operation])
    repaired = compiler.apply_semantic_operations(
        moved, [operation.model_copy(update={"allow_reconnect": True})]
    )
    repaired_root = ET.fromstring(repaired.raw_bytes)
    assert all(
        pad.get("InternalConnection") == "-1"
        for pad in repaired_root.findall("./Board/Components/Component/Pads/Pad")
    )


def test_sync_rebuilds_missing_nets_and_existing_component_properties() -> None:
    pcb, operation = _sync_operation()
    synced = compiler.apply_semantic_operations(pcb, [operation]).document
    root = ET.fromstring(synced.raw_bytes)
    board = root.find("./Board")
    nets = root.find("./Board/Nets")
    component = root.find("./Board/Components/Component")
    assert board is not None and nets is not None and component is not None
    board.remove(nets)
    for tag in ("Name", "Value"):
        child = component.find(f"./{tag}")
        if child is not None:
            component.remove(child)
    blank = ET.SubElement(root.find("./Board/Components"), "Component")  # type: ignore[arg-type]
    ET.SubElement(blank, "RefDes").text = ""
    damaged = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    result = compiler.apply_semantic_operations(
        damaged,
        [operation.model_copy(update={"update_existing_properties": True})],
    )
    repaired = ET.fromstring(result.raw_bytes)
    assert repaired.findall("./Board/Nets/Net")
    assert repaired.find("./Board/Components/Component/Name") is not None


def test_sync_repairs_existing_net_metadata_and_detects_duplicate_names() -> None:
    pcb, operation = _sync_operation()
    synced = compiler.apply_semantic_operations(pcb, [operation]).document
    root = ET.fromstring(synced.raw_bytes)
    nets = root.find("./Board/Nets")
    net = root.find("./Board/Nets/Net")
    assert nets is not None and net is not None
    net.attrib.pop("HiddenId", None)
    net.attrib.pop("RouteMode", None)
    net.set("HideRatlines", "Y")
    pads = net.find("./Pads")
    if pads is not None:
        net.remove(pads)
    ET.SubElement(nets, "Net", {"Id": "blank"})
    damaged = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    repaired = compiler.apply_semantic_operations(damaged, [operation])
    repaired_net = ET.fromstring(repaired.raw_bytes).find("./Board/Nets/Net")
    assert repaired_net is not None and repaired_net.get("RouteMode") == "Ratlines"
    assert repaired_net.find("./Pads") is not None

    root = ET.fromstring(synced.raw_bytes)
    nets = root.find("./Board/Nets")
    net = root.find("./Board/Nets/Net")
    assert nets is not None and net is not None
    nets.append(deepcopy(net))
    duplicate = DipTraceDocument.from_bytes(
        synced.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    with pytest.raises(AmbiguousSelectorError, match="duplicate net name"):
        compiler.apply_semantic_operations(duplicate, [operation])


def test_sync_disables_ratline_generation_explicitly() -> None:
    pcb, operation = _sync_operation()
    result = compiler.apply_semantic_operations(
        pcb, [operation.model_copy(update={"create_ratlines": False})]
    )
    assert all(
        net.get("HideRatlines") == "Y"
        for net in ET.fromstring(result.raw_bytes).findall("./Board/Nets/Net")
    )
