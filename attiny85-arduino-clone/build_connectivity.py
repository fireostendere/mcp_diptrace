#!/usr/bin/env python3
"""Apply the reviewed logical nets to the library-backed schematic."""

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.operations import ConnectPinsOperation, SetPinNoConnectOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

PATH = Path(__file__).resolve().parent / "attiny85-arduino-clone.dchxml"
NETS = {
    "VBUS": [("J1", 0), ("U3", 0), ("U3", 9), ("C1", 0), ("R4", 1)],
    "USB_D-": [("J1", 1), ("U2", 4)],
    "USB_D+": [("J1", 2), ("U2", 3)],
    "GND": [
        ("J1", 4),
        ("J1", 5),
        ("U3", 1),
        ("U3", 2),
        ("U3", 7),
        ("C1", 1),
        ("C2", 1),
        ("R2", 1),
        ("U2", 2),
        ("U2", 28),
        ("C3", 1),
        ("C4", 1),
        ("R5", 0),
        ("U1", 3),
        ("C5", 1),
        ("J2", 5),
        ("J3", 7),
    ],
    "+3V3": [
        ("U3", 5),
        ("C2", 0),
        ("R1", 0),
        ("R3", 1),
        ("U2", 5),
        ("U2", 6),
        ("C3", 0),
        ("C4", 0),
        ("U1", 7),
        ("C5", 0),
        ("R6", 1),
        ("J2", 1),
        ("J3", 6),
    ],
    "TPS_L1": [("U3", 8), ("L1", 0)],
    "TPS_L2": [("L1", 1), ("U3", 6)],
    "TPS_FB": [("U3", 3), ("R1", 1), ("R2", 0)],
    "TPS_PG": [("U3", 4), ("R3", 0)],
    "CP2102_VBUS": [("U2", 7), ("R4", 0), ("R5", 1)],
    "CP2102_TXD": [("U2", 25), ("U1", 1), ("J3", 3)],
    "CP2102_RXD": [("U2", 24), ("U1", 2), ("J3", 4)],
    "CP2102_DTR": [("U2", 27), ("C6", 0)],
    "RESET": [("C6", 1), ("U1", 0), ("R6", 0), ("J2", 4), ("J3", 5)],
    "PB0_MOSI": [("U1", 4), ("J2", 3), ("J3", 0)],
    "PB1_MISO": [("U1", 5), ("J2", 0), ("J3", 1)],
    "PB2_SCK": [("U1", 6), ("J2", 2), ("J3", 2)],
}
NO_CONNECT = {
    ("J1", 3),
    ("U2", 0),
    ("U2", 1),
    ("U2", 8),
    ("U2", 9),
    ("U2", 10),
    ("U2", 11),
    ("U2", 12),
    ("U2", 13),
    ("U2", 14),
    ("U2", 15),
    ("U2", 16),
    ("U2", 17),
    ("U2", 18),
    ("U2", 19),
    ("U2", 20),
    ("U2", 21),
    ("U2", 22),
    ("U2", 23),
    ("U2", 26),
}


def main() -> None:
    document = DipTraceDocument.load(PATH, 134_217_728)
    for net in document.root.findall("./Schematic/Nets/Net"):
        name = net.find("./Name")
        if name is not None and name.text == "USB_5V":
            name.text = "VBUS"
    document = DipTraceDocument.from_bytes(
        document.path,
        ET.tostring(document.root, encoding="utf-8", xml_declaration=True),
    )
    snapshot = build_snapshot(document)
    pin_ids = {}
    for pin in snapshot.schematic.pins:
        if pin.refdes.startswith(("PSG", "PWR", "NPI", "NPO")):
            continue
        pin_ids[(pin.refdes, int(pin.xml_id.split(":", 1)[1]))] = pin.stable_id
    assigned = {endpoint for endpoints in NETS.values() for endpoint in endpoints}
    assert assigned.isdisjoint(NO_CONNECT)
    assert assigned | NO_CONNECT == set(pin_ids)
    operations = [
        ConnectPinsOperation(net=net, pins=[{"refdes": refdes, "pin": pin} for refdes, pin in pins])
        for net, pins in NETS.items()
    ]
    operations.append(
        SetPinNoConnectOperation(
            selector=QuerySelector(ids=[pin_ids[endpoint] for endpoint in sorted(NO_CONNECT)]),
            no_connect=True,
        )
    )
    compiled = apply_semantic_operations(document, operations)
    PATH.write_bytes(compiled.raw_bytes)
    print(compiled.document.sha256)


if __name__ == "__main__":
    main()
