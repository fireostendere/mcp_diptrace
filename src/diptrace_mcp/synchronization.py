from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from .domain import StrictModel
from .errors import AmbiguousSelectorError, DocumentError, EditError, ObjectNotFoundError
from .geometry import to_mm
from .operations import SyncSchematicToPcbOperation
from .xml_document import DipTraceDocument


class PinPadAssignment(StrictModel):
    part_id: str = Field(min_length=1, max_length=512)
    pin: int = Field(ge=0, le=100_000)
    pad_number: str = Field(min_length=1, max_length=256)


class ComponentSyncMapping(StrictModel):
    refdes: str = Field(min_length=1, max_length=256)
    pattern_style: str | None = Field(default=None, min_length=1, max_length=1_000)
    pad_numbers: list[str] = Field(default_factory=list, max_length=10_000)
    pin_map: list[PinPadAssignment] = Field(default_factory=list, max_length=100_000)
    x: float | None = Field(default=None, allow_inf_nan=False)
    y: float | None = Field(default=None, allow_inf_nan=False)
    side: Literal["Top", "Bottom"] = "Top"

    @model_validator(mode="after")
    def validate_mapping(self) -> ComponentSyncMapping:
        numbers = [item.strip() for item in self.pad_numbers]
        if any(not item for item in numbers):
            raise ValueError("pad_numbers cannot contain empty values")
        if len({item.casefold() for item in numbers}) != len(numbers):
            raise ValueError("pad_numbers must be unique")
        keys = [(item.part_id, item.pin) for item in self.pin_map]
        if len(set(keys)) != len(keys):
            raise ValueError("pin_map contains duplicate part/pin assignments")
        return self


class SyncPlacement(StrictModel):
    origin_x: float | None = Field(default=None, allow_inf_nan=False)
    origin_y: float | None = Field(default=None, allow_inf_nan=False)
    pitch_x: float = Field(default=10.0, gt=0.0, allow_inf_nan=False)
    pitch_y: float = Field(default=10.0, gt=0.0, allow_inf_nan=False)
    columns: int = Field(default=8, ge=1, le=1_000)


@dataclass(slots=True)
class SyncPlan:
    operation: SyncSchematicToPcbOperation
    warnings: list[str]
    limitations: list[str]


def _text(element: ET.Element, child: str) -> str:
    return (element.findtext(child) or "").strip()


def _additional_fields(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in element.findall("./AddFields/AddField"):
        name = _text(field, "Name")
        if name:
            result[name] = _text(field, "Text")
    return result


def _pattern_elements(document: DipTraceDocument) -> list[ET.Element]:
    if document.source_type == "DipTrace-PatternLibrary":
        return document.root.findall("./Patterns/Pattern")
    return document.root.findall(".//Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern")


def _pad_style_elements(document: DipTraceDocument) -> list[ET.Element]:
    if document.source_type == "DipTrace-PatternLibrary":
        return document.root.findall("./PadStyles/PadStyle")
    return document.root.findall(
        ".//Library[@Type='DipTrace-PatternLibrary']/PadStyles/PadStyle"
    )


def _pattern_style(pattern: ET.Element) -> str:
    return (pattern.get("PatternStyle") or pattern.get("Style") or "").strip()


def _pattern_pad_numbers(pattern: ET.Element) -> list[str]:
    result: list[str] = []
    for index, pad in enumerate(pattern.findall("./Pads/Pad")):
        number = (pad.get("Number") or pad.findtext("./Number") or pad.get("Id") or "").strip()
        result.append(number or str(index + 1))
    return result


def _referenced_pad_styles(pattern: ET.Element) -> set[str]:
    result: set[str] = set()
    default = pattern.find("./DefPad")
    if default is not None and default.get("Style"):
        result.add(str(default.get("Style")))
    for pad in pattern.findall("./Pads/Pad"):
        if pad.get("Style"):
            result.add(str(pad.get("Style")))
    return result


def _existing_components(pcb: DipTraceDocument) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for component in pcb.container.findall("./Components/Component"):
        refdes = _text(component, "RefDes")
        key = refdes.casefold()
        if not key:
            continue
        if key in result:
            raise AmbiguousSelectorError(f"PCB contains duplicate RefDes: {refdes}")
        result[key] = component
    return result


def _board_origin(pcb: DipTraceDocument, placement: SyncPlacement) -> tuple[float, float]:
    points = pcb.container.findall("./BoardOutline/Points/Point")
    xs = [to_mm(float(item.get("X", "0")), pcb.units) for item in points]
    ys = [to_mm(float(item.get("Y", "0")), pcb.units) for item in points]
    default_x = min(xs) + 5.0 if xs else 5.0
    default_y = min(ys) + 5.0 if ys else 5.0
    return (
        placement.origin_x if placement.origin_x is not None else default_x,
        placement.origin_y if placement.origin_y is not None else default_y,
    )


def _inferred_pattern(part: ET.Element) -> str | None:
    attached_pattern = part.find("./Pattern")
    candidates = [
        part.get("PatternStyle"),
        attached_pattern.get("Style") if attached_pattern is not None else None,
    ]
    fields = {key.casefold(): value for key, value in _additional_fields(part).items()}
    candidates.extend(
        fields.get(key) for key in ("patternstyle", "pattern", "footprint", "package")
    )
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def build_sync_plan(
    schematic: DipTraceDocument,
    pcb: DipTraceDocument,
    *,
    mappings: list[ComponentSyncMapping] | None = None,
    placement: SyncPlacement | None = None,
    pattern_documents: list[DipTraceDocument] | None = None,
    update_existing_properties: bool = True,
    create_ratlines: bool = True,
    allow_reconnect: bool = False,
) -> SyncPlan:
    if schematic.kind != "schematic" or pcb.kind != "pcb":
        raise DocumentError("sync_schematic_to_pcb requires schematic and PCB documents")
    placement = placement or SyncPlacement()
    mapping_by_refdes: dict[str, ComponentSyncMapping] = {}
    for provided_mapping in mappings or []:
        key = provided_mapping.refdes.casefold()
        if key in mapping_by_refdes:
            raise AmbiguousSelectorError(
                f"Duplicate component mapping: {provided_mapping.refdes}"
            )
        mapping_by_refdes[key] = provided_mapping

    parts_by_refdes: dict[str, list[ET.Element]] = {}
    parts_by_id: dict[str, ET.Element] = {}
    for part in schematic.container.findall("./Components/Part"):
        refdes = _text(part, "RefDes")
        if not refdes:
            raise EditError("Every synchronized schematic part requires a RefDes")
        parts_by_refdes.setdefault(refdes.casefold(), []).append(part)
        part_id = part.get("Id", "")
        if not part_id or part_id in parts_by_id:
            raise EditError(f"Schematic part has missing or duplicate Id: {part_id!r}")
        parts_by_id[part_id] = part
    if not parts_by_refdes:
        raise ObjectNotFoundError("Schematic contains no parts to synchronize")
    unknown_mappings = sorted(set(mapping_by_refdes) - set(parts_by_refdes))
    if unknown_mappings:
        raise ObjectNotFoundError(
            "Mappings reference schematic RefDes values that do not exist",
            details={"refdes": unknown_mappings},
        )

    existing = _existing_components(pcb)
    source_documents = [pcb, *(pattern_documents or [])]
    patterns: dict[str, tuple[DipTraceDocument, ET.Element]] = {}
    pad_styles: dict[str, tuple[DipTraceDocument, ET.Element]] = {}
    for document in source_documents:
        if document is not pcb and document.units != pcb.units:
            raise EditError(
                "Pattern-library units must match PCB units for lossless subtree copying",
                details={"pcb_units": pcb.units, "library_units": document.units},
            )
        for pattern in _pattern_elements(document):
            style = _pattern_style(pattern)
            if style:
                key = style.casefold()
                existing_pattern_entry = patterns.get(key)
                if (
                    existing_pattern_entry is not None
                    and existing_pattern_entry[0] is not pcb
                    and document is not pcb
                    and ET.tostring(existing_pattern_entry[1]) != ET.tostring(pattern)
                ):
                    raise AmbiguousSelectorError(
                        f"Conflicting pattern definitions found for {style}"
                    )
                patterns.setdefault(key, (document, pattern))
        for style_element in _pad_style_elements(document):
            name = (style_element.get("Name") or "").strip()
            if name:
                key = name.casefold()
                existing_pad_style_entry = pad_styles.get(key)
                if (
                    existing_pad_style_entry is not None
                    and existing_pad_style_entry[0] is not pcb
                    and document is not pcb
                    and ET.tostring(existing_pad_style_entry[1])
                    != ET.tostring(style_element)
                ):
                    raise AmbiguousSelectorError(
                        f"Conflicting pad-style definitions found for {name}"
                    )
                pad_styles.setdefault(key, (document, style_element))

    origin_x, origin_y = _board_origin(pcb, placement)
    component_specs: list[dict[str, Any]] = []
    pin_to_pad: dict[tuple[str, int], tuple[str, str]] = {}
    copied_patterns: dict[str, str] = {}
    copied_pad_styles: dict[str, str] = {}
    warnings: list[str] = []

    for component_index, key in enumerate(sorted(parts_by_refdes)):
        parts = sorted(
            parts_by_refdes[key],
            key=lambda item: (int(item.get("PartNumber", "0")), item.get("Id", "")),
        )
        refdes = _text(parts[0], "RefDes")
        mapping = mapping_by_refdes.get(key)
        target = existing.get(key)
        pattern_style = (
            mapping.pattern_style
            if mapping is not None and mapping.pattern_style is not None
            else target.get("PatternStyle")
            if target is not None
            else _inferred_pattern(parts[0])
        )
        if not pattern_style:
            raise EditError(
                f"Pattern mapping is required for new PCB component {refdes}",
                details={"refdes": refdes, "hint": "supply component_mappings.pattern_style"},
            )
        pattern_entry = patterns.get(pattern_style.casefold())
        if mapping is not None and mapping.pad_numbers:
            pad_numbers = list(mapping.pad_numbers)
        elif target is not None:
            pad_numbers = [
                (pad.get("Number") or pad.get("Id") or "").strip()
                for pad in target.findall("./Pads/Pad")
            ]
        elif pattern_entry is not None:
            pad_numbers = _pattern_pad_numbers(pattern_entry[1])
        elif len(parts) == 1:
            pad_numbers = [str(index + 1) for index, _ in enumerate(parts[0].findall("./Pins/Pin"))]
            warnings.append(
                f"{refdes}: pad numbers were inferred from single-part pin order because "
                f"pattern {pattern_style!r} was not available"
            )
        else:
            raise EditError(
                f"Pad numbers are required for multi-part component {refdes}",
                details={"refdes": refdes},
            )
        if not pad_numbers:
            raise EditError(f"PCB component {refdes} has no pads")
        if len({item.casefold() for item in pad_numbers}) != len(pad_numbers):
            raise EditError(f"PCB component {refdes} has duplicate pad numbers")

        explicit_pin_map = {
            (item.part_id, item.pin): item.pad_number
            for item in (mapping.pin_map if mapping is not None else [])
        }
        if explicit_pin_map:
            for (part_id, pin_index), pad_number in explicit_pin_map.items():
                if part_id not in {part.get("Id", "") for part in parts}:
                    raise EditError(f"Pin map for {refdes} references foreign part {part_id}")
                pins = parts_by_id[part_id].findall("./Pins/Pin")
                if pin_index >= len(pins):
                    raise EditError(f"Pin map for {refdes} references missing pin {pin_index}")
                if pad_number.casefold() not in {item.casefold() for item in pad_numbers}:
                    raise EditError(
                        f"Pin map for {refdes} references missing pad {pad_number}"
                    )
                pin_to_pad[(part_id, pin_index)] = (refdes, pad_number)
        elif len(parts) == 1:
            pins = parts[0].findall("./Pins/Pin")
            if len(pins) > len(pad_numbers):
                raise EditError(
                    f"Component {refdes} has more schematic pins than PCB pads",
                    details={"pins": len(pins), "pads": len(pad_numbers)},
                )
            for pin_index in range(len(pins)):
                pin_to_pad[(parts[0].get("Id", ""), pin_index)] = (
                    refdes,
                    pad_numbers[pin_index],
                )

        fields: dict[str, str] = {}
        for part in parts:
            for field_name, field_value in _additional_fields(part).items():
                field_previous = fields.setdefault(field_name, field_value)
                if field_previous != field_value:
                    warnings.append(
                        f"{refdes}: field {field_name!r} differs between units; first value kept"
                    )
        if target is not None:
            x = to_mm(float(target.get("X", "0")), pcb.units)
            y = to_mm(float(target.get("Y", "0")), pcb.units)
            side = target.get("Side", "Top")
        else:
            column = component_index % placement.columns
            row = component_index // placement.columns
            x = (
                mapping.x
                if mapping is not None and mapping.x is not None
                else origin_x + column * placement.pitch_x
            )
            y = (
                mapping.y
                if mapping is not None and mapping.y is not None
                else origin_y + row * placement.pitch_y
            )
            side = mapping.side if mapping is not None else "Top"
        component_specs.append(
            {
                "refdes": refdes,
                "name": _text(parts[0], "Name"),
                "value": _text(parts[0], "Value"),
                "pattern_style": pattern_style,
                "x": x,
                "y": y,
                "side": side,
                "pad_numbers": pad_numbers,
                "fields": fields,
            }
        )

        target_has_pattern = patterns.get(pattern_style.casefold(), (None, None))[0] is pcb
        if target is None and not target_has_pattern and pattern_entry is not None:
            _, pattern = pattern_entry
            copied_patterns.setdefault(
                pattern_style.casefold(), ET.tostring(pattern, encoding="unicode")
            )
            for style_name in _referenced_pad_styles(pattern):
                style_entry = pad_styles.get(style_name.casefold())
                if style_entry is None:
                    raise EditError(
                        f"Pattern {pattern_style} references missing pad style {style_name}"
                    )
                if style_entry[0] is not pcb:
                    copied_pad_styles.setdefault(
                        style_name.casefold(),
                        ET.tostring(style_entry[1], encoding="unicode"),
                    )

    nets: list[dict[str, Any]] = []
    endpoint_owner: dict[tuple[str, str], str] = {}
    for net in schematic.container.findall("./Nets/Net"):
        name = _text(net, "Name")
        if not name:
            raise EditError("Every synchronized schematic net requires a name")
        endpoints: list[dict[str, str]] = []
        for item in net.findall("./Pins/Item"):
            part_id = item.get("Part", "")
            pin_text = item.get("Pin", "")
            if not pin_text.isdigit():
                raise EditError(f"Net {name} has an invalid pin index: {pin_text!r}")
            pin_key = (part_id, int(pin_text))
            endpoint = pin_to_pad.get(pin_key)
            if endpoint is None:
                endpoint_part = parts_by_id.get(part_id)
                refdes = _text(endpoint_part, "RefDes") if endpoint_part is not None else "?"
                raise EditError(
                    f"Pin-to-pad mapping is required for {refdes} part {part_id} pin {pin_text}",
                    details={"net": name, "part_id": part_id, "pin": int(pin_text)},
                )
            endpoint_key = (endpoint[0].casefold(), endpoint[1].casefold())
            previous_net = endpoint_owner.setdefault(endpoint_key, name)
            if previous_net.casefold() != name.casefold():
                raise EditError(
                    f"PCB endpoint {endpoint[0]}:{endpoint[1]} maps to multiple nets",
                    details={"nets": [previous_net, name]},
                )
            endpoints.append({"refdes": endpoint[0], "pad_number": endpoint[1]})
        if endpoints:
            unique = {
                (item["refdes"].casefold(), item["pad_number"].casefold())
                for item in endpoints
            }
            if len(unique) != len(endpoints):
                raise EditError(f"Net {name} contains duplicate mapped PCB endpoints")
            nets.append({"name": name, "endpoints": endpoints})

    operation = SyncSchematicToPcbOperation.model_validate(
        {
            "schematic_sha256": schematic.sha256,
            "components": component_specs,
            "nets": nets,
            "pattern_xml": list(copied_patterns.values()),
            "pad_style_xml": list(copied_pad_styles.values()),
            "update_existing_properties": update_existing_properties,
            "create_ratlines": create_ratlines,
            "allow_reconnect": allow_reconnect,
        }
    )
    return SyncPlan(
        operation=operation,
        warnings=warnings,
        limitations=[
            "Multi-part components require explicit part-id/pin to pad-number mappings.",
            "Synchronization is additive; extra PCB components, nets and traces are preserved.",
            "New components use deterministic grid placement and should be legalized "
            "before routing.",
        ],
    )
