"""Bounded multi-net routing with rip-up/retry.

The orchestrator routes connections sequentially against an evolving document
(every routed connection becomes an obstacle for the next one) and, when a
connection fails, tries a bounded rip-up/retry: temporarily remove one earlier
routed connection, route the failed one, then re-route the ripped connection.
The result is an ordered list of semantic operations that reproduces the final
state through the normal transactional preview/commit path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from .adapters import build_snapshot
from .errors import DipTraceMcpError, RoutingError
from .geometry import BBox, Point
from .operations import AddTraceOperation, DeleteTraceOperation, SemanticOperation
from .routing import RouteConnectionConfig, synthesize_route
from .semantic_compiler import apply_semantic_operations
from .xml_document import DipTraceDocument

MAX_CONNECTIONS = 64
MAX_RIPUP_ATTEMPTS = 8
RoutingOrder = Literal["input", "congestion_aware"]


@dataclass(slots=True)
class RoutedConnection:
    index: int
    net: str
    operation: AddTraceOperation
    trace_stable_id: str
    metrics: dict[str, Any]


@dataclass(slots=True)
class MultiRouteResult:
    operations: list[SemanticOperation]
    routed: list[RoutedConnection] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    ripups: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoutingPriority:
    index: int
    net: str
    score: float
    obstacle_count: int
    corridor_occupancy: float
    direct_length_mm: float
    max_detour: float
    layer_options: int
    corridor_bbox: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "net": self.net,
            "score": self.score,
            "obstacle_count": self.obstacle_count,
            "corridor_occupancy": self.corridor_occupancy,
            "direct_length_mm": self.direct_length_mm,
            "max_detour": self.max_detour,
            "layer_options": self.layer_options,
            "corridor_bbox": self.corridor_bbox,
        }


def _trace_ids(document: DipTraceDocument) -> set[str]:
    snapshot = build_snapshot(document)
    if snapshot.board is None:
        return set()
    return {record.stable_id for record in snapshot.board.traces}


def _apply(
    document: DipTraceDocument, operations: list[SemanticOperation]
) -> DipTraceDocument:
    return apply_semantic_operations(document, operations).document


def _route_one(
    document: DipTraceDocument, config: RouteConnectionConfig
) -> tuple[DipTraceDocument, AddTraceOperation, str, dict[str, Any]]:
    snapshot = build_snapshot(document)
    before_ids = _trace_ids(document)
    result = synthesize_route(snapshot, config)
    updated = _apply(document, [result.operation])
    new_ids = _trace_ids(updated) - before_ids
    if len(new_ids) != 1:
        raise RoutingError(
            "Could not resolve the newly routed trace identity",
            details={"candidates": sorted(new_ids)},
        )
    return updated, result.operation, next(iter(new_ids)), result.metrics


def _intersection_area(left: BBox, right: BBox) -> float:
    width = min(left.max_x, right.max_x) - max(left.min_x, right.min_x)
    height = min(left.max_y, right.max_y) - max(left.min_y, right.min_y)
    return max(0.0, width) * max(0.0, height)


def _routing_priority(
    document: DipTraceDocument,
    index: int,
    config: RouteConnectionConfig,
) -> RoutingPriority:
    snapshot = build_snapshot(document)
    if snapshot.board is None:
        raise RoutingError("Multi-net routing requires a PCB document")
    net_matches = [
        item
        for item in snapshot.board.nets
        if item.stable_id == config.net
        or item.xml_id == config.net
        or (item.name or "").casefold() == config.net.casefold()
    ]
    if len(net_matches) != 1:
        raise RoutingError(f"Unique net was not found for routing priority: {config.net}")
    net = net_matches[0]
    start = snapshot.get_object(config.start_object_id)
    end = snapshot.get_object(config.end_object_id)
    if start.position is None or end.position is None:
        raise RoutingError(
            "Routing priority requires positioned endpoints",
            object_ids=[start.stable_id, end.stable_id],
        )
    start_point = Point(**start.position)
    end_point = Point(**end.position)
    expansion = max(config.grid, config.width / 2.0 + config.clearance)
    corridor = BBox.from_points([start_point, end_point]).expand(expansion)
    corridor_area = max(
        (corridor.max_x - corridor.min_x) * (corridor.max_y - corridor.min_y),
        config.grid * config.grid,
    )
    endpoint_parents = {start.parent_id, end.parent_id}
    candidates = [
        *snapshot.board.traces,
        *snapshot.board.vias,
        *snapshot.board.pads,
        *snapshot.board.keepouts,
        *snapshot.board.components,
    ]
    obstacles = []
    for item in candidates:
        if item.bbox is None or item.net_id == net.xml_id:
            continue
        if item.kind == "component" and item.stable_id in endpoint_parents:
            continue
        box = BBox(**item.bbox)
        if corridor.intersects(box):
            obstacles.append(box)
    occupied_area = sum(_intersection_area(corridor, item) for item in obstacles)
    occupancy = min(1.0, occupied_area / corridor_area)
    direct_length = (
        (end_point.x - start_point.x) ** 2 + (end_point.y - start_point.y) ** 2
    ) ** 0.5
    layer_options = max(
        1,
        len(
            set(
                [
                    *config.preferred_layers,
                    *(
                        [config.layer]
                        if config.layer is not None
                        else []
                    ),
                    *(
                        [config.start_layer]
                        if config.start_layer is not None
                        else []
                    ),
                    *(
                        [config.end_layer]
                        if config.end_layer is not None
                        else []
                    ),
                ]
            )
        ),
    )
    score = (
        len(obstacles) * 10.0
        + occupancy * 5.0
        + (1.0 / config.max_detour) * 3.0
        + (1.0 / layer_options) * 2.0
        + min(direct_length / 100.0, 2.0)
        + (1.0 if config.max_vias == 0 else 0.0)
    )
    return RoutingPriority(
        index=index,
        net=config.net,
        score=score,
        obstacle_count=len(obstacles),
        corridor_occupancy=occupancy,
        direct_length_mm=direct_length,
        max_detour=config.max_detour,
        layer_options=layer_options,
        corridor_bbox=corridor.as_dict(),
    )


def plan_connection_order(
    document: DipTraceDocument,
    connections: list[RouteConnectionConfig],
    *,
    ordering: RoutingOrder = "congestion_aware",
) -> tuple[list[tuple[int, RouteConnectionConfig]], list[RoutingPriority]]:
    """Return a deterministic most-constrained-first routing order and its evidence."""

    if not connections:
        raise RoutingError("At least one connection is required")
    if len(connections) > MAX_CONNECTIONS:
        raise RoutingError(
            f"A single routing analysis is bounded to {MAX_CONNECTIONS} connections"
        )
    priorities = [
        _routing_priority(document, index, config)
        for index, config in enumerate(connections)
    ]
    if ordering == "input":
        ordered = priorities
    else:
        ordered = sorted(priorities, key=lambda item: (-item.score, item.index))
    return [(item.index, connections[item.index]) for item in ordered], priorities


def synthesize_routes_with_retry(
    document: DipTraceDocument,
    connections: list[RouteConnectionConfig],
    *,
    ripup_retry: bool = True,
    max_ripup_attempts: int = 4,
    time_budget_ms: int = 120_000,
    ordering: RoutingOrder = "congestion_aware",
) -> MultiRouteResult:
    """Route multiple connections sequentially with bounded rip-up/retry."""

    if not connections:
        raise RoutingError("At least one connection is required")
    if len(connections) > MAX_CONNECTIONS:
        raise RoutingError(
            f"A single multi-route call is bounded to {MAX_CONNECTIONS} connections"
        )
    if not 0 <= max_ripup_attempts <= MAX_RIPUP_ATTEMPTS:
        raise RoutingError(f"max_ripup_attempts must be between 0 and {MAX_RIPUP_ATTEMPTS}")
    started = time.monotonic()
    ordered_connections, priorities = plan_connection_order(
        document, connections, ordering=ordering
    )

    def out_of_budget() -> bool:
        return (time.monotonic() - started) * 1_000.0 > time_budget_ms

    working = document
    routed: list[RoutedConnection] = []
    operations: list[SemanticOperation] = []
    failed: list[tuple[int, RouteConnectionConfig, str]] = []
    for index, config in ordered_connections:
        if out_of_budget():
            failed.append((index, config, "time budget exhausted"))
            continue
        try:
            working, operation, trace_id, metrics = _route_one(working, config)
        except DipTraceMcpError as exc:
            failed.append((index, config, str(exc)))
            continue
        routed.append(
            RoutedConnection(
                index=index,
                net=config.net,
                operation=operation,
                trace_stable_id=trace_id,
                metrics=metrics,
            )
        )
        operations.append(operation)

    ripups: list[dict[str, Any]] = []
    still_failed: list[dict[str, Any]] = []
    if ripup_retry and failed and routed:
        for index, config, message in failed:
            recovered = False
            attempts = 0
            for candidate in list(routed):
                if attempts >= max_ripup_attempts or out_of_budget():
                    break
                if candidate.net == config.net:
                    continue
                attempts += 1
                rip = DeleteTraceOperation.model_validate(
                    {
                        "selector": {"ids": [candidate.trace_stable_id]},
                        "allow_connectivity_regression": True,
                    }
                )
                try:
                    ripped_doc = _apply(working, [rip])
                    rerouted_doc, operation, trace_id, metrics = _route_one(
                        ripped_doc, config
                    )
                    restored_doc, restore_operation, restore_trace_id, restore_metrics = (
                        _route_one(rerouted_doc, _config_for(candidate, connections))
                    )
                except DipTraceMcpError:
                    continue
                operations.append(rip)
                operations.append(operation)
                operations.append(restore_operation)
                working = restored_doc
                candidate.operation = restore_operation
                candidate.trace_stable_id = restore_trace_id
                candidate.metrics = restore_metrics
                routed.append(
                    RoutedConnection(
                        index=index,
                        net=config.net,
                        operation=operation,
                        trace_stable_id=trace_id,
                        metrics=metrics,
                    )
                )
                ripups.append(
                    {
                        "connection_index": index,
                        "ripped_connection_index": candidate.index,
                        "ripped_net": candidate.net,
                        "attempt": attempts,
                    }
                )
                recovered = True
                break
            if not recovered:
                still_failed.append(
                    {"index": index, "net": config.net, "error": message, "ripup": "exhausted"}
                )
    else:
        still_failed = [
            {"index": index, "net": config.net, "error": message, "ripup": "disabled"}
            for index, config, message in failed
        ]

    routed.sort(key=lambda item: item.index)
    return MultiRouteResult(
        operations=operations,
        routed=routed,
        failed=still_failed,
        ripups=ripups,
        metrics={
            "algorithm": (
                "congestion_ordered_multinet_a_star_with_bounded_ripup_retry"
                if ordering == "congestion_aware"
                else "sequential_multinet_a_star_with_bounded_ripup_retry"
            ),
            "ordering": ordering,
            "routing_order": [index for index, _config in ordered_connections],
            "priorities": [item.as_dict() for item in priorities],
            "requested": len(connections),
            "routed_count": len(routed),
            "failed_count": len(still_failed),
            "ripup_count": len(ripups),
            "routed": [
                {
                    "index": item.index,
                    "net": item.net,
                    "trace_id": item.trace_stable_id,
                    "length_mm": item.metrics.get("length_mm"),
                    "via_count": item.metrics.get("via_count"),
                }
                for item in routed
            ],
            "elapsed_ms": (time.monotonic() - started) * 1_000.0,
        },
    )


def _config_for(
    routed: RoutedConnection, connections: list[RouteConnectionConfig]
) -> RouteConnectionConfig:
    return connections[routed.index]
