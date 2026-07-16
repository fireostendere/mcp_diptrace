from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, replace
from typing import Any

from pydantic import Field, model_validator

from .adapters import DocumentSnapshot
from .domain import (
    DifferentialPairModel,
    DifferentialPairPadPair,
    ObjectRecord,
    StrictModel,
)
from .errors import (
    CapabilityUnavailableError,
    ConnectivityRegressionError,
    GeometryError,
    ObjectNotFoundError,
    RoutingError,
)
from .geometry import (
    BBox,
    Point,
    distance,
    point_in_polygon,
    polyline_length,
    segment_intersects_bbox,
)
from .operations import (
    AddDifferentialPairRouteOperation,
    AddTraceOperation,
    DifferentialPairCenterPoint,
    TracePathPoint,
)
from .via_styles import resolve_via_span, select_via_style, validate_via_geometry

_DIRECTIONS = (
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
)


class RouteConnectionConfig(StrictModel):
    net: str = Field(min_length=1, max_length=1_000)
    start_object_id: str = Field(min_length=1)
    end_object_id: str = Field(min_length=1)
    layer: str | None = Field(default=None, min_length=1, max_length=256)
    start_layer: str | None = Field(default=None, min_length=1, max_length=256)
    end_layer: str | None = Field(default=None, min_length=1, max_length=256)
    preferred_layers: list[str] = Field(default_factory=list, max_length=64)
    width: float = Field(gt=0.0, allow_inf_nan=False)
    clearance: float = Field(default=0.2, ge=0.0, le=100.0)
    grid: float = Field(default=0.5, gt=0.0, le=10.0)
    bend_cost: float = Field(default=0.2, ge=0.0, le=1_000.0)
    via_style: str | None = Field(default=None, min_length=1, max_length=256)
    max_vias: int = Field(default=0, ge=0, le=32)
    via_cost: float = Field(default=5.0, ge=0.0, le=10_000.0)
    max_detour: float = Field(default=3.0, ge=1.0, le=100.0)
    max_nodes: int = Field(default=100_000, ge=100, le=1_000_000)
    time_budget_ms: int = Field(default=5_000, ge=100, le=30_000)
    avoid_component_bodies: bool = True

    @model_validator(mode="after")
    def validate_layers_and_vias(self) -> RouteConnectionConfig:
        if self.layer is None and not self.preferred_layers and self.start_layer is None:
            raise ValueError("layer, start_layer or preferred_layers is required")
        if self.max_vias and self.via_style is None:
            raise ValueError("via_style is required when max_vias is greater than zero")
        if self.preferred_layers and len(set(self.preferred_layers)) != len(
            self.preferred_layers
        ):
            raise ValueError("preferred_layers must not contain duplicates")
        return self


@dataclass(frozen=True, slots=True)
class RouteSynthesisResult:
    operation: AddTraceOperation
    points: list[Point]
    metrics: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


class DifferentialPairRouteConfig(StrictModel):
    pair: str = Field(min_length=1, max_length=1_000)
    start_pad_point_id: str | None = Field(default=None, min_length=1, max_length=256)
    end_pad_point_id: str | None = Field(default=None, min_length=1, max_length=256)
    layer: str = Field(min_length=1, max_length=256)
    preferred_layers: list[str] = Field(default_factory=list, max_length=64)
    width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    gap: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    clearance: float = Field(default=0.2, ge=0.0, le=100.0)
    grid: float = Field(default=0.025, gt=0.0, le=10.0)
    bend_cost: float = Field(default=0.2, ge=0.0, le=1_000.0)
    via_style: str | None = Field(default=None, min_length=1, max_length=256)
    max_vias: int = Field(default=0, ge=0, le=32)
    via_cost: float = Field(default=8.0, ge=0.0, le=10_000.0)
    max_detour: float = Field(default=3.0, ge=1.0, le=100.0)
    max_nodes: int = Field(default=200_000, ge=100, le=1_000_000)
    time_budget_ms: int = Field(default=10_000, ge=100, le=30_000)
    endpoint_tolerance: float = Field(default=0.01, gt=0.0, le=1.0)
    avoid_component_bodies: bool = True

    @model_validator(mode="after")
    def validate_vias(self) -> DifferentialPairRouteConfig:
        if self.max_vias and self.via_style is None:
            raise ValueError("via_style is required when max_vias is greater than zero")
        return self


@dataclass(frozen=True, slots=True)
class DifferentialPairRouteResult:
    operation: AddDifferentialPairRouteOperation
    center_points: list[Point]
    positive_points: list[Point]
    negative_points: list[Point]
    metrics: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True, slots=True)
class _Obstacle:
    object_id: str
    bbox: BBox
    kind: str


@dataclass(frozen=True, slots=True)
class _ViaStyle:
    style_id: str
    name: str
    diameter: float
    hole: float
    layer_ids: tuple[str, ...]
    span_source: str


@dataclass(frozen=True, slots=True)
class _RouteNode:
    point: Point
    incoming_layer: str | None
    active_layer: str
    via_style: str | None = None


_State = tuple[int, int, int, int, int]


def synthesize_route(
    snapshot: DocumentSnapshot,
    config: RouteConnectionConfig,
) -> RouteSynthesisResult:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Local routing requires a PCB document")
    net = _find_net(snapshot, config.net)
    start = _endpoint(snapshot, config.start_object_id, net)
    end = _endpoint(snapshot, config.end_object_id, net)
    if start.position is None or end.position is None:
        raise CapabilityUnavailableError(
            "Endpoint coordinates require ratline or pattern geometry",
            object_ids=[start.stable_id, end.stable_id],
        )
    start_point = Point(**start.position)
    end_point = Point(**end.position)
    if not _on_grid(start_point, config.grid) or not _on_grid(end_point, config.grid):
        raise GeometryError(
            "Endpoint anchors must lie on the requested routing grid",
            details={
                "grid_mm": config.grid,
                "start": start_point.as_dict(),
                "end": end_point.as_dict(),
            },
            object_ids=[start.stable_id, end.stable_id],
        )
    layer_ids, start_layer, end_layer = _route_layers(snapshot, config)
    via = _via_style(snapshot, config.via_style) if config.via_style else None
    if start_layer != end_layer and (via is None or config.max_vias == 0):
        raise RoutingError(
            "Different endpoint layers require an enabled via style",
            details={"start_layer": start_layer, "end_layer": end_layer},
        )
    if start_layer != end_layer and via is not None and (
        start_layer not in via.layer_ids or end_layer not in via.layer_ids
    ):
        raise RoutingError(
            "Selected via style cannot connect the endpoint routing layers",
            details={
                "start_layer": start_layer,
                "end_layer": end_layer,
                "via_style": via.style_id,
                "span_layer_ids": list(via.layer_ids),
            },
        )
    endpoint_parents = {start.parent_id, end.parent_id}
    expansion = config.width / 2.0 + config.clearance
    obstacle_layer_ids = list(
        dict.fromkeys([*layer_ids, *(via.layer_ids if via is not None else ())])
    )
    obstacles = {
        layer_id: _obstacles(
            snapshot,
            net,
            layer_id,
            expansion=expansion,
            excluded_components=endpoint_parents,
            avoid_component_bodies=config.avoid_component_bodies,
        )
        for layer_id in obstacle_layer_ids
    }
    started = time.monotonic()
    states, visited = _a_star(
        snapshot,
        start_point,
        end_point,
        layer_ids,
        start_layer,
        end_layer,
        obstacles,
        via,
        config,
        started,
    )
    nodes = _simplify_nodes(_collapse_states(states, layer_ids, config.grid, via))
    points = [node.point for node in nodes]
    route_length = polyline_length(points)
    direct_length = distance(start_point, end_point)
    detour = route_length / direct_length if direct_length else 1.0
    if detour > config.max_detour + 1e-9:
        raise RoutingError(
            "Found route exceeds max_detour",
            details={
                "route_length_mm": route_length,
                "direct_length_mm": direct_length,
                "detour": detour,
                "max_detour": config.max_detour,
            },
        )
    path = [TracePathPoint(x=nodes[0].point.x, y=nodes[0].point.y)]
    path.extend(
        TracePathPoint(
            x=node.point.x,
            y=node.point.y,
            layer=node.incoming_layer,
            via_style=node.via_style,
        )
        for node in nodes[1:]
    )
    operation = AddTraceOperation(
        net=net.stable_id,
        start_object_id=start.stable_id,
        end_object_id=end.stable_id,
        points=path,
        layer=start_layer,
        width=config.width,
        clearance=config.clearance,
    )
    used_layers = list(dict.fromkeys(node.active_layer for node in nodes))
    layer_sequence = _layer_sequence(nodes)
    via_count = sum(node.via_style is not None for node in nodes)
    bends = _bend_count(nodes)
    return RouteSynthesisResult(
        operation=operation,
        points=points,
        metrics={
            "algorithm": "bounded_multilayer_a_star_8_neighbor",
            "routing_mode": "45_degree",
            "visited_nodes": visited,
            "raw_state_count": len(states),
            "point_count": len(points),
            "bend_count": bends,
            "via_count": via_count,
            "via_style": via.name if via is not None and via_count else None,
            "layers": used_layers,
            "layer_sequence": layer_sequence,
            "length_mm": route_length,
            "direct_length_mm": direct_length,
            "detour": detour,
            "elapsed_ms": (time.monotonic() - started) * 1_000.0,
            "obstacle_count": sum(len(items) for items in obstacles.values()),
        },
        assumptions=[
            "Routing uses an 8-neighbor fixed grid and generates only 45-degree segments.",
            "Via clearance is checked on every copper layer in its normalized span.",
        ],
        warnings=(
            ["Via span was omitted on a two-layer board and resolved to both layers."]
            if via is not None and via.span_source == "implicit_two_layer"
            else []
        ),
        limitations=[
            "This router does not implement push-and-shove or rip-up/retry.",
            "Component bodies use embedded pattern bounds when explicit courtyard is absent.",
        ],
    )


def synthesize_differential_pair_route(
    snapshot: DocumentSnapshot,
    config: DifferentialPairRouteConfig,
) -> DifferentialPairRouteResult:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Differential-pair routing requires a PCB document")
    pair = _find_pair(snapshot, config.pair)
    start_pair, end_pair = _pair_endpoints(pair, config)
    positive_start = _pair_pad(
        snapshot, start_pair.positive_component_id, start_pair.positive_pad_id
    )
    negative_start = _pair_pad(
        snapshot, start_pair.negative_component_id, start_pair.negative_pad_id
    )
    positive_end = _pair_pad(
        snapshot, end_pair.positive_component_id, end_pair.positive_pad_id
    )
    negative_end = _pair_pad(
        snapshot, end_pair.negative_component_id, end_pair.negative_pad_id
    )
    endpoints = [positive_start, negative_start, positive_end, negative_end]
    if any(item.position is None for item in endpoints):
        raise CapabilityUnavailableError(
            "Differential-pair pad positions require embedded pattern or route geometry",
            object_ids=[item.stable_id for item in endpoints],
        )
    positive_start_point = Point(**positive_start.position)  # type: ignore[arg-type]
    negative_start_point = Point(**negative_start.position)  # type: ignore[arg-type]
    positive_end_point = Point(**positive_end.position)  # type: ignore[arg-type]
    negative_end_point = Point(**negative_end.position)  # type: ignore[arg-type]
    start_center = _midpoint(positive_start_point, negative_start_point)
    end_center = _midpoint(positive_end_point, negative_end_point)
    width, gap = _pair_geometry(snapshot, pair, config)
    spacing = width + gap
    start_spacing = distance(positive_start_point, negative_start_point)
    end_spacing = distance(positive_end_point, negative_end_point)
    start_matches = math.isclose(
        start_spacing, spacing, abs_tol=config.endpoint_tolerance
    )
    end_matches = math.isclose(end_spacing, spacing, abs_tol=config.endpoint_tolerance)
    if not start_matches or not end_matches:
        raise GeometryError(
            "Pad-pair spacing does not match requested coupled width and gap",
            details={
                "requested_center_spacing_mm": spacing,
                "start_center_spacing_mm": start_spacing,
                "end_center_spacing_mm": end_spacing,
                "tolerance_mm": config.endpoint_tolerance,
            },
            object_ids=[item.stable_id for item in endpoints],
        )
    if not _on_grid(start_center, config.grid) or not _on_grid(end_center, config.grid):
        raise GeometryError(
            "Differential-pair center anchors must lie on the requested routing grid",
            details={
                "grid_mm": config.grid,
                "start": start_center.as_dict(),
                "end": end_center.as_dict(),
            },
        )
    start_vector = Point(
        positive_start_point.x - start_center.x,
        positive_start_point.y - start_center.y,
    )
    end_vector = Point(
        positive_end_point.x - end_center.x,
        positive_end_point.y - end_center.y,
    )
    if abs(_cross(start_vector, end_vector)) > config.endpoint_tolerance * spacing or (
        start_vector.x * end_vector.x + start_vector.y * end_vector.y <= 0.0
    ):
        raise GeometryError(
            "Start and end pad-pair orientation must be parallel and consistently ordered",
            object_ids=[item.stable_id for item in endpoints],
        )
    positive_net = _find_net(snapshot, pair.positive_net_id or pair.positive_net_name or "")
    negative_net = _find_net(snapshot, pair.negative_net_id or pair.negative_net_name or "")
    route_config = RouteConnectionConfig(
        net=positive_net.stable_id,
        start_object_id=positive_start.stable_id,
        end_object_id=positive_end.stable_id,
        layer=config.layer,
        preferred_layers=config.preferred_layers,
        width=2.0 * width + gap,
        clearance=config.clearance,
        grid=config.grid,
        bend_cost=config.bend_cost,
        via_style=config.via_style,
        max_vias=config.max_vias,
        via_cost=config.via_cost,
        max_detour=config.max_detour,
        max_nodes=config.max_nodes,
        time_budget_ms=config.time_budget_ms,
        avoid_component_bodies=config.avoid_component_bodies,
    )
    layer_ids, start_layer, end_layer = _route_layers(snapshot, route_config)
    via = _via_style(snapshot, config.via_style) if config.via_style else None
    ignored_nets = {positive_net.xml_id, negative_net.xml_id}
    endpoint_parents = {item.parent_id for item in endpoints}
    envelope_width = 2.0 * width + gap
    virtual_via = (
        _ViaStyle(
            via.style_id,
            via.name,
            spacing + via.diameter,
            via.hole,
            via.layer_ids,
            via.span_source,
        )
        if via is not None
        else None
    )
    obstacle_layer_ids = list(
        dict.fromkeys([*layer_ids, *(via.layer_ids if via is not None else ())])
    )
    obstacles = {
        layer_id: _obstacles(
            snapshot,
            positive_net,
            layer_id,
            expansion=envelope_width / 2.0 + config.clearance,
            excluded_components=endpoint_parents,
            avoid_component_bodies=config.avoid_component_bodies,
            ignored_net_xml_ids=ignored_nets,
        )
        for layer_id in obstacle_layer_ids
    }
    directions = _perpendicular_directions(start_vector)
    started = time.monotonic()
    states, visited = _a_star(
        snapshot,
        start_center,
        end_center,
        layer_ids,
        start_layer,
        end_layer,
        obstacles,
        virtual_via,
        route_config,
        started,
        start_directions=directions,
        end_directions=directions,
    )
    center_nodes = _simplify_nodes(
        _collapse_states(states, layer_ids, config.grid, virtual_via)
    )
    center_points = [node.point for node in center_nodes]
    positive_side = _offset_side(center_points[0], center_points[1], start_vector)
    positive_points = _offset_polyline(center_points, spacing / 2.0, positive_side)
    negative_points = _offset_polyline(center_points, spacing / 2.0, -positive_side)
    for measured, expected, label in (
        (positive_points[0], positive_start_point, "positive start"),
        (negative_points[0], negative_start_point, "negative start"),
        (positive_points[-1], positive_end_point, "positive end"),
        (negative_points[-1], negative_end_point, "negative end"),
    ):
        if distance(measured, expected) > config.endpoint_tolerance:
            raise RoutingError(
                "Coupled offset path does not meet the pad anchor",
                details={
                    "endpoint": label,
                    "generated": measured.as_dict(),
                    "expected": expected.as_dict(),
                    "tolerance_mm": config.endpoint_tolerance,
                },
            )
    positive_path = _paired_trace_points(positive_points, center_nodes, via)
    negative_path = _paired_trace_points(negative_points, center_nodes, via)
    center_path = [
        DifferentialPairCenterPoint(
            x=center.x,
            y=center.y,
            layer=node.incoming_layer or node.active_layer,
            via_style=via.style_id if node.via_style is not None and via is not None else None,
            positive_dx=positive.x - center.x,
            positive_dy=positive.y - center.y,
            negative_dx=negative.x - center.x,
            negative_dy=negative.y - center.y,
        )
        for center, positive, negative, node in zip(
            center_points, positive_points, negative_points, center_nodes, strict=True
        )
    ]
    positive_length = polyline_length(positive_points)
    negative_length = polyline_length(negative_points)
    via_count = sum(node.via_style is not None for node in center_nodes)
    operation = AddDifferentialPairRouteOperation(
        pair=pair.stable_id,
        positive_net=positive_net.stable_id,
        negative_net=negative_net.stable_id,
        positive_start_object_id=positive_start.stable_id,
        positive_end_object_id=positive_end.stable_id,
        negative_start_object_id=negative_start.stable_id,
        negative_end_object_id=negative_end.stable_id,
        positive_points=positive_path,
        negative_points=negative_path,
        center_points=center_path,
        start_pad_point_id=start_pair.xml_id or "",
        end_pad_point_id=end_pair.xml_id or "",
        layer=start_layer,
        width=width,
        clearance=config.clearance,
    )
    return DifferentialPairRouteResult(
        operation=operation,
        center_points=center_points,
        positive_points=positive_points,
        negative_points=negative_points,
        metrics={
            "algorithm": "coupled_centerline_multilayer_a_star",
            "routing_mode": "45_degree_parallel_offset",
            "visited_nodes": visited,
            "center_length_mm": polyline_length(center_points),
            "positive_length_mm": positive_length,
            "negative_length_mm": negative_length,
            "signed_skew_mm": positive_length - negative_length,
            "absolute_skew_mm": abs(positive_length - negative_length),
            "width_mm": width,
            "gap_mm": gap,
            "center_spacing_mm": spacing,
            "via_count_per_net": via_count,
            "symmetric_via_count": via_count * 2,
            "layer_sequence": _layer_sequence(center_nodes),
            "elapsed_ms": (time.monotonic() - started) * 1_000.0,
        },
        assumptions=[
            "Both traces are generated from one centerline with a constant edge gap.",
            "Every layer transition inserts the same via style at symmetric pair offsets.",
            "Via clearance is checked on every copper layer in its normalized span.",
        ],
        warnings=(
            ["Via span was omitted on a two-layer board and resolved to both layers."]
            if via is not None and via.span_source == "implicit_two_layer"
            else []
        ),
        limitations=[
            "Endpoint escapes must already match the requested coupled spacing and orientation.",
            "The planner rejects offset miters above 4x pair half-spacing.",
            "Push-and-shove, dynamic neck-down and phase tuning are not implemented.",
        ],
    )
def _find_pair(snapshot: DocumentSnapshot, value: str) -> DifferentialPairModel:
    assert snapshot.board is not None
    matches = [
        item
        for item in snapshot.board.differential_pairs
        if item.stable_id == value
        or item.xml_id == value
        or item.name.casefold() == value.casefold()
    ]
    if len(matches) != 1:
        raise ObjectNotFoundError(f"Unique differential pair was not found: {value}")
    return matches[0]


def _pair_endpoints(
    pair: DifferentialPairModel,
    config: DifferentialPairRouteConfig,
) -> tuple[DifferentialPairPadPair, DifferentialPairPadPair]:
    if len(pair.pad_pairs) < 2:
        raise CapabilityUnavailableError(
            "Differential-pair routing requires at least two exported PadPoints",
            object_ids=[pair.stable_id],
        )

    def select(value: str | None, fallback: DifferentialPairPadPair) -> DifferentialPairPadPair:
        if value is None:
            return fallback
        matches = [item for item in pair.pad_pairs if item.xml_id == value]
        if len(matches) != 1:
            raise ObjectNotFoundError(f"Differential-pair PadPoint was not found: {value}")
        return matches[0]

    start = select(config.start_pad_point_id, pair.pad_pairs[0])
    end = select(config.end_pad_point_id, pair.pad_pairs[-1])
    if start.xml_id == end.xml_id:
        raise GeometryError("Differential-pair start and end PadPoints must be different")
    for segment in pair.segments:
        endpoints = {segment.attributes.get("StartPoint"), segment.attributes.get("EndPoint")}
        if endpoints == {start.xml_id, end.xml_id}:
            raise ConnectivityRegressionError(
                "The selected differential-pair PadPoints are already routed",
                object_ids=[pair.stable_id],
            )
    return start, end


def _pair_pad(
    snapshot: DocumentSnapshot,
    component_id: str | None,
    pad_id: str | None,
) -> ObjectRecord:
    if component_id is None or pad_id is None:
        raise ObjectNotFoundError(
            "Differential-pair PadPoint does not resolve to normalized component/pad ids"
        )
    component = snapshot.get_object(component_id)
    pad = snapshot.get_object(pad_id)
    if component.kind not in {"component", "testpoint"} or (
        pad.kind != "pad" or pad.parent_id != component.stable_id
    ):
        raise ObjectNotFoundError(
            f"Differential-pair pad relationship is invalid: {component_id}:{pad_id}"
        )
    return pad


def _pair_geometry(
    snapshot: DocumentSnapshot,
    pair: DifferentialPairModel,
    config: DifferentialPairRouteConfig,
) -> tuple[float, float]:
    assert snapshot.board is not None
    layer_id = _layer_id(snapshot, config.layer)
    layer_name = next(
        str(item.get("name", ""))
        for item in snapshot.board.layers
        if str(item.get("id", "")) == layer_id
    )
    layer_rules = next(
        (
            item
            for item in pair.rules.layer_rules
            if item.layer_name.casefold() == layer_name.casefold()
        ),
        None,
    )
    width = config.width or (layer_rules.width_mm if layer_rules is not None else None)
    gap = config.gap if config.gap is not None else (
        layer_rules.gap_mm if layer_rules is not None else None
    )
    if width is None or gap is None:
        raise CapabilityUnavailableError(
            "Differential-pair width and gap are missing from both request and exported rules",
            object_ids=[pair.stable_id],
        )
    return width, gap


def _midpoint(left: Point, right: Point) -> Point:
    return Point((left.x + right.x) / 2.0, (left.y + right.y) / 2.0)


def _cross(left: Point, right: Point) -> float:
    return left.x * right.y - left.y * right.x


def _perpendicular_directions(pair_vector: Point) -> set[int]:
    magnitude = math.hypot(pair_vector.x, pair_vector.y)
    if magnitude <= 1e-12:
        raise GeometryError("Differential-pair pads must have distinct anchors")
    result = {
        index
        for index, (dx, dy) in enumerate(_DIRECTIONS)
        if abs(dx * pair_vector.x + dy * pair_vector.y) <= magnitude * 1e-9
    }
    if not result:
        raise GeometryError(
            "Pad-pair orientation is incompatible with deterministic 45-degree routing"
        )
    return result


def _offset_side(start: Point, end: Point, positive_vector: Point) -> int:
    dx = end.x - start.x
    dy = end.y - start.y
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        raise RoutingError("Coupled centerline starts with a zero-length segment")
    left_x = -dy / length
    left_y = dx / length
    return 1 if left_x * positive_vector.x + left_y * positive_vector.y >= 0.0 else -1


def _offset_polyline(points: list[Point], offset: float, side: int) -> list[Point]:
    if len(points) < 2:
        raise RoutingError("Coupled centerline requires at least two points")
    directions: list[Point] = []
    normals: list[Point] = []
    for start, end in zip(points, points[1:], strict=False):
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            raise RoutingError("Coupled centerline contains a zero-length segment")
        direction = Point(dx / length, dy / length)
        directions.append(direction)
        normals.append(Point(-direction.y * offset * side, direction.x * offset * side))
    result = [points[0].translate(normals[0].x, normals[0].y)]
    for index in range(1, len(points) - 1):
        vertex = points[index]
        first_direction = directions[index - 1]
        second_direction = directions[index]
        first = vertex.translate(normals[index - 1].x, normals[index - 1].y)
        second = vertex.translate(normals[index].x, normals[index].y)
        determinant = _cross(first_direction, second_direction)
        if abs(determinant) <= 1e-12:
            if first_direction.x * second_direction.x + first_direction.y * second_direction.y < 0:
                raise RoutingError("Coupled centerline contains a 180-degree reversal")
            intersection = _midpoint(first, second)
        else:
            delta = Point(second.x - first.x, second.y - first.y)
            scale = _cross(delta, second_direction) / determinant
            intersection = Point(
                first.x + first_direction.x * scale,
                first.y + first_direction.y * scale,
            )
        if distance(vertex, intersection) > max(offset * 4.0, offset + 1e-9):
            raise RoutingError(
                "Coupled offset miter exceeds the configured geometric safety bound",
                details={"point_index": index, "offset_mm": offset},
            )
        result.append(intersection)
    result.append(points[-1].translate(normals[-1].x, normals[-1].y))
    return result


def _paired_trace_points(
    points: list[Point],
    center_nodes: list[_RouteNode],
    via: _ViaStyle | None,
) -> list[TracePathPoint]:
    result = [TracePathPoint(x=points[0].x, y=points[0].y)]
    result.extend(
        TracePathPoint(
            x=point.x,
            y=point.y,
            layer=node.incoming_layer,
            via_style=(
                via.style_id if node.via_style is not None and via is not None else None
            ),
        )
        for point, node in zip(points[1:], center_nodes[1:], strict=True)
    )
    return result


def _layer_sequence(nodes: list[_RouteNode]) -> list[str]:
    result = [nodes[0].active_layer]
    for node in nodes[1:]:
        if node.active_layer != result[-1]:
            result.append(node.active_layer)
    return result


def _find_net(snapshot: DocumentSnapshot, value: str) -> ObjectRecord:
    matches = [
        item
        for item in snapshot.objects.values()
        if item.kind == "net"
        and (
            item.stable_id == value
            or item.xml_id == value
            or (item.name or "").casefold() == value.casefold()
        )
    ]
    if not matches:
        raise ObjectNotFoundError(f"Net was not found: {value}")
    if len(matches) > 1:
        raise RoutingError(f"Net selector is ambiguous: {value}")
    return matches[0]


def _endpoint(
    snapshot: DocumentSnapshot, object_id: str, net: ObjectRecord
) -> ObjectRecord:
    endpoint = snapshot.get_object(object_id)
    if endpoint.kind != "pad":
        raise CapabilityUnavailableError(
            "Local routing currently supports pad endpoints", object_ids=[object_id]
        )
    if endpoint.net_id != net.xml_id:
        raise ConnectivityRegressionError(
            f"Endpoint does not belong to net {net.name}",
            object_ids=[endpoint.stable_id, net.stable_id],
        )
    return endpoint


def _layer_id(snapshot: DocumentSnapshot, value: str) -> str:
    assert snapshot.board is not None
    matches = [
        item
        for item in snapshot.board.layers
        if str(item.get("id", "")) == value
        or str(item.get("name", "")).casefold() == value.casefold()
    ]
    if len(matches) != 1:
        raise ObjectNotFoundError(f"Unique copper layer was not found: {value}")
    return str(matches[0]["id"])


def _route_layers(
    snapshot: DocumentSnapshot,
    config: RouteConnectionConfig,
) -> tuple[list[str], str, str]:
    requested = list(config.preferred_layers)
    if not requested and config.layer is not None:
        requested.append(config.layer)
    for endpoint_layer in (config.start_layer, config.end_layer):
        if endpoint_layer is not None and endpoint_layer not in requested:
            requested.append(endpoint_layer)
    layer_ids = list(dict.fromkeys(_layer_id(snapshot, item) for item in requested))
    start = _layer_id(snapshot, config.start_layer or config.layer or requested[0])
    end = _layer_id(snapshot, config.end_layer or config.layer or requested[-1])
    for layer_id in (start, end):
        if layer_id not in layer_ids:
            layer_ids.append(layer_id)
    return layer_ids, start, end


def _via_style(snapshot: DocumentSnapshot, value: str) -> _ViaStyle:
    assert snapshot.board is not None
    style = select_via_style(snapshot.board, value)
    diameter, hole = validate_via_geometry(style)
    span = resolve_via_span(snapshot.board, style)
    span_source = (
        "implicit_two_layer" if style.span_source == "unspecified" else style.span_source
    )
    return _ViaStyle(style.id, style.name or value, diameter, hole, span, span_source)


def _obstacles(
    snapshot: DocumentSnapshot,
    net: ObjectRecord,
    layer_id: str,
    *,
    expansion: float,
    excluded_components: set[str | None],
    avoid_component_bodies: bool,
    ignored_net_xml_ids: set[str | None] | None = None,
) -> list[_Obstacle]:
    assert snapshot.board is not None
    obstacles: list[_Obstacle] = []
    for trace in snapshot.board.traces:
        if trace.net_id in (ignored_net_xml_ids or {net.xml_id}):
            continue
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        layers = trace.attributes.get("segment_layers", [])
        widths = trace.attributes.get("segment_widths_mm", [])
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            segment_layer = str(layers[index]) if index < len(layers) else trace.layer or ""
            if segment_layer != layer_id:
                continue
            other_radius = float(widths[index]) / 2.0 if index < len(widths) else 0.0
            obstacles.append(
                _Obstacle(
                    f"{trace.stable_id}:{index}",
                    BBox.from_points([start, end]).expand(expansion + other_radius),
                    "trace_segment",
                )
            )
    for item in [*snapshot.board.keepouts, *snapshot.board.pads, *snapshot.board.vias]:
        if item.bbox is None or item.net_id in (ignored_net_xml_ids or {net.xml_id}):
            continue
        if item.kind == "pad" and not _pad_on_layer(snapshot, item, layer_id):
            continue
        obstacles.append(
            _Obstacle(item.stable_id, BBox(**item.bbox).expand(expansion), item.kind)
        )
    if avoid_component_bodies:
        for item in snapshot.board.components:
            if item.stable_id in excluded_components:
                continue
            if item.bbox is not None:
                obstacles.append(
                    _Obstacle(
                        item.stable_id,
                        BBox(**item.bbox).expand(expansion),
                        "component",
                    )
                )
    return obstacles


def _pad_on_layer(snapshot: DocumentSnapshot, pad: ObjectRecord, layer_id: str) -> bool:
    style = pad.attributes.get("pad_style") or {}
    if str(style.get("pad_type", "")).casefold() != "surface":
        return True
    assert snapshot.board is not None
    layer = next(
        (item for item in snapshot.board.layers if str(item.get("id", "")) == layer_id),
        None,
    )
    if layer is None:
        return False
    return str(layer.get("name", "")).casefold().startswith((pad.side or "Top").casefold())


def _on_grid(point: Point, grid: float) -> bool:
    return math.isclose(point.x / grid, round(point.x / grid), abs_tol=1e-7) and math.isclose(
        point.y / grid, round(point.y / grid), abs_tol=1e-7
    )


def _grid_key(point: Point, grid: float) -> tuple[int, int]:
    return round(point.x / grid), round(point.y / grid)


def _point_from_key(key: tuple[int, int], grid: float) -> Point:
    return Point(key[0] * grid, key[1] * grid)


def _octile(left: tuple[int, int], right: tuple[int, int], grid: float) -> float:
    dx = abs(left[0] - right[0])
    dy = abs(left[1] - right[1])
    return (max(dx, dy) + (math.sqrt(2.0) - 1.0) * min(dx, dy)) * grid


def _a_star(
    snapshot: DocumentSnapshot,
    start: Point,
    end: Point,
    layer_ids: list[str],
    start_layer: str,
    end_layer: str,
    obstacles: dict[str, list[_Obstacle]],
    via: _ViaStyle | None,
    config: RouteConnectionConfig,
    started: float,
    *,
    start_directions: set[int] | None = None,
    end_directions: set[int] | None = None,
) -> tuple[list[_State], int]:
    assert snapshot.board is not None and snapshot.board.outline is not None
    polygon = [Point(**item) for item in snapshot.board.outline.get("points", [])]
    bounds = BBox(**snapshot.board.outline["bbox"])
    start_key = _grid_key(start, config.grid)
    end_key = _grid_key(end, config.grid)
    start_index = layer_ids.index(start_layer)
    end_index = layer_ids.index(end_layer)
    start_state: _State = (start_key[0], start_key[1], start_index, -1, 0)
    queue: list[tuple[float, float, _State]] = [
        (_octile(start_key, end_key, config.grid), 0.0, start_state)
    ]
    costs = {start_state: 0.0}
    parents: dict[_State, _State] = {}
    visited = 0
    deadline = started + config.time_budget_ms / 1_000.0
    goal: _State | None = None
    while queue:
        if time.monotonic() >= deadline:
            raise RoutingError(
                "Local routing time budget exhausted",
                details={"visited_nodes": visited, "time_budget_ms": config.time_budget_ms},
            )
        _priority, cost, state = heapq.heappop(queue)
        x, y, layer_index, previous_direction, via_count = state
        if cost > costs.get(state, math.inf) + 1e-12:
            continue
        visited += 1
        if visited > config.max_nodes:
            raise RoutingError(
                "Local routing node budget exhausted",
                details={"visited_nodes": visited, "max_nodes": config.max_nodes},
            )
        if (x, y, layer_index) == (end_key[0], end_key[1], end_index) and (
            end_directions is None or previous_direction in end_directions
        ):
            goal = state
            break
        current = _point_from_key((x, y), config.grid)
        layer_id = layer_ids[layer_index]
        for direction_index, (dx, dy) in enumerate(_DIRECTIONS):
            if (x, y) == start_key and start_directions is not None and (
                direction_index not in start_directions
            ):
                continue
            next_key = (x + dx, y + dy)
            point = _point_from_key(next_key, config.grid)
            if not bounds.contains_point(point) or not point_in_polygon(point, polygon):
                continue
            if _segment_blocked(current, point, obstacles[layer_id]):
                continue
            step = config.grid * (math.sqrt(2.0) if dx and dy else 1.0)
            bend = (
                config.bend_cost
                if previous_direction >= 0 and previous_direction != direction_index
                else 0.0
            )
            next_state: _State = (
                next_key[0],
                next_key[1],
                layer_index,
                direction_index,
                via_count,
            )
            _queue_state(
                queue,
                costs,
                parents,
                state,
                next_state,
                cost + step + bend,
                _octile(next_key, end_key, config.grid)
                + (config.via_cost if layer_index != end_index else 0.0),
            )
        can_via = (
            via is not None
            and via_count < config.max_vias
            and previous_direction >= 0
            and (x, y) not in {start_key, end_key}
        )
        if via is not None and can_via and layer_id in via.layer_ids and not _via_blocked(
            current, via, config.width, obstacles
        ):
            for target_index in range(len(layer_ids)):
                if target_index == layer_index:
                    continue
                if layer_ids[target_index] not in via.layer_ids:
                    continue
                next_state = (x, y, target_index, previous_direction, via_count + 1)
                _queue_state(
                    queue,
                    costs,
                    parents,
                    state,
                    next_state,
                    cost + config.via_cost,
                    _octile((x, y), end_key, config.grid)
                    + (config.via_cost if target_index != end_index else 0.0),
                )
    if goal is None:
        raise RoutingError(
            "No legal multi-layer 45-degree route was found within configured bounds",
            details={
                "visited_nodes": visited,
                "obstacle_count": sum(len(items) for items in obstacles.values()),
                "layers": layer_ids,
                "max_vias": config.max_vias,
            },
        )
    states = [goal]
    while states[-1] != start_state:
        states.append(parents[states[-1]])
    states.reverse()
    return states, visited


def _queue_state(
    queue: list[tuple[float, float, _State]],
    costs: dict[_State, float],
    parents: dict[_State, _State],
    parent: _State,
    state: _State,
    cost: float,
    heuristic: float,
) -> None:
    if cost + 1e-12 >= costs.get(state, math.inf):
        return
    costs[state] = cost
    parents[state] = parent
    heapq.heappush(queue, (cost + heuristic, cost, state))


def _segment_blocked(start: Point, end: Point, obstacles: list[_Obstacle]) -> bool:
    return any(segment_intersects_bbox(start, end, item.bbox) for item in obstacles)


def _via_blocked(
    point: Point,
    via: _ViaStyle,
    route_width: float,
    obstacles: dict[str, list[_Obstacle]],
) -> bool:
    extra = max(0.0, (via.diameter - route_width) / 2.0)
    via_box = BBox(point.x, point.y, point.x, point.y).expand(extra)
    return any(
        via_box.intersects(obstacle.bbox)
        for layer_id in via.layer_ids
        for obstacle in obstacles[layer_id]
    )


def _collapse_states(
    states: list[_State],
    layer_ids: list[str],
    grid: float,
    via: _ViaStyle | None,
) -> list[_RouteNode]:
    first = states[0]
    nodes = [
        _RouteNode(
            point=_point_from_key((first[0], first[1]), grid),
            incoming_layer=None,
            active_layer=layer_ids[first[2]],
        )
    ]
    for previous, current in zip(states, states[1:], strict=False):
        point = _point_from_key((current[0], current[1]), grid)
        if (previous[0], previous[1]) == (current[0], current[1]):
            if via is None or len(nodes) == 1:
                raise RoutingError("Internal router produced an invalid via transition")
            nodes[-1] = replace(
                nodes[-1],
                active_layer=layer_ids[current[2]],
                via_style=via.style_id,
            )
            continue
        nodes.append(
            _RouteNode(
                point=point,
                incoming_layer=layer_ids[current[2]],
                active_layer=layer_ids[current[2]],
            )
        )
    return nodes


def _simplify_nodes(nodes: list[_RouteNode]) -> list[_RouteNode]:
    if len(nodes) <= 2:
        return nodes
    result = [nodes[0]]
    for index in range(1, len(nodes) - 1):
        previous = result[-1]
        current = nodes[index]
        following = nodes[index + 1]
        if current.via_style is not None:
            result.append(current)
            continue
        if current.incoming_layer != following.incoming_layer:
            result.append(current)
            continue
        if _direction(previous.point, current.point) != _direction(
            current.point, following.point
        ):
            result.append(current)
    result.append(nodes[-1])
    return result


def _direction(start: Point, end: Point) -> tuple[int, int]:
    return (
        0 if end.x == start.x else 1 if end.x > start.x else -1,
        0 if end.y == start.y else 1 if end.y > start.y else -1,
    )


def _bend_count(nodes: list[_RouteNode]) -> int:
    return sum(
        _direction(nodes[index - 1].point, nodes[index].point)
        != _direction(nodes[index].point, nodes[index + 1].point)
        for index in range(1, len(nodes) - 1)
    )
