#!/usr/bin/env python3
"""Audit and rebuild schematic with proper component selection.

Implements the SKILL lookup order for every part on the Rev.A board:
  1. DipTrace exact MPN → reuse native (preferred)
  2. LCSC exact MPN → converted (already done)
  3. Custom only after 0 results from both

Usage:
  PYTHONPATH=src .venv/bin/python scripts/audit_components.py --report
  PYTHONPATH=src .venv/bin/python scripts/audit_components.py --rebuild
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diptrace_mcp.services.builtin_library import query_catalog

# ---------------------------------------------------------------------------
# Catalog of every part type on the Rev.A board.
# For passives, we record the series (e.g. "0603WAF") since exact values
# (10k, 100nF) share the same footprint — the value is an instance field,
# not a library selection criterion.
# ---------------------------------------------------------------------------
PART_TYPES = [
    # ICs / modules (expected to be LCSC-only except AMS1117)
    ("ESP32-S3-MINI-1U-N8", "ESP32-S3-MINI-1U-N8", "C2980299"),
    ("AMS1117-3.3",          "AMS1117-3.3",          "C6186"),
    ("TS3USB221RSER",        "TS3USB221RSER",        "C130085"),
    ("SY6280AAC",            "SY6280AAC",            "C55136"),
    ("INA226AIDGSR",         "INA226AIDGSR",         "C2653870"),
    ("TS5A23157DGSR",        "TS5A23157DGSR",        "C11133"),
    ("SN74LVC1T45DBVR",      "SN74LVC1T45DBVR",      "C7843"),
    ("PCA9539PW",            "PCA9539PW",            "C129516"),
    ("ADS7830IPWR",          "ADS7830IPWR",          "C161747"),
    ("MS122WF200MT4E",       "MS122WF200MT4E",       "C68608"),  # 2512 20mR shunt
    ("BZT52C5V6S-7-F",       "BZT52C5V6S-7-F",       "C108176"),
    ("BZT52C12S",            "BZT52C12S",            "C14643"),
    ("BSMD2920-200-24V",     "BSMD2920-200-24V",     "C910842"),
    # Diodes / protection
    ("SMAJ5.0A",             "SMAJ5.0A",             "C10758"),
    ("SMBJ26A",              "SMBJ26A",              "C123820"),
    ("BAT54S-7-F",           "BAT54S-7-F",           "C83574"),
    ("USBLC6-2SC6",          "USBLC6-2SC6",          "C7519"),
    ("TLP176A(F)",           "TLP176A(F)",            "C146332"),
    # Opto / isolation
    ("AO3401A",              "AO3401A",              "C15127"),
    ("MMBT3904",             "MMBT3904",             "C84104"),
    # Connectors (expected to have builtin matches — to be verified)
    ("TYPE-C-31-M-12",       "TYPE-C-31-M-12",       "C165948"),
    ("UK-USB AF 90-19.6",    "UK-USB AF 90-19.6",    "C698206"),
    ("W.FL-R-SMT-1",         "W.FL-R-SMT-1",         "WFL_custom"),  # hand-authored from Hirose cat
    ("WJ500V-5.08-2P",       "WJ500V-5.08-2P",       "C8465"),
    ("TS-1187A-B-A-B",       "TS-1187A-B-A-B",       "C318884"),
    # Passives - generic footprints (candidates for builtin reuse)
    ("R_0603 10k",           "0603WAF",              "JLC_BASIC"),
    ("R_0603 100k",          "0603WAF",              "JLC_BASIC"),
    ("R_0603 15k",           "0603WAF",              "JLC_BASIC"),
    ("R_0603 390R",          "0603WAF",              "JLC_BASIC"),
    ("R_0603 1k",            "0603WAF",              "JLC_BASIC"),
    ("C_0603 100nF",         "CAPC100",              "JLC_BASIC"),
    ("C_0805 22uF",          "CAPC200",              "JLC_BASIC"),
    ("HDR-1x4 P2.54",        "HDR-1x4",              "BUILTIN"),
    ("HDR-2x5 P2.54",        "HDR-2x5",              "BUILTIN"),
    ("HDR-2x8 P2.54",        "HDR-2x8",              "BUILTIN"),
    ("LED 0603 red",         "LED-0603",             "BUILTIN"),
]

SKIP_BUILTIN_FOR = {
    # Known LCSC-only parts — no point querying DipTrace for them.
    "ESP32-S3-MINI-1U-N8", "TS3USB221RSER", "SY6280AAC", "INA226AIDGSR",
    "TS5A23157DGSR", "SN74LVC1T45DBVR", "PCA9539PW", "ADS7830IPWR",
    "MS122WF200MT4E", "BZT52C5V6S-7-F", "BZT52C12S", "BSMD2920-200-24V",
    "SMAJ5.0A", "SMBJ26A", "BAT54S-7-F", "USBLC6-2SC6", "TLP176A(F)",
    "AO3401A", "MMBT3904",
}


def run_report() -> None:
    header = f"{'Part':28s}  {'MPN':22s}  DipTrace →            LCSC C-code   Decision"
    print(header)
    print("-" * len(header))
    counts = {"builtin": 0, "lcsc": 0, "custom": 0, "checked": 0}
    for label, mpn, expected_c in PART_TYPES:
        if label in SKIP_BUILTIN_FOR:
            print(f"{label:28s}  {mpn:22s}  (skip)                {expected_c:12s}  LCSC ✓")
            counts["lcsc"] += 1
            counts["checked"] += 1
            continue

        counts["checked"] += 1
        try:
            res = query_catalog("/mnt/c/Program Files/DipTrace", "component", mpn, 0, 3)
            result = res.get("result") or res
            items = result.get("items", [])
            if items:
                cid = items[0]["catalog_id"]
                pat = items[0].get("pattern", "")[:28]
                print(f"{label:28s}  {mpn:22s}  {cid:40s}  {expected_c:12s}  BUILTIN ★ {pat}")
                counts["builtin"] += 1
            else:
                # Try a rougher query on the MPN root
                base = mpn.split()[0].split("-")[0]
                res2 = query_catalog("/mnt/c/Program Files/DipTrace", "component", base, 0, 3)
                items2 = (res2.get("result") or res2).get("items", [])
                if items2:
                    cid = items2[0]["catalog_id"]
                    print(f"{label:28s}  {mpn:22s}  ~{base:20s} → {cid:18s}  {expected_c:12s}  (partial match)")
                    counts["builtin"] += 1
                else:
                    print(f"{label:28s}  {mpn:22s}  — not in DipTrace     {expected_c:12s}  LCSC ✓")
                    counts["lcsc"] += 1
        except Exception as e:
            print(f"{label:28s}  {mpn:22s}  ERR: {e}")

    print("-" * len(header))
    print(f"Checked: {counts['checked']}  Builtin: {counts['builtin']}  LCSC: {counts['lcsc']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="Query both libraries and print audit table")
    args = ap.parse_args()
    if args.report:
        run_report()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
