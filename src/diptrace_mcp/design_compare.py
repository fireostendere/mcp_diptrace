from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .adapters import DocumentSnapshot
from .errors import DocumentError
from .pin_mapping import schematic_pin_pad_numbers


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


def _net_endpoints(
    snapshot: DocumentSnapshot, issues: list[dict[str, str]]
) -> tuple[dict[str, set[tuple[str, str]]], int]:
    container = snapshot.document.container
    schematic = snapshot.schematic is not None
    source = "schematic" if schematic else "pcb"

    issue_count = 0

    def issue(code: str, object_id: str) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < 200:
            issues.append({"source": source, "code": code, "object_id": object_id})

    owner_tag, item_tag, owner_key, endpoint_key = (
        ("Part", "Pins", "Part", "Pin") if schematic else ("Component", "Pads", "Comp", "Pad")
    )
    owner_elements = container.findall(f"./Components/{owner_tag}")
    ids = Counter(owner.get("Id", "") for owner in owner_elements)
    refs = Counter((owner.findtext("./RefDes") or "").strip().casefold()
                   for owner in owner_elements)
    owners = {}
    for owner in owner_elements:
        identity = owner.get("Id", "")
        refdes = (owner.findtext("./RefDes") or "").strip().casefold()
        if not identity or ids[identity] != 1:
            issue("missing_or_duplicate_owner_id", identity)
            continue
        if not refdes or (not schematic and refs[refdes] != 1):
            issue("missing_or_duplicate_refdes", identity)
            continue
        owners[identity] = (refdes, owner)

    bindings = schematic_pin_pad_numbers(snapshot.document) if schematic else {}
    board_numbers: dict[tuple[str, str], str] = {}
    if not schematic:
        patterns = snapshot.document.root.findall(".//Patterns/Pattern")
        for identity, (_, owner) in owners.items():
            candidates = [pattern for pattern in patterns
                          if pattern.get("PatternStyle") == owner.get("PatternStyle")]
            pads = owner.findall("./Pads/Pad")
            pad_ids = Counter(pad.get("Id", "") for pad in pads)
            for pad in pads:
                pad_id = pad.get("Id", "")
                number = (pad.get("Number") or pad.findtext("./Number") or "").strip()
                if not number and len(candidates) == 1:
                    definitions = [item for item in candidates[0].findall("./Pads/Pad")
                                   if item.get("Id") == pad_id]
                    if len(definitions) == 1:
                        number = (definitions[0].findtext("./Number") or "").strip()
                if not pad_id or pad_ids[pad_id] != 1 or not number:
                    issue("unresolved_pad_number", f"{identity}:{pad_id}")
                else:
                    board_numbers[(identity, pad_id)] = number

    result: dict[str, set[tuple[str, str]]] = defaultdict(set)
    nets = container.findall("./Nets/Net")
    net_ids = Counter(net.get("Id", "") for net in nets)
    membership: dict[tuple[str, str], str] = {}
    raw_membership: dict[tuple[str, str], set[str]] = defaultdict(set)
    for net in nets:
        identity = net.get("Id", "")
        name = (net.findtext("./Name") or "").strip().casefold()
        if not name or name in result:
            issue("missing_or_duplicate_net_name", identity)
        if not identity or net_ids[identity] != 1:
            issue("missing_or_duplicate_net_id", identity)
        endpoints = result[name]  # Preserve all endpoints, never overwrite duplicate names.
        for item in net.findall(f"./{item_tag}/Item"):
            owner_id, pin_id = item.get(owner_key, ""), item.get(endpoint_key, "")
            if owner_id not in owners:
                issue("unresolved_endpoint_owner", f"{identity}:{owner_id}")
                continue
            refdes, owner = owners[owner_id]
            raw_membership[(owner_id, pin_id)].add(identity)
            mapped_number: str | None = None
            if schematic:
                try:
                    index = int(pin_id)
                except ValueError:
                    index = -1
                if 0 <= index < len(owner.findall("./Pins/Pin")):
                    mapped_number = bindings.get((owner_id, index))
            else:
                mapped_number = board_numbers.get((owner_id, pin_id))
            if mapped_number is None:
                issue("unverified_pin_pad_mapping", f"{owner_id}:{pin_id}")
                continue
            endpoint = (refdes, mapped_number)
            if endpoint in endpoints:
                issue("duplicate_endpoint", f"{identity}:{refdes}:{mapped_number}")
            if endpoint in membership and membership[endpoint] != identity:
                issue("endpoint_in_multiple_nets", f"{refdes}:{mapped_number}")
            membership[endpoint] = identity
            endpoints.add(endpoint)
    for owner_id, (_, owner) in owners.items():
        endpoint_tag = "Pin" if schematic else "Pad"
        for index, endpoint_element in enumerate(owner.findall(f"./{item_tag}/{endpoint_tag}")):
            pin_id = str(index) if schematic else endpoint_element.get("Id", "")
            observed = raw_membership.get((owner_id, pin_id), set())
            declared = endpoint_element.get("NetId")
            if declared is not None and observed != ({declared} if declared != "-1" else set()):
                issue("inconsistent_endpoint_netid", f"{owner_id}:{pin_id}")
            if endpoint_element.get("NotConnected") == "Y" and observed:
                issue("explicit_nc_pin_connected", f"{owner_id}:{pin_id}")
    return dict(result), issue_count


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
    issues: list[dict[str, str]] = []
    schematic_nets, schematic_issue_count = _net_endpoints(schematic, issues)
    pcb_nets, pcb_issue_count = _net_endpoints(pcb, issues)
    ambiguity_count = schematic_issue_count + pcb_issue_count
    missing_nets = sorted(set(schematic_nets) - set(pcb_nets))
    extra_nets = sorted(set(pcb_nets) - set(schematic_nets))
    endpoint_mismatches: list[dict[str, Any]] = []
    for net_name in sorted(set(schematic_nets) & set(pcb_nets)):
        if schematic_nets[net_name] == pcb_nets[net_name]:
            continue
        endpoint_mismatches.append(
            {
                "net": net_name,
                "missing_on_pcb": [
                    f"{refdes}:{number}"
                    for refdes, number in sorted(schematic_nets[net_name] - pcb_nets[net_name])
                ],
                "extra_on_pcb": [
                    f"{refdes}:{number}"
                    for refdes, number in sorted(pcb_nets[net_name] - schematic_nets[net_name])
                ],
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
        "matches": difference_count == 0 and not issues,
        "comparison_complete": not issues,
        "comparison_basis": "explicit_physical_pad_numbers",
        "status": "inconclusive" if issues else "different" if difference_count else "matches",
        "ambiguities": issues,
        "ambiguity_count": ambiguity_count,
        "ambiguities_truncated": ambiguity_count > len(issues),
        "sources": {"schematic_sha256": schematic.info.sha256, "pcb_sha256": pcb.info.sha256},
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
        "confidence": "low" if issues else "medium",
        "limitations": [
            "Only explicit cached pin-to-pad bindings and declared PCB pad numbers are compared.",
            "Missing mappings and ambiguous identities prevent a positive match claim.",
            "Hierarchical aliases and hidden power-net equivalence are not inferred.",
            "This compares exported logical membership, not routed copper or native ERC/DRC."
        ],
    }
