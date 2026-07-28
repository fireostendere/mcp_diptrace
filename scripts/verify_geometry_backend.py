#!/usr/bin/env python3
"""Exercise the selected geometry backend without substituting a mock."""

from __future__ import annotations

import argparse
import math

from diptrace_mcp.domain import GeometryShape
from diptrace_mcp.geometry import Point
from diptrace_mcp.geometry_backend import backend_report, line_to_shape_distance, shape_bbox


def verify_backend(expected: str) -> None:
    """Assert that the installed backend executes its promised geometry path."""

    report = backend_report()
    actual = report["engine"]
    if actual != expected:
        raise RuntimeError(f"Expected geometry backend {expected!r}, got {actual!r}")

    pad = GeometryShape(
        kind="rectangle",
        center={"x": 5.0, "y": 5.0},
        width=2.0,
        height=1.0,
        rotation_deg=45.0 if expected == "pure_python" else 90.0,
    )
    bounds = shape_bbox(pad)
    if expected == "pure_python":
        measured = line_to_shape_distance(Point(0.0, 5.0), Point(3.0, 5.0), 0.2, pad)
        # The no-GEOS implementation encloses the rotated 2x1 rectangle in the
        # square defined by its diagonal: span = hypot(2, 1).
        expected_span = math.hypot(2.0, 1.0)
        span_matches = math.isclose(
            bounds.width, expected_span, rel_tol=1e-12, abs_tol=0.0
        ) and math.isclose(bounds.height, expected_span, rel_tol=1e-12, abs_tol=0.0)
        if not span_matches or measured <= 0.0:
            raise RuntimeError("Pure-Python conservative geometry probe failed")
    else:
        measured = line_to_shape_distance(Point(0.0, 5.0), Point(4.0, 5.0), 0.2, pad)
        # A 90-degree 2x1 rectangle has exact 1x2 bounds. Its left edge is
        # x=4.5; the test line ends at x=4.0 with radius 0.1, hence 0.4 mm.
        if abs(bounds.width - 1.0) > 1e-9 or abs(bounds.height - 2.0) > 1e-9:
            raise RuntimeError("GEOS exact rotated bounds probe failed")
        if abs(measured - 0.4) > 1e-9:
            raise RuntimeError("GEOS exact line-to-shape distance probe failed")
    print(f"OK: exercised {actual} geometry backend")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect",
        required=True,
        choices=("pure_python", "shapely_geos"),
        help="backend that must be installed and exercised",
    )
    args = parser.parse_args()
    verify_backend(args.expect)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
