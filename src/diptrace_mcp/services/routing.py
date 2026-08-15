"""Routing analysis and bounded routing-plan orchestration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from ..adapters import DocumentSnapshot, build_snapshot
from ..clearance import resolve_clearance
from ..errors import DocumentError, RoutingError
from ..geometry import Point, distance
from ..multirouter import (
    RoutingOrder,
    plan_connection_order,
    synthesize_routes_with_retry,
)
from ..operations import SemanticOperation
from ..plans import PlanStore
from ..routing import (
    DifferentialPairRouteConfig,
    RouteConnectionConfig,
    _find_net,
    _route_layers,
    synthesize_differential_pair_route,
    synthesize_route_min_vias,
)
from ..semantic_compiler import apply_semantic_operations
from ..xml_document import DipTraceDocument
from .context import DocumentGateway, ServiceContext, read_success

SemanticWrite = Callable[
    [SemanticOperation, str | None, bool, str | None, str | None],
    dict[str, Any],
]
SemanticOperations = Callable[
    [Sequence[SemanticOperation], str | None, bool, str | None, str | None],
    dict[str, Any],
]
PreviewSemanticOperations = Callable[[DipTraceDocument, list[SemanticOperation]], dict[str, Any]]


class ApplyStoredPlan(Protocol):
    def __call__(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]: ...


class RoutingService:
    """Implementation for routing analysis and bounded routing plans."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        plan_store: PlanStore,
        semantic_write: SemanticWrite,
        semantic_operations: SemanticOperations,
        preview_semantic_operations: PreviewSemanticOperations,
        apply_stored_plan: ApplyStoredPlan,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.plan_store = plan_store
        self.semantic_write = semantic_write
        self.semantic_operations = semantic_operations
        self.preview_semantic_operations = preview_semantic_operations
        self.apply_stored_plan = apply_stored_plan

    @staticmethod
    def _unrouted_pairs(
        snapshot: DocumentSnapshot,
        nets: list[str],
    ) -> list[dict[str, str]]:
        if snapshot.board is None:
            raise DocumentError("Routing requires a PCB document")
        requested = {item.casefold() for item in nets}
        pairs: list[dict[str, str]] = []
        for ratline in snapshot.board.ratlines:
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2 or any(item.get("pad_id") is None for item in endpoints):
                continue
            first = snapshot.get_object(str(endpoints[0]["pad_id"]))
            second = snapshot.get_object(str(endpoints[1]["pad_id"]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next((item for item in snapshot.board.nets if item.xml_id == first.net_id), None)
            if net is None or not (
                (net.name or "").casefold() in requested
                or net.stable_id.casefold() in requested
                or (net.xml_id or "").casefold() in requested
            ):
                continue
            pairs.append(
                {
                    "net_id": net.stable_id,
                    "start_object_id": first.stable_id,
                    "end_object_id": second.stable_id,
                }
            )
        return pairs

    def list_unrouted_connections(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Unrouted connections require a PCB document")
        requested = {item.casefold() for item in nets or []}
        items: list[dict[str, Any]] = []
        for index, ratline in enumerate(snapshot.board.ratlines):
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2:
                continue
            pad_ids = [endpoint.get("pad_id") for endpoint in endpoints]
            if any(pad_id is None for pad_id in pad_ids):
                continue
            first = snapshot.get_object(str(pad_ids[0]))
            second = snapshot.get_object(str(pad_ids[1]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next(
                (item for item in snapshot.board.nets if item.xml_id == first.net_id),
                None,
            )
            if net is None or (
                requested
                and (net.name or "").casefold() not in requested
                and net.stable_id.casefold() not in requested
            ):
                continue
            positions = [endpoint.get("position") for endpoint in endpoints]
            ratline_length = (
                distance(Point(**positions[0]), Point(**positions[1]))
                if positions[0] is not None and positions[1] is not None
                else None
            )
            items.append(
                {
                    "connection_id": f"ratline:{index}",
                    "net_id": net.stable_id,
                    "net": net.name,
                    "net_class": net.attributes.get("net_class"),
                    "endpoints": endpoints,
                    "ratline_length_mm": ratline_length,
                    "priority": 0,
                    "differential_pair": None,
                }
            )
        return read_success(
            snapshot.info,
            {"matched_count": len(items), "items": items},
            limitations=[
                "Unrouted connections are derived from exported Ratlines.",
                "Priority and differential-pair enrichment are not implemented yet.",
            ],
        )

    def get_route_details(
        self,
        *,
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        if (trace_id is None) == (net is None):
            raise DocumentError("Specify exactly one of trace_id or net", code="scope_required")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Route details require a PCB document")
        if trace_id is not None:
            traces = [snapshot.get_object(trace_id)]
            if traces[0].kind != "trace":
                raise DocumentError(f"Object is not a trace: {trace_id}")
        else:
            assert net is not None
            net_matches = [
                item
                for item in snapshot.board.nets
                if item.stable_id == net
                or item.xml_id == net
                or (item.name or "").casefold() == net.casefold()
            ]
            if len(net_matches) != 1:
                raise DocumentError(f"Unique net was not found: {net}")
            traces = [
                item for item in snapshot.board.traces if item.parent_id == net_matches[0].stable_id
            ]
        per_layer: dict[str, float] = {}
        total_length = 0.0
        via_ids: list[str] = []
        items: list[dict[str, Any]] = []
        for trace in traces:
            points = [Point(**item) for item in trace.attributes.get("points", [])]
            layers = trace.attributes.get("segment_layers", [])
            segment_lengths: list[float] = []
            for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
                length = distance(start, end)
                segment_lengths.append(length)
                layer = (
                    str(layers[segment_index]) if segment_index < len(layers) else trace.layer or ""
                )
                per_layer[layer] = per_layer.get(layer, 0.0) + length
                total_length += length
            via_ids.extend(trace.relationships.get("vias", []))
            items.append(
                {
                    **trace.model_dump(mode="json"),
                    "segment_lengths_mm": segment_lengths,
                    "bend_count": max(0, len(points) - 2),
                }
            )
        return read_success(
            snapshot.info,
            {
                "trace_count": len(traces),
                "traces": items,
                "total_length_mm": total_length,
                "per_layer_length_mm": per_layer,
                "via_count": len(set(via_ids)),
                "via_ids": sorted(set(via_ids)),
                "layer_transition_count": len(set(via_ids)),
            },
            limitations=[
                "Length is geometric centerline length; arc and electrical delay are not included."
            ],
        )

    def route_connection(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        bend_cost: float = 0.2,
        preferred_layers: list[str] | None = None,
        start_layer: str | None = None,
        end_layer: str | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        max_detour: float = 3.0,
        max_nodes: int = 100_000,
        time_budget_ms: int = 5_000,
        avoid_component_bodies: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = RouteConnectionConfig(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers or [],
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
        )
        route = synthesize_route_min_vias(snapshot, config)
        response = self.semantic_write(route.operation, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "points": [point.as_dict() for point in route.points],
            "path": [point.model_dump(mode="json") for point in route.operation.points],
            "metrics": route.metrics,
            "clearance_resolution": route.clearance_resolution,
            "assumptions": route.assumptions,
        }
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def route_net(
        self,
        net: str,
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, [net])
        if not pairs:
            raise DocumentError(f"No exported unrouted connection was found for net: {net}")
        operations: list[SemanticOperation] = []
        metrics: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route_min_vias(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            metrics.append(route.metrics)
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        response = self.semantic_operations(operations, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "connection_count": len(operations),
            "routes": metrics,
            "clearance_resolutions": [
                {
                    key: item[key]
                    for key in (
                        "requested_clearance_mm",
                        "required_clearance_mm",
                        "effective_clearance_mm",
                        "clearance_sources",
                        "netclass_rules_applied",
                        "netclass_rules_ignored",
                        "clearance_rule_status",
                    )
                    if key in item
                }
                for item in metrics
            ],
        }
        response["clearance_rule_status"] = {
            "per_route": [item.get("clearance_rule_status") for item in metrics],
            "netclass_rules_applied": all(
                bool(item.get("netclass_rules_applied", False)) for item in metrics
            ),
            "netclass_rules_ignored": any(
                bool(item.get("netclass_rules_ignored", False)) for item in metrics
            ),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        return response

    def route_diff_pair(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        route = synthesize_differential_pair_route(
            snapshot,
            DifferentialPairRouteConfig(
                pair=pair,
                start_pad_point_id=start_pad_point_id,
                end_pad_point_id=end_pad_point_id,
                layer=layer,
                preferred_layers=preferred_layers or [],
                width=width,
                gap=gap,
                clearance=clearance,
                grid=grid,
                via_style=via_style,
                max_vias=max_vias,
                via_cost=via_cost,
                max_detour=max_detour,
            ),
        )
        response = self.semantic_write(route.operation, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "center_points": [point.as_dict() for point in route.center_points],
            "positive_points": [point.as_dict() for point in route.positive_points],
            "negative_points": [point.as_dict() for point in route.negative_points],
            "metrics": route.metrics,
            "clearance_resolution": route.clearance_resolution,
            "assumptions": route.assumptions,
        }
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def plan_diff_pair_route(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = DifferentialPairRouteConfig(
            pair=pair,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            layer=layer,
            preferred_layers=preferred_layers or [],
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
        )
        route = synthesize_differential_pair_route(snapshot, config)
        resolved_config = config.model_copy(update={"clearance": route.operation.clearance})
        preview = self.preview_semantic_operations(document, [route.operation])
        record = self.plan_store.create(
            plan_type="diff_pair_route",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=resolved_config.model_dump(mode="json"),
            operations=[route.operation.model_dump(mode="json")],
            changed_ids=[
                route.operation.pair,
                route.operation.positive_net,
                route.operation.negative_net,
            ],
            unresolved=[],
            candidates=[{"metrics": route.metrics}],
            score={"absolute_skew_mm": float(route.metrics["absolute_skew_mm"])},
            metrics=route.metrics,
            assumptions=route.assumptions,
            warnings=route.warnings,
            limitations=route.limitations,
        )
        resources = self.plan_store.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "center_points": [point.as_dict() for point in route.center_points],
                "positive_points": [point.as_dict() for point in route.positive_points],
                "negative_points": [point.as_dict() for point in route.negative_points],
                "metrics": route.metrics,
            },
            diff=preview["diff"],
        )
        record = self.plan_store.read(record.plan_id)
        response = read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        return response

    def plan_route_nets(
        self,
        nets: list[str],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not nets:
            raise DocumentError("At least one net is required", code="scope_required")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, nets)
        if not pairs:
            raise DocumentError("No matching exported unrouted connections were found")
        if len(pairs) > 20:
            raise DocumentError("A local route plan is limited to 20 connections")
        operations: list[SemanticOperation] = []
        candidates: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route_min_vias(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            candidates.append(
                {
                    "net_id": pair["net_id"],
                    "points": [point.as_dict() for point in route.points],
                    "metrics": route.metrics,
                }
            )
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        preview = self.preview_semantic_operations(document, operations)
        total_length = sum(float(item["metrics"]["length_mm"]) for item in candidates)
        resolved_clearance = float(candidates[0]["metrics"]["clearance_mm"])
        record = self.plan_store.create(
            plan_type="route_nets",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config={
                "nets": nets,
                "layer": layer,
                "width": width,
                "clearance": resolved_clearance,
                "grid": grid,
                "preferred_layers": preferred_layers or [],
                "via_style": via_style,
                "max_vias": max_vias,
                "via_cost": via_cost,
            },
            operations=[operation.model_dump(mode="json") for operation in operations],
            changed_ids=sorted({pair["net_id"] for pair in pairs}),
            unresolved=[],
            candidates=candidates,
            score={"total_length_mm": total_length},
            metrics={
                "connection_count": len(operations),
                "total_length_mm": total_length,
                "clearance_resolutions": [
                    {
                        key: item["metrics"][key]
                        for key in (
                            "requested_clearance_mm",
                            "required_clearance_mm",
                            "effective_clearance_mm",
                            "clearance_sources",
                            "netclass_rules_applied",
                            "netclass_rules_ignored",
                            "clearance_rule_status",
                        )
                        if key in item["metrics"]
                    }
                    for item in candidates
                ],
                "netclass_rules_ignored": any(
                    bool(item["metrics"].get("netclass_rules_ignored", False))
                    for item in candidates
                ),
            },
            assumptions=["Connections are routed sequentially with bounded 45-degree A*."],
            warnings=[],
            limitations=["No push-and-shove or rip-up/retry is implemented."],
        )
        resources = self.plan_store.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "routes": candidates,
            },
            diff=preview["diff"],
        )
        record = self.plan_store.read(record.plan_id)
        response = read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )
        response["clearance_rule_status"] = {
            "per_route": [item["metrics"].get("clearance_rule_status") for item in candidates],
            "netclass_rules_ignored": any(
                bool(item["metrics"].get("netclass_rules_ignored", False)) for item in candidates
            ),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        return response

    def apply_route_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        plan = self.plan_store.read(plan_id)
        if plan.plan_type not in {"route_nets", "diff_pair_route"}:
            raise DocumentError(
                f"Unexpected route plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
            )
        return self.apply_stored_plan(
            plan_id,
            expected_plan_type=plan.plan_type,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def route_connections(
        self,
        connections: list[dict[str, Any]],
        *,
        ripup_retry: bool = True,
        max_ripup_attempts: int = 4,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route multiple connections sequentially with bounded rip-up/retry."""

        configs = [RouteConnectionConfig.model_validate(item) for item in connections]
        document, _target = self.gateway.load(path)
        synthesis = synthesize_routes_with_retry(
            document,
            configs,
            ripup_retry=ripup_retry,
            max_ripup_attempts=max_ripup_attempts,
            ordering=ordering,
        )
        if not synthesis.operations:
            raise RoutingError(
                "No connection could be routed",
                details={"failed": synthesis.failed},
            )
        response = self.semantic_operations(
            synthesis.operations, path, dry_run, expected_sha256, txid
        )
        response["routing"] = synthesis.metrics
        response["clearance_rule_status"] = {
            "per_route": [
                item.get("clearance_rule_status")
                for item in synthesis.metrics.get("clearance_resolutions", [])
            ],
            "netclass_rules_ignored": bool(synthesis.metrics.get("netclass_rules_ignored", False)),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        if synthesis.failed:
            response.setdefault("warnings", []).append(
                f"{len(synthesis.failed)} connection(s) could not be routed; "
                "see routing metrics for details."
            )
            response["routing"]["failed"] = synthesis.failed
        if synthesis.ripups:
            response["routing"]["ripups"] = synthesis.ripups
        return response

    def analyze_routing_congestion(
        self,
        connections: list[dict[str, Any]],
        *,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
    ) -> dict[str, Any]:
        """Rank routing connections deterministically without changing the document."""

        configs = [RouteConnectionConfig.model_validate(item) for item in connections]
        if not configs:
            raise RoutingError("At least one connection is required")
        document, target = self.gateway.load(path)
        ordered, priorities = plan_connection_order(
            document,
            configs,
            ordering=ordering,
        )
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        clearance_resolutions = []
        for _index, config in ordered:
            net = _find_net(snapshot, config.net)
            layer_ids, _start_layer, _end_layer = _route_layers(snapshot, config)
            # Congestion ranking uses the same clearance resolver as routing;
            # the returned resolution is part of the read-only decision record.
            clearance_resolutions.append(
                resolve_clearance(
                    snapshot,
                    layer_ids,
                    config.clearance,
                    nets=[net],
                ).as_dict()
            )
        return read_success(
            snapshot.info,
            {
                "ordering": ordering,
                "routing_order": [index for index, _config in ordered],
                "priorities": [item.as_dict() for item in priorities],
                "clearance_resolutions": clearance_resolutions,
                "clearance_rule_status": {
                    "per_route": [item["clearance_rule_status"] for item in clearance_resolutions],
                    "netclass_rules_ignored": any(
                        item["netclass_rules_ignored"] for item in clearance_resolutions
                    ),
                },
                "netclass_rules_ignored": any(
                    item["netclass_rules_ignored"] for item in clearance_resolutions
                ),
            },
            limitations=[
                "Congestion ranking is a deterministic corridor/bounding-box heuristic, "
                "not a global routing or push-and-shove solver."
            ],
        )
