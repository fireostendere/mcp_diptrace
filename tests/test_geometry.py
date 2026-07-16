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
    shape_bbox,
    shapely_available,
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

    assert report["engine"] in {"pure_python", "shapely_geos"}
    assert report["shapely_available"] is shapely_available()
    assert all("shapely" not in value.__class__.__module__ for value in report.values())


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
