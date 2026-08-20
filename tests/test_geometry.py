import pytest

import diptrace_mcp.geometry_backend as geometry_backend
from diptrace_mcp.domain import GeometryShape
from diptrace_mcp.geometry import (
    BBox,
    Point,
    Transform,
    distance,
    point_in_polygon,
    point_to_segment_distance,
    segment_distance,
    segments_intersect,
)
from diptrace_mcp.geometry_backend import (
    backend_report,
    line_to_shape_distance,
    offset_shape,
    point_to_shape_distance,
    segment_to_shape_distance,
    shape_bbox,
    shape_distance,
    shapely_available,
    transform_shape,
)


def test_transform_roundtrip_and_bbox_intersection() -> None:
    point = Point(1.0, 2.0)
    transform = Transform(translate_x=10.0, translate_y=-3.0, rotation_deg=90.0)
    transformed = transform.apply_point(point)
    restored = transform.inverse().apply_point(transformed)

    assert round(restored.x, 6) == 1.0
    assert round(restored.y, 6) == 2.0
    assert distance(Point(0.0, 0.0), Point(3.0, 4.0)) == 5.0

    box_a = BBox(0.0, 0.0, 2.0, 2.0)
    box_b = BBox(1.5, 1.5, 3.0, 3.0)
    box_c = BBox(3.1, 3.1, 4.0, 4.0)

    assert box_a.intersects(box_b)
    assert not box_a.intersects(box_c)
    assert point_in_polygon(Point(1.0, 1.0), [Point(0, 0), Point(3, 0), Point(3, 3), Point(0, 3)])


def test_segment_intersection_and_distance() -> None:
    assert segments_intersect(Point(0, 0), Point(2, 2), Point(0, 2), Point(2, 0))
    assert segment_distance(Point(0, 0), Point(2, 0), Point(0, 1), Point(2, 1)) == 1
    assert point_to_segment_distance(Point(3, 1), Point(0, 0), Point(2, 0)) == pytest.approx(
        2**0.5
    )


def test_bbox_intersection_area_and_containment() -> None:
    outer = BBox(0, 0, 10, 10)
    inner = BBox(2, 3, 5, 7)
    crossing = BBox(4, 6, 12, 9)

    assert outer.area == 100
    assert outer.contains_bbox(inner)
    assert not inner.contains_bbox(outer)
    assert inner.overlap_area(crossing) == 1
    assert inner.intersection(BBox(5, 7, 6, 8)) is None


def test_geometry_backend_reports_optional_engine_without_leaking_backend_types() -> None:
    report = backend_report()

    assert report["shapely_available"] is shapely_available()
    if shapely_available():
        assert report["engine"] == "shapely_geos"
        assert report["exact_shapes"] == [
            "line",
            "circle",
            "ellipse",
            "rectangle",
            "obround",
            "polygon",
        ]
    else:
        assert report["engine"] == "pure_python"
        assert report["exact_shapes"] == ["line", "circle"]
        assert report["limitations"]
    assert all("shapely" not in value.__class__.__module__ for value in report.values())


def test_geometry_backend_reports_unknown_shapely_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geometry_backend, "shapely_available", lambda: True)

    def missing(_name: str) -> str:
        raise geometry_backend.PackageNotFoundError

    monkeypatch.setattr(geometry_backend, "package_version", missing)
    report = geometry_backend.backend_report()
    assert report["engine"] == "shapely_geos"
    assert report["version"] == "unknown"


def test_geometry_backend_has_conservative_pure_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(geometry_backend, "shapely_available", lambda: False)
    pad = GeometryShape(
        kind="rectangle",
        center={"x": 5.0, "y": 5.0},
        width=2.0,
        height=1.0,
        rotation_deg=45.0,
    )

    report = geometry_backend.backend_report()
    bounds = geometry_backend.shape_bbox(pad)
    assert report["engine"] == "pure_python"
    assert bounds.width == pytest.approx(5**0.5)
    assert bounds.height == pytest.approx(5**0.5)
    assert geometry_backend.line_to_shape_distance(
        Point(0, 5), Point(3, 5), 0.2, pad
    ) > 0.0


def test_shape_bbox_points_params_and_invalid_parametric_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon = GeometryShape(
        kind="polygon",
        points=[{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 5.0}],
        line_width=2.0,
    )
    assert shape_bbox(polygon) == BBox(0.0, 1.0, 4.0, 6.0)

    circle = GeometryShape(kind="circle", center={"x": 2.0, "y": 3.0}, width=4.0, height=4.0)
    assert shape_bbox(circle) == BBox(0.0, 1.0, 4.0, 5.0)

    with pytest.raises(ValueError, match="center, width and height"):
        shape_bbox(GeometryShape(kind="rectangle"))

    monkeypatch.setattr(geometry_backend, "_to_shapely", lambda _shape: None)
    rotated = GeometryShape(
        kind="rectangle",
        center={"x": 0.0, "y": 0.0},
        width=6.0,
        height=8.0,
        rotation_deg=30.0,
    )
    assert shape_bbox(rotated) == BBox(-5.0, -5.0, 5.0, 5.0)


def test_transform_shape_handles_points_missing_center_and_rotated_center() -> None:
    transform = Transform(translate_x=10.0, translate_y=-2.0, rotation_deg=90.0)
    line = GeometryShape(
        kind="line",
        points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}],
        line_width=0.2,
    )
    transformed = transform_shape(line, transform)
    assert transformed.points[0] == pytest.approx({"x": 10.0, "y": -2.0})
    assert transformed.points[1] == pytest.approx({"x": 10.0, "y": -1.0})

    empty = GeometryShape(kind="polygon")
    assert transform_shape(empty, transform) is empty

    rect = GeometryShape(
        kind="rectangle",
        center={"x": 1.0, "y": 2.0},
        width=2.0,
        height=4.0,
        rotation_deg=30.0,
    )
    moved = transform_shape(rect, transform)
    assert moved.center == pytest.approx({"x": 8.0, "y": -1.0})
    assert moved.rotation_deg == pytest.approx(120.0)


def test_offset_shape_parametric_and_unavailable_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    rect = GeometryShape(
        kind="rectangle", center={"x": 0.0, "y": 0.0}, width=4.0, height=2.0
    )
    copied = offset_shape(rect, 0.0)
    assert copied == rect and copied is not rect
    grown = offset_shape(rect, 0.5)
    assert grown is not None
    assert grown.width == 5.0 and grown.height == 3.0
    assert offset_shape(rect, -1.0) is None

    incomplete = GeometryShape(kind="rectangle")
    assert offset_shape(incomplete, 1.0) is None

    monkeypatch.setattr(geometry_backend, "_to_shapely", lambda _shape: None)
    box = GeometryShape(
        kind="polygon",
        points=[
            {"x": 0.0, "y": 0.0},
            {"x": 2.0, "y": 0.0},
            {"x": 2.0, "y": 1.0},
            {"x": 0.0, "y": 1.0},
        ],
    )
    inset = offset_shape(box, -0.25)
    assert inset is not None
    assert inset.points == [
        {"x": 0.25, "y": 0.25},
        {"x": 1.75, "y": 0.25},
        {"x": 1.75, "y": 0.75},
        {"x": 0.25, "y": 0.75},
    ]

    polygon = GeometryShape(
        kind="polygon",
        points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 0.0, "y": 1.0}],
    )
    assert offset_shape(polygon, 1.0) is None


def test_pure_python_shape_distances_cover_circle_line_and_bbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(geometry_backend, "_to_shapely", lambda _shape: None)
    left = GeometryShape(kind="circle", center={"x": 0.0, "y": 0.0}, width=2.0, height=2.0)
    right = GeometryShape(kind="circle", center={"x": 5.0, "y": 0.0}, width=2.0, height=2.0)
    assert shape_distance(left, right) == pytest.approx(3.0)

    line_a = GeometryShape(
        kind="line",
        points=[{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0}],
        line_width=0.2,
    )
    line_b = GeometryShape(
        kind="line",
        points=[{"x": 0.0, "y": 2.0}, {"x": 2.0, "y": 2.0}],
        line_width=0.4,
    )
    assert shape_distance(line_a, line_b) == pytest.approx(1.7)

    rect_a = GeometryShape(
        kind="rectangle", center={"x": 0.0, "y": 0.0}, width=2.0, height=2.0
    )
    rect_b = GeometryShape(
        kind="rectangle", center={"x": 4.0, "y": 5.0}, width=2.0, height=2.0
    )
    assert shape_distance(rect_a, rect_b) == pytest.approx(13**0.5)
    assert geometry_backend._point_distance(Point(0, 0), Point(3, 4)) == 5.0
    assert geometry_backend._bbox_distance(BBox(0, 0, 1, 1), BBox(4, 5, 6, 7)) == 5.0


def test_pure_python_line_segment_and_point_to_shape_distances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(geometry_backend, "shapely_available", lambda: False)
    monkeypatch.setattr(geometry_backend, "_to_shapely", lambda _shape: None)
    circle = GeometryShape(kind="circle", center={"x": 5.0, "y": 0.0}, width=2.0, height=2.0)
    assert line_to_shape_distance(Point(0, 0), Point(3, 0), 0.4, circle) == pytest.approx(0.8)

    rect = GeometryShape(
        kind="rectangle", center={"x": 5.0, "y": 5.0}, width=2.0, height=2.0
    )
    assert line_to_shape_distance(Point(0, 0), Point(2, 0), 0.2, rect) > 0
    assert segment_to_shape_distance(Point(0, 0), Point(2, 0), rect) == pytest.approx(4.47213595)
    assert point_to_shape_distance(Point(0, 0), rect) == pytest.approx(5.65685425)


@pytest.mark.skipif(not shapely_available(), reason="geometry extra is not installed")
def test_shapely_backend_measures_rotated_pad_and_swept_trace_exactly() -> None:
    pad = GeometryShape(
        kind="rectangle",
        center={"x": 5.0, "y": 5.0},
        width=2.0,
        height=1.0,
        rotation_deg=90.0,
    )

    bounds = shape_bbox(pad)
    assert bounds.width == pytest.approx(1.0)
    assert bounds.height == pytest.approx(2.0)
    assert line_to_shape_distance(Point(0, 5), Point(4, 5), 0.2, pad) == pytest.approx(0.4)


@pytest.mark.skipif(not shapely_available(), reason="geometry extra is not installed")
def test_shapely_backend_shape_variants_offsets_and_exact_distances() -> None:
    polygon = GeometryShape(
        kind="polygon",
        points=[{"x": 0.0, "y": 0.0}, {"x": 2.0, "y": 0.0}, {"x": 0.0, "y": 2.0}],
    )
    line = GeometryShape(
        kind="line",
        points=[{"x": 3.0, "y": 0.0}, {"x": 4.0, "y": 0.0}],
        line_width=0.2,
    )
    circle = GeometryShape(kind="circle", center={"x": 5.0, "y": 5.0}, width=2.0, height=2.0)
    ellipse = GeometryShape(
        kind="ellipse", center={"x": 0.0, "y": 0.0}, width=4.0, height=2.0, rotation_deg=20.0
    )
    obround_h = GeometryShape(
        kind="obround", center={"x": 0.0, "y": 0.0}, width=6.0, height=2.0
    )
    obround_v = GeometryShape(
        kind="obround", center={"x": 0.0, "y": 0.0}, width=2.0, height=6.0
    )

    for shape in (polygon, line, circle, ellipse, obround_h, obround_v):
        assert geometry_backend._to_shapely(shape) is not None

    assert geometry_backend._to_shapely(GeometryShape(kind="rectangle")) is None
    grown = offset_shape(polygon, 0.25)
    assert grown is not None and grown.kind == "polygon"
    assert grown.approximation is not None
    assert shape_distance(polygon, line) > 0.0
    assert segment_to_shape_distance(Point(3, 3), Point(4, 3), polygon) > 0.0
    assert point_to_shape_distance(Point(3, 3), polygon) > 0.0
