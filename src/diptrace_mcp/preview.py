from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from typing import Any, Literal

from .adapters import DocumentSnapshot
from .domain import ObjectRecord
from .geometry import BBox, Point

PREVIEW_COPPER_RECORD_LIMIT = 500
PREVIEW_COPPER_POINT_LIMIT = 10_000


@dataclass(frozen=True, slots=True)
class _CopperPrimitive:
    object_id: str
    kind: Literal["trace", "copper_pour"]
    points: tuple[Point, ...]
    layer: str | None
    segment_widths_mm: tuple[float, ...]
    segment_layers: tuple[str, ...]
    changed: bool


def _is_changed(record: ObjectRecord, changed_ids: set[str]) -> bool:
    return record.stable_id in changed_ids


def _normalized_points(record: ObjectRecord) -> tuple[Point, ...] | None:
    raw_points = record.attributes.get("points")
    if not isinstance(raw_points, list):
        return None
    points: list[Point] = []
    for item in raw_points:
        if not isinstance(item, dict) or "x" not in item or "y" not in item:
            return None
        x = item["x"]
        y = item["y"]
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            return None
        x_value = float(x)
        y_value = float(y)
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            return None
        points.append(Point(x_value, y_value))
    return tuple(points)


def _normalized_trace_style(
    record: ObjectRecord,
) -> tuple[tuple[float, ...], tuple[str, ...]] | None:
    raw_widths = record.attributes.get("segment_widths_mm")
    raw_layers = record.attributes.get("segment_layers")
    if not isinstance(raw_widths, list) or not isinstance(raw_layers, list):
        return None
    widths: list[float] = []
    for value in raw_widths:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        width = float(value)
        if not math.isfinite(width) or width < 0.0:
            return None
        widths.append(width)
    if any(not isinstance(value, str) for value in raw_layers):
        return None
    return tuple(widths), tuple(raw_layers)


def _select_copper_primitives(
    snapshot: DocumentSnapshot,
    changed_ids: list[str],
    *,
    changed_only: bool = False,
) -> tuple[list[_CopperPrimitive], dict[str, Any]]:
    changed = set(changed_ids)
    records: list[ObjectRecord] = []
    if snapshot.board is not None:
        records = [*snapshot.board.traces, *snapshot.board.copper_pours]
    if changed_only:
        records = [record for record in records if _is_changed(record, changed)]
    records.sort(
        key=lambda record: (
            not _is_changed(record, changed),
            record.kind,
            record.stable_id,
        )
    )

    primitives: list[_CopperPrimitive] = []
    rendered_points = 0
    invalid_geometry_count = 0
    omitted_record_count = 0
    rendered_by_kind = {"trace": 0, "copper_pour": 0}
    total_by_kind = {
        "trace": sum(record.kind == "trace" for record in records),
        "copper_pour": sum(record.kind == "copper_pour" for record in records),
    }
    for record in records:
        points = _normalized_points(record)
        minimum_points = 2 if record.kind == "trace" else 3
        if points is None or len(points) < minimum_points:
            invalid_geometry_count += 1
            continue
        trace_style = (
            _normalized_trace_style(record)
            if record.kind == "trace"
            else ((), ())
        )
        if trace_style is None:
            invalid_geometry_count += 1
            continue
        if (
            len(primitives) >= PREVIEW_COPPER_RECORD_LIMIT
            or rendered_points + len(points) > PREVIEW_COPPER_POINT_LIMIT
        ):
            omitted_record_count += 1
            continue
        widths, layers = trace_style
        kind: Literal["trace", "copper_pour"] = (
            "trace" if record.kind == "trace" else "copper_pour"
        )
        primitive = _CopperPrimitive(
            object_id=record.stable_id,
            kind=kind,
            points=points,
            layer=record.layer,
            segment_widths_mm=widths,
            segment_layers=layers,
            changed=_is_changed(record, changed),
        )
        primitives.append(primitive)
        rendered_points += len(points)
        rendered_by_kind[kind] += 1
    metadata = {
        "scope": "normalized_trace_centerlines_and_exported_pour_boundaries",
        "record_limit": PREVIEW_COPPER_RECORD_LIMIT,
        "point_limit": PREVIEW_COPPER_POINT_LIMIT,
        "total_record_count": len(records),
        "rendered_record_count": len(primitives),
        "rendered_point_count": rendered_points,
        "omitted_record_count": omitted_record_count,
        "invalid_geometry_count": invalid_geometry_count,
        "truncated": omitted_record_count > 0,
        "complete": omitted_record_count == 0 and invalid_geometry_count == 0,
        "trace_count": {
            "total": total_by_kind["trace"],
            "rendered": rendered_by_kind["trace"],
        },
        "copper_pour_count": {
            "total": total_by_kind["copper_pour"],
            "rendered": rendered_by_kind["copper_pour"],
        },
        "limitations": [
            "Trace copper is a centerline preview of normalized exported points; "
            "arc triples are drawn as straight point-to-point chords.",
            "Copper-pour geometry is the exported boundary only, not authoritative "
            "refilled copper, thermals, cutouts, or islands.",
        ],
    }
    return primitives, metadata


def _all_points(
    snapshot: DocumentSnapshot,
    copper_primitives: list[_CopperPrimitive],
) -> list[Point]:
    points: list[Point] = []
    if snapshot.board and snapshot.board.outline:
        for item in snapshot.board.outline.get("points", []):
            points.append(Point(float(item["x"]), float(item["y"])))
    for primitive in copper_primitives:
        points.extend(primitive.points)
    for record in snapshot.objects.values():
        if record.position:
            points.append(Point(float(record.position["x"]), float(record.position["y"])))
    if not points:
        points = [Point(0.0, 0.0), Point(10.0, 10.0)]
    return points


def _bounds(
    snapshot: DocumentSnapshot,
    copper_primitives: list[_CopperPrimitive],
) -> BBox:
    points = _all_points(snapshot, copper_primitives)
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


def _svg_attributes(primitive: _CopperPrimitive, state: str) -> str:
    return (
        f'data-object-id="{escape(primitive.object_id, quote=True)}" '
        f'data-kind="{primitive.kind}" '
        f'data-state="{state}" '
        f'data-layer="{escape(primitive.layer or "", quote=True)}"'
    )


def _render_pour_svg(
    primitive: _CopperPrimitive,
    box: BBox,
    width: int,
    height: int,
    *,
    state: Literal["before", "after"],
) -> str:
    mapped = [_map_point(point, box, width, height) for point in primitive.points]
    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in mapped)
    changed = primitive.changed
    if state == "before":
        return (
            f'<polygon {_svg_attributes(primitive, state)} points="{points}" '
            'fill="none" stroke="#d9480f" stroke-width="2" '
            'stroke-dasharray="6 4" opacity="0.75" />'
        )
    color = "#d9480f" if changed else "#d97706"
    return (
        f'<polygon {_svg_attributes(primitive, state)} '
        'data-geometry-scope="exported-boundary-only" '
        f'points="{points}" fill="{color}" fill-opacity="0.16" '
        f'stroke="{color}" stroke-width="1.5" />'
    )


def _render_trace_svg(
    primitive: _CopperPrimitive,
    box: BBox,
    width: int,
    height: int,
    *,
    state: Literal["before", "after"],
) -> list[str]:
    scale, _origin_x, _origin_y = _scale(box, width, height)
    color = "#d9480f" if primitive.changed or state == "before" else "#b45309"
    result: list[str] = []
    for index, (start, end) in enumerate(
        zip(primitive.points, primitive.points[1:], strict=False)
    ):
        x1, y1 = _map_point(start, box, width, height)
        x2, y2 = _map_point(end, box, width, height)
        width_mm = (
            primitive.segment_widths_mm[index]
            if index < len(primitive.segment_widths_mm)
            else 0.0
        )
        layer = (
            primitive.segment_layers[index]
            if index < len(primitive.segment_layers)
            else primitive.layer or ""
        )
        dash = ' stroke-dasharray="6 4" opacity="0.75"' if state == "before" else ""
        result.append(
            f'<line {_svg_attributes(primitive, state)} '
            f'data-segment-index="{index}" '
            f'data-segment-layer="{escape(layer, quote=True)}" '
            f'data-width-mm="{width_mm:g}" '
            f'x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="{max(1.0, width_mm * scale):.2f}" '
            f'stroke-linecap="round"{dash} />'
        )
    return result


def _primitive_payload(primitive: _CopperPrimitive) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "object_id": primitive.object_id,
        "kind": primitive.kind,
        "layer": primitive.layer,
        "changed": primitive.changed,
        "points": [point.as_dict() for point in primitive.points],
    }
    if primitive.kind == "trace":
        payload.update(
            {
                "geometry_scope": "normalized_centerline",
                "segment_widths_mm": list(primitive.segment_widths_mm),
                "segment_layers": list(primitive.segment_layers),
            }
        )
    else:
        payload["geometry_scope"] = "exported_boundary_only"
    return payload


def render_preview_svg(
    before: DocumentSnapshot,
    after: DocumentSnapshot,
    changed_ids: list[str],
    *,
    width: int = 960,
    height: int = 640,
) -> str:
    after_copper, after_copper_metadata = _select_copper_primitives(
        after, changed_ids
    )
    before_changed_copper, before_copper_metadata = _select_copper_primitives(
        before,
        changed_ids,
        changed_only=True,
    )
    box = _bounds(after, [*after_copper, *before_changed_copper])
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
        (
            '<metadata id="diptrace-copper-preview">'
            f'after-complete={str(after_copper_metadata["complete"]).lower()};'
            f'before-changed-complete={str(before_copper_metadata["complete"]).lower()}'
            "</metadata>"
        ),
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

    for primitive in before_changed_copper:
        if primitive.kind == "copper_pour":
            parts.append(
                _render_pour_svg(
                    primitive,
                    box,
                    width,
                    height,
                    state="before",
                )
            )
        else:
            parts.extend(
                _render_trace_svg(
                    primitive,
                    box,
                    width,
                    height,
                    state="before",
                )
            )
    for primitive in after_copper:
        if primitive.kind == "copper_pour":
            parts.append(
                _render_pour_svg(
                    primitive,
                    box,
                    width,
                    height,
                    state="after",
                )
            )
        else:
            parts.extend(
                _render_trace_svg(
                    primitive,
                    box,
                    width,
                    height,
                    state="after",
                )
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
    after_copper, after_copper_metadata = _select_copper_primitives(
        after, changed_ids
    )
    before_changed_copper, before_copper_metadata = _select_copper_primitives(
        before,
        changed_ids,
        changed_only=True,
    )
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
        "copper": {
            "after": {
                **after_copper_metadata,
                "primitives": [
                    _primitive_payload(primitive) for primitive in after_copper
                ],
            },
            "before_changed": {
                **before_copper_metadata,
                "primitives": [
                    _primitive_payload(primitive)
                    for primitive in before_changed_copper
                ],
            },
        },
    }
