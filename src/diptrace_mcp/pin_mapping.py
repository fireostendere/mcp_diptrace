"""Resolve explicit cached symbol-pin/footprint-pad bindings, never pin order guesses."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter

from .xml_document import DipTraceDocument


def part_pin_pad_numbers(
    part: ET.Element, pattern: ET.Element
) -> tuple[dict[int, str], list[str]]:
    """Validate PadId/PadIndex and PadNumber as a pair against one pattern."""
    errors: list[str] = []
    pads: dict[str, str] = {}
    for pad in pattern.findall("./Pads/Pad"):
        identity = pad.get("Id", "")
        number = (pad.findtext("./Number") or pad.get("Number") or "").strip()
        if not identity or not number or identity in pads:
            errors.append("pattern pad identity is incomplete or ambiguous")
        pads[identity] = number
    if errors:
        return {}, errors
    result: dict[int, str] = {}
    for index, pin in enumerate(part.findall("./Pins/Pin")):
        target_id = pin.get("PadId", pin.get("PadIndex"))
        number = (pin.findtext("./PadNumber") or "").strip()
        label = (pin.findtext("./Name") or pin.get("Id") or str(index)).strip()
        if target_id is None or not number:
            errors.append(f"pin {label}: mapping is incomplete")
        elif pin.get("PadId") is not None and pin.get("PadIndex", target_id) != target_id:
            errors.append(f"pin {label}: conflicting PadId/PadIndex")
        elif target_id not in pads:
            errors.append(f"pin {label}: PadId {target_id!r} is absent")
        elif pads[target_id] != number:
            errors.append(
                f"pin {label}: PadNumber {number!r} does not match "
                f"PadId {target_id!r} ({pads[target_id]!r})"
            )
        else:
            result[index] = number
    # Do not partially certify a section with inconsistent library data.
    return ({}, errors) if errors else (result, [])


def schematic_pin_pad_numbers(document: DipTraceDocument) -> dict[tuple[str, int], str]:
    """Resolve only exact embedded cache bindings; missing/ambiguous data stays absent.

    CompTypeN selects a cache component by position; ComponentPart selects its
    section. Schematic Pin indices are section-local, not physical pad IDs.
    External libraries, name similarity and datasheet interpretation belong to
    the caller, not to this resolver.
    """
    if document.kind != "schematic":
        return {}
    libraries = document.root.findall("./Library[@Type='DipTrace-ComponentLibrary']")
    if len(libraries) != 1:
        return {}
    library = libraries[0]
    # Literal identities avoid coercing Unicode digits or oversized integers
    # from untrusted XML into apparently valid native cache indices.
    sections_by_style = {
        f"CompType{index}": {
            str(section_index): section
            for section_index, section in enumerate(component.findall("./Part"))
        }
        for index, component in enumerate(library.findall("./Components/Component"))
        if component.get("Id", str(index)) == str(index)
    }
    patterns: dict[str, list[ET.Element]] = {}
    for pattern in library.findall(
        "./Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern"
    ):
        patterns.setdefault(pattern.get("PatternStyle", ""), []).append(pattern)
    parts = document.container.findall("./Components/Part")
    id_counts = Counter(part.get("Id", "") for part in parts)
    result: dict[tuple[str, int], str] = {}
    for part in parts:
        identity = part.get("Id", "")
        if not identity or id_counts[identity] != 1:
            continue
        section = sections_by_style.get(part.get("ComponentStyle", ""), {}).get(
            part.get("ComponentPart", "")
        )
        if section is None:
            continue
        if len(section.findall("./Pins/Pin")) != len(part.findall("./Pins/Pin")):
            continue
        attachment = section.find("./Pattern")
        style = attachment.get("Style", "") if attachment is not None else ""
        candidates = patterns.get(style, [])
        if not style or len(candidates) != 1:
            continue
        mapping, errors = part_pin_pad_numbers(section, candidates[0])
        if not errors:
            result.update({(identity, index): number for index, number in mapping.items()})
    return result
