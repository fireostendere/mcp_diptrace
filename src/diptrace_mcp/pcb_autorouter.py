"""Block-aware PCB routing orchestration over the existing bounded solvers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import ObjectRecord, StrictModel
from .errors import CapabilityUnavailableError, DipTraceMcpError, RoutingError
from .multirouter import MultiRouteResult, synthesize_routes_with_retry
from .numeric_inputs import xml_number_mm
from .operations import SemanticOperation
from .pcb_design_intent import PCBIntentOverrides
from .pcb_placement import PCBPlacementV2Config, plan_pcb_placement_v2
from .pcb_routing_policy import (
    PCBNetRoutingPolicy,
    PCBRoutingPolicySet,
    compile_pcb_routing_policy,
)
from .routing import RouteConnectionConfig
from .semantic_compiler import apply_semantic_operations
from .via_styles import resolve_via_span, validate_via_geometry
from .xml_document import DipTraceDocument


class PCBRouterConfig(StrictModel):
    nets: list[str] = Field(default_factory=list, max_length=64)
    routing_layers: list[str] = Field(default_factory=list, max_length=32)
    default_trace_width_mm: float | None = Field(default=None, gt=0.0)
    clearance_mm: float | None = Field(default=None, ge=0.0)
    grid_mm: float = Field(default=0.5, gt=0.0, le=10.0)
    via_style: str | None = Field(default=None, min_length=1, max_length=256)
    max_vias_per_connection: int = Field(default=2, ge=0, le=32)
    max_detour: float = Field(default=3.0, ge=1.0, le=100.0)
    max_nodes: int = Field(default=100_000, ge=100, le=1_000_000)
    route_time_budget_ms: int = Field(default=5_000, ge=100, le=30_000)
    ripup_retry: bool = True
    max_ripup_attempts: int = Field(default=4, ge=0, le=8)
    allow_component_moves: bool = True
    component_move_penalty_mm: float = Field(default=5.0, ge=0.0)
    placement: PCBPlacementV2Config = Field(default_factory=PCBPlacementV2Config)


class TraceWidthResolution(StrictModel):
    net_id: str
    net_name: str | None = None
    layer_ids: list[str]
    requested_width_mm: float | None = None
    effective_width_mm: float = Field(gt=0.0)
    minimum_width_mm: float = Field(ge=0.0)
    maximum_width_mm: float | None = Field(default=None, gt=0.0)
    effective_source: str
    promoted_to_minimum: bool = False
    sources: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PCBRoutePlan:
    operations: list[SemanticOperation]
    routing: MultiRouteResult
    policy: PCBRoutingPolicySet
    width_resolutions: list[TraceWidthResolution]
    selected_candidate: str
    changed_component_ids: list[str]
    metrics: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


def _require_board(snapshot: DocumentSnapshot) -> None:
    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB autorouting requires a PCB document")


def _layer(snapshot: DocumentSnapshot, value: str) -> dict[str, Any]:
    assert snapshot.board is not None
    matches = [
        item
        for item in snapshot.board.layers
        if str(item.get("id", "")) == value
        or str(item.get("name", "")).casefold() == value.casefold()
    ]
    if len(matches) != 1:
        raise RoutingError(f"Unique routing layer was not found: {value}")
    return matches[0]


def _net_class(snapshot: DocumentSnapshot, net: ObjectRecord) -> Any:
    class_id = str(net.attributes.get("net_class", ""))
    if not class_id:
        return None
    matches = [
        item
        for item in snapshot.document.container.findall("./NetClasses/NetClass")
        if item.get("Id") == class_id
    ]
    if len(matches) != 1:
        raise RoutingError(
            "Net references an unavailable NetClass",
            details={"net_id": net.stable_id, "net_class_id": class_id},
        )
    return matches[0]


def _layer_property(net_class: Any, layer_id: str, layer_name: str) -> Any:
    if net_class is None:
        return None
    matches = [
        item
        for item in net_class.findall("./LayProperties/LayProperty")
        if item.get("Lay") == layer_id
        or (item.findtext("./LayerName") or item.get("LayerName", "")).casefold()
        == layer_name.casefold()
    ]
    if len(matches) > 1:
        raise RoutingError(
            "NetClass contains ambiguous routing rules for one copper layer",
            details={"layer_id": layer_id, "layer_name": layer_name},
        )
    return matches[0] if matches else None


def _positive_rule(
    snapshot: DocumentSnapshot,
    element: Any,
    attribute: str,
    *,
    source: str,
) -> float | None:
    if element is None or element.get(attribute) in {None, ""}:
        return None
    value = xml_number_mm(snapshot.document, element, attribute)
    if value <= 0.0:
        raise RoutingError(
            "Trace-width rule must be positive",
            details={"source": source, "attribute": attribute, "value_mm": value},
        )
    return value


def resolve_trace_width(
    snapshot: DocumentSnapshot,
    net: ObjectRecord,
    layers: list[str],
    *,
    requested: float | None = None,
) -> TraceWidthResolution:
    """Resolve one constant route width without inventing electrical facts."""

    _require_board(snapshot)
    if not layers:
        raise RoutingError("At least one routing layer is required for width resolution")
    if requested is not None and (not math.isfinite(requested) or requested <= 0.0):
        raise RoutingError("Requested trace width must be a positive finite number")
    resolved_layers = [_layer(snapshot, item) for item in layers]
    net_class = _net_class(snapshot, net)
    sources: list[dict[str, Any]] = []
    defaults: list[tuple[float, str]] = []
    minimums: list[float] = []
    maximums: list[float] = []
    for layer in resolved_layers:
        layer_id = str(layer.get("id", ""))
        layer_name = str(layer.get("name", ""))
        prop = _layer_property(net_class, layer_id, layer_name)
        for attribute, kind in (
            ("Width", "netclass_default"),
            ("MinWidth", "netclass_minimum"),
            ("MaxWidth", "netclass_maximum"),
        ):
            value = _positive_rule(
                snapshot,
                prop,
                attribute,
                source="NetClasses/NetClass/LayProperties/LayProperty",
            )
            if value is None:
                continue
            sources.append(
                {
                    "kind": kind,
                    "layer_id": layer_id,
                    "layer_name": layer_name,
                    "value_mm": value,
                }
            )
            if attribute == "Width":
                defaults.append((value, kind))
            elif attribute == "MinWidth":
                minimums.append(value)
            else:
                maximums.append(value)
        drc = next(
            (
                item
                for item in snapshot.document.container.findall("./DRC/LaySizes/LaySize")
                if item.get("Lay") == layer_id
            ),
            None,
        )
        minimum = _positive_rule(
            snapshot,
            drc,
            "MinTrace",
            source="DRC/LaySizes/LaySize",
        )
        if minimum is not None:
            minimums.append(minimum)
            sources.append(
                {
                    "kind": "board_minimum",
                    "layer_id": layer_id,
                    "layer_name": layer_name,
                    "value_mm": minimum,
                }
            )

    routing = snapshot.document.container.find("./Settings/Routing")
    board_default = _positive_rule(
        snapshot,
        routing,
        "TraceWidth",
        source="Settings/Routing.TraceWidth",
    )
    if board_default is not None:
        sources.append({"kind": "board_default", "value_mm": board_default})
    if requested is not None:
        base, source = requested, "explicit"
        sources.append({"kind": "explicit", "value_mm": requested})
    elif defaults:
        base, source = max(defaults, key=lambda item: item[0])
    elif board_default is not None:
        base, source = board_default, "board_default"
    else:
        stack_widths = [
            item.material.trace_width_mm
            for item in snapshot.board.stackup.layers  # type: ignore[union-attr]
            if item.layer_id in {str(layer.get("id", "")) for layer in resolved_layers}
            and item.material.trace_width_mm is not None
        ]
        if not stack_widths:
            raise CapabilityUnavailableError(
                "Trace width is missing from the request, NetClass, board defaults and stackup",
                object_ids=[net.stable_id],
            )
        base, source = max(stack_widths), "stackup_default"
        sources.append({"kind": source, "value_mm": base})

    minimum = max(minimums, default=0.0)
    maximum = min(maximums) if maximums else None
    if maximum is not None and minimum > maximum:
        raise RoutingError(
            "Trace-width rules have no legal intersection",
            details={"minimum_width_mm": minimum, "maximum_width_mm": maximum},
            object_ids=[net.stable_id],
        )
    effective = max(base, minimum)
    if maximum is not None and effective > maximum:
        raise RoutingError(
            "Resolved trace width exceeds the NetClass maximum",
            details={"effective_width_mm": effective, "maximum_width_mm": maximum},
            object_ids=[net.stable_id],
        )
    return TraceWidthResolution(
        net_id=net.stable_id,
        net_name=net.name,
        layer_ids=[str(item.get("id", "")) for item in resolved_layers],
        requested_width_mm=requested,
        effective_width_mm=effective,
        minimum_width_mm=minimum,
        maximum_width_mm=maximum,
        effective_source="minimum_rule" if effective > base else source,
        promoted_to_minimum=effective > base,
        sources=sources,
    )


def _routing_layers(
    snapshot: DocumentSnapshot,
    policy: PCBNetRoutingPolicy,
    config: PCBRouterConfig,
) -> list[str]:
    assert snapshot.board is not None
    requested = (
        config.routing_layers
        or policy.preferred_layers
        or [
            str(item.get("name") or item.get("id", ""))
            for item in snapshot.board.layers
            if str(item.get("type", "")).casefold() == "signal"
        ]
    )
    forbidden = {item.casefold() for item in policy.forbidden_layers}
    result: list[str] = []
    for value in requested:
        layer = _layer(snapshot, value)
        layer_id = str(layer.get("id", ""))
        name = str(layer.get("name", ""))
        if str(layer.get("type", "")).casefold() != "signal":
            raise RoutingError(f"Active routing is not supported on layer {name!r}")
        if layer_id.casefold() in forbidden or name.casefold() in forbidden:
            continue
        if name not in result:
            result.append(name)
    if not result:
        raise RoutingError(
            f"No permitted signal layer remains for net {policy.name or policy.net_id}"
        )
    return result


def _endpoint_layer(
    snapshot: DocumentSnapshot,
    pad: ObjectRecord,
    permitted: list[str],
) -> str:
    style = pad.attributes.get("pad_style") or {}
    if str(style.get("pad_type", "")).casefold() != "surface":
        return permitted[0]
    side = (pad.side or "Top").casefold()
    match = next((item for item in permitted if item.casefold().startswith(side)), None)
    if match is None:
        raise RoutingError(
            f"Surface pad side {pad.side!r} is excluded from permitted routing layers",
            object_ids=[pad.stable_id],
        )
    return match


def _automatic_via_style(
    snapshot: DocumentSnapshot,
    permitted: list[str],
    start_layer: str,
    end_layer: str,
) -> str | None:
    assert snapshot.board is not None
    permitted_ids = {str(_layer(snapshot, item).get("id", "")) for item in permitted}
    required_ids = {
        str(_layer(snapshot, start_layer).get("id", "")),
        str(_layer(snapshot, end_layer).get("id", "")),
    }
    for style in snapshot.board.via_styles:
        try:
            validate_via_geometry(style)
            span = set(resolve_via_span(snapshot.board, style))
        except DipTraceMcpError:
            continue
        if required_ids <= span and len(permitted_ids & span) >= 2:
            return style.id
    return None


def _connections(
    snapshot: DocumentSnapshot,
    policy_set: PCBRoutingPolicySet,
    config: PCBRouterConfig,
) -> tuple[list[RouteConnectionConfig], list[TraceWidthResolution], list[str]]:
    assert snapshot.board is not None
    requested = {item.casefold() for item in config.nets}
    policies = {item.net_id: item for item in policy_set.policies}
    nets_by_xml = {item.xml_id: item for item in snapshot.board.nets}
    blocks = {item.component_id: item.block_id for item in policy_set.intent.components}
    warnings: list[str] = []
    result: list[RouteConnectionConfig] = []
    widths: dict[str, TraceWidthResolution] = {}
    seen: set[tuple[str, str, str]] = set()
    for ratline in snapshot.board.ratlines:
        endpoints = ratline.get("endpoints", [])
        if len(endpoints) != 2 or any(item.get("pad_id") is None for item in endpoints):
            continue
        start = snapshot.get_object(str(endpoints[0]["pad_id"]))
        end = snapshot.get_object(str(endpoints[1]["pad_id"]))
        if start.net_id is None or start.net_id != end.net_id:
            continue
        net = nets_by_xml.get(start.net_id)
        if net is None or (
            requested
            and net.stable_id.casefold() not in requested
            and (net.name or "").casefold() not in requested
            and (net.xml_id or "").casefold() not in requested
        ):
            continue
        left_id, right_id = sorted((start.stable_id, end.stable_id))
        key = (net.stable_id, left_id, right_id)
        if key in seen:
            continue
        seen.add(key)
        policy = policies[net.stable_id]
        layers = _routing_layers(snapshot, policy, config)
        start_layer = _endpoint_layer(snapshot, start, layers)
        end_layer = _endpoint_layer(snapshot, end, layers)
        width_layers = list(dict.fromkeys([*layers, start_layer, end_layer]))
        width = widths.get(net.stable_id)
        if width is None:
            width = resolve_trace_width(
                snapshot,
                net,
                width_layers,
                requested=(
                    policy.trace_width_mm
                    if policy.trace_width_mm is not None
                    else config.default_trace_width_mm
                ),
            )
            widths[net.stable_id] = width
        via_budget = min(
            config.max_vias_per_connection,
            policy.max_vias if policy.max_vias is not None else config.max_vias_per_connection,
        )
        if len(width_layers) == 1:
            via_budget = 0
        via_style = config.via_style
        if via_budget and via_style is None:
            via_style = _automatic_via_style(snapshot, width_layers, start_layer, end_layer)
        if via_budget and via_style is None:
            warnings.append(
                f"{policy.name or policy.net_id}: no compatible valid via style is available; "
                "routing is limited to endpoint layers"
            )
            via_budget = 0
        component_blocks = {
            blocks[item]
            for item in (start.parent_id, end.parent_id)
            if item is not None and item in blocks
        }
        priority = min(1_000, policy.priority + (50 if len(component_blocks) == 1 else 0))
        clearance_values = [
            item for item in (config.clearance_mm, policy.minimum_spacing_mm) if item is not None
        ]
        result.append(
            RouteConnectionConfig(
                net=net.stable_id,
                start_object_id=start.stable_id,
                end_object_id=end.stable_id,
                layer=start_layer,
                start_layer=start_layer,
                end_layer=end_layer,
                preferred_layers=width_layers,
                width=width.effective_width_mm,
                clearance=max(clearance_values) if clearance_values else None,
                grid=config.grid_mm,
                via_style=via_style,
                max_vias=via_budget,
                via_cost=5.0 + policy.via_penalty,
                max_detour=config.max_detour,
                max_nodes=config.max_nodes,
                time_budget_ms=config.route_time_budget_ms,
                routing_priority=priority,
            )
        )
    if not result:
        raise RoutingError("No matching exported unrouted PCB connections were found")
    return result, list(widths.values()), warnings


def _candidate_score(
    routing: MultiRouteResult,
    move_count: int,
    config: PCBRouterConfig,
) -> tuple[int, int, float, int]:
    return (
        len(routing.failed),
        int(routing.metrics.get("total_via_count", 0)),
        float(routing.metrics.get("total_length_mm", 0.0))
        + move_count * config.component_move_penalty_mm,
        move_count,
    )


def _movement_has_pattern_geometry(
    snapshot: DocumentSnapshot,
    component_ids: list[str],
) -> bool:
    assert snapshot.board is not None
    by_id = {item.stable_id: item for item in snapshot.board.components}
    return all(
        component_id in by_id
        and all(
            snapshot.get_object(pad_id).attributes.get("local_position") is not None
            for pad_id in by_id[component_id].relationships.get("pads", [])
        )
        for component_id in component_ids
    )


def plan_pcb_routes(
    document: DipTraceDocument,
    *,
    overrides: PCBIntentOverrides | None = None,
    config: PCBRouterConfig | None = None,
) -> PCBRoutePlan:
    """Plan block-aware PCB placement plus minimum-via multinet routing."""

    config = config or PCBRouterConfig()
    snapshot = build_snapshot(document)
    _require_board(snapshot)
    assert snapshot.board is not None
    policy = compile_pcb_routing_policy(snapshot, overrides=overrides)
    connections, widths, warnings = _connections(snapshot, policy, config)
    baseline = synthesize_routes_with_retry(
        document,
        connections,
        ripup_retry=config.ripup_retry,
        max_ripup_attempts=config.max_ripup_attempts,
    )
    candidates: list[tuple[str, list[SemanticOperation], list[str], MultiRouteResult]] = [
        ("existing_placement", [], [], baseline)
    ]

    # ponytail: one bounded block candidate; add ensemble profiles only after a real miss.
    if config.allow_component_moves:
        if snapshot.board.traces:
            warnings.append(
                "Component movement was skipped because existing traces would need "
                "connectivity-preserving endpoint repair."
            )
        elif config.nets:
            warnings.append(
                "Component movement was skipped for a partial-net request to avoid "
                "moving unrelated functional blocks."
            )
        else:
            try:
                placement = plan_pcb_placement_v2(
                    snapshot,
                    overrides=overrides,
                    config=config.placement,
                )
                if placement.operations and _movement_has_pattern_geometry(
                    snapshot, placement.changed_component_ids
                ):
                    placed = apply_semantic_operations(document, placement.operations).document
                    placed_routing = synthesize_routes_with_retry(
                        placed,
                        connections,
                        ripup_retry=config.ripup_retry,
                        max_ripup_attempts=config.max_ripup_attempts,
                    )
                    candidates.append(
                        (
                            "block_placement",
                            placement.operations,
                            placement.changed_component_ids,
                            placed_routing,
                        )
                    )
                elif placement.operations:
                    warnings.append(
                        "Component movement was skipped because exact pattern-derived "
                        "pad anchors are unavailable."
                    )
            except DipTraceMcpError as exc:
                warnings.append(f"Block-placement routing candidate failed: {exc}")

    selected = min(
        candidates,
        key=lambda item: _candidate_score(item[3], len(item[2]), config),
    )
    name, placement_operations, changed_ids, routing = selected
    candidate_metrics = [
        {
            "name": candidate_name,
            "changed_component_count": len(candidate_changed_ids),
            "failed_count": len(candidate_routing.failed),
            "routed_count": len(candidate_routing.routed),
            "via_count": candidate_routing.metrics.get("total_via_count", 0),
            "length_mm": candidate_routing.metrics.get("total_length_mm", 0.0),
            "selection_score": _candidate_score(
                candidate_routing, len(candidate_changed_ids), config
            ),
        }
        for candidate_name, _ops, candidate_changed_ids, candidate_routing in candidates
    ]
    return PCBRoutePlan(
        operations=[*placement_operations, *routing.operations],
        routing=routing,
        policy=policy,
        width_resolutions=widths,
        selected_candidate=name,
        changed_component_ids=changed_ids,
        metrics={
            **routing.metrics,
            "selected_candidate": name,
            "candidates": candidate_metrics,
            "functional_blocks": [item.model_dump(mode="json") for item in policy.intent.blocks],
            "trace_widths": [item.model_dump(mode="json") for item in widths],
        },
        assumptions=[
            "Each connection is attempted with VIA budgets 0..N; the first legal "
            "budget proves the minimum within the bounded routing model.",
            "Functional blocks come from deterministic design-intent grouping and "
            "mechanical anchors remain fixed.",
        ],
        warnings=sorted(set([*policy.warnings, *warnings])),
        limitations=[
            "Trace width is resolved from explicit/exported rules; current capacity, "
            "temperature rise and impedance still require sufficient physical inputs.",
            "Placement feedback compares one bounded block-aware candidate with the "
            "existing placement; it is not unrestricted global co-optimization.",
            "The router remains bounded 45-degree A* with bounded rip-up/retry, not "
            "push-and-shove.",
        ],
    )
