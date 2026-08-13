from __future__ import annotations

import copy
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any, Literal

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import LibraryComponent, LibraryModel, LibraryPin, ObjectRecord, StrictModel
from .geometry import Point, Transform
from .library_adapters import get_library_model
from .xml_document import DipTraceDocument

_EPS = 1e-9
MatchBasis = Literal["explicit_binding", "component_style_index", "unique_component_name"]
LibrarySource = Literal["provided", "embedded_design_cache", "external_fallback"]


class SchematicPinGeometryConfig(StrictModel):
    allow_component_style_index_match: bool = True
    allow_unique_component_name_match: bool = True
    allow_unverified_part_rotation: bool = True
    allow_external_library_fallback: bool = False


class ResolvedSchematicPinGeometry(StrictModel):
    pin_id: str
    part_id: str
    refdes: str | None = None
    pin_index: int = Field(ge=0)
    library_component_id: str
    library_pin_id: str
    library_part_index: int = Field(ge=0)
    local_position: dict[str, float]
    absolute_position: dict[str, float] | None = None
    local_orientation_deg: float
    absolute_orientation_deg: float | None = None
    electrical_type: str
    pin_type: str
    match_basis: MatchBasis
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class SchematicPinGeometryResolution(StrictModel):
    pins: list[ResolvedSchematicPinGeometry] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    component_matches: dict[str, str] = Field(default_factory=dict)
    library_source: LibrarySource = "provided"
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _pin_index(pin: ObjectRecord) -> int | None:
    raw = pin.xml_id or ""
    _, separator, suffix = raw.rpartition(":")
    if not separator:
        return None
    try:
        value = int(suffix)
    except ValueError:
        return None
    return value if value >= 0 else None


def _component_part_index(part: ObjectRecord) -> int | None:
    raw = str(part.attributes.get("component_part", "")).strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _part_pins(snapshot: DocumentSnapshot) -> dict[str, list[ObjectRecord]]:
    assert snapshot.schematic is not None
    result: dict[str, list[ObjectRecord]] = defaultdict(list)
    for pin in snapshot.schematic.pins:
        if pin.parent_id is not None:
            result[pin.parent_id].append(pin)
    return result


def _component_pins(component: LibraryComponent, part_index: int) -> list[LibraryPin]:
    return [pin for pin in component.pins if pin.part_index == part_index]


def _refdes_prefix(refdes: str | None) -> str:
    if not refdes:
        return ""
    match = re.match(r"[A-Za-z]+", refdes)
    return match.group(0).casefold() if match else ""


def _validate_component_match(
    part: ObjectRecord,
    schematic_pin_count: int,
    component: LibraryComponent,
    component_part: int,
    *,
    require_name: bool,
) -> list[str]:
    reasons: list[str] = []
    if component_part >= component.part_count:
        reasons.append(
            f"component part index {component_part} is outside library part_count "
            f"{component.part_count}"
        )
        return reasons
    library_pins = _component_pins(component, component_part)
    if len(library_pins) != schematic_pin_count:
        reasons.append(
            f"schematic pin count {schematic_pin_count} does not match library part pin "
            f"count {len(library_pins)}"
        )
    part_name = (part.name or "").strip().casefold()
    component_name = component.name.strip().casefold()
    if require_name and part_name and component_name and part_name != component_name:
        reasons.append(
            f"schematic name {part.name!r} does not match library component "
            f"name {component.name!r}"
        )
    schematic_prefix = _refdes_prefix(part.refdes)
    library_prefix = component.refdes.strip().casefold()
    if schematic_prefix and library_prefix and schematic_prefix != library_prefix:
        reasons.append(
            f"schematic RefDes prefix {schematic_prefix!r} does not match library "
            f"prefix {library_prefix!r}"
        )
    return reasons


def _style_index(component_style: str) -> int | None:
    match = re.fullmatch(r"CompType([0-9]+)", component_style.strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _match_component(
    part: ObjectRecord,
    schematic_pin_count: int,
    library: LibraryModel,
    bindings: dict[str, str],
    config: SchematicPinGeometryConfig,
) -> tuple[LibraryComponent | None, MatchBasis | None, list[str]]:
    component_part = _component_part_index(part)
    if component_part is None:
        return None, None, ["schematic component_part is missing or invalid"]

    component_style = str(part.attributes.get("component_style", "")).strip()
    by_id = {component.stable_id: component for component in library.components}
    if component_style in bindings:
        component = by_id.get(bindings[component_style])
        if component is None:
            return None, None, ["explicit binding points to a missing library component"]
        problems = _validate_component_match(
            part,
            schematic_pin_count,
            component,
            component_part,
            require_name=False,
        )
        if problems:
            return None, None, problems
        return component, "explicit_binding", []

    if config.allow_component_style_index_match:
        style_index = _style_index(component_style)
        if style_index is not None:
            indexed = [
                component
                for component in library.components
                if component.index == style_index
            ]
            if len(indexed) == 1:
                problems = _validate_component_match(
                    part,
                    schematic_pin_count,
                    indexed[0],
                    component_part,
                    require_name=True,
                )
                if not problems:
                    return indexed[0], "component_style_index", []

    if config.allow_unique_component_name_match and part.name:
        name = part.name.strip().casefold()
        candidates = [
            component
            for component in library.components
            if component.name.strip().casefold() == name
            and not _validate_component_match(
                part,
                schematic_pin_count,
                component,
                component_part,
                require_name=True,
            )
        ]
        if len(candidates) == 1:
            return candidates[0], "unique_component_name", []
        if len(candidates) > 1:
            return None, None, [
                f"{len(candidates)} library components match schematic name {part.name!r}"
            ]

    return None, None, [
        "no unique structurally compatible library component could be resolved"
    ]


def _absolute_geometry(
    part: ObjectRecord,
    pin: LibraryPin,
    config: SchematicPinGeometryConfig,
) -> tuple[dict[str, float] | None, float | None, list[str]]:
    warnings: list[str] = []
    if part.position is None or pin.position is None:
        return None, None, ["part or library pin position is unavailable"]
    orientation_rad = math.radians(pin.orientation_deg)
    local = Point(
        pin.position["x"] - math.cos(orientation_rad) * pin._length_mm,
        pin.position["y"] + math.sin(orientation_rad) * pin._length_mm,
    )
    origin = Point(**part.position)
    angle = part.rotation_deg
    if not math.isclose(angle, 0.0, abs_tol=_EPS) and not config.allow_unverified_part_rotation:
        return None, None, [
            "non-zero schematic part rotation is not applied because the live DipTrace "
            "angle convention is not yet trusted for pin geometry"
        ]
    if math.isclose(angle, 0.0, abs_tol=_EPS):
        absolute = Point(origin.x + local.x, origin.y + local.y)
    else:
        absolute = Transform(
            translate_x=origin.x,
            translate_y=origin.y,
            rotation_deg=angle,
        ).apply_point(local)
        warnings.append(
            "absolute pin geometry uses the verified DipTrace schematic rotation convention"
        )
    orientation = (pin.orientation_deg + angle) % 360.0
    return absolute.as_dict(), orientation, warnings


def get_embedded_schematic_component_library(
    document: DipTraceDocument,
) -> LibraryModel | None:
    """Return the schematic's embedded design-cache Component Library model.

    DipTrace stores the project design cache as a sibling ``Library`` element under the
    schematic ``Source`` root.  Reusing ``get_library_model`` keeps component/pin parsing in
    one typed adapter rather than introducing a second XML interpretation here.
    """
    if document.source_type != "DipTrace-Schematic":
        return None
    library_root = document.root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    if library_root is None:
        return None
    root = copy.deepcopy(library_root)
    root.set("Type", "DipTrace-ComponentLibrary")
    root.set("Version", root.get("Version", document.version))
    root.set("Units", root.get("Units", document.units))
    embedded = DipTraceDocument(
        path=document.path,
        root=root,
        raw_bytes=ET.tostring(root, encoding="utf-8"),
    )
    return get_library_model(embedded)


def resolve_schematic_pin_geometry(
    snapshot: DocumentSnapshot,
    library: LibraryModel,
    *,
    bindings: dict[str, str] | None = None,
    config: SchematicPinGeometryConfig | None = None,
) -> SchematicPinGeometryResolution:
    """Resolve schematic Pin records against a component-library geometry model.

    Resolution is intentionally conservative. Opaque component styles are never treated as
    sufficient evidence by themselves. A CompTypeN index hint is accepted only when the
    indexed library component also matches the schematic component name, RefDes prefix,
    multipart index and pin count. Otherwise an exact unique component-name match or an
    explicit caller binding is required.
    """
    config = config or SchematicPinGeometryConfig()
    bindings = dict(bindings or {})
    if snapshot.schematic is None:
        return SchematicPinGeometryResolution(
            unresolved=[{"reason": "snapshot_has_no_schematic"}],
            limitations=["Schematic pin geometry requires a normalized schematic snapshot."],
        )
    if not library.components:
        return SchematicPinGeometryResolution(
            unresolved=[{"reason": "component_library_has_no_components"}],
            limitations=["A Component Library model with symbol pins is required."],
        )

    pins_by_part = _part_pins(snapshot)
    resolved: list[ResolvedSchematicPinGeometry] = []
    unresolved: list[dict[str, Any]] = []
    component_matches: dict[str, str] = {}
    aggregate_warnings: list[str] = []

    for part in sorted(snapshot.schematic.parts, key=lambda item: item.stable_id):
        schematic_pins = pins_by_part.get(part.stable_id, [])
        component_part = _component_part_index(part)
        component, basis, match_problems = _match_component(
            part,
            len(schematic_pins),
            library,
            bindings,
            config,
        )
        if component is None or basis is None or component_part is None:
            unresolved.append(
                {
                    "part_id": part.stable_id,
                    "refdes": part.refdes,
                    "component_style": part.attributes.get("component_style"),
                    "reasons": match_problems,
                }
            )
            continue
        component_matches[part.stable_id] = component.stable_id
        library_pins = _component_pins(component, component_part)
        for schematic_pin in schematic_pins:
            pin_index = _pin_index(schematic_pin)
            if pin_index is None or pin_index >= len(library_pins):
                unresolved.append(
                    {
                        "pin_id": schematic_pin.stable_id,
                        "part_id": part.stable_id,
                        "reason": "pin_index_cannot_be_mapped_to_library_part",
                    }
                )
                continue
            library_pin = library_pins[pin_index]
            if library_pin.position is None:
                unresolved.append(
                    {
                        "pin_id": schematic_pin.stable_id,
                        "part_id": part.stable_id,
                        "reason": "library_pin_has_no_position",
                    }
                )
                continue
            absolute, absolute_orientation, geometry_warnings = _absolute_geometry(
                part,
                library_pin,
                config,
            )
            aggregate_warnings.extend(geometry_warnings)
            confidence = {
                "explicit_binding": 0.98,
                "component_style_index": 0.95,
                "unique_component_name": 0.9,
            }[basis]
            if absolute is None:
                confidence = min(confidence, 0.7)
            resolved.append(
                ResolvedSchematicPinGeometry(
                    pin_id=schematic_pin.stable_id,
                    part_id=part.stable_id,
                    refdes=part.refdes,
                    pin_index=pin_index,
                    library_component_id=component.stable_id,
                    library_pin_id=library_pin.stable_id,
                    library_part_index=component_part,
                    local_position=dict(library_pin.position),
                    absolute_position=absolute,
                    local_orientation_deg=library_pin.orientation_deg,
                    absolute_orientation_deg=absolute_orientation,
                    electrical_type=library_pin.electrical_type,
                    pin_type=library_pin.pin_type,
                    match_basis=basis,
                    confidence=confidence,
                    warnings=geometry_warnings,
                )
            )

    return SchematicPinGeometryResolution(
        pins=resolved,
        unresolved=unresolved,
        component_matches=component_matches,
        assumptions=[
            "Schematic pin order is matched to library pin order within the resolved "
            "component part, consistent with the current normalized Pin indexing model.",
            "CompTypeN is only an index hint; structural identity checks are mandatory.",
            "Pin Length and Orientation are applied to the routed connection point.",
            "Part rotation follows the convention verified by a DipTrace 5.3 native "
            "re-export; callers may still disable it with the conservative config flag.",
        ],
        warnings=sorted(set(aggregate_warnings)),
        limitations=[
            "This resolver does not search external libraries or download datasheets.",
            "Mirroring and arbitrary rotated schematic symbols require verified host "
            "semantics before they can be authoritative.",
            "A resolved pin coordinate is geometric evidence, not proof that the chosen "
            "library revision exactly matches the original project library revision.",
        ],
    )


def resolve_document_schematic_pin_geometry(
    document: DipTraceDocument,
    *,
    bindings: dict[str, str] | None = None,
    fallback_library: LibraryModel | None = None,
    config: SchematicPinGeometryConfig | None = None,
) -> SchematicPinGeometryResolution:
    """Resolve pin geometry using the schematic's own embedded design cache first.

    A standalone Component Library may be supplied as a fallback, but it is ignored unless
    ``allow_external_library_fallback`` is explicitly enabled.  This avoids silently mixing
    a project with a different library revision when the authoritative design cache is
    missing or incomplete.
    """
    config = config or SchematicPinGeometryConfig()
    if document.source_type != "DipTrace-Schematic":
        return SchematicPinGeometryResolution(
            unresolved=[{"reason": "document_is_not_schematic"}],
            limitations=["Document-level pin geometry requires DipTrace-Schematic XML."],
        )

    snapshot = build_snapshot(document)
    embedded = get_embedded_schematic_component_library(document)
    if embedded is not None and embedded.components:
        resolution = resolve_schematic_pin_geometry(
            snapshot,
            embedded,
            bindings=bindings,
            config=config,
        )
        resolution.library_source = "embedded_design_cache"
        resolution.assumptions.append(
            "Component geometry was resolved from the schematic's embedded design cache."
        )
        return resolution

    if fallback_library is not None and config.allow_external_library_fallback:
        resolution = resolve_schematic_pin_geometry(
            snapshot,
            fallback_library,
            bindings=bindings,
            config=config,
        )
        resolution.library_source = "external_fallback"
        resolution.warnings.append(
            "Embedded design-cache component geometry was unavailable; an explicitly "
            "enabled external Component Library fallback was used."
        )
        return resolution

    limitations = [
        "The schematic has no usable embedded design-cache component geometry.",
    ]
    if fallback_library is not None and not config.allow_external_library_fallback:
        limitations.append(
            "An external Component Library was supplied but fallback is disabled by default."
        )
    return SchematicPinGeometryResolution(
        unresolved=[{"reason": "embedded_design_cache_has_no_components"}],
        library_source="embedded_design_cache",
        limitations=limitations,
    )
