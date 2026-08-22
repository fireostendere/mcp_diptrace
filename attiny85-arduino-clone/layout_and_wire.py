#!/usr/bin/env python3
"""Place and wire the fixed sheets as compact, human-readable blocks."""

import copy
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.geometry import BBox, Point
from diptrace_mcp.operations import (
    AddWireOperation,
    ConnectPinsOperation,
    MoveComponentsOperation,
    PlacePartOperation,
    RotateComponentsOperation,
    SetComponentPropertiesOperation,
)
from diptrace_mcp.schematic_layout import schematic_sheet_usable_bounds
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.services.builtin_library import _component_definitions
from diptrace_mcp.services.schematic_wire_quality import _text_obstacles
from diptrace_mcp.xml_document import DipTraceDocument

PATH = Path(__file__).with_name("attiny85-arduino-clone.dchxml")
NET_PORT_LIBRARY = Path(
    "/mnt/c/Users/fireo/Documents/attiny85-arduino-clone/library-cache/auto_net_ports.elixml"
)
GROUND_LIBRARY_INDEX = 19
POWER_LIBRARY_INDEXES = {"+3V3": 4, "VBUS": 14}
GENERATED_PORT_PREFIXES = ("PSG", "PWR", "NPI", "NPO")

PLACEMENT = {
    # USB_POWER: connector -> regulator -> inductor; bias and returns below.
    "J1": (45.0, 160.0),
    "C1": (62.0, 145.0),
    "U3": (110.0, 160.0),
    "L1": (140.0, 160.0),
    "C2": (130.0, 140.0),
    "R1": (68.0, 149.27),
    "R2": (68.0, 137.76),
    "R3": (89.5, 140.0),
    # USB_UART: supply and USB on the left, UART and reset on the right.
    "U2": (120.0, 155.0),
    "C3": (65.0, 185.0),
    "C4": (82.0, 185.0),
    "R4": (41.0, 150.0),
    "R5": (57.0, 150.0),
    "C6": (160.08, 176.59),
    # MCU_ISP: programming connector -> MCU -> local decoupling.
    "J2": (55.0, 160.0),
    "R6": (121.82, 149.84),
    "U1": (165.0, 160.0),
    "C5": (207.54, 157.46),
    # IO
    "J3": (120.0, 160.0),
}

HORIZONTAL_FLIP = {"J3"}

ROTATION = {
    "C1": 270.0,
    "C2": 270.0,
    "R1": 270.0,
    "R2": 270.0,
    "R3": 0.0,
    "L1": 270.0,
    "C3": 270.0,
    "C4": 270.0,
    "R4": 0.0,
    "R5": 0.0,
    "C6": 0.0,
    "R6": 0.0,
    "C5": 270.0,
}


@dataclass(frozen=True)
class Endpoint:
    refdes: str
    pin: int
    sheet: int
    x: float
    y: float
    dx: float
    dy: float


@dataclass(frozen=True)
class WireSpec:
    net: str
    sheet: int
    start: tuple[str, int] | None
    end: tuple[str, int] | None
    points: tuple[tuple[float, float], ...]


def marking(tag: str) -> ET.Element:
    return ET.Element(
        tag,
        Show="Hide",
        Align="Common",
        Horz="Center",
        Vert="Center",
        X="0",
        Y="0",
        Angle="0",
        ShowPart="Hide",
    )


def is_generated_port(refdes: str) -> bool:
    return refdes.startswith(GENERATED_PORT_PREFIXES)


def ensure_overview_sheet(root: ET.Element) -> int:
    sheets = root.find("./Schematic/SheetSettings/Sheets")
    assert sheets is not None
    for sheet in sheets.findall("./Sheet"):
        if sheet.findtext("./Name") == "SYSTEM_OVERVIEW":
            return int(sheet.findtext("./Id") or "0")
    template = sheets.find("./Sheet")
    assert template is not None
    sheet = copy.deepcopy(template)
    sheet_id = max(int(item.findtext("./Id") or "0") for item in sheets) + 1
    sheet.find("./Id").text = str(sheet_id)  # type: ignore[union-attr]
    sheet.find("./Name").text = "SYSTEM_OVERVIEW"  # type: ignore[union-attr]
    sheet.find("./Type").text = "Normal"  # type: ignore[union-attr]
    sheets.append(sheet)
    return sheet_id


def clean_visuals(raw_bytes: bytes) -> DipTraceDocument:
    root = ET.fromstring(raw_bytes)
    ensure_overview_sheet(root)
    components = root.find("./Schematic/Components")
    library_components = root.find("./Library/Components")
    assert components is not None and library_components is not None
    generated_styles = {
        part.get("ComponentStyle", "")
        for part in components.findall("./Part")
        if is_generated_port(part.findtext("./RefDes") or "")
    }
    for part in list(components.findall("./Part")):
        if is_generated_port(part.findtext("./RefDes") or ""):
            components.remove(part)
    for component in list(library_components.findall("./Component")):
        if component.get("ComponentStyle", "") in generated_styles:
            library_components.remove(component)
    for net in root.findall("./Schematic/Nets/Net"):
        wires = net.find("./Wires")
        if wires is not None:
            net.remove(wires)
    shapes = root.find("./Schematic/Shapes")
    assert shapes is not None
    shapes.clear()
    for part in root.findall("./Schematic/Components/Part"):
        for tag in ("NameMarking", "ManufacturerMarking", "DatasheetMarking"):
            existing = part.find(f"./{tag}")
            if existing is not None:
                part.remove(existing)
            part.append(marking(tag))
        for tag in ("RefDesMarking", "ValueMarking"):
            element = part.find(f"./{tag}")
            assert element is not None
            element.set("Show", "Show")
    return DipTraceDocument.from_bytes(
        PATH,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def apply_instance_flips(document: DipTraceDocument) -> DipTraceDocument:
    root = document.root
    for part in root.findall("./Schematic/Components/Part"):
        if (part.findtext("./RefDes") or "") in HORIZONTAL_FLIP:
            part.set("HorzFlip", "Y")
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def rotate(x: float, y: float, angle: float) -> tuple[float, float]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return x * cosine - y * sine, x * sine + y * cosine


def transform_local(part: ET.Element, x: float, y: float) -> tuple[float, float]:
    if part.get("HorzFlip") == "Y":
        x = -x
    if part.get("VertFlip") == "Y":
        y = -y
    return rotate(x, y, float(part.get("Angle", "0")))


def endpoints(document: DipTraceDocument) -> dict[str, list[Endpoint]]:
    root = document.root
    styles = {
        component.get("ComponentStyle"): component
        for component in root.findall("./Library/Components/Component")
    }
    net_names = {
        net.get("Id", ""): net.findtext("./Name") or ""
        for net in root.findall("./Schematic/Nets/Net")
    }
    result: dict[str, list[Endpoint]] = {name: [] for name in net_names.values()}
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        sheet = int(part.get("Sheet", "0"))
        part_x, part_y = float(part.get("X", "0")), float(part.get("Y", "0"))
        style = styles[part.get("ComponentStyle")]
        library_part = style.find("./Part[@Id='0']")
        assert library_part is not None
        library_pins = library_part.findall("./Pins/Pin")
        for pin_index, placed_pin in enumerate(part.findall("./Pins/Pin")):
            net_id = placed_pin.get("NetId", "-1")
            if net_id == "-1":
                continue
            pin = library_pins[pin_index]
            pin_angle = math.radians(float(pin.get("Orientation", "0")))
            local_dx, local_dy = -math.cos(pin_angle), math.sin(pin_angle)
            local_x = float(pin.get("X", "0")) + local_dx * float(pin.get("Length", "0"))
            local_y = float(pin.get("Y", "0")) + local_dy * float(pin.get("Length", "0"))
            offset_x, offset_y = transform_local(part, local_x, local_y)
            dx, dy = transform_local(part, local_dx, local_dy)
            result[net_names[net_id]].append(
                Endpoint(
                    refdes,
                    pin_index,
                    sheet,
                    part_x + offset_x,
                    part_y + offset_y,
                    dx,
                    dy,
                )
            )
    return result


def endpoint_index(by_net: dict[str, list[Endpoint]]) -> dict[tuple[str, int], Endpoint]:
    return {
        (endpoint.refdes, endpoint.pin): endpoint
        for net_endpoints in by_net.values()
        for endpoint in net_endpoints
    }


def component_boxes(
    document: DipTraceDocument,
) -> dict[str, tuple[int, float, float, float, float]]:
    root = document.root
    styles = {
        component.get("ComponentStyle"): component
        for component in root.findall("./Library/Components/Component")
    }
    result = {}
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        library_part = styles[part.get("ComponentStyle")].find("./Part[@Id='0']")
        assert library_part is not None
        x, y = float(part.get("X", "0")), float(part.get("Y", "0"))
        half_width = float(library_part.get("Width", "0")) / 2
        half_height = float(library_part.get("Height", "0")) / 2
        corners = [
            transform_local(part, dx, dy)
            for dx in (-half_width, half_width)
            for dy in (-half_height, half_height)
        ]
        result[refdes] = (
            int(part.get("Sheet", "0")),
            x + min(point[0] for point in corners),
            y + min(point[1] for point in corners),
            x + max(point[0] for point in corners),
            y + max(point[1] for point in corners),
        )
    return result


def segments(points: tuple[tuple[float, float], ...] | list[tuple[float, float]]):
    return zip(points, points[1:], strict=False)


def body_intersections(
    points: tuple[tuple[float, float], ...],
    sheet: int,
    boxes: dict[str, tuple[int, float, float, float, float]],
) -> list[str]:
    hits = []
    for a, b in segments(points):
        horizontal = math.isclose(a[1], b[1], abs_tol=1e-6)
        assert horizontal or math.isclose(a[0], b[0], abs_tol=1e-6), (a, b, points)
        for refdes, (part_sheet, min_x, min_y, max_x, max_y) in boxes.items():
            if part_sheet != sheet:
                continue
            if horizontal:
                low, high = sorted((a[0], b[0]))
                intersects = min_y < a[1] < max_y and max(low, min_x) < min(high, max_x)
            else:
                low, high = sorted((a[1], b[1]))
                intersects = min_x < a[0] < max_x and max(low, min_y) < min(high, max_y)
            if intersects:
                hits.append(refdes)
    return hits


def crossing_count(
    spec: WireSpec,
    planned: list[tuple[int, str, tuple[float, float], tuple[float, float]]],
) -> int:
    count = 0
    for a, b in segments(spec.points):
        horizontal = math.isclose(a[1], b[1], abs_tol=1e-6)
        for other_sheet, other_net, c, d in planned:
            if spec.sheet != other_sheet or spec.net == other_net:
                continue
            other_horizontal = math.isclose(c[1], d[1], abs_tol=1e-6)
            if horizontal == other_horizontal:
                continue
            h1, h2, v1, v2 = (a, b, c, d) if horizontal else (c, d, a, b)
            x, y = v1[0], h1[1]
            if min(h1[0], h2[0]) < x < max(h1[0], h2[0]) and min(v1[1], v2[1]) < y < max(
                v1[1], v2[1]
            ):
                count += 1
    return count


def pin_stubs(
    document: DipTraceDocument,
) -> list[tuple[int, str, int, tuple[float, float], tuple[float, float]]]:
    root = document.root
    styles = {
        component.get("ComponentStyle"): component
        for component in root.findall("./Library/Components/Component")
    }
    result = []
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        sheet = int(part.get("Sheet", "0"))
        origin_x, origin_y = float(part.get("X", "0")), float(part.get("Y", "0"))
        library_part = styles[part.get("ComponentStyle")].find("./Part[@Id='0']")
        assert library_part is not None
        for pin_index, pin in enumerate(library_part.findall("./Pins/Pin")):
            pin_angle = math.radians(float(pin.get("Orientation", "0")))
            dx, dy = -math.cos(pin_angle), math.sin(pin_angle)
            local_body = (float(pin.get("X", "0")), float(pin.get("Y", "0")))
            local_outer = (
                local_body[0] + dx * float(pin.get("Length", "0")),
                local_body[1] + dy * float(pin.get("Length", "0")),
            )
            body_offset = transform_local(part, *local_body)
            outer_offset = transform_local(part, *local_outer)
            result.append(
                (
                    sheet,
                    refdes,
                    pin_index,
                    (origin_x + body_offset[0], origin_y + body_offset[1]),
                    (origin_x + outer_offset[0], origin_y + outer_offset[1]),
                )
            )
    return result


def segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    a_horizontal = math.isclose(a[1], b[1], abs_tol=1e-6)
    c_horizontal = math.isclose(c[1], d[1], abs_tol=1e-6)
    if a_horizontal and c_horizontal:
        return math.isclose(a[1], c[1], abs_tol=1e-6) and max(
            min(a[0], b[0]), min(c[0], d[0])
        ) <= min(max(a[0], b[0]), max(c[0], d[0]))
    if not a_horizontal and not c_horizontal:
        return math.isclose(a[0], c[0], abs_tol=1e-6) and max(
            min(a[1], b[1]), min(c[1], d[1])
        ) <= min(max(a[1], b[1]), max(c[1], d[1]))
    h1, h2, v1, v2 = (a, b, c, d) if a_horizontal else (c, d, a, b)
    return min(h1[0], h2[0]) <= v1[0] <= max(h1[0], h2[0]) and min(v1[1], v2[1]) <= h1[1] <= max(
        v1[1], v2[1]
    )


def unrelated_pin_hits(
    spec: WireSpec,
    stubs: list[tuple[int, str, int, tuple[float, float], tuple[float, float]]],
    net_by_pin: dict[tuple[str, int], str],
) -> list[tuple[str, int]]:
    return [
        (refdes, pin)
        for a, b in segments(spec.points)
        for pin_sheet, refdes, pin, c, d in stubs
        if pin_sheet == spec.sheet
        and net_by_pin.get((refdes, pin)) != spec.net
        and segments_intersect(a, b, c, d)
    ]


def assert_pin_escape(spec: WireSpec, index: dict[tuple[str, int], Endpoint]) -> None:
    if spec.start is not None and not is_generated_port(spec.start[0]):
        endpoint = index[spec.start]
        next_point = spec.points[1]
        assert (next_point[0] - endpoint.x) * endpoint.dx + (
            next_point[1] - endpoint.y
        ) * endpoint.dy > 0.5, (spec.net, spec.start, spec.points)
    if spec.end is not None and not is_generated_port(spec.end[0]):
        endpoint = index[spec.end]
        previous = spec.points[-2]
        assert (previous[0] - endpoint.x) * endpoint.dx + (
            previous[1] - endpoint.y
        ) * endpoint.dy > 0.5, (spec.net, spec.end, spec.points)


def pin_point(index: dict[tuple[str, int], Endpoint], key: tuple[str, int]) -> tuple[float, float]:
    endpoint = index[key]
    return endpoint.x, endpoint.y


def wire(
    index: dict[tuple[str, int], Endpoint],
    net: str,
    sheet: int,
    start: tuple[str, int] | None,
    end: tuple[str, int] | None,
    *middle: tuple[float, float],
    free_start: tuple[float, float] | None = None,
    free_end: tuple[float, float] | None = None,
) -> WireSpec:
    points = (
        free_start if start is None else pin_point(index, start),
        *middle,
        free_end if end is None else pin_point(index, end),
    )
    assert all(point is not None for point in points)
    compact = tuple(
        point
        for position, point in enumerate(points)
        if position == 0 or point != points[position - 1]
    )
    return WireSpec(net, sheet, start, end, compact)  # type: ignore[arg-type]


def port(
    index: dict[tuple[str, int], Endpoint],
    net: str,
    sheet: int,
    key: tuple[str, int],
    length: float = 7.62,
) -> tuple[WireSpec, tuple[float, float]]:
    endpoint = index[key]
    label_point = (endpoint.x + endpoint.dx * length, endpoint.y + endpoint.dy * length)
    return wire(index, net, sheet, key, None, free_end=label_point), label_point


def add_ground_symbols(
    document: DipTraceDocument,
    groups: list[tuple[int, tuple[tuple[str, int], ...], tuple[float, float]]],
) -> tuple[DipTraceDocument, list[tuple[str, tuple[str, int], tuple[float, float]]]]:
    source = DipTraceDocument.load(NET_PORT_LIBRARY, 512 * 1024 * 1024)
    definitions = _component_definitions(
        source,
        document,
        {"library_index": GROUND_LIBRARY_INDEX, "name": "GND"},
    )
    component = ET.fromstring(definitions["component_xml"])
    pin = component.find("./Part[@Id='0']/Pins/Pin")
    assert pin is not None
    pin_angle = math.radians(float(pin.get("Orientation", "0")))
    pin_offset_x = float(pin.get("X", "0")) - math.cos(pin_angle) * float(pin.get("Length", "0"))
    pin_offset_y = float(pin.get("Y", "0")) + math.sin(pin_angle) * float(pin.get("Length", "0"))
    operations = []
    symbol_pins = []
    mapping = []
    for number, (sheet, keys, terminal) in enumerate(groups, 1):
        refdes = f"PSG{number}"
        operations.append(
            PlacePartOperation(
                component_style=definitions["component_style"],
                refdes=refdes,
                name="GND",
                value="GND",
                x=terminal[0] - pin_offset_x,
                y=terminal[1] - pin_offset_y,
                sheet=sheet,
                pin_count=1,
                library_component_xml=definitions["component_xml"] if number == 1 else None,
            )
        )
        symbol_pins.append({"refdes": refdes, "pin": 0})
        mapping.extend((refdes, key, terminal) for key in keys)
    operations.append(ConnectPinsOperation(net="GND", pins=symbol_pins))
    placed = apply_semantic_operations(document, operations).document
    marked = apply_semantic_operations(
        placed,
        [
            SetComponentPropertiesOperation(
                selector=QuerySelector(refdes=[item["refdes"] for item in symbol_pins]),
                fields={"DNP": "Y"},
            )
        ],
    ).document
    for part in marked.root.findall("./Schematic/Components/Part"):
        if (part.findtext("./RefDes") or "").startswith("PSG"):
            name_marking = part.find("./NameMarking")
            if name_marking is not None:
                name_marking.set("Show", "Hide")
    hidden_names = DipTraceDocument.from_bytes(
        marked.path,
        ET.tostring(marked.root, encoding="utf-8", xml_declaration=True),
    )
    return hidden_names, mapping


def add_named_net_ports(
    document: DipTraceDocument,
    labels: list[tuple[str, int, tuple[float, float]]],
    specs: list[WireSpec],
) -> tuple[DipTraceDocument, dict[tuple[str, int, tuple[float, float]], tuple[str, int]]]:
    source = DipTraceDocument.load(NET_PORT_LIBRARY, 512 * 1024 * 1024)
    records = []
    counters = {"PWR": 0, "NPI": 0, "NPO": 0}
    for net, sheet, terminal in labels:
        alignment = label_alignment(terminal, sheet, specs)
        if net in POWER_LIBRARY_INDEXES:
            prefix = "PWR"
            library_index = POWER_LIBRARY_INDEXES[net]
        elif alignment == "Right":
            prefix = "NPI"
            library_index = 28 + min(max(len(net), 1), 7)
        else:
            assert alignment == "Left", (net, sheet, terminal)
            prefix = "NPO"
            library_index = 36 + min(max(len(net), 1), 7)
        counters[prefix] += 1
        records.append((library_index, f"{prefix}{counters[prefix]}", net, sheet, terminal))

    placed = document
    mapping = {}
    for library_index in dict.fromkeys(record[0] for record in records):
        part_name = source.root.findall("./Components/Component")[library_index].findtext(
            "./Part/Name"
        )
        assert part_name is not None
        definitions = _component_definitions(
            source,
            placed,
            {"library_index": library_index, "name": part_name},
        )
        component = ET.fromstring(definitions["component_xml"])
        pin = component.find("./Part[@Id='0']/Pins/Pin")
        assert pin is not None
        pin_angle = math.radians(float(pin.get("Orientation", "0")))
        pin_offset_x = float(pin.get("X", "0")) - math.cos(pin_angle) * float(
            pin.get("Length", "0")
        )
        pin_offset_y = float(pin.get("Y", "0")) + math.sin(pin_angle) * float(
            pin.get("Length", "0")
        )
        matching = [record for record in records if record[0] == library_index]
        placed = apply_semantic_operations(
            placed,
            [
                PlacePartOperation(
                    component_style=definitions["component_style"],
                    refdes=refdes,
                    name=net,
                    value="",
                    x=terminal[0] - pin_offset_x,
                    y=terminal[1] - pin_offset_y,
                    sheet=sheet,
                    pin_count=1,
                    library_component_xml=(
                        definitions["component_xml"] if position == 0 else None
                    ),
                )
                for position, (_, refdes, net, sheet, terminal) in enumerate(matching)
            ],
        ).document
        for _, refdes, net, sheet, terminal in matching:
            mapping[(net, sheet, terminal)] = (refdes, 0)

    pins_by_net: dict[str, list[dict[str, object]]] = {}
    for _, refdes, net, _, _ in records:
        pins_by_net.setdefault(net, []).append({"refdes": refdes, "pin": 0})
    connected = apply_semantic_operations(
        placed,
        [ConnectPinsOperation(net=net, pins=pins) for net, pins in pins_by_net.items()],
    ).document
    marked = apply_semantic_operations(
        connected,
        [
            SetComponentPropertiesOperation(
                selector=QuerySelector(refdes=[record[1] for record in records]),
                fields={"DNP": "Y"},
            )
        ],
    ).document
    return marked, mapping


def attach_named_ports(
    specs: list[WireSpec],
    mapping: dict[tuple[str, int, tuple[float, float]], tuple[str, int]],
) -> list[WireSpec]:
    result = []
    for spec in specs:
        start = spec.start or mapping.get((spec.net, spec.sheet, spec.points[0]))
        end = spec.end or mapping.get((spec.net, spec.sheet, spec.points[-1]))
        result.append(WireSpec(spec.net, spec.sheet, start, end, spec.points))
    return result


def append_wires(
    document: DipTraceDocument, operations: list[AddWireOperation]
) -> DipTraceDocument:
    root = document.root
    parts = {
        (part.findtext("./RefDes") or "").casefold(): part
        for part in root.findall("./Schematic/Components/Part")
    }
    nets = {
        (net.findtext("./Name") or "").casefold(): net
        for net in root.findall("./Schematic/Nets/Net")
    }

    def endpoint_attributes(side: int, endpoint: object) -> dict[str, str]:
        result = {f"Connected{side}": endpoint.type, f"Bus{side}": "-1"}
        if endpoint.type == "Pin":
            part = parts[endpoint.refdes.casefold()]
            result.update(
                {
                    f"Object{side}": part.get("Id", ""),
                    f"SubObject{side}": str(endpoint.pin),
                }
            )
        else:
            result.update({f"Object{side}": "-1", f"SubObject{side}": "-1"})
        return result

    for operation in operations:
        net = nets[operation.net.casefold()]
        wires = net.find("./Wires")
        if wires is None:
            wires = ET.SubElement(net, "Wires")
        wire = ET.SubElement(
            wires,
            "Wire",
            {
                "Id": str(len(wires.findall("./Wire"))),
                "Sheet": str(operation.sheet),
                **endpoint_attributes(1, operation.start),
                **endpoint_attributes(2, operation.end),
                "HiddenPower": "N",
                "CanUnhide": "N",
                "Arrows": "None",
                "Group": "-1",
                "Selected": "N",
            },
        )
        points = ET.SubElement(wire, "Points")
        previous = None
        for point in operation.points:
            direction = (
                "-1"
                if previous is None
                else "0"
                if math.isclose(point.y, previous.y, abs_tol=1e-6)
                else "1"
            )
            ET.SubElement(
                points,
                "Point",
                {"X": f"{point.x:.9g}", "Y": f"{point.y:.9g}", "Dir": direction},
            )
            previous = point
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def label_alignment(
    point: tuple[float, float],
    sheet: int,
    specs: list[WireSpec],
) -> str:
    for spec in specs:
        if spec.sheet != sheet:
            continue
        if spec.end is None and spec.points[-1] == point:
            previous = spec.points[-2]
        elif spec.start is None and spec.points[0] == point:
            previous = spec.points[1]
        else:
            continue
        if point[0] < previous[0]:
            return "Right"
        if point[0] > previous[0]:
            return "Left"
        return "Center"
    return "Center"


def append_graphic(
    shapes: ET.Element,
    *,
    shape_type: str,
    sheet: int,
    points: tuple[tuple[float, float], ...],
) -> None:
    shape = ET.SubElement(
        shapes,
        "Shape",
        {
            "Enabled": "Y",
            "Id": str(len(shapes.findall("./Shape"))),
            "Type": shape_type,
            "Sheet": str(sheet),
            "LineWidth": "0.1",
            "NetId": "-1",
            "BusId": "-1",
            "Group": "-1",
            "Selected": "N",
            "Locked": "N",
        },
    )
    point_container = ET.SubElement(shape, "Points")
    for x, y in points:
        ET.SubElement(point_container, "Point", {"X": f"{x:g}", "Y": f"{y:g}"})


def append_text(
    shapes: ET.Element,
    *,
    sheet: int,
    x: float,
    y: float,
    text: str,
    font_size: int = 6,
    horizontal_align: str = "Center",
    vertical_align: str = "Center",
) -> None:
    shape = ET.SubElement(
        shapes,
        "Shape",
        {
            "Enabled": "Y",
            "Id": str(len(shapes.findall("./Shape"))),
            "Type": "Text",
            "Sheet": str(sheet),
            "Angle": "0",
            "HorzAlign": horizontal_align,
            "VertAlign": vertical_align,
            "TextAlign": horizontal_align,
            "FontVector": "Y",
            "FontSize": str(font_size),
            "FontWidth": "-2",
            "FontScale": "1",
            "LineSpacing": "1.2",
            "NetId": "-1",
            "BusId": "-1",
            "Group": "-1",
            "Selected": "N",
            "Locked": "N",
        },
    )
    points = ET.SubElement(shape, "Points")
    ET.SubElement(points, "Point", {"X": f"{x:g}", "Y": f"{y:g}"})
    lines = ET.SubElement(shape, "TextLines")
    ET.SubElement(lines, "TextLine").text = text


def append_overview(document: DipTraceDocument) -> DipTraceDocument:
    root = document.root
    sheet = next(
        item
        for item in root.findall("./Schematic/SheetSettings/Sheets/Sheet")
        if item.findtext("./Name") == "SYSTEM_OVERVIEW"
    )
    sheet_id = int(sheet.findtext("./Id") or "0")
    shapes = root.find("./Schematic/Shapes")
    assert shapes is not None
    blocks = (
        ("USB_POWER", "J1 - TPS63802", -105.0, -20.0, -60.0, 20.0),
        ("USB_UART", "CP2102", -45.0, -20.0, 0.0, 20.0),
        ("MCU_ISP", "ATTINY85 - ISP", 15.0, -20.0, 60.0, 20.0),
        ("IO", "J3", 75.0, -20.0, 120.0, 20.0),
    )
    append_text(shapes, sheet=sheet_id, x=7.5, y=64.0, text="SYSTEM OVERVIEW", font_size=10)
    append_text(
        shapes,
        sheet=sheet_id,
        x=7.5,
        y=55.0,
        text="Cross-sheet power and signal map",
        font_size=6,
    )
    for title, description, min_x, min_y, max_x, max_y in blocks:
        append_graphic(
            shapes,
            shape_type="Rectangle",
            sheet=sheet_id,
            points=((min_x, min_y), (max_x, max_y)),
        )
        center_x = (min_x + max_x) / 2.0
        append_text(shapes, sheet=sheet_id, x=center_x, y=11.0, text=title, font_size=7)
        append_text(shapes, sheet=sheet_id, x=center_x, y=3.0, text=description, font_size=5)

    for start_x, end_x, labels in (
        (-60.0, -45.0, ((7.0, "USB_D+"), (0.0, "USB_D-"))),
        (0.0, 15.0, ((8.0, "CP2102_TXD"), (1.0, "CP2102_RXD"), (-6.0, "RESET"))),
        (
            60.0,
            75.0,
            ((9.0, "PB0_MOSI"), (3.0, "PB1_MISO"), (-3.0, "PB2_SCK"), (-9.0, "RESET")),
        ),
    ):
        for y, label in labels:
            append_graphic(
                shapes,
                shape_type="Line",
                sheet=sheet_id,
                points=((start_x, y), (end_x, y)),
            )
            append_text(
                shapes,
                sheet=sheet_id,
                x=(start_x + end_x) / 2.0,
                y=y + 2.0,
                text=label,
                font_size=4,
                vertical_align="Bottom",
            )

    centers = (-82.5, -22.5, 37.5, 97.5)
    append_graphic(
        shapes,
        shape_type="Line",
        sheet=sheet_id,
        points=((-82.5, 40.0), (97.5, 40.0)),
    )
    append_graphic(
        shapes,
        shape_type="Line",
        sheet=sheet_id,
        points=((-82.5, -40.0), (97.5, -40.0)),
    )
    for center_x in centers:
        append_graphic(
            shapes,
            shape_type="Line",
            sheet=sheet_id,
            points=((center_x, 20.0), (center_x, 40.0)),
        )
        append_graphic(
            shapes,
            shape_type="Line",
            sheet=sheet_id,
            points=((center_x, -20.0), (center_x, -40.0)),
        )
    append_text(shapes, sheet=sheet_id, x=-70.0, y=43.0, text="+3V3", font_size=5)
    append_text(shapes, sheet=sheet_id, x=-70.0, y=-37.0, text="GND", font_size=5)
    append_text(
        shapes,
        sheet=sheet_id,
        x=7.5,
        y=-55.0,
        text="DOCUMENTATION ONLY - no electrical connectivity",
        font_size=5,
    )
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def annotate_rotated_parts(document: DipTraceDocument) -> DipTraceDocument:
    root = document.root
    shapes = root.find("./Schematic/Shapes")
    assert shapes is not None
    annotations = {
        "C1": ((-5.0, 2.5), (-5.0, -2.5)),
        "C2": ((4.0, 2.5), (4.0, -2.5)),
        "C3": ((4.0, 2.5), (4.0, -2.5)),
        "C4": ((4.0, 2.5), (4.0, -2.5)),
        "R1": ((4.0, 2.5), (4.0, -2.5)),
        "R2": ((3.0, 0.0), (3.0, -5.0)),
        "L1": ((6.0, 3.0), (6.0, -3.0)),
        "C5": ((4.0, 2.5), (4.0, -2.5)),
    }
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        if refdes not in annotations:
            continue
        for tag in ("RefDesMarking", "ValueMarking"):
            marking_element = part.find(f"./{tag}")
            assert marking_element is not None
            marking_element.set("Show", "Hide")
        for text, (dx, dy) in zip(
            (refdes, part.findtext("./Value") or ""),
            annotations[refdes],
            strict=True,
        ):
            append_text(
                shapes,
                sheet=int(part.get("Sheet", "0")),
                x=float(part.get("X", "0")) + dx,
                y=float(part.get("Y", "0")) + dy,
                text=text,
                font_size=6,
                horizontal_align="Right" if dx < 0 else "Left",
            )
    return DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def content_bounds(document: DipTraceDocument, sheet: int) -> BBox:
    boxes = [
        BBox(min_x, min_y, max_x, max_y)
        for part_sheet, min_x, min_y, max_x, max_y in component_boxes(document).values()
        if part_sheet == sheet
    ]
    boxes.extend(_text_obstacles(document, sheet))
    for shape in document.root.findall("./Schematic/Shapes/Shape"):
        if shape.get("Sheet", "0") != str(sheet) or shape.get("Type") == "Text":
            continue
        shape_points = [
            Point(float(point.get("X", "0")), float(point.get("Y", "0")))
            for point in shape.findall("./Points/Point")
        ]
        if shape_points:
            boxes.append(BBox.from_points(shape_points))
    points = [
        (float(point.get("X", "0")), float(point.get("Y", "0")))
        for wire in document.root.findall("./Schematic/Nets/Net/Wires/Wire")
        if int(wire.get("Sheet", "0")) == sheet
        for point in wire.findall("./Points/Point")
    ]
    if points:
        boxes.append(
            BBox(
                min(x for x, _ in points),
                min(y for _, y in points),
                max(x for x, _ in points),
                max(y for _, y in points),
            )
        )
    assert boxes, sheet
    return BBox(
        min(box.min_x for box in boxes),
        min(box.min_y for box in boxes),
        max(box.max_x for box in boxes),
        max(box.max_y for box in boxes),
    )


def center_sheet_content(
    document: DipTraceDocument,
) -> tuple[DipTraceDocument, dict[int, tuple[float, float]]]:
    bounds = schematic_sheet_usable_bounds(build_snapshot(document))
    shifts = {
        int(sheet): (
            page.center.x - content_bounds(document, int(sheet)).center.x,
            page.center.y - content_bounds(document, int(sheet)).center.y,
        )
        for sheet, page in bounds.items()
    }
    root = document.root
    for part in root.findall("./Schematic/Components/Part"):
        dx, dy = shifts[int(part.get("Sheet", "0"))]
        part.set("X", f"{float(part.get('X', '0')) + dx:.9g}")
        part.set("Y", f"{float(part.get('Y', '0')) + dy:.9g}")
    for wire in root.findall("./Schematic/Nets/Net/Wires/Wire"):
        dx, dy = shifts[int(wire.get("Sheet", "0"))]
        for point in wire.findall("./Points/Point"):
            point.set("X", f"{float(point.get('X', '0')) + dx:.9g}")
            point.set("Y", f"{float(point.get('Y', '0')) + dy:.9g}")
    for shape in root.findall("./Schematic/Shapes/Shape"):
        dx, dy = shifts[int(shape.get("Sheet", "0"))]
        for point in shape.findall("./Points/Point"):
            point.set("X", f"{float(point.get('X', '0')) + dx:.9g}")
            point.set("Y", f"{float(point.get('Y', '0')) + dy:.9g}")
    centered = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    for sheet, page in bounds.items():
        assert page.contains_bbox(content_bounds(centered, int(sheet)).expand(5.0)), sheet
    return centered, shifts


def main() -> None:
    document = DipTraceDocument.load(PATH, 134_217_728)
    cleaned = clean_visuals(document.raw_bytes)
    actual = {
        part.findtext("./RefDes") for part in cleaned.root.findall("./Schematic/Components/Part")
    }
    assert set(PLACEMENT) == actual
    placement_operations = [
        MoveComponentsOperation(
            selector=QuerySelector(refdes=[refdes]),
            absolute_x=x,
            absolute_y=y,
        )
        for refdes, (x, y) in PLACEMENT.items()
    ]
    placement_operations.extend(
        RotateComponentsOperation(
            selector=QuerySelector(refdes=[refdes]),
            angle_deg=angle,
            mode="absolute",
            allowed_angles=[0.0, 90.0, 180.0, 270.0],
        )
        for refdes, angle in ROTATION.items()
    )
    placed = apply_instance_flips(
        apply_semantic_operations(cleaned, placement_operations).document
    )

    ground_groups = [
        (0, (("J1", 4), ("J1", 5)), (60.0, 154.92)),
        (0, (("C1", 1),), (62.0, 134.84)),
        (0, (("U3", 1), ("U3", 2)), (65.0, 160.0)),
        (0, (("R2", 1),), (68.0, 127.6)),
        (0, (("U3", 7),), (129.05, 160.0)),
        (0, (("C2", 1),), (130.0, 127.3)),
        (1, (("C3", 1),), (65.0, 172.3)),
        (1, (("C4", 1),), (82.0, 172.3)),
        (1, (("R5", 0),), (68.0, 140.0)),
        (1, (("U2", 2), ("U2", 28)), (98.0, 133.41)),
        (2, (("U1", 3),), (205.0, 157.46)),
        (2, (("C5", 1),), (207.54, 147.3)),
        (2, (("J2", 5),), (70.0, 153.65)),
        (3, (("J3", 7),), (105.0, 143.49)),
    ]
    with_ground, ground_mapping = add_ground_symbols(placed, ground_groups)
    by_net = endpoints(with_ground)
    index = endpoint_index(by_net)

    specs: list[WireSpec] = []
    labels: list[tuple[str, int, tuple[float, float]]] = []

    # USB_POWER
    specs.append(wire(index, "VBUS", 0, ("J1", 0), ("U3", 0)))
    specs.append(
        wire(
            index,
            "VBUS",
            0,
            ("C1", 0),
            None,
            free_end=(62.0, 165.08),
        )
    )
    item, point = port(index, "VBUS", 0, ("U3", 9), 7.62)
    specs.append(item)
    labels.append(("VBUS", 0, point))
    for net, key in (("USB_D-", ("J1", 1)), ("USB_D+", ("J1", 2))):
        item, point = port(index, net, 0, key)
        specs.append(item)
        labels.append((net, 0, point))
    specs.extend(
        (
            wire(
                index,
                "TPS_L1",
                0,
                ("U3", 8),
                ("L1", 0),
                (137.079, 162.54),
                (137.079, 167.62),
                (139.619, 167.62),
            ),
            wire(
                index,
                "TPS_L2",
                0,
                ("U3", 6),
                ("L1", 1),
                (124.0, 157.46),
                (124.0, 152.38),
                (139.619, 152.38),
            ),
            wire(
                index,
                "TPS_FB",
                0,
                ("U3", 3),
                None,
                (85.0, 157.46),
                (85.0, 143.5),
                free_end=(68.0, 143.5),
            ),
            wire(index, "TPS_FB", 0, ("R1", 1), ("R2", 0)),
            wire(
                index,
                "TPS_PG",
                0,
                ("U3", 4),
                ("R3", 0),
                (97.8, 154.92),
                (97.8, 140.0),
            ),
        )
    )
    specs.append(
        wire(
            index,
            "+3V3",
            0,
            ("U3", 5),
            None,
            (122.7, 154.92),
            free_end=(122.7, 149.84),
        )
    )
    labels.append(("+3V3", 0, (122.7, 149.84)))
    item, point = port(index, "+3V3", 0, ("C2", 0), 2.54)
    specs.append(item)
    labels.append(("+3V3", 0, point))
    item, point = port(index, "+3V3", 0, ("R1", 0), 1.27)
    specs.append(item)
    labels.append(("+3V3", 0, point))
    specs.append(
        wire(
            index,
            "+3V3",
            0,
            ("R3", 1),
            None,
            (79.34, 140.0),
            (79.34, 136.9),
            free_end=(76.8, 136.9),
        )
    )
    labels.append(("+3V3", 0, (76.8, 136.9)))

    # USB_UART
    specs.extend(
        (
            wire(index, "+3V3", 1, ("U2", 5), None, free_end=(100.95, 176.59)),
            wire(
                index,
                "+3V3",
                1,
                None,
                ("U2", 6),
                (104.76, 176.59),
                (104.76, 171.51),
                free_start=(100.95, 176.59),
            ),
            wire(index, "CP2102_VBUS", 1, ("R4", 0), ("R5", 1)),
            wire(
                index,
                "CP2102_VBUS",
                1,
                ("U2", 7),
                None,
                (49.0, 161.35),
                free_end=(49.0, 150.0),
            ),
            wire(index, "CP2102_DTR", 1, ("U2", 27), ("C6", 0)),
        )
    )
    labels.append(("+3V3", 1, (100.95, 176.59)))
    for key in (("C3", 0), ("C4", 0)):
        item, point = port(index, "+3V3", 1, key, 5.08)
        specs.append(item)
        labels.append(("+3V3", 1, point))
    item, point = port(index, "VBUS", 1, ("R4", 1), 5.08)
    specs.append(item)
    labels.append(("VBUS", 1, point))
    for net, key in (
        ("USB_D-", ("U2", 4)),
        ("USB_D+", ("U2", 3)),
        ("CP2102_RXD", ("U2", 24)),
        ("CP2102_TXD", ("U2", 25)),
        ("RESET", ("C6", 1)),
    ):
        item, point = port(index, net, 1, key)
        specs.append(item)
        labels.append((net, 1, point))

    # MCU_ISP. Signal names genuinely continue to the other sheets, so short
    # ports are clearer here than crossing the incompatible J2/U1 pin orders.
    for key, length in ((("U1", 7), 7.62), (("C5", 0), 2.54)):
        item, point = port(index, "+3V3", 2, key, length)
        specs.append(item)
        labels.append(("+3V3", 2, point))
    specs.append(
        wire(
            index,
            "RESET",
            2,
            ("R6", 0),
            ("U1", 0),
            (131.98, 149.84),
            (131.98, 154.92),
        )
    )
    item, point = port(index, "+3V3", 2, ("R6", 1), 5.08)
    specs.append(item)
    labels.append(("+3V3", 2, point))
    specs.append(
        wire(
            index,
            "+3V3",
            2,
            ("J2", 1),
            None,
            free_end=(76.0, 163.81),
        )
    )
    labels.append(("+3V3", 2, (76.0, 163.81)))
    for net, key in (
        ("CP2102_TXD", ("U1", 1)),
        ("CP2102_RXD", ("U1", 2)),
        ("PB0_MOSI", ("U1", 4)),
        ("PB1_MISO", ("U1", 5)),
        ("PB2_SCK", ("U1", 6)),
        ("PB1_MISO", ("J2", 0)),
        ("PB2_SCK", ("J2", 2)),
        ("PB0_MOSI", ("J2", 3)),
        ("RESET", ("J2", 4)),
    ):
        item, point = port(index, net, 2, key, 7.62)
        specs.append(item)
        labels.append((net, 2, point))

    # IO: every non-ground pin is intentionally a cross-sheet breakout.
    specs.append(
        wire(index, "+3V3", 3, ("J3", 6), None, free_end=(98.0, 153.65))
    )
    labels.append(("+3V3", 3, (98.0, 153.65)))
    for net, key in (
        ("CP2102_TXD", ("J3", 3)),
        ("CP2102_RXD", ("J3", 4)),
        ("RESET", ("J3", 5)),
        ("PB0_MOSI", ("J3", 0)),
        ("PB1_MISO", ("J3", 1)),
        ("PB2_SCK", ("J3", 2)),
    ):
        item, point = port(index, net, 3, key)
        specs.append(item)
        labels.append((net, 3, point))

    # Native GND ports, always below the local item or block.
    ground_routes = {
        ("J1", 4): ((60.0, 160.0),),
        ("J1", 5): (),
        ("C1", 1): (),
        ("U3", 1): ((65.0, 162.54),),
        ("U3", 2): (),
        ("R2", 1): (),
        ("U3", 7): (),
        ("C2", 1): (),
        ("C3", 1): (),
        ("C4", 1): (),
        ("R5", 0): ((68.0, 150.0),),
        ("U2", 2): ((98.0, 135.95),),
        ("U2", 28): (),
        ("U1", 3): (),
        ("C5", 1): (),
        ("J2", 5): (),
        ("J3", 7): ((105.0, 151.11),),
    }
    for symbol_refdes, key, terminal in ground_mapping:
        specs.append(
            wire(
                index,
                "GND",
                index[key].sheet,
                key,
                (symbol_refdes, 0),
                *ground_routes[key],
            )
        )
        actual_terminal = pin_point(index, (symbol_refdes, 0))
        assert all(
            math.isclose(actual, expected, abs_tol=1e-6)
            for actual, expected in zip(actual_terminal, terminal, strict=True)
        )

    with_ports, port_mapping = add_named_net_ports(with_ground, labels, specs)
    specs = attach_named_ports(specs, port_mapping)
    by_net = endpoints(with_ports)
    index = endpoint_index(by_net)
    for key, port_key in port_mapping.items():
        actual_terminal = pin_point(index, port_key)
        assert all(
            math.isclose(actual, expected, abs_tol=1e-6)
            for actual, expected in zip(actual_terminal, key[2], strict=True)
        )

    boxes = component_boxes(with_ports)
    stubs = pin_stubs(with_ports)
    net_by_pin = {
        (endpoint.refdes, endpoint.pin): net
        for net, net_endpoints in by_net.items()
        for endpoint in net_endpoints
    }
    planned: list[tuple[int, str, tuple[float, float], tuple[float, float]]] = []
    for spec in specs:
        assert len(spec.points) >= 2
        assert_pin_escape(spec, index)
        assert not body_intersections(spec.points, spec.sheet, boxes), (
            spec,
            body_intersections(spec.points, spec.sheet, boxes),
        )
        assert not unrelated_pin_hits(spec, stubs, net_by_pin), (
            spec,
            unrelated_pin_hits(spec, stubs, net_by_pin),
        )
        assert crossing_count(spec, planned) == 0, spec
        planned.extend((spec.sheet, spec.net, a, b) for a, b in segments(spec.points))

    wire_operations = [
        AddWireOperation(
            net=spec.net,
            points=[{"x": x, "y": y} for x, y in spec.points],
            start=(
                {"type": "Free"}
                if spec.start is None
                else {"type": "Pin", "refdes": spec.start[0], "pin": spec.start[1]}
            ),
            end=(
                {"type": "Free"}
                if spec.end is None
                else {"type": "Pin", "refdes": spec.end[0], "pin": spec.end[1]}
            ),
            sheet=spec.sheet,
        )
        for spec in specs
    ]
    wired = append_wires(with_ports, wire_operations)
    documented = append_overview(annotate_rotated_parts(wired))
    result, shifts = center_sheet_content(documented)
    PATH.write_bytes(result.raw_bytes)
    print(
        f"manual_wires={len(specs)} labels={len(labels)} "
        f"crossings=0 body_hits=0 foreign_pin_hits=0 "
        f"centered_sheets={len(shifts)} sha256={result.sha256}"
    )


if __name__ == "__main__":
    main()
