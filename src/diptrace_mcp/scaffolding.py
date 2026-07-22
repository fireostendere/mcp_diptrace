"""Scaffolding: build synthetic DipTrace-shaped XML documents from scratch.

The generators produce XML that follows the official DipTrace XML structure
(Schematic and PCB Layout, 4.3-era format version) and is validated by parsing
back through :class:`~diptrace_mcp.xml_document.DipTraceDocument`.

**Important:** These are synthetic MCP-generated documents. They have the correct
XML shape and can be parsed by the MCP parser, but they have **not** been opened,
saved, or re-exported by DipTrace. They must not be treated as DipTrace-compatible
or production-ready without independent verification by a real DipTrace installation.

Use ``create_document_from_seed`` with a real DipTrace-exported XML seed when
DipTrace compatibility is required.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import Field, model_validator

from .domain import StrictModel
from .errors import EditError

DEFAULT_FORMAT_VERSION = "4.3.0.3"
MAX_SHEETS = 256
MAX_LAYERS = 32
MAX_DIMENSION_MM = 2_000.0

_DEFAULT_LAYER_NAMES = {
    1: ("Top",),
    2: ("Top", "Bottom"),
}


def _format(value: float) -> str:
    return f"{value:.9g}"


def _indent(element: ET.Element) -> None:
    ET.indent(element, space="  ")


def _serialize(root: ET.Element) -> bytes:
    _indent(root)
    body: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body + b"\n"


class LayerSpec(StrictModel):
    """Copper layer of a new PCB document."""

    name: str = Field(min_length=1, max_length=256)
    type: Literal["Signal", "Plane"] = "Signal"


class PcbScaffold(StrictModel):
    """Options for a new PCB document."""

    width_mm: float = Field(default=50.0, gt=0.1, le=MAX_DIMENSION_MM, allow_inf_nan=False)
    height_mm: float = Field(default=50.0, gt=0.1, le=MAX_DIMENSION_MM, allow_inf_nan=False)
    layers: list[LayerSpec] = Field(default_factory=list, max_length=MAX_LAYERS)
    trace_width_mm: float = Field(default=0.25, gt=0.01, le=10.0, allow_inf_nan=False)
    clearance_mm: float = Field(default=0.2, ge=0.0, le=10.0, allow_inf_nan=False)
    min_trace_mm: float = Field(default=0.15, gt=0.01, le=10.0, allow_inf_nan=False)
    min_drill_mm: float = Field(default=0.2, gt=0.05, le=10.0, allow_inf_nan=False)
    min_ring_mm: float = Field(default=0.1, ge=0.0, le=10.0, allow_inf_nan=False)
    via_diameter_mm: float = Field(default=0.6, gt=0.1, le=10.0, allow_inf_nan=False)
    via_hole_mm: float = Field(default=0.3, gt=0.05, le=10.0, allow_inf_nan=False)
    dielectric_thickness_mm: float = Field(
        default=1.6, gt=0.01, le=20.0, allow_inf_nan=False
    )
    dielectric_constant: float = Field(default=4.5, gt=1.0, le=100.0, allow_inf_nan=False)
    copper_thickness_mm: float = Field(default=0.035, gt=0.001, le=1.0, allow_inf_nan=False)
    stackup_name: str = Field(default="Custom", min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_geometry(self) -> PcbScaffold:
        if self.via_hole_mm >= self.via_diameter_mm:
            raise ValueError("via_hole_mm must be smaller than via_diameter_mm")
        return self


class SchematicScaffold(StrictModel):
    """Options for a new schematic document."""

    sheet_names: list[str] = Field(default_factory=lambda: ["Sheet 1"], max_length=MAX_SHEETS)

    @model_validator(mode="after")
    def validate_sheets(self) -> SchematicScaffold:
        if not self.sheet_names:
            raise ValueError("at least one sheet is required")
        names = [name.strip() for name in self.sheet_names]
        if any(not name for name in names):
            raise ValueError("sheet names cannot be empty")
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("sheet names must be unique")
        return self


def default_layers(count: int) -> list[LayerSpec]:
    """Default copper layer names for a stackup of ``count`` layers."""

    if count in _DEFAULT_LAYER_NAMES:
        return [LayerSpec(name=name) for name in _DEFAULT_LAYER_NAMES[count]]
    names = ["Top", *(f"L{index}" for index in range(2, count)), "Bottom"]
    return [LayerSpec(name=name) for name in names]


def build_schematic_document(
    options: SchematicScaffold | None = None,
    *,
    units: str = "mm",
    version: str = DEFAULT_FORMAT_VERSION,
) -> bytes:
    """Build a synthetic DipTrace Schematic XML document.

    The returned bytes are MCP-generated XML that follows the DipTrace 4.3-era
    structure. They are validated by parser re-read but have **not** been verified
    by DipTrace open/save. Treat as ``synthetic_parser_only`` provenance.
    """

    scaffold = options or SchematicScaffold()
    root = ET.Element(
        "Source", {"Type": "DipTrace-Schematic", "Version": version, "Units": units}
    )
    ET.SubElement(
        root,
        "Library",
        {"Type": "DipTrace-ComponentLibrary", "Version": version, "Units": units},
    )
    schematic = ET.SubElement(root, "Schematic")
    sheet_settings = ET.SubElement(schematic, "SheetSettings")
    ET.SubElement(sheet_settings, "ActiveSheet").text = "0"
    sheets = ET.SubElement(sheet_settings, "Sheets")
    for index, name in enumerate(scaffold.sheet_names):
        sheet = ET.SubElement(sheets, "Sheet")
        ET.SubElement(sheet, "Id").text = str(index)
        ET.SubElement(sheet, "Name").text = name
        ET.SubElement(sheet, "Type").text = "Normal"
    net_classes = ET.SubElement(schematic, "NetClasses")
    net_class = ET.SubElement(
        net_classes, "NetClass", {"Id": "0", "UpdateId": "0", "Type": "Normal"}
    )
    ET.SubElement(net_class, "Name").text = "Default"
    erc = ET.SubElement(
        schematic,
        "ERC",
        {
            "CheckPinType": "Y",
            "CheckNotConnected": "Y",
            "CheckSinglePin": "Y",
            "CheckShort": "Y",
            "CheckPinSuperimpose": "Y",
        },
    )
    ET.SubElement(erc, "VCCTemplate").text = "V*"
    ET.SubElement(erc, "GNDTemplate").text = "GND*"
    ET.SubElement(schematic, "Components")
    ET.SubElement(schematic, "Nets")
    ET.SubElement(schematic, "DifferentialPairs")
    ET.SubElement(schematic, "Buses")
    return _serialize(root)


def build_pcb_document(
    options: PcbScaffold | None = None,
    *,
    units: str = "mm",
    version: str = DEFAULT_FORMAT_VERSION,
) -> bytes:
    """Build a synthetic DipTrace PCB Layout XML document.

    The returned bytes are MCP-generated XML that follows the DipTrace 4.3-era
    structure. They are validated by parser re-read but have **not** been verified
    by DipTrace open/save. Treat as ``synthetic_parser_only`` provenance.
    """

    scaffold = options or PcbScaffold()
    layers = scaffold.layers or default_layers(2)
    if not layers:
        raise EditError("A PCB document requires at least one copper layer")
    if units != "mm":
        # Geometry options are accepted in millimetres only; convert into the
        # document units so the generated file stays consistent.
        from .geometry import from_mm

        factor = from_mm(1.0, units)
    else:
        factor = 1.0

    def dim(value_mm: float) -> str:
        return _format(value_mm * factor)

    root = ET.Element(
        "Source", {"Type": "DipTrace-PCB", "Version": version, "Units": units}
    )
    ET.SubElement(
        root,
        "Library",
        {"Type": "DipTrace-ComponentLibrary", "Version": version, "Units": units},
    )
    ET.SubElement(
        root,
        "Library",
        {"Type": "DipTrace-PatternLibrary", "Version": version, "Units": units},
    )
    board = ET.SubElement(root, "Board")
    outline = ET.SubElement(board, "BoardOutline", {"Locked": "N", "Selected": "N"})
    outline_points = ET.SubElement(outline, "Points")
    for x_mm, y_mm in (
        (0.0, 0.0),
        (scaffold.width_mm, 0.0),
        (scaffold.width_mm, scaffold.height_mm),
        (0.0, scaffold.height_mm),
    ):
        ET.SubElement(outline_points, "Point", {"X": dim(x_mm), "Y": dim(y_mm)})
    settings = ET.SubElement(board, "Settings")
    ET.SubElement(
        settings,
        "Routing",
        {
            "TraceWidth": dim(scaffold.trace_width_mm),
            "TraceClearance": dim(scaffold.clearance_mm),
            "ViaSize": dim(scaffold.via_diameter_mm),
            "ViaHole": dim(scaffold.via_hole_mm),
        },
    )
    copper_layers = ET.SubElement(board, "CopperLayers")
    for layer_id, layer in enumerate(layers):
        lay = ET.SubElement(copper_layers, "Lay", {"Id": str(layer_id), "Type": layer.type})
        ET.SubElement(lay, "Name").text = layer.name
    ET.SubElement(board, "LayerStackName").text = scaffold.stackup_name
    stack_items = ET.SubElement(board, "LayerStackItems")
    for layer_id, _layer in enumerate(layers):
        item = ET.SubElement(stack_items, "LayerStackItem", {"Lay": str(layer_id)})
        material = ET.SubElement(
            item,
            "Material",
            {
                "Type": "Conductor",
                "VariableThickness": "N",
                "Thickness": dim(scaffold.copper_thickness_mm),
                "Constant": "0",
                "TraceWidth": dim(scaffold.trace_width_mm),
            },
        )
        material.append(_named("Name", "Copper"))
        if layer_id < len(layers) - 1:
            dielectric = ET.SubElement(stack_items, "LayerStackItem", {"Lay": "-1"})
            material = ET.SubElement(
                dielectric,
                "Material",
                {
                    "Type": "Dielectric",
                    "VariableThickness": "N",
                    "Thickness": dim(scaffold.dielectric_thickness_mm),
                    "Constant": _format(scaffold.dielectric_constant),
                },
            )
            material.append(_named("Name", "Core"))
    via_styles = ET.SubElement(board, "ViaStyles")
    via_attributes = {
        "Id": "0",
        "Diameter": dim(scaffold.via_diameter_mm),
        "Hole": dim(scaffold.via_hole_mm),
    }
    if len(layers) > 2:
        via_attributes.update({"Lay1": "0", "Lay2": str(len(layers) - 1)})
    via_style = ET.SubElement(via_styles, "ViaStyle", via_attributes)
    ET.SubElement(via_style, "Name").text = "Default"
    net_classes = ET.SubElement(board, "NetClasses")
    net_class = ET.SubElement(
        net_classes,
        "NetClass",
        {
            "Id": "0",
            "UpdateId": "0",
            "Type": "Normal",
            "AllLayers": "Y",
            "CheckLength": "N",
            "AllVias": "Y",
            "PerformDRC": "Y",
            "LengthDelta": dim(2.54),
            "FixedLength": "0",
            "MaxUncoupledLength": dim(10.0),
            "Tolerance": dim(2.0),
        },
    )
    ET.SubElement(net_class, "Name").text = "Default"
    lay_properties = ET.SubElement(net_class, "LayProperties")
    for layer in layers:
        prop = ET.SubElement(
            lay_properties,
            "LayProperty",
            {
                "Width": dim(scaffold.trace_width_mm),
                "MinWidth": dim(scaffold.min_trace_mm),
                "MaxWidth": dim(2.0),
                "Clearance": dim(scaffold.clearance_mm),
                "Neck_Width": dim(scaffold.min_trace_mm),
                "Neck_DifClearance": dim(scaffold.clearance_mm),
                "Neck_MaxLength": dim(3.0),
                "DifClearance": dim(scaffold.clearance_mm),
            },
        )
        ET.SubElement(prop, "LayerName").text = layer.name
    drc = ET.SubElement(board, "DRC", {"CheckClearance": "Y", "CheckNetConnectivity": "Y"})
    clearances = ET.SubElement(drc, "LayClearances")
    sizes = ET.SubElement(drc, "LaySizes")
    for layer_id in range(len(layers)):
        ET.SubElement(
            clearances,
            "LayClearance",
            {
                "Lay": str(layer_id),
                "TraceToTrace": dim(scaffold.clearance_mm),
                "TraceToPad": dim(scaffold.clearance_mm),
            },
        )
        ET.SubElement(
            sizes,
            "LaySize",
            {
                "Lay": str(layer_id),
                "MinTrace": dim(scaffold.min_trace_mm),
                "MinDrill": dim(scaffold.min_drill_mm),
                "MinRing": dim(scaffold.min_ring_mm),
            },
        )
    ET.SubElement(
        board,
        "ConnectivityCheck",
        {"Traces": "Y", "Shapes": "Y", "CopperPours": "Y"},
    )
    ET.SubElement(board, "Components")
    ET.SubElement(board, "Ratlines")
    ET.SubElement(board, "Nets")
    ET.SubElement(board, "DifferentialPairs")
    ET.SubElement(board, "CopperPours")
    ET.SubElement(board, "Shapes")
    return _serialize(root)


def _named(tag: str, text: str) -> ET.Element:
    element = ET.Element(tag)
    element.text = text
    return element
