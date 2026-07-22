from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Literal

from .domain import (
    BoardModel,
    CapabilityReport,
    DifferentialPairLayerRules,
    DifferentialPairModel,
    DifferentialPairPadPair,
    DifferentialPairRules,
    DifferentialPairSegment,
    DocumentInfo,
    GeometryShape,
    ObjectRecord,
    QueryRequest,
    QueryResult,
    QuerySelector,
    SchematicModel,
    StackupLayer,
    StackupMaterial,
    StackupModel,
    ViaStyleModel,
)
from .errors import DocumentError
from .geometry import BBox, Point, Transform, distance, to_mm, trace_path_length
from .geometry_backend import backend_report, shape_bbox, transform_shape
from .xml_document import DipTraceDocument, XmlEdit

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


def _float_attr(element: ET.Element, name: str) -> float | None:
    value = element.get(name)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _float_text(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _float_attr_mm(document: DipTraceDocument, element: ET.Element, name: str) -> float | None:
    value = _float_attr(element, name)
    if value is None:
        return None
    return to_mm(value, document.units)


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


def _component_records(
    document: DipTraceDocument,
) -> tuple[list[ObjectRecord], dict[str, str], dict[str, str]]:
    records: list[ObjectRecord] = []
    by_xml_id: dict[str, str] = {}
    by_refdes: dict[str, str] = {}
    if document.kind == "pcb":
        from .library_adapters import get_embedded_pattern_model

        pattern_model = get_embedded_pattern_model(document)
        patterns_by_style = {
            pattern.style: pattern
            for pattern in pattern_model.patterns if pattern.style
        } if pattern_model is not None else {}
        pad_styles_by_name = {
            style.name: style
            for style in pattern_model.pad_styles
        } if pattern_model is not None else {}
        for component in document.container.findall("./Components/Component"):
            xml_id = component.get("Id", "")
            refdes = _text(component, "RefDes")
            name = _text(component, "Name")
            value = _text(component, "Value")
            manufacturer = _text(component, "Manufacturer")
            datasheet = _text(component, "Datasheet")
            additional_fields = _additional_fields(component)
            component_type = component.get("Type", "LibraryComponent")
            component_pads = component.findall("./Pads/Pad")
            first_pad = component_pads[0] if component_pads else None
            is_testpoint = (
                component_type == "Pad"
                and (refdes.upper().startswith("TP") or name == "MCP_TESTPOINT")
            ) or (refdes.upper().startswith("TP") and len(component_pads) == 1)
            testpoint_net_id = (
                first_pad.get("NetId")
                if is_testpoint and first_pad is not None and first_pad.get("NetId") != "-1"
                else None
            )
            x = _float_attr_mm(document, component, "X")
            y = _float_attr_mm(document, component, "Y")
            side = component.get("Side", "Top")
            angle_rad = _float_attr(component, "Angle") or 0.0
            rotation_deg = math.degrees(angle_rad)
            pattern_style = component.get("PatternStyle", "")
            pattern = patterns_by_style.get(pattern_style)
            component_transform = (
                Transform(
                    translate_x=x,
                    translate_y=y,
                    rotation_deg=rotation_deg,
                    mirror_x=side == "Bottom",
                )
                if x is not None and y is not None
                else None
            )
            pattern_bbox = (
                component_transform.apply_bbox(BBox(**pattern.bbox))
                if component_transform is not None
                and pattern is not None
                and pattern.bbox is not None
                else None
            )
            stable = stable_id(
                "testpoint" if is_testpoint else "component",
                document.source_type,
                *_xml_identity(xml_id, refdes, name),
            )
            record = ObjectRecord(
                stable_id=stable,
                kind="testpoint" if is_testpoint else "component",
                label=refdes or name or xml_id or stable,
                name=name or None,
                value=value or None,
                refdes=refdes or None,
                xml_id=xml_id or None,
                net_id=testpoint_net_id,
                layer=side,
                side=side,
                locked=_bool_attr(component, "Locked"),
                selected=_bool_attr(component, "Selected"),
                position=_point_dict(Point(x, y)) if x is not None and y is not None else None,
                bbox=_bbox_dict(
                    pattern_bbox or _bbox_from_center(
                        x,
                        y,
                        _float_text(additional_fields.get("MCP.TestpointDiameterMm"), 1.0)
                        if is_testpoint
                        else 1.0,
                        _float_text(additional_fields.get("MCP.TestpointDiameterMm"), 1.0)
                        if is_testpoint
                        else 1.0,
                    )
                ),
                rotation_deg=rotation_deg,
                mirrored=side == "Bottom" or _bool_attr(component, "Flip"),
                geometry_source=(
                    "embedded-pattern-library" if pattern_bbox is not None else "xml-position"
                ),
                confidence=0.95 if pattern_bbox is not None else 0.55,
                attributes={
                    "pattern_style": pattern_style,
                    "pattern_name": pattern.name if pattern is not None else "",
                    "type": component_type,
                    "angle_rad": angle_rad,
                    "manufacturer": manufacturer,
                    "datasheet": datasheet,
                    "additional_fields": additional_fields,
                },
                relationships={"pads": [], "holes": [], "texts": []},
            )
            records.append(record)
            if xml_id:
                by_xml_id[xml_id] = stable
            if refdes:
                by_refdes[refdes.casefold()] = stable
        for component in document.container.findall("./Components/Component"):
            parent = by_xml_id.get(component.get("Id", ""))
            if parent is None:
                continue
            parent_record = next(item for item in records if item.stable_id == parent)
            pattern = patterns_by_style.get(str(parent_record.attributes.get("pattern_style", "")))
            pattern_pads_by_id = {
                item.xml_id: item for item in pattern.pads
            } if pattern is not None else {}
            pattern_pads_by_number = {
                item.number: item for item in pattern.pads if item.number
            } if pattern is not None else {}
            component_transform = (
                Transform(
                    translate_x=parent_record.position["x"],
                    translate_y=parent_record.position["y"],
                    rotation_deg=parent_record.rotation_deg,
                    mirror_x=parent_record.side == "Bottom",
                )
                if parent_record.position is not None
                else None
            )
            for pad in component.findall("./Pads/Pad"):
                pad_id = pad.get("Id", "")
                pad_number = pad.get("Number", pad_id)
                pad_stable = _pad_stable_id(document, parent, pad_id or pad_number)
                parent_record.relationships.setdefault("pads", []).append(pad_stable)
                library_pad = pattern_pads_by_id.get(pad_id) or pattern_pads_by_number.get(
                    pad_number
                )
                local_position = (
                    Point(**library_pad.position) if library_pad is not None else None
                )
                board_position = (
                    component_transform.apply_point(local_position)
                    if component_transform is not None and local_position is not None
                    else None
                )
                pad_position = (
                    parent_record.position
                    if parent_record.kind == "testpoint"
                    else board_position.as_dict() if board_position is not None else None
                )
                board_pad_bbox = (
                    shape_bbox(transform_shape(library_pad.geometry, component_transform))
                    if component_transform is not None
                    and library_pad is not None
                    and library_pad.geometry is not None
                    else component_transform.apply_bbox(BBox(**library_pad.bbox))
                    if component_transform is not None
                    and library_pad is not None
                    and library_pad.bbox is not None
                    else BBox(**parent_record.bbox)
                    if parent_record.kind == "testpoint" and parent_record.bbox is not None
                    else None
                )
                pad_style = (
                    pad_styles_by_name.get(library_pad.style)
                    if library_pad is not None
                    else None
                )
                board_mask_geometry = (
                    {
                        side: [
                            transform_shape(shape, component_transform).model_dump(
                                mode="json"
                            )
                            for shape in shapes
                        ]
                        for side, shapes in library_pad.mask_geometry.items()
                    }
                    if component_transform is not None and library_pad is not None
                    else {}
                )
                board_paste_geometry = (
                    {
                        side: [
                            transform_shape(shape, component_transform).model_dump(
                                mode="json"
                            )
                            for shape in shapes
                        ]
                        for side, shapes in library_pad.paste_geometry.items()
                    }
                    if component_transform is not None and library_pad is not None
                    else {}
                )
                records.append(
                    ObjectRecord(
                        stable_id=pad_stable,
                        kind="pad",
                        label=pad_number or pad_id or pad_stable,
                        name=pad_number or None,
                        xml_id=pad_id or None,
                        parent_id=parent,
                        side=component.get("Side", "Top"),
                        net_id=pad.get("NetId") if pad.get("NetId") != "-1" else None,
                        locked=_bool_attr(component, "Locked"),
                        selected=_bool_attr(component, "Selected"),
                        position=pad_position,
                        bbox=_bbox_dict(board_pad_bbox),
                        geometry=(
                            transform_shape(library_pad.geometry, component_transform)
                            if component_transform is not None
                            and library_pad is not None
                            and library_pad.geometry is not None
                            else None
                        ),
                        geometry_source=(
                            "standalone-pad-component"
                            if parent_record.kind == "testpoint" and pad_position is not None
                            else "embedded-pattern-library"
                            if board_position is not None
                            else "xml-structure"
                        ),
                        confidence=(
                            0.95 if board_position is not None else 0.9
                            if pad_position is not None else 0.4
                        ),
                        attributes={
                            **dict(pad.attrib),
                            "number": pad_number,
                            "pattern_pad_id": library_pad.xml_id if library_pad else None,
                            "local_position": (
                                library_pad.position if library_pad is not None else None
                            ),
                            "pad_style": (
                                pad_style.model_dump(mode="json") if pad_style is not None else None
                            ),
                            "mask_geometry": board_mask_geometry,
                            "paste_geometry": board_paste_geometry,
                        },
                    )
                )
            if pattern is not None and component_transform is not None:
                for hole_index, hole in enumerate(pattern.holes):
                    local = Point(float(hole["x_mm"]), float(hole["y_mm"]))
                    position = component_transform.apply_point(local)
                    diameter = float(
                        hole.get("hole_diameter_mm") or hole.get("diameter_mm") or 0.0
                    )
                    if diameter <= 0:
                        continue
                    hole_id = stable_id(
                        "hole",
                        document.source_type,
                        parent,
                        str(hole.get("Id", hole_index)),
                    )
                    parent_record.relationships["holes"].append(hole_id)
                    records.append(
                        ObjectRecord(
                            stable_id=hole_id,
                            kind="hole",
                            label=f"{parent_record.label}:hole-{hole_index}",
                            parent_id=parent,
                            side=parent_record.side,
                            locked=parent_record.locked,
                            position=position.as_dict(),
                            bbox=point_bbox(position, diameter / 2.0).as_dict(),
                            geometry_source="embedded-pattern-library",
                            confidence=0.95,
                            attributes={
                                **hole,
                                "diameter_mm": diameter,
                                "plated": str(hole.get("Plated", "N")).upper() == "Y",
                            },
                            relationships={"component": [parent]},
                        )
                    )
            for marking_tag, value_source in _MARKING_TAGS:
                marking = component.find(f"./{marking_tag}")
                if marking is None:
                    continue
                for surface in ("Silk", "Assy"):
                    settings = marking.find(f"./{surface}")
                    if settings is None:
                        continue
                    text_stable = _marking_stable_id(
                        document,
                        parent,
                        marking_tag,
                        surface,
                    )
                    parent_record.relationships["texts"].append(text_stable)
                    local = Point(
                        _float_attr_mm(document, settings, "X") or 0.0,
                        _float_attr_mm(document, settings, "Y") or 0.0,
                    )
                    parent_position = parent_record.position or {"x": 0.0, "y": 0.0}
                    board_position = Transform(
                        translate_x=parent_position["x"],
                        translate_y=parent_position["y"],
                        rotation_deg=parent_record.rotation_deg,
                        mirror_x=parent_record.side == "Bottom",
                    ).apply_point(local)
                    text_value = (
                        component.get(value_source, "")
                        if value_source == "PatternStyle"
                        else _text(component, value_source)
                    )
                    text_width = max(1.0, len(text_value) * 0.6)
                    records.append(
                        ObjectRecord(
                            stable_id=text_stable,
                            kind="component_text",
                            label=text_value or marking_tag,
                            name=marking_tag.removesuffix("Marking"),
                            value=text_value,
                            refdes=parent_record.refdes,
                            parent_id=parent,
                            layer=f"{parent_record.side} {surface}",
                            side=parent_record.side,
                            locked=parent_record.locked,
                            position=board_position.as_dict(),
                            bbox=_bbox_dict(
                                _bbox_from_center(
                                    board_position.x,
                                    board_position.y,
                                    text_width,
                                    1.0,
                                )
                            ),
                            rotation_deg=math.degrees(_float_attr(settings, "Angle") or 0.0),
                            mirrored=parent_record.side == "Bottom",
                            geometry_source="xml-component-marking",
                            confidence=0.65,
                            attributes={
                                "marking": marking_tag,
                                "surface": surface,
                                **dict(settings.attrib),
                            },
                            relationships={"component": [parent]},
                        )
                    )
        pad_anchors: dict[tuple[str, str], tuple[Point, str]] = {}
        for trace in document.container.findall("./Nets/Net/Traces/Trace"):
            points = trace.findall("./Points/Point")
            if not points:
                continue
            for suffix, point in (("1", points[0]), ("2", points[-1])):
                if trace.get(f"Connected{suffix}") != "Pad":
                    continue
                comp_id = trace.get(f"Object{suffix}", "")
                pad_id = trace.get(f"SubObject{suffix}", "")
                x = _float_attr_mm(document, point, "X")
                y = _float_attr_mm(document, point, "Y")
                if comp_id and pad_id and x is not None and y is not None:
                    pad_anchors[(comp_id, pad_id)] = (
                        Point(x, y),
                        "xml-trace-endpoint",
                    )
        for ratline in document.container.findall("./Ratlines/Ratline"):
            for suffix in ("1", "2"):
                comp_id = ratline.get(f"Comp{suffix}", "")
                pad_id = ratline.get(f"Pad{suffix}", "")
                x = _float_attr_mm(document, ratline, f"X{suffix}")
                y = _float_attr_mm(document, ratline, f"Y{suffix}")
                if comp_id and pad_id and x is not None and y is not None:
                    pad_anchors[(comp_id, pad_id)] = (
                        Point(x, y),
                        "xml-ratline-endpoint",
                    )
        component_xml_by_stable = {value: key for key, value in by_xml_id.items()}
        for record in records:
            if record.kind != "pad" or record.parent_id is None or record.xml_id is None:
                continue
            component_xml_id = component_xml_by_stable.get(record.parent_id, "")
            anchor_details = pad_anchors.get((component_xml_id, record.xml_id))
            if anchor_details is None:
                continue
            anchor, geometry_source = anchor_details
            if record.position is not None and record.geometry_source == "embedded-pattern-library":
                calculated = Point(**record.position)
                mismatch = distance(calculated, anchor)
                if mismatch > 0.01:
                    record.warnings.append(
                        "Pattern-derived pad position differs from ratline anchor by "
                        f"{mismatch:g} mm"
                    )
                continue
            record.position = anchor.as_dict()
            record.geometry_source = geometry_source
            record.confidence = 0.9 if geometry_source == "xml-trace-endpoint" else 0.75
        return records, by_xml_id, by_refdes

    if document.kind == "schematic":
        for part in document.container.findall("./Components/Part"):
            xml_id = part.get("Id", "")
            refdes = _text(part, "RefDes")
            part_refdes = _text(part, "PartRefDes")
            part_name = _text(part, "PartName")
            name = _text(part, "Name")
            value = _text(part, "Value")
            x = _float_attr_mm(document, part, "X")
            y = _float_attr_mm(document, part, "Y")
            angle_rad = _float_attr(part, "Angle") or 0.0
            stable = stable_id(
                "part",
                document.source_type,
                *_xml_identity(xml_id, refdes, part_refdes, part_name),
            )
            record = ObjectRecord(
                stable_id=stable,
                kind="part",
                label=refdes or part_name or name or xml_id or stable,
                name=name or None,
                value=value or None,
                refdes=refdes or None,
                xml_id=xml_id or None,
                side="schematic",
                locked=_bool_attr(part, "Locked"),
                selected=_bool_attr(part, "Selected"),
                position=_point_dict(Point(x, y)) if x is not None and y is not None else None,
                bbox=_bbox_dict(_bbox_from_center(x, y, 1.0, 1.0)),
                rotation_deg=math.degrees(angle_rad),
                mirrored=_bool_attr(part, "HorzFlip") or _bool_attr(part, "VertFlip"),
                geometry_source="xml-position",
                confidence=0.55,
                attributes={
                    "component_style": part.get("ComponentStyle", ""),
                    "angle_rad": angle_rad,
                    "component_part": part.get("ComponentPart", ""),
                    "part_number": part.get("PartNumber", ""),
                    "sheet": part.get("Sheet", ""),
                    "part_refdes": part_refdes,
                    "part_name": part_name,
                    "additional_fields": _additional_fields(part),
                },
                relationships={"pins": []},
            )
            records.append(record)
            if xml_id:
                by_xml_id[xml_id] = stable
            if refdes:
                by_refdes.setdefault(refdes.casefold(), stable)
        for part in document.container.findall("./Components/Part"):
            parent = by_xml_id.get(part.get("Id", ""))
            if parent is None:
                continue
            parent_record = next(item for item in records if item.stable_id == parent)
            for pin_index, pin in enumerate(part.findall("./Pins/Pin")):
                pin_id = f"{part.get('Id', '')}:{pin_index}"
                pin_stable = _pin_stable_id(document, parent, pin_id)
                parent_record.relationships.setdefault("pins", []).append(pin_stable)
                records.append(
                    ObjectRecord(
                        stable_id=pin_stable,
                        kind="pin",
                        label=f"pin-{pin_index}",
                        refdes=parent_record.refdes,
                        xml_id=pin_id,
                        parent_id=parent,
                        locked=_bool_attr(part, "Locked"),
                        selected=_bool_attr(part, "Selected"),
                        attributes=dict(pin.attrib),
                        geometry_source="xml-structure",
                        confidence=0.4,
                    )
                )
        return records, by_xml_id, by_refdes

    return records, by_xml_id, by_refdes


def _net_records(
    document: DipTraceDocument,
    owner_map: dict[str, str],
    normalized_via_styles: list[ViaStyleModel],
) -> list[ObjectRecord]:
    records: list[ObjectRecord] = []
    if document.kind == "pcb":
        endpoint_list_name = "Pads"
        endpoint_owner_key = "Comp"
    elif document.kind == "schematic":
        endpoint_list_name = "Pins"
        endpoint_owner_key = "Part"
    else:
        return records

    for net in document.container.findall("./Nets/Net"):
        name = _text(net, "Name")
        xml_id = net.get("Id", "")
        stable = stable_id("net", document.source_type, *_xml_identity(xml_id, name))
        endpoints: list[str] = []
        for endpoint in net.findall(f"./{endpoint_list_name}/Item"):
            owner_xml_id = endpoint.get(endpoint_owner_key, "")
            owner_stable = owner_map.get(owner_xml_id)
            if owner_stable:
                if document.kind == "pcb":
                    endpoint_id = endpoint.get("Pad", "")
                    endpoints.append(
                        _pad_stable_id(document, owner_stable, endpoint_id)
                        if endpoint_id
                        else owner_stable
                    )
                else:
                    pin_index = endpoint.get("Pin", "")
                    endpoints.append(
                        _pin_stable_id(
                            document, owner_stable, f"{owner_xml_id}:{pin_index}"
                        )
                        if pin_index
                        else owner_stable
                    )
        trace_ids: list[str] = []
        via_ids: list[str] = []
        via_styles = {style.id: style for style in normalized_via_styles}
        for trace_index, trace in enumerate(net.findall("./Traces/Trace")):
            trace_xml_id = trace.get("Id", "")
            trace_stable = stable_id(
                "trace",
                document.source_type,
                stable,
                *_xml_identity(trace_xml_id, str(trace_index)),
            )
            trace_ids.append(trace_stable)
            points = [
                Point(
                    _float_attr_mm(document, point, "X") or 0.0,
                    _float_attr_mm(document, point, "Y") or 0.0,
                )
                for point in trace.findall("./Points/Point")
            ]
            widths = [
                _float_attr_mm(document, point, "Width")
                for point in trace.findall("./Points/Point")[1:]
            ]
            width_values = [width for width in widths if width is not None]
            segment_layers = [
                point.get("Lay") for point in trace.findall("./Points/Point")[1:]
            ]
            point_elements = trace.findall("./Points/Point")
            arc_middle = [_bool_attr(point, "Arc") for point in point_elements]
            trace_bbox = BBox.from_points(points) if points else None
            if trace_bbox is not None and width_values:
                trace_bbox = trace_bbox.expand(max(width_values) / 2.0)
            trace_record = ObjectRecord(
                stable_id=trace_stable,
                kind="trace",
                label=f"{name or xml_id}:trace-{trace_xml_id or trace_index}",
                xml_id=trace_xml_id or None,
                parent_id=stable,
                net_id=xml_id or None,
                net_name=name or None,
                layer=_trace_layer(trace),
                selected=_bool_attr(trace, "Selected"),
                bbox=_bbox_dict(trace_bbox),
                geometry_source="xml-trace-points" if points else "xml-structure",
                confidence=1.0 if points else 0.3,
                attributes={
                    **dict(trace.attrib),
                    "points": [point.as_dict() for point in points],
                    "segment_widths_mm": widths,
                    "segment_layers": segment_layers,
                    "point_arc_middle": arc_middle,
                    "point_via_styles": [point.get("ViaStyle", "-1") for point in point_elements],
                    "length_mm": trace_path_length(points, arc_middle),
                },
                relationships={"net": [stable], "vias": []},
            )
            records.append(trace_record)
            for point_index, point_element in enumerate(point_elements):
                via_style = point_element.get("ViaStyle", "-1")
                if not _trace_point_is_physical_via(point_elements, point_index):
                    continue
                point = points[point_index]
                via_stable = stable_id(
                    "via",
                    document.source_type,
                    trace_stable,
                    point_element.get("Id", str(point_index)),
                )
                via_ids.append(via_stable)
                trace_record.relationships["vias"].append(via_stable)
                style = via_styles.get(via_style)
                diameter = style.diameter_mm if style is not None else None
                hole = style.hole_mm if style is not None else None
                records.append(
                    ObjectRecord(
                        stable_id=via_stable,
                        kind="via",
                        label=f"{name or xml_id}:via-{point_index}",
                        xml_id=point_element.get("Id"),
                        parent_id=trace_stable,
                        net_id=xml_id or None,
                        net_name=name or None,
                        layer=(
                            f"{style.layer_start_id}:{style.layer_end_id}"
                            if style is not None and style.span_source == "explicit"
                            else "multilayer"
                        ),
                        selected=_bool_attr(point_element, "Selected"),
                        position=point.as_dict(),
                        bbox=point_bbox(point, (diameter or 0.0) / 2.0).as_dict(),
                        geometry=(
                            GeometryShape(
                                kind="circle",
                                center=point.as_dict(),
                                width=diameter,
                                height=diameter,
                            )
                            if diameter is not None and diameter > 0.0
                            else None
                        ),
                        geometry_source="xml-trace-point",
                        confidence=0.8,
                        attributes={
                            "representation": "trace_layer_transition",
                            "via_style": via_style,
                            "diameter_mm": diameter,
                            "hole_mm": hole,
                            "layer_start_id": (
                                style.layer_start_id if style is not None else None
                            ),
                            "layer_end_id": (
                                style.layer_end_id if style is not None else None
                            ),
                            "span_layer_ids": (
                                style.span_layer_ids if style is not None else []
                            ),
                            "span_source": (
                                style.span_source if style is not None else "invalid"
                            ),
                            **dict(point_element.attrib),
                        },
                        relationships={"net": [stable], "trace": [trace_stable]},
                    )
                )
        records.append(
            ObjectRecord(
                stable_id=stable,
                kind="net",
                label=name or xml_id or stable,
                name=name or None,
                xml_id=xml_id or None,
                net_id=xml_id or None,
                net_name=name or None,
                locked=_bool_attr(net, "Locked"),
                selected=_bool_attr(net, "Selected"),
                attributes={
                    "net_class": net.get("NetClass", ""),
                    "enabled": net.get("Enabled", "Y"),
                    "endpoint_count": len(endpoints),
                    "trace_count": len(trace_ids),
                    "wire_count": len(net.findall("./Wires/Wire")),
                },
                relationships={
                    "endpoints": endpoints,
                    "traces": trace_ids,
                    "vias": via_ids,
                },
                geometry_source="topology",
                confidence=1.0,
            )
        )
    return records


def _static_via_records(
    document: DipTraceDocument,
    normalized_via_styles: list[ViaStyleModel],
    net_records: list[ObjectRecord],
) -> list[ObjectRecord]:
    """Normalize standalone DipTrace ``Component Type=\"Via\"`` objects.

    DipTrace stores routed layer transitions on trace points, but standalone/static
    vias live in the component table.  They are physical vias even though they are
    not associated with a trace layer transition.
    """
    if document.kind != "pcb":
        return []
    nets_by_xml = {
        item.xml_id: item for item in net_records if item.kind == "net" and item.xml_id
    }
    styles_by_id = {style.id: style for style in normalized_via_styles}
    records: list[ObjectRecord] = []
    for component in document.container.findall("./Components/Component"):
        if component.get("Type") != "Via":
            continue
        xml_id = component.get("Id", "")
        refdes = _text(component, "RefDes")
        pads = component.findall("./Pads/Pad")
        net_ids = {
            pad.get("NetId", "")
            for pad in pads
            if pad.get("NetId") not in {None, "", "-1"}
        }
        net_id = next(iter(net_ids)) if len(net_ids) == 1 else None
        net = nets_by_xml.get(net_id) if net_id is not None else None
        style_id = component.get("ViaStyle", "-1")
        style = styles_by_id.get(style_id)
        diameter = style.diameter_mm if style is not None else None
        hole = style.hole_mm if style is not None else None
        x = _float_attr_mm(document, component, "X")
        y = _float_attr_mm(document, component, "Y")
        position = Point(x, y) if x is not None and y is not None else None
        via_stable = stable_id(
            "via",
            document.source_type,
            "static-component",
            *_xml_identity(xml_id, refdes),
        )
        warnings = []
        if len(net_ids) > 1:
            warnings.append("Static via pads reference more than one net.")
        record = ObjectRecord(
            stable_id=via_stable,
            kind="via",
            label=refdes or f"static-via-{xml_id}",
            refdes=refdes or None,
            xml_id=xml_id or None,
            net_id=net_id,
            net_name=net.name if net is not None else None,
            layer=(
                f"{style.layer_start_id}:{style.layer_end_id}"
                if style is not None and style.span_source == "explicit"
                else "multilayer"
            ),
            locked=_bool_attr(component, "Locked"),
            selected=_bool_attr(component, "Selected"),
            position=position.as_dict() if position is not None else None,
            bbox=(
                point_bbox(position, (diameter or 0.0) / 2.0).as_dict()
                if position is not None
                else None
            ),
            geometry=(
                GeometryShape(
                    kind="circle",
                    center=position.as_dict(),
                    width=diameter,
                    height=diameter,
                )
                if position is not None and diameter is not None and diameter > 0.0
                else None
            ),
            geometry_source="xml-static-via-component",
            confidence=1.0,
            attributes={
                "representation": "static_component",
                "via_style": style_id,
                "diameter_mm": diameter,
                "hole_mm": hole,
                "layer_start_id": style.layer_start_id if style is not None else None,
                "layer_end_id": style.layer_end_id if style is not None else None,
                "span_layer_ids": style.span_layer_ids if style is not None else [],
                "span_source": style.span_source if style is not None else "invalid",
                **dict(component.attrib),
            },
            relationships={"net": [net.stable_id] if net is not None else []},
            warnings=warnings,
        )
        records.append(record)
        if net is not None:
            net.relationships.setdefault("vias", []).append(via_stable)
    return records


def _enrich_endpoint_connectivity(records: list[ObjectRecord]) -> None:
    records_by_id = {record.stable_id: record for record in records}
    for net in records:
        if net.kind != "net":
            continue
        for endpoint_id in net.relationships.get("endpoints", []):
            endpoint = records_by_id.get(endpoint_id)
            if endpoint is None:
                continue
            endpoint.net_id = net.xml_id
            endpoint.net_name = net.name
            endpoint.relationships.setdefault("net", []).append(net.stable_id)


def _trace_layer(trace: ET.Element) -> str | None:
    points = trace.findall("./Points/Point")
    for point in points[1:] or points:
        layer = point.get("Lay")
        if layer is not None:
            return layer
    return trace.get("Layer")


def _trace_point_is_physical_via(points: list[ET.Element], index: int) -> bool:
    """Return true only for a styled trace point that changes the active layer.

    Real DipTrace exports may retain ``ViaStyle`` on same-layer routing points.
    Treating that metadata alone as a via creates false via counts and false
    differential-pair via-balance failures.  Segment parameters are stored on the
    second point, so the transition is from ``points[index].Lay`` to the following
    point's ``Lay``.
    """
    if index <= 0 or index + 1 >= len(points):
        return False
    point = points[index]
    if point.get("ViaStyle", "-1") in {"", "-1"}:
        return False
    incoming_layer = point.get("Lay")
    outgoing_layer = points[index + 1].get("Lay")
    return (
        incoming_layer is not None
        and outgoing_layer is not None
        and incoming_layer != outgoing_layer
    )


def point_bbox(point: Point, radius: float) -> BBox:
    return BBox(point.x - radius, point.y - radius, point.x + radius, point.y + radius)


def _board_outline(document: DipTraceDocument) -> dict[str, Any] | None:
    if document.kind != "pcb":
        return None
    points = [
        Point(
            _float_attr_mm(document, point, "X") or 0.0,
            _float_attr_mm(document, point, "Y") or 0.0,
        )
        for point in document.container.findall("./BoardOutline/Points/Point")
    ]
    if not points:
        return None
    box = BBox.from_points(points)
    return {
        "points": [point.as_dict() for point in points],
        "bbox": box.as_dict(),
        "point_count": len(points),
    }


def _board_layers(document: DipTraceDocument) -> list[dict[str, Any]]:
    if document.kind != "pcb":
        return []
    return [
        {
            "id": layer.get("Id", ""),
            "name": _text(layer, "Name", layer.get("Name", "")),
            "type": layer.get("Type", ""),
        }
        for layer in document.container.findall("./CopperLayers/Lay")
    ]


def _board_net_classes(document: DipTraceDocument) -> list[dict[str, Any]]:
    if document.kind != "pcb":
        return []
    return [
        {"id": item.get("Id", ""), "name": _text(item, "Name"), "attributes": dict(item.attrib)}
        for item in document.container.findall("./NetClasses/NetClass")
    ]


def _board_via_styles(document: DipTraceDocument) -> list[ViaStyleModel]:
    if document.kind != "pcb":
        return []
    layer_ids = [str(item.get("id", "")) for item in _board_layers(document)]
    layer_index = {layer_id: index for index, layer_id in enumerate(layer_ids)}
    styles: list[ViaStyleModel] = []
    for item in document.container.findall("./ViaStyles/ViaStyle"):
        start = item.get("Lay1")
        end = item.get("Lay2")
        span: list[str] = []
        span_source: Literal["explicit", "unspecified", "invalid"] = "unspecified"
        if start is not None or end is not None:
            if start in layer_index and end in layer_index and start != end:
                low, high = sorted((layer_index[start], layer_index[end]))
                span = layer_ids[low : high + 1]
                span_source = "explicit"
            else:
                span_source = "invalid"
        styles.append(
            ViaStyleModel(
                id=item.get("Id", "") or "<missing>",
                name=_text(item, "Name"),
                diameter_mm=_first_float_attr_mm(
                    document, item, ("Diameter", "Size")
                ),
                hole_mm=_first_float_attr_mm(document, item, ("Hole", "HoleSize")),
                layer_start_id=start,
                layer_end_id=end,
                span_layer_ids=span,
                span_source=span_source,
                attributes=dict(item.attrib),
            )
        )
    return styles


def _board_ratlines(
    document: DipTraceDocument, owner_map: dict[str, str]
) -> list[dict[str, Any]]:
    if document.kind != "pcb":
        return []
    records: list[dict[str, Any]] = []
    for item in document.container.findall("./Ratlines/Ratline"):
        attributes = dict(item.attrib)
        endpoints: list[dict[str, Any]] = []
        for suffix in ("1", "2"):
            owner = owner_map.get(item.get(f"Comp{suffix}", ""))
            pad_id = item.get(f"Pad{suffix}", "")
            x = _float_attr_mm(document, item, f"X{suffix}")
            y = _float_attr_mm(document, item, f"Y{suffix}")
            endpoints.append(
                {
                    "component_id": owner,
                    "pad_id": (
                        _pad_stable_id(document, owner, pad_id)
                        if owner is not None and pad_id
                        else None
                    ),
                    "position": (
                        Point(x, y).as_dict() if x is not None and y is not None else None
                    ),
                }
            )
        records.append({"attributes": attributes, "endpoints": endpoints})
    return records


def _net_class_pair_rules(
    document: DipTraceDocument, net_class: ET.Element | None
) -> DifferentialPairRules:
    if net_class is None:
        return DifferentialPairRules()
    layer_rules: list[DifferentialPairLayerRules] = []
    for item in net_class.findall("./LayProperties/LayProperty"):
        layer_name = _text(item, "LayerName")
        layer_rules.append(
            DifferentialPairLayerRules(
                layer_name=layer_name,
                width_mm=_float_attr_mm(document, item, "Width"),
                min_width_mm=_float_attr_mm(document, item, "MinWidth"),
                max_width_mm=_float_attr_mm(document, item, "MaxWidth"),
                clearance_to_others_mm=_float_attr_mm(document, item, "Clearance"),
                gap_mm=_float_attr_mm(document, item, "DifClearance"),
                neck_width_mm=_float_attr_mm(document, item, "Neck_Width"),
                neck_gap_mm=_float_attr_mm(document, item, "Neck_DifClearance"),
                max_neck_length_mm=_float_attr_mm(document, item, "Neck_MaxLength"),
            )
        )
    return DifferentialPairRules(
        max_uncoupled_length_mm=_float_attr_mm(document, net_class, "MaxUncoupledLength"),
        length_tolerance_mm=_float_attr_mm(document, net_class, "Tolerance"),
        phase_tolerance=_float_attr(net_class, "Phase"),
        phase_error_length_mm=_float_attr_mm(document, net_class, "Phase_ErrorLength"),
        check_length=_bool_attr(net_class, "CheckLength"),
        fixed_length_mm=_float_attr_mm(document, net_class, "FixedLength"),
        length_delta_mm=_float_attr_mm(document, net_class, "LengthDelta"),
        layer_rules=layer_rules,
    )


def _differential_center_point(
    document: DipTraceDocument, item: ET.Element
) -> dict[str, Any]:
    point: dict[str, Any] = {
        "position": {
            "x": _float_attr_mm(document, item, "X") or 0.0,
            "y": _float_attr_mm(document, item, "Y") or 0.0,
        },
        "layer_id": item.get("Lay"),
        "via_style_id": item.get("ViaStyle"),
        "type": item.get("Type", ""),
        "necked": _bool_attr(item, "Necked"),
        "phase_error": _bool_attr(item, "PhaseError"),
        "positive_offsets": [],
        "negative_offsets": [],
    }
    for key, path in (
        ("positive_offsets", "./PosPoints/PosPoint"),
        ("negative_offsets", "./NegPoints/NegPoint"),
    ):
        point[key] = [
            {
                "x": _float_attr_mm(document, child, "X") or 0.0,
                "y": _float_attr_mm(document, child, "Y") or 0.0,
                "layer_id": child.get("Lay"),
                "via_style_id": child.get("ViaStyle"),
                "necked": _bool_attr(child, "Necked"),
                "arc": _bool_attr(child, "Arc"),
            }
            for child in item.findall(path)
        ]
    return point


def _board_differential_pairs(
    document: DipTraceDocument, owner_map: dict[str, str]
) -> list[DifferentialPairModel]:
    if document.kind != "pcb":
        return []
    nets_by_xml: dict[str, tuple[str, str]] = {}
    for net_element in document.container.findall("./Nets/Net"):
        xml_id = net_element.get("Id", "")
        name = _text(net_element, "Name")
        nets_by_xml[xml_id] = (
            stable_id("net", document.source_type, *_xml_identity(xml_id, name)),
            name,
        )
    classes_by_xml = {
        item.get("Id", ""): item
        for item in document.container.findall("./NetClasses/NetClass")
    }
    result: list[DifferentialPairModel] = []
    for index, item in enumerate(
        document.container.findall("./DifferentialPairs/DifferentialPair")
    ):
        xml_id = item.get("Id", "")
        name = _text(item, "Name", f"pair-{xml_id or index}")
        positive_xml = item.get("PosNet", "")
        negative_xml = item.get("NegNet", "")
        positive = nets_by_xml.get(positive_xml)
        negative = nets_by_xml.get(negative_xml)
        class_id = item.get("NetClass", "")
        net_class = classes_by_xml.get(class_id)
        warnings: list[str] = []
        if positive is None:
            warnings.append(f"Positive net id {positive_xml!r} is not present in Nets")
        if negative is None:
            warnings.append(f"Negative net id {negative_xml!r} is not present in Nets")
        pad_pairs: list[DifferentialPairPadPair] = []
        for pad_pair in item.findall("./PadPoints/PadPoint"):
            positive_owner = owner_map.get(pad_pair.get("PosComp", ""))
            negative_owner = owner_map.get(pad_pair.get("NegComp", ""))
            positive_pad_xml = pad_pair.get("PosPad", "")
            negative_pad_xml = pad_pair.get("NegPad", "")
            pad_pairs.append(
                DifferentialPairPadPair(
                    xml_id=pad_pair.get("Id"),
                    positive_component_id=positive_owner,
                    positive_pad_id=(
                        _pad_stable_id(document, positive_owner, positive_pad_xml)
                        if positive_owner is not None and positive_pad_xml
                        else None
                    ),
                    negative_component_id=negative_owner,
                    negative_pad_id=(
                        _pad_stable_id(document, negative_owner, negative_pad_xml)
                        if negative_owner is not None and negative_pad_xml
                        else None
                    ),
                )
            )
        segments = [
            DifferentialPairSegment(
                index=segment_index,
                positive_trace_xml_id=segment.get("PosTrace"),
                negative_trace_xml_id=segment.get("NegTrace"),
                center_points=[
                    _differential_center_point(document, point)
                    for point in segment.findall("./CenterPoints/CenterPoint")
                ],
                attributes=dict(segment.attrib),
            )
            for segment_index, segment in enumerate(item.findall("./Segments/Segment"))
        ]
        result.append(
            DifferentialPairModel(
                stable_id=stable_id(
                    "differential-pair",
                    document.source_type,
                    *_xml_identity(xml_id, name, str(index)),
                ),
                xml_id=xml_id or None,
                name=name,
                positive_net_id=positive[0] if positive else None,
                positive_net_xml_id=positive_xml or None,
                positive_net_name=positive[1] if positive else None,
                negative_net_id=negative[0] if negative else None,
                negative_net_xml_id=negative_xml or None,
                negative_net_name=negative[1] if negative else None,
                net_class_id=class_id or None,
                net_class_name=_text(net_class, "Name") if net_class is not None else None,
                route_mode=item.get("RouteMode", ""),
                auto_pad_points=_bool_attr(item, "AutoPadPoints"),
                pad_pairs=pad_pairs,
                segments=segments,
                rules=_net_class_pair_rules(document, net_class),
                attributes=dict(item.attrib),
                warnings=warnings,
            )
        )
    return result


def _board_stackup(document: DipTraceDocument) -> StackupModel:
    if document.kind != "pcb":
        return StackupModel()
    container = document.container.find("./LayerStackItems")
    if container is None:
        return StackupModel(
            name=_text(document.container, "LayerStackName"),
            missing_fields=["LayerStackItems"],
            warnings=["The PCB XML does not contain a physical layer stack."],
        )
    copper_layers = {
        layer.get("Id", ""): _text(layer, "Name", layer.get("Name", ""))
        for layer in document.container.findall("./CopperLayers/Lay")
    }
    layers: list[StackupLayer] = []
    warnings: list[str] = []
    missing: list[str] = []
    for index, stack_item in enumerate(container.findall("./LayerStackItem")):
        layer_id = stack_item.get("Lay")
        material = stack_item.find("./Material")
        if material is None:
            missing.append(f"layers[{index}].material")
            continue
        raw_type = material.get("Type", "").casefold()
        material_type: Literal["conductor", "plane", "dielectric", "unknown"]
        if raw_type == "conductor":
            material_type = "conductor"
        elif raw_type == "plane":
            material_type = "plane"
        elif raw_type == "dielectric":
            material_type = "dielectric"
        else:
            material_type = "unknown"
        constant = _float_attr(material, "Constant")
        dielectric_constant = (
            constant
            if material_type == "dielectric" and constant is not None and constant > 1.0
            else None
        )
        thickness = _float_attr_mm(document, material, "Thickness")
        if thickness is None or thickness <= 0:
            missing.append(f"layers[{index}].thickness_mm")
            thickness = None
        if material_type == "dielectric" and dielectric_constant is None:
            missing.append(f"layers[{index}].dielectric_constant")
        if material_type == "unknown":
            warnings.append(
                f"Layer stack item {index} has unsupported material type "
                f"{material.get('Type', '')!r}."
            )
        trace_width = _float_attr_mm(document, material, "TraceWidth")
        if trace_width is not None and trace_width <= 0:
            trace_width = None
        layers.append(
            StackupLayer(
                index=index,
                layer_id=layer_id,
                layer_name=copper_layers.get(layer_id or ""),
                material=StackupMaterial(
                    material_type=material_type,
                    name=_text(material, "Name"),
                    variable_thickness=_bool_attr(material, "VariableThickness"),
                    thickness_mm=thickness,
                    dielectric_constant=dielectric_constant,
                    material_constant_raw=constant,
                    trace_width_mm=trace_width,
                    attributes=dict(material.attrib),
                ),
            )
        )
    total = sum(
        layer.material.thickness_mm or 0.0
        for layer in layers
    )
    has_conductor = any(
        layer.material.material_type in {"conductor", "plane"} for layer in layers
    )
    has_dielectric = any(
        layer.material.material_type == "dielectric" for layer in layers
    )
    if not has_conductor:
        missing.append("conductor_or_plane_layer")
    if not has_dielectric:
        missing.append("dielectric_layer")
    completeness: Literal["complete", "partial", "missing"] = (
        "complete" if layers and not missing else "partial"
    )
    return StackupModel(
        name=_text(document.container, "LayerStackName"),
        source="LayerStackItems",
        layers=layers,
        total_thickness_mm=total or None,
        completeness=completeness,
        missing_fields=sorted(set(missing)),
        warnings=warnings,
    )


def _board_copper_pour_records(document: DipTraceDocument) -> list[ObjectRecord]:
    if document.kind != "pcb":
        return []
    net_lookup: dict[str, tuple[str, str]] = {}
    for net in document.container.findall("./Nets/Net"):
        xml_id = net.get("Id", "")
        name = _text(net, "Name")
        net_lookup[xml_id] = (
            stable_id("net", document.source_type, *_xml_identity(xml_id, name)),
            name,
        )
    records: list[ObjectRecord] = []
    for index, pour in enumerate(document.container.findall("./CopperPours/CopperPour")):
        xml_id = pour.get("Id", "")
        net_xml_id = pour.get("NetId", "")
        connected_net = net_lookup.get(net_xml_id)
        points = [
            Point(
                _float_attr_mm(document, point, "X") or 0.0,
                _float_attr_mm(document, point, "Y") or 0.0,
            )
            for point in pour.findall("./Points/Point")
        ]
        records.append(
            ObjectRecord(
                stable_id=stable_id(
                    "copper-pour",
                    document.source_type,
                    *_xml_identity(xml_id, str(index)),
                ),
                kind="copper_pour",
                label=(
                    f"{connected_net[1] if connected_net else 'unassigned'}:"
                    f"pour-{xml_id or index}"
                ),
                xml_id=xml_id or None,
                net_id=net_xml_id if connected_net is not None else None,
                net_name=connected_net[1] if connected_net is not None else None,
                layer=pour.get("Lay"),
                locked=_bool_attr(pour, "Locked"),
                selected=_bool_attr(pour, "Selected"),
                bbox=BBox.from_points(points).as_dict() if points else None,
                geometry_source="xml-copper-pour-boundary",
                confidence=0.8 if points else 0.3,
                attributes={
                    **dict(pour.attrib),
                    "points": [point.as_dict() for point in points],
                    "poured": _bool_attr(pour, "Poured"),
                    "regions_done": _bool_attr(pour, "RegionsDone"),
                    "clearance_mm": _float_attr_mm(document, pour, "Clearance"),
                    "board_clearance_mm": _float_attr_mm(
                        document, pour, "BoardClearance"
                    ),
                    "minimum_area_mm2": (
                        to_mm(1.0, document.units) ** 2
                        * (_float_attr(pour, "MinimumArea") or 0.0)
                    ),
                },
                relationships={
                    "net": [connected_net[0]] if connected_net is not None else []
                },
                warnings=[
                    "Boundary geometry is not the final refilled copper region."
                ],
            )
        )
    return records


def _board_shape_records(document: DipTraceDocument) -> list[ObjectRecord]:
    if document.kind != "pcb":
        return []
    records: list[ObjectRecord] = []
    for index, shape in enumerate(document.container.findall("./Shapes/Shape")):
        xml_id = shape.get("Id", "")
        shape_type = shape.get("Type", "")
        layer = shape.get("Layer", "")
        points = [
            Point(
                _float_attr_mm(document, point, "X") or 0.0,
                _float_attr_mm(document, point, "Y") or 0.0,
            )
            for point in shape.findall("./Points/*")
        ]
        if shape_type == "Text":
            lines = [item.text or "" for item in shape.findall("./Lines/Item")]
            text_value = "\n".join(lines)
            position = points[0] if points else None
            width = max(1.0, max((len(line) for line in lines), default=1) * 0.6)
            bbox = (
                _bbox_from_center(position.x, position.y, width, max(1.0, len(lines)))
                if position
                else None
            )
            records.append(
                ObjectRecord(
                    stable_id=stable_id(
                        "board-text",
                        document.source_type,
                        *_xml_identity(xml_id, str(index), text_value),
                    ),
                    kind="board_text",
                    label=text_value or f"text-{xml_id or index}",
                    value=text_value,
                    xml_id=xml_id or None,
                    layer=layer or None,
                    side=_side_from_layer(layer),
                    locked=_bool_attr(shape, "Locked"),
                    selected=_bool_attr(shape, "Selected"),
                    position=_point_dict(position),
                    bbox=_bbox_dict(bbox),
                    rotation_deg=math.degrees(_float_attr(shape, "Angle") or 0.0),
                    mirrored=_bool_attr(shape, "Inverted"),
                    geometry_source="xml-board-shape",
                    confidence=0.65,
                    attributes={**dict(shape.attrib), "lines": lines},
                )
            )
            continue
        if layer in {"Route Keepout", "Placement Keepout"}:
            box = BBox.from_points(points) if points else None
            records.append(
                ObjectRecord(
                    stable_id=stable_id(
                        "keepout",
                        document.source_type,
                        *_xml_identity(xml_id, str(index)),
                    ),
                    kind="keepout",
                    label=f"{layer}-{xml_id or index}",
                    xml_id=xml_id or None,
                    layer=layer,
                    locked=_bool_attr(shape, "Locked"),
                    selected=_bool_attr(shape, "Selected"),
                    bbox=_bbox_dict(box),
                    geometry_source="xml-board-shape",
                    confidence=1.0 if points else 0.3,
                    attributes={
                        **dict(shape.attrib),
                        "points": [point.as_dict() for point in points],
                    },
                )
            )
    return records


def _side_from_layer(layer: str) -> str | None:
    if layer.startswith("Top"):
        return "Top"
    if layer.startswith("Bottom"):
        return "Bottom"
    return None


def _schematic_sheets(document: DipTraceDocument) -> list[dict[str, Any]]:
    if document.kind != "schematic":
        return []
    return [
        {
            "id": _text(sheet, "Id"),
            "name": _text(sheet, "Name"),
            "type": _text(sheet, "Type"),
        }
        for sheet in document.container.findall("./SheetSettings/Sheets/Sheet")
    ]


def _schematic_erc(document: DipTraceDocument) -> dict[str, Any]:
    if document.kind != "schematic":
        return {}
    erc = document.container.find("./ERC")
    if erc is None:
        return {}
    return {
        "attributes": dict(erc.attrib),
        "vcctemplate": _text(erc, "VCCTemplate"),
        "gndtemplate": _text(erc, "GNDTemplate"),
    }


def _schematic_buses(document: DipTraceDocument) -> list[dict[str, Any]]:
    if document.kind != "schematic":
        return []
    return [
        {
            "id": item.get("Id", ""),
            "enabled": item.get("Enabled", "Y"),
            "locked": item.get("Locked", "N"),
            "attributes": dict(item.attrib),
        }
        for item in document.container.findall("./Buses/Bus")
    ]


def _schematic_differential_pairs(document: DipTraceDocument) -> list[dict[str, Any]]:
    if document.kind != "schematic":
        return []
    return [
        {"attributes": dict(item.attrib), "name": _text(item, "Name")}
        for item in document.container.findall("./DifferentialPairs/DifferentialPair")
    ]


@dataclass(slots=True)
class DocumentSnapshot:
    document: DipTraceDocument
    info: DocumentInfo
    objects: dict[str, ObjectRecord]
    elements: dict[str, ET.Element]
    board: BoardModel | None
    schematic: SchematicModel | None
    warnings: list[str]

    def get_object(self, stable_id_value: str) -> ObjectRecord:
        try:
            return self.objects[stable_id_value]
        except KeyError as exc:
            raise DocumentError(f"Object not found: {stable_id_value}") from exc

    def query(self, request: QueryRequest) -> QueryResult:
        items = [
            item
            for item in self.objects.values()
            if _matches_selector(item, request.selector)
        ]
        items.sort(
            key=lambda item: (
                getattr(item, request.sort_by, None) is None,
                str(getattr(item, request.sort_by, item.stable_id) or "").casefold(),
                item.stable_id,
            )
        )
        total = len(items)
        offset = max(0, request.offset)
        limit = max(1, request.limit)
        return QueryResult(
            document_id=self.info.document_id,
            total=total,
            offset=offset,
            limit=limit,
            items=items[offset : offset + limit],
        )

    def select(self, selector: QuerySelector, *, kinds: set[str]) -> list[ObjectRecord]:
        return [
            item
            for item in self.objects.values()
            if item.kind in kinds and _matches_selector(item, selector)
        ]


def _matches_selector(item: ObjectRecord, selector: QuerySelector) -> bool:
    if selector.ids and item.stable_id not in selector.ids:
        return False
    if selector.kinds and item.kind not in selector.kinds:
        return False
    if selector.refdes:
        refdes = item.refdes or ""
        if not any(refdes.casefold() == candidate.casefold() for candidate in selector.refdes):
            return False
    if selector.refdes_glob and not fnmatchcase(
        (item.refdes or "").casefold(), selector.refdes_glob.casefold()
    ):
        return False
    if selector.refdes_regex and not re.search(selector.refdes_regex, item.refdes or ""):
        return False
    if selector.names:
        name = item.name or ""
        if not any(name.casefold() == candidate.casefold() for candidate in selector.names):
            return False
    if selector.name_regex and not re.search(selector.name_regex, item.name or ""):
        return False
    if selector.values:
        value = item.value or ""
        if not any(value.casefold() == candidate.casefold() for candidate in selector.values):
            return False
    if selector.fields:
        item_fields = item.attributes.get("additional_fields", {})
        if not isinstance(item_fields, dict):
            return False
        if any(
            str(item_fields.get(key, "")) != expected
            for key, expected in selector.fields.items()
        ):
            return False
    if selector.nets:
        names = {item.net_name or "", item.net_id or ""}
        if not any(candidate in names for candidate in selector.nets) and not any(
            candidate.casefold() == net.casefold()
            for candidate in selector.nets
            for net in names
            if net
        ):
            return False
    if selector.layers and (item.layer or "") not in selector.layers:
        return False
    if selector.sides and (item.side or "") not in selector.sides:
        return False
    if selector.selected is not None and item.selected != selector.selected:
        return False
    if selector.locked is not None and item.locked != selector.locked:
        return False
    if selector.text:
        needle = selector.text.casefold()
        haystack = " ".join(
            [
                item.label or "",
                item.name or "",
                item.value or "",
                item.refdes or "",
                item.net_name or "",
                " ".join(f"{key}={value}" for key, value in item.attributes.items()),
            ]
        ).casefold()
        if needle not in haystack:
            return False
    if selector.bbox:
        if item.bbox is None:
            return False
        bbox = BBox(
            selector.bbox["min_x"],
            selector.bbox["min_y"],
            selector.bbox["max_x"],
            selector.bbox["max_y"],
        )
        item_bbox = BBox(
            item.bbox["min_x"],
            item.bbox["min_y"],
            item.bbox["max_x"],
            item.bbox["max_y"],
        )
        if not bbox.intersects(item_bbox):
            return False
    if selector.near is not None:
        if item.position is None:
            return False
        target = Point(selector.near["x"], selector.near["y"])
        item_point = Point(item.position["x"], item.position["y"])
        if (
            selector.max_distance is not None
            and distance(item_point, target) > selector.max_distance
        ):
            return False
    return True


def build_snapshot(document: DipTraceDocument, *, live_session: bool = False) -> DocumentSnapshot:
    document_id = document_id_for(document)
    warnings: list[str] = []
    pattern_model = None
    if document.kind == "pcb":
        from .library_adapters import get_embedded_pattern_model

        pattern_model = get_embedded_pattern_model(document)
    via_styles = _board_via_styles(document)
    component_records, component_map, component_refdes_map = _component_records(document)
    net_records = _net_records(document, component_map, via_styles)
    static_via_records = _static_via_records(document, via_styles, net_records)
    _enrich_endpoint_connectivity([*component_records, *net_records, *static_via_records])
    shape_records = _board_shape_records(document)
    pour_records = _board_copper_pour_records(document)
    objects: dict[str, ObjectRecord] = {}
    elements: dict[str, ET.Element] = {}
    for record in (
        component_records + net_records + static_via_records + shape_records + pour_records
    ):
        objects[record.stable_id] = record
    # Populate XML element mapping after the object tables are built so callers can resolve edits.
    if document.kind == "pcb":
        static_vias_by_xml = {
            record.xml_id: record.stable_id
            for record in static_via_records
            if record.xml_id is not None
        }
        for component in document.container.findall("./Components/Component"):
            xml_id = component.get("Id", "")
            refdes = _text(component, "RefDes")
            stable = component_map.get(xml_id) or component_refdes_map.get(
                refdes.casefold() if refdes else ""
            )
            if stable:
                elements[stable] = component
                for pad in component.findall("./Pads/Pad"):
                    pad_id = pad.get("Id", "")
                    pad_number = pad.get("Number", pad_id)
                    pad_stable = _pad_stable_id(document, stable, pad_id or pad_number)
                    elements[pad_stable] = pad
                for marking_tag, _value_source in _MARKING_TAGS:
                    marking = component.find(f"./{marking_tag}")
                    if marking is None:
                        continue
                    for surface in ("Silk", "Assy"):
                        settings = marking.find(f"./{surface}")
                        if settings is not None:
                            text_stable = _marking_stable_id(
                                document,
                                stable,
                                marking_tag,
                                surface,
                            )
                            elements[text_stable] = settings
            static_via_stable = static_vias_by_xml.get(xml_id)
            if static_via_stable is not None:
                elements[static_via_stable] = component
        for net in document.container.findall("./Nets/Net"):
            net_xml_id = net.get("Id", "")
            net_name = _text(net, "Name")
            net_stable = stable_id(
                "net",
                document.source_type,
                *_xml_identity(net_xml_id, net_name),
            )
            elements[net_stable] = net
            for trace_index, trace in enumerate(net.findall("./Traces/Trace")):
                trace_stable = stable_id(
                    "trace",
                    document.source_type,
                    net_stable,
                    *_xml_identity(trace.get("Id", ""), str(trace_index)),
                )
                elements[trace_stable] = trace
                point_elements = trace.findall("./Points/Point")
                for point_index, point in enumerate(point_elements):
                    if not _trace_point_is_physical_via(point_elements, point_index):
                        continue
                    via_stable = stable_id(
                        "via",
                        document.source_type,
                        trace_stable,
                        point.get("Id", str(point_index)),
                    )
                    elements[via_stable] = point
        for index, shape in enumerate(document.container.findall("./Shapes/Shape")):
            xml_id = shape.get("Id", "")
            shape_type = shape.get("Type", "")
            layer = shape.get("Layer", "")
            if shape_type == "Text":
                lines = [item.text or "" for item in shape.findall("./Lines/Item")]
                shape_stable = stable_id(
                    "board-text",
                    document.source_type,
                    *_xml_identity(xml_id, str(index), "\n".join(lines)),
                )
                elements[shape_stable] = shape
            elif layer in {"Route Keepout", "Placement Keepout"}:
                shape_stable = stable_id(
                    "keepout",
                    document.source_type,
                    *_xml_identity(xml_id, str(index)),
                )
                elements[shape_stable] = shape
        for index, pour in enumerate(
            document.container.findall("./CopperPours/CopperPour")
        ):
            pour_stable = stable_id(
                "copper-pour",
                document.source_type,
                *_xml_identity(pour.get("Id", ""), str(index)),
            )
            elements[pour_stable] = pour
        board = BoardModel(
            document_id=document_id,
            outline=_board_outline(document),
            components=[
                record
                for record in component_records
                if record.kind == "component" and record.attributes.get("type") != "Via"
            ],
            pads=[
                record
                for record in component_records
                if record.kind == "pad"
                and objects.get(record.parent_id or "") is not None
                and objects[record.parent_id or ""].attributes.get("type") != "Via"
            ],
            holes=[record for record in component_records if record.kind == "hole"],
            nets=[record for record in net_records if record.kind == "net"],
            traces=[record for record in net_records if record.kind == "trace"],
            vias=[record for record in net_records if record.kind == "via"]
            + static_via_records,
            copper_pours=pour_records,
            keepouts=[record for record in shape_records if record.kind == "keepout"],
            layers=_board_layers(document),
            patterns=pattern_model.patterns if pattern_model is not None else [],
            pad_styles=pattern_model.pad_styles if pattern_model is not None else [],
            via_styles=via_styles,
            net_classes=_board_net_classes(document),
            differential_pairs=_board_differential_pairs(document, component_map),
            ratlines=_board_ratlines(document, component_map),
            texts=[
                record
                for record in component_records + shape_records
                if record.kind in {"component_text", "board_text"}
            ],
            testpoints=[record for record in component_records if record.kind == "testpoint"],
            rules={
                "drc": _element_data(document.container.find("./DRC")),
                "connectivity_check": _element_data(document.container.find("./ConnectivityCheck")),
                "routing_defaults": _element_data(document.container.find("./Settings/Routing")),
            },
            stackup=_board_stackup(document),
            warnings=warnings,
        )
        schematic = None
    elif document.kind == "schematic":
        for part in document.container.findall("./Components/Part"):
            xml_id = part.get("Id", "")
            refdes = _text(part, "RefDes")
            stable = component_map.get(xml_id) or component_refdes_map.get(
                refdes.casefold() if refdes else ""
            )
            if stable:
                elements[stable] = part
                for pin_index, pin in enumerate(part.findall("./Pins/Pin")):
                    pin_id = f"{xml_id}:{pin_index}"
                    pin_stable = _pin_stable_id(document, stable, pin_id)
                    elements[pin_stable] = pin
        wire_records: list[ObjectRecord] = []
        for net in document.container.findall("./Nets/Net"):
            net_xml_id = net.get("Id", "")
            net_name = _text(net, "Name")
            net_stable = stable_id(
                "net",
                document.source_type,
                *_xml_identity(net_xml_id, net_name),
            )
            elements[net_stable] = net
            for wire_index, wire in enumerate(net.findall("./Wires/Wire")):
                wire_stable = stable_id(
                    "wire",
                    document.source_type,
                    net_stable,
                    *_xml_identity(wire.get("Id", ""), str(wire_index)),
                )
                elements[wire_stable] = wire
                wire_points = [
                    Point(
                        _float_attr_mm(document, point, "X") or 0.0,
                        _float_attr_mm(document, point, "Y") or 0.0,
                    )
                    for point in wire.findall("./Points/Point")
                ]
                wire_records.append(
                    ObjectRecord(
                        stable_id=wire_stable,
                        kind="wire",
                        label=f"{net_name or net_xml_id} wire {wire.get('Id', str(wire_index))}",
                        xml_id=wire.get("Id") or None,
                        net_id=net_xml_id or None,
                        net_name=net_name or None,
                        locked=_bool_attr(wire, "Locked"),
                        selected=_bool_attr(wire, "Selected"),
                        bbox=(
                            BBox.from_points(wire_points).as_dict() if wire_points else None
                        ),
                        attributes={
                            "sheet": wire.get("Sheet", ""),
                            "point_count": len(wire_points),
                            **dict(wire.attrib),
                        },
                        relationships={"net": [net_stable]},
                        geometry_source="xml-wire-points",
                        confidence=1.0,
                    )
                )
        objects.update({record.stable_id: record for record in wire_records})
        board = None
        schematic = SchematicModel(
            document_id=document_id,
            sheets=_schematic_sheets(document),
            parts=[record for record in component_records if record.kind == "part"],
            pins=[record for record in component_records if record.kind == "pin"],
            nets=[record for record in net_records if record.kind == "net"],
            wires=wire_records,
            buses=_schematic_buses(document),
            differential_pairs=_schematic_differential_pairs(document),
            erc=_schematic_erc(document),
            warnings=warnings,
        )
    else:
        board = None
        schematic = None

    info = DocumentInfo(
        document_id=document_id,
        source_type=document.source_type,
        kind=document.kind,
        version=document.version,
        units=document.units,
        path=str(document.path),
        live_session=live_session,
        size_bytes=len(document.raw_bytes),
        sha256=document.sha256,
        parse_warnings=warnings,
        compatibility=_compatibility_for(document),
    )
    return DocumentSnapshot(
        document=document,
        info=info,
        objects=objects,
        elements=elements,
        board=board,
        schematic=schematic,
        warnings=warnings,
    )


def _compatibility_for(document: DipTraceDocument) -> dict[str, Any]:
    format_context = {
        "format_version": document.version or None,
        "version_policy": "feature_detection_with_unknown_field_preservation",
        "default_omission_tolerant": True,
        "unknown_fields_preserved": True,
    }
    if document.kind == "pcb":
        return {
            **format_context,
            "detected_features": {
                "explicit_via_style_spans": any(
                    item.get("Lay1") is not None and item.get("Lay2") is not None
                    for item in document.container.findall("./ViaStyles/ViaStyle")
                ),
                "documented_via_size_fields": any(
                    item.get("Size") is not None or item.get("HoleSize") is not None
                    for item in document.container.findall("./ViaStyles/ViaStyle")
                ),
                "observed_via_size_aliases": any(
                    item.get("Diameter") is not None or item.get("Hole") is not None
                    for item in document.container.findall("./ViaStyles/ViaStyle")
                ),
            },
            "readable_objects": [
                "board_outline",
                "components",
                "pads",
                "holes",
                "nets",
                "ratlines",
                "traces",
                "vias",
                "copper_pour_boundaries",
                "keepouts",
                "texts",
                "testpoints",
                "layers",
                "physical_stackup",
                "net_classes",
                "via_styles",
                "differential_pairs",
                "rules",
            ],
            "writable_objects": [
                "component_value",
                "component_position",
                "component_rotation_side_lock_properties_pattern_groups",
                "board_text_position_rotation_visibility_style",
                "net_name_and_net_class_rules",
                "testpoints",
                "traces_and_vias",
                "panelization",
                "xml_edits",
            ],
            "limitations": [
                "geometry is estimated when footprint dimensions are unavailable",
                "copper pour geometry is a boundary, not authoritative refill",
                "routing is bounded multi-layer 45-degree without push-and-shove",
            ],
            "roundtrip": "partial",
        }
    if document.kind in {"component_library", "pattern_library"}:
        return {
            **format_context,
            "readable_objects": [
                "library_metadata",
                "components",
                "parts",
                "pins",
                "attached_patterns",
                "pad_styles",
                "patterns",
                "pads",
                "holes",
                "shapes",
                "models_3d",
            ],
            "writable_objects": ["xml_edits"],
            "limitations": [
                "typed library creation and editing are not implemented",
                "semantic coverage follows the official 4.3 XML specification",
            ],
            "roundtrip": "read-and-preserve-unknown",
        }
    if document.kind == "schematic":
        return {
            **format_context,
            "readable_objects": [
                "sheets",
                "parts",
                "pins",
                "nets",
                "wires",
                "buses",
                "differential_pairs",
                "erc",
            ],
            "writable_objects": [
                "component_value",
                "component_position",
                "component_rotation_lock_properties",
                "pin_no_connect",
                "net_name",
                "sheets",
                "parts",
                "pin_net_connectivity",
                "wires",
                "net_labels",
                "xml_edits",
            ],
            "limitations": [
                "connectivity is limited to structures present in exported XML",
                "placed parts reference library ComponentStyle entries resolved by "
                "DipTrace on import",
            ],
            "roundtrip": "partial",
        }
    return {
        **format_context,
        "readable_objects": ["source", "top_level_sections"],
        "writable_objects": ["xml_edits"],
        "limitations": ["non-XML native formats are not parsed"],
        "roundtrip": "limited",
    }


def _element_data(element: ET.Element | None, depth: int = 3) -> Any:
    if element is None:
        return None
    result: dict[str, Any] = {"tag": element.tag, "attributes": dict(element.attrib)}
    if element.text and element.text.strip():
        result["text"] = element.text.strip()
    children = [child for child in element if isinstance(child.tag, str)]
    if children and depth > 0:
        result["children"] = [_element_data(child, depth - 1) for child in children[:200]]
        if len(children) > 200:
            result["children_truncated"] = len(children) - 200
    return result


def get_document_info(document: DipTraceDocument, *, live_session: bool = False) -> DocumentInfo:
    return build_snapshot(document, live_session=live_session).info


def get_board_model(document: DipTraceDocument, *, live_session: bool = False) -> BoardModel:
    snapshot = build_snapshot(document, live_session=live_session)
    if snapshot.board is None:
        raise DocumentError("PCB model is only available for PCB documents")
    return snapshot.board


def get_schematic_model(
    document: DipTraceDocument, *, live_session: bool = False
) -> SchematicModel:
    snapshot = build_snapshot(document, live_session=live_session)
    if snapshot.schematic is None:
        raise DocumentError("Schematic model is only available for schematic documents")
    return snapshot.schematic


def query_objects(
    document: DipTraceDocument,
    request: QueryRequest,
    *,
    live_session: bool = False,
) -> QueryResult:
    return build_snapshot(document, live_session=live_session).query(request)


def get_object(
    document: DipTraceDocument,
    stable_id_value: str,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    snapshot = build_snapshot(document, live_session=live_session)
    record = snapshot.get_object(stable_id_value)
    payload = record.model_dump()
    element = snapshot.elements.get(stable_id_value)
    payload["source_xml"] = _element_short(element) if element is not None else None
    payload["document"] = snapshot.info.model_dump()
    return payload


def summarize(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    snapshot = build_snapshot(document, live_session=live_session)
    result = snapshot.info.model_dump()
    result.update(
        {
            "kind": document.kind,
            "live_session": live_session,
            "compatibility": snapshot.info.compatibility,
        }
    )
    if snapshot.board is not None:
        net_records = [item for item in snapshot.board.nets]
        result.update(
            {
                "component_count": len(snapshot.board.components),
                "net_count": len(snapshot.board.nets),
                "copper_layer_count": len(snapshot.board.layers),
                "ratline_count": len(snapshot.board.ratlines),
                "differential_pair_count": len(snapshot.board.differential_pairs),
                "board_outline_point_count": snapshot.board.outline["point_count"]
                if snapshot.board.outline
                else 0,
                "routed_trace_count": sum(
                    int(item.attributes.get("trace_count", 0)) for item in net_records
                ),
                "component_types": {
                    item.attributes.get("type", "LibraryComponent"): sum(
                        1 for component in snapshot.board.components
                        if component.attributes.get("type", "LibraryComponent")
                        == item.attributes.get("type", "LibraryComponent")
                    )
                    for item in snapshot.board.components
                },
            }
        )
    if snapshot.schematic is not None:
        part_pins = sum(
            len(item.relationships.get("pins", [])) for item in snapshot.schematic.parts
        )
        parts_by_refdes = {
            item.refdes for item in snapshot.schematic.parts if item.refdes
        }
        unconnected_pin_count = 0
        intentional_no_connect_count = 0
        for part in document.container.findall("./Components/Part"):
            for pin in part.findall("./Pins/Pin"):
                if pin.get("NetId", "-1") == "-1" and pin.get("NotConnected", "N") != "Y":
                    unconnected_pin_count += 1
                if pin.get("NotConnected", "N") == "Y":
                    intentional_no_connect_count += 1
        result.update(
            {
                "sheet_count": len(snapshot.schematic.sheets),
                "component_count": len(parts_by_refdes),
                "part_count": len(snapshot.schematic.parts),
                "net_count": len(snapshot.schematic.nets),
                "pin_count": part_pins,
                "bus_count": len(snapshot.schematic.buses),
                "differential_pair_count": len(snapshot.schematic.differential_pairs),
                "unconnected_pin_count": unconnected_pin_count,
                "intentional_no_connect_count": intentional_no_connect_count,
            }
        )
    if snapshot.board is None and snapshot.schematic is None:
        result["top_level_sections"] = [
            child.tag for child in document.root if isinstance(child.tag, str)
        ]
    return result


def components(
    document: DipTraceDocument,
    query: str | None = None,
    offset: int = 0,
    limit: int = 100,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    snapshot = build_snapshot(document, live_session=live_session)
    if document.kind == "schematic":
        grouped: dict[str, dict[str, Any]] = {}
        for part in document.container.findall("./Components/Part"):
            refdes = _text(part, "RefDes") or f"<part:{part.get('Id', '?')}>"
            component_group = grouped.setdefault(
                refdes,
                {
                    "refdes": refdes,
                    "name": _text(part, "Name"),
                    "value": _text(part, "Value"),
                    "additional_fields": _additional_fields(part),
                    "part_count": 0,
                    "pin_count": 0,
                    "connected_pin_count": 0,
                    "parts": [],
                },
            )
            pins = part.findall("./Pins/Pin")
            component_group["part_count"] += 1
            component_group["pin_count"] += len(pins)
            component_group["connected_pin_count"] += sum(
                pin.get("NetId", "-1") != "-1" for pin in pins
            )
            component_group["parts"].append(
                {
                    "id": part.get("Id", ""),
                    "update_id": part.get("UpdateId", ""),
                    "part_refdes": _text(part, "PartRefDes"),
                    "part_name": _text(part, "PartName"),
                    "sheet": part.get("Sheet", ""),
                    "x": part.get("X", ""),
                    "y": part.get("Y", ""),
                    "angle": part.get("Angle", "0"),
                    "locked": part.get("Locked", "N"),
                    "selected": part.get("Selected", "N"),
                    "pins": [dict(pin.attrib, index=index) for index, pin in enumerate(pins)],
                }
            )
        items = list(grouped.values())
        if query:
            needle = query.casefold()
            items = [
                item
                for item in items
                if needle
                in " ".join(
                    [
                        str(item.get("refdes", "")),
                        str(item.get("name", "")),
                        str(item.get("value", "")),
                        " ".join(
                            f"{name} {value}"
                            for name, value in item.get("additional_fields", {}).items()
                        ),
                    ]
                ).casefold()
            ]
        items.sort(key=lambda item: str(item.get("refdes", "")))
        total = len(items)
        page = items[offset : offset + limit]
        payload = page
    elif document.kind == "pcb":
        items = []
        for component_element in document.container.findall("./Components/Component"):
            pads = component_element.findall("./Pads/Pad")
            entry = {
                "id": component_element.get("Id", ""),
                "update_id": component_element.get("UpdateId", ""),
                "refdes": _text(component_element, "RefDes"),
                "name": _text(component_element, "Name"),
                "value": _text(component_element, "Value"),
                "pattern_style": component_element.get("PatternStyle", ""),
                "type": component_element.get("Type", "LibraryComponent"),
                "x": component_element.get("X", ""),
                "y": component_element.get("Y", ""),
                "angle": component_element.get("Angle", "0"),
                "side": component_element.get("Side", "Top"),
                "locked": component_element.get("Locked", "N"),
                "selected": component_element.get("Selected", "N"),
                "pad_count": len(pads),
                "additional_fields": _additional_fields(component_element),
                "pads": [dict(pad.attrib, index=index) for index, pad in enumerate(pads)],
            }
            items.append(entry)
        if query:
            needle = query.casefold()
            items = [
                item
                for item in items
                if needle
                in " ".join(
                    [
                        str(item.get("refdes", "")),
                        str(item.get("name", "")),
                        str(item.get("value", "")),
                        " ".join(
                            f"{name} {value}"
                            for name, value in item.get("additional_fields", {}).items()
                        ),
                    ]
                ).casefold()
            ]
        items.sort(key=lambda item: str(item.get("refdes", "")))
        total = len(items)
        page = items[offset : offset + limit]
        payload = page
    else:
        raise DocumentError("Component listing supports PCB and Schematic XML only")

    return {
        "document": snapshot.info.document_id,
        "path": str(document.path),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": payload,
    }


def component(
    document: DipTraceDocument, refdes: str, *, live_session: bool = False
) -> dict[str, Any]:
    listing = components(document, limit=10_000, live_session=live_session)
    matches = [
        item
        for item in listing["items"]
        if str(item.get("refdes", "")).casefold() == refdes.casefold()
    ]
    if not matches:
        raise DocumentError(f"Component not found: {refdes}")
    target = matches[0]
    connected_nets = [
        net
        for net in nets(document, include_endpoints=True, limit=10_000, live_session=live_session)[
            "items"
        ]
        if any(
            str(endpoint.get("refdes", "")).casefold() == refdes.casefold()
            for endpoint in net.get("endpoints", [])
        )
    ]
    return {
        "path": str(document.path),
        "component": target,
        "connected_nets": connected_nets,
    }


def nets(
    document: DipTraceDocument,
    query: str | None = None,
    include_endpoints: bool = True,
    offset: int = 0,
    limit: int = 100,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    endpoint_map: dict[str, dict[str, Any]] = {}
    endpoint_key: str
    if document.kind == "schematic":
        for part in document.container.findall("./Components/Part"):
            endpoint_map[part.get("Id", "")] = {
                "refdes": _text(part, "RefDes"),
                "part_refdes": _text(part, "PartRefDes"),
                "part_name": _text(part, "PartName"),
                "sheet": part.get("Sheet", ""),
            }
        endpoint_list_name = "Pins"
        endpoint_key = "Part"
        endpoint_index_name = "Pin"
    elif document.kind == "pcb":
        for component in document.container.findall("./Components/Component"):
            endpoint_map[component.get("Id", "")] = {
                "refdes": _text(component, "RefDes"),
                "side": component.get("Side", "Top"),
            }
        endpoint_list_name = "Pads"
        endpoint_key = "Comp"
        endpoint_index_name = "Pad"
    else:
        raise DocumentError("Net listing supports PCB and Schematic XML only")

    items: list[dict[str, Any]] = []
    for net in document.container.findall("./Nets/Net"):
        name = _text(net, "Name")
        if query and query.casefold() not in name.casefold():
            continue
        endpoints = []
        for endpoint in net.findall(f"./{endpoint_list_name}/Item"):
            owner_id = endpoint.get(endpoint_key, "")
            details = dict(endpoint_map.get(owner_id, {}))
            details.update(
                {
                    "owner_id": owner_id,
                    "index": endpoint.get(endpoint_index_name, ""),
                }
            )
            endpoints.append(details)
        item: dict[str, Any] = {
            "id": net.get("Id", ""),
            "name": name,
            "net_class": net.get("NetClass", ""),
            "locked": net.get("Locked", "N"),
            "enabled": net.get("Enabled", "Y"),
            "endpoint_count": len(endpoints),
            "wire_count": len(net.findall("./Wires/Wire")),
            "trace_count": len(net.findall("./Traces/Trace")),
        }
        if include_endpoints:
            item["endpoints"] = endpoints
        items.append(item)

    items.sort(key=lambda item: str(item["name"]))
    total = len(items)
    payload = items[offset : offset + limit]
    return {
        "document": build_snapshot(document, live_session=live_session).info.model_dump(),
        "path": str(document.path),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": payload,
    }


def design_rules(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    snapshot = build_snapshot(document, live_session=live_session)
    if snapshot.board is not None:
        return {
            "document": snapshot.info.model_dump(),
            "path": str(document.path),
            "type": document.source_type,
            "units": document.units,
            "routing_defaults": snapshot.board.rules.get("routing_defaults"),
            "drc": snapshot.board.rules.get("drc"),
            "connectivity_check": snapshot.board.rules.get("connectivity_check"),
            "net_classes": snapshot.board.net_classes,
            "via_styles": [style.model_dump(mode="json") for style in snapshot.board.via_styles],
        }
    if snapshot.schematic is not None:
        return {
            "document": snapshot.info.model_dump(),
            "path": str(document.path),
            "type": document.source_type,
            "units": document.units,
            "erc": snapshot.schematic.erc,
            "net_classes": [
                _element_data(item) for item in document.container.findall("./NetClasses/NetClass")
            ],
        }
    raise DocumentError("Design rules support PCB and Schematic XML only")


def capability_report(
    document: DipTraceDocument, *, live_session: bool = False
) -> CapabilityReport:
    from . import __version__
    from .review import registry

    snapshot = build_snapshot(document, live_session=live_session)
    board = snapshot.board
    routable_via_style = bool(
        board is not None
        and any(
            style.diameter_mm is not None
            and style.hole_mm is not None
            and style.diameter_mm > style.hole_mm
            and (
                style.span_source == "explicit"
                or (style.span_source == "unspecified" and len(board.layers) == 2)
            )
            for style in board.via_styles
        )
    )
    return CapabilityReport(
        server_version=__version__,
        source_types={
            "document": snapshot.info.source_type,
            "kind": snapshot.info.kind,
            "compatibility": snapshot.info.compatibility,
        },
        read_capabilities={
            "board_model": snapshot.board is not None,
            "schematic_model": snapshot.schematic is not None,
            "library_model": document.kind in {"component_library", "pattern_library"},
            "library_validation": document.kind in {"component_library", "pattern_library"},
            "query_objects": True,
            "get_object": True,
            "connectivity_graph": document.kind in {"pcb", "schematic"},
            "bom": document.kind in {"pcb", "schematic"},
            "xml_fragments": True,
            "structured_findings": document.kind in {"pcb", "schematic"},
            "offline_review": document.kind in {"pcb", "schematic"},
            "manufacturing_review": snapshot.board is not None,
            "assembly_review": snapshot.board is not None,
            "testability_review": snapshot.board is not None,
            "return_path_heuristics": snapshot.board is not None,
            "copper_pour_boundaries": snapshot.board is not None,
            "silkscreen_planning": snapshot.board is not None,
            "placement_analysis": snapshot.board is not None,
            "placement_scoring": snapshot.board is not None,
            "local_placement_candidates": snapshot.board is not None,
            "unrouted_connections": snapshot.board is not None,
            "route_details": snapshot.board is not None,
            "physical_stackup": snapshot.board is not None,
            "net_length_measurement": snapshot.board is not None,
            "differential_pair_analysis": snapshot.board is not None,
            "analytical_microstrip_impedance": True,
            "analytical_differential_microstrip_impedance": True,
            "analytical_symmetric_stripline_impedance": True,
            "local_45_degree_routing": snapshot.board is not None,
            "multilayer_local_routing": bool(
                board is not None and len(board.layers) > 1 and routable_via_style
            ),
            "coupled_diff_pair_routing": bool(
                snapshot.board is not None and snapshot.board.differential_pairs
            ),
            "autorouter_ses_inspection": snapshot.board is not None,
            "external_jobs": True,
        },
        write_capabilities={
            "apply_xml_edits": True,
            "document_creation": True,
            "schematic_authoring": snapshot.schematic is not None,
            "schematic_to_pcb_sync": True,
            "panelization": snapshot.board is not None,
            "move_components": snapshot.board is not None or snapshot.schematic is not None,
            "rotate_components": snapshot.board is not None or snapshot.schematic is not None,
            "set_component_side": snapshot.board is not None,
            "lock_components": snapshot.board is not None or snapshot.schematic is not None,
            "set_component_value": snapshot.board is not None or snapshot.schematic is not None,
            "set_component_properties": snapshot.board is not None
            or snapshot.schematic is not None,
            "set_component_pattern": snapshot.board is not None,
            "align_distribute_components": snapshot.board is not None,
            "component_groups": snapshot.board is not None,
            "board_text_edits": snapshot.board is not None,
            "set_pin_no_connect": snapshot.schematic is not None,
            "rename_net": snapshot.board is not None or snapshot.schematic is not None,
            "net_class_rules": snapshot.board is not None,
            "testpoints": snapshot.board is not None,
            "apply_silkscreen_plan": snapshot.board is not None,
            "apply_component_placement_plan": snapshot.board is not None,
            "trace_primitives": snapshot.board is not None,
            "via_primitives": snapshot.board is not None,
            "apply_route_plan": snapshot.board is not None,
            "route_diff_pair": bool(
                snapshot.board is not None and snapshot.board.differential_pairs
            ),
            "bom_export": document.kind in {"pcb", "schematic"},
            "fabrication_manifest_export": snapshot.board is not None,
            "assembly_manifest_export": snapshot.board is not None,
            "autorouter_dsn_export": False,
            "autorouter_ses_import": snapshot.board is not None,
            "transactions": True,
        },
        experimental_capabilities={
            "push_and_shove_routing": False,
            "rip_up_retry_routing": snapshot.board is not None,
            "automatic_via_routing": routable_via_style,
            "coupled_diff_pair_routing": bool(
                snapshot.board is not None and snapshot.board.differential_pairs
            ),
            "global_placement": False,
            "symmetric_stripline_impedance": True,
            "differential_impedance": True,
            "return_path_heuristics": snapshot.board is not None,
        },
        external_adapters={
            "freerouting": {
                "available": False,
                "implemented": True,
                "reason": "Runtime availability requires DIPTRACE_MCP_FREEROUTING.",
            },
            "ngspice": {
                "available": False,
                "implemented": True,
                "reason": "Runtime availability requires DIPTRACE_MCP_NGSPICE or ngspice on PATH.",
            },
            "openems": {
                "available": False,
                "implemented": True,
                "reason": "Runtime availability requires DIPTRACE_MCP_OPENEMS_RUNNER.",
            },
        },
        geometry_backend=backend_report(),
        preview_formats=["svg", "json", "diff"],
        limits={
            "max_document_bytes": None,
            "max_query_results": 500,
            "max_transaction_operations": 10_000,
        },
        policy={
            "default_write_mode": "dry_run",
            "rollback_supported": True,
            "conflict_safe_rollback": True,
            "explicit_sha_on_commit": True,
            "preserve_unknown_xml": True,
        },
        reasons_unavailable=[
            *(
                [
                    {
                        "feature": "automatic_via_routing",
                        "code": "capability_unavailable",
                        "message": (
                            "No via style has valid geometry and a resolvable Lay1/Lay2 span."
                        ),
                    }
                ]
                if board is not None and len(board.layers) > 1 and not routable_via_style
                else []
            ),
            {
                "feature": "external_autorouting",
                "code": "external_tool_unavailable",
                "message": "Freerouting adapter is implemented but no executable is configured.",
            },
            {
                "feature": "global_placement",
                "code": "capability_unavailable",
                "message": "Only deterministic bounded local placement is implemented.",
            },
            {
                "feature": "push_and_shove_routing",
                "code": "capability_unavailable",
                "message": (
                    "The local router is bounded 45-degree A*; rip-up/retry is "
                    "available via route_connections, push-and-shove is not implemented."
                ),
            },
            {
                "feature": "native_manufacturing_outputs",
                "code": "capability_unavailable",
                "message": "Gerber, NC drill, ODB++ and IPC-2581 generation is unavailable.",
            },
            {
                "feature": "library_mutation",
                "code": "capability_unavailable",
                "message": "Component and pattern libraries are read/validate only.",
            },
            {
                "feature": "external_si_pi_solver",
                "code": "external_tool_unavailable",
                "message": (
                    "The ngspice batch adapter is implemented for user-supplied "
                    "netlists. The typed openEMS stripline adapter is implemented; "
                    "configure DIPTRACE_MCP_OPENEMS_RUNNER to enable it."
                ),
            },
        ],
        registered_checks=registry.ids(),
        workflow_prompts=[
            {"name": name, "status": "available"}
            for name in (
                "review_board_before_release",
                "review_schematic_before_layout",
                "place_selected_components_safely",
                "place_decoupling_network",
                "route_critical_net",
                "route_diff_pair_with_constraints",
                "clean_silkscreen_for_manufacturing",
                "add_testpoints_for_fixture",
                "review_return_paths",
                "prepare_fabrication_export",
                "prepare_assembly_export",
                "review_bom",
                "compare_schematic_and_pcb",
                "synchronize_schematic_to_pcb",
            )
        ],
    )


def apply_low_level_edits(
    document: DipTraceDocument,
    edits: list[XmlEdit],
) -> tuple[bytes, list[dict[str, object]]]:
    return document.apply_edits(edits)
