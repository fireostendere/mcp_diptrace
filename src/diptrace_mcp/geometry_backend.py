from __future__ import annotations

import importlib.util
import math
from typing import Any

from .domain import GeometryShape
from .geometry import BBox, Point, Transform, point_to_segment_distance, segment_distance


def shapely_available() -> bool:
    return importlib.util.find_spec("shapely") is not None


def backend_report() -> dict[str, object]:
    if not shapely_available():
        return {
            "engine": "pure_python",
            "shapely_available": False,
            "exact_shapes": ["line", "circle"],
            "limitations": [
                "Rotated ellipse, obround and polygon offsets use conservative bbox fallback."
            ],
        }
    import shapely  # type: ignore[import-untyped]

    return {
        "engine": "shapely_geos",
        "shapely_available": True,
        "version": shapely.__version__,
        "exact_shapes": ["line", "circle", "ellipse", "rectangle", "obround", "polygon"],
        "deterministic_ordering": "stable_id_sort_after_spatial_query",
    }


def shape_bbox(shape: GeometryShape) -> BBox:
    if shape.points:
        margin = (shape.line_width or 0.0) / 2.0
        return BBox.from_points([Point(**item) for item in shape.points]).expand(margin)
    if shape.center is None or shape.width is None or shape.height is None:
        raise ValueError("center, width and height are required for parametric geometry")
    center = Point(**shape.center)
    if not shape.rotation_deg or shape.kind == "circle":
        return BBox(
            center.x - shape.width / 2.0,
            center.y - shape.height / 2.0,
            center.x + shape.width / 2.0,
            center.y + shape.height / 2.0,
        )
    geometry = _to_shapely(shape)
    if geometry is not None:
        min_x, min_y, max_x, max_y = geometry.bounds
        return BBox(float(min_x), float(min_y), float(max_x), float(max_y))
    radius = ((shape.width / 2.0) ** 2 + (shape.height / 2.0) ** 2) ** 0.5
    return BBox(center.x - radius, center.y - radius, center.x + radius, center.y + radius)


def transform_shape(shape: GeometryShape, transform: Transform) -> GeometryShape:
    if shape.points:
        return shape.model_copy(
            update={
                "points": [
                    transform.apply_point(Point(**point)).as_dict() for point in shape.points
                ]
            }
        )
    if shape.center is None:
        return shape
    center = Point(**shape.center)
    transformed_center = transform.apply_point(center)
    radians = math.radians(shape.rotation_deg)
    axis = Point(center.x + math.cos(radians), center.y + math.sin(radians))
    transformed_axis = transform.apply_point(axis)
    rotation = math.degrees(
        math.atan2(
            transformed_axis.y - transformed_center.y,
            transformed_axis.x - transformed_center.x,
        )
    )
    return shape.model_copy(
        update={"center": transformed_center.as_dict(), "rotation_deg": rotation}
    )


def offset_shape(shape: GeometryShape, offset: float) -> GeometryShape | None:
    if offset == 0.0:
        return shape.model_copy(deep=True)
    if shape.kind in {"circle", "ellipse", "rectangle", "obround"}:
        if shape.width is None or shape.height is None:
            return None
        width = shape.width + 2.0 * offset
        height = shape.height + 2.0 * offset
        if width <= 0.0 or height <= 0.0:
            return None
        return shape.model_copy(update={"width": width, "height": height})
    geometry = _to_shapely(shape)
    if geometry is None:
        return None
    buffered = geometry.buffer(offset, join_style="round")
    if buffered.is_empty or buffered.geom_type != "Polygon":
        return None
    return GeometryShape(
        kind="polygon",
        points=[{"x": float(x), "y": float(y)} for x, y in buffered.exterior.coords[:-1]],
        approximation="GEOS offset from documented custom swell/shrink",
    )


def shape_distance(left: GeometryShape, right: GeometryShape) -> float:
    left_geometry = _to_shapely(left)
    right_geometry = _to_shapely(right)
    if left_geometry is not None and right_geometry is not None:
        return float(left_geometry.distance(right_geometry))
    if left.kind == "circle" and right.kind == "circle":
        assert left.center is not None and right.center is not None
        assert left.width is not None and right.width is not None
        centers = Point(**left.center), Point(**right.center)
        return max(0.0, _point_distance(*centers) - (left.width + right.width) / 2.0)
    if left.kind == "line" and right.kind == "line" and len(left.points) == len(right.points) == 2:
        return max(
            0.0,
            segment_distance(
                Point(**left.points[0]),
                Point(**left.points[1]),
                Point(**right.points[0]),
                Point(**right.points[1]),
            )
            - ((left.line_width or 0.0) + (right.line_width or 0.0)) / 2.0,
        )
    return _bbox_distance(shape_bbox(left), shape_bbox(right))


def line_to_shape_distance(
    start: Point,
    end: Point,
    line_width: float,
    shape: GeometryShape,
) -> float:
    line = GeometryShape(
        kind="line",
        points=[start.as_dict(), end.as_dict()],
        line_width=line_width,
    )
    geometry = _to_shapely(line)
    obstacle = _to_shapely(shape)
    if geometry is not None and obstacle is not None:
        return float(geometry.distance(obstacle))
    if shape.kind == "circle" and shape.center is not None and shape.width is not None:
        return max(
            0.0,
            point_to_segment_distance(Point(**shape.center), start, end)
            - shape.width / 2.0
            - line_width / 2.0,
        )
    return _bbox_distance(shape_bbox(line), shape_bbox(shape))


def _to_shapely(shape: GeometryShape) -> Any | None:
    if not shapely_available():
        return None
    from shapely import affinity
    from shapely.geometry import (  # type: ignore[import-untyped]
        LineString,
        Polygon,
        box,
    )
    from shapely.geometry import (
        Point as ShapelyPoint,
    )

    if shape.kind == "line":
        geometry = LineString([(item["x"], item["y"]) for item in shape.points])
        return geometry.buffer((shape.line_width or 0.0) / 2.0, cap_style="round")
    if shape.kind == "polygon":
        return Polygon([(item["x"], item["y"]) for item in shape.points])
    if shape.center is None or shape.width is None or shape.height is None:
        return None
    x = shape.center["x"]
    y = shape.center["y"]
    if shape.kind == "circle":
        return ShapelyPoint(x, y).buffer(shape.width / 2.0, quad_segs=32)
    if shape.kind == "rectangle":
        geometry = box(
            -shape.width / 2.0,
            -shape.height / 2.0,
            shape.width / 2.0,
            shape.height / 2.0,
        )
    elif shape.kind == "ellipse":
        geometry = affinity.scale(
            ShapelyPoint(0.0, 0.0).buffer(1.0, quad_segs=32),
            xfact=shape.width / 2.0,
            yfact=shape.height / 2.0,
        )
    elif shape.kind == "obround":
        horizontal = shape.width >= shape.height
        radius = min(shape.width, shape.height) / 2.0
        half_straight = max(shape.width, shape.height) / 2.0 - radius
        endpoints = (
            [(-half_straight, 0.0), (half_straight, 0.0)]
            if horizontal
            else [(0.0, -half_straight), (0.0, half_straight)]
        )
        geometry = LineString(endpoints).buffer(radius, quad_segs=32, cap_style="round")
    if shape.rotation_deg:
        geometry = affinity.rotate(geometry, shape.rotation_deg, origin=(0.0, 0.0))
    return affinity.translate(geometry, xoff=x, yoff=y)


def _point_distance(left: Point, right: Point) -> float:
    return float(math.hypot(left.x - right.x, left.y - right.y))


def _bbox_distance(left: BBox, right: BBox) -> float:
    dx = max(left.min_x - right.max_x, right.min_x - left.max_x, 0.0)
    dy = max(left.min_y - right.max_y, right.min_y - left.max_y, 0.0)
    return float(math.hypot(dx, dy))
