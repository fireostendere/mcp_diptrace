from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from .geometry import BBox, Point, to_mm
from .numeric_inputs import (
    require_finite_number,
)
from .xml_document import DipTraceDocument

_XML_ID = re.compile(r"[^A-Za-z0-9._-]+")
_MARKING_TAGS = (
    ("RefDesMarking", "RefDes"),
    ("NameMarking", "Name"),
    ("ValueMarking", "Value"),
    ("PatternMarking", "PatternStyle"),
    ("ManufacturerMarking", "Manufacturer"),
    ("DatasheetMarking", "Datasheet"),
)
def _slug(value: str) -> str:
    return _XML_ID.sub("-", value.strip()).strip("-") or "object"
def stable_id(kind: str, *parts: str) -> str:
    payload = "::".join(part for part in parts if part)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{_slug(kind)}_{digest}"
def document_id_for(document: DipTraceDocument) -> str:
    return stable_id("doc", document.source_type, str(document.path.resolve()))
def _xml_identity(xml_id: str, *fallback: str) -> tuple[str, ...]:
    if xml_id:
        return (f"xml:{xml_id}",)
    return tuple(f"fallback:{value}" for value in fallback if value)
def _marking_stable_id(
    document: DipTraceDocument,
    parent_id: str,
    marking_tag: str,
    surface: str,
) -> str:
    return stable_id(
        "component-text",
        document.source_type,
        parent_id,
        marking_tag,
        surface,
    )
def _pad_stable_id(document: DipTraceDocument, parent_id: str, pad_id: str) -> str:
    return stable_id(
        "pad",
        document.source_type,
        parent_id,
        *_xml_identity(pad_id, pad_id),
    )
def _pin_stable_id(document: DipTraceDocument, parent_id: str, pin_index: str) -> str:
    return stable_id("pin", document.source_type, parent_id, pin_index)
def _bool_attr(element: ET.Element, name: str, default: str = "N") -> bool:
    return element.get(name, default).upper() == "Y"
def _float_attr(
    document: DipTraceDocument,
    element: ET.Element,
    name: str,
) -> float | None:
    value = element.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return require_finite_number(
        parsed,
        context=f"attribute {name}={value!r} on <{element.tag}>",
        offset=document.element_byte_offset(element),
        details={"element": str(element.tag), "attribute": name},
    )
def _float_text(
    document: DipTraceDocument,
    element: ET.Element,
    field_name: str,
    value: str | None,
    default: float,
) -> float:
    try:
        parsed = float(value) if value is not None else default
    except ValueError:
        return default
    return require_finite_number(
        parsed,
        context=f"numeric field {field_name} on <{element.tag}>",
        offset=document.element_byte_offset(element),
        details={"element": str(element.tag), "field": field_name},
    )
def _float_attr_mm(document: DipTraceDocument, element: ET.Element, name: str) -> float | None:
    value = _float_attr(document, element, name)
    if value is None:
        return None
    return require_finite_number(
        to_mm(value, document.units),
        context=f"converted attribute {name} on <{element.tag}>",
        offset=document.element_byte_offset(element),
        details={"element": str(element.tag), "attribute": name},
    )
def _first_float_attr_mm(
    document: DipTraceDocument,
    element: ET.Element,
    names: tuple[str, ...],
) -> float | None:
    for name in names:
        if element.get(name) is not None:
            return _float_attr_mm(document, element, name)
    return None
def _text(element: ET.Element, child: str, default: str = "") -> str:
    value = element.findtext(child)
    return value.strip() if value is not None else default
def _additional_fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field in element.findall("./AddFields/AddField"):
        name = _text(field, "Name")
        if name:
            fields[name] = _text(field, "Text")
    return fields
def _point_dict(point: Point | None) -> dict[str, float] | None:
    if point is None:
        return None
    return {"x": point.x, "y": point.y}
def _bbox_dict(box: BBox | None) -> dict[str, float] | None:
    if box is None:
        return None
    return {
        "min_x": box.min_x,
        "min_y": box.min_y,
        "max_x": box.max_x,
        "max_y": box.max_y,
    }
def _bbox_from_center(x: float | None, y: float | None, width: float, height: float) -> BBox | None:
    if x is None or y is None:
        return None
    half_width = width / 2.0
    half_height = height / 2.0
    return BBox(x - half_width, y - half_height, x + half_width, y + half_height)
def _element_short(element: ET.Element, limit: int = 400) -> str:
    rendered = ET.tostring(element, encoding="unicode")
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:limit]}..."
