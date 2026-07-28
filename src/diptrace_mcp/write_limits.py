"""Fail-closed accounting for the bounded-write object limit."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .adapters import build_snapshot
from .capability_model import MAX_WRITE_OBJECTS
from .errors import EditError
from .library_adapters import get_library_model
from .xml_document import DipTraceDocument


@dataclass(frozen=True, slots=True)
class WriteImpact:
    """Independent normalized and XML-structural estimates for one write."""

    changed_ids: tuple[str, ...]
    normalized_object_count: int
    structural_element_count: int

    @property
    def object_count(self) -> int:
        compiler_only_count = max(
            0,
            len(self.changed_ids) - self.normalized_object_count,
        )
        # There is no complete XML-element-to-normalized-object mapping. The
        # independent views can overlap, but taking only their maximum is not
        # fail-closed: normalized geometry derived from one XML definition can
        # change alongside unrelated passthrough XML. Charge the conservative
        # sum and disclose the possible overlap to clients.
        return (
            self.normalized_object_count
            + self.structural_element_count
            + compiler_only_count
        )


def _dump(value: BaseModel | dict[str, Any]) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _add_library_items(
    records: dict[str, Any],
    *,
    prefix: str,
    components: list[Any],
    patterns: list[Any],
    pad_styles: list[Any],
) -> None:
    for component in components:
        component_key = f"{prefix}:component:{component.stable_id}"
        records[component_key] = _dump(component.model_copy(update={"pins": []}))
        for pin in component.pins:
            records[f"{component_key}:pin:{pin.stable_id}"] = _dump(pin)
    for pattern in patterns:
        pattern_key = f"{prefix}:pattern:{pattern.stable_id}"
        records[pattern_key] = _dump(
            pattern.model_copy(
                update={
                    "pads": [],
                    "holes": [],
                    "shapes": [],
                    "courtyard_geometry": {},
                }
            )
        )
        for pad in pattern.pads:
            records[f"{pattern_key}:pad:{pad.stable_id}"] = _dump(pad)
        for index, hole in enumerate(pattern.holes):
            records[f"{pattern_key}:hole:{index}"] = hole
        for index, shape in enumerate(pattern.shapes):
            records[f"{pattern_key}:shape:{index}"] = shape
        for layer, shapes in sorted(pattern.courtyard_geometry.items()):
            for index, shape in enumerate(shapes):
                records[f"{pattern_key}:courtyard:{layer}:{index}"] = _dump(shape)
    for index, style in enumerate(pad_styles):
        name = style.name or str(index)
        records[f"{prefix}:pad-style:{name}:{index}"] = _dump(style)


def normalized_object_map(document: DipTraceDocument) -> dict[str, Any]:
    """Flatten every normalized object, including library children."""

    snapshot = build_snapshot(document)
    records: dict[str, Any] = {
        stable_id: record.model_dump(mode="json") for stable_id, record in snapshot.objects.items()
    }
    if snapshot.board is not None:
        _add_library_items(
            records,
            prefix="embedded-library",
            components=[],
            patterns=snapshot.board.patterns,
            pad_styles=snapshot.board.pad_styles,
        )
    if document.source_type in {
        "DipTrace-ComponentLibrary",
        "DipTrace-PatternLibrary",
    }:
        library = get_library_model(document)
        _add_library_items(
            records,
            prefix="library",
            components=library.components,
            patterns=library.patterns,
            pad_styles=library.pad_styles,
        )
    return records


def _element_identity(element: ET.Element) -> tuple[str, str]:
    for attribute in (
        "Id",
        "UniqueName",
        "PatternStyle",
        "Style",
        "Name",
        "Number",
    ):
        value = element.get(attribute)
        if value:
            return attribute, value
    if len(element) == 0 and element.text and element.text.strip():
        return "text", element.text.strip()
    return "", ""


_ElementPathStep = tuple[int, str, tuple[str, str], int]


class _ElementPathInterner:
    """Assign stable integer ids to linked XML paths in linear space."""

    def __init__(self) -> None:
        self._ids: dict[_ElementPathStep, int] = {}

    def intern(
        self,
        parent_path: int,
        tag: str,
        identity: tuple[str, str],
        occurrence: int,
    ) -> int:
        step = (parent_path, tag, identity, occurrence)
        path_id = self._ids.get(step)
        if path_id is None:
            path_id = len(self._ids) + 1
            self._ids[step] = path_id
        return path_id


def _structural_element_map(
    root: ET.Element,
    paths: _ElementPathInterner,
) -> dict[int, Any]:
    """Map exact local XML state and sibling order without recursive traversal."""

    records: dict[int, Any] = {}
    stack: list[tuple[ET.Element, int, int, int]] = [(root, 0, 0, 0)]
    while stack:
        element, parent_path, sibling_index, occurrence = stack.pop()
        tag = str(element.tag)
        path = paths.intern(
            parent_path,
            tag,
            _element_identity(element),
            occurrence,
        )
        records[path] = (
            tag,
            tuple(sorted(element.attrib.items())),
            element.text,
            element.tail,
            sibling_index,
        )
        sibling_counts: dict[tuple[str, tuple[str, str]], int] = {}
        children: list[tuple[ET.Element, int, int]] = []
        for child_index, child in enumerate(element):
            child_tag = str(child.tag)
            identity = _element_identity(child)
            key = (child_tag, identity)
            child_occurrence = sibling_counts.get(key, 0)
            sibling_counts[key] = child_occurrence + 1
            children.append((child, child_index, child_occurrence))
        for child, child_index, child_occurrence in reversed(children):
            stack.append((child, path, child_index, child_occurrence))

    return records


def _document_interpretation_changed(before: ET.Element, after: ET.Element) -> bool:
    def values(
        root: ET.Element,
    ) -> list[tuple[str, str | None, str | None, str | None]]:
        return [
            (
                str(element.tag),
                element.get("Type"),
                element.get("Version"),
                element.get("Units"),
            )
            for element in root.iter()
            if isinstance(element.tag, str)
            and element.tag in {"Source", "Library"}
        ]

    return values(before) != values(after)


def write_impact(
    before: DipTraceDocument | None,
    after: DipTraceDocument,
    *,
    compiler_changed_ids: list[str] | None = None,
) -> WriteImpact:
    """Measure changed normalized records and independently changed XML elements."""

    after_normalized = normalized_object_map(after)
    paths = _ElementPathInterner()
    after_structural = _structural_element_map(after.root, paths)
    if before is None:
        normalized_ids = set(after_normalized)
        structural_count = len(after_structural)
    else:
        before_normalized = normalized_object_map(before)
        normalized_ids = {
            key
            for key in before_normalized.keys() | after_normalized.keys()
            if before_normalized.get(key) != after_normalized.get(key)
        }
        before_structural = _structural_element_map(before.root, paths)
        structural_count = sum(
            before_structural.get(key) != after_structural.get(key)
            for key in before_structural.keys() | after_structural.keys()
        )
        if _document_interpretation_changed(before.root, after.root):
            # Type, Version, or Units on Source or an embedded/library root can
            # change how every descendant is interpreted. Charge the complete
            # scope rather than silently treating it as one attribute edit.
            structural_count = max(
                structural_count,
                len(before_structural),
                len(after_structural),
            )

    changed_ids = set(compiler_changed_ids or ())
    changed_ids.update(normalized_ids)
    return WriteImpact(
        changed_ids=tuple(sorted(changed_ids)),
        normalized_object_count=len(normalized_ids),
        structural_element_count=structural_count,
    )


def require_write_impact(impact: WriteImpact, *, operation: str) -> None:
    if impact.object_count <= MAX_WRITE_OBJECTS:
        return
    raise EditError(
        f"{operation} would affect {impact.object_count} objects/elements; "
        f"the per-write limit is {MAX_WRITE_OBJECTS}",
        code="write_object_limit_exceeded",
        details={
            "operation": operation,
            "object_count": impact.object_count,
            "max_write_objects": MAX_WRITE_OBJECTS,
            "normalized_object_count": impact.normalized_object_count,
            "structural_element_count": impact.structural_element_count,
            "changed_id_count": len(impact.changed_ids),
        },
        object_ids=list(impact.changed_ids[:MAX_WRITE_OBJECTS]),
    )
