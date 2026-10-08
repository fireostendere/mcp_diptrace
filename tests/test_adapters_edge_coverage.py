from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp import adapters
from diptrace_mcp.domain import QueryRequest, QuerySelector
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def test_adapter_public_read_models_and_object_payloads() -> None:
    pcb = _load("pcb.xml")
    schematic = _load("schematic.xml")
    assert adapters.get_document_info(pcb).source_type == "DipTrace-PCB"
    assert adapters.get_board_model(pcb).components
    assert adapters.get_schematic_model(schematic).parts
    with pytest.raises(DocumentError, match="PCB model"):
        adapters.get_board_model(schematic)
    with pytest.raises(DocumentError, match="Schematic model"):
        adapters.get_schematic_model(pcb)

    result = adapters.query_objects(
        pcb,
        QueryRequest(selector=QuerySelector(kinds=["component"]), limit=1),
    )
    assert result.items
    snapshot = adapters.build_snapshot(pcb)
    object_id = next(iter(snapshot.objects))
    payload = adapters.get_object(pcb, object_id)
    assert payload["stable_id"] == object_id and payload["document"]


def test_adapter_listing_queries_and_unsupported_document_guards() -> None:
    pcb = _load("pcb.xml")
    schematic = _load("schematic.xml")
    library = _load("component_library.xml")

    assert adapters.components(pcb, query="R1")["total"] == 1
    assert adapters.components(schematic, query="U1")["total"] >= 1
    assert adapters.component(pcb, "R1")["component"]["refdes"] == "R1"
    with pytest.raises(DocumentError, match="Component not found"):
        adapters.component(pcb, "missing")
    assert adapters.nets(pcb, query="VCC")["items"]
    assert adapters.nets(schematic, query="VCC")["items"]
    assert adapters.design_rules(schematic)["erc"] is not None

    with pytest.raises(DocumentError, match="Component listing"):
        adapters.components(library)
    with pytest.raises(DocumentError, match="Net listing"):
        adapters.nets(library)
    with pytest.raises(DocumentError, match="Design rules"):
        adapters.design_rules(library)


def test_adapter_generic_summary_and_bounded_element_rendering() -> None:
    library = _load("component_library.xml")
    summary = adapters.summarize(library)
    assert summary["top_level_sections"]

    root = ET.Element("Root")
    root.text = " value "
    for index in range(201):
        ET.SubElement(root, "Child", {"index": str(index)})
    rendered = adapters._element_data(root)
    assert rendered["text"] == "value"
    assert rendered["children_truncated"] == 1
    assert adapters._element_data(None) is None


def test_adapter_side_and_empty_schematic_helpers() -> None:
    assert adapters._side_from_layer("Bottom Silk") == "Bottom"
    assert adapters._side_from_layer("Mechanical") is None
    library = _load("component_library.xml")
    assert adapters._schematic_sheets(library) == []
    assert adapters._schematic_erc(library) == {}
    assert adapters._schematic_buses(library) == []
    assert adapters._schematic_differential_pairs(library) == []
