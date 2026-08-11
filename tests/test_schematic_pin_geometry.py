from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.library_adapters import get_library_model
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.schematic_pin_geometry import (
    SchematicPinGeometryConfig,
    get_embedded_schematic_component_library,
    resolve_document_schematic_pin_geometry,
    resolve_schematic_pin_geometry,
)
from diptrace_mcp.services.schematic_wire_quality import clean_schematic_wire_operation
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _schematic_document() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)


def _schematic_snapshot():
    return build_snapshot(_schematic_document())


def _library_document() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)


def _library_model():
    return get_library_model(_library_document())


def _schematic_document_with_embedded_library() -> DipTraceDocument:
    schematic = _schematic_document()
    library = _library_document()
    root = ET.fromstring(schematic.raw_bytes)
    existing = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert existing is not None
    index = list(root).index(existing)
    root.remove(existing)
    root.insert(index, ET.fromstring(library.raw_bytes))
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return DipTraceDocument.from_bytes(schematic.path, raw)


def test_comp_type_index_resolves_verified_resistor_pin_geometry() -> None:
    resolution = resolve_schematic_pin_geometry(_schematic_snapshot(), _library_model())

    r1_pins = sorted(
        (pin for pin in resolution.pins if pin.refdes == "R1"),
        key=lambda pin: pin.pin_index,
    )
    assert len(r1_pins) == 2
    assert [pin.match_basis for pin in r1_pins] == [
        "component_style_index",
        "component_style_index",
    ]
    assert r1_pins[0].local_position == {"x": -1.0, "y": 0.0}
    assert r1_pins[1].local_position == {"x": 1.0, "y": 0.0}
    assert r1_pins[0].absolute_position == pytest.approx({"x": 8.5, "y": 20.0})
    assert r1_pins[1].absolute_position == pytest.approx({"x": 11.5, "y": 20.0})
    assert [pin.local_orientation_deg for pin in r1_pins] == [0.0, 180.0]
    assert [pin.electrical_type for pin in r1_pins] == ["Passive", "Passive"]
    assert "_length_mm" not in _library_model().components[0].pins[0].model_dump()


def test_unavailable_library_component_fails_closed_for_mcu_parts() -> None:
    resolution = resolve_schematic_pin_geometry(_schematic_snapshot(), _library_model())

    unresolved_u1 = [item for item in resolution.unresolved if item.get("refdes") == "U1"]
    assert len(unresolved_u1) == 2
    assert all(
        "no unique structurally compatible library component" in " ".join(item["reasons"])
        for item in unresolved_u1
    )
    assert all(pin.refdes != "U1" for pin in resolution.pins)


def test_component_style_index_is_only_a_hint_when_name_does_not_match() -> None:
    snapshot = _schematic_snapshot()
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    r1.name = "WRONG_COMPONENT"

    resolution = resolve_schematic_pin_geometry(snapshot, _library_model())

    assert all(pin.refdes != "R1" for pin in resolution.pins)
    unresolved = next(item for item in resolution.unresolved if item.get("refdes") == "R1")
    assert "no unique structurally compatible library component" in " ".join(
        unresolved["reasons"]
    )


def test_explicit_binding_can_override_name_but_not_structural_mismatch() -> None:
    snapshot = _schematic_snapshot()
    library = _library_model()
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    r1.name = "PROJECT_ALIAS"
    component = library.components[0]

    resolution = resolve_schematic_pin_geometry(
        snapshot,
        library,
        bindings={"CompType0": component.stable_id},
    )

    r1_pins = [pin for pin in resolution.pins if pin.refdes == "R1"]
    assert len(r1_pins) == 2
    assert {pin.match_basis for pin in r1_pins} == {"explicit_binding"}

    snapshot.schematic.pins = [
        pin
        for pin in snapshot.schematic.pins
        if not (pin.parent_id == r1.stable_id and pin.label == "pin-1")
    ]
    mismatched = resolve_schematic_pin_geometry(
        snapshot,
        library,
        bindings={"CompType0": component.stable_id},
    )
    assert all(pin.refdes != "R1" for pin in mismatched.pins)
    unresolved = next(item for item in mismatched.unresolved if item.get("refdes") == "R1")
    assert "pin count" in " ".join(unresolved["reasons"])


def test_nonzero_part_rotation_can_still_be_failed_closed_explicitly() -> None:
    snapshot = _schematic_snapshot()
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    r1.rotation_deg = 90.0

    resolution = resolve_schematic_pin_geometry(
        snapshot,
        _library_model(),
        config=SchematicPinGeometryConfig(allow_unverified_part_rotation=False),
    )

    r1_pins = [pin for pin in resolution.pins if pin.refdes == "R1"]
    assert len(r1_pins) == 2
    assert all(pin.absolute_position is None for pin in r1_pins)
    assert all(pin.absolute_orientation_deg is None for pin in r1_pins)
    assert all(pin.confidence <= 0.7 for pin in r1_pins)
    assert any("angle convention" in warning for warning in resolution.warnings)


def test_rotation_transform_uses_native_verified_pin_tip_by_default() -> None:
    snapshot = _schematic_snapshot()
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    r1.rotation_deg = 90.0

    resolution = resolve_schematic_pin_geometry(snapshot, _library_model())

    r1_pins = sorted(
        (pin for pin in resolution.pins if pin.refdes == "R1"),
        key=lambda pin: pin.pin_index,
    )
    assert r1_pins[0].absolute_position == pytest.approx({"x": 10.0, "y": 18.5})
    assert r1_pins[1].absolute_position == pytest.approx({"x": 10.0, "y": 21.5})
    assert r1_pins[0].absolute_orientation_deg == pytest.approx(90.0)
    assert r1_pins[1].absolute_orientation_deg == pytest.approx(270.0)
    assert any("verified DipTrace" in warning for warning in resolution.warnings)


def test_embedded_design_cache_is_primary_document_geometry_source() -> None:
    document = _schematic_document_with_embedded_library()

    embedded = get_embedded_schematic_component_library(document)
    assert embedded is not None
    assert [component.name for component in embedded.components] == ["RES_0603"]

    resolution = resolve_document_schematic_pin_geometry(document)

    assert resolution.library_source == "embedded_design_cache"
    r1_pins = sorted(
        (pin for pin in resolution.pins if pin.refdes == "R1"),
        key=lambda pin: pin.pin_index,
    )
    assert [pin.absolute_position for pin in r1_pins] == pytest.approx(
        [{"x": 8.5, "y": 20.0}, {"x": 11.5, "y": 20.0}]
    )
    assert any("embedded design cache" in item for item in resolution.assumptions)


def test_wire_cleaner_snaps_declared_pin_endpoint_to_native_pin_tip() -> None:
    document = _schematic_document_with_embedded_library()
    operation = AddWireOperation(
        net="VCC",
        points=[{"x": 9.0, "y": 20.0}, {"x": 8.5, "y": 5.0}],
        start={"type": "Pin", "refdes": "R1", "pin": 0},
        end={"type": "Free"},
    )

    cleaned = clean_schematic_wire_operation(document, build_snapshot(document), operation)

    assert cleaned.points[0].model_dump() == pytest.approx({"x": 8.5, "y": 20.0})


def test_wire_cleaner_keeps_native_submicron_axis_noise_orthogonal() -> None:
    document = _schematic_document_with_embedded_library()
    operation = AddWireOperation(
        net="VCC",
        points=[
            {"x": 8.5000002, "y": 20.0},
            {"x": 8.5000002, "y": 5.0},
            {"x": 20.0, "y": 5.0},
        ],
        start={"type": "Pin", "refdes": "R1", "pin": 0},
        end={"type": "Free"},
    )

    cleaned = clean_schematic_wire_operation(document, build_snapshot(document), operation)

    assert cleaned.points[1].x == pytest.approx(8.5000002)


def test_external_library_fallback_is_disabled_by_default() -> None:
    document = _schematic_document()

    resolution = resolve_document_schematic_pin_geometry(
        document,
        fallback_library=_library_model(),
    )

    assert not resolution.pins
    assert resolution.library_source == "embedded_design_cache"
    assert any("fallback is disabled" in item for item in resolution.limitations)


def test_external_library_fallback_requires_explicit_opt_in() -> None:
    document = _schematic_document()

    resolution = resolve_document_schematic_pin_geometry(
        document,
        fallback_library=_library_model(),
        config=SchematicPinGeometryConfig(allow_external_library_fallback=True),
    )

    assert resolution.library_source == "external_fallback"
    assert len([pin for pin in resolution.pins if pin.refdes == "R1"]) == 2
    assert any("external Component Library fallback" in item for item in resolution.warnings)
