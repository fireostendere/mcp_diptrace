from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Literal

from .adapters import document_id_for, stable_id
from .domain import (
    GeometryShape,
    LibraryComponent,
    LibraryModel,
    LibraryPad,
    LibraryPadStyle,
    LibraryPattern,
    LibraryPin,
    LibraryValidationFinding,
)
from .errors import AmbiguousSelectorError, DocumentError, ObjectNotFoundError
from .geometry import BBox, Point, Transform, bbox_union, to_mm
from .geometry_backend import offset_shape, shape_bbox
from .xml_document import DipTraceDocument


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path) or "").strip()


def _number(element: ET.Element, attribute: str, default: float = 0.0) -> float:
    raw = element.get(attribute)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise DocumentError(
            f"Invalid numeric attribute {attribute}={raw!r} on <{element.tag}>"
        ) from exc


def _additional_fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field in element.findall("./AddFields/AddField"):
        name = _text(field, "./Name")
        if name:
            fields[name] = _text(field, "./Text")
    return fields


def _bbox_dict(box: BBox | None) -> dict[str, float] | None:
    return box.as_dict() if box is not None else None


def _center_bbox(x: float, y: float, width: float, height: float) -> BBox:
    return BBox(x - width / 2.0, y - height / 2.0, x + width / 2.0, y + height / 2.0)


def _point_elements(element: ET.Element) -> list[ET.Element]:
    """Return points used by both documented and observed DipTrace exports."""
    points = element.find("./Points")
    if points is None:
        return []
    return [item for item in points if item.tag in {"Point", "Item"}]


def _pad_geometry(
    style: LibraryPadStyle | None,
    x: float,
    y: float,
    rotation_deg: float,
) -> GeometryShape | None:
    if style is None or style.width <= 0.0 or style.height <= 0.0:
        return None
    shape_name = style.shape.casefold().replace(" ", "")
    if shape_name in {"ellipse", "oval"}:
        kind: Literal["circle", "ellipse", "rectangle", "obround"] = (
            "circle" if math.isclose(style.width, style.height) else "ellipse"
        )
    elif shape_name in {"rectangle", "rect"}:
        kind = "rectangle"
    elif shape_name in {"obround", "roundedrectangle", "long"}:
        kind = "obround"
    elif shape_name == "polygon" and len(style.polygon_points) >= 3:
        transform = Transform(translate_x=x, translate_y=y, rotation_deg=rotation_deg)
        return GeometryShape(
            kind="polygon",
            points=[
                transform.apply_point(
                    Point(
                        point["x"] + style.x_offset,
                        point["y"] + style.y_offset,
                    )
                ).as_dict()
                for point in style.polygon_points
            ],
        )
    else:
        return None
    transform = Transform(translate_x=x, translate_y=y, rotation_deg=rotation_deg)
    center = transform.apply_point(Point(style.x_offset, style.y_offset))
    return GeometryShape(
        kind=kind,
        center=center.as_dict(),
        width=style.width,
        height=style.height,
        rotation_deg=rotation_deg,
        approximation=(
            "Rounded corner is conservatively represented as a rectangle"
            if style.corner_percent > 0.0 and kind == "rectangle"
            else None
        ),
    )


def _mask_paste_geometry(
    style: LibraryPadStyle | None,
    copper: GeometryShape | None,
    x: float,
    y: float,
    rotation_deg: float,
) -> tuple[dict[str, list[GeometryShape]], dict[str, list[GeometryShape]]]:
    if style is None or copper is None:
        return {}, {}
    mask: dict[str, list[GeometryShape]] = {}
    paste: dict[str, list[GeometryShape]] = {}
    for side, prefix in (("Top", "Top"), ("Bottom", "Bot")):
        mask_mode = style.mask_paste.get(f"{prefix}Mask")
        if mask_mode == "Tented":
            mask[side] = []
        elif mask_mode == "Open" and style.custom_swell is not None:
            expanded = offset_shape(copper, style.custom_swell)
            if expanded is not None:
                mask[side] = [expanded]
        paste_mode = style.mask_paste.get(f"{prefix}Paste")
        if paste_mode == "No Solder":
            paste[side] = []
        elif paste_mode == "Solder" and style.custom_shrink is not None:
            reduced = offset_shape(copper, -style.custom_shrink)
            if reduced is not None:
                paste[side] = [reduced]
        elif paste_mode == "Segments":
            transform = Transform(translate_x=x, translate_y=y, rotation_deg=rotation_deg)
            segment_shapes: list[GeometryShape] = []
            for item in style.mask_paste_segments.get(side, []):
                center = transform.apply_point(
                    Point(
                        (item["x1"] + item["x2"]) / 2.0,
                        (item["y1"] + item["y2"]) / 2.0,
                    )
                )
                segment_shapes.append(
                    GeometryShape(
                        kind="rectangle",
                        center=center.as_dict(),
                        width=abs(item["x2"] - item["x1"]),
                        height=abs(item["y2"] - item["y1"]),
                        rotation_deg=rotation_deg,
                    )
                )
            paste[side] = segment_shapes
    return mask, paste


def _pattern_library_root(document: DipTraceDocument) -> ET.Element | None:
    if document.source_type == "DipTrace-PatternLibrary":
        return document.root
    if document.source_type == "DipTrace-ComponentLibrary":
        return document.root.find("./Library[@Type='DipTrace-PatternLibrary']")
    return None


def _pad_styles(root: ET.Element | None, units: str) -> list[LibraryPadStyle]:
    if root is None:
        return []
    styles: list[LibraryPadStyle] = []
    for element in root.findall("./PadStyles/PadStyle"):
        main = element.find("./MainStack")
        if main is None:
            shape = ""
            width = 0.0
            height = 0.0
        else:
            shape = main.get("Shape", "")
            width = to_mm(_number(main, "Width"), units)
            height = to_mm(_number(main, "Height"), units)
        hole = element.get("Hole")
        hole_height = element.get("HoleH")
        hole_width_mm = to_mm(float(hole), units) if hole else None
        hole_height_mm = to_mm(float(hole_height), units) if hole_height else None
        mask = element.find("./MaskPaste")
        polygon_points = (
            [
                {
                    "x": to_mm(_number(point, "X"), units),
                    "y": to_mm(_number(point, "Y"), units),
                }
                for point in _point_elements(main)
            ]
            if main is not None
            else []
        )
        segments: dict[str, list[dict[str, float]]] = {}
        if mask is not None:
            for side, tag in (("Top", "TopSegments"), ("Bottom", "BotSegments")):
                items = [
                    {
                        key.casefold(): to_mm(_number(item, key), units)
                        for key in ("X1", "Y1", "X2", "Y2")
                    }
                    for item in mask.findall(f"./{tag}/Item")
                ]
                if items:
                    segments[side] = items
        styles.append(
            LibraryPadStyle(
                name=element.get("Name", "") or "<unnamed>",
                pad_type=element.get("Type", "Surface"),
                side=element.get("Side", "Top"),
                shape=shape,
                width=width,
                height=height,
                x_offset=(
                    to_mm(_number(main, "XOff"), units) if main is not None else 0.0
                ),
                y_offset=(
                    to_mm(_number(main, "YOff", _number(main, "Yoff")), units)
                    if main is not None
                    else 0.0
                ),
                corner_percent=(
                    _number(main, "Corner") if main is not None else 0.0
                ),
                polygon_points=polygon_points,
                hole_type=element.get("HoleType"),
                # Observed 5.2 design caches use negative drill values as a
                # sentinel on unused/generated styles, not physical geometry.
                hole_width=(
                    hole_width_mm
                    if hole_width_mm is not None and hole_width_mm >= 0
                    else None
                ),
                hole_height=(
                    hole_height_mm
                    if hole_height_mm is not None and hole_height_mm >= 0
                    else None
                ),
                mask_paste=dict(mask.attrib) if mask is not None else {},
                mask_paste_segments=segments,
                custom_swell=(
                    to_mm(float(mask.get("CustomSwell", "0")), units)
                    if mask is not None and mask.get("CustomSwell") is not None
                    else None
                ),
                custom_shrink=(
                    to_mm(float(mask.get("CustomShrink", "0")), units)
                    if mask is not None and mask.get("CustomShrink") is not None
                    else None
                ),
            )
        )
    return styles


def _pattern_bbox(
    pads: list[LibraryPad],
    pattern: ET.Element,
    units: str,
) -> dict[str, float] | None:
    boxes = [BBox(**pad.bbox) for pad in pads if pad.bbox is not None]
    for shape in pattern.findall("./Shapes/Shape"):
        points = _point_elements(shape)
        coordinates = [
            Point(to_mm(_number(point, "X"), units), to_mm(_number(point, "Y"), units))
            for point in points
        ]
        if coordinates:
            boxes.append(BBox.from_points(coordinates))
    for hole in pattern.findall("./Holes/Hole"):
        x = to_mm(_number(hole, "X"), units)
        y = to_mm(_number(hole, "Y"), units)
        diameter = to_mm(_number(hole, "Diam"), units)
        boxes.append(_center_bbox(x, y, diameter, diameter))
    return _bbox_dict(bbox_union(boxes)) if boxes else None


def _patterns(
    document: DipTraceDocument,
    root: ET.Element | None,
    styles: list[LibraryPadStyle],
) -> list[LibraryPattern]:
    if root is None:
        return []
    style_by_name = {style.name: style for style in styles}
    patterns: list[LibraryPattern] = []
    for index, element in enumerate(root.findall("./Patterns/Pattern")):
        name = _text(element, "./Name")
        unique_name = _text(element, "./Name_Unique")
        pattern_style = element.get("PatternStyle") or element.get("Style")
        identity = pattern_style or unique_name or name or f"index:{index}"
        pattern_id = stable_id("library-pattern", document.source_type, identity)
        default_pad = element.find("./DefPad")
        default_style = default_pad.get("Style", "") if default_pad is not None else ""
        pads: list[LibraryPad] = []
        for pad_index, pad in enumerate(element.findall("./Pads/Pad")):
            xml_id = pad.get("Id", str(pad_index))
            style_name = pad.get("Style", default_style)
            style = style_by_name.get(style_name)
            x = to_mm(_number(pad, "X"), document.units)
            y = to_mm(_number(pad, "Y"), document.units)
            rotation_deg = math.degrees(_number(pad, "Angle"))
            geometry = _pad_geometry(style, x, y, rotation_deg)
            pad_box = shape_bbox(geometry) if geometry is not None else None
            mask_geometry, paste_geometry = _mask_paste_geometry(
                style, geometry, x, y, rotation_deg
            )
            pads.append(
                LibraryPad(
                    stable_id=stable_id("library-pad", pattern_id, f"xml:{xml_id}"),
                    xml_id=xml_id,
                    number=_text(pad, "./Number"),
                    style=style_name,
                    position={"x": x, "y": y},
                    rotation_deg=rotation_deg,
                    side=pad.get("Side", "Top"),
                    locked=pad.get("Locked", "N") == "Y",
                    bbox=_bbox_dict(pad_box),
                    geometry=geometry,
                    mask_geometry=mask_geometry,
                    paste_geometry=paste_geometry,
                )
            )
        holes = [
            {
                **dict(hole.attrib),
                "x_mm": to_mm(_number(hole, "X"), document.units),
                "y_mm": to_mm(_number(hole, "Y"), document.units),
                "diameter_mm": to_mm(_number(hole, "Diam"), document.units),
                "hole_diameter_mm": to_mm(_number(hole, "HoleDiam"), document.units),
            }
            for hole in element.findall("./Holes/Hole")
        ]
        shapes: list[dict[str, Any]] = [
            {
                "attributes": dict(shape.attrib),
                "points": [
                    {
                        "x": to_mm(_number(point, "X"), document.units),
                        "y": to_mm(_number(point, "Y"), document.units),
                    }
                    for point in _point_elements(shape)
                ],
                "lines": [item.text or "" for item in shape.findall("./Lines/Item")],
            }
            for shape in element.findall("./Shapes/Shape")
        ]
        courtyard_geometry: dict[str, list[GeometryShape]] = {}
        for shape_data in shapes:
            attributes = shape_data["attributes"]
            layer = str(attributes.get("Layer", ""))
            if "Courtyard" not in layer:
                continue
            points = list(shape_data["points"])
            shape_type = str(attributes.get("Type", ""))
            courtyard_shape: GeometryShape | None = None
            if shape_type == "Polygon" and len(points) >= 3:
                courtyard_shape = GeometryShape(kind="polygon", points=points)
            elif shape_type == "Line" and len(points) >= 2:
                line_width = to_mm(float(attributes.get("LineWidth", "0")), document.units)
                if line_width > 0.0:
                    courtyard_shape = GeometryShape(
                        kind="line",
                        points=points,
                        line_width=line_width,
                    )
            if courtyard_shape is not None:
                side = "Bottom" if layer.startswith("Bottom") else "Top"
                courtyard_geometry.setdefault(side, []).append(courtyard_shape)
        model = element.find("./Model3D")
        model_rotate = model.find("./Rotate") if model is not None else None
        model_offset = model.find("./Offset") if model is not None else None
        model_zoom = model.find("./Zoom") if model is not None else None
        pattern = LibraryPattern(
            stable_id=pattern_id,
            index=index,
            style=pattern_style,
            name=name,
            unique_name=unique_name,
            value=_text(element, "./Value"),
            refdes=element.get("RefDes", ""),
            mounting=element.get("Mounting", "None"),
            manufacturer=_text(element, "./Manufacturer"),
            datasheet=_text(element, "./Datasheet"),
            fields=_additional_fields(element),
            pads=pads,
            holes=holes,
            shapes=shapes,
            courtyard_geometry=courtyard_geometry,
            model_3d=(
                {
                    "filename": _text(model, "./Filename"),
                    "rotate": dict(model_rotate.attrib) if model_rotate is not None else {},
                    "offset": dict(model_offset.attrib) if model_offset is not None else {},
                    "zoom": dict(model_zoom.attrib) if model_zoom is not None else {},
                }
                if model is not None
                else None
            ),
        )
        pattern.bbox = _pattern_bbox(pads, element, document.units)
        patterns.append(pattern)
    return patterns


def _components(document: DipTraceDocument) -> list[LibraryComponent]:
    if document.source_type != "DipTrace-ComponentLibrary":
        return []
    components: list[LibraryComponent] = []
    for index, element in enumerate(document.root.findall("./Components/Component")):
        parts = element.findall("./Part")
        first = parts[0] if parts else element
        name = next((_text(part, "./Name") for part in parts if _text(part, "./Name")), "")
        refdes = next((part.get("RefDes", "") for part in parts if part.get("RefDes")), "")
        identity = name or f"index:{index}"
        component_id = stable_id("library-component", document.source_type, identity)
        pins: list[LibraryPin] = []
        for part_index, part in enumerate(parts):
            for pin_index, pin in enumerate(part.findall("./Pins/Pin")):
                xml_id = pin.get("Id", str(pin_index))
                pins.append(
                    LibraryPin(
                        stable_id=stable_id(
                            "library-pin", component_id, str(part_index), f"xml:{xml_id}"
                        ),
                        part_index=part_index,
                        xml_id=xml_id,
                        name=_text(pin, "./Name"),
                        number=_text(pin, "./PadNumber"),
                        pad_id=pin.get("PadId"),
                        electrical_type=pin.get("ElectricType", "Undefined"),
                        pin_type=pin.get("Type", "Default"),
                        position={
                            "x": to_mm(_number(pin, "X"), document.units),
                            "y": to_mm(_number(pin, "Y"), document.units),
                        },
                        orientation_deg=_number(pin, "Orientation"),
                        locked=pin.get("Locked", "N") == "Y",
                    )
                )
        attached_pattern = first.find("./Pattern")
        components.append(
            LibraryComponent(
                stable_id=component_id,
                index=index,
                name=name,
                refdes=refdes,
                value=_text(first, "./Value"),
                manufacturer=_text(first, "./Manufacturer"),
                datasheet=_text(first, "./Datasheet"),
                fields=_additional_fields(first),
                pattern_style=(
                    attached_pattern.get("Style") if attached_pattern is not None else None
                ),
                part_count=len(parts),
                pins=pins,
            )
        )
    return components


def get_library_model(document: DipTraceDocument) -> LibraryModel:
    if document.source_type not in {
        "DipTrace-ComponentLibrary",
        "DipTrace-PatternLibrary",
    }:
        raise DocumentError("Library model requires a Component or Pattern Library XML document")
    pattern_root = _pattern_library_root(document)
    styles = _pad_styles(pattern_root, document.units)
    patterns = _patterns(document, pattern_root, styles)
    return LibraryModel(
        document_id=document_id_for(document),
        source_type=document.source_type,
        name=document.root.get("Name", ""),
        hint=document.root.get("Hint", ""),
        version=document.version,
        source_units=document.units,
        components=_components(document),
        patterns=patterns,
        pad_styles=styles,
        warnings=[
            "Parser coverage is based on the official DipTrace 4.3 XML specification; "
            "unknown newer fields are preserved but not interpreted."
        ]
        if document.version and not document.version.startswith("4.3")
        else [],
    )


def get_embedded_pattern_model(document: DipTraceDocument) -> LibraryModel | None:
    """Read the PCB design-cache pattern library without mutating the source tree."""
    if document.kind != "pcb":
        return None
    pattern_root = next(
        (
            item
            for item in document.root.iter("Library")
            if item.find("./Patterns") is not None or item.find("./PadStyles") is not None
        ),
        None,
    )
    if pattern_root is None:
        return None
    root = copy.deepcopy(pattern_root)
    # DipTrace 4.3 PCB documentation contains a Type typo for this section. Its
    # structure, rather than that attribute, is authoritative here.
    root.set("Type", "DipTrace-PatternLibrary")
    root.set("Version", root.get("Version", document.version))
    root.set("Units", root.get("Units", document.units))
    embedded = DipTraceDocument(
        path=document.path,
        root=root,
        raw_bytes=ET.tostring(root, encoding="utf-8"),
    )
    return get_library_model(embedded)


def query_library_items(model: LibraryModel, query: str | None = None) -> list[dict[str, Any]]:
    items = [
        {"kind": "library_component", **component.model_dump()}
        for component in model.components
    ] + [{"kind": "library_pattern", **pattern.model_dump()} for pattern in model.patterns]
    if not query:
        return items
    needle = query.casefold()
    return [
        item
        for item in items
        if needle
        in " ".join(
            str(item.get(key, ""))
            for key in ("name", "unique_name", "refdes", "value", "manufacturer")
        ).casefold()
    ]


def get_library_item(
    model: LibraryModel,
    *,
    stable_id_value: str | None = None,
    name: str | None = None,
    kind: str,
) -> LibraryComponent | LibraryPattern:
    candidates: list[LibraryComponent | LibraryPattern]
    candidates = list(model.components if kind == "component" else model.patterns)
    matches = [
        item
        for item in candidates
        if (stable_id_value is not None and item.stable_id == stable_id_value)
        or (name is not None and item.name.casefold() == name.casefold())
    ]
    if not matches:
        raise ObjectNotFoundError(f"Library {kind} was not found")
    if len(matches) > 1:
        raise AmbiguousSelectorError(
            f"Library {kind} selector matched multiple items",
            object_ids=[item.stable_id for item in matches],
        )
    return matches[0]


def validate_library(model: LibraryModel) -> list[LibraryValidationFinding]:
    findings: list[LibraryValidationFinding] = []
    styles = {style.name: style for style in model.pad_styles}
    patterns_by_style = {pattern.style: pattern for pattern in model.patterns if pattern.style}
    for name, count in Counter(item.name.casefold() for item in model.components).items():
        if name and count > 1:
            findings.append(
                LibraryValidationFinding(
                    code="duplicate_component_name",
                    severity="error",
                    message=f"Component name is duplicated: {name}",
                )
            )
    for component in model.components:
        if not component.name:
            findings.append(
                LibraryValidationFinding(
                    code="missing_component_name",
                    severity="error",
                    message="Component has no name",
                    object_id=component.stable_id,
                )
            )
        if not component.pins:
            findings.append(
                LibraryValidationFinding(
                    code="component_without_pins",
                    severity="warning",
                    message=f"Component {component.name!r} has no pins",
                    object_id=component.stable_id,
                )
            )
        numbers = [pin.number for pin in component.pins if pin.number]
        for duplicate, count in Counter(numbers).items():
            if count > 1:
                findings.append(
                    LibraryValidationFinding(
                        code="duplicate_pin_number",
                        severity="error",
                        message=f"Pin number {duplicate!r} occurs {count} times",
                        object_id=component.stable_id,
                    )
                )
        for pin in component.pins:
            if not pin.number:
                findings.append(
                    LibraryValidationFinding(
                        code="missing_pin_number",
                        severity="error",
                        message=f"Pin {pin.name or pin.xml_id!r} has no pad number",
                        object_id=pin.stable_id,
                    )
                )
        if component.pattern_style:
            pattern = patterns_by_style.get(component.pattern_style)
            if pattern is None:
                findings.append(
                    LibraryValidationFinding(
                        code="attached_pattern_not_found",
                        severity="error",
                        message=f"Attached pattern style {component.pattern_style!r} is absent",
                        object_id=component.stable_id,
                    )
                )
            else:
                pad_numbers = {pad.number for pad in pattern.pads}
                for pin in component.pins:
                    if pin.number and pin.number not in pad_numbers:
                        findings.append(
                            LibraryValidationFinding(
                                code="pin_pad_mapping_missing",
                                severity="error",
                                message=f"Pin {pin.number!r} has no matching pattern pad",
                                object_id=pin.stable_id,
                                details={"pattern_id": pattern.stable_id},
                            )
                        )
    for pattern in model.patterns:
        if not pattern.name:
            findings.append(
                LibraryValidationFinding(
                    code="missing_pattern_name",
                    severity="error",
                    message="Pattern has no name",
                    object_id=pattern.stable_id,
                )
            )
        numbers = [pad.number for pad in pattern.pads if pad.number]
        for duplicate, count in Counter(numbers).items():
            if count > 1:
                findings.append(
                    LibraryValidationFinding(
                        code="duplicate_pad_number",
                        severity="error",
                        message=f"Pad number {duplicate!r} occurs {count} times",
                        object_id=pattern.stable_id,
                    )
                )
        for pad in pattern.pads:
            if not pad.number:
                findings.append(
                    LibraryValidationFinding(
                        code="missing_pad_number",
                        severity="error",
                        message="Pattern pad has no number",
                        object_id=pad.stable_id,
                    )
                )
            style = styles.get(pad.style)
            if style is None:
                findings.append(
                    LibraryValidationFinding(
                        code="pad_style_not_found",
                        severity="error",
                        message=f"Pad style {pad.style!r} is absent",
                        object_id=pad.stable_id,
                    )
                )
                continue
            if style.width <= 0 or style.height <= 0:
                findings.append(
                    LibraryValidationFinding(
                        code="invalid_pad_geometry",
                        severity="error",
                        message="Pad width and height must be positive",
                        object_id=pad.stable_id,
                    )
                )
            if style.hole_width is not None:
                ring = (min(style.width, style.height) - style.hole_width) / 2.0
                if ring <= 0:
                    findings.append(
                        LibraryValidationFinding(
                            code="invalid_annular_ring",
                            severity="error",
                            message="Hole is not smaller than the copper pad",
                            object_id=pad.stable_id,
                            details={"annular_ring_mm": ring},
                        )
                    )
    return findings
