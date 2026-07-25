#!/usr/bin/env python3
"""Extract a machine-readable inventory from the official DipTrace XML specification PDFs.

Usage:
    python scripts/extract_spec_inventory.py \
        --sources reference/diptrace-xml/sources \
        --out reference/diptrace-xml/spec_inventory.json

With --check, regenerates in memory and exits non-zero if the committed file differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _extract_pages(pdf_path: Path) -> list[str]:
    """Return per-page text for a PDF."""
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Matches an XML example line like:  <Source Type="DipTrace-PCB" ...>
_XML_EXAMPLE_RE = re.compile(r"<(\w+)(?:\s[^>]*)?\s*/?>")

# Matches an attribute definition line like:    Type Text "DipTrace-PCB" – file created in ...
# or:                                Id Int Component identifier (Id).
_ATTR_LINE_RE = re.compile(
    r"^(\w+)\s+(Int|Real|Text|Bool)\s+(.+)$"
)

# Matches an enum value line like:   "Y" – enabled;
# or:                                "N" – disabled.
_ENUM_VALUE_RE = re.compile(r'"([^"]+)"\s*[–—-]\s*(.+?)(?:;|\s*$)')

# Known element names that appear as children in the spec
_KNOWN_ELEMENTS = frozenset([
    "Item", "Point", "Field", "Cell", "Lay", "Rule",
    "Net", "Pad", "Wire", "Shape", "Table", "Column",
    "Group", "Trace", "ViaStyle", "NetClass",
    "Component", "CopperPour", "DifferentialPair",
    "Segment", "CenterPoint", "PadPoint",
    "Teardrop", "DesignError", "Dimension",
    "Part", "Signal", "BusConnector", "Bus",
    "Material", "LayProperty", "LayClearance",
    "LaySize", "NonSignal", "LayerStackItem",
    "HSheet", "UId", "Folder", "Lib",
    "CustomSpoke", "IntCon", "CategoryType",
    "RemovedDifferentialPair", "TeardropParams",
    "ClearanceDetails", "AutoUpdate", "ColumnWidths",
    "RowHeights", "TextLines", "TextLine", "FontName",
    "Path", "Var", "Name", "Value", "RefDes", "PartRefDes",
    "PartName", "BlockId", "LibPath", "HierarchyPath",
    "AssemblyExclude", "AddFields", "AddField",
    "Pins", "Pin", "HideRingLay", "BlindLay",
    "InternalConnections", "Category", "CategoryTypes",
    "Ratlines", "Traces", "DifferentialPairs",
    "CopperPours", "Shapes", "DesignErrors", "Tables",
    "Dimensions", "Groups", "StackupItems",
    "CopperLayers", "NonSignals", "HierarchySheets",
    "ViaStyles", "NetClasses", "LengthRules",
    "CTC_Cells", "LayClearances", "LaySizes",
    "ConnectivityCheck", "MainLengthRule",
    "ProjectLibs", "Folders", "Libs",
    "BoardOutline", "Points", "HorzTabsX", "VertTabsY",
    "SheetSettings", "Sheets", "Sheet",
    "BottomRightBlock", "BottomLeftBlock",
    "TopRightBlock", "TopLeftBlock",
    "ExtTopLeftBlock", "ExtBottomLeftBlock",
    "Settings", "Markings",
    "DisplayTitles", "DisplaySheet",
    "XPos", "YPos", "Scale", "SheetWidth", "SheetHeight",
    "LeftMargin", "TopMargin", "RightMargin", "BottomMargin",
    "BorderZones", "Visible", "HorzZones", "VertZones",
    "Standard", "Border", "HorzBorderSize", "VertBorderSize",
    "Cells", "Fields", "ColumnWidths", "RowHeights",
    "RefDesGlobal", "SilkShow", "SilkAlign", "AssyShow", "AssyAlign",
    "CompRotate", "FontVector", "FontSize", "FontWidth", "FontScale",
    "UsePartFontColor", "FontColor",
    "RefDesMarking", "NameMarking", "ValueMarking",
    "PatternMarking", "ManufacturerMarking", "DatasheetMarking",
    "Silk", "Assy", "Horz", "Vert",
    "ShowFiducials", "GridAlign", "PanelExclude",
    "ProjectDir", "JumperLayer",
    "StackupItems", "LayerStackName",
    "StackupItem", "Thickness", "Constant", "TraceWidth",
    "CheckClearance", "CheckSize", "CheckJumpers",
    "CheckCopperPours", "CheckClassToClass", "CheckSilk",
    "CheckLength", "CheckKeepouts", "CheckSameNet",
    "CheckSameComponentPads", "CheckCourtyard",
    "SilkClearance", "ShowList", "RealTimeMode", "DRCDone",
    "Autorouting", "RoutePriority", "PriorityValue",
    "RouteMaxVias", "MaxViasValue",
    "RouteMaxIncorrectWay", "MaxIncorrectWayValue",
    "RouteAllLayers", "RouteLayers",
    "AllowedVias",
    "ClassToClass", "Enabled",
    "LayClearances",
    "TeardropParams",
    "PadVia", "Smd", "Trace", "TJunc",
    "PadViaWidth", "PadViaLength",
    "SmdWidth", "SmdLength",
    "TraceLength", "TJuncLength",
    "MaskPaste",
    "TopMask", "BotMask", "TopPaste", "BotPaste",
    "Segment_Percent", "Segment_EdgeGap", "Segment_Gap", "Segment_Side",
    "CustomSwell", "CustomShrink",
    "TopSegments", "BotSegments",
    "CustomSpoke",
    "Width", "MinWidth", "MaxWidth",
    "Clearance", "Neck_Width", "Neck_DifClearance", "Neck_MaxLength",
    "DifClearance",
    "LayerName",
    "Connected1", "Connected2", "Object1", "Object2",
    "SubObject1", "SubObject2", "Point1", "Point2",
    "PairSeparateTrace",
    "PosTrace", "NegTrace", "StartPoint", "EndPoint",
    "StartSegment", "EndSegment",
    "PosPoints", "NegPoints",
    "PosPoint", "NegPoint",
    "PosSeparateTraces", "NegSeparateTraces",
    "RemovedDifferentialPairs",
    "AutoPadPoints", "TraceColor",
    "PosNet", "NegNet",
    "PadPoints",
    "Type",
    "PlanePad", "NetId", "PlaneRing", "Color",
    "Locked", "Selected",
    "PlanePad",
    "Panel", "Type", "Columns", "Rows",
    "ColumnSpacing", "RowSpacing",
    "PanelizeSingle", "RailShow",
    "RailLeft", "RailRight", "RailTop", "RailBottom",
    "TabWidth", "TabRadius", "TabStep",
    "HoleDiam", "HoleStep", "HoleInset", "HoleKeepout",
    "TabsDone", "CombinedRadius",
    "KeepMaterial", "BorderTabs",
    "Orientation",
    "CellWidth", "CellHeight", "HideBorder",
    "AutoUpdate", "RowType", "Header",
    "AssemblyVariant", "BomRowNumber", "BomTotal",
    "PickOffX", "PickOffY", "PickMirror", "PickOrigin",
    "AssemblyName", "Separator",
    "Columns", "Column",
    "Title", "Width",
    "ColWidths",
    "PictureWidth", "PictureHeight", "PictureProportions",
    "PictureRaster", "PictureTransparent",
    "PictureVector", "Polygons", "Polygon",
    "PointerMode",
    "XD", "YD",
    "ArrowSize", "ExternalRadius",
    "Units", "ShowUnits",
    "Connected1", "Connected2",
    "PointerText",
    "PictureFile",
    "BusConnections",
    "Show", "Position",
    "PinNumbers", "Font",
    "HidePower",
    "DesignCache", "Count",
    "ERC",
    "CheckPinType", "CheckNotConnected",
    "CheckSinglePin", "CheckShort",
    "CheckPinSuperimpose",
    "VCCTemplate", "GNDTemplate",
    "AllowParts", "PartNumber",
    "ShowNumbers", "ShowOrigin",
    "NotConnected",
    "Enabled", "NetId", "UniteByName", "ConnectPinByName", "Global",
    "WireColor",
    "Direction", "Arrows", "CanUnhide", "HiddenPower",
    "DifferentialPairs",
    "BusConnectors",
    "Simulator",
    "GndNetId",
    "Signals",
    "DisplayName",
    "SmallSignalAC", "Variation", "NumberOfPoints",
    "StartFrequency", "StopFrequency",
    "DCTransferFunc", "SourceType", "SourceRefDes",
    "StartValue", "Step", "StopValue",
    "SecondSource", "SecondSourceType", "SecondSourceRefDes",
    "SecondStartValue", "SecondStep", "SecondStopValue",
    "Transient", "StartTime", "StopTime",
    "Noise", "OutputNet", "ReferenceNet", "Source",
    "PointsPerSummary",
    "GndNetName",
    "NonSignal",
])


def _parse_xml_example_attrs(xml_line: str) -> dict[str, str]:
    """Parse attributes from an XML example line like <Source Type="..." Version="...">."""
    attrs: dict[str, str] = {}
    # Find all Name="Value" pairs
    for m in re.finditer(r'(\w+)="([^"]*)"', xml_line):
        attrs[m.group(1)] = m.group(2)
    return attrs


def _parse_attribute_line(line: str) -> tuple[str, str, str] | None:
    """Parse ``AttrName Type Description`` and return (name, type, description)."""
    m = _ATTR_LINE_RE.match(line.strip())
    if m:
        return m.group(1), m.group(2), m.group(3).strip()
    return None


def _extract_enum_values_from_block(text_block: str) -> list[str]:
    """Extract enumerated values from a text block following an attribute definition."""
    values: list[str] = []
    for m in _ENUM_VALUE_RE.finditer(text_block):
        values.append(m.group(1))
    return values


def _detect_element_name_from_example(line: str) -> str | None:
    """Extract the element name from an XML example line."""
    m = _XML_EXAMPLE_RE.search(line)
    if m:
        return m.group(1)
    return None


def _is_toc_line(line: str) -> bool:
    """Check if a line is from the table of contents."""
    return "..." in line and line.count(".") > 3


# ---------------------------------------------------------------------------
# Main extraction logic
# ---------------------------------------------------------------------------

def _parse_spec_pages(
    pages: list[str],
    document_type: str,  # "pcb" or "schematic"
    page_offset: int,    # 1-based page number offset for this PDF
) -> dict[str, dict[str, Any]]:
    """Parse a specification's pages and return element inventory.

    Returns dict keyed by element name, each value containing documents, pages,
    attributes, and children.
    """
    elements: dict[str, dict[str, Any]] = {}

    current_element: str | None = None
    current_attr_name: str | None = None
    attr_enum_buffer: list[str] = []

    for page_idx, page_text in enumerate(pages):
        page_num = page_idx + page_offset
        lines = page_text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Skip TOC lines
            if _is_toc_line(stripped):
                continue

            # --- Try to detect an XML example line introducing an element ---
            elem_name = _detect_element_name_from_example(stripped)
            if elem_name and not stripped.startswith("<!"):
                if elem_name in ("?xml",):
                    continue

                # Register the element
                if elem_name not in elements:
                    elements[elem_name] = {
                        "documents": [],
                        "pages": [],
                        "attributes": {},
                        "children": [],
                    }
                if document_type not in elements[elem_name]["documents"]:
                    elements[elem_name]["documents"].append(document_type)
                if page_num not in elements[elem_name]["pages"]:
                    elements[elem_name]["pages"].append(page_num)

                # Parse inline attributes from the XML example
                inline_attrs = _parse_xml_example_attrs(stripped)
                for attr_name, attr_value in inline_attrs.items():
                    if attr_name not in elements[elem_name]["attributes"]:
                        # Try to infer type from value
                        attr_type = _infer_type(attr_value)
                        units = _infer_units(attr_name, "", elem_name)
                        elements[elem_name]["attributes"][attr_name] = {
                            "type": attr_type,
                            "description": f'Attribute of <{elem_name}> (from XML example)',
                            "enum": None,
                            "units": units,
                            "omitted_when": None,
                        }

                current_element = elem_name
                current_attr_name = None
                attr_enum_buffer = []
                continue

            # --- Try to parse an attribute definition line ---
            if current_element and current_element in elements:
                attr = _parse_attribute_line(stripped)
                if attr:
                    # Flush any pending enum values
                    if current_attr_name and attr_enum_buffer:
                        attrs = elements[current_element]["attributes"]
                        attrs[current_attr_name]["enum"] = attr_enum_buffer
                    attr_enum_buffer = []

                    attr_name, attr_type, attr_desc = attr
                    units = _infer_units(attr_name, attr_desc, current_element)
                    omitted = _detect_omitted_when(attr_desc)

                    current_attr_name = attr_name
                    elements[current_element]["attributes"][attr_name] = {
                        "type": attr_type,
                        "description": attr_desc,
                        "enum": None,
                        "units": units,
                        "omitted_when": omitted,
                    }
                    continue

                # --- Try to parse enum values immediately following an attribute ---
                if current_attr_name and current_element in elements:
                    enum_m = _ENUM_VALUE_RE.match(stripped)
                    if enum_m:
                        attr_enum_buffer.append(enum_m.group(1))
                        continue

                # --- Detect child elements listed in prose ---
                if (current_element in elements
                        and ("list of" in stripped.lower()
                             or "start of" in stripped.lower())):
                    for child_m in re.finditer(r"\((\w+)\)", stripped):
                        child_name = child_m.group(1)
                        if (child_name in _KNOWN_ELEMENTS
                                and child_name not in elements[current_element]["children"]):
                            elements[current_element]["children"].append(child_name)

    # Flush any pending enum from the last attribute
    if current_attr_name and attr_enum_buffer:
        attrs = elements.get(current_element, {}).get("attributes", {})
        if current_attr_name in attrs:
            attrs[current_attr_name]["enum"] = attr_enum_buffer

    return elements


def _infer_type(value: str) -> str:
    """Infer the type of an attribute from its example value."""
    if value in ("Y", "N"):
        return "Bool"
    try:
        int(value)
        return "Int"
    except ValueError:
        pass
    try:
        float(value)
        return "Real"
    except ValueError:
        pass
    return "Text"


def _infer_units(attr_name: str, attr_desc: str, element_name: str) -> str:
    """Infer the unit of an attribute from its name, description, and context."""
    name_lower = attr_name.lower()
    desc_lower = attr_desc.lower() if attr_desc else ""

    # Text/picture Angle is explicitly radians
    if name_lower == "angle":
        if element_name in ("Shape", "Dimension") and "angle of the text" in desc_lower:
            return "radians"
        # Component Angle unit is not specified in the spec
        return "unknown"

    if name_lower == "orientation" and "digrees" in desc_lower:
        return "degrees"

    # X, Y coordinates and sizes are in document units (root Source/@Units)
    if name_lower in ("x", "y", "x1", "y1", "x2", "y2", "xd", "yd"):
        return "document_units"
    if name_lower in ("width", "height") and element_name in (
        "Shape", "Dimension", "Table", "Material"
    ):
        return "document_units"
    if "spacing" in name_lower or "clearance" in name_lower:
        return "document_units"
    if "margin" in name_lower or "offset" in name_lower:
        return "document_units"
    if "linewidth" in name_lower or "line_width" in name_lower:
        return "document_units"

    return "unknown"


def _detect_omitted_when(desc: str) -> str | None:
    """Detect if the spec says the attribute is omitted under some condition."""
    desc_lower = desc.lower() if desc else ""
    if "absent" in desc_lower or "omitted" in desc_lower:
        m = re.search(r"(?:absent|omitted)\s+(?:when|if)\s+(.+?)(?:\.|$)", desc_lower)
        if m:
            return m.group(1).strip()
        if "absent" in desc_lower:
            return "absent when not set"
    if "not used" in desc_lower:
        return "not used"
    if "only if" in desc_lower or "only when" in desc_lower:
        m = re.search(r"(only (?:if|when)\s+.+?)(?:\.|$)", desc_lower)
        if m:
            return m.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Spec inventory assembly
# ---------------------------------------------------------------------------

def _source_url(filename: str) -> str:
    """Map a local filename to the download URL."""
    url_map = {
        "DipTrace_Plugins.pdf": "https://diptrace.com/books/DipTrace_Plugins.pdf",
        "DipTraceXML_Pcb_En.pdf": "https://diptrace.com/books/DipTraceXML_Pcb_En.pdf",
        "DipTraceXML_Schematic_En.pdf": "https://diptrace.com/books/DipTraceXML_Schematic_En.pdf",
    }
    return url_map.get(filename, f"https://diptrace.com/books/{filename}")


def build_inventory(sources_dir: Path) -> dict[str, Any]:
    """Build the complete spec inventory from the PDFs in sources_dir."""
    sources_info: list[dict[str, Any]] = []
    all_elements: dict[str, dict[str, Any]] = {}

    pdf_files = sorted(sources_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {sources_dir}")

    for pdf_path in pdf_files:
        sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        size_bytes = pdf_path.stat().st_size

        # Determine document type from filename
        name_lower = pdf_path.name.lower()
        if "pcb" in name_lower:
            doc_type = "pcb"
        elif "schematic" in name_lower:
            doc_type = "schematic"
        elif "plugin" in name_lower:
            # Plugins spec describes settings.xml, not the XML format elements
            sources_info.append({
                "file": pdf_path.name,
                "url": _source_url(pdf_path.name),
                "sha256": sha256,
                "pages": len(_extract_pages(pdf_path)),
                "document_format_version": "4.3.0.3",
                "published": "2023",
                "size_bytes": size_bytes,
                "note": (
                    "Plug-in specification; describes settings.xml, "
                    "not the XML format elements"
                ),
            })
            continue
        else:
            doc_type = "unknown"

        pages = _extract_pages(pdf_path)
        elements = _parse_spec_pages(pages, doc_type, 1)

        sources_info.append({
            "file": pdf_path.name,
            "url": _source_url(pdf_path.name),
            "sha256": sha256,
            "pages": len(pages),
            "document_format_version": "4.3.0.3",
            "published": "2023",
            "size_bytes": size_bytes,
        })

        # Merge elements
        for elem_name, elem_data in elements.items():
            if elem_name not in all_elements:
                all_elements[elem_name] = elem_data
            else:
                # Merge documents and pages
                for doc in elem_data["documents"]:
                    if doc not in all_elements[elem_name]["documents"]:
                        all_elements[elem_name]["documents"].append(doc)
                for pg in elem_data["pages"]:
                    if pg not in all_elements[elem_name]["pages"]:
                        all_elements[elem_name]["pages"].append(pg)
                # Merge attributes
                for attr_name, attr_data in elem_data["attributes"].items():
                    if attr_name not in all_elements[elem_name]["attributes"]:
                        all_elements[elem_name]["attributes"][attr_name] = attr_data
                # Merge children
                for child in elem_data["children"]:
                    if child not in all_elements[elem_name]["children"]:
                        all_elements[elem_name]["children"].append(child)

    # Sort pages within each element
    for elem_data in all_elements.values():
        elem_data["pages"].sort()

    inventory = {
        "schema_version": "diptrace-spec-inventory-v1",
        "sources": sources_info,
        "elements": all_elements,
    }
    return inventory


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DipTrace XML spec inventory")
    parser.add_argument("--sources", required=True, help="Directory containing spec PDFs")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--check", action="store_true", help="Verify committed file matches")
    args = parser.parse_args()

    sources_dir = Path(args.sources)
    out_path = Path(args.out)

    inventory = build_inventory(sources_dir)

    # Deterministic JSON output
    output_json = json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

    if args.check:
        if not out_path.exists():
            print(f"FAIL: {out_path} does not exist", file=sys.stderr)
            return 1
        existing = out_path.read_text(encoding="utf-8")
        if existing != output_json:
            print(f"FAIL: {out_path} differs from generated inventory", file=sys.stderr)
            existing_data = json.loads(existing)
            new_data = json.loads(output_json)
            existing_elems = set(existing_data.get("elements", {}).keys())
            new_elems = set(new_data.get("elements", {}).keys())
            added = new_elems - existing_elems
            removed = existing_elems - new_elems
            if added:
                print(f"  Added elements: {sorted(added)}", file=sys.stderr)
            if removed:
                print(f"  Removed elements: {sorted(removed)}", file=sys.stderr)
            return 1
        print(f"OK: {out_path} matches generated inventory")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_json, encoding="utf-8")

    # Summary
    num_elements = len(inventory["elements"])
    num_attrs = sum(len(e["attributes"]) for e in inventory["elements"].values())
    num_sources = len(inventory["sources"])
    print(f"Extracted {num_elements} elements, {num_attrs} attributes from {num_sources} sources")
    print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
