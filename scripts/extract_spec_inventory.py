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
import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__:
    from .spec_inventory_integrity import validate_inventory
else:
    from spec_inventory_integrity import validate_inventory

_EXTRACTED_TEXT_SCHEMA = "diptrace-extracted-text-v1"
_EXTRACTION_ENGINE = "pypdf"
_EXTRACTION_ENGINE_VERSION = "6.14.2"
_EXTRACTED_TEXT_REPOSITORY_DIR = Path("reference/diptrace-xml/extracted_text")


@dataclass(frozen=True)
class ExtractedSource:
    file: str
    url: str
    sha256: str
    size_bytes: int
    pages: tuple[str, ...]
    extracted_text_file: str
    extracted_text_sha256: str

# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def _extract_pages(pdf_path: Path) -> list[str]:
    """Return per-page text using the pinned extraction engine."""
    import pypdf
    from pypdf import PdfReader

    if pypdf.__version__ != _EXTRACTION_ENGINE_VERSION:
        raise RuntimeError(
            "PDF extraction requires "
            f"{_EXTRACTION_ENGINE}=={_EXTRACTION_ENGINE_VERSION}; "
            f"found {pypdf.__version__}"
        )
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _bundle_filename(pdf_name: str) -> str:
    return f"{Path(pdf_name).stem}.pages.json"


def _bundle_repository_path(pdf_name: str) -> str:
    return str(_EXTRACTED_TEXT_REPOSITORY_DIR / _bundle_filename(pdf_name))


def _extracted_text_bundle(pdf_path: Path, pages: list[str]) -> dict[str, Any]:
    raw = pdf_path.read_bytes()
    return {
        "schema_version": _EXTRACTED_TEXT_SCHEMA,
        "source": {
            "file": pdf_path.name,
            "url": _source_url(pdf_path.name),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "page_count": len(pages),
        },
        "extraction": {
            "engine": _EXTRACTION_ENGINE,
            "version": _EXTRACTION_ENGINE_VERSION,
        },
        "pages": [
            {
                "page": index,
                "text": text,
            }
            for index, text in enumerate(pages, start=1)
        ],
    }


def _source_from_pdf(
    pdf_path: Path,
    *,
    write_extracted_text_dir: Path | None,
) -> ExtractedSource:
    pages = _extract_pages(pdf_path)
    bundle = _extracted_text_bundle(pdf_path, pages)
    bundle_bytes = _canonical_json(bundle).encode("utf-8")
    if write_extracted_text_dir is not None:
        write_extracted_text_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = write_extracted_text_dir / _bundle_filename(pdf_path.name)
        bundle_path.write_bytes(bundle_bytes)
    source = bundle["source"]
    return ExtractedSource(
        file=str(source["file"]),
        url=str(source["url"]),
        sha256=str(source["sha256"]),
        size_bytes=int(source["size_bytes"]),
        pages=tuple(pages),
        extracted_text_file=_bundle_repository_path(pdf_path.name),
        extracted_text_sha256=hashlib.sha256(bundle_bytes).hexdigest(),
    )


def _source_from_bundle(bundle_path: Path) -> ExtractedSource:
    raw = bundle_path.read_bytes()
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid extracted-text JSON: {bundle_path}: {exc}") from exc
    if bundle.get("schema_version") != _EXTRACTED_TEXT_SCHEMA:
        raise ValueError(f"Unsupported extracted-text schema: {bundle_path}")
    extraction = bundle.get("extraction")
    if extraction != {
        "engine": _EXTRACTION_ENGINE,
        "version": _EXTRACTION_ENGINE_VERSION,
    }:
        raise ValueError(f"Unexpected extraction engine metadata: {bundle_path}")
    source = bundle.get("source")
    page_entries = bundle.get("pages")
    if not isinstance(source, dict) or not isinstance(page_entries, list):
        raise ValueError(f"Malformed extracted-text bundle: {bundle_path}")
    expected_pages = list(range(1, len(page_entries) + 1))
    actual_pages = [
        item.get("page") if isinstance(item, dict) else None for item in page_entries
    ]
    if actual_pages != expected_pages:
        raise ValueError(f"Extracted-text pages are not contiguous: {bundle_path}")
    pages = tuple(
        str(item.get("text", ""))
        for item in page_entries
        if isinstance(item, dict)
    )
    if int(source.get("page_count", -1)) != len(pages):
        raise ValueError(f"Extracted-text page count mismatch: {bundle_path}")
    canonical = _canonical_json(bundle).encode("utf-8")
    if raw != canonical:
        raise ValueError(f"Extracted-text bundle is not canonical JSON: {bundle_path}")
    file_name = str(source.get("file", ""))
    return ExtractedSource(
        file=file_name,
        url=str(source.get("url", "")),
        sha256=str(source.get("sha256", "")),
        size_bytes=int(source.get("size_bytes", 0)),
        pages=pages,
        extracted_text_file=_bundle_repository_path(file_name),
        extracted_text_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _load_extracted_sources(
    sources_dir: Path,
    *,
    write_extracted_text_dir: Path | None = None,
) -> list[ExtractedSource]:
    pdf_files = sorted(sources_dir.glob("*.pdf"))
    if pdf_files:
        return [
            _source_from_pdf(
                pdf_path,
                write_extracted_text_dir=write_extracted_text_dir,
            )
            for pdf_path in pdf_files
        ]
    bundle_files = sorted(sources_dir.glob("*.pages.json"))
    if bundle_files:
        if write_extracted_text_dir is not None:
            raise ValueError("--write-extracted-text requires PDF sources")
        return [_source_from_bundle(path) for path in bundle_files]
    raise FileNotFoundError(
        f"No PDF files or extracted-text bundles found in {sources_dir}"
    )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Matches a literal XML example at the start of a line. Prose that merely
# mentions ``<Element>`` must never re-anchor the parser.
_XML_EXAMPLE_RE = re.compile(
    r"^<([A-Za-z_][A-Za-z0-9_.:-]*)(?:\s+[^<>]*)?\s*/?>"
    r"(?:\s*[–—-]\s*.*)?$"
)
_XML_CLOSE_RE = re.compile(
    r"^</([A-Za-z_][A-Za-z0-9_.:-]*)\s*>(?:\s*[–—-]\s*.*)?$"
)
_XML_SCALAR_RE = re.compile(
    r"^<(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^>]*)?>"
    r"(?P<text>.*?)</(?P=name)>\s*$"
)
_SECTION_HEADING_RE = re.compile(
    r"^(?P<section>(?:\d+\.)+\d+\.?|\d+\.)\s+"
)
_HEADING_ELEMENT_RE = re.compile(
    r"<([A-Za-z_][A-Za-z0-9_.:-]*)>\.?\s*$"
)
_PLACEHOLDER_CHILD_RE = re.compile(
    r"\{\s*\.\.\.\s*\}.*\(([A-Za-z_][A-Za-z0-9_.:-]*)\)"
)
_ROOT_PROSE_ATTR_RE = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_.:-]*)="([^"]*)"\s*[–—-]\s*(.+)$'
)
_SAME_AS_ELEMENT_RE = re.compile(
    r"\bSame as\b.*<([A-Za-z_][A-Za-z0-9_.:-]*)>\.?\s*$",
    re.IGNORECASE,
)
_SAME_AS_SECTION_RE = re.compile(
    r"\bSame as\b.*\((\d+(?:\.\d+)+)\)\.?\s*$",
    re.IGNORECASE,
)

# Matches an attribute definition line like:    Type Text "DipTrace-PCB" – file created in ...
# or:                                Id Int Component identifier (Id).
_ATTR_LINE_RE = re.compile(
    r"^(\w+)\s+(Int|Real|Text|Bool)\s*(.+)$"
)
_TEXT_CONTENT_LINE_RE = re.compile(r"^(Int|Real|Text|Bool)\s+(.+)$")
_MISSING_TYPE_ATTRIBUTE_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_.:-]*)\s+(.+)$"
)

# Matches an enum value line like:   "Y" – enabled;
# or:                                "N" – disabled.
_ENUM_VALUE_RE = re.compile(r'"([^"]+)"(?=\s*(?:[;.]|[–—-]))')

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
    stripped = line.strip()
    m = _ATTR_LINE_RE.match(stripped)
    if m:
        return m.group(1), m.group(2), m.group(3).strip()
    # pypdf 4 can glue either side of the type token. Prefer the right-most
    # plausible token so PointerTextText... becomes PointerText / Text rather
    # than Pointer / Text.
    candidates: list[tuple[str, str, str]] = []
    for type_match in re.finditer(r"(Int|Real|Text|Bool)", stripped):
        name = stripped[: type_match.start()]
        description = stripped[type_match.end() :]
        if (
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", name)
            and description.strip()
        ):
            candidates.append(
                (
                    name,
                    type_match.group(1),
                    description.strip(),
                )
            )
    if candidates:
        return candidates[-1]
    return None


def _extract_enum_values_from_block(text_block: str) -> list[str]:
    """Extract enumerated values from a text block following an attribute definition."""
    values: list[str] = []
    for line in text_block.splitlines():
        stripped = line.strip()
        # Quoted examples embedded in prose ("Conductor", "Separate Trace",
        # etc.) are references, not enum declarations. Specification enum
        # rows consistently begin with the quoted value.
        if not stripped.startswith('"'):
            continue
        for match in _ENUM_VALUE_RE.finditer(stripped):
            value = match.group(1)
            if value not in values:
                values.append(value)
    return values


def _detect_element_name_from_example(line: str) -> str | None:
    """Extract the element name from an XML example line."""
    stripped = line.strip()
    scalar = _XML_SCALAR_RE.match(stripped)
    if scalar:
        return scalar.group("name")
    m = _XML_EXAMPLE_RE.match(stripped)
    if m:
        return m.group(1)
    return None


def _is_toc_line(line: str) -> bool:
    """Check if a line is from the table of contents."""
    return "..." in line and line.count(".") > 3


def _logical_page_lines(
    pages: list[str],
    page_offset: int,
) -> list[tuple[int, str]]:
    """Return page-tagged lines, joining XML openings even across page breaks."""
    physical_lines = [
        (page_idx + page_offset, line.strip())
        for page_idx, page_text in enumerate(pages)
        for line in page_text.splitlines()
    ]
    result: list[tuple[int, str]] = []
    index = 0
    while index < len(physical_lines):
        page_num, stripped = physical_lines[index]
        if (
            _SECTION_HEADING_RE.match(stripped)
            and stripped.endswith(",")
            and index + 1 < len(physical_lines)
            and re.fullmatch(
                r"<[A-Za-z_][A-Za-z0-9_.:-]*>",
                physical_lines[index + 1][1],
            )
        ):
            index += 1
            stripped = f"{stripped} {physical_lines[index][1]}"
        if (
            stripped.startswith("<")
            and not stripped.startswith(("</", "<!", "<?"))
            and ">" not in stripped
        ):
            parts = [stripped]
            while index + 1 < len(physical_lines) and not any(
                ">" in part for part in parts
            ):
                index += 1
                _, continuation = physical_lines[index]
                if continuation.startswith("©"):
                    continue
                parts.append(continuation)
            stripped = " ".join(part for part in parts if part)
        result.append((page_num, stripped))
        index += 1
    return result


def _new_element_record(document_type: str, page_num: int) -> dict[str, Any]:
    return {
        "documents": [document_type],
        "pages": [page_num],
        "attributes": {},
        "text_content": [],
        "children": [],
    }


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
    definition_element: str | None = None
    definition_is_scalar = False
    definition_inline_attributes: set[str] = set()
    definition_inline_values: dict[str, str] = {}
    example_stack: list[str] = []
    awaiting_primary_example = True
    prefer_next_literal = False
    list_parent: str | None = None
    pending: dict[str, Any] | None = None
    root_units_documented = False
    current_section: str | None = None
    section_elements: dict[str, str] = {}
    same_as_elements: list[tuple[str, str]] = []

    def register_element(name: str, page_num: int) -> dict[str, Any]:
        element = elements.setdefault(
            name,
            _new_element_record(document_type, page_num),
        )
        if document_type not in element["documents"]:
            element["documents"].append(document_type)
        if page_num not in element["pages"]:
            element["pages"].append(page_num)
        return element

    def flush_pending() -> None:
        nonlocal pending, root_units_documented
        if pending is None:
            return
        element_name = str(pending["element"])
        element = elements[element_name]
        description = " ".join(
            part.strip() for part in pending["description_parts"] if part.strip()
        ).strip()
        enum_values = list(dict.fromkeys(pending["enum_values"]))
        metadata = {
            "type": pending["type"],
            "description": description,
            "enum": enum_values or None,
            "units": _infer_units(
                str(pending["name"]),
                description,
                element_name,
            ),
            "omitted_when": _detect_omitted_when(description),
        }
        if (
            element_name in {"Source", "Library"}
            and pending["name"] == "Units"
            and _documents_root_units(description)
        ):
            metadata = _document_units_metadata()
            root_units_documented = True
        if pending["text_content"]:
            text_entry = {
                "source_name": pending["name"],
                **metadata,
                "documents": [document_type],
                "pages": [pending["page"]],
            }
            if text_entry not in element["text_content"]:
                element["text_content"].append(text_entry)
        else:
            name = str(pending["name"])
            existing = element["attributes"].get(name)
            if (
                existing is None
                or "from XML example" in str(existing.get("description", ""))
            ):
                element["attributes"][name] = metadata
            elif existing != metadata:
                alternatives = existing.setdefault("alternatives", [])
                if metadata not in alternatives:
                    alternatives.append(metadata)
                merged_enum = list(
                    dict.fromkeys(
                        [
                            *(existing.get("enum") or []),
                            *(metadata.get("enum") or []),
                        ]
                    )
                )
                existing["enum"] = merged_enum or None
                if (
                    existing.get("omitted_when") is None
                    and metadata.get("omitted_when") is not None
                ):
                    existing["omitted_when"] = metadata["omitted_when"]
        pending = None

    for page_num, stripped in _logical_page_lines(pages, page_offset):
        if not stripped or _is_toc_line(stripped) or stripped.startswith("©"):
            continue

        heading = _SECTION_HEADING_RE.match(stripped)
        if heading:
            flush_pending()
            current_section = heading.group("section").rstrip(".")
            heading_element = _HEADING_ELEMENT_RE.search(stripped)
            if heading_element:
                section_elements[current_section] = heading_element.group(1)
                # A heading is only a boundary hint. It must never introduce
                # an element by itself; the following literal XML example does.
                definition_element = None
                definition_is_scalar = False
                definition_inline_attributes.clear()
                definition_inline_values.clear()
                example_stack.clear()
                awaiting_primary_example = True
                prefer_next_literal = False
            else:
                prefer_next_literal = True
            continue

        closing = _XML_CLOSE_RE.match(stripped)
        if closing:
            flush_pending()
            closing_name = closing.group(1)
            if list_parent == closing_name:
                list_parent = None
            if closing_name in example_stack:
                while example_stack:
                    popped = example_stack.pop()
                    if popped == closing_name:
                        break
            continue

        elem_name = _detect_element_name_from_example(stripped)
        if elem_name:
            flush_pending()
            scalar_match = _XML_SCALAR_RE.match(stripped)
            self_closing = stripped.partition(">")[0].rstrip().endswith("/")
            if example_stack:
                parent_name = example_stack[-1]
                parent = register_element(parent_name, page_num)
                if elem_name not in parent["children"]:
                    parent["children"].append(elem_name)
            elif list_parent is not None and elem_name != list_parent:
                parent = register_element(list_parent, page_num)
                if elem_name not in parent["children"]:
                    parent["children"].append(elem_name)
            element = register_element(elem_name, page_num)
            inline_attrs = _parse_xml_example_attrs(stripped)
            for attr_name, attr_value in inline_attrs.items():
                description = (
                    f"Attribute of <{elem_name}> (from XML example)"
                )
                if elem_name == "Library" and attr_name == "Type":
                    description = (
                        "Library file type shown in the specification's "
                        "literal XML example."
                    )
                elif elem_name == "Library" and attr_name == "Version":
                    description = (
                        "Library file-format version shown in the "
                        "specification's literal XML example."
                    )
                element["attributes"].setdefault(
                    attr_name,
                    {
                        "type": _infer_type(attr_value),
                        "description": description,
                        "enum": None,
                        "units": _infer_units(attr_name, "", elem_name),
                        "omitted_when": None,
                    },
                )
            if (
                awaiting_primary_example
                or prefer_next_literal
                or not example_stack
            ):
                definition_element = elem_name
                definition_is_scalar = scalar_match is not None
                definition_inline_attributes = set(inline_attrs)
                definition_inline_values = inline_attrs
                awaiting_primary_example = False
                prefer_next_literal = False
                if current_section is not None:
                    section_elements[current_section] = elem_name
            if "start of" in stripped.casefold():
                list_parent = elem_name
            if scalar_match is None and not self_closing:
                example_stack.append(elem_name)
            continue

        placeholder = _PLACEHOLDER_CHILD_RE.search(stripped)
        if placeholder and list_parent is not None:
            child_name = placeholder.group(1)
            parent = register_element(list_parent, page_num)
            register_element(child_name, page_num)
            if child_name not in parent["children"]:
                parent["children"].append(child_name)
            continue

        same_as_target = _SAME_AS_ELEMENT_RE.search(stripped)
        if definition_element is not None and same_as_target:
            same_as_elements.append(
                (definition_element, same_as_target.group(1))
            )
            continue
        same_as_section = _SAME_AS_SECTION_RE.search(stripped)
        if definition_element is not None and same_as_section:
            target = section_elements.get(same_as_section.group(1))
            if target is not None:
                same_as_elements.append((definition_element, target))
            continue

        if definition_element is None:
            continue

        root_prose = _ROOT_PROSE_ATTR_RE.match(stripped)
        if root_prose and definition_element in {"Source", "Library"}:
            prefer_next_literal = False
            flush_pending()
            pending = {
                "element": definition_element,
                "name": root_prose.group(1),
                "type": _infer_type(root_prose.group(2)),
                "description_parts": [root_prose.group(3)],
                "enum_values": [],
                "enum_mode": False,
                "text_content": False,
                "page": page_num,
            }
            continue

        text_content = (
            _TEXT_CONTENT_LINE_RE.match(stripped)
            if definition_is_scalar
            else None
        )
        if text_content:
            prefer_next_literal = False
            flush_pending()
            pending = {
                "element": definition_element,
                "name": definition_element,
                "type": text_content.group(1),
                "description_parts": [text_content.group(2)],
                "enum_values": _extract_enum_values_from_block(
                    text_content.group(2)
                ),
                "enum_mode": (
                    text_content.group(2).rstrip().endswith(":")
                    or text_content.group(2).lstrip().startswith('"')
                ),
                "text_content": True,
                "page": page_num,
            }
            continue

        attr = _parse_attribute_line(stripped)
        if attr:
            prefer_next_literal = False
            flush_pending()
            attr_name, attr_type, attr_desc = attr
            pending = {
                "element": definition_element,
                "name": attr_name,
                "type": attr_type,
                "description_parts": [attr_desc],
                "enum_values": _extract_enum_values_from_block(attr_desc),
                "enum_mode": (
                    attr_desc.rstrip().endswith(":")
                    or attr_desc.lstrip().startswith('"')
                ),
                "text_content": (
                    definition_is_scalar
                    and attr_name not in definition_inline_attributes
                ),
                "page": page_num,
            }
            continue

        missing_type_attr = _MISSING_TYPE_ATTRIBUTE_RE.match(stripped)
        if (
            missing_type_attr
            and missing_type_attr.group(1) in definition_inline_attributes
        ):
            prefer_next_literal = False
            flush_pending()
            attr_name = missing_type_attr.group(1)
            attr_desc = missing_type_attr.group(2)
            pending = {
                "element": definition_element,
                "name": attr_name,
                "type": _infer_type(definition_inline_values[attr_name]),
                "description_parts": [attr_desc],
                "enum_values": _extract_enum_values_from_block(attr_desc),
                "enum_mode": (
                    attr_desc.rstrip().endswith(":")
                    or attr_desc.lstrip().startswith('"')
                ),
                "text_content": False,
                "page": page_num,
            }
            continue

        if pending is not None:
            enum_values = _extract_enum_values_from_block(stripped)
            if enum_values and (
                pending["enum_mode"]
                or pending["enum_values"]
            ):
                pending["enum_values"].extend(enum_values)
                pending["enum_mode"] = True
            else:
                pending["description_parts"].append(stripped)

    flush_pending()

    for source_name, target_name in same_as_elements:
        source = elements.get(source_name)
        target = elements.get(target_name)
        if (
            target is not None
            and not target["attributes"]
            and len(target["children"]) == 1
        ):
            target = elements.get(target["children"][0])
        if source is None or target is None:
            continue
        for attr_name, metadata in target["attributes"].items():
            existing = source["attributes"].get(attr_name)
            if (
                existing is None
                or "from XML example"
                in str(existing.get("description", ""))
            ):
                source["attributes"][attr_name] = copy.deepcopy(metadata)

    if root_units_documented:
        for element_name in ("Source", "Library"):
            element = elements.get(element_name)
            if element is None or "Units" not in element["attributes"]:
                continue
            element["attributes"]["Units"] = _document_units_metadata()

    return elements


def _documents_root_units(description: str) -> bool:
    normalized = " ".join(description.casefold().split())
    return (
        "measurement units of dimensions in the file" in normalized
        and "mm" in normalized
        and "millimetres" in normalized
        and "inch" in normalized
        and "inches" in normalized
        and "mil" in normalized
        and "mils" in normalized
    )


def _document_units_metadata() -> dict[str, Any]:
    return {
        "type": "Text",
        "description": (
            "Measurement units of dimensions in the file: "
            "mm – millimetres; inch – inches; mil – mils."
        ),
        "enum": ["mm", "inch", "mil"],
        "units": "document_units",
        "omitted_when": None,
    }


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
    if not desc:
        return None
    match = re.search(
        r"\b(?:parameter\s+is\s+)?(?:absent|omitted)\s+(.+?)(?:\.|$)",
        desc,
        flags=re.IGNORECASE,
    )
    if match:
        # Preserve the source clause instead of replacing an unknown
        # condition with a generic assumption.
        return match.group(1).strip()
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


def build_inventory(
    sources_dir: Path,
    *,
    write_extracted_text_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the inventory from pinned PDF extraction or committed page bundles."""
    sources_info: list[dict[str, Any]] = []
    all_elements: dict[str, dict[str, Any]] = {}

    sources = _load_extracted_sources(
        sources_dir,
        write_extracted_text_dir=write_extracted_text_dir,
    )
    for source in sources:
        # Determine document type from filename
        name_lower = source.file.lower()
        if "pcb" in name_lower:
            doc_type = "pcb"
        elif "schematic" in name_lower:
            doc_type = "schematic"
        elif "plugin" in name_lower:
            # Plugins spec describes settings.xml, not the XML format elements
            sources_info.append({
                "file": source.file,
                "url": source.url,
                "sha256": source.sha256,
                "pages": len(source.pages),
                "document_format_version": "4.3.0.3",
                "published": "2023",
                "size_bytes": source.size_bytes,
                "extracted_text_file": source.extracted_text_file,
                "extracted_text_sha256": source.extracted_text_sha256,
                "extraction_engine": {
                    "name": _EXTRACTION_ENGINE,
                    "version": _EXTRACTION_ENGINE_VERSION,
                },
                "note": (
                    "Plug-in specification; describes settings.xml, "
                    "not the XML format elements"
                ),
            })
            continue
        else:
            doc_type = "unknown"

        pages = list(source.pages)
        elements = _parse_spec_pages(pages, doc_type, 1)

        sources_info.append({
            "file": source.file,
            "url": source.url,
            "sha256": source.sha256,
            "pages": len(pages),
            "document_format_version": "4.3.0.3",
            "published": "2023",
            "size_bytes": source.size_bytes,
            "extracted_text_file": source.extracted_text_file,
            "extracted_text_sha256": source.extracted_text_sha256,
            "extraction_engine": {
                "name": _EXTRACTION_ENGINE,
                "version": _EXTRACTION_ENGINE_VERSION,
            },
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
                # Keep scalar element content distinct from XML attributes.
                for text_entry in elem_data["text_content"]:
                    if text_entry not in all_elements[elem_name]["text_content"]:
                        all_elements[elem_name]["text_content"].append(text_entry)
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
    parser.add_argument(
        "--sources",
        required=True,
        help="Directory containing spec PDFs or committed *.pages.json bundles",
    )
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument(
        "--write-extracted-text",
        help="Write canonical per-page text bundles to this directory (PDF mode only)",
    )
    parser.add_argument("--check", action="store_true", help="Verify committed file matches")
    args = parser.parse_args()

    sources_dir = Path(args.sources)
    out_path = Path(args.out)
    extracted_text_dir = (
        Path(args.write_extracted_text) if args.write_extracted_text is not None else None
    )

    inventory = build_inventory(
        sources_dir,
        write_extracted_text_dir=extracted_text_dir,
    )
    try:
        validate_inventory(
            inventory,
            repository_root=Path(__file__).resolve().parents[1],
        )
    except ValueError as exc:
        print(f"FAIL: generated inventory failed integrity checks: {exc}", file=sys.stderr)
        return 1

    # Deterministic JSON output
    output_json = _canonical_json(inventory)

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
