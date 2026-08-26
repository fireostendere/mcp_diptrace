#!/usr/bin/env python3
"""Nativeize the Rev.A documents: transplant generated content into
DipTrace-native templates so the real editor parses them cleanly.

Templates (proven to open in the installed DipTrace):
  - schematic: i2c-level-shifter-module.dchxml   (repo, headless-built)
  - pcb:       attiny85-arduino-clone-pcb.dipxml (repo, native gate11 save)

The templates contribute every standard section the 5.3 loader expects
(Settings, Categories, Simulator, pad Terminal stacks, sheet BorderZones...);
our generators contribute the actual design content.
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCH_TPL = ROOT / "i2c-level-shifter-module.dchxml"
PCB_TPL = ROOT / "attiny85-arduino-clone" / "attiny85-arduino-clone-pcb.dipxml"

SCH_MINE = ROOT / "dut-controller-reva.dchxml"
PCB_MINE = ROOT / "dut-controller-reva-pcb.dipxml"

SHEET_NAMES = [
    "SYSTEM_OVERVIEW", "ESP32_CONTROL", "POWER", "USB_DUT",
    "UART", "SWITCHES", "AUX_ADC", "CURRENT_SENSE",
]


def nativeize_schematic() -> None:
    tpl = ET.parse(SCH_TPL).getroot()
    mine = ET.parse(SCH_MINE).getroot()

    tpl.set("Units", "mm")
    tlib = tpl.find("./Library")
    tlib.set("Units", "mm")
    plib_units = tlib.find("./Library")
    if plib_units is not None:
        plib_units.set("Units", "mm")
    mlib = mine.find("./Library")

    # template layout: Library/Library(PatternLibrary){PadStyles,Patterns}, Library/Components
    plib = tlib.find("./Library")
    assert plib is not None, "template pattern library missing"
    for tag in ("PadStyles", "Patterns"):
        el = plib.find(tag)
        if el is not None:
            plib.remove(el)
    tcomps = tlib.find("Components")
    for c in list(tcomps):
        tcomps.remove(c)
    mplib = mlib.find("./Library")
    for tag in ("PadStyles", "Patterns"):
        src_el = mplib.find(tag)
        if src_el is not None:
            plib.append(copy.deepcopy(src_el))
    for c in mlib.findall("./Components/Component"):
        tcomps.append(copy.deepcopy(c))
    cats = tlib.find("Categories")
    if cats is None and mlib.find("Categories") is None:
        pass  # template already carries Categories

    sch = tpl.find("./Schematic")
    msch = mine.find("./Schematic")

    comps_t = sch.find("./Components")
    for c in list(comps_t):
        comps_t.remove(c)
    for p in msch.find("./Components"):
        comps_t.append(copy.deepcopy(p))

    nets_t = sch.find("./Nets")
    if nets_t is None:
        nets_t = ET.SubElement(sch, "Nets")
    for n in list(nets_t):
        nets_t.remove(n)
    mnets = msch.find("./Nets")
    if mnets is not None:
        for n in mnets:
            nets_t.append(copy.deepcopy(n))

    # sheets: keep template sheet Id=0, clone for our sheets 1..N-1
    sheets_t = sch.find("./SheetSettings/Sheets")
    base_sheet = sheets_t.find("./Sheet")
    existing = {s.findtext("./Id") for s in sheets_t}
    for idx, name in enumerate(SHEET_NAMES):
        sid = str(idx)
        if sid in existing:
            s = next(x for x in sheets_t if x.findtext("./Id") == sid)
        else:
            s = copy.deepcopy(base_sheet)
            sheets_t.append(s)
            s.find("./Id").text = sid
        nm = s.find("./Name")
        if nm is None:
            nm = ET.SubElement(s, "Name")
        nm.text = name

    for s in sheets_t.findall("./Sheet"):
        for tag, val in (("SheetWidth", "297"), ("SheetHeight", "210"),
                         ("XPos", "0"), ("YPos", "0"), ("Scale", "1"),
                         ("LeftMargin", "10"), ("RightMargin", "10"),
                         ("TopMargin", "10"), ("BottomMargin", "10")):
            el = s.find(f"./{tag}")
            if el is None:
                el = ET.SubElement(s, tag)
            el.text = val

    active = sch.find("./SheetSettings/ActiveSheet")
    if active is not None:
        active.text = "1"

    # differential pairs / buses containers if we had them
    for tag in ("DifferentialPairs", "Buses"):
        if msch.find(f"./{tag}") is not None and sch.find(f"./{tag}") is None:
            sch.append(ET.Element(tag))

    out = ROOT / "dut-controller-reva-native.dchxml"
    ET.indent(tpl, space="  ")
    out.write_bytes(ET.tostring(tpl, encoding="utf-8", xml_declaration=True))
    print("wrote", out)


def nativeize_pcb() -> None:
    tpl = ET.parse(PCB_TPL).getroot()
    mine = ET.parse(PCB_MINE).getroot()

    tboard = tpl.find("./Board")
    mboard = mine.find("./Board")

    # --- Library (patterns + pad styles) ---------------------------------
    def lib_containers(el):
        plib = el.find("./Library/Library")
        return (
            plib.find("PadStyles"),
            plib.find("Patterns"),
            el.find("./Library/Components"),
        )

    tp, tpat, tcomp = lib_containers(tpl)
    mp, mpat, mcomp = lib_containers(mine)
    # PCB libraries carry patterns/padstyles only (components live in Board)

    for holder in (tp, tpat):
        if holder is not None:
            for c in list(holder):
                holder.remove(c)
    if tcomp is not None:
        for c in list(tcomp):
            tcomp.remove(c)
    for c in (mp or []):
        tp.append(copy.deepcopy(c))
    for c in (mpat or []):
        tpat.append(copy.deepcopy(c))
    for c in (mcomp or []):
        tcomp.append(copy.deepcopy(c))

    # --- Board sections ---------------------------------------------------
    # outline
    tout = tboard.find("./BoardOutline/Points")
    minel = mboard.find("./BoardOutline/Points")
    for c in list(tout):
        tout.remove(c)
    for p_ in minel:
        tout.append(copy.deepcopy(p_))

    # components
    tcomps_b = tboard.find("./Components")
    for c in list(tcomps_b):
        tcomps_b.remove(c)
    for c in mboard.find("./Components"):
        tcomps_b.append(copy.deepcopy(c))

    # nets (incl traces); keep template NetClasses/ViaStyles
    tnets = tboard.find("./Nets")
    for n in list(tnets):
        tnets.remove(n)
    for n in mboard.find("./Nets"):
        tnets.append(copy.deepcopy(n))

    # pours replace; ratlines replace; shapes (board texts) replace
    for tag in ("CopperPours", "Ratlines"):
        th = tboard.find(tag)
        mh = mboard.find(tag)
        for c in list(th):
            th.remove(c)
        if mh is not None:
            for c in mh:
                th.append(copy.deepcopy(c))
    tsh = tboard.find("Shapes")
    if tsh is not None:
        for c in list(tsh):
            tsh.remove(c)
        msh = mboard.find("Shapes")
        if msh is not None:
            for c in msh:
                tsh.append(copy.deepcopy(c))

    out = ROOT / "dut-controller-reva-native.dipxml"
    ET.indent(tpl, space="  ")
    out.write_bytes(ET.tostring(tpl, encoding="utf-8", xml_declaration=True))
    print("wrote", out)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "sch"):
        nativeize_schematic()
    if which in ("both", "pcb"):
        nativeize_pcb()
