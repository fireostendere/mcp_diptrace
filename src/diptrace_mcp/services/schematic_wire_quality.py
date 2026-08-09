from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..adapters import DocumentSnapshot
from ..geometry import BBox, Point, to_mm
from ..operations import AddWireOperation, WireEndpoint
from ..xml_document import DipTraceDocument

if TYPE_CHECKING:
    from collections.abc import Iterable

_EPS = 1e-9
_PART_VISUAL_MARGIN_MM = 2.0
_TEXT_MARGIN_MM = 0.5
_WIRE_LANE_GAP_MM = 0.75
_OUTER_LANE_GAP_MM = 2.0
_MAX_AXIS_COORDINATES = 96
_MAX_EXISTING_SEGMENTS = 512
_CROSSING_PENALTY = 100_000.0
_OVERLAP_PENALTY = 1_000_000.0
_BEND_PENALTY = 0.35


@dataclass(frozen=True, slots=True)
class _Segment:
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @property
    def horizontal(self) -> bool:
        return math.isclose(self.start.y, self.end.y, abs_tol=_EPS)

    @property
    def vertical(self) -> bool:
        return math.isclose(self.start.x, self.end.x, abs_tol=_EPS)


@dataclass(frozen=True, slots=True)
class _PathQuality:
    obstacle_hits: int
    overlaps: int
    crossings: int
    self_intersections: int
    diagonal_segments: int
    bends: int
    length: float

    def score(self) -> tuple[int, int, int, int, int, int, float]:
        return (
            self.obstacle_hits,
            self.overlaps,
            self.crossings,
            self.self_intersections,
            self.diagonal_segments,
            self.bends,
            self.length,
        )


def _same_point(first: Point, second: Point) -> bool:
    return math.isclose(first.x, second.x, abs_tol=_EPS) and math.isclose(
        first.y, second.y, abs_tol=_EPS
    )


def _simplify_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    for point in points:
        if not deduped or not _same_point(deduped[-1], point):
            deduped.append(point)
    if len(deduped) <= 2:
        return deduped
    simplified = [deduped[0]]
    for point in deduped[1:-1]:
        previous = simplified[-1]
        following = deduped[deduped.index(point) + 1]
        same_x = math.isclose(previous.x, point.x, abs_tol=_EPS) and math.isclose(
            point.x, following.x, abs_tol=_EPS
        )
        same_y = math.isclose(previous.y, point.y, abs_tol=_EPS) and math.isclose(
            point.y, following.y, abs_tol=_EPS
        )
        if not (same_x or same_y):
            simplified.append(point)
    simplified.append(deduped[-1])
    return simplified


def _path_segments(points: list[Point]) -> list[_Segment]:
    return [_Segment(start, end) for start, end in zip(points, points[1:], strict=False)]


def _cross(first: Point, second: Point, third: Point) -> float:
    return (second.x - first.x) * (third.y - first.y) - (
        second.y - first.y
    ) * (third.x - first.x)


def _point_on_segment(point: Point, segment: _Segment) -> bool:
    if abs(_cross(segment.start, segment.end, point)) > _EPS:
        return False
    return (
        min(segment.start.x, segment.end.x) - _EPS
        <= point.x
        <= max(segment.start.x, segment.end.x) + _EPS
        and min(segment.start.y, segment.end.y) - _EPS
        <= point.y
        <= max(segment.start.y, segment.end.y) + _EPS
    )


def _collinear_overlap_length(first: _Segment, second: _Segment) -> float:
    if abs(_cross(first.start, first.end, second.start)) > _EPS or abs(
        _cross(first.start, first.end, second.end)
    ) > _EPS:
        return 0.0
    if first.horizontal and second.horizontal:
        return max(
            0.0,
            min(first.start.x, first.end.x, second.start.x, second.end.x)
            - max(
                min(first.start.x, first.end.x),
                min(second.start.x, second.end.x),
            ),
        )
    if first.vertical and second.vertical:
        return max(
            0.0,
            min(first.start.y, first.end.y, second.start.y, second.end.y)
            - max(
                min(first.start.y, first.end.y),
                min(second.start.y, second.end.y),
            ),
        )
    first_dx = abs(first.end.x - first.start.x)
    first_dy = abs(first.end.y - first.start.y)
    if first_dx >= first_dy:
        return max(
            0.0,
            min(max(first.start.x, first.end.x), max(second.start.x, second.end.x))
            - max(min(first.start.x, first.end.x), min(second.start.x, second.end.x)),
        )
    return max(
        0.0,
        min(max(first.start.y, first.end.y), max(second.start.y, second.end.y))
        - max(min(first.start.y, first.end.y), min(second.start.y, second.end.y)),
    )


def _segments_intersect(first: _Segment, second: _Segment) -> bool:
    c1 = _cross(first.start, first.end, second.start)
    c2 = _cross(first.start, first.end, second.end)
    c3 = _cross(second.start, second.end, first.start)
    c4 = _cross(second.start, second.end, first.end)
    if (
        ((c1 > _EPS and c2 < -_EPS) or (c1 < -_EPS and c2 > _EPS))
        and ((c3 > _EPS and c4 < -_EPS) or (c3 < -_EPS and c4 > _EPS))
    ):
        return True
    return any(
        (
            abs(cross_value) <= _EPS,
            _point_on_segment(point, segment),
        )
        == (True, True)
        for cross_value, point, segment in (
            (c1, second.start, first),
            (c2, second.end, first),
            (c3, first.start, second),
            (c4, first.end, second),
        )
    )


def _allowed_endpoint_touch(
    candidate: _Segment,
    existing: _Segment,
    allowed_touches: tuple[Point, Point],
) -> bool:
    if _collinear_overlap_length(candidate, existing) > _EPS:
        return False
    for point in allowed_touches:
        if (
            (_same_point(candidate.start, point) or _same_point(candidate.end, point))
            and _point_on_segment(point, existing)
        ):
            return True
    return False


def _segment_hits_box(segment: _Segment, box: BBox) -> bool:
    if segment.horizontal:
        y = segment.start.y
        if not box.min_y + _EPS < y < box.max_y - _EPS:
            return False
        low = max(min(segment.start.x, segment.end.x), box.min_x)
        high = min(max(segment.start.x, segment.end.x), box.max_x)
        return high - low > _EPS
    if segment.vertical:
        x = segment.start.x
        if not box.min_x + _EPS < x < box.max_x - _EPS:
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


def _xml_coordinate_mm(document: DipTraceDocument, raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return to_mm(float(raw), document.units)
    except (TypeError, ValueError):
        return None


def _endpoint_matches_part(endpoint: WireEndpoint, part: Any) -> bool:
    if endpoint.type != "Pin":
        return False
    if endpoint.refdes is not None and (part.refdes or "").casefold() == endpoint.refdes.casefold():
        return True
    if endpoint.part_id is not None and endpoint.part_id in {
        part.stable_id,
        part.xml_id or "",
    }:
        return True
    return False


def _part_obstacles(
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    anchors: tuple[Point, Point],
) -> list[BBox]:
    if snapshot.schematic is None:
        return []
    boxes: list[BBox] = []
    for part in snapshot.schematic.parts:
        if str(part.attributes.get("sheet", "0")) != str(operation.sheet):
            continue
        if part.bbox is None:
            continue
        if _endpoint_matches_part(operation.start, part) or _endpoint_matches_part(
            operation.end, part
        ):
            continue
        box = BBox(**part.bbox).expand(_PART_VISUAL_MARGIN_MM)
        if any(box.contains_point(anchor) for anchor in anchors):
            continue
        boxes.append(box)
    return boxes


def _text_obstacles(
    document: DipTraceDocument,
    sheet: int,
    anchors: tuple[Point, Point],
) -> list[BBox]:
    boxes: list[BBox] = []
    for shape in document.container.findall("./Shapes/Shape"):
        if shape.get("Type") != "Text" or shape.get("Sheet", "0") != str(sheet):
            continue
        point = shape.find("./Points/Point")
        if point is None:
            continue
        x = _xml_coordinate_mm(document, point.get("X"))
        y = _xml_coordinate_mm(document, point.get("Y"))
        if x is None or y is None:
            continue
        lines = [item.text or "" for item in shape.findall("./TextLines/TextLine")]
        longest = max((len(line) for line in lines), default=1)
        try:
            font_scale = max(0.7, float(shape.get("FontSize", "10")) / 10.0)
        except ValueError:
            font_scale = 1.0
        width = max(1.0, longest * 0.65 * font_scale)
        height = max(1.0, max(1, len(lines)) * 1.2 * font_scale)
        box = BBox(
            x - width / 2.0,
            y - height / 2.0,
            x + width / 2.0,
            y + height / 2.0,
        ).expand(_TEXT_MARGIN_MM)
        if any(box.contains_point(anchor) for anchor in anchors):
            continue
        boxes.append(box)
    return boxes


def _existing_wire_segments(
    snapshot: DocumentSnapshot,
    sheet: int,
) -> list[_Segment]:
    if snapshot.schematic is None:
        return []
    segments: list[_Segment] = []
    for wire in snapshot.schematic.wires:
        if str(wire.attributes.get("sheet", "0")) != str(sheet):
            continue
        raw_points = wire.attributes.get("points", [])
        points = [
            Point(float(item["x"]), float(item["y"]))
            for item in raw_points
            if isinstance(item, dict) and "x" in item and "y" in item
        ]
        segments.extend(_path_segments(points))
        if len(segments) >= _MAX_EXISTING_SEGMENTS:
            return segments[:_MAX_EXISTING_SEGMENTS]
    return segments


def _wire_endpoint_anchor(
    snapshot: DocumentSnapshot,
    endpoint: WireEndpoint,
    fallback: Point,
) -> Point:
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
    return Point(float(item["x"]), float(item["y"]))


def _path_quality(
    points: list[Point],
    obstacles: list[BBox],
    existing: list[_Segment],
    allowed_touches: tuple[Point, Point],
) -> _PathQuality:
    segments = _path_segments(points)
    obstacle_hits = sum(
        1 for segment in segments for box in obstacles if _segment_hits_box(segment, box)
    )
    overlaps = 0
    crossings = 0
    for segment in segments:
        for other in existing:
            if not _segments_intersect(segment, other):
                continue
            if _collinear_overlap_length(segment, other) > _EPS:
                overlaps += 1
            elif not _allowed_endpoint_touch(segment, other, allowed_touches):
                crossings += 1
    self_intersections = 0
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 2, len(segments)):
            if second_index == first_index + 1:
                continue
            second = segments[second_index]
            if _segments_intersect(first, second):
                self_intersections += 1
    diagonal_segments = sum(1 for segment in segments if not (segment.horizontal or segment.vertical))
    bends = max(0, len(segments) - 1)
    length = sum(segment.length for segment in segments)
    return _PathQuality(
        obstacle_hits=obstacle_hits,
        overlaps=overlaps,
        crossings=crossings,
        self_intersections=self_intersections,
        diagonal_segments=diagonal_segments,
        bends=bends,
        length=length,
    )


def _axis_values(
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
        xs.update(
            (
                segment.start.x - _WIRE_LANE_GAP_MM,
                segment.start.x,
                segment.start.x + _WIRE_LANE_GAP_MM,
                segment.end.x - _WIRE_LANE_GAP_MM,
                segment.end.x,
                segment.end.x + _WIRE_LANE_GAP_MM,
            )
        )
        ys.update(
            (
                segment.start.y - _WIRE_LANE_GAP_MM,
                segment.start.y,
                segment.start.y + _WIRE_LANE_GAP_MM,
                segment.end.y - _WIRE_LANE_GAP_MM,
                segment.end.y,
                segment.end.y + _WIRE_LANE_GAP_MM,
            )
        )
    all_x = [*xs, *(value for box in obstacles for value in (box.min_x, box.max_x))]
    all_y = [*ys, *(value for box in obstacles for value in (box.min_y, box.max_y))]
    xs.update((min(all_x) - _OUTER_LANE_GAP_MM, max(all_x) + _OUTER_LANE_GAP_MM))
    ys.update((min(all_y) - _OUTER_LANE_GAP_MM, max(all_y) + _OUTER_LANE_GAP_MM))
    return _bounded_axis(xs, start.x, end.x), _bounded_axis(ys, start.y, end.y)


def _bounded_axis(values: Iterable[float], start: float, end: float) -> list[float]:
    unique = sorted({round(float(value), 9) for value in values})
    if len(unique) <= _MAX_AXIS_COORDINATES:
        return unique
    low, high = sorted((start, end))

    def distance_to_interval(value: float) -> float:
        if low <= value <= high:
            return 0.0
        return min(abs(value - low), abs(value - high))

    keep = {round(start, 9), round(end, 9)}
    for value in sorted(unique, key=lambda item: (distance_to_interval(item), abs(item), item)):
        keep.add(value)
        if len(keep) >= _MAX_AXIS_COORDINATES:
            break
    return sorted(keep)


def _node_blocked(point: Point, obstacles: list[BBox], anchors: tuple[Point, Point]) -> bool:
    if any(_same_point(point, anchor) for anchor in anchors):
        return False
    return any(
        box.min_x + _EPS < point.x < box.max_x - _EPS
        and box.min_y + _EPS < point.y < box.max_y - _EPS
        for box in obstacles
    )


def _edge_penalty(
    segment: _Segment,
    existing: list[_Segment],
    allowed_touches: tuple[Point, Point],
) -> float:
    crossings = 0
    overlaps = 0
    for other in existing:
        if not _segments_intersect(segment, other):
            continue
        if _collinear_overlap_length(segment, other) > _EPS:
            overlaps += 1
        elif not _allowed_endpoint_touch(segment, other, allowed_touches):
            crossings += 1
    return crossings * _CROSSING_PENALTY + overlaps * _OVERLAP_PENALTY


def _route_clean_path(
    start: Point,
    end: Point,
    obstacles: list[BBox],
    existing: list[_Segment],
) -> list[Point] | None:
    if _same_point(start, end):
        return None
    anchors = (start, end)
    xs, ys = _axis_values(start, end, obstacles, existing)
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
    adjacency: dict[tuple[float, float], list[tuple[tuple[float, float], int, float]]] = {
        key: [] for key in nodes
    }

    def connect(keys: list[tuple[float, float]], direction: int) -> None:
        for first_key, second_key in zip(keys, keys[1:], strict=False):
            first = nodes[first_key]
            second = nodes[second_key]
            segment = _Segment(first, second)
            if any(_segment_hits_box(segment, box) for box in obstacles):
                continue
            cost = segment.length + _edge_penalty(segment, existing, anchors)
            adjacency[first_key].append((second_key, direction, cost))
            adjacency[second_key].append((first_key, direction, cost))

    for y in ys:
        row = sorted((key for key in nodes if math.isclose(key[1], y, abs_tol=_EPS)))
        connect(row, 1)
    for x in xs:
        column = sorted(
            (key for key in nodes if math.isclose(key[0], x, abs_tol=_EPS)),
            key=lambda item: item[1],
        )
        connect(column, 2)

    queue: list[tuple[float, tuple[float, float], int]] = [(0.0, start_key, 0)]
    distance_by_state: dict[tuple[tuple[float, float], int], float] = {(start_key, 0): 0.0}
    previous: dict[
        tuple[tuple[float, float], int], tuple[tuple[float, float], int] | None
    ] = {(start_key, 0): None}
    final_state: tuple[tuple[float, float], int] | None = None
    while queue:
        cost, node_key, direction = heapq.heappop(queue)
        state = (node_key, direction)
        if cost > distance_by_state.get(state, math.inf) + _EPS:
            continue
        if node_key == end_key:
            final_state = state
            break
        for neighbor_key, next_direction, edge_cost in adjacency.get(node_key, []):
            bend_cost = _BEND_PENALTY if direction not in {0, next_direction} else 0.0
            candidate_cost = cost + edge_cost + bend_cost
            next_state = (neighbor_key, next_direction)
            if candidate_cost + _EPS >= distance_by_state.get(next_state, math.inf):
                continue
            distance_by_state[next_state] = candidate_cost
            previous[next_state] = state
            heapq.heappush(queue, (candidate_cost, neighbor_key, next_direction))
    if final_state is None:
        return None
    keys: list[tuple[float, float]] = []
    cursor: tuple[tuple[float, float], int] | None = final_state
    while cursor is not None:
        keys.append(cursor[0])
        cursor = previous[cursor]
    keys.reverse()
    return _simplify_points([nodes[key] for key in keys])


def clean_schematic_wire_operation(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
) -> AddWireOperation:
    """Improve a newly authored schematic wire without changing its connectivity intent.

    Explicit clean orthogonal paths are left alone.  If the caller-provided path
    contains a diagonal, visual-obstacle collision, existing-wire crossing/overlap,
    or self-intersection, a deterministic Manhattan route is searched.  Component
    bodies/labels are represented conservatively by expanded part bboxes and
    schematic text shapes.  Existing wires are soft obstacles: crossings are much
    more expensive than length, and collinear overlap is more expensive still.
    """
    if snapshot.schematic is None or len(operation.points) < 2:
        return operation
    supplied = _simplify_points([Point(item.x, item.y) for item in operation.points])
    if len(supplied) < 2:
        return operation
    supplied[0] = _wire_endpoint_anchor(snapshot, operation.start, supplied[0])
    supplied[-1] = _wire_endpoint_anchor(snapshot, operation.end, supplied[-1])
    supplied = _simplify_points(supplied)
    anchors = (supplied[0], supplied[-1])
    obstacles = [
        *_part_obstacles(snapshot, operation, anchors),
        *_text_obstacles(document, operation.sheet, anchors),
    ]
    existing = _existing_wire_segments(snapshot, operation.sheet)
    original_quality = _path_quality(supplied, obstacles, existing, anchors)
    if original_quality.score()[:5] == (0, 0, 0, 0, 0):
        cleaned = supplied
    else:
        routed = _route_clean_path(anchors[0], anchors[1], obstacles, existing)
        if routed is None:
            cleaned = supplied
        else:
            routed_quality = _path_quality(routed, obstacles, existing, anchors)
            cleaned = routed if routed_quality.score() < original_quality.score() else supplied
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

    cleaned = clean_schematic_wire_operation(document, snapshot, operation)
    return _apply_add_wire(index, document, snapshot, cleaned, changed_ids)


_INSTALLED = False


def install_schematic_wire_quality() -> None:
    """Install schematic-wire quality routing into the semantic operation registry."""
    global _INSTALLED
    if _INSTALLED:
        return
    from ..semantic_compiler import SEMANTIC_OPERATION_HANDLERS, _adapt_semantic_handler

    SEMANTIC_OPERATION_HANDLERS[AddWireOperation] = _adapt_semantic_handler(
        _quality_add_wire_handler
    )
    _INSTALLED = True
