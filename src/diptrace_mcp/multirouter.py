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
from typing import Any

from .adapters import build_snapshot
from .errors import DipTraceMcpError, RoutingError
from .operations import AddTraceOperation, DeleteTraceOperation, SemanticOperation
from .routing import RouteConnectionConfig, synthesize_route
from .semantic_compiler import apply_semantic_operations
from .xml_document import DipTraceDocument

MAX_CONNECTIONS = 64
MAX_RIPUP_ATTEMPTS = 8


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


def synthesize_routes_with_retry(
    document: DipTraceDocument,
    connections: list[RouteConnectionConfig],
    *,
    ripup_retry: bool = True,
    max_ripup_attempts: int = 4,
    time_budget_ms: int = 120_000,
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

    def out_of_budget() -> bool:
        return (time.monotonic() - started) * 1_000.0 > time_budget_ms

    working = document
    routed: list[RoutedConnection] = []
    operations: list[SemanticOperation] = []
    failed: list[tuple[int, RouteConnectionConfig, str]] = []
    for index, config in enumerate(connections):
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
            "algorithm": "sequential_multinet_a_star_with_bounded_ripup_retry",
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
