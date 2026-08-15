from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document, build_schematic_document
from diptrace_mcp.synchronization import ComponentSyncMapping, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_sync_wraps_new_components_inside_board_outline() -> None:
    root = ET.fromstring(build_schematic_document())
    components = root.find("./Schematic/Components")
    assert components is not None
    mappings = []
    for index in range(4):
        refdes = f"J{index + 1}"
        part = ET.SubElement(
            components,
            "Part",
            {"Id": str(index), "PartNumber": "0", "Sheet": "0"},
        )
        ET.SubElement(part, "RefDes").text = refdes
        ET.SubElement(part, "Name").text = "HEADER"
        pins = ET.SubElement(part, "Pins")
        ET.SubElement(pins, "Pin", {"NetId": "-1", "NotConnected": "Y"})
        ET.SubElement(pins, "Pin", {"NetId": "-1", "NotConnected": "Y"})
        mappings.append(ComponentSyncMapping(refdes=refdes, pattern_style="PatType1"))

    schematic = DipTraceDocument.from_bytes(
        Path("schematic.dch"), ET.tostring(root, encoding="utf-8")
    )
    pcb = DipTraceDocument.from_bytes(
        Path("board.dip"), build_pcb_document(PcbScaffold(width_mm=20, height_mm=20))
    )
    patterns = DipTraceDocument.load(FIXTURES / "pattern_library.xml", 10_000_000)

    plan = build_sync_plan(
        schematic,
        pcb,
        mappings=mappings,
        pattern_documents=[patterns],
    )

    positions = [(item.x, item.y) for item in plan.operation.components]
    assert positions == [(5.0, 5.0), (15.0, 5.0), (5.0, 15.0), (15.0, 15.0)]
    assert all(2.5 <= x <= 17.5 and 1.0 <= y <= 19.0 for x, y in positions)
