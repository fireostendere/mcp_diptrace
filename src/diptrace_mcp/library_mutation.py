"""Raw-preserving Component/Pattern Library mutation primitives.

This module intentionally stays below the public MCP surface until real DipTrace
open/save/re-export evidence exists for the writer paths.  It implements the
code-side contract required for that evidence work:

* create/update Pattern Library patterns;
* create/update Component Library components/parts/pins/fields;
* explicit pin-to-pad mapping and pattern attachment;
* explicit collision and known-collection replacement policy;
* preservation of unknown XML outside the explicitly replaced known collections;
* deterministic/idempotent output through :class:`RawTreeSnapshot`.

The module never claims that generated XML is accepted by an arbitrary DipTrace
build.  That remains a human acceptance gate.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import DocumentError, EditError
from .xml_document import DipTraceDocument, RawTreeSnapshot

CollisionPolicy = Literal["error", "keep", "update"]


class _StrictSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PatternPadSpec(_StrictSpec):
    xml_id: str = Field(min_length=1, max_length=128)
    number: str = Field(min_length=1, max_length=128)
    style: str = Field(min_length=1, max_length=256)
    x_mm: float = Field(allow_inf_nan=False)
    y_mm: float = Field(allow_inf_nan=False)
    angle_deg: float = Field(default=0.0, allow_inf_nan=False)
    side: str = Field(default="Top", min_length=1, max_length=32)
    locked: bool = False


class PatternGraphicSpec(_StrictSpec):
    xml_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="Line", min_length=1, max_length=64)
    layer: str = Field(default="Top Silk", min_length=1, max_length=128)
    line_width_mm: float = Field(default=0.15, gt=0.0, allow_inf_nan=False)
    points: list[tuple[float, float]] = Field(default_factory=list, min_length=2, max_length=4096)

    @field_validator("points")
    @classmethod
    def _finite_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not math.isfinite(x) or not math.isfinite(y) for x, y in value):
            raise ValueError("graphic points must be finite")
        return value


class PatternSpec(_StrictSpec):
    name: str = Field(min_length=1, max_length=512)
    style: str = Field(min_length=1, max_length=512)
    unique_name: str = Field(default="", max_length=512)
    refdes: str = Field(default="", max_length=64)
    mounting: str = Field(default="None", min_length=1, max_length=64)
    value: str = Field(default="", max_length=2048)
    manufacturer: str = Field(default="", max_length=512)
    width_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    height_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    orientation_deg: float = Field(default=0.0, allow_inf_nan=False)
    default_pad_style: str | None = Field(default=None, min_length=1, max_length=256)
    pads: list[PatternPadSpec] = Field(default_factory=list, max_length=4096)
    graphics: list[PatternGraphicSpec] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def _unique_pad_and_graphic_ids(self) -> PatternSpec:
        pad_ids = [item.xml_id for item in self.pads]
        if len(set(pad_ids)) != len(pad_ids):
            raise ValueError("pattern pad xml_id values must be unique")
        graphic_ids = [item.xml_id for item in self.graphics]
        if len(set(graphic_ids)) != len(graphic_ids):
            raise ValueError("pattern graphic xml_id values must be unique")
        return self


class ComponentPinSpec(_StrictSpec):
    xml_id: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=512)
    number: str = Field(min_length=1, max_length=128)
    pad_id: str | None = Field(default=None, max_length=128)
    pad_number: str | None = Field(default=None, max_length=128)
    electrical_type: str = Field(default="Undefined", min_length=1, max_length=128)
    pin_type: str = Field(default="Default", min_length=1, max_length=128)
    x_mm: float = Field(default=0.0, allow_inf_nan=False)
    y_mm: float = Field(default=0.0, allow_inf_nan=False)
    orientation_deg: float = Field(default=0.0, allow_inf_nan=False)
    length_mm: float = Field(default=0.5, ge=0.0, allow_inf_nan=False)
    locked: bool = False
    show_name: bool = True

    @model_validator(mode="after")
    def _mapping_is_explicit(self) -> ComponentPinSpec:
        if (self.pad_id is None) != (self.pad_number is None):
            raise ValueError("pad_id and pad_number must be supplied together")
        return self


class ComponentGraphicSpec(_StrictSpec):
    xml_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="Line", min_length=1, max_length=64)
    line_width_mm: float = Field(default=0.15, gt=0.0, allow_inf_nan=False)
    points: list[tuple[float, float]] = Field(default_factory=list, min_length=2, max_length=4096)

    @field_validator("points")
    @classmethod
    def _finite_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not math.isfinite(x) or not math.isfinite(y) for x, y in value):
            raise ValueError("graphic points must be finite")
        return value


class ComponentPartSpec(_StrictSpec):
    name: str = Field(min_length=1, max_length=512)
    refdes: str = Field(default="", max_length=64)
    value: str = Field(default="", max_length=2048)
    manufacturer: str = Field(default="", max_length=512)
    datasheet: str = Field(default="", max_length=4096)
    fields: dict[str, str] = Field(default_factory=dict)
    pattern_style: str | None = Field(default=None, min_length=1, max_length=512)
    pins: list[ComponentPinSpec] = Field(default_factory=list, max_length=4096)
    graphics: list[ComponentGraphicSpec] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def _unique_pin_and_graphic_ids(self) -> ComponentPartSpec:
        pin_ids = [item.xml_id for item in self.pins]
        if len(set(pin_ids)) != len(pin_ids):
            raise ValueError("component pin xml_id values must be unique within a part")
        graphic_ids = [item.xml_id for item in self.graphics]
        if len(set(graphic_ids)) != len(graphic_ids):
            raise ValueError("component graphic xml_id values must be unique within a part")
        return self


class ComponentSpec(_StrictSpec):
    name: str = Field(min_length=1, max_length=512)
    parts: list[ComponentPartSpec] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _first_part_matches_component_name(self) -> ComponentSpec:
        if self.parts[0].name != self.name:
            raise ValueError("the first part name must match the component name")
        return self


@dataclass(frozen=True, slots=True)
class LibraryMutationResult:
    raw_bytes: bytes
    changed: bool
    changed_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _fmt(value: float) -> str:
    if not math.isfinite(value):
        raise EditError("library numeric values must be finite")
    rendered = f"{value:.12g}"
    return "0" if rendered in {"-0", "-0.0"} else rendered


def _set_attr(element: ET.Element, name: str, value: str) -> bool:
    if element.get(name) == value:
        return False
    element.set(name, value)
    return True


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(f"./{tag}")
    return (child.text or "") if child is not None else ""


def _set_child_text(element: ET.Element, tag: str, value: str) -> bool:
    child = element.find(f"./{tag}")
    if child is None:
        child = ET.SubElement(element, tag)
        child.text = value
        return True
    if (child.text or "") == value:
        return False
    child.text = value
    return True


def _ensure_child(element: ET.Element, tag: str) -> tuple[ET.Element, bool]:
    child = element.find(f"./{tag}")
    if child is not None:
        return child, False
    return ET.SubElement(element, tag), True


def _clone_for_mutation(document: DipTraceDocument) -> tuple[DipTraceDocument, RawTreeSnapshot]:
    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    return working, RawTreeSnapshot.capture(working)


def _compile(
    original: DipTraceDocument,
    working: DipTraceDocument,
    snapshot: RawTreeSnapshot,
    changed_ids: list[str],
    warnings: list[str] | None = None,
) -> LibraryMutationResult:
    raw = snapshot.compile(working.root, original.path)
    reparsed = DipTraceDocument.from_bytes(original.path, raw)
    if reparsed.source_type != original.source_type:
        raise EditError("library mutation changed the document type")
    return LibraryMutationResult(
        raw_bytes=raw,
        changed=raw != original.raw_bytes,
        changed_ids=tuple(changed_ids if raw != original.raw_bytes else ()),
        warnings=tuple(warnings or ()),
    )


def _pattern_library_root(document: DipTraceDocument) -> ET.Element:
    if document.source_type == "DipTrace-PatternLibrary":
        return document.root
    if document.source_type == "DipTrace-ComponentLibrary":
        nested = document.root.find("./Library[@Type='DipTrace-PatternLibrary']")
        if nested is None:
            raise DocumentError("Component Library has no embedded Pattern Library")
        return nested
    raise DocumentError("Pattern mutation requires a Component or Pattern Library")


def _patterns_container(document: DipTraceDocument) -> ET.Element:
    root = _pattern_library_root(document)
    patterns, _ = _ensure_child(root, "Patterns")
    return patterns


def _components_container(document: DipTraceDocument) -> ET.Element:
    if document.source_type != "DipTrace-ComponentLibrary":
        raise DocumentError("Component mutation requires a Component Library")
    components, _ = _ensure_child(document.root, "Components")
    return components


def _matching_patterns(container: ET.Element, spec: PatternSpec) -> list[ET.Element]:
    return [
        item
        for item in container.findall("./Pattern")
        if _child_text(item, "Name") == spec.name or item.get("PatternStyle") == spec.style
    ]


def _matching_components(container: ET.Element, name: str) -> list[ET.Element]:
    result: list[ET.Element] = []
    for component in container.findall("./Component"):
        first_part = component.find("./Part")
        if first_part is not None and _child_text(first_part, "Name") == name:
            result.append(component)
    return result


def _new_pad(spec: PatternPadSpec) -> ET.Element:
    pad = ET.Element(
        "Pad",
        {
            "Id": spec.xml_id,
            "Style": spec.style,
            "X": _fmt(spec.x_mm),
            "Y": _fmt(spec.y_mm),
            "Angle": _fmt(math.radians(spec.angle_deg)),
            "Locked": "Y" if spec.locked else "N",
            "Side": spec.side,
        },
    )
    number = ET.SubElement(pad, "Number")
    number.text = spec.number
    return pad


def _update_pad(element: ET.Element, spec: PatternPadSpec) -> bool:
    changed = False
    for key, value in (
        ("Id", spec.xml_id),
        ("Style", spec.style),
        ("X", _fmt(spec.x_mm)),
        ("Y", _fmt(spec.y_mm)),
        ("Angle", _fmt(math.radians(spec.angle_deg))),
        ("Locked", "Y" if spec.locked else "N"),
        ("Side", spec.side),
    ):
        changed |= _set_attr(element, key, value)
    changed |= _set_child_text(element, "Number", spec.number)
    return changed


def _new_pattern_graphic(spec: PatternGraphicSpec) -> ET.Element:
    shape = ET.Element(
        "Shape",
        {
            "Id": spec.xml_id,
            "Type": spec.kind,
            "Locked": "N",
            "Layer": spec.layer,
            "LineWidth": _fmt(spec.line_width_mm),
            "AllLayers": "N",
            "Group": "-1",
        },
    )
    points = ET.SubElement(shape, "Points")
    for x, y in spec.points:
        ET.SubElement(points, "Item", {"X": _fmt(x), "Y": _fmt(y)})
    return shape


def _replace_points(container: ET.Element, points: list[tuple[float, float]]) -> bool:
    current = [
        (item.get("X", ""), item.get("Y", ""))
        for item in container
        if item.tag in {"Item", "Point"}
    ]
    desired = [(_fmt(x), _fmt(y)) for x, y in points]
    if current == desired:
        return False
    for item in list(container):
        if item.tag in {"Item", "Point"}:
            container.remove(item)
    for x, y in desired:
        ET.SubElement(container, "Item", {"X": x, "Y": y})
    return True


def _update_pattern_graphic(element: ET.Element, spec: PatternGraphicSpec) -> bool:
    changed = False
    for key, value in (
        ("Id", spec.xml_id),
        ("Type", spec.kind),
        ("Layer", spec.layer),
        ("LineWidth", _fmt(spec.line_width_mm)),
    ):
        changed |= _set_attr(element, key, value)
    points, created = _ensure_child(element, "Points")
    changed |= created
    changed |= _replace_points(points, spec.points)
    return changed


def _apply_pattern_spec(
    pattern: ET.Element,
    spec: PatternSpec,
    *,
    replace_pads: bool,
    replace_graphics: bool,
) -> None:
    _set_attr(pattern, "PatternStyle", spec.style)
    _set_attr(pattern, "RefDes", spec.refdes)
    _set_attr(pattern, "Mounting", spec.mounting)
    _set_attr(pattern, "Orientation", _fmt(math.radians(spec.orientation_deg)))
    pattern.attrib.setdefault("Type", "Free")
    if spec.width_mm is not None:
        _set_attr(pattern, "Width", _fmt(spec.width_mm))
    if spec.height_mm is not None:
        _set_attr(pattern, "Height", _fmt(spec.height_mm))
    _set_child_text(pattern, "Name", spec.name)
    _set_child_text(pattern, "Name_Unique", spec.unique_name)
    if spec.value:
        _set_child_text(pattern, "Value", spec.value)
    if spec.manufacturer:
        _set_child_text(pattern, "Manufacturer", spec.manufacturer)
    if spec.default_pad_style is not None:
        default_pad, _ = _ensure_child(pattern, "DefPad")
        _set_attr(default_pad, "Style", spec.default_pad_style)

    pads, _ = _ensure_child(pattern, "Pads")
    by_id = {item.get("Id", ""): item for item in pads.findall("./Pad")}
    desired_pad_ids = {item.xml_id for item in spec.pads}
    if replace_pads:
        for item in list(pads):
            if item.tag == "Pad" and item.get("Id", "") not in desired_pad_ids:
                pads.remove(item)
    for pad_spec in spec.pads:
        existing = by_id.get(pad_spec.xml_id)
        if existing is None:
            pads.append(_new_pad(pad_spec))
        else:
            _update_pad(existing, pad_spec)

    if spec.graphics or replace_graphics:
        shapes, _ = _ensure_child(pattern, "Shapes")
        by_shape_id = {item.get("Id", ""): item for item in shapes.findall("./Shape")}
        desired_graphic_ids = {item.xml_id for item in spec.graphics}
        if replace_graphics:
            for item in list(shapes):
                if item.tag == "Shape" and item.get("Id", "") not in desired_graphic_ids:
                    shapes.remove(item)
        for graphic_spec in spec.graphics:
            existing = by_shape_id.get(graphic_spec.xml_id)
            if existing is None:
                shapes.append(_new_pattern_graphic(graphic_spec))
            else:
                _update_pattern_graphic(existing, graphic_spec)


def mutate_pattern(
    document: DipTraceDocument,
    spec: PatternSpec | dict[str, object],
    *,
    collision: CollisionPolicy = "error",
    replace_pads: bool = False,
    replace_graphics: bool = False,
) -> LibraryMutationResult:
    """Create or update one pattern while preserving unrelated/unknown XML.

    ``replace_pads`` and ``replace_graphics`` remove only known ``Pad``/``Shape``
    children absent from the supplied spec. Unknown sibling elements remain.
    """

    parsed = spec if isinstance(spec, PatternSpec) else PatternSpec.model_validate(spec)
    working, snapshot = _clone_for_mutation(document)
    patterns = _patterns_container(working)
    matches = _matching_patterns(patterns, parsed)
    if len(matches) > 1:
        raise EditError("pattern selector is ambiguous: name/style collides with multiple entries")
    if matches:
        if collision == "error":
            raise EditError(f"pattern already exists: {parsed.name}")
        if collision == "keep":
            return LibraryMutationResult(document.raw_bytes, False, ())
        pattern = matches[0]
    else:
        pattern = ET.SubElement(patterns, "Pattern")
    _apply_pattern_spec(
        pattern,
        parsed,
        replace_pads=replace_pads,
        replace_graphics=replace_graphics,
    )
    return _compile(document, working, snapshot, [f"pattern:{parsed.name}"])


def _new_component_graphic(spec: ComponentGraphicSpec) -> ET.Element:
    shape = ET.Element(
        "Shape",
        {
            "Id": spec.xml_id,
            "Type": spec.kind,
            "Locked": "N",
            "LineWidth": _fmt(spec.line_width_mm),
            "Group": "-1",
        },
    )
    points = ET.SubElement(shape, "Points")
    for x, y in spec.points:
        ET.SubElement(points, "Item", {"X": _fmt(x), "Y": _fmt(y)})
    return shape


def _new_pin(spec: ComponentPinSpec) -> ET.Element:
    attributes = {
        "Id": spec.xml_id,
        "X": _fmt(spec.x_mm),
        "Y": _fmt(spec.y_mm),
        "Locked": "Y" if spec.locked else "N",
        "Type": spec.pin_type,
        "ElectricType": spec.electrical_type,
        "Orientation": _fmt(math.radians(spec.orientation_deg)),
        "Length": _fmt(spec.length_mm),
        "ShowName": "Y" if spec.show_name else "N",
    }
    if spec.pad_id is not None:
        attributes["PadId"] = spec.pad_id
    pin = ET.Element("Pin", attributes)
    name = ET.SubElement(pin, "Name")
    name.text = spec.name
    number = ET.SubElement(pin, "PadNumber")
    number.text = spec.pad_number if spec.pad_number is not None else spec.number
    return pin


def _update_pin(element: ET.Element, spec: ComponentPinSpec) -> None:
    for key, value in (
        ("Id", spec.xml_id),
        ("X", _fmt(spec.x_mm)),
        ("Y", _fmt(spec.y_mm)),
        ("Locked", "Y" if spec.locked else "N"),
        ("Type", spec.pin_type),
        ("ElectricType", spec.electrical_type),
        ("Orientation", _fmt(math.radians(spec.orientation_deg))),
        ("Length", _fmt(spec.length_mm)),
        ("ShowName", "Y" if spec.show_name else "N"),
    ):
        _set_attr(element, key, value)
    if spec.pad_id is None:
        element.attrib.pop("PadId", None)
    else:
        _set_attr(element, "PadId", spec.pad_id)
    _set_child_text(element, "Name", spec.name)
    _set_child_text(
        element,
        "PadNumber",
        spec.pad_number if spec.pad_number is not None else spec.number,
    )


def _merge_fields(part: ET.Element, fields: dict[str, str], *, replace_fields: bool) -> None:
    if not fields and not replace_fields:
        return
    container, _ = _ensure_child(part, "AddFields")
    existing = {
        _child_text(item, "Name"): item for item in container.findall("./AddField")
    }
    if replace_fields:
        for item in list(container):
            if item.tag == "AddField" and _child_text(item, "Name") not in fields:
                container.remove(item)
    for name, value in fields.items():
        item = existing.get(name)
        if item is None:
            item = ET.SubElement(container, "AddField", {"Type": "Text"})
        item.attrib.setdefault("Type", "Text")
        _set_child_text(item, "Name", name)
        _set_child_text(item, "Text", value)


def _apply_part_spec(
    part: ET.Element,
    spec: ComponentPartSpec,
    *,
    replace_pins: bool,
    replace_fields: bool,
    replace_graphics: bool,
) -> None:
    _set_attr(part, "RefDes", spec.refdes)
    part.attrib.setdefault("PartType", "Normal")
    part.attrib.setdefault("ShowNumbers", "Common")
    part.attrib.setdefault("Type", "Free")
    part.attrib.setdefault("LockTypeChange", "N")
    _set_child_text(part, "Name", spec.name)
    _set_child_text(part, "Value", spec.value)
    if spec.manufacturer:
        _set_child_text(part, "Manufacturer", spec.manufacturer)
    if spec.datasheet:
        _set_child_text(part, "Datasheet", spec.datasheet)
    _merge_fields(part, spec.fields, replace_fields=replace_fields)

    pins, _ = _ensure_child(part, "Pins")
    by_id = {item.get("Id", ""): item for item in pins.findall("./Pin")}
    desired_pin_ids = {item.xml_id for item in spec.pins}
    if replace_pins:
        for item in list(pins):
            if item.tag == "Pin" and item.get("Id", "") not in desired_pin_ids:
                pins.remove(item)
    for pin_spec in spec.pins:
        existing = by_id.get(pin_spec.xml_id)
        if existing is None:
            pins.append(_new_pin(pin_spec))
        else:
            _update_pin(existing, pin_spec)

    if spec.graphics or replace_graphics:
        shapes, _ = _ensure_child(part, "Shapes")
        by_id_shape = {item.get("Id", ""): item for item in shapes.findall("./Shape")}
        desired_ids = {item.xml_id for item in spec.graphics}
        if replace_graphics:
            for item in list(shapes):
                if item.tag == "Shape" and item.get("Id", "") not in desired_ids:
                    shapes.remove(item)
        for graphic_spec in spec.graphics:
            existing = by_id_shape.get(graphic_spec.xml_id)
            if existing is None:
                shapes.append(_new_component_graphic(graphic_spec))
            else:
                _set_attr(existing, "Type", graphic_spec.kind)
                _set_attr(existing, "LineWidth", _fmt(graphic_spec.line_width_mm))
                points, _ = _ensure_child(existing, "Points")
                _replace_points(points, graphic_spec.points)

    if spec.pattern_style is not None:
        pattern, _ = _ensure_child(part, "Pattern")
        _set_attr(pattern, "Style", spec.pattern_style)


def mutate_component(
    document: DipTraceDocument,
    spec: ComponentSpec | dict[str, object],
    *,
    collision: CollisionPolicy = "error",
    replace_parts: bool = False,
    replace_pins: bool = False,
    replace_fields: bool = False,
    replace_graphics: bool = False,
) -> LibraryMutationResult:
    """Create/update a component with explicit collection-replacement policy."""

    parsed = spec if isinstance(spec, ComponentSpec) else ComponentSpec.model_validate(spec)
    working, snapshot = _clone_for_mutation(document)
    components = _components_container(working)
    matches = _matching_components(components, parsed.name)
    if len(matches) > 1:
        raise EditError(f"component selector is ambiguous: {parsed.name}")
    if matches:
        if collision == "error":
            raise EditError(f"component already exists: {parsed.name}")
        if collision == "keep":
            return LibraryMutationResult(document.raw_bytes, False, ())
        component = matches[0]
    else:
        component = ET.SubElement(components, "Component")

    existing_parts = [item for item in component.findall("./Part")]
    if replace_parts and len(existing_parts) > len(parsed.parts):
        for item in existing_parts[len(parsed.parts) :]:
            component.remove(item)
        existing_parts = existing_parts[: len(parsed.parts)]
    for index, part_spec in enumerate(parsed.parts):
        if index < len(existing_parts):
            part = existing_parts[index]
        else:
            part = ET.SubElement(component, "Part")
        _apply_part_spec(
            part,
            part_spec,
            replace_pins=replace_pins,
            replace_fields=replace_fields,
            replace_graphics=replace_graphics,
        )
    return _compile(document, working, snapshot, [f"component:{parsed.name}"])


def attach_pattern(
    document: DipTraceDocument,
    component_name: str,
    pattern_style: str,
    *,
    part_indexes: list[int] | None = None,
) -> LibraryMutationResult:
    """Attach one existing pattern style to selected component parts.

    The writer checks the embedded Pattern Library first so a typo cannot create
    an unresolvable component-to-pattern link in synthetic/library tests.
    """

    working, snapshot = _clone_for_mutation(document)
    pattern_root = _pattern_library_root(working)
    if not any(
        item.get("PatternStyle") == pattern_style or _child_text(item, "Name") == pattern_style
        for item in pattern_root.findall("./Patterns/Pattern")
    ):
        raise EditError(f"pattern is not present in the library: {pattern_style}")
    components = _components_container(working)
    matches = _matching_components(components, component_name)
    if len(matches) != 1:
        raise EditError(
            f"component selector must match exactly one entry: {component_name} ({len(matches)} found)"
        )
    parts = matches[0].findall("./Part")
    indexes = list(range(len(parts))) if part_indexes is None else part_indexes
    if len(set(indexes)) != len(indexes) or any(index < 0 or index >= len(parts) for index in indexes):
        raise EditError("part_indexes contains duplicates or an out-of-range part index")
    for index in indexes:
        target, _ = _ensure_child(parts[index], "Pattern")
        _set_attr(target, "Style", pattern_style)
    return _compile(document, working, snapshot, [f"component:{component_name}:pattern"])


def validate_explicit_pin_pad_mapping(document: DipTraceDocument, component_name: str) -> list[str]:
    """Return deterministic mapping errors for one component.

    This is intentionally strict: every mapped pin must carry both ``PadId`` and
    ``PadNumber`` and must resolve to the attached embedded pattern.
    """

    if document.source_type != "DipTrace-ComponentLibrary":
        raise DocumentError("Pin/pad mapping validation requires a Component Library")
    components = document.root.find("./Components")
    if components is None:
        return ["component library has no Components container"]
    matches = _matching_components(components, component_name)
    if len(matches) != 1:
        return [f"component selector matched {len(matches)} entries"]
    pattern_root = _pattern_library_root(document)
    patterns = {
        item.get("PatternStyle", ""): item
        for item in pattern_root.findall("./Patterns/Pattern")
        if item.get("PatternStyle")
    }
    errors: list[str] = []
    for part_index, part in enumerate(matches[0].findall("./Part")):
        pattern = part.find("./Pattern")
        style = pattern.get("Style", "") if pattern is not None else ""
        resolved = patterns.get(style)
        if resolved is None:
            errors.append(f"part {part_index}: attached pattern {style!r} is missing")
            continue
        valid_ids = {pad.get("Id", "") for pad in resolved.findall("./Pads/Pad")}
        valid_numbers = {_child_text(pad, "Number") for pad in resolved.findall("./Pads/Pad")}
        for pin in part.findall("./Pins/Pin"):
            pad_id = pin.get("PadId")
            pad_number = _child_text(pin, "PadNumber")
            label = _child_text(pin, "Name") or pin.get("Id", "<unknown>")
            if pad_id is None or not pad_number:
                errors.append(f"part {part_index} pin {label}: mapping is incomplete")
                continue
            if pad_id not in valid_ids:
                errors.append(f"part {part_index} pin {label}: PadId {pad_id!r} is absent")
            if pad_number not in valid_numbers:
                errors.append(
                    f"part {part_index} pin {label}: PadNumber {pad_number!r} is absent"
                )
    return errors
