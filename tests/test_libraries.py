from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.library_adapters import get_library_model, validate_library
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_pattern_library_model_normalizes_geometry_and_preserves_unknown_xml() -> None:
    document = _load("pattern_library.xml")
    model = get_library_model(document)

    assert model.source_type == "DipTrace-PatternLibrary"
    assert model.name == "Test Patterns"
    assert len(model.patterns) == 2
    assert len(model.pad_styles) == 2
    resistor = model.patterns[0]
    assert resistor.style == "PatType0"
    assert [pad.number for pad in resistor.pads] == ["1", "2"]
    assert resistor.pads[0].bbox == {
        "min_x": -1.25,
        "min_y": -0.475,
        "max_x": -0.35000000000000003,
        "max_y": 0.475,
    }
    assert resistor.pads[0].geometry is not None
    assert resistor.pads[0].geometry.kind == "rectangle"
    assert resistor.pads[0].geometry.center == {"x": -0.8, "y": 0.0}
    assert model.pad_styles[0].mask_paste == {
        "TopMask": "Common",
        "BotMask": "Common",
        "TopPaste": "Common",
        "BotPaste": "Common",
    }
    assert validate_library(model) == []
    assert document.serialize().find(b"FuturePatternData") >= 0


def test_component_library_model_and_pin_pad_mapping() -> None:
    model = get_library_model(_load("component_library.xml"))

    assert len(model.components) == 1
    assert len(model.patterns) == 1
    component = model.components[0]
    assert component.name == "RES_0603"
    assert component.refdes == "R"
    assert component.pattern_style == "PatType0"
    assert component.fields == {"MPN": "RC0603-GOLDEN"}
    assert [(pin.name, pin.number, pin.electrical_type) for pin in component.pins] == [
        ("A", "1", "Passive"),
        ("B", "2", "Passive"),
    ]
    assert validate_library(model) == []


def test_library_validation_reports_real_mapping_and_geometry_errors() -> None:
    component_document = _load("component_library.xml")
    component_root = ET.fromstring(component_document.raw_bytes)
    pin = component_root.find("./Components/Component/Part/Pins/Pin[@Id='1']/PadNumber")
    assert pin is not None
    pin.text = "99"
    bad_component = DipTraceDocument.from_bytes(
        component_document.path,
        ET.tostring(component_root, encoding="utf-8", xml_declaration=True),
    )
    component_codes = {
        finding.code for finding in validate_library(get_library_model(bad_component))
    }
    assert "pin_pad_mapping_missing" in component_codes

    pattern_document = _load("pattern_library.xml")
    pattern_root = ET.fromstring(pattern_document.raw_bytes)
    style = pattern_root.find("./PadStyles/PadStyle[@Name='THT_1MM']/MainStack")
    assert style is not None
    style.set("Width", "0.5")
    style.set("Height", "0.5")
    bad_pattern = DipTraceDocument.from_bytes(
        pattern_document.path,
        ET.tostring(pattern_root, encoding="utf-8", xml_declaration=True),
    )
    pattern_codes = {
        finding.code for finding in validate_library(get_library_model(bad_pattern))
    }
    assert "invalid_annular_ring" in pattern_codes


def test_documented_custom_mask_and_paste_geometry_is_normalized() -> None:
    document = _load("pattern_library.xml")
    root = ET.fromstring(document.raw_bytes)
    mask = root.find("./PadStyles/PadStyle[@Name='SMD_0603']/MaskPaste")
    assert mask is not None
    mask.set("TopMask", "Open")
    mask.set("TopPaste", "Solder")
    mask.set("CustomSwell", "0.05")
    mask.set("CustomShrink", "0.1")
    modified = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    model = get_library_model(modified)
    pad = model.patterns[0].pads[0]
    mask_shape = pad.mask_geometry["Top"][0]
    paste_shape = pad.paste_geometry["Top"][0]
    assert mask_shape.width == 1.0
    assert mask_shape.height == pytest.approx(1.05)
    assert paste_shape.width == pytest.approx(0.7)
    assert paste_shape.height == pytest.approx(0.75)


def test_documented_courtyard_line_geometry_is_normalized() -> None:
    document = _load("pattern_library.xml")
    root = ET.fromstring(document.raw_bytes)
    shape = root.find("./Patterns/Pattern/Shapes/Shape")
    assert shape is not None
    shape.set("Layer", "Top Courtyard")
    modified = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    courtyard = get_library_model(modified).patterns[0].courtyard_geometry
    assert list(courtyard) == ["Top"]
    assert courtyard["Top"][0].kind == "line"
    assert courtyard["Top"][0].line_width == pytest.approx(0.15)
    assert courtyard["Top"][0].points == [
        {"x": -1.5, "y": -0.8},
        {"x": -1.5, "y": 0.8},
    ]


def test_library_service_scan_query_get_and_validate(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    component_path = workspace / "components.xml"
    pattern_path = workspace / "patterns.xml"
    shutil.copyfile(FIXTURES / "component_library.xml", component_path)
    shutil.copyfile(FIXTURES / "pattern_library.xml", pattern_path)
    service = _service(workspace, tmp_path / "state")

    component_scan = service.scan_component_libraries()
    pattern_scan = service.scan_pattern_libraries()
    assert component_scan["result"]["matched_count"] == 1
    assert pattern_scan["result"]["matched_count"] == 1

    queried = service.query_library_items(str(component_path), "RES")
    assert queried["result"]["matched_count"] == 1
    component = service.get_library_component(str(component_path), name="RES_0603")
    assert component["result"]["pattern_style"] == "PatType0"
    mapping = service.validate_pin_pad_mapping(str(component_path), name="RES_0603")
    assert mapping["result"]["valid"] is True

    pattern = service.get_library_pattern(str(pattern_path), name="HDR_1X02")
    assert pattern["result"]["mounting"] == "Through"
    validation = service.validate_library_pattern(str(pattern_path), name="HDR_1X02")
    assert validation["result"]["valid"] is True
