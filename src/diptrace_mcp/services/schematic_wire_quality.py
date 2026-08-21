from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..adapters import DocumentSnapshot
from ..errors import EditError
from ..geometry import BBox, Point, Transform, to_mm
from ..operations import AddWireOperation, WireEndpoint
from ..schematic_pin_geometry import resolve_document_schematic_pin_geometry
from ..xml_document import DipTraceDocument

if TYPE_CHECKING:
    from collections.abc import Iterable

_EPS = 1e-9
_ANCHOR_EPS_MM = 1e-6
_PART_VISUAL_MARGIN_MM = 3.0
_TEXT_MARGIN_MM = 0.6
_WIRE_LANE_GAP_MM = 0.75
_OUTER_LANE_GAP_MM = 2.0
_MAX_AXIS_COORDINATES = 80
_MAX_EXISTING_SEGMENTS = 512
_CROSSING_PENALTY = 100_000.0
_OVERLAP_PENALTY = 1_000_000.0
_BEND_PENALTY = 0.35
_MAX_CROSSING_CLEANUP_ADDED_BENDS = 2
_ESCAPE_STUB_MM = 5.0


@dataclass(frozen=True, slots=True)
class _Segment:
    start: Point
    end: Point

    @property
    def horizontal(self) -> bool:
        return math.isclose(self.start.y, self.end.y, abs_tol=_ANCHOR_EPS_MM)

    @property
    def vertical(self) -> bool:
        return math.isclose(self.start.x, self.end.x, abs_tol=_ANCHOR_EPS_MM)

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)


@dataclass(frozen=True, slots=True)
class _PathQuality:
    obstacle_hits: int
    overlaps: int
    crossings: int
    self_intersections: int
    diagonals: int
    bends: int
    length: float

    @property
    def score(self) -> tuple[int, int, int, int, int, int, float]:
        return (
            self.obstacle_hits,
            self.overlaps,
            self.crossings,
            self.self_intersections,
            self.diagonals,
            self.bends,
            self.length,
        )


def _same_point(first: Point, second: Point) -> bool:
    return math.isclose(first.x, second.x, abs_tol=_ANCHOR_EPS_MM) and math.isclose(
        first.y, second.y, abs_tol=_ANCHOR_EPS_MM
    )


def _escape_direction(first: Point, second: Point) -> tuple[str, int] | None:
    if math.isclose(first.y, second.y, abs_tol=_ANCHOR_EPS_MM):
        return "x", 1 if second.x > first.x else -1
    if math.isclose(first.x, second.x, abs_tol=_ANCHOR_EPS_MM):
        return "y", 1 if second.y > first.y else -1
    return None


def _preserves_pin_escape(
    operation: AddWireOperation,
    supplied: list[Point],
    candidate: list[Point],
    required_start: tuple[str, int] | None,
    required_end: tuple[str, int] | None,
    *,
    declared_fallback: bool,
) -> bool:
    """Check the candidate against the explicit pin-escape requirements.

    With ``declared_fallback`` (authored wires under enforcement) an endpoint
    without an explicit requirement keeps the supplied wire's own approach
    direction as the declared escape.  Planners pass ``False``: auto-generated
    initial routes choose that direction arbitrarily and must not veto
    compliant cleanup.
    """
    if operation.start.type == "Pin":
        candidate_start = _escape_direction(candidate[0], candidate[1])
        required = required_start
        if declared_fallback and required is None:
            required = _escape_direction(supplied[0], supplied[1])
        if required is not None and candidate_start != required:
            return False
    if operation.end.type == "Pin":
        candidate_end = _escape_direction(candidate[-2], candidate[-1])
        required = required_end
        if declared_fallback and required is None:
            required = _escape_direction(supplied[-2], supplied[-1])
        if required is not None and candidate_end != required:
            return False
    return True


def _matches_required_pin_escape(
    operation: AddWireOperation,
    points: list[Point],
    required_start: tuple[str, int] | None,
    required_end: tuple[str, int] | None,
) -> bool:
    return not (
        operation.start.type == "Pin"
        and required_start is not None
        and _escape_direction(points[0], points[1]) != required_start
    ) and not (
        operation.end.type == "Pin"
        and required_end is not None
        and _escape_direction(points[-2], points[-1]) != required_end
    )


def _orientation_escape(
    orientation_deg: float | None,
    *,
    outward: bool,
) -> tuple[str, int] | None:
    if orientation_deg is None:
        return None
    normalized = orientation_deg % 360.0
    quarter_turn = round(normalized / 90.0)
    snapped = (quarter_turn * 90.0) % 360.0
    delta = abs(((normalized - snapped + 180.0) % 360.0) - 180.0)
    if delta > 1e-3:
        return None
    radians = math.radians(snapped)
    dx, dy = math.cos(radians), math.sin(radians)
    if outward:
        dx, dy = -dx, -dy
    return ("x", 1 if dx > 0 else -1) if abs(dx) > abs(dy) else ("y", 1 if dy > 0 else -1)


def _simplify_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    for point in points:
        if not deduped or not _same_point(deduped[-1], point):
            deduped.append(point)
    if len(deduped) <= 2:
        return deduped
    result = [deduped[0]]
    for index in range(1, len(deduped) - 1):
        previous = result[-1]
        point = deduped[index]
        following = deduped[index + 1]
        collinear_x = math.isclose(previous.x, point.x, abs_tol=_EPS) and math.isclose(
            point.x, following.x, abs_tol=_EPS
        )
        collinear_y = math.isclose(previous.y, point.y, abs_tol=_EPS) and math.isclose(
            point.y, following.y, abs_tol=_EPS
        )
        if not (collinear_x or collinear_y):
            result.append(point)
    result.append(deduped[-1])
    return result


def _segments(points: list[Point]) -> list[_Segment]:
    return [_Segment(first, second) for first, second in zip(points, points[1:], strict=False)]


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _point_on_segment(point: Point, segment: _Segment) -> bool:
    return (
        abs(_cross(segment.start, segment.end, point)) <= _EPS
        and min(segment.start.x, segment.end.x) - _EPS
        <= point.x
        <= max(segment.start.x, segment.end.x) + _EPS
        and min(segment.start.y, segment.end.y) - _EPS
        <= point.y
        <= max(segment.start.y, segment.end.y) + _EPS
    )


def _segments_intersect(first: _Segment, second: _Segment) -> bool:
    c1 = _cross(first.start, first.end, second.start)
    c2 = _cross(first.start, first.end, second.end)
    c3 = _cross(second.start, second.end, first.start)
    c4 = _cross(second.start, second.end, first.end)
    if ((c1 > _EPS and c2 < -_EPS) or (c1 < -_EPS and c2 > _EPS)) and (
        (c3 > _EPS and c4 < -_EPS) or (c3 < -_EPS and c4 > _EPS)
    ):
        return True
    return (
        (abs(c1) <= _EPS and _point_on_segment(second.start, first))
        or (abs(c2) <= _EPS and _point_on_segment(second.end, first))
        or (abs(c3) <= _EPS and _point_on_segment(first.start, second))
        or (abs(c4) <= _EPS and _point_on_segment(first.end, second))
    )


def _collinear_overlap_length(first: _Segment, second: _Segment) -> float:
    if (
        abs(_cross(first.start, first.end, second.start)) > _EPS
        or abs(_cross(first.start, first.end, second.end)) > _EPS
    ):
        return 0.0
    if first.horizontal and second.horizontal:
        return max(
            0.0,
            min(max(first.start.x, first.end.x), max(second.start.x, second.end.x))
            - max(min(first.start.x, first.end.x), min(second.start.x, second.end.x)),
        )
    if first.vertical and second.vertical:
        return max(
            0.0,
            min(max(first.start.y, first.end.y), max(second.start.y, second.end.y))
            - max(min(first.start.y, first.end.y), min(second.start.y, second.end.y)),
        )
    return 0.0


def _segment_hits_box(segment: _Segment, box: BBox) -> bool:
    if segment.horizontal:
        if not box.min_y + _EPS < segment.start.y < box.max_y - _EPS:
            return False
        low = max(min(segment.start.x, segment.end.x), box.min_x)
        high = min(max(segment.start.x, segment.end.x), box.max_x)
        return high - low > _EPS
    if segment.vertical:
        if not box.min_x + _EPS < segment.start.x < box.max_x - _EPS:
            return False
        low = max(min(segment.start.y, segment.end.y), box.min_y)
        high = min(max(segment.start.y, segment.end.y), box.max_y)
        return high - low > _EPS
    if box.contains_point(segment.start) or box.contains_point(segment.end):
        return True
    corners = (
        Point(box.min_x, box.min_y),
        Point(box.max_x, box.min_y),
        Point(box.max_x, box.max_y),
        Point(box.min_x, box.max_y),
    )
    edges = (
        _Segment(corners[0], corners[1]),
        _Segment(corners[1], corners[2]),
        _Segment(corners[2], corners[3]),
        _Segment(corners[3], corners[0]),
    )
    return any(_segments_intersect(segment, edge) for edge in edges)


def _endpoint_matches_part(endpoint: WireEndpoint, part: Any) -> bool:
    if endpoint.type != "Pin":
        return False
    if endpoint.refdes is not None and (part.refdes or "").casefold() == endpoint.refdes.casefold():
        return True
    return endpoint.part_id is not None and endpoint.part_id in {
        part.stable_id,
        part.xml_id or "",
    }


def _pin_endpoint_key(
    snapshot: DocumentSnapshot,
    endpoint: WireEndpoint,
) -> tuple[str, int] | None:
    if endpoint.type != "Pin" or endpoint.pin is None or snapshot.schematic is None:
        return None
    matches = [part for part in snapshot.schematic.parts if _endpoint_matches_part(endpoint, part)]
    return (matches[0].stable_id, endpoint.pin) if len(matches) == 1 else None


def _part_obstacles(snapshot: DocumentSnapshot, operation: AddWireOperation) -> list[BBox]:
    if snapshot.schematic is None:
        return []
    result: list[BBox] = []
    for part in snapshot.schematic.parts:
        if str(part.attributes.get("sheet", "0")) != str(operation.sheet) or part.bbox is None:
            continue
        if _endpoint_matches_part(operation.start, part) or _endpoint_matches_part(
            operation.end, part
        ):
            continue
        result.append(BBox(**part.bbox).expand(_PART_VISUAL_MARGIN_MM))
    return result


def _endpoint_pin_envelopes(
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    pin_anchors: dict[tuple[str, int], Point],
) -> list[BBox]:
    """Keep cleanup routes from re-entering their own endpoint symbols."""
    if snapshot.schematic is None:
        return []
    result: list[BBox] = []
    for part in snapshot.schematic.parts:
        if not (
            _endpoint_matches_part(operation.start, part)
            or _endpoint_matches_part(operation.end, part)
        ):
            continue
        if part.bbox is not None:
            result.append(BBox(**part.bbox))
        points = [point for (part_id, _), point in pin_anchors.items() if part_id == part.stable_id]
        if len(points) < 2:
            continue
        box = BBox(
            min(point.x for point in points),
            min(point.y for point in points),
            max(point.x for point in points),
            max(point.y for point in points),
        )
        if box.width > _EPS and box.height > _EPS:
            result.append(box)
    return result


def _xml_mm(document: DipTraceDocument, value: str | None) -> float | None:
    if value is None:
        return None
    try:
        converted = to_mm(float(value), document.units)
    except ValueError:
        return None
    return converted if math.isfinite(converted) else None


def _text_bbox(
    document: DipTraceDocument,
    shape: Any,
    *,
    margin_mm: float = _TEXT_MARGIN_MM,
) -> BBox | None:
    point = shape.find("./Points/Point")
    if point is None:
        return None
    x = _xml_mm(document, point.get("X"))
    y = _xml_mm(document, point.get("Y"))
    if x is None or y is None:
        return None
    lines = [item.text or "" for item in shape.findall("./TextLines/TextLine")]
    longest = max((len(line) for line in lines), default=1)
    width_value = shape.get("TextWidth")
    height_value = shape.get("TextHeight")
    stored_width = _xml_mm(document, width_value)
    stored_height = _xml_mm(document, height_value)
    if (width_value is not None and stored_width is None) or (
        height_value is not None and stored_height is None
    ):
        return None
    needs_fallback = stored_width is None or stored_height is None
    if needs_fallback and (
        shape.get("FontVector", "Y") != "Y"
        or any(not 32 <= ord(character) <= 126 for line in lines for character in line)
    ):
        return None
    try:
        font_size = float(shape.get("FontSizeFloat", shape.get("FontSize", "10")))
        font_scale = float(shape.get("FontScale", "1"))
        font_width = float(shape.get("FontWidth", "-2"))
        line_spacing = float(shape.get("LineSpacing", "1.2"))
        if not all(
            math.isfinite(value)
            for value in (font_size, font_scale, font_width, line_spacing)
        ):
            return None
        stroke = (
            font_size / 12.0
            if font_width == -3
            else font_size / 8.5
            if font_width == -2
            else font_size / 6.0
            if font_width == -1
            else max(0.0, font_width)
        )
        font_height = max(0.1, (1.3627 * font_size + stroke) / 3.0)
        extra_line_height = (
            1.3627 * font_size / 2.45 + stroke
        ) * (line_spacing + 1.0) / 3.0
    except ValueError:
        return None
    width = stored_width if stored_width is not None else max(
        font_height,
        longest * 0.75 * font_height * font_scale,
    )
    height = stored_height if stored_height is not None else (
        font_height + max(0, len(lines) - 1) * extra_line_height
    )
    if not math.isfinite(width) or not math.isfinite(height):
        return None
    horizontal = shape.get("HorzAlign", "Left")
    min_x, max_x = (
        (x, x + width)
        if horizontal == "Left"
        else (x - width, x)
        if horizontal == "Right"
        else (x - width / 2.0, x + width / 2.0)
    )
    vertical = shape.get("VertAlign", "Bottom")
    min_y, max_y = (
        (y, y + height)
        if vertical == "Bottom"
        else (y - height, y)
        if vertical == "Top"
        else (y - height / 2.0, y + height / 2.0)
    )
    box = BBox(min_x, min_y, max_x, max_y)
    try:
        angle_deg = math.degrees(float(shape.get("Angle", "0")))
    except ValueError:
        return None
    if not math.isfinite(angle_deg):
        return None
    if angle_deg:
        box = Transform(origin_x=x, origin_y=y, rotation_deg=angle_deg).apply_bbox(box)
    result = box.expand(margin_mm)
    return result if all(math.isfinite(value) for value in result.as_dict().values()) else None


def _text_obstacles(document: DipTraceDocument, sheet: int) -> list[BBox]:
    shapes = [
        shape
        for shape in document.container.findall("./Shapes/Shape")
        if shape.get("Enabled", "Y") == "Y"
        and shape.get("Type") == "Text"
        and shape.get("Sheet", "0") == str(sheet)
    ]
    boxes = [_text_bbox(document, shape) for shape in shapes]
    if any(box is None for box in boxes):
        raise EditError("Cannot safely route around unmeasured schematic text")
    return [box for box in boxes if box is not None]


def _existing_wire_segments(snapshot: DocumentSnapshot, sheet: int) -> list[_Segment]:
    if snapshot.schematic is None:
        return []
    result: list[_Segment] = []
    for wire in snapshot.schematic.wires:
        if str(wire.attributes.get("sheet", "0")) != str(sheet):
            continue
        raw_points = wire.attributes.get("points", [])
        points = [
            Point(float(item["x"]), float(item["y"]))
            for item in raw_points
            if isinstance(item, dict) and "x" in item and "y" in item
        ]
        result.extend(_segments(points))
        if len(result) >= _MAX_EXISTING_SEGMENTS:
            return result[:_MAX_EXISTING_SEGMENTS]
    return result


def _wire_anchor(
    snapshot: DocumentSnapshot,
    endpoint: WireEndpoint,
    fallback: Point,
    pin_anchors: dict[tuple[str, int], Point] | None = None,
) -> Point:
    pin_anchors = pin_anchors or {}
    if endpoint.type == "Pin" and endpoint.pin is not None and snapshot.schematic is not None:
        key = _pin_endpoint_key(snapshot, endpoint)
        if key is not None:
            return pin_anchors.get(key, fallback)
        return fallback
    if endpoint.type != "Wire" or endpoint.wire_id is None:
        return fallback
    record = snapshot.objects.get(endpoint.wire_id)
    if record is None or record.kind != "wire":
        return fallback
    raw_points = record.attributes.get("points", [])
    if not isinstance(raw_points, list) or not raw_points:
        return fallback
    index = endpoint.point_index if endpoint.point_index is not None else len(raw_points) - 1
    if not 0 <= index < len(raw_points):
        return fallback
    item = raw_points[index]
    if not isinstance(item, dict) or "x" not in item or "y" not in item:
        return fallback
    anchor = Point(float(item["x"]), float(item["y"]))
    if index > 0:
        previous = raw_points[index - 1]
        if isinstance(previous, dict) and "x" in previous and "y" in previous:
            segment = _Segment(
                Point(float(previous["x"]), float(previous["y"])),
                anchor,
            )
            if segment.vertical and (
                abs(fallback.x - segment.start.x) <= _ANCHOR_EPS_MM
                and min(segment.start.y, segment.end.y) - _ANCHOR_EPS_MM
                <= fallback.y
                <= max(segment.start.y, segment.end.y) + _ANCHOR_EPS_MM
            ):
                return Point(segment.start.x, fallback.y)
            if segment.horizontal and (
                abs(fallback.y - segment.start.y) <= _ANCHOR_EPS_MM
                and min(segment.start.x, segment.end.x) - _ANCHOR_EPS_MM
                <= fallback.x
                <= max(segment.start.x, segment.end.x) + _ANCHOR_EPS_MM
            ):
                return Point(fallback.x, segment.start.y)
            if _point_on_segment(fallback, segment):
                return fallback
    if index == 0 and _same_point(fallback, anchor):
        return anchor
    raise EditError(
        f"Wire endpoint is not on referenced wire segment {index}",
        code="geometry_invalid",
        object_ids=[endpoint.wire_id],
    )


def _intentional_wire_touches(
    operation: AddWireOperation, start: Point, end: Point
) -> tuple[Point, ...]:
    result: list[Point] = []
    if operation.start.type == "Wire":
        result.append(start)
    if operation.end.type == "Wire":
        result.append(end)
    return tuple(result)


def _allowed_touch(candidate: _Segment, existing: _Segment, touches: tuple[Point, ...]) -> bool:
    if _collinear_overlap_length(candidate, existing) > _EPS:
        return False
    return any(
        (_same_point(candidate.start, point) or _same_point(candidate.end, point))
        and _point_on_segment(point, existing)
        for point in touches
    )


def _quality(
    points: list[Point],
    obstacles: list[BBox],
    existing: list[_Segment],
    touches: tuple[Point, ...],
) -> _PathQuality:
    path_segments = _segments(points)
    obstacle_hits = sum(
        _segment_hits_box(segment, box) for segment in path_segments for box in obstacles
    )
    overlaps = 0
    crossings = 0
    for segment in path_segments:
        for other in existing:
            if not _segments_intersect(segment, other):
                continue
            if _collinear_overlap_length(segment, other) > _EPS:
                overlaps += 1
            elif not _allowed_touch(segment, other, touches):
                crossings += 1
    self_intersections = 0
    for first_index, first in enumerate(path_segments):
        for second in path_segments[first_index + 2 :]:
            if _segments_intersect(first, second):
                self_intersections += 1
    return _PathQuality(
        obstacle_hits=obstacle_hits,
        overlaps=overlaps,
        crossings=crossings,
        self_intersections=self_intersections,
        diagonals=sum(not (segment.horizontal or segment.vertical) for segment in path_segments),
        bends=max(0, len(path_segments) - 1),
        length=sum(segment.length for segment in path_segments),
    )


def _bounded_axis(values: Iterable[float], start: float, end: float) -> list[float]:
    unique = sorted({round(float(value), 9) for value in values})
    if len(unique) <= _MAX_AXIS_COORDINATES:
        return unique
    low, high = sorted((start, end))

    def interval_distance(value: float) -> float:
        if low <= value <= high:
            return 0.0
        return min(abs(value - low), abs(value - high))

    kept = {round(start, 9), round(end, 9)}
    for value in sorted(unique, key=lambda item: (interval_distance(item), item)):
        kept.add(value)
        if len(kept) == _MAX_AXIS_COORDINATES:
            break
    return sorted(kept)


def _axes(
    start: Point,
    end: Point,
    obstacles: list[BBox],
    existing: list[_Segment],
) -> tuple[list[float], list[float]]:
    xs = {start.x, end.x}
    ys = {start.y, end.y}
    for box in obstacles:
        xs.update((box.min_x - _WIRE_LANE_GAP_MM, box.max_x + _WIRE_LANE_GAP_MM))
        ys.update((box.min_y - _WIRE_LANE_GAP_MM, box.max_y + _WIRE_LANE_GAP_MM))
    for segment in existing:
        for point in (segment.start, segment.end):
            xs.update((point.x - _WIRE_LANE_GAP_MM, point.x, point.x + _WIRE_LANE_GAP_MM))
            ys.update((point.y - _WIRE_LANE_GAP_MM, point.y, point.y + _WIRE_LANE_GAP_MM))
    xs.update((min(xs) - _OUTER_LANE_GAP_MM, max(xs) + _OUTER_LANE_GAP_MM))
    ys.update((min(ys) - _OUTER_LANE_GAP_MM, max(ys) + _OUTER_LANE_GAP_MM))
    return _bounded_axis(xs, start.x, end.x), _bounded_axis(ys, start.y, end.y)


def _node_blocked(point: Point, obstacles: list[BBox], anchors: tuple[Point, Point]) -> bool:
    if any(_same_point(point, anchor) for anchor in anchors):
        return False
    return any(
        box.min_x + _EPS < point.x < box.max_x - _EPS
        and box.min_y + _EPS < point.y < box.max_y - _EPS
        for box in obstacles
    )


def _wire_penalty(segment: _Segment, existing: list[_Segment], touches: tuple[Point, ...]) -> float:
    crossings = 0
    overlaps = 0
    for other in existing:
        if not _segments_intersect(segment, other):
            continue
        if _collinear_overlap_length(segment, other) > _EPS:
            overlaps += 1
        elif not _allowed_touch(segment, other, touches):
            crossings += 1
    return crossings * _CROSSING_PENALTY + overlaps * _OVERLAP_PENALTY


def _route(
    start: Point,
    end: Point,
    obstacles: list[BBox],
    existing: list[_Segment],
    touches: tuple[Point, ...],
    required_start: tuple[str, int] | None = None,
    required_end: tuple[str, int] | None = None,
) -> list[Point] | None:
    if _same_point(start, end):
        return None
    anchors = (start, end)
    xs, ys = _axes(start, end, obstacles, existing)
    for anchor, required in ((start, required_start), (end, required_end)):
        if required is None:
            continue
        axis, sign = required
        if axis == "x":
            xs.append(anchor.x + sign * _ESCAPE_STUB_MM)
        else:
            ys.append(anchor.y + sign * _ESCAPE_STUB_MM)
    xs = _bounded_axis(xs, start.x, end.x)
    ys = _bounded_axis(ys, start.y, end.y)
    nodes = {
        (x, y): Point(x, y)
        for x in xs
        for y in ys
        if not _node_blocked(Point(x, y), obstacles, anchors)
    }
    start_key = (round(start.x, 9), round(start.y, 9))
    end_key = (round(end.x, 9), round(end.y, 9))
    nodes[start_key] = start
    nodes[end_key] = end
    edges: dict[tuple[float, float], list[tuple[tuple[float, float], int, float]]] = {
        key: [] for key in nodes
    }

    # A wire may enter or leave its own endpoint anchor even when that anchor
    # sits inside the endpoint symbol's envelope (unresolved pins fall back to
    # the part centre); every other segment must respect the keep-out.
    anchor_containing_boxes = [
        [box for box in obstacles if box.contains_point(anchor)] for anchor in anchors
    ]

    def connect(keys: list[tuple[float, float]], direction: int) -> None:
        for first_key, second_key in zip(keys, keys[1:], strict=False):
            segment = _Segment(nodes[first_key], nodes[second_key])
            active = obstacles
            for anchor, exempt in zip(anchors, anchor_containing_boxes, strict=True):
                if _same_point(segment.start, anchor) or _same_point(segment.end, anchor):
                    active = [box for box in active if box not in exempt]
            if any(_segment_hits_box(segment, box) for box in active):
                continue
            cost = segment.length + _wire_penalty(segment, existing, touches)
            edges[first_key].append((second_key, direction, cost))
            edges[second_key].append((first_key, direction, cost))

    for y in ys:
        connect(sorted(key for key in nodes if math.isclose(key[1], y, abs_tol=_EPS)), 1)
    for x in xs:
        connect(
            sorted(
                (key for key in nodes if math.isclose(key[0], x, abs_tol=_EPS)),
                key=lambda key: key[1],
            ),
            2,
        )

    initial = (start_key, 0)
    distances = {initial: 0.0}
    previous: dict[tuple[tuple[float, float], int], tuple[tuple[float, float], int] | None] = {
        initial: None
    }
    queue: list[tuple[float, tuple[float, float], int]] = [(0.0, start_key, 0)]
    final: tuple[tuple[float, float], int] | None = None
    while queue:
        cost, key, direction = heapq.heappop(queue)
        state = (key, direction)
        if cost > distances.get(state, math.inf) + _EPS:
            continue
        if key == end_key:
            final = state
            break
        for next_key, next_direction, edge_cost in edges[key]:
            escape = _escape_direction(nodes[key], nodes[next_key])
            if key == start_key and required_start is not None and escape != required_start:
                continue
            if next_key == end_key and required_end is not None and escape != required_end:
                continue
            bend = _BEND_PENALTY if direction not in {0, next_direction} else 0.0
            candidate = cost + edge_cost + bend
            next_state = (next_key, next_direction)
            if candidate + _EPS >= distances.get(next_state, math.inf):
                continue
            distances[next_state] = candidate
            previous[next_state] = state
            heapq.heappush(queue, (candidate, next_key, next_direction))
    if final is None:
        return None
    keys: list[tuple[float, float]] = []
    cursor: tuple[tuple[float, float], int] | None = final
    while cursor is not None:
        keys.append(cursor[0])
        cursor = previous[cursor]
    keys.reverse()
    return _simplify_points([nodes[key] for key in keys])


def schematic_wire_pin_escape_satisfied(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
) -> bool:
    """Report whether the operation's points satisfy derivable pin-escape rules.

    Planners use this to keep escape-violating candidates out of accepted
    routes without raising, mirroring the hard check ``clean_schematic_wire_
    operation`` enforces for applied operations.
    """
    if snapshot.schematic is None or len(operation.points) < 2:
        return True
    pin_resolution = resolve_document_schematic_pin_geometry(document)
    pin_orientations = {
        (pin.part_id, pin.pin_index): getattr(pin, "absolute_orientation_deg", None)
        for pin in pin_resolution.pins
        if getattr(pin, "absolute_orientation_deg", None) is not None
    }
    start_key = _pin_endpoint_key(snapshot, operation.start)
    end_key = _pin_endpoint_key(snapshot, operation.end)
    required_start = _orientation_escape(
        pin_orientations.get(start_key) if start_key is not None else None,
        outward=True,
    )
    required_end = _orientation_escape(
        pin_orientations.get(end_key) if end_key is not None else None,
        outward=False,
    )
    points = [Point(item.x, item.y) for item in operation.points]
    return _matches_required_pin_escape(operation, points, required_start, required_end)


def clean_schematic_wire_operation(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    *,
    part_deltas: dict[str, Point] | None = None,
    enforce_pin_escape: bool = True,
) -> AddWireOperation:
    """Route a problematic authored wire around schematic visual obstacles.

    Clean orthogonal caller paths are preserved.  Rerouting is attempted when a
    path crosses/overlaps another wire, intersects a component/text obstacle,
    self-intersects, or contains a diagonal.  Component boxes are conservative
    proxies because current schematic models do not expose exact symbol/marking
    geometry.  The search is bounded and deterministic.

    ``part_deltas`` maps part ids to translations applied to a virtual snapshot;
    document-resolved pin anchors are translated by them so anchor snapping and
    pin-escape routing stay consistent with the snapshot's coordinates.

    ``enforce_pin_escape`` keeps the fail-closed raise for applied operations;
    non-mutating planners pass ``False`` so an unreachable escape requirement
    degrades to the measured route instead of aborting candidate scoring.  An
    operation carrying ``pin_escape_policy="best_effort"`` degrades the same
    way when it is applied, preserving connectivity-safe reroute replacements.
    """
    enforce_pin_escape = enforce_pin_escape and operation.pin_escape_policy == "enforce"
    if snapshot.schematic is None or len(operation.points) < 2:
        return operation
    supplied = _simplify_points([Point(item.x, item.y) for item in operation.points])
    if len(supplied) < 2:
        raise EditError("Schematic wire needs two distinct points", code="geometry_invalid")
    pin_resolution = resolve_document_schematic_pin_geometry(document)
    pin_anchors = {
        (pin.part_id, pin.pin_index): Point(**pin.absolute_position)
        for pin in pin_resolution.pins
        if pin.absolute_position is not None
    }
    if part_deltas:
        pin_anchors = {
            key: (
                Point(
                    anchor.x + part_deltas[key[0]].x,
                    anchor.y + part_deltas[key[0]].y,
                )
                if key[0] in part_deltas
                else anchor
            )
            for key, anchor in pin_anchors.items()
        }
    pin_orientations = {
        (pin.part_id, pin.pin_index): getattr(pin, "absolute_orientation_deg", None)
        for pin in pin_resolution.pins
        if getattr(pin, "absolute_orientation_deg", None) is not None
    }
    start_key = _pin_endpoint_key(snapshot, operation.start)
    end_key = _pin_endpoint_key(snapshot, operation.end)
    required_start = _orientation_escape(
        pin_orientations.get(start_key) if start_key is not None else None,
        outward=True,
    )
    required_end = _orientation_escape(
        pin_orientations.get(end_key) if end_key is not None else None,
        outward=False,
    )
    if enforce_pin_escape and (
        (start_key in pin_orientations and required_start is None)
        or (end_key in pin_orientations and required_end is None)
    ):
        raise EditError(
            "Orthogonal routing requires cardinal resolved pin orientations",
            code="geometry_invalid",
        )
    supplied[0] = _wire_anchor(snapshot, operation.start, supplied[0], pin_anchors)
    supplied[-1] = _wire_anchor(snapshot, operation.end, supplied[-1], pin_anchors)
    supplied = _simplify_points(supplied)
    if len(supplied) < 2:
        raise EditError(
            "Schematic wire endpoints collapse to one point",
            code="geometry_invalid",
        )
    start, end = supplied[0], supplied[-1]
    obstacles = [
        *_part_obstacles(snapshot, operation),
        *_endpoint_pin_envelopes(snapshot, operation, pin_anchors),
        *_text_obstacles(document, operation.sheet),
    ]
    existing = _existing_wire_segments(snapshot, operation.sheet)
    touches = _intentional_wire_touches(operation, start, end)
    original = _quality(supplied, obstacles, existing, touches)
    supplied_escape_valid = _matches_required_pin_escape(
        operation, supplied, required_start, required_end
    )
    repair_pin_escape = not supplied_escape_valid
    hard_clean = original.score[:5] == (0, 0, 0, 0, 0) and supplied_escape_valid
    ideal_bends = 0 if math.isclose(start.x, end.x) or math.isclose(start.y, end.y) else 1
    simplify_clean_detour = hard_clean and original.bends > ideal_bends
    if hard_clean and not simplify_clean_detour:
        cleaned = supplied
    else:
        candidate = _route(
            start,
            end,
            obstacles,
            existing,
            touches,
            required_start,
            required_end,
        )
        if candidate is None:
            cleaned = supplied
        else:
            candidate_quality = _quality(candidate, obstacles, existing, touches)
            crossing_only = (
                original.obstacle_hits == 0
                and original.overlaps == 0
                and original.crossings > 0
                and original.self_intersections == 0
                and original.diagonals == 0
            )
            cleaned = (
                candidate
                if _preserves_pin_escape(
                    operation,
                    supplied,
                    candidate,
                    required_start,
                    required_end,
                    # The declared approach binds only while the authored wire
                    # already satisfies its explicit escape requirements; a
                    # repair may change the approach to achieve compliance.
                    declared_fallback=enforce_pin_escape and supplied_escape_valid,
                )
                and (
                    candidate_quality.score < original.score
                    if not (simplify_clean_detour or repair_pin_escape)
                    else (
                        candidate_quality.score[:5] <= original.score[:5]
                        or (repair_pin_escape and not enforce_pin_escape)
                    )
                    and (
                        candidate_quality.bends < original.bends
                        or (
                            candidate_quality.bends == original.bends
                            and candidate_quality.length < original.length
                        )
                        # Pin-escape repair fixes a hard-rule violation: accept
                        # any candidate whose hard score does not regress; the
                        # router's bend penalty already keeps the shape tidy.
                        or repair_pin_escape
                    )
                )
                and (
                    not crossing_only
                    or candidate_quality.bends <= original.bends + _MAX_CROSSING_CLEANUP_ADDED_BENDS
                )
                else supplied
            )
    if not _matches_required_pin_escape(operation, cleaned, required_start, required_end):
        if enforce_pin_escape:
            raise EditError(
                "Schematic wire must leave each resolved pin away from its symbol body"
            )
        payload = operation.model_dump(mode="json")
        payload["points"] = [point.as_dict() for point in supplied]
        return AddWireOperation.model_validate(payload)
    payload = operation.model_dump(mode="json")
    payload["points"] = [point.as_dict() for point in cleaned]
    return AddWireOperation.model_validate(payload)


def _quality_add_wire_handler(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    from ..semantic_compiler import _apply_add_wire

    return _apply_add_wire(
        index,
        document,
        snapshot,
        clean_schematic_wire_operation(document, snapshot, operation),
        changed_ids,
    )


_INSTALLED = False


def install_schematic_wire_quality() -> None:
    """Install the quality wrapper without changing the public MCP contract."""
    global _INSTALLED
    if _INSTALLED:
        return
    from ..semantic_compiler import SEMANTIC_OPERATION_HANDLERS, _adapt_semantic_handler

    SEMANTIC_OPERATION_HANDLERS[AddWireOperation] = _adapt_semantic_handler(
        _quality_add_wire_handler
    )
    _INSTALLED = True
