from __future__ import annotations

import collections
import xml.etree.ElementTree as ET
from typing import Any

from .errors import DocumentError
from .xml_document import DipTraceDocument


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


def _source_info(document: DipTraceDocument) -> dict[str, Any]:
    return {
        "path": str(document.path),
        "type": document.source_type,
        "kind": document.kind,
        "version": document.version,
        "units": document.units,
        "size_bytes": len(document.raw_bytes),
        "sha256": document.sha256,
    }


def summarize(document: DipTraceDocument) -> dict[str, Any]:
    result = _source_info(document)
    if document.kind == "schematic":
        schematic = document.container
        parts = schematic.findall("./Components/Part")
        nets = schematic.findall("./Nets/Net")
        sheets = [
            {
                "id": _text(sheet, "Id"),
                "name": _text(sheet, "Name"),
                "type": _text(sheet, "Type"),
            }
            for sheet in schematic.findall("./SheetSettings/Sheets/Sheet")
        ]
        refdes = {_text(part, "RefDes") for part in parts if _text(part, "RefDes")}
        pins = [pin for part in parts for pin in part.findall("./Pins/Pin")]
        result.update(
            {
                "sheets": sheets,
                "sheet_count": len(sheets),
                "component_count": len(refdes),
                "part_count": len(parts),
                "net_count": sum(net.get("Enabled", "Y") != "N" for net in nets),
                "pin_count": len(pins),
                "unconnected_pin_count": sum(
                    pin.get("NetId", "-1") == "-1" and pin.get("NotConnected", "N") != "Y"
                    for pin in pins
                ),
                "intentional_no_connect_count": sum(
                    pin.get("NotConnected", "N") == "Y" for pin in pins
                ),
                "differential_pair_count": len(
                    schematic.findall("./DifferentialPairs/DifferentialPair")
                ),
                "bus_count": len(schematic.findall("./Buses/Bus")),
                "net_class_count": len(schematic.findall("./NetClasses/NetClass")),
            }
        )
        return result

    if document.kind == "pcb":
        board = document.container
        components = board.findall("./Components/Component")
        nets = board.findall("./Nets/Net")
        component_types = collections.Counter(
            component.get("Type", "LibraryComponent") for component in components
        )
        copper_layers = [
            {
                "id": layer.get("Id", str(index)),
                "name": _text(layer, "Name", layer.get("Name", "")),
                "type": layer.get("Type", ""),
            }
            for index, layer in enumerate(board.findall("./CopperLayers/Lay"))
        ]
        result.update(
            {
                "component_count": len(components),
                "component_types": dict(component_types),
                "net_count": len(nets),
                "routed_trace_count": sum(
                    len(net.findall("./Traces/Trace")) for net in nets
                ),
                "ratline_count": len(board.findall("./Ratlines/Ratline")),
                "differential_pair_count": len(
                    board.findall("./DifferentialPairs/DifferentialPair")
                ),
                "copper_layer_count": len(copper_layers),
                "copper_layers": copper_layers,
                "board_outline_point_count": len(
                    board.findall("./BoardOutline/Points/Point")
                ),
                "net_class_count": len(board.findall("./NetClasses/NetClass")),
                "via_style_count": len(board.findall("./ViaStyles/ViaStyle")),
                "copper_pour_count": len(board.findall(".//CopperPour")),
            }
        )
        return result

    result["top_level_sections"] = [
        child.tag for child in document.root if isinstance(child.tag, str)
    ]
    return result


def _schematic_components(document: DipTraceDocument) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for part in document.container.findall("./Components/Part"):
        refdes = _text(part, "RefDes") or f"<part:{part.get('Id', '?')}>"
        component = grouped.setdefault(
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
        component["part_count"] += 1
        component["pin_count"] += len(pins)
        component["connected_pin_count"] += sum(
            pin.get("NetId", "-1") != "-1" for pin in pins
        )
        component["parts"].append(
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
    return list(grouped.values())


def _pcb_components(document: DipTraceDocument) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for component in document.container.findall("./Components/Component"):
        pads = component.findall("./Pads/Pad")
        components.append(
            {
                "id": component.get("Id", ""),
                "update_id": component.get("UpdateId", ""),
                "refdes": _text(component, "RefDes"),
                "name": _text(component, "Name"),
                "value": _text(component, "Value"),
                "pattern_style": component.get("PatternStyle", ""),
                "type": component.get("Type", "LibraryComponent"),
                "x": component.get("X", ""),
                "y": component.get("Y", ""),
                "angle": component.get("Angle", "0"),
                "side": component.get("Side", "Top"),
                "locked": component.get("Locked", "N"),
                "selected": component.get("Selected", "N"),
                "pad_count": len(pads),
                "additional_fields": _additional_fields(component),
                "pads": [dict(pad.attrib, index=index) for index, pad in enumerate(pads)],
            }
        )
    return components


def components(
    document: DipTraceDocument,
    query: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    if document.kind == "schematic":
        items = _schematic_components(document)
    elif document.kind == "pcb":
        items = _pcb_components(document)
    else:
        raise DocumentError("Component listing supports PCB and Schematic XML only")

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
    return {
        "path": str(document.path),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items[offset : offset + limit],
    }


def _endpoint_maps(document: DipTraceDocument) -> tuple[dict[str, dict[str, Any]], str]:
    if document.kind == "schematic":
        mapping: dict[str, dict[str, Any]] = {}
        for part in document.container.findall("./Components/Part"):
            mapping[part.get("Id", "")] = {
                "refdes": _text(part, "RefDes"),
                "part_refdes": _text(part, "PartRefDes"),
                "part_name": _text(part, "PartName"),
                "sheet": part.get("Sheet", ""),
            }
        return mapping, "Part"
    if document.kind == "pcb":
        mapping = {}
        for component in document.container.findall("./Components/Component"):
            mapping[component.get("Id", "")] = {
                "refdes": _text(component, "RefDes"),
                "side": component.get("Side", "Top"),
            }
        return mapping, "Comp"
    raise DocumentError("Net listing supports PCB and Schematic XML only")


def nets(
    document: DipTraceDocument,
    query: str | None = None,
    include_endpoints: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    endpoint_map, endpoint_key = _endpoint_maps(document)
    endpoint_list_name = "Pins" if document.kind == "schematic" else "Pads"
    endpoint_index_name = "Pin" if document.kind == "schematic" else "Pad"
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
    return {
        "path": str(document.path),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items[offset : offset + limit],
    }


def component(document: DipTraceDocument, refdes: str) -> dict[str, Any]:
    listing = components(document, limit=10_000)
    matches = [
        item
        for item in listing["items"]
        if str(item.get("refdes", "")).casefold() == refdes.casefold()
    ]
    if not matches:
        raise DocumentError(f"Component not found: {refdes}")
    connected_nets = []
    for net in nets(document, include_endpoints=True, limit=10_000)["items"]:
        endpoints = [
            endpoint
            for endpoint in net.get("endpoints", [])
            if str(endpoint.get("refdes", "")).casefold() == refdes.casefold()
        ]
        if endpoints:
            connected_nets.append(
                {
                    "id": net["id"],
                    "name": net["name"],
                    "endpoints": endpoints,
                }
            )
    return {
        "path": str(document.path),
        "component": matches[0],
        "connected_nets": connected_nets,
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


def design_rules(document: DipTraceDocument) -> dict[str, Any]:
    container = document.container
    if document.kind == "schematic":
        return {
            "path": str(document.path),
            "type": document.source_type,
            "units": document.units,
            "erc": _element_data(container.find("./ERC"), depth=2),
            "net_classes": [
                _element_data(item, depth=3)
                for item in container.findall("./NetClasses/NetClass")
            ],
        }
    if document.kind == "pcb":
        return {
            "path": str(document.path),
            "type": document.source_type,
            "units": document.units,
            "routing_defaults": _element_data(container.find("./Settings/Routing"), depth=3),
            "drc": _element_data(container.find("./DRC"), depth=5),
            "connectivity_check": _element_data(
                container.find("./ConnectivityCheck"), depth=2
            ),
            "net_classes": [
                _element_data(item, depth=5)
                for item in container.findall("./NetClasses/NetClass")
            ],
            "via_styles": [
                _element_data(item, depth=3)
                for item in container.findall("./ViaStyles/ViaStyle")
            ],
            "class_to_class": _element_data(container.find("./ClassToClass"), depth=4),
        }
    raise DocumentError("Design rules support PCB and Schematic XML only")
