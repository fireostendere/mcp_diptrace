from __future__ import annotations

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
