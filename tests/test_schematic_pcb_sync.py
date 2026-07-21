from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError
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
