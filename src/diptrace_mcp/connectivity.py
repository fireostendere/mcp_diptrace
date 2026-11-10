from __future__ import annotations

import math
from typing import Any, Literal

from .adapters import DocumentSnapshot
from .domain import ConnectivityGraph, ObjectRecord
from .errors import CapabilityUnavailableError


class _DisjointSet:
    def __init__(self, items: set[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, first: str, second: str) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[max(first_root, second_root)] = min(first_root, second_root)


def _endpoint_data(endpoint: ObjectRecord, net: ObjectRecord) -> dict[str, Any]:
    return {
        "endpoint_id": endpoint.stable_id,
        "endpoint_kind": endpoint.kind,
        "owner_id": endpoint.parent_id,
        "refdes": endpoint.refdes,
        "number": endpoint.label,
        "net_id": net.stable_id,
        "net_name": net.name,
        "position": endpoint.position,
    }


def build_connectivity_graph(snapshot: DocumentSnapshot) -> ConnectivityGraph:
    model = snapshot.board or snapshot.schematic
    if model is None:
        raise CapabilityUnavailableError(
            "Connectivity graphs require a PCB or schematic document"
        )
    source_kind: Literal["pcb", "schematic"] = (
        "pcb" if snapshot.board is not None else "schematic"
    )
    owner_kind = "component" if source_kind == "pcb" else "part"
    owners = {
        record.stable_id: record
        for record in snapshot.objects.values()
        if record.kind == owner_kind
    }
    disjoint = _DisjointSet(set(owners))
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    nets: list[dict[str, Any]] = []
    endpoint_mapping: list[dict[str, Any]] = []
    included_nodes: set[str] = set()

    for owner in sorted(owners.values(), key=lambda item: item.stable_id):
        nodes.append(
            {
                "id": owner.stable_id,
                "kind": owner.kind,
                "refdes": owner.refdes,
                "label": owner.label,
            }
        )
        included_nodes.add(owner.stable_id)

    for net in sorted(model.nets, key=lambda item: item.stable_id):
        endpoint_ids = net.relationships.get("endpoints", [])
        endpoints = [snapshot.objects[item] for item in endpoint_ids if item in snapshot.objects]
        owner_ids = sorted(
            {item.parent_id for item in endpoints if item.parent_id in owners}
        )
        for owner_id in owner_ids[1:]:
            disjoint.union(owner_ids[0], owner_id)
        nodes.append({"id": net.stable_id, "kind": "net", "name": net.name})
        included_nodes.add(net.stable_id)
        for endpoint in endpoints:
            if endpoint.stable_id not in included_nodes:
                nodes.append(
                    {
                        "id": endpoint.stable_id,
                        "kind": endpoint.kind,
                        "owner_id": endpoint.parent_id,
                        "refdes": endpoint.refdes,
                        "number": endpoint.label,
                    }
                )
                included_nodes.add(endpoint.stable_id)
            edges.append(
                {
                    "source": endpoint.stable_id,
                    "target": net.stable_id,
                    "kind": "logical_net_membership",
                }
            )
            endpoint_mapping.append(_endpoint_data(endpoint, net))
        nets.append(
            {
                "id": net.stable_id,
                "xml_id": net.xml_id,
                "name": net.name,
                "net_class": net.attributes.get("net_class"),
                "endpoint_ids": [item.stable_id for item in endpoints],
                "owner_ids": owner_ids,
                "trace_ids": net.relationships.get("traces", []),
                "via_ids": net.relationships.get("vias", []),
            }
        )

    grouped: dict[str, list[str]] = {}
    for owner_id in sorted(owners):
        grouped.setdefault(disjoint.find(owner_id), []).append(owner_id)
    components = sorted(grouped.values(), key=lambda items: (items[0], len(items)))

    unrouted: list[dict[str, Any]] = []
    if snapshot.board is not None:
        for index, ratline in enumerate(snapshot.board.ratlines):
            endpoints = ratline.get("endpoints", [])
            pad_ids = [item.get("pad_id") for item in endpoints]
            net_ids = {
                snapshot.objects[pad_id].relationships.get("net", [None])[0]
                for pad_id in pad_ids
                if isinstance(pad_id, str)
                and pad_id in snapshot.objects
                and snapshot.objects[pad_id].relationships.get("net")
            }
            unrouted.append(
                {
                    "ratline_index": index,
                    "endpoint_ids": pad_ids,
                    "positions": [item.get("position") for item in endpoints],
                    "net_id": next(iter(net_ids)) if len(net_ids) == 1 else None,
                    "ambiguous_net": len(net_ids) != 1,
                }
            )

    return ConnectivityGraph(
        document_id=snapshot.info.document_id,
        source_kind=source_kind,
        nodes=nodes,
        edges=edges,
        nets=nets,
        connected_components=components,
        unrouted_connections=unrouted,
        endpoint_mapping=endpoint_mapping,
        warnings=[
            "Connected components are logical owner groups, not proof of routed copper continuity."
        ],
    )


def _point_segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    ratio = 0.0
    if length_sq:
        ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
        ratio = max(0.0, min(1.0, ratio))
    return math.hypot(point[0] - start[0] - ratio * dx, point[1] - start[1] - ratio * dy)


def copper_connectivity(snapshot: DocumentSnapshot) -> list[dict[str, Any]]:
    """Per-net pad groups joined by exported trace copper.

    A net whose pads fall into more than one group is ``open`` unless a poured copper
    pour of that net could join them; that case is ``pour_reliant`` because only a
    native refill decides it. Returned only for nets with at least two pads.

    shortcut: layers are ignored, so same-net copper that overlaps on two layers
    without a via counts as joined; upgrade when a board needs that distinction.
    """
    board = snapshot.board
    if board is None:
        raise CapabilityUnavailableError("Copper connectivity requires a PCB document")
    traces_by_net: dict[str, list[ObjectRecord]] = {}
    for trace in board.traces:
        for net_id in trace.relationships.get("net", []):
            traces_by_net.setdefault(net_id, []).append(trace)
    poured_net_ids = {
        pour.net_id for pour in board.copper_pours if pour.attributes.get("poured") is True
    }
    result: list[dict[str, Any]] = []
    for net in board.nets:
        pads = [
            snapshot.objects[item]
            for item in net.relationships.get("endpoints", [])
            if item in snapshot.objects
        ]
        if len(pads) < 2:
            continue
        traces = traces_by_net.get(net.stable_id, [])
        groups = _DisjointSet({item.stable_id for item in (*pads, *traces)})
        polylines: list[tuple[str, list[tuple[float, float]], float]] = []
        for trace in traces:
            points = [(p["x"], p["y"]) for p in trace.attributes.get("points", [])]
            widths = trace.attributes.get("segment_widths_mm") or [0.0]
            polylines.append((trace.stable_id, points, max(widths) / 2 + 0.01))
        for trace_id, points, reach in polylines:
            for pad in pads:
                box, centre = pad.bbox, pad.position
                for x, y in points:
                    inside = box is not None and (
                        box["min_x"] - reach <= x <= box["max_x"] + reach
                        and box["min_y"] - reach <= y <= box["max_y"] + reach
                    )
                    at_centre = centre is not None and (
                        math.hypot(x - centre["x"], y - centre["y"]) <= reach
                    )
                    if inside or at_centre:
                        groups.union(trace_id, pad.stable_id)
                        break
            for other_id, other_points, other_reach in polylines:
                if other_id <= trace_id:
                    continue
                touching = any(
                    _point_segment_distance(point, start, end) <= max(reach, other_reach)
                    for mine, theirs in ((points, other_points), (other_points, points))
                    for point in (mine[:1] + mine[-1:] if mine else [])
                    for start, end in zip(theirs, theirs[1:], strict=False)
                )
                if touching:
                    groups.union(trace_id, other_id)
        pad_groups = len({groups.find(pad.stable_id) for pad in pads})
        status = "connected"
        if pad_groups > 1:
            status = "pour_reliant" if net.xml_id in poured_net_ids else "open"
        result.append(
            {
                "net_id": net.stable_id,
                "net_name": net.name,
                "pad_count": len(pads),
                "pad_group_count": pad_groups,
                "status": status,
            }
        )
    return result
