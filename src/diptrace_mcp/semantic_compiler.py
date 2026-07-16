from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot, build_snapshot, stable_id
from .domain import ObjectRecord, QuerySelector
from .errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    EditError,
    LockedObjectError,
    ObjectNotFoundError,
    RoundtripValidationError,
    ScopeRequiredError,
)
from .geometry import (
    Point,
    Transform,
    from_mm,
    point_in_polygon,
    to_mm,
)
from .operations import (
    AddTestpointOperation,
    AssignNetsToClassOperation,
    GroupComponentsOperation,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    RemoveTestpointsOperation,
    RenameNetOperation,
    RotateBoardTextsOperation,
    RotateComponentsOperation,
    SemanticOperation,
    SetComponentLockOperation,
    SetComponentPatternOperation,
    SetComponentPropertiesOperation,
    SetComponentSideOperation,
    SetComponentValueOperation,
    SetPinNoConnectOperation,
    SetTextStyleOperation,
    SetTextVisibilityOperation,
    UngroupComponentsOperation,
    UpdateNetClassRulesOperation,
)
from .routing_compiler import (
    ROUTING_OPERATION_TYPES,
    apply_routing_operation,
)
from .xml_document import DipTraceDocument, RawTreeSnapshot, sha256_bytes


@dataclass(slots=True)
class SemanticApplyResult:
    document: DipTraceDocument
    raw_bytes: bytes
    previews: list[dict[str, Any]]
    changed_ids: list[str]
    warnings: list[str]
    validation: dict[str, Any]
    patch_count: int


def apply_semantic_operations(
    document: DipTraceDocument,
    operations: list[SemanticOperation],
    *,
    live_session: bool = False,
) -> SemanticApplyResult:
    if not operations:
        raise EditError("At least one semantic operation is required")
    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    raw_tree = RawTreeSnapshot.capture(working)
    snapshot = build_snapshot(working, live_session=live_session)
    previews: list[dict[str, Any]] = []
    changed_ids: list[str] = []
    warnings = list(snapshot.warnings)
    patch_count = 0

    for index, operation in enumerate(operations):
        if isinstance(operation, MoveComponentsOperation):
            preview, patches = _apply_move_components(
                index,
                working,
                snapshot,
                operation,
                changed_ids,
            )
        elif isinstance(operation, SetComponentValueOperation):
            preview, patches = _apply_set_component_value(
                index,
                working,
                snapshot,
                operation,
                changed_ids,
            )
        elif isinstance(operation, RotateComponentsOperation):
            preview, patches = _apply_rotate_components(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetComponentSideOperation):
            preview, patches = _apply_component_side(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetComponentLockOperation):
            preview, patches = _apply_component_lock(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetComponentPropertiesOperation):
            preview, patches = _apply_component_properties(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetComponentPatternOperation):
            preview, patches = _apply_component_pattern(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, GroupComponentsOperation):
            preview, patches = _apply_group_components(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, UngroupComponentsOperation):
            preview, patches = _apply_ungroup_components(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, MoveBoardTextsOperation):
            preview, patches = _apply_move_texts(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, RotateBoardTextsOperation):
            preview, patches = _apply_rotate_texts(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetTextVisibilityOperation):
            preview, patches = _apply_text_visibility(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetTextStyleOperation):
            preview, patches = _apply_text_style(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetPinNoConnectOperation):
            preview, patches = _apply_pin_no_connect(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, RenameNetOperation):
            preview, patches = _apply_rename_net(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, UpdateNetClassRulesOperation):
            preview, patches = _apply_net_class_rules(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, AssignNetsToClassOperation):
            preview, patches = _apply_assign_nets_to_class(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, AddTestpointOperation):
            preview, patches = _apply_add_testpoint(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, MoveTestpointsOperation):
            preview, patches = _apply_move_components(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, RemoveTestpointsOperation):
            preview, patches = _apply_remove_testpoints(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, ROUTING_OPERATION_TYPES):
            preview, patches, routing_changed_ids = apply_routing_operation(
                index,
                working,
                snapshot,
                operation,
            )
            changed_ids.extend(routing_changed_ids)
        else:
            raise EditError(f"Unsupported semantic operation kind: {operation.kind!r}")
        previews.append(preview)
        patch_count += patches
        snapshot = build_snapshot(working, live_session=live_session)

    raw_bytes = raw_tree.compile(working.root, working.path) if patch_count else document.raw_bytes
    try:
        validated = DipTraceDocument.from_bytes(working.path, raw_bytes)
    except Exception as exc:
        raise RoundtripValidationError(
            f"Compiled semantic operations produced invalid XML: {exc}"
        ) from exc
    if validated.source_type != document.source_type:
        raise RoundtripValidationError("Semantic operation changed the DipTrace document type")
    validation = {
        "reparsed": True,
        "source_type": validated.source_type,
        "kind": validated.kind,
        "before_sha256": document.sha256,
        "after_sha256": sha256_bytes(raw_bytes),
        "patch_count": patch_count,
    }
    return SemanticApplyResult(
        document=validated,
        raw_bytes=raw_bytes,
        previews=previews,
        changed_ids=sorted(dict.fromkeys(changed_ids)),
        warnings=warnings,
        validation=validation,
        patch_count=patch_count,
    )


def _select_records(
    snapshot: DocumentSnapshot,
    selector: QuerySelector,
    allowed_kinds: set[str],
) -> list[ObjectRecord]:
    if selector.is_empty():
        raise ScopeRequiredError("Selector is required for semantic writes")
    records = snapshot.select(selector, kinds=allowed_kinds)
    if not records:
        raise ObjectNotFoundError(
            "No matching objects were found",
            details={"selector": selector.model_dump(mode="json")},
        )
    return records


def _coordinate_mm(document: DipTraceDocument, element: ET.Element, name: str) -> float:
    raw = element.get(name)
    if raw is None:
        raise EditError(f"Element <{element.tag}> has no {name} coordinate")
    try:
        return to_mm(float(raw), document.units)
    except ValueError as exc:
        raise EditError(f"Invalid {name} coordinate on <{element.tag}>: {raw!r}") from exc


def _apply_move_components(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: MoveComponentsOperation | MoveTestpointsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    allowed_kinds = (
        {"testpoint"} if isinstance(operation, MoveTestpointsOperation) else {"component", "part"}
    )
    targets = _select_records(snapshot, operation.selector, allowed_kinds)
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        element = _resolved_element(snapshot, record)
        if record.locked and not operation.allow_locked:
            raise LockedObjectError(
                f"Object is locked: {record.label or record.stable_id}",
                object_ids=[record.stable_id],
            )
        x = _coordinate_mm(document, element, "X")
        y = _coordinate_mm(document, element, "Y")
        new_x = operation.absolute_x if operation.absolute_x is not None else x + operation.dx
        new_y = operation.absolute_y if operation.absolute_y is not None else y + operation.dy
        if operation.grid_snap is not None:
            new_x = round(new_x / operation.grid_snap) * operation.grid_snap
            new_y = round(new_y / operation.grid_snap) * operation.grid_snap
        before.append({"id": record.stable_id, "position": {"x": x, "y": y}})
        after.append({"id": record.stable_id, "position": {"x": new_x, "y": new_y}})
        if new_x == x and new_y == y:
            continue
        element.set("X", f"{from_mm(new_x, document.units):.9g}")
        element.set("Y", f"{from_mm(new_y, document.units):.9g}")
        changed_ids.append(record.stable_id)
        patch_count += 2
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_set_component_value(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetComponentValueOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component", "part"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        element = _resolved_element(snapshot, record)
        value_element = element.find("./Value")
        previous = value_element.text or "" if value_element is not None else ""
        before.append({"id": record.stable_id, "value": previous})
        after.append({"id": record.stable_id, "value": operation.value})
        if previous == operation.value:
            continue
        if value_element is None:
            value_element = ET.SubElement(element, "Value")
        value_element.text = operation.value
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_rotate_components(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: RotateComponentsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component", "part"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        previous = _normalize_angle(record.rotation_deg)
        requested = (
            operation.angle_deg if operation.mode == "absolute" else previous + operation.angle_deg
        )
        angle = _normalize_angle(requested)
        if operation.allowed_angles and not any(
            math.isclose(angle, _normalize_angle(item), abs_tol=1e-7)
            for item in operation.allowed_angles
        ):
            raise EditError(
                f"Angle {angle:g} is not in allowed_angles for {record.label}",
                code="placement_illegal",
                object_ids=[record.stable_id],
            )
        before.append({"id": record.stable_id, "rotation_deg": previous})
        after.append({"id": record.stable_id, "rotation_deg": angle})
        if math.isclose(previous, angle, abs_tol=1e-9):
            continue
        _set_angle_attribute(element, angle)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_component_side(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetComponentSideOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        previous = element.get("Side", "Top")
        before.append({"id": record.stable_id, "side": previous})
        after.append({"id": record.stable_id, "side": operation.side})
        if previous == operation.side:
            continue
        element.set("Side", operation.side)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_component_lock(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetComponentLockOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component", "part"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        element = _resolved_element(snapshot, record)
        before.append({"id": record.stable_id, "locked": record.locked})
        after.append({"id": record.stable_id, "locked": operation.locked})
        if record.locked == operation.locked:
            continue
        element.set("Locked", "Y" if operation.locked else "N")
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_component_properties(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetComponentPropertiesOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component", "part"})
    _validate_refdes_change(snapshot, targets, operation.refdes)
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    requested = {
        key: value
        for key, value in {
            "Name": operation.name,
            "Value": operation.value,
            "RefDes": operation.refdes,
        }.items()
        if value is not None
    }
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        before_item: dict[str, Any] = {"id": record.stable_id}
        after_item: dict[str, Any] = {"id": record.stable_id}
        changed = False
        for tag, value in requested.items():
            child = element.find(f"./{tag}")
            previous = child.text or "" if child is not None else ""
            before_item[tag] = previous
            after_item[tag] = value
            if previous == value:
                continue
            if child is None:
                child = ET.SubElement(element, tag)
            child.text = value
            patch_count += 1
            changed = True
        field_before, field_patches = _set_additional_fields(element, operation.fields)
        before_item["fields"] = field_before
        after_item["fields"] = operation.fields
        patch_count += field_patches
        changed = changed or field_patches > 0
        before.append(before_item)
        after.append(after_item)
        if changed:
            changed_ids.append(record.stable_id)
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_component_pattern(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetComponentPatternOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Pattern changes require a PCB document")
    patterns = [
        pattern
        for pattern in snapshot.board.patterns
        if pattern.style == operation.pattern_style
        or pattern.name == operation.pattern_style
        or pattern.unique_name == operation.pattern_style
    ]
    if len(patterns) != 1:
        raise ObjectNotFoundError(
            f"Unique embedded pattern was not found: {operation.pattern_style}",
            details={"matched_count": len(patterns)},
        )
    pattern = patterns[0]
    targets = _select_records(snapshot, operation.selector, {"component"})
    target_numbers = {pad.number or pad.xml_id for pad in pattern.pads}
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        current_pads = element.findall("./Pads/Pad")
        current_numbers = {
            pad.get("Number") or pad.get("Id") or "" for pad in current_pads
        }
        if len(current_pads) != len(pattern.pads) or current_numbers != target_numbers:
            raise EditError(
                f"Pattern {pattern.name!r} does not preserve the pad mapping for "
                f"{record.refdes or record.label}",
                code="connectivity_regression",
                details={
                    "current_pad_numbers": sorted(current_numbers),
                    "target_pad_numbers": sorted(target_numbers),
                },
                object_ids=[record.stable_id],
            )
        previous = element.get("PatternStyle", "")
        target_style = pattern.style or operation.pattern_style
        before.append({"id": record.stable_id, "pattern_style": previous})
        after.append(
            {
                "id": record.stable_id,
                "pattern_style": target_style,
                "pattern_bbox": pattern.bbox,
            }
        )
        if previous == target_style:
            continue
        element.set("PatternStyle", target_style)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_group_components(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: GroupComponentsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "pcb":
        raise CapabilityUnavailableError("PCB grouping requires a PCB document")
    targets = _select_records(snapshot, operation.selector, {"component"})
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
    groups = document.container.find("./Groups")
    patch_count = 0
    if groups is None:
        groups = ET.SubElement(document.container, "Groups")
        patch_count += 1
    existing = groups.findall("./Group")
    group_id = (
        str(operation.group_id)
        if operation.group_id is not None
        else _next_numeric_id(existing)
    )
    group = next((item for item in existing if item.get("Id") == group_id), None)
    if group is None:
        ET.SubElement(groups, "Group", {"Id": group_id, "Selected": "N"})
        patch_count += 1
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    for record in targets:
        element = _resolved_element(snapshot, record)
        previous = element.get("Group", "-1")
        before.append({"id": record.stable_id, "group_id": previous})
        after.append({"id": record.stable_id, "group_id": group_id})
        if previous == group_id:
            continue
        element.set("Group", group_id)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_ungroup_components(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: UngroupComponentsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "pcb":
        raise CapabilityUnavailableError("PCB ungrouping requires a PCB document")
    targets = _select_records(snapshot, operation.selector, {"component"})
    touched_groups: set[str] = set()
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        previous = element.get("Group", "-1")
        before.append({"id": record.stable_id, "group_id": previous})
        after.append({"id": record.stable_id, "group_id": "-1"})
        if previous == "-1":
            continue
        touched_groups.add(previous)
        element.set("Group", "-1")
        changed_ids.append(record.stable_id)
        patch_count += 1
    groups = document.container.find("./Groups")
    if operation.remove_empty_groups and groups is not None:
        used = {
            element.get("Group", "-1")
            for element in document.container.iter()
            if element is not groups and element.get("Group", "-1") != "-1"
        }
        for group in list(groups.findall("./Group")):
            if group.get("Id", "") in touched_groups - used:
                groups.remove(group)
                patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_move_texts(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: MoveBoardTextsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component_text", "board_text"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        if record.position is None:
            raise EditError(
                f"Text has no position: {record.stable_id}",
                code="geometry_invalid",
                object_ids=[record.stable_id],
            )
        previous = Point(**record.position)
        next_point = Point(
            operation.absolute_x if operation.absolute_x is not None else previous.x + operation.dx,
            operation.absolute_y if operation.absolute_y is not None else previous.y + operation.dy,
        )
        before.append({"id": record.stable_id, "position": previous.as_dict()})
        after.append({"id": record.stable_id, "position": next_point.as_dict()})
        if previous == next_point:
            continue
        element = _resolved_element(snapshot, record)
        write_point = next_point
        if record.kind == "component_text":
            write_point = _board_to_component_local(snapshot, record, next_point)
        else:
            point_element = element.find("./Points/*")
            if point_element is None:
                raise EditError(
                    f"Board text has no anchor point: {record.stable_id}",
                    code="geometry_invalid",
                    object_ids=[record.stable_id],
                )
            element = point_element
        element.set("X", f"{from_mm(write_point.x, document.units):.9g}")
        element.set("Y", f"{from_mm(write_point.y, document.units):.9g}")
        changed_ids.append(record.stable_id)
        patch_count += 2
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_rotate_texts(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: RotateBoardTextsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component_text", "board_text"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        previous = _normalize_angle(record.rotation_deg)
        angle = _normalize_angle(
            operation.angle_deg if operation.mode == "absolute" else previous + operation.angle_deg
        )
        before.append({"id": record.stable_id, "rotation_deg": previous})
        after.append({"id": record.stable_id, "rotation_deg": angle})
        if math.isclose(previous, angle, abs_tol=1e-9):
            continue
        _set_angle_attribute(_resolved_element(snapshot, record), angle)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_text_visibility(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetTextVisibilityOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"component_text", "board_text"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        if record.kind == "board_text":
            raise CapabilityUnavailableError(
                "DipTrace PCB XML has no verified visibility attribute for free board text",
                object_ids=[record.stable_id],
            )
        element = _resolved_element(snapshot, record)
        previous = element.get("Show", "Common")
        before.append({"id": record.stable_id, "visibility": previous})
        after.append({"id": record.stable_id, "visibility": operation.visibility})
        if previous == operation.visibility:
            continue
        element.set("Show", operation.visibility)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_text_style(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetTextStyleOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"board_text"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    attributes = {
        "FontSize": operation.font_size,
        "FontWidth": operation.font_width,
        "HorzAlign": operation.horizontal_align,
        "VertAlign": operation.vertical_align,
        "Inverted": None if operation.mirrored is None else ("Y" if operation.mirrored else "N"),
    }
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        element = _resolved_element(snapshot, record)
        before_item: dict[str, Any] = {"id": record.stable_id}
        after_item: dict[str, Any] = {"id": record.stable_id}
        changed = False
        for attribute, value in attributes.items():
            if value is None:
                continue
            rendered = f"{value:g}" if isinstance(value, float) else str(value)
            previous = element.get(attribute)
            before_item[attribute] = previous
            after_item[attribute] = rendered
            if previous == rendered:
                continue
            element.set(attribute, rendered)
            patch_count += 1
            changed = True
        before.append(before_item)
        after.append(after_item)
        if changed:
            changed_ids.append(record.stable_id)
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_pin_no_connect(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetPinNoConnectOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "schematic":
        raise CapabilityUnavailableError("set_pin_no_connect requires a schematic document")
    targets = _select_records(snapshot, operation.selector, {"pin"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    rendered = "Y" if operation.no_connect else "N"
    for record in targets:
        element = _resolved_element(snapshot, record)
        previous = element.get("NotConnected", "N")
        before.append({"id": record.stable_id, "no_connect": previous == "Y"})
        after.append({"id": record.stable_id, "no_connect": operation.no_connect})
        if previous == rendered:
            continue
        element.set("NotConnected", rendered)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _apply_rename_net(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: RenameNetOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    targets = _select_records(snapshot, operation.selector, {"net"})
    target_ids = {record.stable_id for record in targets}
    conflicts = [
        record
        for record in snapshot.objects.values()
        if record.kind == "net"
        and record.stable_id not in target_ids
        and (record.name or "").casefold() == operation.new_name.casefold()
    ]
    if conflicts:
        raise AmbiguousSelectorError(
            f"A net named {operation.new_name!r} already exists",
            object_ids=[record.stable_id for record in conflicts],
        )
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        element = _resolved_element(snapshot, record)
        name_element = element.find("./Name")
        previous = name_element.text or "" if name_element is not None else ""
        before.append({"id": record.stable_id, "name": previous})
        after.append({"id": record.stable_id, "name": operation.new_name})
        if previous == operation.new_name:
            continue
        if name_element is None:
            name_element = ET.SubElement(element, "Name")
        name_element.text = operation.new_name
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _find_net_class(document: DipTraceDocument, class_name: str) -> ET.Element:
    matches = [
        element
        for element in document.container.findall("./NetClasses/NetClass")
        if (element.findtext("./Name") or "").casefold() == class_name.casefold()
        or element.get("Id") == class_name
    ]
    if not matches:
        raise ObjectNotFoundError(f"Net class was not found: {class_name}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(f"Net class selector is ambiguous: {class_name}")
    return matches[0]


def _apply_net_class_rules(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: UpdateNetClassRulesOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "pcb":
        raise CapabilityUnavailableError("Net class rule edits require a PCB document")
    net_class = _find_net_class(document, operation.class_name)
    net_class_id = net_class.get("Id", operation.class_name)
    changed_id = stable_id("net-class", document.source_type, f"xml:{net_class_id}")
    before: dict[str, Any] = {
        "id": changed_id,
        "attributes": dict(net_class.attrib),
        "layers": [],
    }
    after: dict[str, Any] = {"id": changed_id, "attributes": {}, "layers": []}
    patch_count = 0
    class_attributes: dict[str, float | bool | None] = {
        "MaxUncoupledLength": operation.max_uncoupled_length,
        "Tolerance": operation.tolerance,
        "CheckLength": operation.check_length,
        "FixedLength": operation.fixed_length,
        "LengthDelta": operation.length_delta,
    }
    for attribute, value in class_attributes.items():
        if value is None:
            continue
        rendered = (
            "Y"
            if value is True
            else "N"
            if value is False
            else f"{from_mm(float(value), document.units):.9g}"
        )
        if net_class.get(attribute) != rendered:
            net_class.set(attribute, rendered)
            patch_count += 1
    layer_properties = net_class.findall("./LayProperties/LayProperty")
    layer_values: dict[str, float | None] = {
        "Width": operation.width,
        "MinWidth": operation.min_width,
        "MaxWidth": operation.max_width,
        "Clearance": operation.clearance,
        "Neck_Width": operation.neck_width,
        "DifClearance": operation.differential_gap,
    }
    if any(value is not None for value in layer_values.values()):
        if not layer_properties:
            raise CapabilityUnavailableError(
                "The selected net class has no verified LayProperties structure"
            )
        selected_layers = [
            layer
            for layer in layer_properties
            if operation.layer is None
            or (layer.findtext("./LayerName") or "").casefold()
            == operation.layer.casefold()
        ]
        if not selected_layers:
            raise ObjectNotFoundError(
                f"Layer {operation.layer!r} is absent from net class {operation.class_name!r}"
            )
        for layer in selected_layers:
            layer_name = layer.findtext("./LayerName") or ""
            before["layers"].append({"name": layer_name, "attributes": dict(layer.attrib)})
            for attribute, value in layer_values.items():
                if value is None:
                    continue
                rendered = f"{from_mm(value, document.units):.9g}"
                if layer.get(attribute) != rendered:
                    layer.set(attribute, rendered)
                    patch_count += 1
            after["layers"].append({"name": layer_name, "attributes": dict(layer.attrib)})
    after["attributes"] = dict(net_class.attrib)
    if patch_count:
        changed_ids.append(changed_id)
    target = ObjectRecord(stable_id=changed_id, kind="net_class", label=operation.class_name)
    return _operation_preview(
        index, operation.kind, [target], [before], [after], document
    ), patch_count


def _apply_assign_nets_to_class(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AssignNetsToClassOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    net_class = _find_net_class(document, operation.class_name)
    class_id = net_class.get("Id")
    if class_id is None:
        raise EditError(f"Net class has no Id: {operation.class_name}")
    targets = _select_records(snapshot, operation.selector, {"net"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        element = _resolved_element(snapshot, record)
        previous = element.get("NetClass", "")
        before.append({"id": record.stable_id, "net_class": previous})
        after.append({"id": record.stable_id, "net_class": class_id})
        if previous == class_id:
            continue
        element.set("NetClass", class_id)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(index, operation.kind, targets, before, after, document), patch_count


def _next_numeric_id(elements: list[ET.Element]) -> str:
    numeric = [int(value) for element in elements if (value := element.get("Id", "")).isdigit()]
    return str(max(numeric, default=-1) + 1)


def _next_testpoint_refdes(snapshot: DocumentSnapshot) -> str:
    used = {
        record.refdes.casefold()
        for record in snapshot.objects.values()
        if record.refdes is not None
    }
    number = 1
    while f"tp{number}" in used:
        number += 1
    return f"TP{number}"


def _require_testpoint_position(snapshot: DocumentSnapshot, point: Point, diameter: float) -> None:
    if snapshot.board is None or snapshot.board.outline is None:
        raise EditError("Board outline is required to add a testpoint", code="geometry_invalid")
    polygon = [Point(**item) for item in snapshot.board.outline.get("points", [])]
    if not point_in_polygon(point, polygon):
        raise EditError(
            "Testpoint center is outside the board outline",
            code="placement_illegal",
            details={"position": point.as_dict()},
        )
    candidate = {
        "min_x": point.x - diameter / 2.0,
        "min_y": point.y - diameter / 2.0,
        "max_x": point.x + diameter / 2.0,
        "max_y": point.y + diameter / 2.0,
    }
    for record in snapshot.objects.values():
        if record.kind not in {"component", "testpoint"} or record.bbox is None:
            continue
        if not (
            candidate["max_x"] < record.bbox["min_x"]
            or candidate["min_x"] > record.bbox["max_x"]
            or candidate["max_y"] < record.bbox["min_y"]
            or candidate["min_y"] > record.bbox["max_y"]
        ):
            raise EditError(
                f"Testpoint overlaps {record.label or record.stable_id}",
                code="placement_illegal",
                object_ids=[record.stable_id],
            )


def _apply_add_testpoint(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddTestpointOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "pcb":
        raise CapabilityUnavailableError("Testpoints require a PCB document")
    net_targets = snapshot.select(QuerySelector(names=[operation.net]), kinds={"net"})
    if not net_targets:
        net_targets = snapshot.select(QuerySelector(ids=[operation.net]), kinds={"net"})
    if not net_targets:
        raise ObjectNotFoundError(f"Net was not found: {operation.net}")
    if len(net_targets) != 1:
        raise AmbiguousSelectorError(f"Net selector is ambiguous: {operation.net}")
    net_record = net_targets[0]
    net_element = _resolved_element(snapshot, net_record)
    point = Point(operation.x, operation.y)
    _require_testpoint_position(snapshot, point, operation.pad_diameter)
    refdes = operation.refdes or _next_testpoint_refdes(snapshot)
    if any(
        (record.refdes or "").casefold() == refdes.casefold()
        for record in snapshot.objects.values()
    ):
        raise AmbiguousSelectorError(f"RefDes already exists: {refdes}")

    components = document.container.find("./Components")
    if components is None:
        components = ET.SubElement(document.container, "Components")
    component_id = _next_numeric_id(components.findall("./Component"))
    pattern_style = f"MCPTestPoint{component_id}"
    pad_style = f"MCPTestPointPad{component_id}"
    pattern_library = document.root.find("./Library[@Type='DipTrace-PatternLibrary']")
    if pattern_library is None:
        pattern_library = ET.Element(
            "Library",
            {
                "Type": "DipTrace-PatternLibrary",
                "Version": document.version,
                "Units": document.units,
            },
        )
        document.root.insert(0, pattern_library)
    pad_styles = pattern_library.find("./PadStyles")
    if pad_styles is None:
        pad_styles = ET.SubElement(pattern_library, "PadStyles")
    style_attributes = {
        "Name": pad_style,
        "Type": "Through" if operation.hole_diameter > 0 else "Surface",
        "Side": operation.side,
    }
    if operation.hole_diameter > 0:
        style_attributes.update(
            {"HoleType": "Round", "Hole": f"{from_mm(operation.hole_diameter, document.units):.9g}"}
        )
    style = ET.SubElement(pad_styles, "PadStyle", style_attributes)
    ET.SubElement(
        style,
        "MainStack",
        {
            "Shape": "Ellipse",
            "Width": f"{from_mm(operation.pad_diameter, document.units):.9g}",
            "Height": f"{from_mm(operation.pad_diameter, document.units):.9g}",
            "XOff": "0",
            "YOff": "0",
        },
    )
    patterns = pattern_library.find("./Patterns")
    if patterns is None:
        patterns = ET.SubElement(pattern_library, "Patterns")
    pattern = ET.SubElement(
        patterns,
        "Pattern",
        {
            "PatternStyle": pattern_style,
            "RefDes": "TP",
            "Mounting": "Through" if operation.hole_diameter > 0 else "SMD",
            "Width": f"{from_mm(operation.pad_diameter, document.units):.9g}",
            "Height": f"{from_mm(operation.pad_diameter, document.units):.9g}",
            "Orientation": "0",
            "Type": "Free",
        },
    )
    ET.SubElement(pattern, "Name").text = "MCP_TESTPOINT"
    ET.SubElement(pattern, "Name_Unique").text = pattern_style
    ET.SubElement(pattern, "Origin", {"X": "0", "Y": "0"})
    ET.SubElement(pattern, "DefPad", {"Style": pad_style})
    pattern_pads = ET.SubElement(pattern, "Pads")
    pattern_pad = ET.SubElement(
        pattern_pads,
        "Pad",
        {"Id": "0", "Style": pad_style, "X": "0", "Y": "0", "Locked": "N", "Side": operation.side},
    )
    ET.SubElement(pattern_pad, "Number").text = "1"

    component = ET.SubElement(
        components,
        "Component",
        {
            "Id": component_id,
            "UpdateId": "-1",
            "Type": "Pad",
            "PatternStyle": pattern_style,
            "X": f"{from_mm(point.x, document.units):.9g}",
            "Y": f"{from_mm(point.y, document.units):.9g}",
            "Side": operation.side,
            "Locked": "N",
            "Selected": "N",
        },
    )
    ET.SubElement(component, "RefDes").text = refdes
    ET.SubElement(component, "Name").text = "MCP_TESTPOINT"
    ET.SubElement(component, "Value").text = net_record.name or operation.net
    _set_additional_fields(
        component,
        {
            "MCP.TestpointDiameterMm": f"{operation.pad_diameter:.9g}",
            "MCP.TestpointHoleMm": f"{operation.hole_diameter:.9g}",
        },
    )
    component_pads = ET.SubElement(component, "Pads")
    ET.SubElement(
        component_pads,
        "Pad",
        {"Id": "0", "NetId": net_record.xml_id or "-1", "InternalConnection": "-1"},
    )
    net_pads = net_element.find("./Pads")
    if net_pads is None:
        net_pads = ET.SubElement(net_element, "Pads")
    ET.SubElement(net_pads, "Item", {"Comp": component_id, "Pad": "0"})

    testpoint_id = stable_id("testpoint", document.source_type, f"xml:{component_id}")
    changed_ids.append(testpoint_id)
    target = ObjectRecord(
        stable_id=testpoint_id,
        kind="testpoint",
        label=refdes,
        refdes=refdes,
        net_id=net_record.xml_id,
        net_name=net_record.name,
        side=operation.side,
        position=point.as_dict(),
    )
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [],
        [
            {
                "id": testpoint_id,
                "refdes": refdes,
                "position": point.as_dict(),
                "net": net_record.name,
            }
        ],
        document,
    ), 6


def _apply_remove_testpoints(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: RemoveTestpointsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    if document.kind != "pcb":
        raise CapabilityUnavailableError("Testpoints require a PCB document")
    targets = _select_records(snapshot, operation.selector, {"testpoint"})
    components = document.container.find("./Components")
    if components is None:
        raise ObjectNotFoundError("PCB Components section is absent")
    before: list[dict[str, Any]] = []
    patch_count = 0
    pattern_library = document.root.find("./Library[@Type='DipTrace-PatternLibrary']")
    for record in targets:
        _ensure_unlocked(record, operation.allow_locked)
        component = _resolved_element(snapshot, record)
        xml_id = component.get("Id", "")
        pattern_style = component.get("PatternStyle", "")
        before.append(record.model_dump())
        for net in document.container.findall("./Nets/Net"):
            pads = net.find("./Pads")
            if pads is None:
                continue
            for item in list(pads.findall("./Item")):
                if item.get("Comp") == xml_id:
                    pads.remove(item)
                    patch_count += 1
        components.remove(component)
        patch_count += 1
        if pattern_library is not None and pattern_style.startswith("MCPTestPoint"):
            patterns = pattern_library.find("./Patterns")
            pad_styles = pattern_library.find("./PadStyles")
            if patterns is not None:
                for pattern in list(patterns.findall("./Pattern")):
                    if pattern.get("PatternStyle") == pattern_style:
                        default_pad = pattern.find("./DefPad")
                        style_name = default_pad.get("Style", "") if default_pad is not None else ""
                        patterns.remove(pattern)
                        patch_count += 1
                        if pad_styles is not None:
                            for style in list(pad_styles.findall("./PadStyle")):
                                if style.get("Name") == style_name:
                                    pad_styles.remove(style)
                                    patch_count += 1
        changed_ids.append(record.stable_id)
    return _operation_preview(index, operation.kind, targets, before, [], document), patch_count


def _ensure_unlocked(record: ObjectRecord, allow_locked: bool) -> None:
    if record.locked and not allow_locked:
        raise LockedObjectError(
            f"Object is locked: {record.label or record.stable_id}",
            object_ids=[record.stable_id],
        )


def _normalize_angle(angle_deg: float) -> float:
    normalized = angle_deg % 360.0
    return 0.0 if math.isclose(normalized, 360.0, abs_tol=1e-9) else normalized


def _set_angle_attribute(element: ET.Element, angle_deg: float) -> None:
    angle_rad = math.radians(_normalize_angle(angle_deg))
    if math.isclose(angle_rad, 0.0, abs_tol=1e-12):
        element.attrib.pop("Angle", None)
    else:
        element.set("Angle", f"{angle_rad:.9g}")


def _validate_refdes_change(
    snapshot: DocumentSnapshot,
    targets: list[ObjectRecord],
    new_refdes: str | None,
) -> None:
    if new_refdes is None:
        return
    target_ids = {record.stable_id for record in targets}
    conflicts = [
        record
        for record in snapshot.objects.values()
        if record.kind in {"component", "part"}
        and record.stable_id not in target_ids
        and (record.refdes or "").casefold() == new_refdes.casefold()
    ]
    target_refdes = {(record.refdes or "").casefold() for record in targets}
    if conflicts or (len(targets) > 1 and len(target_refdes) > 1):
        raise AmbiguousSelectorError(
            f"RefDes {new_refdes!r} would not be unique",
            object_ids=[record.stable_id for record in conflicts or targets],
        )


def _set_additional_fields(
    element: ET.Element,
    fields: dict[str, str],
) -> tuple[dict[str, str], int]:
    if not fields:
        return {}, 0
    container = element.find("./AddFields")
    existing: dict[str, ET.Element] = {}
    before: dict[str, str] = {}
    if container is not None:
        for existing_field in container.findall("./AddField"):
            name = (existing_field.findtext("./Name") or "").strip()
            if name:
                existing[name] = existing_field
                before[name] = existing_field.findtext("./Text") or ""
    patch_count = 0
    for name, value in fields.items():
        field_element = existing.get(name)
        if field_element is None:
            if container is None:
                container = ET.SubElement(element, "AddFields")
            field_element = ET.SubElement(container, "AddField", {"Type": "Text"})
            ET.SubElement(field_element, "Name").text = name
            ET.SubElement(field_element, "Text").text = value
            patch_count += 1
            continue
        text_element = field_element.find("./Text")
        previous = text_element.text or "" if text_element is not None else ""
        if previous == value:
            continue
        if text_element is None:
            text_element = ET.SubElement(field_element, "Text")
        text_element.text = value
        patch_count += 1
    return before, patch_count


def _board_to_component_local(
    snapshot: DocumentSnapshot,
    text_record: ObjectRecord,
    board_point: Point,
) -> Point:
    if not text_record.parent_id:
        raise EditError(
            f"Component text has no parent component: {text_record.stable_id}",
            code="geometry_invalid",
            object_ids=[text_record.stable_id],
        )
    parent = snapshot.get_object(text_record.parent_id)
    if parent.position is None:
        raise EditError(
            f"Parent component has no position: {parent.stable_id}",
            code="geometry_invalid",
            object_ids=[parent.stable_id],
        )
    transform = Transform(
        translate_x=parent.position["x"],
        translate_y=parent.position["y"],
        rotation_deg=parent.rotation_deg,
        mirror_x=parent.side == "Bottom",
    )
    return transform.inverse().apply_point(board_point)


def _resolved_element(snapshot: DocumentSnapshot, record: ObjectRecord) -> ET.Element:
    element = snapshot.elements.get(record.stable_id)
    if element is None:
        raise EditError(
            f"Cannot resolve XML element for {record.stable_id}",
            object_ids=[record.stable_id],
        )
    return element


def _operation_preview(
    index: int,
    kind: str,
    targets: list[ObjectRecord],
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    document: DipTraceDocument,
) -> dict[str, Any]:
    return {
        "index": index,
        "kind": kind,
        "target_ids": [record.stable_id for record in targets],
        "before": before,
        "after": after,
        "source_sha256": document.sha256,
    }
