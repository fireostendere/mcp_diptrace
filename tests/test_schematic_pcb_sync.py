from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError, LockedObjectError
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
    assert [
        item.get("PatternStyle")
        for item in root.findall(
            "./Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern"
        )
    ] == ["PatType0", "PatType1"]
    assert {
        item.get("Name")
        for item in root.findall(
            "./Library[@Type='DipTrace-PatternLibrary']/PadStyles/PadStyle"
        )
    } == {"SMD_0603", "THT_1MM"}
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
    assert len(root.findall("./Board/Ratlines/Ratline")) == 2


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
        {"Id": "2", "NetClass": "0", "Locked": "N"},
    )
    ET.SubElement(extra_net, "Name").text = "EXTRA"
    ET.SubElement(extra_net, "Pads")
    ET.SubElement(extra_net, "Traces")

    ratlines = root.find("./Board/Ratlines")
    assert ratlines is not None
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
    assert len(root.findall("./Board/Ratlines/Ratline")) == 2

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
    assert response["transaction"]["status"] == "validated"
    assert response["result"]["schematic_source"]["sha256"]
    assert "<Component" in response["preview"]["diff"]
    assert pcb_path.read_bytes() == build_pcb_document()
