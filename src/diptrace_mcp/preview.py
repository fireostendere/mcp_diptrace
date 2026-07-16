from __future__ import annotations

from html import escape
from typing import Any

from .adapters import DocumentSnapshot
from .geometry import BBox, Point


def _all_points(snapshot: DocumentSnapshot) -> list[Point]:
    points: list[Point] = []
    if snapshot.board and snapshot.board.outline:
        for item in snapshot.board.outline.get("points", []):
            points.append(Point(float(item["x"]), float(item["y"])))
    for record in snapshot.objects.values():
        if record.position:
            points.append(Point(float(record.position["x"]), float(record.position["y"])))
    if not points:
        points = [Point(0.0, 0.0), Point(10.0, 10.0)]
    return points


def _bounds(snapshot: DocumentSnapshot) -> BBox:
    points = _all_points(snapshot)
    box = BBox.from_points(points)
    margin_x = max(box.width * 0.1, 2.0)
    margin_y = max(box.height * 0.1, 2.0)
    return BBox(
        box.min_x - margin_x,
        box.min_y - margin_y,
        box.max_x + margin_x,
        box.max_y + margin_y,
    )


def _scale(box: BBox, width: int, height: int) -> tuple[float, float, float]:
    scale_x = width / (box.width or 1.0)
    scale_y = height / (box.height or 1.0)
    scale = min(scale_x, scale_y)
    return scale, box.min_x, box.min_y


def _map_point(point: Point, box: BBox, width: int, height: int) -> tuple[float, float]:
    scale, origin_x, origin_y = _scale(box, width, height)
    x = (point.x - origin_x) * scale + 20.0
    y = height - ((point.y - origin_y) * scale + 20.0)
    return x, y


def render_preview_svg(
    before: DocumentSnapshot,
    after: DocumentSnapshot,
    changed_ids: list[str],
    *,
    width: int = 960,
    height: int = 640,
) -> str:
    box = _bounds(after)
    outline = after.board.outline if after.board else None
    before_positions = {
        record.stable_id: Point(record.position["x"], record.position["y"])
        for record in before.objects.values()
        if record.position
    }
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" ',
        f'viewBox="0 0 {width} {height}" role="img" aria-label="DipTrace preview">',
        "<defs>",
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">',
        '<path d="M0,0 L8,4 L0,8 z" fill="#d9480f" />',
        "</marker>",
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f8f6f2" />',
    ]

    if outline:
        points = [
            _map_point(Point(float(item["x"]), float(item["y"])), box, width, height)
            for item in outline.get("points", [])
        ]
        if points:
            path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
            parts.append(
                f'<polygon points="{path}" fill="none" stroke="#1f2937" stroke-width="2" />'
            )

    for record in after.objects.values():
        if record.position is None:
            continue
        cx, cy = _map_point(
            Point(record.position["x"], record.position["y"]),
            box,
            width,
            height,
        )
        radius = 5.0 if record.kind in {"component", "part"} else 3.0
        color = "#2563eb"
        if record.stable_id in changed_ids:
            color = "#d9480f"
        parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" fill="{color}" '
            f'stroke="#ffffff" stroke-width="1" />'
        )
        label = escape(record.label or record.refdes or record.name or record.stable_id)
        parts.append(
            f'<text x="{cx + 8:.2f}" y="{cy - 8:.2f}" fill="#111827" '
            f'font-family="ui-sans-serif,system-ui" font-size="12">{label}</text>'
        )
        if record.stable_id in changed_ids and record.stable_id in before_positions:
            bx, by = _map_point(before_positions[record.stable_id], box, width, height)
            parts.append(
                f'<line x1="{bx:.2f}" y1="{by:.2f}" x2="{cx:.2f}" y2="{cy:.2f}" '
                f'stroke="#d9480f" stroke-width="2" marker-end="url(#arrow)" />'
            )
    parts.append("</svg>")
    return "".join(parts)


def render_preview_json(
    before: DocumentSnapshot,
    after: DocumentSnapshot,
    changed_ids: list[str],
) -> dict[str, Any]:
    before_positions = {
        record.stable_id: record.position
        for record in before.objects.values()
        if record.position is not None
    }
    after_positions = {
        record.stable_id: record.position
        for record in after.objects.values()
        if record.position is not None
    }
    return {
        "changed_ids": changed_ids,
        "before_positions": before_positions,
        "after_positions": after_positions,
        "outline": after.board.outline if after.board else None,
    }
