from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.advanced_review import check_thermal_metadata, check_trace_board_edge
from diptrace_mcp.lengths import _stackup_copper_centers
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
PCB = FIXTURES / "diff_pair_pcb.xml"
MAX_BYTES = 10_000_000


def _snapshot(root: ET.Element):
    return build_snapshot(
        DipTraceDocument.from_bytes(
            PCB,
            ET.tostring(root, encoding="utf-8", xml_declaration=True),
        )
    )


def _root() -> ET.Element:
    return ET.fromstring(PCB.read_bytes())


def _add_trace_to_board_rule(root: ET.Element, clearance: str, layer: str = "0") -> None:
    drc = ET.SubElement(root.find("./Board"), "DRC")
    clearances = ET.SubElement(drc, "LayClearances")
    ET.SubElement(clearances, "LayClearance", {"Lay": layer, "TraceToBoard": clearance})


def _add_field(component: ET.Element, name: str, text: str) -> None:
    fields = component.find("./AddFields")
    if fields is None:
        fields = ET.SubElement(component, "AddFields")
    field = ET.SubElement(fields, "AddField")
    ET.SubElement(field, "Name").text = name
    ET.SubElement(field, "Text").text = text


def test_trace_board_edge_reports_copper_too_close_to_outline() -> None:
    root = _root()
    _add_trace_to_board_rule(root, "50")

    findings, metrics = check_trace_board_edge(_snapshot(root))

    assert metrics == {"segments_checked": 2}
    assert len(findings) == 2
    assert {finding.check_id for finding in findings} == {"pcb.trace_board_edge"}
    first = findings[0]
    assert first.severity == "error"
    assert first.measured is not None and first.required == pytest.approx(50.0)
    assert first.units == "mm"


def test_trace_board_edge_passes_when_clearance_is_met() -> None:
    root = _root()
    _add_trace_to_board_rule(root, "0.001")

    findings, metrics = check_trace_board_edge(_snapshot(root))

    assert findings == []
    assert metrics == {"segments_checked": 2}


def test_trace_board_edge_skips_without_trace_to_board_rules() -> None:
    findings, metrics = check_trace_board_edge(
        build_snapshot(DipTraceDocument.load(PCB, MAX_BYTES))
    )

    assert findings == []
    assert metrics == {"skipped": "trace_to_board_rules_unavailable"}


def test_trace_board_edge_skips_degenerate_outline() -> None:
    root = _root()
    _add_trace_to_board_rule(root, "50")
    points = root.find("./Board/BoardOutline/Points")
    assert points is not None
    for point in list(points)[2:]:
        points.remove(point)

    findings, metrics = check_trace_board_edge(_snapshot(root))

    assert findings == []
    assert metrics == {"skipped": "board_outline_invalid"}


def test_trace_board_edge_skips_missing_outline() -> None:
    root = _root()
    _add_trace_to_board_rule(root, "50")
    board = root.find("./Board")
    assert board is not None
    outline = board.find("./BoardOutline")
    assert outline is not None
    board.remove(outline)

    findings, metrics = check_trace_board_edge(_snapshot(root))

    assert findings == []
    assert metrics == {"skipped": "board_outline_missing"}


def test_thermal_metadata_flags_dissipation_without_strategy() -> None:
    root = _root()
    component = root.find("./Board/Components/Component")
    assert component is not None
    _add_field(component, "Power (W)", "1.5")

    findings, metrics = check_thermal_metadata(_snapshot(root))

    assert metrics == {"annotated_components": 1}
    assert len(findings) == 1
    assert findings[0].check_id == "pcb.thermal_metadata"
    assert findings[0].severity == "info"


def test_thermal_metadata_accepts_documented_strategy() -> None:
    root = _root()
    component = root.find("./Board/Components/Component")
    assert component is not None
    _add_field(component, "Power (W)", "1.5")
    _add_field(component, "Thermal Strategy", "2oz copper pour under the tab")

    findings, metrics = check_thermal_metadata(_snapshot(root))

    assert findings == []
    assert metrics == {"annotated_components": 1}


def test_thermal_metadata_skips_without_power_metadata() -> None:
    findings, metrics = check_thermal_metadata(
        build_snapshot(DipTraceDocument.load(PCB, MAX_BYTES))
    )

    assert findings == []
    assert metrics == {"skipped": "explicit_component_power_metadata_unavailable"}


def test_stackup_copper_centers_are_measured_from_the_stack() -> None:
    centers, reason = _stackup_copper_centers(
        build_snapshot(DipTraceDocument.load(PCB, MAX_BYTES))
    )

    assert reason is None
    assert centers == {"0": pytest.approx(0.0175), "1": pytest.approx(0.2325)}


def test_stackup_copper_centers_reject_missing_layer_id() -> None:
    root = _root()
    items = root.find("./Board").findall(".//LayerStackItem")
    del items[0].attrib["Lay"]

    centers, reason = _stackup_copper_centers(_snapshot(root))

    assert centers is None
    assert reason == "copper_layer_id_missing"


def test_stackup_copper_centers_reject_duplicate_layer_id() -> None:
    root = _root()
    items = root.find("./Board").findall(".//LayerStackItem")
    items[2].set("Lay", "0")

    centers, reason = _stackup_copper_centers(_snapshot(root))

    assert centers is None
    assert reason == "duplicate_copper_layer_id"
