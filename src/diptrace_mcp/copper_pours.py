from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass

from .adapters import build_snapshot
from .errors import EditError
from .geometry import BBox, Point, from_mm, point_in_polygon, point_to_segment_distance
from .xml_document import DipTraceDocument, RawTreeSnapshot

_STITCH_VIA_NAME = "MCP Ground Stitch Via"


@dataclass(frozen=True, slots=True)
class CopperPourResult:
    document: DipTraceDocument
    pour_count: int
    stitch_via_count: int


def add_copper_pours(
    document: DipTraceDocument,
    *,
    net: str,
    layers: Iterable[str],
    clearance_mm: float = 0.2,
    board_clearance_mm: float = 0.2,
    spoke_width_mm: float = 0.3,
    stitch_pitch_mm: float | None = None,
    stitch_edge_mm: float = 1.0,
) -> CopperPourResult:
    """Assign full-board copper pours and optional ground stitching vias."""

    if document.kind != "pcb":
        raise EditError("Copper pours require a PCB document")
    if not net.strip():
        raise EditError("Copper-pour net must not be empty")
    layer_values = tuple(dict.fromkeys(value.strip() for value in layers if value.strip()))
    if not layer_values:
        raise EditError("At least one copper-pour layer is required")
    if clearance_mm < 0 or board_clearance_mm < 0 or stitch_edge_mm < 0:
        raise EditError("Copper-pour clearances must be non-negative")
    if spoke_width_mm <= 0:
        raise EditError("Thermal-spoke width must be positive")
    if stitch_pitch_mm is not None and stitch_pitch_mm <= 0:
        raise EditError("Stitch pitch must be positive")

    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    raw_tree = RawTreeSnapshot.capture(working)
    board = working.container
    net_element = _unique_named(board.findall("./Nets/Net"), net, "net")
    layer_elements = [
        _unique_named(board.findall("./CopperLayers/Lay"), value, "layer") for value in layer_values
    ]
    outline = board.find("./BoardOutline/Points")
    if outline is None or len(outline.findall("./Point")) < 3:
        raise EditError("Copper pours require a board outline with at least three points")

    components = board.find("./Components")
    pours = board.find("./CopperPours")
    if components is None or pours is None:
        raise EditError("PCB document is missing Components or CopperPours")
    for component in list(components):
        if component.findtext("./Name") == _STITCH_VIA_NAME:
            components.remove(component)

    net_id = net_element.get("Id", "")
    next_pour_id = _next_numeric_id(pours.findall("./CopperPour"))
    for layer in layer_elements:
        layer_id = layer.get("Id", "")
        matches = [
            item
            for item in pours.findall("./CopperPour")
            if item.get("NetId") == net_id and item.get("Lay") == layer_id
        ]
        if len(matches) > 1:
            raise EditError(f"Multiple pours already use net {net!r} on layer {layer_id!r}")
        if matches:
            pour = matches[0]
            pour_id = pour.get("Id", str(next_pour_id))
            pour.clear()
            pour.set("Id", pour_id)
        else:
            pour = ET.SubElement(pours, "CopperPour")
            pour.set("Id", str(next_pour_id))
            next_pour_id += 1
        pour.attrib.update(
            {
                "NetId": net_id,
                "Lay": layer_id,
                "Priority": "0",
                "Poured": "Y",
                "Type": "Solid",
                "Clearance": _number(clearance_mm, working.units),
                "UseNetClearance": "N",
                "BoardClearance": _number(board_clearance_mm, working.units),
                "LineWidth": _number(0.1, working.units),
                "LineSpacing": _number(0.1, working.units),
                "MinimumArea": _area_number(1.0, working.units),
                "Spoke": "4 spoke",
                "SpokeWidth": _number(spoke_width_mm, working.units),
                "ViaDirect": "Y",
                "SMD_Separate": "N",
                "SMD_Spoke": "4 spoke",
                "SMD_SpokeWidth": _number(spoke_width_mm, working.units),
                "RatlineMode": "Automaticaly",
                "SnapToBoard": "Y",
                "IslandRegion": "N",
                "IslandInternal": "N",
                "IslandConnection": "N",
                "RegionsDone": "N",
                "Locked": "N",
                "Selected": "N",
            }
        )
        boundary = ET.SubElement(pour, "Points")
        for outline_point in outline.findall("./Point"):
            ET.SubElement(
                boundary,
                "Point",
                {
                    key: value
                    for key, value in outline_point.attrib.items()
                    if key in {"X", "Y"}
                },
            )

    stitch_points: list[Point] = []
    if stitch_pitch_mm is not None:
        stitch_points = _stitch_points(
            working,
            pitch=stitch_pitch_mm,
            edge=stitch_edge_mm,
            clearance=clearance_mm,
        )
        via_style = board.find("./ViaStyles/ViaStyle")
        if via_style is None or not via_style.get("Id"):
            raise EditError("Ground stitching requires a PCB ViaStyle")
        next_component_id = _next_numeric_id(components.findall("./Component"))
        for index, point in enumerate(stitch_points, start=1):
            via = ET.SubElement(
                components,
                "Component",
                {
                    "Id": str(next_component_id),
                    "Type": "Via",
                    "ViaStyle": via_style.get("Id", "0"),
                    "X": _number(point.x, working.units),
                    "Y": _number(point.y, working.units),
                    "Locked": "N",
                    "Selected": "N",
                },
            )
            next_component_id += 1
            ET.SubElement(via, "RefDes").text = f"GNDV{index}"
            ET.SubElement(via, "Name").text = _STITCH_VIA_NAME
            pads = ET.SubElement(via, "Pads")
            ET.SubElement(pads, "Pad", {"Id": "1", "NetId": net_id})

    raw_bytes = raw_tree.compile(working.root, working.path)
    return CopperPourResult(
        document=DipTraceDocument.from_bytes(working.path, raw_bytes),
        pour_count=len(layer_elements),
        stitch_via_count=len(stitch_points),
    )


def _unique_named(elements: list[ET.Element], value: str, kind: str) -> ET.Element:
    folded = value.casefold()
    matches = [
        item
        for item in elements
        if item.get("Id", "").casefold() == folded
        or (item.findtext("./Name") or "").casefold() == folded
    ]
    if len(matches) != 1:
        raise EditError(f"Unique copper-pour {kind} was not found: {value}")
    return matches[0]


def _next_numeric_id(elements: list[ET.Element]) -> int:
    ids = [int(value) for item in elements if (value := item.get("Id", "")).isdigit()]
    return max(ids, default=-1) + 1


def _number(value_mm: float, units: str) -> str:
    return f"{from_mm(value_mm, units):.9g}"


def _area_number(value_mm2: float, units: str) -> str:
    scale = from_mm(1.0, units)
    return f"{value_mm2 * scale * scale:.9g}"


def _axis_points(start: float, end: float, pitch: float) -> list[float]:
    if start > end:
        return []
    count = math.floor((end - start) / pitch)
    values = [start + index * pitch for index in range(count + 1)]
    if not values or end - values[-1] > 1e-6:
        values.append(end)
    return values


def _stitch_points(
    document: DipTraceDocument,
    *,
    pitch: float,
    edge: float,
    clearance: float,
) -> list[Point]:
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    outline = snapshot.board.outline
    if outline is None:
        return []
    polygon = [Point(**value) for value in outline["points"]]
    box = BBox(**outline["bbox"])
    via_style = snapshot.board.via_styles[0] if snapshot.board.via_styles else None
    radius = (via_style.diameter_mm or 0.6) / 2.0 if via_style is not None else 0.3
    inset = edge + radius
    xs = _axis_points(box.min_x + inset, box.max_x - inset, pitch)
    ys = _axis_points(box.min_y + inset, box.max_y - inset, pitch)
    if len(xs) * len(ys) > 2_048:
        raise EditError("Ground-stitch candidate count exceeds 2048")
    obstacles = [
        BBox(**record.bbox).expand(clearance + radius)
        for record in (
            snapshot.board.components
            + snapshot.board.pads
            + snapshot.board.holes
            + snapshot.board.traces
            + snapshot.board.vias
            + snapshot.board.keepouts
            + [
                item
                for item in snapshot.board.texts
                if "Silk" in (item.layer or "") and item.attributes.get("Show", "Show") != "Hide"
            ]
        )
        if record.bbox is not None
    ]
    segments = list(zip(polygon, polygon[1:] + polygon[:1], strict=True))
    points: list[Point] = []
    for x in xs:
        for y in ys:
            point = Point(x, y)
            if not point_in_polygon(point, polygon):
                continue
            if (
                min(point_to_segment_distance(point, start, end) for start, end in segments) + 1e-9
                < inset
            ):
                continue
            if any(obstacle.contains_point(point) for obstacle in obstacles):
                continue
            points.append(point)
    return points
