from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_atomic_reroute import (
    plan_atomic_schematic_rotation_reroute,
)
from diptrace_mcp.schematic_pin_geometry import (
    resolve_document_schematic_pin_geometry,
)
from diptrace_mcp.schematic_rotation import generate_schematic_rotation_candidates
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _two_resistor_document() -> DipTraceDocument:
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)
    library = DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)
    root = ET.fromstring(schematic.raw_bytes)

    embedded = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert embedded is not None
    index = list(root).index(embedded)
    root.remove(embedded)
    root.insert(index, ET.fromstring(library.raw_bytes))

    components = root.find("./Schematic/Components")
    assert components is not None
    r1 = components.find("./Part[@Id='0']")
    assert r1 is not None
    r2 = copy.deepcopy(r1)
    r2.set("Id", "3")
    r2.set("UpdateId", "103")
    r2.set("X", "30")
    r2.set("Y", "30")
    refdes = r2.find("./RefDes")
    assert refdes is not None
    refdes.text = "R2"
    for child in list(components):
        components.remove(child)
    components.extend([r1, r2])

    nets = root.find("./Schematic/Nets")
    assert nets is not None
    for net, pin_index in zip(list(nets.findall("./Net")), [0, 1], strict=True):
        pins = net.find("./Pins")
        wires = net.find("./Wires")
        assert pins is not None and wires is not None
        pins.clear()
        ET.SubElement(pins, "Item", {"Part": "0", "Pin": str(pin_index)})
        ET.SubElement(pins, "Item", {"Part": "3", "Pin": str(pin_index)})
        wires.clear()

    document = DipTraceDocument.from_bytes(
        schematic.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    geometry = resolve_document_schematic_pin_geometry(document)
    by_key = {(item.refdes, item.pin_index): item for item in geometry.pins}

    operations = []
    for net_name, pin_index in (("VCC", 0), ("SIGNAL", 1)):
        start = by_key[("R1", pin_index)]
        end = by_key[("R2", pin_index)]
        assert start.absolute_position is not None
        assert end.absolute_position is not None
        sx = start.absolute_position["x"]
        sy = start.absolute_position["y"]
        ex = end.absolute_position["x"]
        ey = end.absolute_position["y"]
        operations.append(
            AddWireOperation(
                net=net_name,
                sheet=0,
                points=[
                    {"x": sx, "y": sy},
                    {"x": ex, "y": sy},
                    {"x": ex, "y": ey},
                ],
                start={"type": "Pin", "refdes": "R1", "pin": pin_index},
                end={"type": "Pin", "refdes": "R2", "pin": pin_index},
            )
        )
    return apply_semantic_operations(document, operations).document


def test_rotation_candidates_require_complete_high_confidence_pin_geometry() -> None:
    document = _two_resistor_document()

    result = generate_schematic_rotation_candidates(document)

    assert result.enabled_by_default is False
    assert result.required_manual_gate == "M2"
    assert result.candidates
    assert {item.refdes for item in result.candidates} == {"R1", "R2"}
    assert all(item.pin_geometry_confidence >= 0.9 for item in result.candidates)
    assert {item.target_angle_deg for item in result.candidates} == {0, 90, 180, 270}

    resolution = resolve_document_schematic_pin_geometry(document)
    truncated = resolution.model_copy(
        update={
            "pins": [
                item
                for item in resolution.pins
                if not (item.refdes == "R1" and item.pin_index == 1)
            ]
        }
    )
    incomplete = generate_schematic_rotation_candidates(
        document,
        pin_geometry=truncated,
    )
    assert all(item.refdes != "R1" for item in incomplete.candidates)
    assert any(
        item.get("reason") == "incomplete_pin_geometry"
        for item in incomplete.skipped
    )


def test_rotation_reroute_is_one_delete_rotate_rebuild_atomic_batch() -> None:
    document = _two_resistor_document()
    before = document.raw_bytes
    candidates = generate_schematic_rotation_candidates(document).candidates
    changed = next(
        item
        for item in candidates
        if item.refdes == "R1"
        and item.target_angle_deg != round(item.source_angle_deg) % 360
    )

    plan = plan_atomic_schematic_rotation_reroute(document, changed)

    kinds = [item.kind for item in plan.operations]
    assert kinds.count("delete_wire") == 2
    assert kinds.count("rotate_components") == 1
    assert kinds.count("add_wire") == 2
    rotate_index = kinds.index("rotate_components")
    assert all(kind == "delete_wire" for kind in kinds[:rotate_index])
    assert all(kind == "add_wire" for kind in kinds[rotate_index + 1 :])
    assert document.raw_bytes == before

    applied = apply_semantic_operations(document, plan.operations).document
    snapshot = build_snapshot(applied)
    assert snapshot.schematic is not None
    rotated = next(
        part for part in snapshot.schematic.parts if part.stable_id == changed.part_id
    )
    assert round(rotated.rotation_deg) % 360 == changed.target_angle_deg
    assert len(snapshot.schematic.wires) == 2
    assert {wire.net_name for wire in snapshot.schematic.wires} == {"VCC", "SIGNAL"}


def test_rotation_plan_rejects_stale_candidate_before_wire_deletion() -> None:
    document = _two_resistor_document()
    candidate = next(
        item
        for item in generate_schematic_rotation_candidates(document).candidates
        if item.refdes == "R1" and item.target_angle_deg == 90
    )
    stale = candidate.model_copy(update={"source_angle_deg": 180.0})

    with pytest.raises(CapabilityUnavailableError, match="stale"):
        plan_atomic_schematic_rotation_reroute(document, stale)
