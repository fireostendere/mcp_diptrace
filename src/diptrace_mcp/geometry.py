from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace

UNIT_TO_MM: dict[str, float] = {"mm": 1.0, "inch": 25.4, "mil": 0.0254}


def to_mm(value: float, unit: str) -> float:
    try:
        scale = UNIT_TO_MM[unit.casefold()]
    except KeyError as exc:
        raise ValueError(f"Unsupported coordinate unit: {unit!r}") from exc
    return float(value) * scale


def from_mm(value: float, unit: str) -> float:
    try:
        scale = UNIT_TO_MM[unit.casefold()]
    except KeyError as exc:
        raise ValueError(f"Unsupported coordinate unit: {unit!r}") from exc
    return float(value) / scale


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def translate(self, dx: float = 0.0, dy: float = 0.0) -> Point:
        return replace(self, x=self.x + dx, y=self.y + dy)


@dataclass(frozen=True, slots=True)
class BBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.min_x > self.max_x or self.min_y > self.max_y:
            msg = f"Invalid bbox: {self}"
            raise ValueError(msg)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center(self) -> Point:
        return Point((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def translate(self, dx: float = 0.0, dy: float = 0.0) -> BBox:
        return BBox(
            self.min_x + dx,
            self.min_y + dy,
            self.max_x + dx,
            self.max_y + dy,
        )

    def expand(self, margin: float) -> BBox:
        return BBox(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )

    def intersects(self, other: BBox) -> bool:
        return not (
            self.max_x < other.min_x
            or self.min_x > other.max_x
            or self.max_y < other.min_y
            or self.min_y > other.max_y
        )

    def contains_point(self, point: Point) -> bool:
        return (
            self.min_x <= point.x <= self.max_x and self.min_y <= point.y <= self.max_y
        )

    def contains_bbox(self, other: BBox) -> bool:
        return (
            self.min_x <= other.min_x
            and self.min_y <= other.min_y
            and self.max_x >= other.max_x
            and self.max_y >= other.max_y
        )

    def intersection(self, other: BBox) -> BBox | None:
        min_x = max(self.min_x, other.min_x)
        min_y = max(self.min_y, other.min_y)
        max_x = min(self.max_x, other.max_x)
        max_y = min(self.max_y, other.max_y)
        if min_x >= max_x or min_y >= max_y:
            return None
        return BBox(min_x, min_y, max_x, max_y)

    def overlap_area(self, other: BBox) -> float:
        overlap = self.intersection(other)
        return overlap.area if overlap is not None else 0.0

    @classmethod
    def from_points(cls, points: Sequence[Point]) -> BBox:
        if not points:
            raise ValueError("at least one point is required")
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        return cls(min(xs), min(ys), max(xs), max(ys))

    @classmethod
    def empty(cls) -> BBox:
        return cls(0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Transform:
    translate_x: float = 0.0
    translate_y: float = 0.0
    rotation_deg: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False
    origin_x: float = 0.0
    origin_y: float = 0.0
    matrix: tuple[float, float, float, float, float, float] | None = None

    def _parameter_matrix(self) -> tuple[float, float, float, float, float, float]:
        origin = Point(self.origin_x, self.origin_y)
        p0 = self._apply_parameter_transform(Point(0.0, 0.0), origin)
        p1 = self._apply_parameter_transform(Point(1.0, 0.0), origin)
        p2 = self._apply_parameter_transform(Point(0.0, 1.0), origin)
        a = p1.x - p0.x
        b = p1.y - p0.y
        c = p2.x - p0.x
        d = p2.y - p0.y
        e = p0.x
        f = p0.y
        return a, b, c, d, e, f

    def _apply_parameter_transform(self, point: Point, origin: Point) -> Point:
        x = point.x - origin.x
        y = point.y - origin.y
        if self.mirror_x:
            x = -x
        if self.mirror_y:
            y = -y
        if self.rotation_deg:
            radians = math.radians(self.rotation_deg)
            cos_v = math.cos(radians)
            sin_v = math.sin(radians)
            x, y = x * cos_v - y * sin_v, x * sin_v + y * cos_v
        return Point(x + origin.x + self.translate_x, y + origin.y + self.translate_y)

    @staticmethod
    def _invert_matrix(
        matrix: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float]:
        a, b, c, d, e, f = matrix
        det = a * d - b * c
        if abs(det) < 1e-12:
            raise ValueError("Transform is not invertible")
        inv_a = d / det
        inv_b = -b / det
        inv_c = -c / det
        inv_d = a / det
        inv_e = (c * f - d * e) / det
        inv_f = (b * e - a * f) / det
        return inv_a, inv_b, inv_c, inv_d, inv_e, inv_f

    @staticmethod
    def _multiply_matrix(
        left: tuple[float, float, float, float, float, float],
        right: tuple[float, float, float, float, float, float],
    ) -> tuple[float, float, float, float, float, float]:
        a1, b1, c1, d1, e1, f1 = left
        a2, b2, c2, d2, e2, f2 = right
        return (
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    def _current_matrix(self) -> tuple[float, float, float, float, float, float]:
        if self.matrix is not None:
            return self.matrix
        return self._parameter_matrix()

    def apply_point(self, point: Point) -> Point:
        a, b, c, d, e, f = self._current_matrix()
        return Point(a * point.x + c * point.y + e, b * point.x + d * point.y + f)

    def apply_bbox(self, bbox: BBox) -> BBox:
        points = [
            self.apply_point(Point(bbox.min_x, bbox.min_y)),
            self.apply_point(Point(bbox.min_x, bbox.max_y)),
            self.apply_point(Point(bbox.max_x, bbox.min_y)),
            self.apply_point(Point(bbox.max_x, bbox.max_y)),
        ]
        return BBox.from_points(points)

    def compose(self, other: Transform) -> Transform:
        return Transform(
            matrix=self._multiply_matrix(self._current_matrix(), other._current_matrix())
        )

    def inverse(self) -> Transform:
        return Transform(matrix=self._invert_matrix(self._current_matrix()))


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return distance(point, start)
    projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_squared
    projection = min(1.0, max(0.0, projection))
    nearest = Point(start.x + projection * dx, start.y + projection * dy)
    return distance(point, nearest)


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _point_on_segment(point: Point, start: Point, end: Point, tolerance: float = 1e-12) -> bool:
    return (
        abs(_orientation(start, end, point)) <= tolerance
        and min(start.x, end.x) - tolerance <= point.x <= max(start.x, end.x) + tolerance
        and min(start.y, end.y) - tolerance <= point.y <= max(start.y, end.y) + tolerance
    )


def segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    return any(
        (
            abs(orientation) <= 1e-12 and _point_on_segment(point, start, end)
            for orientation, point, start, end in (
                (o1, b1, a1, a2),
                (o2, b2, a1, a2),
                (o3, a1, b1, b2),
                (o4, a2, b1, b2),
            )
        )
    )


def segment_distance(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        point_to_segment_distance(a1, b1, b2),
        point_to_segment_distance(a2, b1, b2),
        point_to_segment_distance(b1, a1, a2),
        point_to_segment_distance(b2, a1, a2),
    )


def segment_intersects_bbox(start: Point, end: Point, box: BBox) -> bool:
    if box.contains_point(start) or box.contains_point(end):
        return True
    corners = (
        Point(box.min_x, box.min_y),
        Point(box.max_x, box.min_y),
        Point(box.max_x, box.max_y),
        Point(box.min_x, box.max_y),
    )
    return any(
        segments_intersect(start, end, left, right)
        for left, right in zip(corners, (*corners[1:], corners[0]), strict=True)
    )


def polyline_length(points: Sequence[Point]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for left, right in zip(points, points[1:], strict=False):
        total += distance(left, right)
    return total


def arc_through_points_length(start: Point, middle: Point, end: Point) -> float:
    """Return the circular arc from start to end that passes through middle."""
    determinant = 2.0 * (
        start.x * (middle.y - end.y)
        + middle.x * (end.y - start.y)
        + end.x * (start.y - middle.y)
    )
    if abs(determinant) <= 1e-12:
        return distance(start, middle) + distance(middle, end)
    start_sq = start.x * start.x + start.y * start.y
    middle_sq = middle.x * middle.x + middle.y * middle.y
    end_sq = end.x * end.x + end.y * end.y
    center = Point(
        (
            start_sq * (middle.y - end.y)
            + middle_sq * (end.y - start.y)
            + end_sq * (start.y - middle.y)
        )
        / determinant,
        (
            start_sq * (end.x - middle.x)
            + middle_sq * (start.x - end.x)
            + end_sq * (middle.x - start.x)
        )
        / determinant,
    )
    radius = distance(center, start)
    start_angle = math.atan2(start.y - center.y, start.x - center.x)
    middle_angle = math.atan2(middle.y - center.y, middle.x - center.x)
    end_angle = math.atan2(end.y - center.y, end.x - center.x)
    full_turn = 2.0 * math.pi
    start_to_middle = (middle_angle - start_angle) % full_turn
    start_to_end = (end_angle - start_angle) % full_turn
    sweep = (
        start_to_end
        if start_to_middle <= start_to_end + 1e-12
        else full_turn - start_to_end
    )
    return radius * sweep


def trace_path_length(points: Sequence[Point], arc_middle: Sequence[bool]) -> float:
    """Measure a DipTrace path where an Arc=Y point is the circular-arc midpoint."""
    if len(points) < 2:
        return 0.0
    if len(arc_middle) != len(points):
        raise ValueError("arc_middle must have one flag per point")
    total = 0.0
    index = 0
    while index < len(points) - 1:
        if index + 2 < len(points) and arc_middle[index + 1]:
            total += arc_through_points_length(
                points[index], points[index + 1], points[index + 2]
            )
            index += 2
        else:
            total += distance(points[index], points[index + 1])
            index += 1
    return total


def bbox_union(boxes: Iterable[BBox]) -> BBox:
    boxes = list(boxes)
    if not boxes:
        raise ValueError("at least one bbox is required")
    return BBox(
        min(box.min_x for box in boxes),
        min(box.min_y for box in boxes),
        max(box.max_x for box in boxes),
        max(box.max_y for box in boxes),
    )


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i, vertex in enumerate(polygon):
        prev = polygon[j]
        intersects = (
            (vertex.y > point.y) != (prev.y > point.y)
            and point.x
            < (prev.x - vertex.x) * (point.y - vertex.y) / ((prev.y - vertex.y) or 1e-12)
            + vertex.x
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def round_mm(value: float, digits: int = 6) -> float:
    return round(float(value), digits)
