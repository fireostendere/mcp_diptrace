from __future__ import annotations

from collections import defaultdict
from typing import Any

from .adapters import DocumentSnapshot
from .errors import DocumentError


def _component_values(snapshot: DocumentSnapshot) -> dict[str, set[str]]:
    if snapshot.schematic is not None:
        items = snapshot.schematic.parts
    else:
        assert snapshot.board is not None
        items = snapshot.board.components
    result: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item.refdes:
            result[item.refdes.casefold()].add(item.value or "")
    return result


def _net_endpoints(snapshot: DocumentSnapshot) -> dict[str, set[str]]:
    container = snapshot.document.container
    if snapshot.schematic is not None:
        owners = {
            part.get("Id", ""): (part.findtext("./RefDes") or "").strip()
            for part in container.findall("./Components/Part")
        }
        return {
            (net.findtext("./Name") or "").strip().casefold(): {
                f"{owners.get(item.get('Part', ''), '?')}:{item.get('Pin', '?')}"
                for item in net.findall("./Pins/Item")
            }
            for net in container.findall("./Nets/Net")
        }
    if snapshot.board is None:
        raise DocumentError("Schematic/PCB comparison requires design documents")
    owners = {
        component.get("Id", ""): (component.findtext("./RefDes") or "").strip()
        for component in container.findall("./Components/Component")
    }
    return {
        (net.findtext("./Name") or "").strip().casefold(): {
            f"{owners.get(item.get('Comp', ''), '?')}:{item.get('Pad', '?')}"
            for item in net.findall("./Pads/Item")
        }
        for net in container.findall("./Nets/Net")
    }


def compare_schematic_to_pcb(
    schematic: DocumentSnapshot, pcb: DocumentSnapshot
) -> dict[str, Any]:
    if schematic.schematic is None or pcb.board is None:
        raise DocumentError("Expected one schematic snapshot and one PCB snapshot")
    schematic_components = _component_values(schematic)
    pcb_components = _component_values(pcb)
    missing_on_pcb = sorted(set(schematic_components) - set(pcb_components))
    extra_on_pcb = sorted(set(pcb_components) - set(schematic_components))
    value_mismatches = [
        {
            "refdes": refdes,
            "schematic_values": sorted(schematic_components[refdes]),
            "pcb_values": sorted(pcb_components[refdes]),
        }
        for refdes in sorted(set(schematic_components) & set(pcb_components))
        if schematic_components[refdes] != pcb_components[refdes]
    ]
    schematic_nets = _net_endpoints(schematic)
    pcb_nets = _net_endpoints(pcb)
    missing_nets = sorted(set(schematic_nets) - set(pcb_nets))
    extra_nets = sorted(set(pcb_nets) - set(schematic_nets))
    endpoint_mismatches: list[dict[str, Any]] = []
    for net_name in sorted(set(schematic_nets) & set(pcb_nets)):
        if schematic_nets[net_name] == pcb_nets[net_name]:
            continue
        endpoint_mismatches.append(
            {
                "net": net_name,
                "missing_on_pcb": sorted(schematic_nets[net_name] - pcb_nets[net_name]),
                "extra_on_pcb": sorted(pcb_nets[net_name] - schematic_nets[net_name]),
            }
        )
    difference_count = sum(
        (
            len(missing_on_pcb),
            len(extra_on_pcb),
            len(value_mismatches),
            len(missing_nets),
            len(extra_nets),
            len(endpoint_mismatches),
        )
    )
    return {
        "matches": difference_count == 0,
        "difference_count": difference_count,
        "components": {
            "schematic_count": len(schematic_components),
            "pcb_count": len(pcb_components),
            "missing_on_pcb": missing_on_pcb,
            "extra_on_pcb": extra_on_pcb,
            "value_mismatches": value_mismatches,
        },
        "nets": {
            "schematic_count": len(schematic_nets),
            "pcb_count": len(pcb_nets),
            "missing_on_pcb": missing_nets,
            "extra_on_pcb": extra_nets,
            "endpoint_mismatches": endpoint_mismatches,
        },
        "confidence": "medium",
        "limitations": [
            "Endpoint comparison assumes schematic Pin indices map to PCB Pad ids.",
            "Hierarchical aliases and hidden power-net equivalence are not inferred.",
            "Run library pin-to-pad validation before treating endpoint differences as final."
        ],
    }
