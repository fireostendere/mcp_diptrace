"""Metadata heuristics: title, part numbers, revision, manufacturer, authority.

Rule: never invent metadata. Fields stay None/[] unless confidently detected.
Part numbers are extracted only from filename/title (high-precision zone);
manufacturer only via an explicit known-name list.
"""
from __future__ import annotations

import re
from pathlib import Path

# Canonical manufacturer names matched case-insensitively against text.
MANUFACTURERS = [
    "Texas Instruments", "Analog Devices", "Linear Technology",
    "Infineon", "STMicroelectronics", "NXP Semiconductors", "Microchip",
    "Renesas", "ON Semiconductor", "onsemi", "Diodes Incorporated",
    "Vishay", "Murata", "TDK", "Espressif", "Nordic Semiconductor",
    "Silicon Labs", "Maxim Integrated", "Rohm", "Toshiba", "Panasonic",
    "Samsung", "Kyocera", "Yageo", "Samtec", "TE Connectivity",
    "Amphenol", "Molex", "Wurth Elektronik", "Bourns", "Littelfuse",
    "Allegro MicroSystems", "Semtech", "Melexis", "AMS OSRAM", "ams",
    "DipTrace", "KiCad", "Cadence", "Altium", "Keysight", "Rigol",
]
_MANUF_RE = re.compile(
    "|".join(re.escape(m) for m in sorted(MANUFACTURERS, key=len, reverse=True)),
    re.IGNORECASE,
)

# Part-number-ish token: letters+digits mix, at least one digit, 4..16 chars.
PART_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7}\d[A-Z0-9]{0,6}(?:-[A-Z0-9]{1,5})?)\b")
PART_BLACKLIST = {
    "PDF", "REV", "USB", "GPIO", "LED", "PCB", "EMC", "EMI", "ESD", "ADC",
    "DAC", "PWM", "SPI", "I2C", "UART", "CAN", "RAM", "ROM", "EEPROM",
    "SMD", "SMT", "BGA", "QFN", "SOIC", "MSOP", "VQFN", "WSON", "LDO",
    "DCDC", "RF", "GND", "VIN", "VOUT", "SW", "BOOT", "EN", "PG", "SS",
    "A1", "B2", "FIG", "TABLE", "NOTE", "MAX", "MIN", "TYP", "UNIT",
}
REVISION_RE = re.compile(
    r"\b(?:rev(?:ision)?\.?\s*[:#]?\s*)([A-Z0-9]{1,4}(?:\.[0-9]+)?)\b", re.I)


def prettify_filename(stem: str) -> str:
    return re.sub(r"[_\-]+", " ", stem).strip()


def guess_title(filename: str | None, blocks: list | None = None,
                pdf_title: str | None = None) -> str:
    if pdf_title and 3 < len(pdf_title) < 200 and "untitled" not in pdf_title.lower():
        return pdf_title.strip()
    # first meaningful block wins (title line usually leads the document)
    if blocks:
        for b in blocks[:8]:
            if b.text.strip():
                return b.text.strip()[:200]
    if filename:
        return prettify_filename(Path(filename).stem)[:200]
    return "Untitled"


def extract_part_numbers(*texts: str) -> list[str]:
    """Confident part-number candidates from the given texts (title/filename)."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for m in PART_RE.finditer(text):
            tok = m.group(1)
            if tok.upper() in PART_BLACKLIST or len(tok) > 16:
                continue
            if tok not in found:
                found.append(tok)
    return found[:8]


def extract_revision(*texts: str) -> str | None:
    seen: list[str] = []
    for text in texts:
        if not text:
            continue
        for m in REVISION_RE.finditer(text):
            val = m.group(1).upper()
            if val not in seen:
                seen.append(val)
    # Only report when unambiguous.
    if len(seen) == 1 and len(seen[0]) <= 4:
        return seen[0]
    return None


def detect_manufacturer(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        m = _MANUF_RE.search(text)
        if m:
            word = m.group(0)
            for canon in MANUFACTURERS:
                if canon.lower() == word.lower():
                    return canon
    return None


def infer_authority(path_or_url: str, kind: str) -> str:
    """Best-effort trust tier from location; override via sources.yaml."""
    haystack = path_or_url.lower().replace("\\", "/")

    if any(d in haystack for d in ("datasheet", "ds_", "_ds", "/lit/ds")):
        return "datasheet"
    if any(d in haystack for d in ("appnote", "application-note", "application_note",
                                   "app_note", "an-", "slva", "sluu", "snva")):
        return "appnote"
    if any(d in haystack for d in ("reference-design", "reference_design", "eval", "evm", "evk")):
        return "reference_design"
    if any(d in haystack for d in ("diptrace.com", "docs.diptrace")):
        return "official_docs"
    if any(d in haystack for d in ("specification", "/spec/", "ipc-", "jedec")):
        return "specification"
    if kind == "youtube":
        return "community"
    return "article"
