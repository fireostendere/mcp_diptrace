from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError, LockedObjectError
from diptrace_mcp.operations import SyncSchematicToPcbOperation
from diptrace_mcp.scaffolding import build_pcb_document
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.synchronization import ComponentSyncMapping, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, MAX_BYTES)


def _mapping() -> list[ComponentSyncMapping]:
    return [
        ComponentSyncMapping(refdes="R1", pattern_style="PatType0"),
        ComponentSyncMapping(
            refdes="U1",
            pattern_style="PatType1",
            pin_map=[
                {"part_id": "1", "pin": 0, "pad_number": "1"},
                {"part_id": "2", "pin": 0, "pad_number": "2"},
            ],
        ),
    ]


def test_sync_compiler_rejects_entity_in_pattern_xml_even_if_model_is_bypassed() -> None:
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    operation = SyncSchematicToPcbOperation.model_construct(
        schematic_sha256="0" * 64,
        components=[],
        pattern_xml=[
            '<!DOCTYPE Pattern [<!ENTITY x "boom">]>'
            '<Pattern PatternStyle="unsafe">&x;</Pattern>'
        ],
    )

    with pytest.raises(
        EditError,
        match="DTD and ENTITY declarations are forbidden in pattern definitions",
    ):
        apply_semantic_operations(pcb, [operation])


def test_sync_populates_empty_pcb_and_copies_patterns() -> None:
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )
    result = apply_semantic_operations(pcb, [plan.operation])
    root = ET.fromstring(result.raw_bytes)
    components = root.findall("./Board/Components/Component")
    assert [item.findtext("./RefDes") for item in components] == ["R1", "U1"]
    assert [item.get("PatternStyle") for item in components] == ["PatType0", "PatType1"]
    embedded_patterns = root.findall(
        "./Library[@Type='DipTrace-ComponentLibrary']/"
        "Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern"
    )
    assert [item.get("PatternStyle") for item in embedded_patterns] == [
        "PatType0",
        "PatType1",
    ]
    assert [item.get("Id") for item in embedded_patterns] == ["0", "1"]
    assert all(item.get("LockTypeChange") == "N" for item in embedded_patterns)
    assert all(item.get("Float1") == "0" for item in embedded_patterns)
    assert all(item.get("Float2") == "0" for item in embedded_patterns)
    assert all(item.get("Float3") == "0" for item in embedded_patterns)
    assert all(item.get("Int1") == "0" for item in embedded_patterns)
    assert all(item.get("Int2") == "0" for item in embedded_patterns)
    assert {
        item.get("Name")
        for item in root.findall(
            "./Library[@Type='DipTrace-ComponentLibrary']/"
            "Library[@Type='DipTrace-PatternLibrary']/PadStyles/PadStyle"
        )
    } == {"SMD_0603", "THT_1MM"}
    outer_library = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert outer_library is not None
    assert outer_library.get("Version") is None
    pattern_library = outer_library.find("./Library[@Type='DipTrace-PatternLibrary']")
    assert pattern_library is not None
    assert pattern_library.get("Version") is None
    assert root.find("./Library[@Type='DipTrace-PatternLibrary']") is None
    nets = {
        net.findtext("./Name"): {
            (item.get("Comp"), item.get("Pad"))
            for item in net.findall("./Pads/Item")
        }
        for net in root.findall("./Board/Nets/Net")
    }
    assert nets == {
        "VCC": {("0", "0"), ("1", "0")},
        "SIGNAL": {("0", "1"), ("1", "1")},
    }
    assert {
        (component.get("Id"), pad.get("Id")): (
            pad.get("NetId"),
            pad.get("InternalConnection"),
        )
        for component in components
        for pad in component.findall("./Pads/Pad")
    } == {
        ("0", "0"): ("0", "-1"),
        ("0", "1"): ("1", "-1"),
        ("1", "0"): ("0", "-1"),
        ("1", "1"): ("1", "-1"),
    }
    assert root.find("./Board/Ratlines") is None
    assert [net.get("HiddenId") for net in root.findall("./Board/Nets/Net")] == [
        "0",
        "1",
    ]
    for component in components:
        assert component.get("MarkingFontSize") == "10"
        assert component.get("MarkingFontSizeFloat") == "10"
        assert component.get("GridAlign") == "Pad"
        refdes_silk = component.find("./RefDesMarking/Silk")
        name_silk = component.find("./NameMarking/Silk")
        value_silk = component.find("./ValueMarking/Silk")
        assert refdes_silk is not None and refdes_silk.get("Align") == "Top"
        assert name_silk is not None and name_silk.get("Align") == "Left"
        assert value_silk is not None and value_silk.get("Align") == "Bottom"


def test_sync_bootstraps_missing_embedded_libraries() -> None:
    schematic = _load("schematic.xml")
    root = ET.fromstring(build_pcb_document())
    for library in list(root.findall("./Library")):
        root.remove(library)
    pcb = DipTraceDocument.from_bytes(
        Path("board.dip"), ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )

    result = apply_semantic_operations(pcb, [plan.operation])
    result_root = ET.fromstring(result.raw_bytes)
    component_library = result_root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert component_library is not None
    pattern_library = component_library.find("./Library[@Type='DipTrace-PatternLibrary']")
    assert pattern_library is not None
    assert pattern_library.find("./PadStyles") is not None
    assert [
        item.get("PatternStyle") for item in pattern_library.findall("./Patterns/Pattern")
    ] == ["PatType0", "PatType1"]


def test_sync_restores_missing_embedded_library_units() -> None:
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    initial_plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )
    initial = apply_semantic_operations(pcb, [initial_plan.operation])
    root = ET.fromstring(initial.raw_bytes)
    component_library = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert component_library is not None
    pattern_library = component_library.find("./Library[@Type='DipTrace-PatternLibrary']")
    assert pattern_library is not None
    component_library.attrib.pop("Units", None)
    pattern_library.attrib.pop("Units", None)
    missing_units = DipTraceDocument.from_bytes(
        Path("board.dip"), ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    repair_plan = build_sync_plan(
        schematic,
        missing_units,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )

    repaired = apply_semantic_operations(missing_units, [repair_plan.operation])
    repaired_root = ET.fromstring(repaired.raw_bytes)
    repaired_component_library = repaired_root.find(
        "./Library[@Type='DipTrace-ComponentLibrary']"
    )
    assert repaired_component_library is not None
    repaired_pattern_library = repaired_component_library.find(
        "./Library[@Type='DipTrace-PatternLibrary']"
    )
    assert repaired_pattern_library is not None
    assert repaired_component_library.get("Units") == missing_units.units
    assert repaired_pattern_library.get("Units") == missing_units.units


def test_sync_operation_is_idempotent() -> None:
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )
    first = apply_semantic_operations(pcb, [plan.operation])
    second_plan = build_sync_plan(
        schematic,
        first.document,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )
    second = apply_semantic_operations(first.document, [second_plan.operation])
    assert second.patch_count == 0
    assert second.raw_bytes == first.raw_bytes


def test_sync_without_ratlines_hides_derived_guides() -> None:
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
        create_ratlines=False,
    )

    result = apply_semantic_operations(pcb, [plan.operation])
    root = ET.fromstring(result.raw_bytes)
    assert root.find("./Board/Ratlines") is None
    assert {
        net.get("HideRatlines") for net in root.findall("./Board/Nets/Net")
    } == {"Y"}


def _synced_pcb_with_extras(*, locked_extra: bool = False) -> DipTraceDocument:
    schematic = _load("schematic.xml")
    empty = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    additive_plan = build_sync_plan(
        schematic,
        empty,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
    )
    synced = apply_semantic_operations(empty, [additive_plan.operation]).document
    root = ET.fromstring(synced.raw_bytes)
    components = root.find("./Board/Components")
    assert components is not None
    extra = ET.SubElement(
        components,
        "Component",
        {
            "Id": "2",
            "UpdateId": "102",
            "PatternStyle": "PatType0",
            "X": "30",
            "Y": "30",
            "Side": "Top",
            "Locked": "Y" if locked_extra else "N",
            "Selected": "N",
        },
    )
    ET.SubElement(extra, "RefDes").text = "X1"
    ET.SubElement(extra, "Name").text = "EXTRA"
    ET.SubElement(extra, "Value").text = "EXTRA"
    pads = ET.SubElement(extra, "Pads")
    ET.SubElement(pads, "Pad", {"Id": "0", "Number": "1"})

    vcc = root.find("./Board/Nets/Net[Name='VCC']")
    assert vcc is not None
    vcc_pads = vcc.find("./Pads")
    vcc_traces = vcc.find("./Traces")
    assert vcc_pads is not None and vcc_traces is not None
    ET.SubElement(vcc_pads, "Item", {"Comp": "2", "Pad": "0"})
    trace = ET.SubElement(vcc_traces, "Trace", {"Id": "0", "Locked": "N"})
    points = ET.SubElement(trace, "Points")
    ET.SubElement(points, "Point", {"X": "10", "Y": "10", "Layer": "0"})
    ET.SubElement(points, "Point", {"X": "30", "Y": "30", "Layer": "0"})

    nets = root.find("./Board/Nets")
    assert nets is not None
    extra_net = ET.SubElement(
        nets,
        "Net",
        {"Id": "2", "HiddenId": "2", "NetClass": "0", "Locked": "N"},
    )
    ET.SubElement(extra_net, "Name").text = "EXTRA"
    ET.SubElement(extra_net, "Pads")
    ET.SubElement(extra_net, "Traces")

    board = root.find("./Board")
    assert board is not None
    ratlines = root.find("./Board/Ratlines")
    if ratlines is None:
        ratlines = ET.SubElement(board, "Ratlines")
    ET.SubElement(
        ratlines,
        "Ratline",
        {
            "Id": "99",
            "Hidden": "N",
            "X1": "10",
            "Y1": "10",
            "X2": "30",
            "Y2": "30",
            "Comp1": "0",
            "Pad1": "0",
            "Comp2": "2",
            "Pad2": "0",
        },
    )
    return DipTraceDocument.from_bytes(
        Path("board.dip"), ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def test_exact_sync_removes_unmatched_objects_and_changed_net_traces() -> None:
    schematic = _load("schematic.xml")
    pcb = _synced_pcb_with_extras()
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
        reconciliation_mode="exact",
    )

    first = apply_semantic_operations(pcb, [plan.operation])
    root = ET.fromstring(first.raw_bytes)
    assert {
        item.findtext("./RefDes")
        for item in root.findall("./Board/Components/Component")
    } == {"R1", "U1"}
    assert {
        item.findtext("./Name") for item in root.findall("./Board/Nets/Net")
    } == {"VCC", "SIGNAL"}
    assert root.findall("./Board/Nets/Net/Traces/Trace") == []
    assert root.find("./Board/Ratlines") is None

    second_plan = build_sync_plan(
        schematic,
        first.document,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
        reconciliation_mode="exact",
    )
    second = apply_semantic_operations(first.document, [second_plan.operation])
    assert second.patch_count == 0
    assert second.raw_bytes == first.raw_bytes


def test_exact_sync_rejects_locked_unmatched_component_by_default() -> None:
    schematic = _load("schematic.xml")
    pcb = _synced_pcb_with_extras(locked_extra=True)
    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=_mapping(),
        pattern_documents=[_load("pattern_library.xml")],
        reconciliation_mode="exact",
    )

    with pytest.raises(LockedObjectError, match="allow_locked_reconciliation"):
        apply_semantic_operations(pcb, [plan.operation])


def test_sync_requires_explicit_mapping_for_connected_multi_part_pin() -> None:
    schematic = _load("schematic.xml")
    pcb = DipTraceDocument.from_bytes(Path("board.dip"), build_pcb_document())
    with pytest.raises(EditError, match="Pin-to-pad mapping"):
        build_sync_plan(
            schematic,
            pcb,
            mappings=[
                ComponentSyncMapping(refdes="R1", pattern_style="PatType0"),
                ComponentSyncMapping(refdes="U1", pattern_style="PatType1"),
            ],
            pattern_documents=[_load("pattern_library.xml")],
        )


def test_sync_service_produces_guarded_transaction_preview(tmp_path: Path) -> None:
    schematic_path = tmp_path / "schematic.dch"
    pcb_path = tmp_path / "board.dip"
    pattern_path = tmp_path / "patterns.lib"
    shutil.copy2(FIXTURES / "schematic.xml", schematic_path)
    shutil.copy2(FIXTURES / "pattern_library.xml", pattern_path)
    pcb_path.write_bytes(build_pcb_document())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
            max_document_bytes=MAX_BYTES,
        )
    )
    response = service.sync_schematic_to_pcb(
        str(schematic_path),
        str(pcb_path),
        component_mappings=[item.model_dump() for item in _mapping()],
        pattern_library_paths=[str(pattern_path)],
        dry_run=True,
    )
    assert response["ok"] is True
    assert response["written"] is False
    assert response["transaction"]["status"] == "validated"
    assert response["result"]["schematic_source"]["sha256"]
    assert response["preview"]["inline"] is False
    diff_uri = response["preview"]["artifacts"]["diff"]["resource_uri"]
    assert diff_uri.endswith("/diff")
    txid = response["transaction"]["txid"]
    assert "<Component" in service.transactions.diff_path(txid).read_text(encoding="utf-8")
    assert pcb_path.read_bytes() == build_pcb_document()
