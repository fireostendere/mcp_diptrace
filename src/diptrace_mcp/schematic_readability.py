"""Read-only, sheet-complete schematic geometry review (not native ERC)."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cached_property
from itertools import combinations
from typing import Any, Literal

from .adapter_common import _MARKING_TAGS, _component_markings_rotate, stable_id
from .adapters import DocumentSnapshot
from .errors import DocumentError
from .findings import Finding, make_finding
from .geometry import (
    BBox,
    Point,
    Transform,
    from_mm,
    point_in_polygon,
    point_to_segment_distance,
    segment_intersects_bbox,
    segments_intersect,
)
from .numeric_inputs import xml_number, xml_number_mm
from .schematic_layout import schematic_sheet_usable_bounds
from .services.schematic_wire_quality import _text_bbox
from .xml_document import DipTraceDocument

_EPS = 1e-6  # Drawing-coordinate tolerance, not an electrical clearance.


@dataclass(frozen=True)
class _Path:
    object_id: str
    points: tuple[Point, ...]
    net_id: str | None = None
    owner: str | None = None
    filled: bool = False

    @cached_property
    def box(self) -> BBox:
        return BBox.from_points(self.points)

    @cached_property
    def segments(self) -> list[tuple[Point, Point]]:
        return [(a, b) for a, b in zip(self.points, self.points[1:], strict=False)
                if a != b]


def _points(document: DipTraceDocument, element: ET.Element) -> tuple[Point, ...]:
    raw = element.findall('./Points/Point')
    if any(point.get('X') is None or point.get('Y') is None for point in raw):
        return ()
    return tuple(Point(xml_number_mm(document, point, 'X'),
                       xml_number_mm(document, point, 'Y')) for point in raw)


def _contact(a: Point, b: Point, c: Point, d: Point) -> tuple[str, BBox] | None:
    if not segments_intersect(a, b, c, d):
        return None
    # Projection also handles diagonal collinear overlaps, not just Manhattan wires.
    dx, dy = b.x - a.x, b.y - a.y
    cross_c = dx * (c.y - a.y) - dy * (c.x - a.x)
    cross_d = dx * (d.y - a.y) - dy * (d.x - a.x)
    length = math.hypot(dx, dy)
    if length and max(abs(cross_c), abs(cross_d)) <= _EPS * length:
        t1 = ((c.x - a.x) * dx + (c.y - a.y) * dy) / (length * length)
        t2 = ((d.x - a.x) * dx + (d.y - a.y) * dy) / (length * length)
        low, high = max(0.0, min(t1, t2)), min(1.0, max(t1, t2))
        if (high - low) * length > _EPS:
            return 'overlap', BBox.from_points([
                Point(a.x + low * dx, a.y + low * dy),
                Point(a.x + high * dx, a.y + high * dy),
            ])
    denominator = (b.x - a.x) * (d.y - c.y) - (b.y - a.y) * (d.x - c.x)
    if abs(denominator) > 1e-12:
        t = ((c.x - a.x) * (d.y - c.y) - (c.y - a.y) * (d.x - c.x)) / denominator
        point = Point(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y))
    else:
        point = next(p for p in (a, b, c, d)
                     if point_to_segment_distance(p, a, b) <= _EPS
                     and point_to_segment_distance(p, c, d) <= _EPS)
    return 'point', BBox.from_points([point])


def _contacts(
    first: _Path, second: _Path, *, allowed_tip: Point | None = None,
) -> dict[str, BBox]:
    if not first.box.intersects(second.box):
        return {}
    result: dict[str, BBox] = {}
    for a, b in first.segments:
        for c, d in second.segments:
            hit = _contact(a, b, c, d)
            if hit is not None:
                if (allowed_tip is not None and hit[0] == 'point'
                    and math.hypot(hit[1].min_x - allowed_tip.x,
                                   hit[1].min_y - allowed_tip.y) <= _EPS):
                    continue
                result.setdefault(hit[0], hit[1])
    return result


def _body_hit(wire: _Path, body: _Path) -> bool:
    return bool(_contacts(wire, body)) or (
        body.filled and any(point_in_polygon(point, body.points) for point in wire.points)
    )


def _library_units(document: DipTraceDocument) -> dict[tuple[str, str], ET.Element]:
    components = document.root.findall('./Library/Components/Component')
    explicit = any(c.get('ComponentStyle') is not None for c in components)
    result: dict[tuple[str, str], ET.Element] = {}
    duplicates: set[tuple[str, str]] = set()
    for index, component in enumerate(components):
        style = component.get('ComponentStyle', '') if explicit else f'CompType{index}'
        for part_index, unit in enumerate(component.findall('./Part')):
            key = style, unit.get('Id', str(part_index))
            if key in result:
                duplicates.add(key)
            result[key] = unit
    return {key: unit for key, unit in result.items() if key not in duplicates}


def check_schematic_readability(
    snapshot: DocumentSnapshot, *, sheets: list[int] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    if snapshot.schematic is None:
        raise DocumentError('Schematic readability requires a schematic document')
    model, document = snapshot.schematic, snapshot.document
    indices = list(range(len(model.sheets)))
    if sheets is not None and (
        not sheets or len(sheets) > 256
        or any(type(i) is not int or i not in indices for i in sheets)
        or len(sheets) != len(set(sheets))
    ):
        raise DocumentError('sheets must contain 1 to 256 unique existing zero-based sheet indices')
    selected = sorted(indices if sheets is None else sheets)
    bounds = schematic_sheet_usable_bounds(snapshot)
    rows: dict[str, dict[str, Any]] = {}
    for index in selected:
        descriptor = model.sheets[index]
        rows[str(index)] = {
            'index': index, 'id': descriptor.get('id'), 'name': descriptor.get('name'),
            **dict.fromkeys((
                'parts_checked', 'pin_stubs_checked', 'wire_count', 'wire_segments',
                'documentary_segments', 'different_net_crossings', 'collinear_overlaps',
                'documentary_crossings', 'documentary_overlaps', 'body_conflicts',
                'pin_stub_conflicts', 'port_tip_conflicts', 'texts_checked',
                'stored_texts_checked', 'estimated_texts_checked',
                'text_orientation_conflicts', 'text_collisions', 'outside_page',
                'unmeasured_symbol_texts', 'automatic_markings',
            ), 0),
            'missing_geometry': [],
        }
        if str(index) not in bounds:
            rows[str(index)]['missing_geometry'].append({'reason': 'sheet_bounds_unavailable'})

    findings: list[Finding] = []
    unassigned: list[dict[str, str]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def emit(
        sheet: str, code: str, counter: str, ids: list[str], box: BBox, message: str,
        severity: Literal['error', 'warning'] = 'error',
    ) -> None:
        key = sheet, code, tuple(sorted(ids))
        if key in seen:
            return
        seen.add(key)
        rows[sheet][counter] += 1
        findings.append(make_finding(
            f'schematic.readability.{code}', 'readability', severity,
            f'Schematic {code.replace("_", " ")}',
            f'Sheet {sheet} ({rows[sheet]["name"]!r}): {message}',
            object_ids=ids, layer=f'sheet:{sheet}', bbox=box.as_dict(),
            confidence=0.8 if code.startswith('text') else 0.95,
            rule_source='schematic readability house rules; exported XML geometry',
            suggested_actions=['Rearrange the functional block; keep short local wiring visible.'],
        ))

    def missing(sheet: str, object_id: str, reason: str) -> None:
        rows[sheet]['missing_geometry'].append({'object_id': object_id, 'reason': reason})

    def selected_sheet(raw: str, object_id: str) -> bool:
        if raw not in {str(i) for i in indices}:
            unassigned.append({'object_id': object_id, 'sheet': raw})
        return raw in rows

    def containment(
        sheet: str, object_id: str, box: BBox,
        severity: Literal['error', 'warning'] = 'error',
    ) -> None:
        bound = bounds.get(sheet)
        if bound is not None and not bound.expand(_EPS).contains_bbox(box):
            emit(sheet, 'sheet_containment', 'outside_page', [object_id], box,
                 'Object extends beyond the usable page bounds.', severity)

    wires: dict[str, list[_Path]] = {s: [] for s in rows}
    documentary: dict[str, list[_Path]] = {s: [] for s in rows}
    bodies: dict[str, list[_Path]] = {s: [] for s in rows}
    stubs: dict[str, list[_Path]] = {s: [] for s in rows}
    tips: dict[str, list[_Path]] = {s: [] for s in rows}
    texts: dict[str, list[tuple[str, BBox, bool]]] = {s: [] for s in rows}
    units = _library_units(document)

    for record in model.wires:
        sheet = str(record.attributes.get('sheet', ''))
        if not selected_sheet(sheet, record.stable_id):
            continue
        rows[sheet]['wire_count'] += 1
        element = snapshot.elements.get(record.stable_id)
        points = _points(document, element) if element is not None else tuple(
            Point(**p) for p in record.attributes.get('points', [])
        )
        path = _Path(record.stable_id, points, record.net_id)
        if len(points) < 2 or not path.segments:
            missing(sheet, record.stable_id, 'wire_polyline_unavailable')
            continue
        if record.net_id is None or record.net_id not in {n.xml_id for n in model.nets}:
            missing(sheet, record.stable_id, 'wire_net_unresolved')
        wires[sheet].append(path)
        rows[sheet]['wire_segments'] += len(path.segments)
        containment(sheet, record.stable_id, path.box)

    def add_text(sheet: str, object_id: str, shape: ET.Element) -> None:
        box = _text_bbox(document, shape, margin_mm=0.0)
        angle = xml_number(document, shape, 'Angle') % math.tau
        if not min(angle, math.tau - angle) <= 1e-3:
            emit(sheet, 'text_orientation', 'text_orientation_conflicts', [object_id],
                 box or BBox.empty(), 'Visible text is not horizontal and upright.')
        if box is None:
            missing(sheet, object_id, 'text_bounds_unavailable')
            return
        stored = shape.get('TextWidth') is not None and shape.get('TextHeight') is not None
        texts[sheet].append((object_id, box, stored))
        rows[sheet]['texts_checked'] += 1
        rows[sheet]['stored_texts_checked' if stored else 'estimated_texts_checked'] += 1
        containment(sheet, object_id, box, 'error' if stored else 'warning')

    for ordinal, shape in enumerate(document.container.findall('./Shapes/Shape')):
        if shape.get('Enabled', 'Y') != 'Y':
            continue
        object_id = stable_id('schematic-shape', shape.get('Id', str(ordinal)), str(ordinal))
        sheet = shape.get('Sheet', '0')
        if not selected_sheet(sheet, object_id):
            continue
        kind = shape.get('Type', '')
        if kind == 'Text':
            add_text(sheet, object_id, shape)
            continue
        points = _points(document, shape)
        if not points:
            missing(sheet, object_id, 'shape_points_unavailable')
            continue
        containment(sheet, object_id, BBox.from_points(points))
        if kind == 'Line':
            path = _Path(object_id, points)
            if len(points) != 2 or not path.segments:
                missing(sheet, object_id, 'documentary_line_requires_two_distinct_endpoints')
            else:
                documentary[sheet].append(path)
                rows[sheet]['documentary_segments'] += 1
        elif kind not in {'Rectangle', 'Polygon'}:
            missing(sheet, object_id, f'unsupported_documentary_shape:{kind}')

    for part in model.parts:
        sheet = str(part.attributes.get('sheet', ''))
        if not selected_sheet(sheet, part.stable_id):
            continue
        rows[sheet]['parts_checked'] += 1
        unit = units.get((str(part.attributes.get('component_style', '')),
                          str(part.attributes.get('component_part', ''))))
        if unit is None or part.position is None:
            missing(sheet, part.stable_id, 'embedded_symbol_unavailable_or_ambiguous')
            continue
        transform = Transform(
            translate_x=part.position['x'], translate_y=part.position['y'],
            rotation_deg=part.rotation_deg,
            mirror_x=bool(part.attributes.get('horz_flip')),
            mirror_y=bool(part.attributes.get('vert_flip')),
        )
        graphics = unit.findall('./Shapes/Shape')
        if not graphics:
            missing(sheet, part.stable_id, 'symbol_glyphs_unavailable')
        for shape in graphics:
            kind = shape.get('Type', '')
            if kind == 'Text':
                rows[sheet]['unmeasured_symbol_texts'] += 1
                continue
            local = _points(document, shape)
            if len(local) < 2:
                missing(sheet, part.stable_id, 'symbol_shape_points_unavailable')
                continue
            if kind == 'Rectangle':
                box = BBox.from_points(local)
                local = (Point(box.min_x, box.min_y), Point(box.max_x, box.min_y),
                         Point(box.max_x, box.max_y), Point(box.min_x, box.max_y),
                         Point(box.min_x, box.min_y))
            elif kind == 'Polygon':
                local = (*local, local[0])
            elif kind not in {'Line', 'Polyline'}:
                missing(sheet, part.stable_id, f'unsupported_symbol_shape:{kind}')
                continue
            body = _Path(part.stable_id, tuple(transform.apply_point(p) for p in local),
                         owner=part.stable_id, filled=kind in {'Rectangle', 'Polygon'})
            bodies[sheet].append(body)
            containment(sheet, part.stable_id, body.box)
        instance = snapshot.elements.get(part.stable_id)
        pin_elements = unit.findall('./Pins/Pin')
        instance_pins = instance.findall('./Pins/Pin') if instance is not None else []
        if len(pin_elements) != len(instance_pins):
            missing(sheet, part.stable_id, 'symbol_pin_map_incomplete')
        for index, pin in enumerate(pin_elements):
            if any(pin.get(attr) is None for attr in ('X', 'Y', 'Length', 'Orientation')):
                missing(sheet, part.stable_id, 'pin_stub_geometry_unavailable')
                continue
            anchor = Point(xml_number_mm(document, pin, 'X'), xml_number_mm(document, pin, 'Y'))
            angle = math.radians(xml_number(document, pin, 'Orientation'))
            length = xml_number_mm(document, pin, 'Length')
            tip = Point(anchor.x - math.cos(angle) * length, anchor.y + math.sin(angle) * length)
            pin_id = part.relationships.get('pins', [])[index] if index < len(
                part.relationships.get('pins', [])
            ) else stable_id('unmapped-pin', part.stable_id, str(index))
            net = instance_pins[index].get('NetId') if index < len(instance_pins) else None
            stub = _Path(pin_id, (transform.apply_point(anchor), transform.apply_point(tip)),
                         net, part.stable_id)
            stubs[sheet].append(stub)
            rows[sheet]['pin_stubs_checked'] += 1
            containment(sheet, pin_id, stub.box)
            if part.attributes.get('part_type') == 'Net Port':
                tips[sheet].append(stub)
        if instance is not None:
            for tag, field in _MARKING_TAGS:
                marking = instance.find(f'./{tag}')
                value = instance.findtext(f'./{field}', '').strip()
                if marking is None or marking.get('Show', 'Hide') == 'Hide' or not value:
                    continue
                if marking.get('Align', '') != 'Position':
                    # The native editor places it; nothing is exported to measure.
                    rows[sheet]['automatic_markings'] += 1
                    continue
                text_id = stable_id('schematic-marking', part.stable_id, tag)
                offset = transform.apply_point(Point(xml_number_mm(document, marking, 'X'),
                                                     xml_number_mm(document, marking, 'Y')))
                angle = xml_number(document, marking, 'Angle')
                if _component_markings_rotate(document):
                    angle += math.radians(part.rotation_deg)
                shape = ET.Element('Shape', {
                    **marking.attrib, 'Angle': str(angle),
                    'HorzAlign': marking.get('Horz', 'Center'),
                    'VertAlign': marking.get('Vert', 'Center'),
                    'FontSizeFloat': instance.get('MarkingFontSizeFloat',
                                                  instance.get('MarkingFontSize', '10')),
                })
                ET.SubElement(ET.SubElement(shape, 'Points'), 'Point',
                              X=str(from_mm(offset.x, document.units)),
                              Y=str(from_mm(offset.y, document.units)))
                ET.SubElement(ET.SubElement(shape, 'TextLines'), 'TextLine').text = value
                add_text(sheet, text_id, shape)

    # ponytail: per-sheet pair scans; use the existing SpatialIndex if large sheets become slow.
    for sheet in rows:
        for first, second in combinations(wires[sheet], 2):
            for kind, box in _contacts(first, second).items():
                if kind == 'overlap':
                    emit(sheet, 'wire_overlap', 'collinear_overlaps',
                         [first.object_id, second.object_id], box,
                         'Wire lanes overlap collinearly.')
                elif first.net_id is None or first.net_id != second.net_id:
                    emit(sheet, 'wire_crossing', 'different_net_crossings',
                         [first.object_id, second.object_id], box,
                         'Different-net full polylines intersect (not an electrical-short claim).')
        for first, second in combinations(documentary[sheet], 2):
            for kind, box in _contacts(first, second).items():
                if kind == 'point' and any(a == b for a in first.points for b in second.points):
                    continue
                emit(sheet, f'documentary_{"overlap" if kind == "overlap" else "crossing"}',
                     'documentary_overlaps' if kind == 'overlap' else 'documentary_crossings',
                     [first.object_id, second.object_id], box,
                     'Documentary connection lines conflict.')
        for wire in wires[sheet]:
            for body in bodies[sheet]:
                if _body_hit(wire, body):
                    emit(sheet, 'wire_body', 'body_conflicts', [wire.object_id, body.object_id],
                         body.box, 'Wire crosses a symbol glyph/body.')
            for stub in stubs[sheet]:
                # Exempt only the legitimate tip, not other contacts later in the polyline.
                allowed_tip = (stub.points[-1] if wire.net_id not in {None, '-1'}
                               and wire.net_id == stub.net_id else None)
                hits = _contacts(wire, stub, allowed_tip=allowed_tip)
                if hits:
                    emit(sheet, 'wire_pin_stub', 'pin_stub_conflicts',
                         [wire.object_id, stub.object_id], stub.box,
                         'Wire crosses a foreign pin/stub.')
        for port in tips[sheet]:
            for stub in stubs[sheet]:
                if port.owner == stub.owner or (port.net_id not in {None, '-1'}
                                               and port.net_id == stub.net_id):
                    continue
                if point_to_segment_distance(port.points[-1], *stub.points) <= _EPS:
                    emit(sheet, 'port_tip', 'port_tip_conflicts', [port.object_id, stub.object_id],
                         BBox.from_points([port.points[-1]]),
                         'Net Port tip lies on a foreign shaft.')
        for text_id, box, stored in texts[sheet]:
            for path in [*wires[sheet], *stubs[sheet], *bodies[sheet]]:
                if any(segment_intersects_bbox(a, b, box) for a, b in path.segments):
                    emit(sheet, 'text_collision', 'text_collisions', [text_id, path.object_id],
                         box, 'Text corridor intersects a wire, glyph or pin shaft '
                         f'({"stored" if stored else "estimated"} bounds).',
                         'error' if stored else 'warning')
            for other_id, other_box, other_stored in texts[sheet]:
                if text_id < other_id and box.intersection(other_box) is not None:
                    emit(sheet, 'text_collision', 'text_collisions', [text_id, other_id],
                         box, 'Visible text corridors overlap '
                         f'({"stored" if stored and other_stored else "estimated"} bounds).',
                         'error' if stored and other_stored else 'warning')

    metrics: dict[str, Any] = {
        'scope': 'all_sheets' if sheets is None else 'selected_sheets',
        'checked_sheet_indices': selected,
        'excluded_sheet_indices': [i for i in indices if i not in selected],
        'all_sheets_checked': selected == indices and bool(indices),
        'geometry_complete': bool(rows) and not unassigned
                             and not any(row['missing_geometry'] for row in rows.values()),
        'sheets': list(rows.values()), 'unassigned_objects': unassigned,
        'evidence_class': 'analytical', 'text_evidence_class': 'heuristic',
        'limitations': [
            'Exported centerline geometry is not native ERC, electrical connectivity '
            'or visual acceptance.',
            'Text corridors use stored dimensions or ASCII vector-font estimates, '
            'not native font metrics.',
            'Symbol text and native pin-name/number glyphs are not measured; '
            'inspect native page-fit views.',
            'Markings on automatic alignment are placed by the native editor: counted, '
            'not measured; inspect native page-fit views.',
            'Curved/unknown symbol primitives are explicitly missing, '
            'not approximated as clean geometry.',
            'Only Shape Type=Line is a documentary channel; rectangle borders are not connections.',
        ],
    }
    if not metrics['geometry_complete']:
        metrics['partial_skipped'] = 'schematic_readability_geometry_incomplete'
    return findings, metrics
