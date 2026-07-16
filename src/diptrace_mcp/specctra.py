from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, SpecctraNetRoute, SpecctraSession, SpecctraVia, SpecctraWire
from .errors import CapabilityUnavailableError, DocumentError, GeometryError
from .geometry import Point, distance, to_mm
from .operations import AddTraceOperation, TracePathPoint
from .via_styles import resolve_via_span, validate_via_geometry

_UNIT_TO_MM = {"mm": 1.0, "um": 0.001, "mil": 0.0254, "inch": 25.4}


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _coordinate(value: float, resolution: int) -> str:
    return str(int(round(value * resolution)))


def _supported_pad_shape(shape: str) -> bool:
    return shape.casefold() in {"rectangle", "rect", "ellipse", "oval", "obround", "circle"}


def dsn_export_limitations(snapshot: DocumentSnapshot) -> list[str]:
    board = snapshot.board
    if board is None:
        return ["Specctra DSN export requires a PCB document."]
    reasons: list[str] = []
    if board.outline is None or len(board.outline.get("points", [])) < 3:
        reasons.append("A polygonal board outline with at least three points is required.")
    if not board.layers:
        reasons.append("At least one copper layer is required.")
    if board.cutouts:
        reasons.append("Board cutouts are not supported by the current DSN serializer.")
    if board.keepouts:
        reasons.append("Route/placement keepouts are not supported by the current DSN serializer.")
    if board.copper_pours:
        reasons.append("Copper pours are not supported by the current DSN serializer.")
    patterns = {item.style: item for item in board.patterns if item.style}
    styles = {item.name: item for item in board.pad_styles}
    for component in board.components:
        style_name = str(component.attributes.get("pattern_style", ""))
        if not component.refdes or component.position is None:
            reasons.append(f"Component {component.stable_id} lacks RefDes or placement geometry.")
        if not style_name or style_name not in patterns:
            reasons.append(
                f"Component {component.refdes or component.stable_id} has no embedded pattern."
            )
    for pattern in patterns.values():
        if not pattern.pads:
            reasons.append(f"Pattern {pattern.name or pattern.stable_id} has no pads.")
        for pad in pattern.pads:
            style = styles.get(pad.style)
            if style is None:
                reasons.append(
                    f"Pattern pad {pad.stable_id} references missing style {pad.style!r}."
                )
            elif not _supported_pad_shape(style.shape) or style.width <= 0 or style.height <= 0:
                reasons.append(
                    f"Pad style {style.name!r} has unsupported or incomplete shape geometry."
                )
    for net in board.nets:
        for endpoint_id in net.relationships.get("endpoints", []):
            endpoint = snapshot.objects.get(endpoint_id)
            if endpoint is None or endpoint.position is None or endpoint.parent_id is None:
                reasons.append(f"Net {net.name or net.stable_id} has an unresolved pad endpoint.")
    for via_style in board.via_styles:
        try:
            validate_via_geometry(via_style)
            resolve_via_span(board, via_style)
        except (CapabilityUnavailableError, GeometryError) as exc:
            reasons.append(f"Via style {via_style.id} is not exportable: {exc}")
    return sorted(set(reasons))


def _padstack_shape(
    *,
    layer: str,
    shape: str,
    width: float,
    height: float,
    resolution: int,
) -> str:
    half_width = width / 2.0
    half_height = height / 2.0
    shape_name = shape.casefold()
    if shape_name in {"rectangle", "rect"}:
        return (
            f"(shape (rect {_quote(layer)} {_coordinate(-half_width, resolution)} "
            f"{_coordinate(-half_height, resolution)} {_coordinate(half_width, resolution)} "
            f"{_coordinate(half_height, resolution)}))"
        )
    if math.isclose(width, height, rel_tol=0.0, abs_tol=1e-9):
        return f"(shape (circle {_quote(layer)} {_coordinate(width, resolution)}))"
    path_width = min(width, height)
    if width > height:
        start = Point(-(width - path_width) / 2.0, 0.0)
        end = Point((width - path_width) / 2.0, 0.0)
    else:
        start = Point(0.0, -(height - path_width) / 2.0)
        end = Point(0.0, (height - path_width) / 2.0)
    return (
        f"(shape (path {_quote(layer)} {_coordinate(path_width, resolution)} "
        f"{_coordinate(start.x, resolution)} {_coordinate(start.y, resolution)} "
        f"{_coordinate(end.x, resolution)} {_coordinate(end.y, resolution)}))"
    )


def export_dsn(snapshot: DocumentSnapshot, *, design_name: str | None = None) -> bytes:
    board = snapshot.board
    reasons = dsn_export_limitations(snapshot)
    if board is None or reasons:
        raise CapabilityUnavailableError(
            "The PCB does not contain sufficient verified geometry for Specctra DSN export",
            details={"reasons": reasons},
        )
    assert board.outline is not None
    resolution = 1000
    name = design_name or snapshot.info.document_id
    layers = [str(item.get("name") or item.get("id")) for item in board.layers]
    layer_by_id = {
        str(item.get("id")): str(item.get("name") or item.get("id")) for item in board.layers
    }
    patterns = {item.style: item for item in board.patterns if item.style}
    styles = {item.name: item for item in board.pad_styles}
    via_names = {item.id: f"MCP_VIA_{item.id}" for item in board.via_styles}
    default_width = to_mm(
        float(
            board.rules.get("routing_defaults", {})
            .get("attributes", {})
            .get("TraceWidth", 0.25)
        ),
        snapshot.info.units,
    )
    default_clearance = to_mm(
        float(
            board.rules.get("routing_defaults", {})
            .get("attributes", {})
            .get("TraceClearance", 0.2)
        ),
        snapshot.info.units,
    )
    lines = [
        f"(pcb {_quote(name)}",
        '  (parser (string_quote ") (space_in_quoted_tokens on)',
        '    (host_cad "DipTrace MCP") (host_version "0.1"))',
        f"  (resolution mm {resolution})",
        "  (unit mm)",
        "  (structure",
    ]
    for index, layer in enumerate(layers):
        layer_type = str(board.layers[index].get("type", "Signal")).casefold()
        dsn_type = "power" if layer_type == "plane" else "signal"
        lines.extend(
            [
                f"    (layer {_quote(layer)} (type {dsn_type})",
                f"      (property (index {index})))",
            ]
        )
    outline = [Point(**item) for item in board.outline["points"]]
    if outline[0] != outline[-1]:
        outline.append(outline[0])
    outline_values = " ".join(
        f"{_coordinate(point.x, resolution)} {_coordinate(point.y, resolution)}"
        for point in outline
    )
    lines.append(f"    (boundary (path pcb 0 {outline_values}))")
    if via_names:
        lines.append("    (via " + " ".join(_quote(item) for item in via_names.values()) + ")")
    lines.extend(
        [
            "    (rule",
            f"      (width {_coordinate(default_width, resolution)})",
            f"      (clearance {_coordinate(default_clearance, resolution)}))",
            "  )",
            "  (placement",
        ]
    )
    components_by_pattern: dict[str, list[ObjectRecord]] = defaultdict(list)
    for component in board.components:
        components_by_pattern[str(component.attributes["pattern_style"])].append(component)
    for pattern_style in sorted(components_by_pattern):
        lines.append(f"    (component {_quote(pattern_style)}")
        for component in sorted(
            components_by_pattern[pattern_style], key=lambda item: item.refdes or ""
        ):
            assert component.position is not None and component.refdes is not None
            side = "back" if component.side == "Bottom" else "front"
            lock = " (lock_type position)" if component.locked else ""
            lines.append(
                f"      (place {_quote(component.refdes)} "
                f"{_coordinate(component.position['x'], resolution)} "
                f"{_coordinate(component.position['y'], resolution)} {side} "
                f"{component.rotation_deg:g}{lock})"
            )
        lines.append("    )")
    lines.extend(["  )", "  (library"])
    for pattern_style in sorted(components_by_pattern):
        pattern = patterns[pattern_style]
        lines.append(f"    (image {_quote(pattern_style)}")
        for pad in pattern.pads:
            rotation = f" (rotate {pad.rotation_deg:g})" if pad.rotation_deg else ""
            lines.append(
                f"      (pin {_quote('PAD_' + pad.style)} {_quote(pad.number or pad.xml_id)} "
                f"{_coordinate(pad.position['x'], resolution)} "
                f"{_coordinate(pad.position['y'], resolution)}{rotation})"
            )
        if pattern.bbox is not None:
            box = pattern.bbox
            coords = " ".join(
                _coordinate(value, resolution)
                for value in (
                    box["min_x"],
                    box["min_y"],
                    box["max_x"],
                    box["min_y"],
                    box["max_x"],
                    box["max_y"],
                    box["min_x"],
                    box["max_y"],
                    box["min_x"],
                    box["min_y"],
                )
            )
            lines.append(f"      (outline (path signal 0 {coords}))")
        lines.append("    )")
    for style_name in sorted(styles):
        style = styles[style_name]
        shape_layers = layers if style.pad_type.casefold() != "surface" else [layers[0]]
        lines.append(f"    (padstack {_quote('PAD_' + style.name)}")
        for layer in shape_layers:
            lines.append(
                "      "
                + _padstack_shape(
                    layer=layer,
                    shape=style.shape,
                    width=style.width,
                    height=style.height,
                    resolution=resolution,
                )
            )
        lines.append("      (attach off)")
        lines.append("    )")
    for style_id, via_name in sorted(via_names.items()):
        via_style_record = next(
            item for item in board.via_styles if item.id == style_id
        )
        diameter, _hole = validate_via_geometry(via_style_record)
        span = resolve_via_span(board, via_style_record)
        lines.append(f"    (padstack {_quote(via_name)}")
        for layer_id in span:
            layer = layer_by_id[layer_id]
            lines.append(
                f"      (shape (circle {_quote(layer)} {_coordinate(diameter, resolution)}))"
            )
        lines.extend(["      (attach off)", "    )"])
    lines.extend(["  )", "  (network"])
    for net in sorted(board.nets, key=lambda item: item.name or ""):
        if not net.name:
            continue
        pins: list[str] = []
        for endpoint_id in net.relationships.get("endpoints", []):
            endpoint = snapshot.get_object(endpoint_id)
            parent = snapshot.get_object(endpoint.parent_id or "")
            if parent.refdes is None:
                continue
            number = str(endpoint.attributes.get("number") or endpoint.label or endpoint.xml_id)
            pins.append(f"{_quote(parent.refdes)}-{_quote(number)}")
        lines.extend(
            [
                f"    (net {_quote(net.name)}",
                f"      (pins {' '.join(pins)}))",
            ]
        )
    net_names = " ".join(_quote(item.name) for item in board.nets if item.name)
    lines.extend(
        [
            f"    (class {_quote('Default')} {net_names}",
            f"      (rule (width {_coordinate(default_width, resolution)}) "
            f"(clearance {_coordinate(default_clearance, resolution)})))",
            "  )",
            "  (wiring",
        ]
    )
    for trace in board.traces:
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        segment_layers = list(trace.attributes.get("segment_layers", []))
        widths = list(trace.attributes.get("segment_widths_mm", []))
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            layer = layer_by_id.get(str(segment_layers[index]), str(segment_layers[index]))
            width = float(widths[index])
            net_name = trace.net_name or ""
            lines.append(
                f"    (wire (path {_quote(layer)} {_coordinate(width, resolution)} "
                f"{_coordinate(start.x, resolution)} {_coordinate(start.y, resolution)} "
                f"{_coordinate(end.x, resolution)} {_coordinate(end.y, resolution)}) "
                f"(net {_quote(net_name)}) (type protect))"
            )
        for via_id in trace.relationships.get("vias", []):
            via_record = snapshot.get_object(via_id)
            style_id = str(via_record.attributes.get("via_style", ""))
            if via_record.position is None or style_id not in via_names:
                continue
            lines.append(
                f"    (via {_quote(via_names[style_id])} "
                f"{_coordinate(via_record.position['x'], resolution)} "
                f"{_coordinate(via_record.position['y'], resolution)} "
                f"(net {_quote(via_record.net_name or '')}) (type protect))"
            )
    lines.extend(["  )", ")", ""])
    return "\n".join(lines).encode("utf-8")


class _SExprParser:
    def __init__(self, text: str, *, max_tokens: int, max_depth: int) -> None:
        self.text = text
        self.max_tokens = max_tokens
        self.max_depth = max_depth
        self.index = 0
        self.tokens = 0

    def parse(self) -> list[Any]:
        values: list[Any] = []
        while self._skip_space():
            values.append(self._value(0))
        return values

    def _skip_space(self) -> bool:
        while self.index < len(self.text):
            char = self.text[self.index]
            if char.isspace():
                self.index += 1
                continue
            if char in {";", "#"}:
                newline = self.text.find("\n", self.index)
                self.index = len(self.text) if newline < 0 else newline + 1
                continue
            return True
        return False

    def _value(self, depth: int) -> Any:
        self.tokens += 1
        if self.tokens > self.max_tokens:
            raise DocumentError("Specctra file exceeds the token limit")
        if depth > self.max_depth:
            raise DocumentError("Specctra file exceeds the nesting limit")
        if not self._skip_space():
            raise DocumentError("Unexpected end of Specctra file")
        char = self.text[self.index]
        if char == "(":
            self.index += 1
            result: list[Any] = []
            while True:
                if not self._skip_space():
                    raise DocumentError("Unclosed Specctra scope")
                if self.text[self.index] == ")":
                    self.index += 1
                    return result
                result.append(self._value(depth + 1))
        if char == ")":
            raise DocumentError("Unexpected closing parenthesis in Specctra file")
        if char == '"':
            return self._quoted()
        start = self.index
        while self.index < len(self.text) and not self.text[self.index].isspace():
            if self.text[self.index] in "()":
                break
            self.index += 1
        if start == self.index:
            raise DocumentError(f"Invalid Specctra token at character {self.index}")
        return self.text[start : self.index]

    def _quoted(self) -> str:
        self.index += 1
        result: list[str] = []
        while self.index < len(self.text):
            char = self.text[self.index]
            self.index += 1
            if char == '"':
                return "".join(result)
            if char == "\\":
                if self.index >= len(self.text):
                    break
                escaped = self.text[self.index]
                self.index += 1
                result.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
            else:
                result.append(char)
        raise DocumentError("Unclosed quoted string in Specctra file")


def _scopes(value: list[Any], name: str) -> Iterator[list[Any]]:
    for item in value[1:]:
        if isinstance(item, list) and item and item[0] == name:
            yield item


def _number(value: Any, context: str) -> float:
    if not isinstance(value, str):
        raise DocumentError(f"Expected a number in {context}")
    try:
        return float(value)
    except ValueError as exc:
        raise DocumentError(f"Invalid number {value!r} in {context}") from exc


def parse_ses(data: bytes, *, max_bytes: int = 128 * 1024 * 1024) -> SpecctraSession:
    if len(data) > max_bytes:
        raise DocumentError(f"SES file exceeds {max_bytes} bytes")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentError("SES file must be UTF-8 text") from exc
    roots = _SExprParser(text, max_tokens=2_000_000, max_depth=128).parse()
    if len(roots) != 1 or not isinstance(roots[0], list) or not roots[0]:
        raise DocumentError("SES file must contain exactly one session scope")
    session_scope = roots[0]
    if session_scope[0] != "session" or len(session_scope) < 2:
        raise DocumentError("Specctra file is not a session file")
    session_name = str(session_scope[1])
    base_scope = next(_scopes(session_scope, "base_design"), None)
    base_design = str(base_scope[1]) if base_scope is not None and len(base_scope) > 1 else ""
    routes_scope = next(_scopes(session_scope, "routes"), None)
    if routes_scope is None:
        raise DocumentError("SES file has no routes scope")
    resolution_scope = next(_scopes(routes_scope, "resolution"), None)
    if resolution_scope is None or len(resolution_scope) < 3:
        raise DocumentError("SES routes scope has no valid resolution")
    unit = str(resolution_scope[1]).casefold()
    resolution = _number(resolution_scope[2], "resolution")
    if unit not in _UNIT_TO_MM or resolution <= 0:
        raise DocumentError(f"Unsupported SES resolution unit: {unit}")
    scale = _UNIT_TO_MM[unit] / resolution
    library_scope = next(_scopes(routes_scope, "library_out"), None)
    padstacks = [
        str(item[1])
        for item in _scopes(library_scope or [], "padstack")
        if len(item) > 1
    ]
    network_scope = next(_scopes(routes_scope, "network_out"), None)
    if network_scope is None:
        raise DocumentError("SES routes scope has no network_out scope")
    routes: list[SpecctraNetRoute] = []
    for net_scope in _scopes(network_scope, "net"):
        if len(net_scope) < 2:
            raise DocumentError("SES net scope has no name")
        wires: list[SpecctraWire] = []
        vias: list[SpecctraVia] = []
        for wire_scope in _scopes(net_scope, "wire"):
            path_scope = next(
                (
                    item
                    for item in wire_scope[1:]
                    if isinstance(item, list) and item and item[0] in {"path", "polygon_path"}
                ),
                None,
            )
            if path_scope is None:
                continue
            if len(path_scope) < 7 or (len(path_scope) - 3) % 2:
                raise DocumentError(f"SES wire for net {net_scope[1]!r} has an invalid path")
            coordinates = [
                _number(item, f"wire for net {net_scope[1]}") * scale for item in path_scope[3:]
            ]
            wires.append(
                SpecctraWire(
                    layer=str(path_scope[1]),
                    width_mm=_number(path_scope[2], "wire width") * scale,
                    points=[
                        {"x": coordinates[index], "y": coordinates[index + 1]}
                        for index in range(0, len(coordinates), 2)
                    ],
                )
            )
        for via_scope in _scopes(net_scope, "via"):
            if len(via_scope) < 4:
                raise DocumentError(f"SES via for net {net_scope[1]!r} is incomplete")
            vias.append(
                SpecctraVia(
                    padstack=str(via_scope[1]),
                    position={
                        "x": _number(via_scope[2], "via x") * scale,
                        "y": _number(via_scope[3], "via y") * scale,
                    },
                )
            )
        routes.append(SpecctraNetRoute(name=str(net_scope[1]), wires=wires, vias=vias))
    return SpecctraSession(
        name=session_name,
        base_design=base_design,
        resolution_unit=unit,
        resolution=resolution,
        routes=routes,
        padstacks=padstacks,
    )


@dataclass(frozen=True, slots=True)
class SesOperationPlan:
    operations: list[AddTraceOperation]
    imported_nets: list[str]
    skipped: list[dict[str, Any]]
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RouteEdge:
    start: tuple[int, int]
    end: tuple[int, int]
    layer: str
    width: float


def _point_key(point: dict[str, float], tolerance: float = 1e-6) -> tuple[int, int]:
    return (round(point["x"] / tolerance), round(point["y"] / tolerance))


def _pad_for_key(
    endpoints: list[ObjectRecord], key: tuple[int, int], tolerance: float = 0.02
) -> ObjectRecord | None:
    coordinate = Point(key[0] * 1e-6, key[1] * 1e-6)
    matches = [
        item
        for item in endpoints
        if item.position is not None and distance(Point(**item.position), coordinate) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def session_to_operations(
    snapshot: DocumentSnapshot,
    session: SpecctraSession,
    *,
    via_style: str | None = None,
) -> SesOperationPlan:
    board = snapshot.board
    if board is None:
        raise CapabilityUnavailableError("SES import requires a PCB document")
    layer_names = {str(item.get("name")): str(item.get("id")) for item in board.layers}
    nets_by_name = {(item.name or "").casefold(): item for item in board.nets if item.name}
    operations: list[AddTraceOperation] = []
    imported: list[str] = []
    skipped: list[dict[str, Any]] = []
    total_length = 0.0
    for route in session.routes:
        net = nets_by_name.get(route.name.casefold())
        reason: str | None = None
        if net is None:
            reason = "net_not_found"
        elif net.relationships.get("traces"):
            reason = "existing_routes_present"
        elif len(net.relationships.get("endpoints", [])) != 2:
            reason = "only_two_endpoint_nets_are_importable"
        elif route.vias and via_style is None:
            reason = "via_style_mapping_required"
        elif any(wire.layer not in layer_names for wire in route.wires):
            reason = "layer_not_found"
        if reason is not None:
            skipped.append({"net": route.name, "reason": reason})
            continue
        assert net is not None
        endpoints = [snapshot.get_object(item) for item in net.relationships["endpoints"]]
        edges: list[_RouteEdge] = []
        adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
        points_by_key: dict[tuple[int, int], dict[str, float]] = {}
        for wire in route.wires:
            for first, second in zip(wire.points, wire.points[1:], strict=False):
                first_key = _point_key(first)
                second_key = _point_key(second)
                if first_key == second_key:
                    continue
                edge_index = len(edges)
                edges.append(
                    _RouteEdge(first_key, second_key, layer_names[wire.layer], wire.width_mm)
                )
                adjacency[first_key].append(edge_index)
                adjacency[second_key].append(edge_index)
                points_by_key[first_key] = first
                points_by_key[second_key] = second
        if not edges or any(len(items) > 2 for items in adjacency.values()):
            skipped.append({"net": route.name, "reason": "branched_or_empty_route"})
            continue
        endpoint_keys = [key for key in adjacency if _pad_for_key(endpoints, key) is not None]
        if len(endpoint_keys) != 2:
            skipped.append({"net": route.name, "reason": "route_endpoints_do_not_match_pads"})
            continue
        start_key, end_key = endpoint_keys
        start_pad = _pad_for_key(endpoints, start_key)
        end_pad = _pad_for_key(endpoints, end_key)
        assert start_pad is not None and end_pad is not None
        ordered_edges: list[tuple[_RouteEdge, tuple[int, int]]] = []
        used: set[int] = set()
        current = start_key
        while current != end_key:
            available = [index for index in adjacency[current] if index not in used]
            if len(available) != 1:
                break
            edge_index = available[0]
            used.add(edge_index)
            edge = edges[edge_index]
            next_key = edge.end if edge.start == current else edge.start
            ordered_edges.append((edge, next_key))
            current = next_key
        if current != end_key or len(used) != len(edges):
            skipped.append({"net": route.name, "reason": "disconnected_route_graph"})
            continue
        via_keys = {_point_key(item.position) for item in route.vias}
        first_point = points_by_key[start_key]
        trace_points = [TracePathPoint(x=first_point["x"], y=first_point["y"])]
        for index, (edge, next_key) in enumerate(ordered_edges):
            next_layer = (
                ordered_edges[index + 1][0].layer
                if index + 1 < len(ordered_edges)
                else None
            )
            next_point = points_by_key[next_key]
            trace_points.append(
                TracePathPoint(
                    x=next_point["x"],
                    y=next_point["y"],
                    layer=edge.layer,
                    width=edge.width,
                    via_style=(
                        via_style if next_key in via_keys and next_layer != edge.layer else None
                    ),
                )
            )
            previous = points_by_key[
                ordered_edges[index - 1][1] if index > 0 else start_key
            ]
            total_length += distance(Point(**previous), Point(**points_by_key[next_key]))
        operations.append(
            AddTraceOperation(
                net=net.stable_id,
                start_object_id=start_pad.stable_id,
                end_object_id=end_pad.stable_id,
                layer=trace_points[1].layer or "",
                width=trace_points[1].width or 0.0,
                points=trace_points,
            )
        )
        imported.append(route.name)
    return SesOperationPlan(
        operations=operations,
        imported_nets=imported,
        skipped=skipped,
        metrics={
            "session_net_count": len(session.routes),
            "importable_net_count": len(operations),
            "skipped_net_count": len(skipped),
            "wire_count": sum(len(item.wires) for item in session.routes),
            "via_count": sum(len(item.vias) for item in session.routes),
            "imported_length_mm": total_length,
        },
    )
