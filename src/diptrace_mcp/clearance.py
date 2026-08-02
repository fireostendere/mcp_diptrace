"""Shared, fail-closed clearance resolution.

The router and offline review must make the same decision from the same XML
rules.  This module intentionally consumes the normalized snapshot only for
object identity/layer names and reads the small rule subtrees from the source
document so malformed numeric values retain the existing byte-location errors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot
from .errors import (
    CapabilityUnavailableError,
    InvalidArgumentError,
    NetClassResolutionError,
)
from .numeric_inputs import xml_number_mm


@dataclass(frozen=True, slots=True)
class ClearanceResolution:
    requested_clearance_mm: float | None
    required_clearance_mm: float
    effective_clearance_mm: float
    clearance_sources: tuple[dict[str, Any], ...]
    netclass_rules_applied: bool
    netclass_rules_ignored: bool
    clearance_rule_status: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_clearance_mm": self.requested_clearance_mm,
            "required_clearance_mm": self.required_clearance_mm,
            "effective_clearance_mm": self.effective_clearance_mm,
            "clearance_sources": [dict(item) for item in self.clearance_sources],
            "netclass_rules_applied": self.netclass_rules_applied,
            "netclass_rules_ignored": self.netclass_rules_ignored,
            "clearance_rule_status": dict(self.clearance_rule_status),
        }


def _layer_name_map(snapshot: DocumentSnapshot) -> dict[str, str]:
    if snapshot.board is None:
        return {}
    result: dict[str, str] = {}
    for layer in snapshot.board.layers:
        layer_id = str(layer.get("id", ""))
        layer_name = str(layer.get("name", ""))
        if layer_id:
            result[layer_id] = layer_name
        if layer_name:
            result.setdefault(layer_name, layer_name)
    return result


def _board_default_rules(
    snapshot: DocumentSnapshot,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rules: dict[str, float] = {}
    sources: list[dict[str, Any]] = []
    for element in snapshot.document.container.findall(
        "./DRC/LayClearances/LayClearance"
    ):
        if element.get("TraceToTrace") is None:
            continue
        layer_id = element.get("Lay", "")
        if not layer_id:
            continue
        value = xml_number_mm(snapshot.document, element, "TraceToTrace")
        rules[layer_id] = value
        sources.append(
            {
                "kind": "board_default",
                "layer_id": layer_id,
                "value_mm": value,
                "source": "DRC/LayClearances/LayClearance.TraceToTrace",
            }
        )
    return rules, sources


def _class_clearance(
    snapshot: DocumentSnapshot,
    *,
    net: Any,
    layer_ids: list[str],
    classes: dict[str, Any],
    names: dict[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    class_ref = str(net.attributes.get("net_class", ""))
    if not class_ref:
        return [], []
    net_class = classes.get(class_ref)
    if net_class is None:
        raise NetClassResolutionError(
            "A net references an unknown NetClass",
            details={
                "net_id": net.xml_id or net.stable_id,
                "net_name": net.name,
                "unresolved_class_reference": class_ref,
            },
            object_ids=[net.stable_id],
        )

    class_name = net_class.findtext("./Name") or net_class.get("Name", "")
    layer_rules = list(net_class.findall("./LayProperties/LayProperty"))
    result: list[dict[str, Any]] = []
    covered_layers: list[str] = []
    for layer_id in layer_ids:
        layer_name = names.get(layer_id, layer_id)
        property_element = next(
            (
                item
                for item in layer_rules
                if (
                    (item.findtext("./LayerName") or item.get("LayerName", "")).casefold()
                    in {layer_name.casefold(), layer_id.casefold()}
                    or str(item.get("Lay", "")) == layer_id
                )
            ),
            None,
        )
        if property_element is None or property_element.get("Clearance") is None:
            continue
        value = xml_number_mm(snapshot.document, property_element, "Clearance")
        covered_layers.append(layer_id)
        result.append(
            {
                "kind": "netclass",
                "net_id": net.xml_id or net.stable_id,
                "net_name": net.name,
                "net_class_id": class_ref,
                "net_class_name": class_name,
                "layer_id": layer_id,
                "value_mm": value,
                "source": "NetClasses/NetClass/LayProperties/LayProperty.Clearance",
            }
        )
    return result, covered_layers


def resolve_clearance(
    snapshot: DocumentSnapshot,
    layer_ids: list[str],
    requested: float | None,
    *,
    nets: list[Any] | None = None,
) -> ClearanceResolution:
    """Resolve clearance using board defaults and every affected NetClass.

    Precedence is deliberately monotonic:

    ``effective = max(requested, board defaults, affected NetClass rules)``.

    A caller value can therefore raise a required rule but can never lower it.
    Unknown class references fail closed for routing callers. Review callers can
    catch :class:`NetClassResolutionError` and publish a structured warning.
    """

    if requested is not None and (
        not math.isfinite(requested) or requested < 0.0
    ):
        raise InvalidArgumentError(
            "Clearance must be a finite non-negative value in millimetres",
            details={"field": "clearance", "units": "mm"},
        )
    if not layer_ids:
        raise CapabilityUnavailableError(
            "Clearance resolution requires at least one routing layer",
            details={"requested_layer_ids": []},
        )
    board_rules, board_sources = _board_default_rules(snapshot)
    classes = {
        item.get("Id", ""): item
        for item in snapshot.document.container.findall("./NetClasses/NetClass")
        if item.get("Id")
    }
    names = _layer_name_map(snapshot)
    netclass_sources: list[dict[str, Any]] = []
    netclass_layers: set[str] = set()
    for net in nets or []:
        sources, covered = _class_clearance(
            snapshot,
            net=net,
            layer_ids=layer_ids,
            classes=classes,
            names=names,
        )
        netclass_sources.extend(sources)
        netclass_layers.update(covered)

    unresolved_layers = [
        layer_id
        for layer_id in layer_ids
        if layer_id not in board_rules and layer_id not in netclass_layers
    ]
    if unresolved_layers and requested is None:
        raise CapabilityUnavailableError(
            "Routing clearance was omitted, but applicable board or NetClass "
            "TraceToTrace rules are unavailable",
            details={
                "missing_layer_ids": unresolved_layers,
                "requested_layer_ids": layer_ids,
                "rule_source": (
                    "DRC/LayClearances/LayClearance.TraceToTrace or "
                    "NetClasses/NetClass/LayProperties/LayProperty.Clearance"
                ),
            },
        )

    sources: tuple[dict[str, Any], ...] = tuple(
        sorted(
            [
                *board_sources,
                *netclass_sources,
                *(
                    [
                        {
                            "kind": "explicit_requested",
                            "value_mm": requested,
                            "source": "caller",
                        }
                    ]
                    if requested is not None
                    else []
                ),
            ],
            key=lambda item: (
                str(item.get("kind", "")),
                str(item.get("layer_id", "")),
                str(item.get("net_id", "")),
                str(item.get("net_class_id", "")),
            ),
        )
    )
    required = max(
        [
            *(
                value
                for layer_id, value in board_rules.items()
                if layer_id in layer_ids
            ),
            *(float(item["value_mm"]) for item in netclass_sources),
            0.0,
        ]
    )
    effective = max(required, requested if requested is not None else 0.0)
    class_applied = bool(netclass_sources)
    if requested is not None and effective == requested:
        source_label = "caller"
    elif class_applied and effective > max(board_rules.values(), default=0.0):
        source_label = "netclass_promoted"
    else:
        source_label = "document_drc_trace_to_trace"
    status: dict[str, Any] = {
        "netclass_rules_applied": class_applied,
        "netclass_rules_ignored": False,
        "fallback_source": (
            "netclass_or_global_default" if class_applied else "explicit_or_global_default"
        ),
        "warning_code": None,
        "clearance_source": source_label,
        "unknown_class_references": [],
    }
    return ClearanceResolution(
        requested_clearance_mm=requested,
        required_clearance_mm=required,
        effective_clearance_mm=effective,
        clearance_sources=sources,
        netclass_rules_applied=class_applied,
        netclass_rules_ignored=False,
        clearance_rule_status=status,
    )


def clearance_rule_status(
    snapshot: DocumentSnapshot | None,
    *,
    operation: str = "netclass_aware_clearance",
) -> dict[str, Any]:
    """Return capability-level disclosure without resolving a route."""

    ignored_operations = [
        "trace_object_clearance",
        "placement_clearance",
    ]
    if snapshot is None or snapshot.board is None:
        ignored = operation in {"capability", *ignored_operations}
        return {
            "netclass_rules_applied": False,
            "netclass_rules_ignored": ignored,
            "fallback_source": "explicit_or_global_default",
            "warning_code": "netclass_rules_ignored" if ignored else None,
            "operation": operation,
            "unknown_class_references": [],
            "ignored_operations": ignored_operations,
            "affected_operations": [
                "route_connection",
                "route_net",
                "route_connections",
                "route_diff_pair",
                "plan_diff_pair_route",
                "analyze_routing_congestion",
                "offline_clearance_review",
            ],
        }
    class_ids = {
        item.get("Id", "")
        for item in snapshot.document.container.findall("./NetClasses/NetClass")
    }
    has_class_clearance = any(
        item.get("Clearance") is not None
        for net_class in snapshot.document.container.findall("./NetClasses/NetClass")
        for item in net_class.findall("./LayProperties/LayProperty")
    )
    unresolved = sorted(
        {
            str(net.attributes.get("net_class", ""))
            for net in snapshot.board.nets
            if net.attributes.get("net_class")
            and str(net.attributes.get("net_class")) not in class_ids
        }
    )
    netclass_aware_operations = {
        "route_connection",
        "route_net",
        "route_connections",
        "route_diff_pair",
        "plan_diff_pair_route",
        "analyze_routing_congestion",
        "offline_clearance_review",
        "netclass_aware_clearance",
    }
    rules_ignored = operation not in netclass_aware_operations and has_class_clearance
    return {
        "netclass_rules_applied": has_class_clearance and not unresolved,
        "netclass_rules_ignored": rules_ignored or bool(unresolved),
        "fallback_source": "board_default_for_unassigned_nets",
        "warning_code": (
            "unknown_net_class"
            if unresolved
            else "netclass_rules_ignored"
            if rules_ignored
            else None
        ),
        "operation": operation,
        "unknown_class_references": unresolved,
        "ignored_operations": ignored_operations,
        "affected_operations": [
            "route_connection",
            "route_net",
            "route_connections",
            "route_diff_pair",
            "plan_diff_pair_route",
            "analyze_routing_congestion",
            "offline_clearance_review",
        ],
    }
