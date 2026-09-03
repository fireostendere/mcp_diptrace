#!/usr/bin/env python3
"""Data-driven schematic builder for Rev.A using only verified library parts.

Lookup order (SKILL §resolve-components):
  1. DipTrace builtin  → place via place_builtin_component catalog id
  2. LCSC converted    → place via place_part from .local/reva_lib/*.elixml
  3. Custom             → last resort, validated against datasheet

All coordinates within A4 landscape usable area: X ∈ [-138, +138], Y ∈ [-95, +95].

Usage:
    PYTHONPATH=src .venv/bin/python scripts/revabuild.py [--dry-run]

Returns JSON of all Part + ConnectPins + Wire operations for MCP commit.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Page geometry ─────────────────────────────────────────────────────────────
# A4 landscape: 297 × 210 mm, margins 10mm each side
SHEET_W, SHEET_H = 297.0, 210.0
MARGIN = 10.0
USABLE_MIN_X = -SHEET_W / 2 + MARGIN  # -138.5
USABLE_MAX_X =  SHEET_W / 2 - MARGIN  # +138.5
USABLE_MIN_Y = -SHEET_H / 2 + MARGIN  # -95.0
USABLE_MAX_Y =  SHEET_H / 2 - MARGIN  # +95.0
GRID = 2.54  # snap grid

# ── Builtin catalog IDs ──────────────────────────────────────────────────────
# Obtained from: query_catalog("/mnt/c/Program Files/DipTrace", "component", <name>)
BUILTIN = {
    "AMS1117-3.3":     {"catalog_id": "builtin-component:390090902:178",  "name": "AMS1117-3.3",      "pins": 4, "pat": "SOT223-4P229_700X180L53X74N"},
    "HDR-1x4":         {"catalog_id": "builtin-component:1525896499:55",  "name": "HDR-1x4",          "pins": 4, "pat": "HDR-1x4"},
    "HDR-2x5":         {"catalog_id": "builtin-component:1525896499:94",  "name": "HDR-2x5",          "pins": 10, "pat": "HDR-2x5"},
    "HDR-2x8":         {"catalog_id": "builtin-component:1525896499:97",  "name": "HDR-2x8",          "pins": 16, "pat": "HDR-2x8"},
    "TB-1X2_5.08":     {"catalog_id": "builtin-component:1322442133:9",   "name": "1546074-2",         "pins": 2, "pat": "TE_TB-1X2_5.08_11X13_SC_A35"},
    "R_0603":          {"catalog_id": "builtin-component:445731070:1",    "name": "0603WAF0000T5E",    "pins": 2, "pat": "RESC160X80X55L30N"},
    "C_0603":          {"catalog_id": "builtin-component:390090902:67",   "name": "0402B102K500NT",    "pins": 2, "pat": "CAPC100X50X55L25N_AD1"},
    "C_0805":          {"catalog_id": "builtin-component:1007963616:8",   "name": "0805B104K500NT",    "pins": 2, "pat": "CAPC200X127X90L50N"},
    "SW_6x6":          {"catalog_id": "builtin-component:133024757:591",  "name": "TS-1187A-B-A-B",    "pins": 4, "pat": "XKB_SMD-SW-4_5.1x5.1x1.5"},
}

# ── LCSC-only components ──────────────────────────────────────────────────────
# These use converted .elixml libraries
LCSC_ONLY = {
    "ESP32-S3-MINI-1U": {"c": "C2980299", "ref": "U1",  "lib": "C2980299", "pins": 41, "desc": "ESP32 module"},
    "TS3USB221":        {"c": "C130085", "ref": "U",   "lib": "C130085", "pins": 10, "desc": "USB 2:1 mux"},
    "SY6280":           {"c": "C55136",  "ref": "U",   "lib": "C55136",  "pins": 8,  "desc": "USB OCP"},
    "INA226":           {"c": "C2653870","ref": "U",   "lib": "C2653870","pins": 10, "desc": "Current sense"},
    "TS5A23157":        {"c": "C11133",  "ref": "U",   "lib": "C11133",  "pins": 8,  "desc": "Dual SPDT"},
    "SN74LVC1T45":      {"c": "C7843",   "ref": "U",   "lib": "C7843",   "pins": 6,  "desc": "Level shifter"},
    "PCA9539":          {"c": "C129516", "ref": "U",   "lib": "C129516", "pins": 24, "desc": "I2C GPIO expander"},
    "ADS7830":          {"c": "C161747", "ref": "U",   "lib": "C161747", "pins": 20, "desc": "8ch 8-bit ADC"},
    "USBLC6-2SC6":      {"c": "C7519",   "ref": "D",   "lib": "C7519",   "pins": 6,  "desc": "USB ESD"},
    "BAT54S":           {"c": "C83574",  "ref": "D",   "lib": "C83574",  "pins": 3,  "desc": "Dual Schottky"},
    "SMAJ5.0A":         {"c": "C10758",  "ref": "D",   "lib": "C10758",  "pins": 2,  "desc": "TVS 5V"},
    "SMBJ26A":          {"c": "C123820", "ref": "D",   "lib": "C123820", "pins": 2,  "desc": "TVS 26V"},
    "BZT52C5V6S":       {"c": "C108176", "ref": "D",   "lib": "C108176", "pins": 2,  "desc": "Zener 5.6V"},
    "BZT52C12":         {"c": "C14643",  "ref": "D",   "lib": "C14643",  "pins": 2,  "desc": "Zener 12V"},
    "BSMD2920-200":     {"c": "C910842", "ref": "F",   "lib": "C910842", "pins": 2,  "desc": "PTC 2A"},
    "TLP176A":          {"c": "C146332", "ref": "U",   "lib": "C146332", "pins": 6,  "desc": "PhotoMOS"},
    "AO3401A":          {"c": "C15127",  "ref": "Q",   "lib": "C15127",  "pins": 3,  "desc": "P-ch MOSFET"},
    "MMBT3904":         {"c": "C84104",  "ref": "Q",   "lib": "C84104",  "pins": 3,  "desc": "NPN BJT"},
    "TYPE-C-31-M-12":   {"c": "C165948", "ref": "J",   "lib": "C165948", "pins": 24, "desc": "USB-C"},
    "UK-USB-AF":        {"c": "C698206", "ref": "J",   "lib": "C698206", "pins": 5,  "desc": "USB-A"},
    "WJ500V-5.08-2P":   {"c": "C8465",   "ref": "J",   "lib": "C8465",   "pins": 2,  "desc": "DC jack 5.08"},
    "MS122WF200":       {"c": "C68608",  "ref": "R",   "lib": "C68608",  "pins": 2,  "desc": "2512 20mR shunt"},
    "WFL-R-SMT-1":      {"c": "WFL_custom","ref":"J",  "lib": "WFL_custom","pins":3, "desc": "Antenna U.FL"},
}

# ── Sheet layout: which components go on which sheet ──────────────────────────
# Sheet 1: ESP32 + support (MCU core)
# Sheet 2: Power (P-FET switches, LDOs, PTCs, TVS, caps, DC jacks)
# Sheet 3: USB + UART + switches (mux, level shifters, photoMOS, connectors)
# Sheet 4: ADC + current sense + GPIO expander

def _grid(x, y):
    """Snap to 2.54mm grid."""
    return (round(x / GRID) * GRID, round(y / GRID) * GRID)

# Sheet 1: MCU core — placed left-to-right, GND below, +3V3 above
SHEET1 = [
    # Component library refdes, builtin/lcsc key, X, Y, angle, value
    ("U1",  "ESP32-S3-MINI-1U",  -100,  0,   0,   "ESP32-S3-MINI-1U-N8"),
    ("C1",  "C_0603",            -75,   30,  0,   "100nF"),
    ("C2",  "C_0603",            -68,   30,  0,   "100nF"),
    ("C3",  "C_0603",            -61,   30,  0,   "100nF"),
    ("C4",  "C_0603",            -54,   30,  0,   "100nF"),
    ("C5",  "C_0603",            -47,   30,  0,   "100nF"),
    ("C6",  "C_0603",            -40,   30,  0,   "100nF"),
    ("C7",  "C_0603",            -33,   30,  0,   "100nF"),
    ("C8",  "C_0603",            -26,   30,  0,   "100nF"),
    ("R1",  "R_0603",            -100,  40,  90,  "15k"),
    ("R2",  "R_0603",            -100,  50,  90,  "100k"),
    ("R3",  "R_0603",            -100,  60,  90,  "10k"),
    ("R4",  "R_0603",            -90,   60,  90,  "10k"),
    ("D1",  "BAT54S",            -90,   50,  0,   "BAT54S"),
    ("D2",  "BAT54S",            -90,   40,  0,   "BAT54S"),
    ("Y1",  "R_0603",            -100,  70,  0,   "32.768kHz"),
    ("J1",  "HDR-1x4",           40,    0,   0,   "DEBUG_UART"),
    ("J2",  "HDR-2x5",           60,    0,   0,   "JTAG"),
    ("J3",  "HDR-1x4",           40,    -30, 0,   "GPIO_EXP"),
    ("U14", "USBLC6-2SC6",       -80,   0,   0,   "USBLC6-2SC6"),
]

# Sheet 2: Power — left-to-right flow
SHEET2 = [
    ("J4",  "WJ500V-5.08-2P",    -120,  40,  0,   "DC_J1"),
    ("J5",  "WJ500V-5.08-2P",    -120,  20,  0,   "DC_J2"),
    ("J6",  "WJ500V-5.08-2P",    -120,  0,   0,   "DC_J3"),
    ("J7",  "WJ500V-5.08-2P",    -120,  -20, 0,   "DC_J4"),
    ("F1",  "BSMD2920-200",      -100,  40,  0,   "PTC_2A"),
    ("F2",  "BSMD2920-200",      -100,  20,  0,   "PTC_2A"),
    ("F3",  "BSMD2920-200",      -100,  0,   0,   "PTC_2A"),
    ("F4",  "BSMD2920-200",      -100,  -20, 0,   "PTC_2A"),
    ("D3",  "SMBJ26A",           -85,   40,  90,  "SMBJ26A"),
    ("D4",  "SMAJ5.0A",          -85,   20,  90,  "SMAJ5.0A"),
    ("D5",  "SMAJ5.0A",          -85,   0,   90,  "SMAJ5.0A"),
    ("Q1",  "AO3401A",           -70,   40,  0,   "P-FET_1"),
    ("Q2",  "AO3401A",           -70,   20,  0,   "P-FET_2"),
    ("Q3",  "AO3401A",           -70,   0,   0,   "P-FET_3"),
    ("Q4",  "AO3401A",           -70,   -20, 0,   "P-FET_4"),
    ("U2",  "SY6280",            -50,   40,  0,   "OCP_1"),
    ("U3",  "SY6280",            -50,   20,  0,   "OCP_2"),
    ("U4",  "SY6280",            -50,   0,   0,   "OCP_3"),
    ("U5",  "AMS1117-3.3",       -30,   0,   0,   "LDO_3V3"),
    ("C9",  "C_0603",            -30,   20,  0,   "100nF"),
    ("C10", "C_0805",            -20,   20,  0,   "22uF"),
    ("R5",  "R_0603",            -50,   60,  90,  "10k"),
    ("R6",  "R_0603",            -40,   60,  90,  "10k"),
    ("R7",  "R_0603",            -30,   60,  90,  "10k"),
]

# Sheet 3: USB × 2, UART, PhotoMOS
SHEET3 = [
    ("J8",  "TYPE-C-31-M-12",    -120,  30,  0,   "USB-C_DUT1"),
    ("J9",  "TYPE-C-31-M-12",    -120,  -30, 0,   "USB-C_DUT2"),
    ("J10", "UK-USB-AF",         -120,  60,  0,   "USB-A_UPLINK"),
    ("D6",  "USBLC6-2SC6",       -100,  60,  0,   "ESD_UPLINK"),
    ("D7",  "USBLC6-2SC6",       -100,  30,  0,   "ESD_DUT1"),
    ("D8",  "USBLC6-2SC6",       -100,  -30, 0,   "ESD_DUT2"),
    ("U6",  "TS3USB221",         -70,   30,  0,   "MUX_USB1"),
    ("U7",  "TS3USB221",         -70,   -30, 0,   "MUX_USB2"),
    ("U12", "SN74LVC1T45",       -40,   50,  0,   "LS_UART1"),
    ("U13", "SN74LVC1T45",       -40,   30,  0,   "LS_UART2"),
    ("U15", "TLP176A",           0,     50,  0,   "PHOTO_1"),
    ("U16", "TLP176A",           0,     30,  0,   "PHOTO_2"),
    ("U17", "TLP176A",           0,     10,  0,   "PHOTO_3"),
    ("U18", "TLP176A",           0,     -10, 0,   "PHOTO_4"),
    ("U19", "TLP176A",           0,     -30, 0,   "PHOTO_5"),
    ("U20", "TLP176A",           0,     -50, 0,   "PHOTO_6"),
    ("U21", "TLP176A",           0,     -70, 0,   "PHOTO_7"),
    ("U22", "TLP176A",           20,    50,  0,   "PHOTO_8"),
    ("U16", "PCA9539",           40,    30,  0,   "GPIO_EXP"),
    ("J11", "HDR-2x5",           60,    30,  0,   "DUT_HDR1"),
    ("J12", "HDR-2x5",           60,    -30, 0,   "DUT_HDR2"),
    ("R8",  "R_0603",            -70,   50,  90,  "10k"),
    ("R9",  "R_0603",            -60,   50,  90,  "10k"),
    ("R10", "R_0603",            40,    50,  90,  "10k"),
    ("R11", "R_0603",            40,    60,  90,  "10k"),
    ("D9",  "BAT54S",            -100,  0,   0,   "SW_DUT1"),
    ("D10", "BAT54S",            -100,  -10, 0,   "SW_DUT2"),
    ("J13", "HDR-2x8",           80,    0,   0,   "AUX_HDR"),
    ("J14", "HDR-1x4",           80,    40,  0,   "ISP_HDR"),
    ("J15", "HDR-1x4",           80,    -40, 0,   "SAFE_HDR"),
    ("J16", "WFL-R-SMT-1",       60,    60,  0,   "ANT"),
]

# Sheet 4: INA226 × 4, ADS7830, ferrite, NTC
SHEET4 = [
    ("U24", "INA226",             -120,  30,  0,   "INA_1"),
    ("U25", "INA226",             -120,  0,   0,   "INA_2"),
    ("U26", "INA226",             -120,  -30, 0,   "INA_3"),
    ("U27", "INA226",             -80,   0,   0,   "INA_4"),
    ("R12", "R_0603",             -130,  30,  90,  "10k"),
    ("R13", "R_0603",             -130,  0,   90,  "10k"),
    ("R14", "R_0603",             -130,  -30, 90,  "10k"),
    ("R15", "R_0603",             -90,   0,   90,  "10k"),
    ("R16", "MS122WF200",         -130,  50,  90,  "SHUNT_1"),
    ("R17", "MS122WF200",         -130,  20,  90,  "SHUNT_2"),
    ("R18", "MS122WF200",         -130,  -10, 90,  "SHUNT_3"),
    ("R19", "MS122WF200",         -90,   20,  90,  "SHUNT_4"),
    ("U23", "ADS7830",            -50,   0,   0,   "ADC"),
    ("R20", "R_0603",             -60,   30,  90,  "10k"),
    ("R21", "R_0603",             -50,   30,  90,  "10k"),
    ("R22", "R_0603",             -40,   30,  90,  "10k"),
    ("R23", "R_0603",             -30,   30,  90,  "10k"),
    ("R24", "R_0603",             -60,   -30, 90,  "4.7k"),
    ("R25", "R_0603",             -50,   -30, 90,  "4.7k"),
    ("R26", "R_0603",             -40,   -30, 90,  "4.7k"),
    ("R27", "R_0603",             -30,   -30, 90,  "4.7k"),
    ("R28", "R_0603",             -20,   30,  90,  "100k"),
    ("C11", "C_0603",             -110,  30,  0,   "100nF"),
    ("C12", "C_0603",             -110,  0,   0,   "100nF"),
    ("C13", "C_0603",             -110,  -30, 0,   "100nF"),
    ("C14", "C_0603",             -70,   0,   0,   "100nF"),
    ("C15", "C_0603",             -50,   -20, 0,   "100nF"),
    ("C16", "C_0603",             -20,   -20, 0,   "100nF"),
    ("D11", "BZT52C5V6S",        -90,   -20, 90,  "Zener_5V6"),
    ("D12", "BZT52C12",           -70,   -20, 90,  "Zener_12V"),
    ("R29", "R_0603",             30,    0,   90,  "10k"),
    ("R30", "R_0603",             30,    10,  90,  "10k"),
    ("R31", "R_0603",             30,    20,  90,  "10k"),
    ("R32", "R_0603",             30,    30,  90,  "10k"),
    ("R33", "R_0603",             30,    -10, 90,  "10k"),
    ("R34", "R_0603",             30,    -20, 90,  "10k"),
    ("R35", "R_0603",             30,    -30, 90,  "10k"),
    ("R36", "R_0603",             30,    -40, 90,  "10k"),
    ("J17", "HDR-2x8",            50,    0,   0,   "ADC_HDR"),
    ("D13", "BZT52C5V6S",        -20,   -30, 90,  "Zener_5V6_b"),
    ("D14", "BZT52C12",           -20,   -40, 90,  "Zener_12V_b"),
    ("F5",  "R_0603",             30,    -50, 0,   "Ferrite_100R"),
]


def build_operations():
    """Return list of (tool, args) tuples for MCP commit."""
    ops = []
    lib_dir = ROOT / ".local" / "reva_lib"
    sheets_data = [
        (0, "MCU",          SHEET1),
        (1, "POWER",        SHEET2),
        (2, "IO",           SHEET3),
        (3, "ADC_CURRENT",  SHEET4),
    ]

    for sheet_idx, sheet_name, components in sheets_data:
        for refdes, lib_key, x, y, angle, value in components:
            x, y = _grid(x, y)
            if lib_key in BUILTIN:
                b = BUILTIN[lib_key]
                ops.append(("place_builtin", {
                    "component": b["catalog_id"],
                    "refdes": refdes,
                    "x": x, "y": y,
                    "sheet": sheet_idx,
                    "value": value,
                    "lib_key": lib_key,
                    "angle_deg": angle,
                }))
            elif lib_key in LCSC_ONLY:
                lc = LCSC_ONLY[lib_key]
                ops.append(("place_part", {
                    "component_style": lc["lib"],
                    "refdes": refdes,
                    "x": x, "y": y,
                    "sheet": sheet_idx,
                    "value": value,
                    "lib_key": lib_key,
                    "pin_count": lc["pins"],
                    "angle_deg": angle,
                }))
            else:
                print(f"WARNING: {refdes} lib_key={lib_key} not found in BUILTIN or LCSC_ONLY")

    return ops


def main():
    ops = build_operations()
    print(f"Total place operations: {len(ops)}")
    # Count by type
    builtin = sum(1 for t, _ in ops if t == "place_builtin")
    lcsc = sum(1 for t, _ in ops if t == "place_part")
    print(f"  builtin: {builtin}  |  LCSC: {lcsc}")
    # Validate coordinates
    out = 0
    for t, a in ops:
        x, y = a["x"], a["y"]
        if not (USABLE_MIN_X <= x <= USABLE_MAX_X and USABLE_MIN_Y <= y <= USABLE_MAX_Y):
            out += 1
            print(f"  OUTSIDE: {a['refdes']} at ({x},{y}) sheet={a['sheet']}")
    print(f"  outside usable area: {out}")
    # Dump JSON for MCP tool consumption
    Path("dut_controller_rev_a_operations.json").write_text(
        json.dumps(ops, indent=2, ensure_ascii=False)
    )
    print("wrote dut_controller_rev_a_operations.json")


if __name__ == "__main__":
    main()
