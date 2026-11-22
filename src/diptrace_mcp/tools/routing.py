"""Trace and via edits, local routing and route plans."""
from __future__ import annotations

from typing import Any, Literal

from ..operations import (
    TracePathPoint,
)
from ..server_inputs import (
    DipTraceFastMCP,
    RouteConnectionInput,
    SelectorInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def add_trace(
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[TracePathPoint],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add an explicit validated trace path between two normalized pad endpoints."""
        return service.add_trace(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            points=[point.model_dump() for point in points],
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def replace_trace(
        trace_id: str,
        points: list[TracePathPoint],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Replace trace geometry while preserving both connected endpoints."""
        return service.replace_trace(
            trace_id,
            [point.model_dump() for point in points],
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def delete_trace(
        selector: SelectorInput,
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Delete selected traces; connectivity regression requires explicit opt-in."""
        return service.delete_trace(
            selector,
            allow_connectivity_regression=allow_connectivity_regression,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def set_trace_width(
        selector: SelectorInput,
        width: float,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set selected trace segment widths with exported DRC minimum checks."""
        return service.set_trace_width(
            selector,
            width,
            segment_indices=segment_indices,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def add_via(
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a verified ViaStyle trace point on an existing segment."""
        return service.add_via(
            trace_id,
            x,
            y,
            via_style,
            layer_before=layer_before,
            layer_after=layer_after,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def move_via(
        selector: SelectorInput,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Move selected trace-point vias transactionally."""
        return service.move_via(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def delete_via(
        selector: SelectorInput,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Remove ViaStyle from selected trace points."""
        return service.delete_via(
            selector,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def set_via_style(
        selector: SelectorInput,
        via_style: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set an existing verified project ViaStyle on selected vias."""
        return service.set_via_style(
            selector,
            via_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def list_unrouted_connections(
        path: str | None = None,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        """List exported ratlines with normalized pad endpoints and lengths."""
        return service.list_unrouted_connections(path, nets=nets)

    @mcp.tool()
    def get_route_details(
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Return trace segments, per-layer geometric length and via counts."""
        return service.get_route_details(trace_id=trace_id, net=net, path=path)

    @mcp.tool()
    def route_connection(
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
        (
            "Route one pad-to-pad connection with bounded deterministic 45-degree A*.\n\n"
            "Omit clearance to use the applicable document DRC TraceToTrace rule."
        )
        return service.route_connection(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers,
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def route_net(
        net: str,
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
        """Route exported ratlines; omitted clearance comes from document DRC."""
        return service.route_net(
            net,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def route_connections(
        connections: list[RouteConnectionInput],
        ripup_retry: bool = True,
        max_ripup_attempts: int = 4,
        ordering: Literal["input", "congestion_aware"] = "congestion_aware",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route multiple connections sequentially with bounded rip-up/retry."""
        return service.route_connections(
            connections,
            ripup_retry=ripup_retry,
            max_ripup_attempts=max_ripup_attempts,
            ordering=ordering,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def analyze_routing_congestion(
        connections: list[RouteConnectionInput],
        ordering: Literal["input", "congestion_aware"] = "congestion_aware",
        path: str | None = None,
    ) -> dict[str, Any]:
        """Rank route connections by deterministic corridor congestion without editing."""
        return service.analyze_routing_congestion(
            connections,
            ordering=ordering,
            path=path,
        )

    @mcp.tool()
    def route_diff_pair(
        pair: str,
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
        """Route a coupled pair; omitted clearance comes from document DRC."""
        return service.route_diff_pair(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def plan_diff_pair_route(
        pair: str,
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
        """Plan a coupled route; omitted clearance comes from document DRC."""
        return service.plan_diff_pair_route(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
        )

    @mcp.tool()
    def plan_route_nets(
        nets: list[str],
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
        """Plan bounded routes; omitted clearance comes from document DRC."""
        return service.plan_route_nets(
            nets,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
        )
