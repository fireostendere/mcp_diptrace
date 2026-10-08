from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp import copper_pours
from diptrace_mcp.errors import EditError
from diptrace_mcp.geometry import Point
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_copper_pour_validation_matrix() -> None:
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    cases = (
        (schematic, {"net": "VCC", "layers": ["Top"]}, "PCB document"),
        (pcb, {"net": " ", "layers": ["Top"]}, "net must not be empty"),
        (pcb, {"net": "VCC", "layers": []}, "At least one"),
        (pcb, {"net": "VCC", "layers": ["Top"], "clearance_mm": -1}, "non-negative"),
        (pcb, {"net": "VCC", "layers": ["Top"], "spoke_width_mm": 0}, "positive"),
        (pcb, {"net": "VCC", "layers": ["Top"], "stitch_pitch_mm": 0}, "positive"),
        (pcb, {"net": "missing", "layers": ["Top"]}, "Unique copper-pour net"),
        (pcb, {"net": "VCC", "layers": ["missing"]}, "Unique copper-pour layer"),
    )
    for document, kwargs, message in cases:
        with pytest.raises(EditError, match=message):
            copper_pours.add_copper_pours(document, **kwargs)


def test_copper_stitch_helpers_cover_empty_and_bounded_cases() -> None:
    assert copper_pours._axis_points(2, 1, 1) == []
    assert copper_pours._axis_points(0, 1.5, 1) == [0, 1, 1.5]
    with pytest.raises(EditError, match="Unique"):
        copper_pours._unique_named([], "Top", "layer")

    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(pcb.raw_bytes)
    outline = root.find("./Board/BoardOutline")
    assert outline is not None
    root.find("./Board").remove(outline)  # type: ignore[union-attr]
    no_outline = DipTraceDocument.from_bytes(
        pcb.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    assert copper_pours._stitch_points(no_outline, pitch=1, edge=1, clearance=0.2) == []
    with pytest.raises(EditError, match="exceeds 2048"):
        copper_pours._stitch_points(pcb, pitch=0.01, edge=0, clearance=0)

    result = copper_pours.add_copper_pours(
        pcb,
        net="VCC",
        layers=["Top", "Top"],
        extra_vias=[Point(5, 5), Point(5, 5)],
    )
    assert result.pour_count == 1
