#!/usr/bin/env python3
"""Build the DUT Controller Rev.A schematic (dut-controller-reva.dchxml).

Connectivity is authoritative via ConnectPinsOperation (pad-number addressing).
Wires/labels are decoration added later by the readability pass.

Run: PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diptrace_mcp.domain import QuerySelector  # noqa: E402
from diptrace_mcp.operations import (  # noqa: E402
    ConnectPinsOperation,
    PinEndpoint,
    PlacePartOperation,
    SetPinNoConnectOperation,
)
from diptrace_mcp.scaffolding import SchematicScaffold, build_schematic_document  # noqa: E402
from diptrace_mcp.semantic_compiler import apply_semantic_operations  # noqa: E402
from diptrace_mcp.services.builtin_library import _component_definitions  # noqa: E402
from diptrace_mcp.xml_document import DipTraceDocument  # noqa: E402

LIB_DIR = ROOT / ".local" / "reva_lib"
OUT_PATH = ROOT / "dut-controller-reva.dchxml"

SHEETS = [
    "SYSTEM_OVERVIEW",
    "ESP32_CONTROL",
    "POWER",
    "USB_DUT",
    "UART",
    "SWITCHES",
    "AUX_ADC",
    "CURRENT_SENSE",
]

LIB_STEMS = [
    "C2980299", "C165948", "C698206", "C130085", "C55136", "C2653870",
    "C11133", "C15741", "C129516", "C161747", "C7519", "C146332",
    "C83574", "C10758", "C123820", "C20802", "C68608", "C2286",
    "C318884", "C8465", "C108176", "C14643", "C910842",
    "C6186", "C7843", "C15127", "C84104",
    "WFL_custom",
]
STD = "std_parts"

_LIBS: dict[str, tuple[DipTraceDocument, dict[str, dict[str, int]]]] = {}
_EMBEDDED: set[str] = set()
_STYLE_ALIAS: dict[tuple[str, str], str] = {}


def load_libraries() -> None:
    for stem in LIB_STEMS:
        doc = DipTraceDocument.load(LIB_DIR / f"{stem}.elixml", 256 * 1024 * 1024)
        mapping: dict[str, dict[str, int]] = {}
        for comp in doc.root.findall("./Components/Component"):
            part = comp.find("./Part")
            style = comp.get("ComponentStyle", "")
            pins = {
                (pin.findtext("./PadNumber") or pin.findtext("./Name") or "").strip(): int(pin.get("Id", "0"))
                for pin in part.findall("./Pins/Pin")
            }
            mapping[style] = pins
        _LIBS[stem] = (doc, mapping)
    std = DipTraceDocument.load(LIB_DIR / "std_parts.elixml", 64 * 1024 * 1024)
    mapping = {}
    for comp in std.root.findall("./Components/Component"):
        style = comp.get("ComponentStyle", "")
        pins = {
            pin.findtext("./PadNumber").strip(): int(pin.get("Id", "0"))
            for pin in comp.find("./Part").findall("./Pins/Pin")
        }
        mapping[style] = pins
    _LIBS[STD] = (std, mapping)


def _rename_fragment(xml: str, tag: str, attr_map: list[tuple[str, str, str]]) -> str:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    for xpath, attr, old in attr_map:
        for el in root.findall(xpath):
            if el.get(attr) == old:
                el.set(attr, f"{tag}_{old}")
    return ET.tostring(root, encoding="unicode")


def defs_for(stem: str, style: str, target: DipTraceDocument) -> dict:
    """Extract definitions and force globally-unique style names."""
    library = _LIBS[stem][0]
    components = library.root.findall("./Components/Component")
    index = next(i for i, c in enumerate(components) if c.get("ComponentStyle") == style)
    row = {"library_index": index, "name": components[index].findtext("./Part/Name")}
    d = _component_definitions(library, target, row)

    tag = f"{stem}_{style}"
    comp_el = ET.fromstring(d["component_xml"])
    old_comp_style = comp_el.get("ComponentStyle", "")
    comp_el.set("ComponentStyle", tag)
    pat_refs = comp_el.findall("./Part/Pattern")
    old_pat_names = [p.get("Style", "") for p in pat_refs]
    mapping: dict[str, str] = {f"{tag}_{old}": old for old in old_pat_names}
    for p_ref in pat_refs:
        p_ref.set("Style", f"{tag}_{p_ref.get('Style', '')}")

    pad_renames: dict[str, str] = {}
    new_pads: list[str] = []
    seen_pad_names: set[str] = set()
    for xml in d["pad_style_xml"]:
        sel = ET.fromstring(xml)
        old_n = sel.get("Name", "")
        if old_n in seen_pad_names:
            continue
        seen_pad_names.add(old_n)
        new_n = f"{tag}_{old_n}"
        pad_renames[old_n] = new_n
        sel.set("Name", new_n)
        new_pads.append(ET.tostring(sel, encoding="unicode"))
    new_patterns: list[str] = []
    for xml in d["pattern_xml"]:
        pel = ET.fromstring(xml)
        old_name = pel.get("PatternStyle", "")
        pel.set("PatternStyle", f"{tag}_{old_name}")
        for pad in pel.findall("./Pads/Pad"):
            pad.set("Style", pad_renames[pad.get("Style", "")])
        dp = pel.find("./DefPad")
        if dp is not None:
            dp.set("Style", pad_renames[dp.get("Style", "")])
        new_patterns.append(ET.tostring(pel, encoding="unicode"))

    return {
        "component_style": tag,
        "name": d["name"],
        "pin_count": d["pin_count"],
        "component_xml": ET.tostring(comp_el, encoding="unicode"),
        "pattern_xml": new_patterns,
        "pad_style_xml": new_pads,
    }


class Builder:
    def __init__(self, document: DipTraceDocument) -> None:
        self.document = document
        self.ops: list[object] = []
        self.pin_map: dict[str, dict[str, int]] = {}   # refdes -> pad -> index

    def part(self, stem_style: tuple[str, str], refdes: str, value: str,
             sheet: int, x: float, y: float) -> None:
        stem, style = stem_style
        pins = _LIBS[stem][1][style]
        name = next(
            (
                comp.findtext("./Part/Name")
                for comp in _LIBS[stem][0].root.findall("./Components/Component")
                if comp.get("ComponentStyle") == style
            ),
            style,
        )
        if (stem, style) in _STYLE_ALIAS:
            emitted_style = _STYLE_ALIAS[(stem, style)]
            kwargs: dict = {}
        else:
            d = defs_for(stem, style, self.document)
            emitted_style = d["component_style"]
            kwargs = {
                "library_component_xml": d["component_xml"],
                "library_pattern_xml": d["pattern_xml"],
                "library_pad_style_xml": d["pad_style_xml"],
            }
            _STYLE_ALIAS[(stem, style)] = emitted_style
        self.ops.append(
            PlacePartOperation(
                component_style=emitted_style, refdes=refdes, name=name, value=value,
                x=x, y=y, sheet=sheet, pin_count=len(pins), **kwargs,
            )
        )
        if refdes in self.pin_map:
            raise ValueError(f"duplicate refdes {refdes}")
        self.pin_map[refdes] = dict(pins)

    def nets(self, table: dict[str, list[tuple[str, str]]]) -> None:
        for net_name, endpoints in table.items():
            pin_endpoints = []
            for refdes, pad in endpoints:
                if refdes not in self.pin_map:
                    raise KeyError(f"net {net_name}: unknown refdes {refdes}")
                if pad not in self.pin_map[refdes]:
                    raise KeyError(f"net {net_name}: {refdes} has no pad {pad} "
                                   f"(has {sorted(self.pin_map[refdes])})")
                pin_endpoints.append(
                    PinEndpoint(refdes=refdes, pin=self.pin_map[refdes][pad])
                )
            self.ops.append(ConnectPinsOperation(net=net_name, pins=pin_endpoints))


def main() -> None:
    load_libraries()
    document = DipTraceDocument.from_bytes(
        OUT_PATH,
        build_schematic_document(SchematicScaffold(sheet_names=SHEETS)),
    )
    b = Builder(document)

    R = ("std_parts", "COMP_R0603")
    C06 = ("std_parts", "COMP_C0603")
    C08 = ("std_parts", "COMP_C0805")

    # ---------------- Sheet 1: ESP32_CONTROL ---------------------------
    s = 1
    b.part(("C2980299", "C2980299"), "U1", "ESP32-S3-MINI-1U-N8", s, 70.0, 100.0)
    b.part(C06, "C1", "100nF", s, 52.0, 86.0)
    b.part(C06, "C2", "100nF", s, 58.0, 86.0)
    b.part(C08, "C3", "10uF", s, 64.0, 86.0)
    b.part(C08, "C4", "22uF", s, 71.0, 86.0)
    b.part(R, "R1", "10k", s, 84.0, 84.0)
    b.part(C06, "C5", "1uF", s, 90.0, 88.0)
    b.part(("C318884", "C318884"), "SW1", "BOOT", s, 92.0, 104.0)
    b.part(("C318884", "C318884"), "SW2", "RST", s, 102.0, 104.0)
    b.part(("C2286", "C2286"), "LED1", "PWR", s, 40.0, 96.0)
    b.part(R, "R2", "1k", s, 46.0, 96.0)
    b.part((STD, "COMP_HDR_2X5"), "J15", "DEBUG", s, 116.0, 100.0)

    # ---------------- Sheet 2: POWER -----------------------------------
    s = 2
    b.part(("C20802", "C20802"), "F1", "1.5A", s, 14.0, 84.0)
    b.part(("C10758", "C10758"), "D1", "TVS 5V", s, 22.0, 88.0)
    b.part(C08, "C6", "22uF", s, 30.0, 84.0)
    b.part(("C6186", "C6186"), "U2", "AMS1117-3.3", s, 44.0, 88.0)
    b.part(C08, "C7", "22uF", s, 56.0, 84.0)
    b.part(C06, "C8", "100nF", s, 63.0, 84.0)
    # PWR channel 1
    b.part(("C8465", "C8465"), "J11", "PWR1_IN", s, 14.0, 112.0)
    b.part(("C123820", "C123820"), "D2", "TVS 26V", s, 24.0, 114.0)
    b.part(("C910842", "C910842"), "F2", "2A 24V", s, 32.0, 112.0)
    b.part(("C15127", "C15127"), "Q1", "AO3401A", s, 42.0, 112.0)
    b.part(("C84104", "C84104"), "Q3", "MMBT3904", s, 50.0, 118.0)
    b.part(R, "R3", "100k", s, 48.0, 106.0)
    b.part(R, "R4", "470R", s, 56.0, 114.0)
    b.part(("C14643", "C14643"), "D4", "12V", s, 48.0, 124.0)
    b.part(("C8465", "C8465"), "J12", "PWR1_OUT", s, 14.0, 126.0)
    # PWR channel 2
    b.part(("C8465", "C8465"), "J13", "PWR2_IN", s, 14.0, 148.0)
    b.part(("C123820", "C123820"), "D3", "TVS 26V", s, 24.0, 150.0)
    b.part(("C910842", "C910842"), "F3", "2A 24V", s, 32.0, 148.0)
    b.part(("C15127", "C15127"), "Q2", "AO3401A", s, 42.0, 148.0)
    b.part(("C84104", "C84104"), "Q4", "MMBT3904", s, 50.0, 154.0)
    b.part(("C14643", "C14643"), "D5", "12V", s, 48.0, 160.0)
    b.part(R, "R6", "100k", s, 48.0, 142.0)
    b.part(R, "R7", "470R", s, 56.0, 150.0)
    b.part(("C8465", "C8465"), "J14", "PWR2_OUT", s, 14.0, 162.0)

    # ---------------- Sheet 3: USB_DUT ---------------------------------
    s = 3
    b.part(("C165948", "C165948"), "J1", "CONTROL", s, 16.0, 96.0)
    b.part(("C165948", "C165948"), "J2", "UPLINK", s, 16.0, 152.0)
    b.part(("C130085", "C130085"), "U3", "TS3USB221 USB1", s, 74.0, 88.0)
    b.part(("C130085", "C130085"), "U4", "TS3USB221 USB2", s, 74.0, 138.0)
    b.part(("C55136", "C55136"), "U5", "SY6280 VBUS1", s, 106.0, 80.0)
    b.part(("C55136", "C55136"), "U6", "SY6280 VBUS2", s, 106.0, 130.0)
    b.part(("C698206", "C698206"), "J3", "USB1 DUT", s, 142.0, 88.0)
    b.part(("C698206", "C698206"), "J4", "USB2 DUT", s, 142.0, 138.0)
    b.part(("C7519", "C7519"), "D7", "ESD CTRL", s, 34.0, 92.0)
    b.part(("C7519", "C7519"), "D8", "ESD ULNK", s, 34.0, 148.0)
    b.part(("C7519", "C7519"), "D9", "ESD U1", s, 122.0, 94.0)
    b.part(("C7519", "C7519"), "D10", "ESD U2", s, 122.0, 144.0)
    b.part(("C10758", "C10758"), "D11", "TVS VB1", s, 128.0, 72.0)
    b.part(("C10758", "C10758"), "D12", "TVS VB2", s, 128.0, 122.0)
    b.part(("C20802", "C20802"), "F4", "1.5A", s, 98.0, 72.0)
    b.part(("C20802", "C20802"), "F5", "1.5A", s, 98.0, 122.0)
    for i, (ref, y) in enumerate((("R11", 104.0), ("R12", 108.0), ("R13", 160.0), ("R14", 164.0))):
        b.part(R, ref, "5.1k CC", s, 26.0, y)
    b.part(R, "R15", "3.9k ILIM1", s, 112.0, 74.0)
    b.part(R, "R16", "3.9k ILIM2", s, 112.0, 124.0)
    b.part(R, "R17", "100k OE1", s, 66.0, 80.0)
    b.part(R, "R18", "100k OE2", s, 66.0, 130.0)
    b.part(R, "R19", "100k S1", s, 70.0, 96.0)
    b.part(R, "R20", "100k S2", s, 70.0, 146.0)
    b.part(R, "R70", "100k EN1", s, 100.0, 76.0)
    b.part(R, "R21", "100k EN2", s, 100.0, 126.0)
    b.part(C06, "C20", "100nF", s, 80.0, 82.0)
    b.part(C06, "C21", "100nF", s, 80.0, 132.0)
    b.part(C08, "C22", "1uF IN1", s, 102.0, 84.0)
    b.part(C08, "C23", "1uF IN2", s, 102.0, 134.0)

    # ---------------- Sheet 4: UART ------------------------------------
    s = 4
    b.part(("C7843", "C7843"), "U9", "TXSHIFT1", s, 56.0, 86.0)
    b.part(("C7843", "C7843"), "U10", "RXSHIFT1", s, 56.0, 100.0)
    b.part(("C11133", "C11133"), "U11", "GATE1", s, 76.0, 88.0)
    b.part(("C11133", "C11133"), "U12", "POL1", s, 96.0, 88.0)
    b.part(("C7843", "C7843"), "U13", "TXSHIFT2", s, 56.0, 140.0)
    b.part(("C7843", "C7843"), "U14", "RXSHIFT2", s, 56.0, 154.0)
    b.part(("C11133", "C11133"), "U15", "GATE2", s, 76.0, 142.0)
    b.part(("C11133", "C11133"), "U16", "POL2", s, 96.0, 142.0)
    b.part((STD, "COMP_HDR_1X4"), "J5", "UART1", s, 126.0, 90.0)
    b.part((STD, "COMP_HDR_1X4"), "J6", "UART2", s, 126.0, 144.0)
    b.part(R, "R22", "1k VREF1", s, 70.0, 78.0)
    b.part(R, "R23", "100k VREF1", s, 76.0, 78.0)
    b.part(("C108176", "C108176"), "D13", "5V6", s, 82.0, 78.0)
    b.part(R, "R24", "1k VREF2", s, 70.0, 132.0)
    b.part(R, "R25", "100k VREF2", s, 76.0, 132.0)
    b.part(("C108176", "C108176"), "D14", "5V6", s, 82.0, 132.0)
    for i, (ref, y) in enumerate((("R26", 94.0), ("R27", 98.0), ("R28", 148.0), ("R29", 152.0))):
        b.part(R, ref, "10k sink", s, 86.0, y)
    for i, (ref, y) in enumerate((
        ("R30", 80.0), ("R31", 84.0), ("R32", 88.0),      # UART1 POL/TXG/RXG PD
        ("R33", 134.0), ("R34", 138.0), ("R35", 142.0),   # UART2
    )):
        b.part(R, ref, "100k ctrl PD", s, 46.0, y)
    b.part(C06, "C24", "100nF U9U10", s, 62.0, 78.0)
    b.part(C06, "C25", "100nF U13U14", s, 62.0, 132.0)
    b.part(C06, "C26", "100nF sw1", s, 90.0, 78.0)
    b.part(C06, "C27", "100nF sw2", s, 90.0, 132.0)

    # ---------------- Sheet 5: SWITCHES --------------------------------
    s = 5
    b.part(("C129516", "C129516"), "U17", "PCA9539PW", s, 40.0, 100.0)
    for i in range(8):
        x = 78.0 + (i % 4) * 17.0
        y = 78.0 + (i // 4) * 15.0
        b.part(("C146332", "C146332"), f"K{i + 1}", "TLP176A", s, x, y)
        b.part(R, f"R{36 + i}", "390R", s, x + 6.0, y)
    b.part(R, "R44", "10k A0", s, 48.0, 84.0)
    b.part(R, "R45", "10k A1", s, 54.0, 84.0)
    b.part(R, "R46", "4.7k SDA", s, 30.0, 92.0)
    b.part(R, "R47", "4.7k SCL", s, 35.0, 92.0)
    b.part(R, "R48", "390R LED2", s, 60.0, 120.0)
    b.part(("C2286", "C2286"), "LED2", "ACT", s, 66.0, 120.0)
    b.part(C06, "C28", "100nF", s, 46.0, 110.0)
    b.part((STD, "COMP_HDR_2X8"), "J7", "SW1..8", s, 130.0, 96.0)

    # ---------------- Sheet 6: AUX_ADC ---------------------------------
    s = 6
    b.part(("C161747", "C161747"), "U18", "ADS7830IPWR", s, 60.0, 96.0)
    b.part(C06, "C9", "100nF", s, 54.0, 86.0)
    b.part(C06, "C29", "100nF REF", s, 66.0, 86.0)
    divs = [("ADC1", 104.0), ("ADC2", 112.0), ("ADC3", 120.0), ("ADC4", 128.0),
            ("MON5V", 136.0), ("MON3V3", 144.0)]
    for i, (label, y) in enumerate(divs):
        top = f"R{49 + i * 2}"
        bot = f"R{50 + i * 2}"
        cap = f"C{10 + i}"
        b.part(R, top, "15k", s, 40.0, y)
        b.part(R, bot, "10k", s, 47.0, y)
        b.part(C06, cap, "1nF", s, 54.0, y)
        if i < 4:
            b.part(("C83574", "C83574"), f"D{15 + i}", "clamp", s, 61.0, y)
    for i in range(8):
        x = 92.0 + (i % 4) * 16.0
        y = 156.0 + (i // 4) * 12.0
        b.part(R, f"RSER{i + 1}", "100R", s, x, y)
        b.part(("C83574", "C83574"), f"D{19 + i}", "clamp", s, x + 6.0, y)
    b.part((STD, "COMP_HDR_2X5"), "J9", "AUX1", s, 130.0, 156.0)
    b.part((STD, "COMP_HDR_2X5"), "J10", "AUX2", s, 130.0, 172.0)

    # ---------------- Sheet 7: CURRENT_SENSE ---------------------------
    s = 7
    mon_labels = ["USB1", "USB2", "PWR1", "PWR2"]
    for i, label in enumerate(mon_labels):
        b.part(("C2653870", "C2653870"), f"U{19 + i}", f"INA226 {label}", s, 24.0 + i * 26.0, 92.0)
        b.part(("C68608", "C68608"), f"RSH_{label.replace(chr(32), chr(95))}", "20mR", s, 24.0 + i * 26.0, 104.0)
        b.part(C06, f"C{16 + i}", "100nF", s, 24.0 + i * 26.0, 84.0)

    # ------------------------------------------------------------------
    # NETLIST ----------------------------------------------------------
    u1_gnd_pads = ["1", "2", "42", "43", *[str(p) for p in range(46, 66)], "61"]
    N: dict[str, list[tuple[str, str]]] = {}

    def net(name: str, *endpoints: tuple[str, str]) -> None:
        N.setdefault(name, []).extend(endpoints)

    net("GND",
        *[("U1", p) for p in u1_gnd_pads],
        ("C1", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"), ("C5", "2"),
        ("C6", "2"), ("C7", "2"), ("C8", "2"),
        ("SW1", "3"), ("SW1", "4"), ("SW2", "3"), ("SW2", "4"),
        ("LED1", "2"),
        ("J15", "5"), ("J15", "10"),
        ("D1", "2"),
        ("U2", "1"),
        ("J11", "2"), ("J12", "2"), ("J13", "2"), ("J14", "2"),
        ("D2", "2"), ("D3", "2"),
        ("Q3", "2"), ("Q4", "2"),
        ("U3", "5"), ("U4", "5"),
        ("U5", "2"), ("U6", "2"),
        ("J3", "4"), ("J3", "8"), ("J3", "9"), ("J3", "10"), ("J3", "11"), ("J3", "12"),
        ("J4", "4"), ("J4", "8"), ("J4", "9"), ("J4", "10"), ("J4", "11"), ("J4", "12"),
        ("J1", "A1B12"), ("J1", "B1A12"), ("J1", "4"), ("J1", "3"), ("J1", "2"), ("J1", "1"),
        ("J2", "A1B12"), ("J2", "B1A12"), ("J2", "4"), ("J2", "3"), ("J2", "2"), ("J2", "1"),
        ("D7", "2"), ("D8", "2"), ("D9", "2"), ("D10", "2"),
        ("R19", "1"), ("R20", "1"), ("R70", "1"), ("R21", "1"),
        ("D11", "2"), ("D12", "2"),
        ("R11", "2"), ("R12", "2"), ("R13", "2"), ("R14", "2"),
        ("C20", "2"), ("C21", "2"), ("C22", "2"), ("C23", "2"),
        ("U9", "2"), ("U10", "2"), ("U13", "2"), ("U14", "2"),
        ("U10", "5"), ("U14", "5"),
        ("U11", "3"), ("U12", "3"), ("U15", "3"), ("U16", "3"),
        ("D13", "2"), ("D14", "2"),
        ("R23", "2"), ("R25", "2"),
        ("R15", "2"), ("R16", "2"),
        ("R26", "2"), ("R27", "2"), ("R28", "2"), ("R29", "2"),
        ("R30", "1"), ("R31", "1"), ("R32", "1"), ("R33", "1"), ("R34", "1"), ("R35", "1"),
        ("C24", "2"), ("C25", "2"), ("C26", "2"), ("C27", "2"),
        ("J5", "1"), ("J6", "1"),
        ("U17", "12"), ("C28", "2"),
        ("U18", "9"), ("U18", "11"), ("U18", "12"), ("U18", "13"),
        ("U18", "7"), ("U18", "8"),
        ("C29", "2"),
        ("C9", "2"),
        *[("R" + str(50 + i * 2), "2") for i in range(6)],
        *[("C" + str(10 + i), "2") for i in range(6)],
        *[("D" + str(n), "1") for n in range(15, 27)],
        ("U19", "7"), ("U20", "7"), ("U21", "7"), ("U22", "7"),
        ("U19", "1"), ("U19", "2"),
        ("U20", "1"),
        ("U21", "2"),
        ("C16", "2"), ("C17", "2"), ("C18", "2"), ("C19", "2"),
        ("J9", "8"), ("J9", "9"), ("J9", "10"),
        ("J10", "8"), ("J10", "9"), ("J10", "10"),
    )
    net("+3V3",
        ("U1", "3"),
        ("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1"),
        ("R1", "1"), ("R2", "1"),
        ("U2", "2"), ("U2", "4"),
        ("C7", "1"), ("C8", "1"),
        ("U3", "10"), ("U4", "10"),
        ("R17", "1"), ("R18", "1"),
        ("C20", "1"), ("C21", "1"),
        ("U9", "1"), ("U10", "1"), ("U13", "1"), ("U14", "1"),
        ("U9", "5"), ("U13", "5"),
        ("U11", "8"), ("U12", "8"), ("U15", "8"), ("U16", "8"),
        ("C24", "1"), ("C25", "1"), ("C26", "1"), ("C27", "1"),
        ("U17", "24"), ("U17", "3"),
        ("R44", "2"), ("R45", "2"),
        ("R48", "1"), ("R46", "1"), ("R47", "1"),
        ("R36", "1"), ("R37", "1"), ("R38", "1"), ("R39", "1"),
        ("R40", "1"), ("R41", "1"), ("R42", "1"), ("R43", "1"),
        ("C28", "1"),
        ("J15", "1"), ("J9", "1"), ("J10", "1"),
        ("U18", "16"), ("C9", "1"),
        *[("D" + str(n), "2") for n in range(15, 27)],
        ("U19", "6"), ("U20", "6"), ("U21", "6"), ("U22", "6"),
        ("C16", "1"), ("C17", "1"), ("C18", "1"), ("C19", "1"),
        ("U20", "2"), ("U21", "1"), ("U22", "1"), ("U22", "2"),
        ("R59", "1"),
    )
    net("+5V",
        ("F1", "2"), ("D1", "1"), ("C6", "1"), ("U2", "3"),
        ("D7", "4"), ("F4", "1"), ("F5", "1"),
    )

    net("ADC_REF", ("U18", "10"), ("C29", "1"))
    net("LED_PWR_A", ("R2", "2"), ("LED1", "1"))
    net("AMP_ILIM1", ("U5", "3"), ("R15", "1"))
    net("AMP_ILIM2", ("U6", "3"), ("R16", "1"))

    # --- ESP32 core signals ---
    net("I2C_SDA", ("U1", "6"), ("U17", "23"), ("U18", "15"),
        ("U19", "4"), ("U20", "4"), ("U21", "4"), ("U22", "4"), ("R46", "2"))
    net("I2C_SCL", ("U1", "8"), ("U17", "22"), ("U18", "14"),
        ("U19", "5"), ("U20", "5"), ("U21", "5"), ("U22", "5"), ("R47", "2"))

    # control USB
    net("CTRL_DP", ("U1", "24"), ("J1", "A6"), ("J1", "B6"), ("D7", "1"), ("D7", "6"))
    net("CTRL_DN", ("U1", "23"), ("J1", "A7"), ("J1", "B7"), ("D7", "3"), ("D7", "5"))
    net("VBUS_CTRL_RAW", ("J1", "A4B9"), ("J1", "B4A9"), ("F1", "1"))
    net("CC1_RD", ("J1", "A5"), ("R11", "1"))
    net("CC2_RD", ("J1", "B5"), ("R12", "1"))

    # uplink
    net("UP_DP", ("J2", "A6"), ("J2", "B6"), ("D8", "1"), ("D8", "6"),
        ("U3", "1"), ("U4", "1"))
    net("UP_DN", ("J2", "A7"), ("J2", "B7"), ("D8", "3"), ("D8", "5"),
        ("U3", "2"), ("U4", "2"))
    net("CC1_RD2", ("J2", "A5"), ("R13", "1"))
    net("CC2_RD2", ("J2", "B5"), ("R14", "1"))

    # USB port data (COM side to receptacles)
    net("USB1_DP", ("U3", "8"), ("J3", "3"), ("J3", "7"), ("D9", "1"), ("D9", "6"))
    net("USB1_DN", ("U3", "7"), ("J3", "2"), ("J3", "6"), ("D9", "3"), ("D9", "5"))
    net("USB2_DP", ("U4", "8"), ("J4", "3"), ("J4", "7"), ("D10", "1"), ("D10", "6"))
    net("USB2_DN", ("U4", "7"), ("J4", "2"), ("J4", "6"), ("D10", "3"), ("D10", "5"))

    # mux controls
    net("USB1_OE", ("U1", "13"), ("U3", "6"), ("R17", "2"))
    net("USB1_S", ("U1", "14"), ("U3", "9"), ("R19", "2"))
    net("USB2_OE", ("U1", "15"), ("U4", "6"), ("R18", "2"))
    net("USB2_S", ("U1", "16"), ("U4", "9"), ("R20", "2"))

    # VBUS switching port 1
    net("VBUS1_SW", ("RSH_USB1", "2"), ("U5", "5"), ("C22", "1"))
    net("VBUS1_OUT", ("U5", "1"), ("J3", "1"), ("J3", "5"),
        ("D11", "1"), ("D9", "4"), ("U19", "8"), ("U20", "8"))
    net("VBUS1_EN", ("U1", "20"), ("U5", "4"), ("R70", "2"))
    # port 2
    net("VBUS2_SW", ("RSH_USB2", "2"), ("U6", "5"), ("C23", "1"))
    net("VBUS2_OUT", ("U6", "1"), ("J4", "1"), ("J4", "5"),
        ("D12", "1"), ("D10", "4"), ("U22", "8"))
    net("VBUS2_EN", ("U1", "21"), ("U6", "4"), ("R21", "2"))
    net("+5V_FUSED", ("F4", "2"), ("F5", "2"), ("R57", "1"), ("RSH_USB1", "1"), ("RSH_USB2", "1"))

    # PWR channels
    net("PWR1_VIN", ("J11", "1"), ("D2", "1"), ("F2", "1"), ("Q1", "2"), ("R3", "1"), ("D4", "1"))
    net("PWR1_GATE", ("Q1", "1"), ("R3", "2"), ("Q3", "3"), ("D4", "2"))
    net("PWR1_EN", ("U1", "22"), ("R4", "2"))
    net("PWR1_MID", ("Q1", "3"), ("RSH_PWR1", "1"), ("U21", "10"), ("F2", "2"))
    net("PWR1_OUT", ("RSH_PWR1", "2"), ("J12", "1"), ("U21", "9"), ("U21", "8"))
    net("PWR2_VIN", ("J13", "1"), ("D3", "1"), ("F3", "1"), ("Q2", "2"), ("R6", "1"), ("D5", "1"))
    net("PWR2_GATE", ("Q2", "1"), ("R6", "2"), ("Q4", "3"), ("D5", "2"))
    net("PWR2_EN", ("U1", "25"), ("R7", "2"))
    net("PWR2_MID", ("Q2", "3"), ("RSH_PWR2", "1"), ("U22", "10"), ("F3", "2"))
    net("PWR2_OUT", ("RSH_PWR2", "2"), ("J14", "1"), ("U22", "9"))
    net("PWR1_BASE", ("Q3", "1"), ("R4", "1"))
    net("PWR2_BASE", ("Q4", "1"), ("R7", "1"))
    N["VBUS1_SW"].append(("U19", "9"))
    N["+5V_FUSED"].append(("U19", "10"))
    N["VBUS2_SW"].append(("U20", "9"))
    N["+5V_FUSED"].append(("U20", "10"))

    # module support
    net("EN_RC", ("U1", "45"), ("R1", "2"), ("C5", "1"), ("SW2", "1"), ("SW2", "2"), ("J15", "4"))
    net("BOOT_IO0", ("U1", "4"), ("SW1", "1"), ("SW1", "2"), ("J15", "6"))
    net("CONSOLE_TX", ("U1", "39"), ("J15", "2"))
    net("CONSOLE_RX", ("U1", "40"), ("J15", "3"))
    net("DEBUG_IO1", ("U1", "35"), ("J15", "7"))
    net("DEBUG_IO2", ("U1", "37"), ("J15", "9"))
    net("DEBUG_IO8", ("U1", "36"), ("J15", "8"))

    # UART port 1
    net("UART1_POL", ("U1", "9"), ("U12", "1"), ("U12", "5"), ("R30", "2"))
    net("UART1_TXG", ("U1", "10"), ("U11", "1"), ("R31", "2"))
    net("UART1_RXG", ("U1", "11"), ("U11", "5"), ("R32", "2"))
    net("U1TX_MCU", ("U1", "5"), ("U9", "3"))
    net("U1RX_MCU", ("U1", "12"), ("U10", "3"))
    net("U1TX_V", ("U9", "4"), ("U11", "10"))
    net("U1RX_V", ("U10", "4"), ("U11", "6"))
    net("U1_TXGATED", ("U11", "2"), ("U12", "10"))
    net("U1_RXGATED", ("U11", "4"), ("U12", "6"))
    net("U1_LA", ("U12", "2"), ("U12", "7"), ("J5", "3"))
    net("U1_LB", ("U12", "9"), ("U12", "4"), ("J5", "4"))
    net("U1_SINK1", ("U11", "9"), ("R26", "1"))
    net("U1_SINK2", ("U11", "7"), ("R27", "1"))
    net("VREF1_RAW", ("J5", "2"), ("R22", "2"))
    net("VREF1", ("R22", "1"), ("R23", "1"), ("D13", "1"), ("U9", "6"), ("U10", "6"))
    # UART port 2
    net("UART2_POL", ("U1", "17"), ("U16", "1"), ("U16", "5"), ("R33", "2"))
    net("UART2_TXG", ("U1", "18"), ("U15", "1"), ("R34", "2"))
    net("UART2_RXG", ("U1", "19"), ("U15", "5"), ("R35", "2"))
    net("U2TX_MCU", ("U1", "26"), ("U13", "3"))
    net("U2RX_MCU", ("U1", "31"), ("U14", "3"))
    net("U2TX_V", ("U13", "4"), ("U15", "10"))
    net("U2RX_V", ("U14", "4"), ("U15", "6"))
    net("U2_TXGATED", ("U15", "2"), ("U16", "10"))
    net("U2_RXGATED", ("U15", "4"), ("U16", "6"))
    net("U2_LB", ("U16", "9"), ("U16", "4"), ("J6", "4"))
    net("U2_SINK1", ("U15", "9"), ("R28", "1"))
    net("U2_SINK2", ("U15", "7"), ("R29", "1"))
    net("U2_LA", ("U16", "2"), ("U16", "7"), ("J6", "3"))
    net("VREF2_RAW", ("J6", "2"), ("R24", "2"))
    net("VREF2", ("R24", "1"), ("R25", "1"), ("D14", "1"), ("U13", "6"), ("U14", "6"))

    # switches
    for i in range(8):
        net(f"SW{i + 1}_A", (f"K{i + 1}", "3"), ("J7", str(i + 1)))
        net(f"SW{i + 1}_B", (f"K{i + 1}", "4"), ("J7", str(8 + i + 1)))
        net(f"SW_LED{i + 1}", (f"K{i + 1}", "1"), (f"R{36 + i}", "2"))
        net(f"SW_EXP{i + 1}", (f"K{i + 1}", "2"), ("U17", str(4 + i)))
    net("EXP_A0", ("U17", "21"), ("R44", "1"))
    net("EXP_A1", ("U17", "2"), ("R45", "1"))
    net("LED_ACT", ("R48", "2"), ("LED2", "1"))
    net("EXP_LED", ("U17", "20"), ("LED2", "2"))

    # AUX IOs
    aux_gpio = [("28", "IO1"), ("29", "IO2"), ("32", "IO3"), ("33", "IO4")]
    aux2_gpio = [("34", "IO1"), ("27", "IO2"), ("30", "IO3"), ("38", "IO4")]
    for i, (gpio, _) in enumerate(aux_gpio):
        net(f"AUX1_MCU{i + 1}", ("U1", gpio), (f"RSER{i + 1}", "1"))
        net(f"AUX1_IO{i + 1}",
            (f"RSER{i + 1}", "2"),
            ("J9", str(2 + i)),
            ("D" + str(19 + i), "3"),
        )
    for i, (gpio, _) in enumerate(aux2_gpio):
        net(f"AUX2_MCU{i + 1}", ("U1", gpio), (f"RSER{5 + i}", "1"))
        net(f"AUX2_IO{i + 1}",
            (f"RSER{5 + i}", "2"),
            ("J10", str(2 + i)),
            ("D" + str(23 + i), "3"),
        )

    # ADC inputs
    adc_nodes = ["ADC1", "ADC2", "ADC3", "ADC4", "MON5V", "MON3V3"]
    for i, label in enumerate(adc_nodes):
        top = f"R{49 + i * 2}"
        bot = f"R{50 + i * 2}"
        node = f"{label}_DIV"
        src = {"ADC1": ("J9", "6"), "ADC2": ("J9", "7"),
               "ADC3": ("J10", "6"), "ADC4": ("J10", "7"),
               "MON5V": None, "MON3V3": None}
        if src[label] is None:
            continue
        net(f"{label}_RAW", src[label], (top, "1"))
        net(node, (top, "2"), (bot, "1"), ("C" + str(10 + i), "1"),
            ("D" + str(15 + i), "3"), ("U18", str(i + 1)))
    net("MON5V_DIV", ("R57", "2"), ("R58", "1"), ("C14", "1"), ("U18", "5"))
    net("MON3V3_DIV", ("R59", "2"), ("R60", "1"), ("C15", "1"), ("U18", "6"))

    b.nets(N)

    import os

    if os.environ.get("DUT_DEBUG_OPS"):
        working = b.document
        for index, op in enumerate(b.ops):
            try:
                working = apply_semantic_operations(working, [op]).document
            except Exception as exc:
                label = getattr(op, "refdes", getattr(op, "net", "?"))
                raise RuntimeError(f"op #{index} ({label}) failed: {exc}") from exc
        compiled = working
    else:
        compiled = apply_semantic_operations(b.document, b.ops).document

    # ------------------------------------------------------------------
    # No-connect flags ---------------------------------------------------
    from diptrace_mcp.adapters import build_snapshot  # noqa: E402

    snap0 = build_snapshot(compiled)

    # Expected no-connect pins: (refdes, pin_index_within_part)
    EXPECTED_NC: dict[str, set[int]] = {
        "U1": set(),      # filled below from pads {7,41,44}
        "J1": set(),     # filled below
        "J2": {0, 5, 6, 7},  # A4B9,B4A9 (idx?) resolved dynamically below
        "D8": {3},        # VBUS sense pin of uplink ESD
        "U3": {2, 3},
        "U4": {2, 3},
        "U17": {0, *range(12, 19)},
        "U19": {2}, "U20": {2}, "U21": {2}, "U22": {2},  # INA Alert
    }
    # Resolve U1 strap pads to indices via library map inverse
    for pad in ("7", "38", "41", "44"):
        if pad in b.pin_map["U1"]:
            EXPECTED_NC["U1"].add(b.pin_map["U1"][pad])
    EXPECTED_NC["J2"] = {b.pin_map["J2"][p] for p in ("A4B9", "B4A9", "A8", "B8")}
    EXPECTED_NC["J1"] = {b.pin_map["J1"][p] for p in ("A8", "B8")}

    nc_ids: list[str] = []
    unexpected: list[str] = []
    for pin in snap0.schematic.pins:
        if pin.net_name or pin.attributes.get("NotConnected") == "Y":
            continue
        part_idx, pin_idx = pin.xml_id.split(":")
        refdes = next(
            (r for r, m in ((pr.refdes, pr) for pr in snap0.schematic.parts) if False),
            None,
        )
        refdes = pin.refdes
        allowed = EXPECTED_NC.get(refdes, set())
        if int(pin_idx) in allowed:
            nc_ids.append(pin.stable_id)
        else:
            unexpected.append(f"{refdes}:{pin.xml_id}")
    if unexpected:
        for refdes_x in sorted(set(u.split(":")[0] for u in unexpected)):
            m = b.pin_map.get(refdes_x, {})
            inv2 = {v: k for k, v in m.items()}
            idxs = sorted(int(u.rsplit(":", 1)[1]) for u in unexpected if u.startswith(refdes_x + ":"))
            print(f"DEBUG {refdes_x}: indices {idxs} -> pads {[inv2.get(i) for i in idxs]}")
        raise AssertionError(f"unconnected pins not declared NC: {unexpected}")
    if nc_ids:
        compiled = apply_semantic_operations(
            compiled,
            [SetPinNoConnectOperation(selector=QuerySelector(ids=nc_ids), no_connect=True)],
        ).document

    # Every declared endpoint must exist
    for name, endpoints in N.items():
        for refdes, pad in endpoints:
            assert pad in b.pin_map.get(refdes, {}), f"net {name}: bad {refdes}.{pad}"

    OUT_PATH.write_bytes(compiled.raw_bytes)
    print("parts:", len(b.pin_map))
    print("nets:", len(N))
    print("no_connect pins:", len(nc_ids))
    print("sha256:", compiled.sha256)


if __name__ == "__main__":
    main()
