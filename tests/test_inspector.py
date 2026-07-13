from pathlib import Path

from diptrace_mcp import inspector
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def test_schematic_summary_and_grouped_components() -> None:
    document = load("schematic.xml")
    summary = inspector.summarize(document)
    listing = inspector.components(document)

    assert summary["kind"] == "schematic"
    assert summary["component_count"] == 2
    assert summary["part_count"] == 3
    assert summary["unconnected_pin_count"] == 1
    assert summary["intentional_no_connect_count"] == 1
    assert listing["total"] == 2
    assert next(item for item in listing["items"] if item["refdes"] == "U1")["part_count"] == 2


def test_pcb_summary_components_nets_and_rules() -> None:
    document = load("pcb.xml")
    summary = inspector.summarize(document)
    listing = inspector.nets(document)
    rules = inspector.design_rules(document)

    assert summary["kind"] == "pcb"
    assert summary["component_count"] == 2
    assert summary["copper_layer_count"] == 2
    assert summary["routed_trace_count"] == 1
    assert listing["items"][0]["endpoint_count"] == 2
    assert {endpoint["refdes"] for endpoint in listing["items"][0]["endpoints"]} == {
        "R1",
        "U1",
    }
    assert rules["drc"]["attributes"]["CheckClearance"] == "Y"


def test_component_details_include_connected_nets() -> None:
    details = inspector.component(load("schematic.xml"), "R1")

    assert details["component"]["value"] == "10k"
    assert {net["name"] for net in details["connected_nets"]} == {"VCC", "SIGNAL"}
