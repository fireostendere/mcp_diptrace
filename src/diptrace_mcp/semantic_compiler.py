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
    AddNetLabelOperation,
    AddSheetOperation,
    AddTestpointOperation,
    AddWireOperation,
    AssignNetsToClassOperation,
    ClearPanelizationOperation,
    ConnectPinsOperation,
    DeleteWireOperation,
    DisconnectPinsOperation,
    GroupComponentsOperation,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    PlacePartOperation,
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
    SetPanelizationOperation,
    SetPinNoConnectOperation,
    SetTextStyleOperation,
    SetTextVisibilityOperation,
    SyncSchematicToPcbOperation,
    UngroupComponentsOperation,
    UpdateNetClassRulesOperation,
    WireEndpoint,
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
        elif isinstance(operation, AddSheetOperation):
            preview, patches = _apply_add_sheet(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, PlacePartOperation):
            preview, patches = _apply_place_part(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SyncSchematicToPcbOperation):
            preview, patches = _apply_sync_schematic_to_pcb(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, ConnectPinsOperation):
            preview, patches = _apply_connect_pins(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, DisconnectPinsOperation):
            preview, patches = _apply_disconnect_pins(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, AddWireOperation):
            preview, patches = _apply_add_wire(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, DeleteWireOperation):
            preview, patches = _apply_delete_wire(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, AddNetLabelOperation):
            preview, patches = _apply_add_net_label(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, SetPanelizationOperation):
            preview, patches = _apply_set_panelization(
                index, working, snapshot, operation, changed_ids
            )
        elif isinstance(operation, ClearPanelizationOperation):
            preview, patches = _apply_clear_panelization(
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
    if not patterns:
        if operation.validation_mode == "strict_embedded_pattern":
            raise ObjectNotFoundError(
                f"Unique embedded pattern was not found: {operation.pattern_style}",
                details={"matched_count": 0, "validation_mode": operation.validation_mode},
            )
        # external_pattern_reference: warn but proceed
        targets = _select_records(snapshot, operation.selector, {"component"})
        warnings = [
            (
                f"Pattern {operation.pattern_style!r} is not in the embedded library; "
                "external pattern resolution is required in DipTrace"
            )
            for _ in targets
        ]
        return (
            _operation_preview(
                index,
                operation.kind,
                targets,
                [{"pattern_style": operation.pattern_style}] * len(targets),
                [
                    {
                        "pattern_style": operation.pattern_style,
                        "warning": "external_pattern_reference",
                    }
                ]
                * len(targets),
                document,
            ),
            0,
        )
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
                    "current_pad_count": len(current_pads),
                    "target_pad_count": len(pattern.pads),
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


# ---------------------------------------------------------------------------
# Schematic authoring and panelization handlers
# ---------------------------------------------------------------------------


def _require_schematic(document: DipTraceDocument, feature: str) -> None:
    if document.kind != "schematic":
        raise CapabilityUnavailableError(f"{feature} requires a schematic document")


def _require_pcb(document: DipTraceDocument, feature: str) -> None:
    if document.kind != "pcb":
        raise CapabilityUnavailableError(f"{feature} requires a PCB document")


def _sheet_ids(document: DipTraceDocument) -> list[str]:
    return [
        sheet_id
        for sheet in document.container.findall("./SheetSettings/Sheets/Sheet")
        if (sheet_id := sheet.findtext("./Id")) is not None
    ]


def _require_sheet(document: DipTraceDocument, sheet: int) -> None:
    if str(sheet) not in _sheet_ids(document):
        raise ObjectNotFoundError(f"Sheet was not found: {sheet}")


def _xml_locked(element: ET.Element) -> bool:
    return element.get("Locked", "N").strip().casefold() in {"y", "yes", "true", "1"}


def _require_reconciliation_unlocked(
    element: ET.Element,
    label: str,
    *,
    allow_locked: bool,
) -> None:
    if _xml_locked(element) and not allow_locked:
        raise LockedObjectError(
            f"Exact schematic-to-PCB reconciliation would modify locked {label}; "
            "set allow_locked_reconciliation=true to authorize it"
        )


def _sync_endpoint_key(
    component_by_refdes: dict[str, ET.Element],
    refdes: str,
    pad_number: str,
) -> tuple[str, str]:
    key, _pad = _sync_endpoint(component_by_refdes, refdes, pad_number)
    return key


def _sync_endpoint(
    component_by_refdes: dict[str, ET.Element],
    refdes: str,
    pad_number: str,
) -> tuple[tuple[str, str], ET.Element]:
    component = component_by_refdes.get(refdes.casefold())
    if component is None:
        raise ObjectNotFoundError(f"Synchronized PCB component was not found: {refdes}")
    matching_pads = [
        pad
        for pad in component.findall("./Pads/Pad")
        if (pad.get("Number") or pad.get("Id") or "").casefold()
        == pad_number.casefold()
    ]
    if len(matching_pads) != 1:
        raise EditError(f"Cannot resolve unique pad {refdes}:{pad_number}")
    pad = matching_pads[0]
    return (component.get("Id", ""), pad.get("Id", "")), pad


def _apply_sync_schematic_to_pcb(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SyncSchematicToPcbOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_pcb(document, "sync_schematic_to_pcb")
    patch_count = 0
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []

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
        patch_count += 1
    patterns = pattern_library.find("./Patterns")
    if patterns is None:
        patterns = ET.SubElement(pattern_library, "Patterns")
        patch_count += 1
    pad_styles = pattern_library.find("./PadStyles")
    if pad_styles is None:
        pad_styles = ET.Element("PadStyles")
        pattern_library.insert(0, pad_styles)
        patch_count += 1
    existing_pattern_styles = {
        (item.get("PatternStyle") or item.get("Style") or "").casefold()
        for item in patterns.findall("./Pattern")
    }
    existing_pad_styles = {
        (item.get("Name") or "").casefold() for item in pad_styles.findall("./PadStyle")
    }
    for raw in operation.pad_style_xml:
        element = ET.fromstring(raw)
        if element.tag != "PadStyle" or not element.get("Name"):
            raise EditError("Schematic sync contains an invalid PadStyle definition")
        key = str(element.get("Name")).casefold()
        if key not in existing_pad_styles:
            pad_styles.append(element)
            existing_pad_styles.add(key)
            patch_count += 1
    for raw in operation.pattern_xml:
        element = ET.fromstring(raw)
        style = element.get("PatternStyle") or element.get("Style")
        if element.tag != "Pattern" or not style:
            raise EditError("Schematic sync contains an invalid Pattern definition")
        key = style.casefold()
        if key not in existing_pattern_styles:
            patterns.append(element)
            existing_pattern_styles.add(key)
            patch_count += 1

    components = document.container.find("./Components")
    if components is None:
        components = ET.SubElement(document.container, "Components")
        patch_count += 1
    existing_components: dict[str, ET.Element] = {}
    for existing_component in components.findall("./Component"):
        refdes = (existing_component.findtext("./RefDes") or "").strip()
        if not refdes:
            continue
        key = refdes.casefold()
        if key in existing_components:
            raise AmbiguousSelectorError(f"PCB contains duplicate RefDes: {refdes}")
        existing_components[key] = existing_component
    next_component_id = int(_next_numeric_id(components.findall("./Component")))
    update_ids = [
        int(value)
        for item in components.findall("./Component")
        if (value := item.get("UpdateId", "")).lstrip("-").isdigit()
    ]
    next_update_id = max(update_ids, default=99) + 1
    component_by_refdes: dict[str, ET.Element] = {}

    for spec in operation.components:
        key = spec.refdes.casefold()
        target_component = existing_components.get(key)
        if target_component is None:
            component_id = str(next_component_id)
            next_component_id += 1
            target_component = ET.SubElement(
                components,
                "Component",
                {
                    "Id": component_id,
                    "UpdateId": str(next_update_id),
                    "PatternStyle": spec.pattern_style,
                    "X": f"{from_mm(spec.x, document.units):.9g}",
                    "Y": f"{from_mm(spec.y, document.units):.9g}",
                    "Side": spec.side,
                    "Locked": "N",
                    "Selected": "N",
                },
            )
            next_update_id += 1
            ET.SubElement(target_component, "RefDes").text = spec.refdes
            ET.SubElement(target_component, "Name").text = spec.name
            ET.SubElement(target_component, "Value").text = spec.value
            _, field_patches = _set_additional_fields(target_component, spec.fields)
            component_pads = ET.SubElement(target_component, "Pads")
            for pad_index, number in enumerate(spec.pad_numbers):
                ET.SubElement(
                    component_pads,
                    "Pad",
                    {
                        "Id": str(pad_index),
                        "Number": number,
                        "NetId": "-1",
                        "InternalConnection": "-1",
                    },
                )
            stable = stable_id(
                "component", document.source_type, f"xml:{component_id}"
            )
            changed_ids.append(stable)
            after.append(
                {
                    "id": stable,
                    "refdes": spec.refdes,
                    "action": "created",
                    "pattern_style": spec.pattern_style,
                    "pad_count": len(spec.pad_numbers),
                }
            )
            patch_count += 1 + field_patches
        else:
            stable = _element_stable_id(
                snapshot,
                target_component,
                stable_id(
                    "component",
                    document.source_type,
                    f"xml:{target_component.get('Id', '')}",
                ),
            )
            before.append(
                {
                    "id": stable,
                    "refdes": spec.refdes,
                    "name": target_component.findtext("./Name") or "",
                    "value": target_component.findtext("./Value") or "",
                }
            )
            current_pattern = target_component.get("PatternStyle", "")
            if current_pattern.casefold() != spec.pattern_style.casefold():
                raise EditError(
                    f"Existing PCB component {spec.refdes} uses pattern {current_pattern!r}, "
                    f"not {spec.pattern_style!r}"
                )
            pads = target_component.findall("./Pads/Pad")
            available_numbers = {
                (pad.get("Number") or pad.get("Id") or "").casefold() for pad in pads
            }
            missing_numbers = [
                number
                for number in spec.pad_numbers
                if number.casefold() not in available_numbers
            ]
            if missing_numbers:
                raise EditError(
                    f"Existing PCB component {spec.refdes} lacks mapped pads",
                    details={"missing_pad_numbers": missing_numbers},
                )
            component_patches = 0
            if operation.update_existing_properties:
                for tag, value in (("Name", spec.name), ("Value", spec.value)):
                    child = target_component.find(f"./{tag}")
                    if child is None:
                        child = ET.SubElement(target_component, tag)
                    if (child.text or "") != value:
                        child.text = value
                        component_patches += 1
                _, field_patches = _set_additional_fields(target_component, spec.fields)
                component_patches += field_patches
            if component_patches:
                changed_ids.append(stable)
                patch_count += component_patches
                after.append(
                    {"id": stable, "refdes": spec.refdes, "action": "updated"}
                )
        component_by_refdes[key] = target_component

    if operation.reconciliation_mode == "exact":
        desired_component_keys = {item.refdes.casefold() for item in operation.components}
        for key, extra_component in list(existing_components.items()):
            if key in desired_component_keys:
                continue
            refdes = (extra_component.findtext("./RefDes") or "").strip() or key
            _require_reconciliation_unlocked(
                extra_component,
                f"component {refdes}",
                allow_locked=operation.allow_locked_reconciliation,
            )
            component_id = extra_component.get("Id", "")
            stable = stable_id(
                "component", document.source_type, f"xml:{component_id}"
            )
            before.append(
                {
                    "id": stable,
                    "refdes": refdes,
                    "action": "removed_by_exact_reconciliation",
                }
            )
            changed_ids.append(stable)
            components.remove(extra_component)
            del existing_components[key]
            patch_count += 1

    nets_container = document.container.find("./Nets")
    if nets_container is None:
        nets_container = ET.SubElement(document.container, "Nets")
        patch_count += 1
    existing_nets: dict[str, ET.Element] = {}
    for existing_net in nets_container.findall("./Net"):
        name = (existing_net.findtext("./Name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in existing_nets:
            raise AmbiguousSelectorError(f"PCB contains duplicate net name: {name}")
        existing_nets[key] = existing_net

    desired_endpoints_by_net = {
        net_spec.name.casefold(): [
            _sync_endpoint_key(
                component_by_refdes,
                endpoint.refdes,
                endpoint.pad_number,
            )
            for endpoint in net_spec.endpoints
        ]
        for net_spec in operation.nets
    }
    if operation.reconciliation_mode == "exact":
        desired_net_keys = set(desired_endpoints_by_net)
        for key, extra_net in list(existing_nets.items()):
            if key in desired_net_keys:
                continue
            net_name = (extra_net.findtext("./Name") or "").strip() or key
            _require_reconciliation_unlocked(
                extra_net,
                f"net {net_name}",
                allow_locked=operation.allow_locked_reconciliation,
            )
            for trace in extra_net.findall("./Traces/Trace"):
                _require_reconciliation_unlocked(
                    trace,
                    f"trace on net {net_name}",
                    allow_locked=operation.allow_locked_reconciliation,
                )
            net_id = extra_net.get("Id", "")
            stable = stable_id("net", document.source_type, f"xml:{net_id}")
            before.append(
                {
                    "id": stable,
                    "net": net_name,
                    "action": "removed_by_exact_reconciliation",
                }
            )
            changed_ids.append(stable)
            nets_container.remove(extra_net)
            del existing_nets[key]
            patch_count += 1

        for key, target_net in existing_nets.items():
            desired_endpoints = desired_endpoints_by_net.get(key)
            if desired_endpoints is None:
                continue
            net_pads = target_net.find("./Pads")
            current_items = net_pads.findall("./Item") if net_pads is not None else []
            current_endpoints = [
                (item.get("Comp", ""), item.get("Pad", "")) for item in current_items
            ]
            if set(current_endpoints) == set(desired_endpoints):
                continue
            net_name = (target_net.findtext("./Name") or "").strip() or key
            _require_reconciliation_unlocked(
                target_net,
                f"net {net_name}",
                allow_locked=operation.allow_locked_reconciliation,
            )
            traces = target_net.find("./Traces")
            trace_elements = traces.findall("./Trace") if traces is not None else []
            for trace in trace_elements:
                _require_reconciliation_unlocked(
                    trace,
                    f"trace on changed net {net_name}",
                    allow_locked=operation.allow_locked_reconciliation,
                )
            if net_pads is None:
                net_pads = ET.SubElement(target_net, "Pads")
                patch_count += 1
            for item in current_items:
                net_pads.remove(item)
                patch_count += 1
            for component_id, pad_id in desired_endpoints:
                ET.SubElement(net_pads, "Item", {"Comp": component_id, "Pad": pad_id})
                patch_count += 1
            if traces is not None:
                for trace in trace_elements:
                    traces.remove(trace)
                    patch_count += 1
            net_id = target_net.get("Id", "")
            stable = stable_id("net", document.source_type, f"xml:{net_id}")
            changed_ids.append(stable)
            after.append(
                {
                    "id": stable,
                    "net": net_name,
                    "action": "exact_connectivity_reconciled",
                    "removed_trace_count": len(trace_elements),
                }
            )

        desired_ratline_pairs = {
            frozenset({first, second})
            for endpoints in desired_endpoints_by_net.values()
            for first, second in zip(endpoints, endpoints[1:], strict=False)
            if first != second
        }
        ratlines = document.container.find("./Ratlines")
        if ratlines is not None:
            for ratline in list(ratlines.findall("./Ratline")):
                pair = frozenset(
                    {
                        (ratline.get("Comp1", ""), ratline.get("Pad1", "")),
                        (ratline.get("Comp2", ""), ratline.get("Pad2", "")),
                    }
                )
                if not operation.create_ratlines or pair not in desired_ratline_pairs:
                    ratlines.remove(ratline)
                    patch_count += 1

    next_net_id = int(_next_numeric_id(nets_container.findall("./Net")))
    endpoint_nets: dict[tuple[str, str], ET.Element] = {}
    for existing_net in nets_container.findall("./Net"):
        for item in existing_net.findall("./Pads/Item"):
            endpoint_nets[(item.get("Comp", ""), item.get("Pad", ""))] = existing_net

    requested_ratlines: list[tuple[str, list[tuple[str, str]]]] = []
    for net_spec in operation.nets:
        sync_net = existing_nets.get(net_spec.name.casefold())
        net_was_created = sync_net is None
        if sync_net is None:
            net_id = str(next_net_id)
            next_net_id += 1
            sync_net = ET.SubElement(
                nets_container,
                "Net",
                {"Id": net_id, "NetClass": "0", "Locked": "N"},
            )
            ET.SubElement(sync_net, "Name").text = net_spec.name
            ET.SubElement(sync_net, "Pads")
            ET.SubElement(sync_net, "Traces")
            existing_nets[net_spec.name.casefold()] = sync_net
            stable = stable_id("net", document.source_type, f"xml:{net_id}")
            changed_ids.append(stable)
            after.append(
                {"id": stable, "net": net_spec.name, "action": "created"}
            )
            patch_count += 1
        net_stable = stable_id(
            "net", document.source_type, f"xml:{sync_net.get('Id', '')}"
        )
        net_changed = net_was_created
        pads_container = sync_net.find("./Pads")
        if pads_container is None:
            pads_container = ET.SubElement(sync_net, "Pads")
            patch_count += 1
            net_changed = True
        preexisting_endpoints = [
            (item.get("Comp", ""), item.get("Pad", ""))
            for item in pads_container.findall("./Item")
        ]
        added_endpoints: list[tuple[str, str]] = []
        for endpoint in net_spec.endpoints:
            endpoint_key, component_pad = _sync_endpoint(
                component_by_refdes,
                endpoint.refdes,
                endpoint.pad_number,
            )
            current_net = endpoint_nets.get(endpoint_key)
            if current_net is not None and current_net is not sync_net:
                current_name = (current_net.findtext("./Name") or "").strip()
                if not operation.allow_reconnect:
                    raise EditError(
                        f"PCB endpoint {endpoint.refdes}:{endpoint.pad_number} is already "
                        f"connected to {current_name}; set allow_reconnect=true to move it"
                    )
                if current_net.findall("./Traces/Trace"):
                    raise EditError(
                        f"Cannot reconnect routed endpoint {endpoint.refdes}:{endpoint.pad_number}"
                    )
                old_pads = current_net.find("./Pads")
                if old_pads is not None:
                    for item in list(old_pads.findall("./Item")):
                        if (item.get("Comp"), item.get("Pad")) == endpoint_key:
                            old_pads.remove(item)
                            patch_count += 1
                            net_changed = True
                endpoint_nets.pop(endpoint_key, None)
            if endpoint_key not in endpoint_nets:
                ET.SubElement(
                    pads_container,
                    "Item",
                    {"Comp": endpoint_key[0], "Pad": endpoint_key[1]},
                )
                endpoint_nets[endpoint_key] = sync_net
                patch_count += 1
                net_changed = True
                added_endpoints.append(endpoint_key)
            net_id = sync_net.get("Id", "")
            if component_pad.get("NetId") != net_id:
                component_pad.set("NetId", net_id)
                patch_count += 1
                net_changed = True
            if component_pad.get("InternalConnection") is None:
                component_pad.set("InternalConnection", "-1")
                patch_count += 1
                net_changed = True
        if operation.reconciliation_mode == "exact":
            requested_ratlines.append(
                (net_spec.name, desired_endpoints_by_net[net_spec.name.casefold()])
            )
        elif added_endpoints:
            ratline_endpoints = (
                added_endpoints
                if not preexisting_endpoints
                else [preexisting_endpoints[0], *added_endpoints]
            )
            requested_ratlines.append((net_spec.name, ratline_endpoints))
        if net_changed and net_stable not in changed_ids:
            changed_ids.append(net_stable)
            if not net_was_created:
                after.append(
                    {
                        "id": net_stable,
                        "net": net_spec.name,
                        "action": "connectivity_updated",
                    }
                )

    # DipTrace stores net membership in both Net/Pads/Item and Component/Pads/Pad.
    # Keep those representations reciprocal, including pads left unconnected by an
    # exact reconciliation.  Omitting these attributes can make otherwise well-formed
    # XML fail native import or force DipTrace to rebuild its ratline structure.
    for component in component_by_refdes.values():
        component_id = component.get("Id", "")
        for pad in component.findall("./Pads/Pad"):
            endpoint_key = (component_id, pad.get("Id", ""))
            endpoint_net = endpoint_nets.get(endpoint_key)
            expected_net_id = (
                endpoint_net.get("Id", "") if endpoint_net is not None else "-1"
            )
            if pad.get("NetId") != expected_net_id:
                pad.set("NetId", expected_net_id)
                patch_count += 1
            if pad.get("InternalConnection") is None:
                pad.set("InternalConnection", "-1")
                patch_count += 1

    if operation.create_ratlines:
        ratlines = document.container.find("./Ratlines")
        if ratlines is None:
            ratlines = ET.SubElement(document.container, "Ratlines")
            patch_count += 1
        existing_pairs = {
            frozenset(
                {
                    (item.get("Comp1", ""), item.get("Pad1", "")),
                    (item.get("Comp2", ""), item.get("Pad2", "")),
                }
            )
            for item in ratlines.findall("./Ratline")
        }
        next_ratline_id = int(_next_numeric_id(ratlines.findall("./Ratline")))
        positioned_snapshot = build_snapshot(document)
        pad_positions: dict[tuple[str, str], Point] = {}
        for component_record in positioned_snapshot.objects.values():
            if (
                component_record.kind not in {"component", "testpoint"}
                or not component_record.xml_id
            ):
                continue
            for pad_stable in component_record.relationships.get("pads", []):
                pad = positioned_snapshot.objects.get(pad_stable)
                if pad is None or not pad.xml_id:
                    continue
                position = pad.position or component_record.position
                if position is not None:
                    pad_positions[(component_record.xml_id, pad.xml_id)] = Point(**position)
        for _net_name, endpoints in requested_ratlines:
            for first, second in zip(endpoints, endpoints[1:], strict=False):
                pair = frozenset({first, second})
                if first == second or pair in existing_pairs:
                    continue
                first_component = component_by_refdes[
                    next(
                        spec.refdes.casefold()
                        for spec in operation.components
                        if component_by_refdes[spec.refdes.casefold()].get("Id") == first[0]
                    )
                ]
                second_component = component_by_refdes[
                    next(
                        spec.refdes.casefold()
                        for spec in operation.components
                        if component_by_refdes[spec.refdes.casefold()].get("Id") == second[0]
                    )
                ]
                first_position = pad_positions.get(first) or Point(
                    to_mm(float(first_component.get("X", "0")), document.units),
                    to_mm(float(first_component.get("Y", "0")), document.units),
                )
                second_position = pad_positions.get(second) or Point(
                    to_mm(float(second_component.get("X", "0")), document.units),
                    to_mm(float(second_component.get("Y", "0")), document.units),
                )
                ET.SubElement(
                    ratlines,
                    "Ratline",
                    {
                        "Id": str(next_ratline_id),
                        "Hidden": "N",
                        "X1": f"{from_mm(first_position.x, document.units):.9g}",
                        "Y1": f"{from_mm(first_position.y, document.units):.9g}",
                        "X2": f"{from_mm(second_position.x, document.units):.9g}",
                        "Y2": f"{from_mm(second_position.y, document.units):.9g}",
                        "Comp1": first[0],
                        "Pad1": first[1],
                        "Comp2": second[0],
                        "Pad2": second[1],
                    },
                )
                next_ratline_id += 1
                existing_pairs.add(pair)
                patch_count += 1

    final_snapshot = build_snapshot(document)
    targets = [
        final_snapshot.objects[stable]
        for stable in dict.fromkeys(changed_ids)
        if stable in final_snapshot.objects
    ]
    return (
        _operation_preview(index, operation.kind, targets, before, after, document),
        patch_count,
    )


def _schematic_net_element(document: DipTraceDocument, name: str) -> ET.Element | None:
    for net in document.container.findall("./Nets/Net"):
        if (net.findtext("./Name") or "").casefold() == name.casefold() or net.get(
            "Id"
        ) == name:
            return net
    return None


def _resolve_part(
    snapshot: DocumentSnapshot,
    *,
    refdes: str | None,
    part_id: str | None,
) -> tuple[ObjectRecord, ET.Element]:
    if part_id is not None:
        record = snapshot.get_object(part_id)
        if record.kind != "part":
            raise EditError(
                f"Object is not a schematic part: {part_id}",
                object_ids=[part_id],
            )
        return record, _resolved_element(snapshot, record)
    assert refdes is not None
    matches = [
        item
        for item in snapshot.objects.values()
        if item.kind == "part" and (item.refdes or "").casefold() == refdes.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(f"Schematic part was not found: {refdes}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(
            f"RefDes {refdes!r} is shared by multiple parts; pass part_id instead",
            object_ids=[item.stable_id for item in matches],
        )
    return matches[0], _resolved_element(snapshot, matches[0])


def _locate_pin(document: DipTraceDocument, pin_element: ET.Element) -> tuple[str, int]:
    for part in document.container.findall("./Components/Part"):
        for index, candidate in enumerate(part.findall("./Pins/Pin")):
            if candidate is pin_element:
                return part.get("Id", ""), index
    raise EditError("Cannot resolve the owning part of a pin element")


def _element_stable_id(
    snapshot: DocumentSnapshot, element: ET.Element, fallback: str
) -> str:
    for stable, candidate in snapshot.elements.items():
        if candidate is element:
            return stable
    return fallback


def _apply_add_sheet(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddSheetOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "add_sheet")
    settings = document.container.find("./SheetSettings")
    if settings is None:
        settings = ET.Element("SheetSettings")
        document.container.insert(0, settings)
    sheets = settings.find("./Sheets")
    if sheets is None:
        sheets = ET.SubElement(settings, "Sheets")
    if any(
        (sheet.findtext("./Name") or "").casefold() == operation.name.casefold()
        for sheet in sheets.findall("./Sheet")
    ):
        raise AmbiguousSelectorError(f"A sheet named {operation.name!r} already exists")
    numeric_ids = [
        int(value)
        for sheet in sheets.findall("./Sheet")
        if (value := sheet.findtext("./Id") or "").isdigit()
    ]
    new_id = str(max(numeric_ids, default=-1) + 1)
    sheet = ET.SubElement(sheets, "Sheet")
    ET.SubElement(sheet, "Id").text = new_id
    ET.SubElement(sheet, "Name").text = operation.name
    ET.SubElement(sheet, "Type").text = operation.sheet_type
    stable = stable_id("sheet", document.source_type, f"xml:{new_id}")
    changed_ids.append(stable)
    target = ObjectRecord(
        stable_id=stable,
        kind="sheet",
        label=operation.name,
        name=operation.name,
    )
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [],
        [{"id": stable, "sheet_id": new_id, "name": operation.name}],
        document,
    ), 1


def _apply_place_part(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: PlacePartOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "place_part")
    _require_sheet(document, operation.sheet)
    existing = [
        item
        for item in snapshot.objects.values()
        if item.kind == "part" and (item.refdes or "").casefold() == operation.refdes.casefold()
    ]
    if existing and not operation.allow_shared_refdes:
        raise AmbiguousSelectorError(
            f"RefDes already exists: {operation.refdes}",
            object_ids=[item.stable_id for item in existing],
        )
    components = document.container.find("./Components")
    if components is None:
        components = ET.SubElement(document.container, "Components")
    part_id = _next_numeric_id(components.findall("./Part"))
    update_ids = [
        int(value)
        for part in components.findall("./Part")
        if (value := part.get("UpdateId", "")).lstrip("-").isdigit()
    ]
    update_id = str(max(update_ids, default=99) + 1)
    attributes = {
        "Id": part_id,
        "UpdateId": update_id,
        "ComponentStyle": operation.component_style,
        "ComponentPart": str(operation.component_part),
        "PartNumber": str(operation.part_number),
        "Sheet": str(operation.sheet),
        "X": f"{from_mm(operation.x, document.units):.9g}",
        "Y": f"{from_mm(operation.y, document.units):.9g}",
        "Locked": "N",
        "Selected": "N",
    }
    if operation.angle_deg:
        attributes["Angle"] = f"{math.radians(operation.angle_deg):.9g}"
    part = ET.SubElement(components, "Part", attributes)
    ET.SubElement(part, "RefDes").text = operation.refdes
    ET.SubElement(part, "PartRefDes").text = operation.part_refdes or str(
        operation.component_part + 1
    )
    ET.SubElement(part, "PartName").text = operation.part_name or "Part 1"
    ET.SubElement(part, "Value").text = operation.value
    ET.SubElement(part, "Name").text = operation.name or operation.component_style
    pins = ET.SubElement(part, "Pins")
    for _ in range(operation.pin_count):
        ET.SubElement(pins, "Pin", {"NetId": "-1", "NotConnected": "N"})
    stable = stable_id("part", document.source_type, f"xml:{part_id}")
    changed_ids.append(stable)
    target = ObjectRecord(
        stable_id=stable,
        kind="part",
        label=operation.refdes,
        refdes=operation.refdes,
        name=operation.name or operation.component_style,
        value=operation.value or None,
        position=Point(operation.x, operation.y).as_dict(),
    )
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [],
        [
            {
                "id": stable,
                "refdes": operation.refdes,
                "component_style": operation.component_style,
                "pin_count": operation.pin_count,
                "position": Point(operation.x, operation.y).as_dict(),
            }
        ],
        document,
    ), 1


def _apply_connect_pins(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: ConnectPinsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "connect_pins")
    nets = document.container.find("./Nets")
    if nets is None:
        nets = ET.SubElement(document.container, "Nets")
    net_element = _schematic_net_element(document, operation.net)
    created_net = False
    patch_count = 0
    if net_element is None:
        net_id = _next_numeric_id(nets.findall("./Net"))
        net_element = ET.SubElement(
            nets,
            "Net",
            {"Id": net_id, "NetClass": "0", "Locked": "N", "Enabled": "Y"},
        )
        ET.SubElement(net_element, "Name").text = operation.net
        ET.SubElement(net_element, "Pins")
        ET.SubElement(net_element, "Wires")
        created_net = True
        patch_count += 1
    else:
        net_id = net_element.get("Id", "")
        if net_element.get("Enabled", "Y") == "N":
            raise EditError(f"Net is disabled: {operation.net}", code="connectivity_conflict")
    net_pins = net_element.find("./Pins")
    if net_pins is None:
        net_pins = ET.SubElement(net_element, "Pins")
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    targets: list[ObjectRecord] = []
    for endpoint in operation.pins:
        record, part_element = _resolve_part(
            snapshot, refdes=endpoint.refdes, part_id=endpoint.part_id
        )
        targets.append(record)
        part_xml_id = part_element.get("Id", "")
        part_pins = part_element.findall("./Pins/Pin")
        if endpoint.pin >= len(part_pins):
            raise EditError(
                f"Pin index {endpoint.pin} is out of range for {record.label or record.stable_id} "
                f"({len(part_pins)} pins)",
                object_ids=[record.stable_id],
            )
        pin_element = part_pins[endpoint.pin]
        pin_stable = _element_stable_id(
            snapshot, pin_element, f"{record.stable_id}:pin:{endpoint.pin}"
        )
        current_net = pin_element.get("NetId", "-1")
        before.append(
            {
                "id": pin_stable,
                "refdes": record.refdes,
                "pin": endpoint.pin,
                "net": current_net,
            }
        )
        after.append(
            {
                "id": pin_stable,
                "refdes": record.refdes,
                "pin": endpoint.pin,
                "net": net_id,
            }
        )
        if current_net == net_id:
            continue
        if current_net not in {"", "-1"}:
            if not operation.allow_reconnect:
                raise EditError(
                    f"Pin {record.refdes or record.stable_id}:{endpoint.pin} is already "
                    f"connected to net {current_net}; pass allow_reconnect=true to move it",
                    code="connectivity_conflict",
                    object_ids=[record.stable_id],
                )
            old_net = document.container.find(f"./Nets/Net[@Id='{current_net}']")
            old_pins = old_net.find("./Pins") if old_net is not None else None
            if old_pins is not None:
                for item in list(old_pins.findall("./Item")):
                    if item.get("Part") == part_xml_id and item.get("Pin") == str(
                        endpoint.pin
                    ):
                        old_pins.remove(item)
                        patch_count += 1
        pin_element.set("NetId", net_id)
        pin_element.set("NotConnected", "N")
        patch_count += 1
        if not any(
            item.get("Part") == part_xml_id and item.get("Pin") == str(endpoint.pin)
            for item in net_pins.findall("./Item")
        ):
            ET.SubElement(net_pins, "Item", {"Part": part_xml_id, "Pin": str(endpoint.pin)})
            patch_count += 1
        changed_ids.append(pin_stable)
    if created_net:
        changed_ids.append(stable_id("net", document.source_type, f"xml:{net_id}"))
    return _operation_preview(
        index, operation.kind, targets, before, after, document
    ), patch_count


def _apply_disconnect_pins(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: DisconnectPinsOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "disconnect_pins")
    targets = _select_records(snapshot, operation.selector, {"pin"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        pin_element = _resolved_element(snapshot, record)
        current_net = pin_element.get("NetId", "-1")
        before.append({"id": record.stable_id, "net": current_net})
        after.append({"id": record.stable_id, "net": "-1"})
        if current_net in {"", "-1"}:
            continue
        part_xml_id, pin_index = _locate_pin(document, pin_element)
        pin_element.set("NetId", "-1")
        patch_count += 1
        old_net = document.container.find(f"./Nets/Net[@Id='{current_net}']")
        old_pins = old_net.find("./Pins") if old_net is not None else None
        if old_pins is not None:
            for item in list(old_pins.findall("./Item")):
                if item.get("Part") == part_xml_id and item.get("Pin") == str(pin_index):
                    old_pins.remove(item)
                    patch_count += 1
        changed_ids.append(record.stable_id)
    return _operation_preview(
        index, operation.kind, targets, before, after, document
    ), patch_count


def _net_of_wire(document: DipTraceDocument, wire: ET.Element) -> ET.Element | None:
    for net in document.container.findall("./Nets/Net"):
        if any(candidate is wire for candidate in net.findall("./Wires/Wire")):
            return net
    return None


def _wire_endpoint_attributes(
    index_suffix: int,
    endpoint: WireEndpoint,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    net_element: ET.Element,
) -> dict[str, str]:
    attributes = {
        f"Connected{index_suffix}": endpoint.type,
        f"Bus{index_suffix}": "-1",
    }
    if endpoint.type == "Free":
        attributes[f"Object{index_suffix}"] = "-1"
        attributes[f"SubObject{index_suffix}"] = "-1"
        return attributes
    if endpoint.type == "Pin":
        record, part_element = _resolve_part(
            snapshot, refdes=endpoint.refdes, part_id=endpoint.part_id
        )
        part_pins = part_element.findall("./Pins/Pin")
        assert endpoint.pin is not None
        if endpoint.pin >= len(part_pins):
            raise EditError(
                f"Pin index {endpoint.pin} is out of range for "
                f"{record.label or record.stable_id} ({len(part_pins)} pins)",
                object_ids=[record.stable_id],
            )
        net_id = net_element.get("Id", "")
        if part_pins[endpoint.pin].get("NetId", "-1") != net_id:
            raise EditError(
                f"Pin {record.refdes or record.stable_id}:{endpoint.pin} does not belong "
                "to the wire net; connect it first",
                code="connectivity_conflict",
                object_ids=[record.stable_id],
            )
        attributes[f"Object{index_suffix}"] = part_element.get("Id", "")
        attributes[f"SubObject{index_suffix}"] = str(endpoint.pin)
        return attributes
    assert endpoint.wire_id is not None
    target = snapshot.get_object(endpoint.wire_id)
    if target.kind != "wire":
        raise EditError(
            f"Object is not a schematic wire: {endpoint.wire_id}",
            object_ids=[endpoint.wire_id],
        )
    wire_element = _resolved_element(snapshot, target)
    if _net_of_wire(document, wire_element) is not net_element:
        raise EditError(
            "A wire endpoint can only reference a wire of the same net",
            code="connectivity_conflict",
            object_ids=[endpoint.wire_id],
        )
    point_count = len(wire_element.findall("./Points/Point"))
    point_index = endpoint.point_index if endpoint.point_index is not None else point_count - 1
    if point_count == 0 or point_index >= point_count:
        raise EditError(
            f"Wire point index {point_index} is out of range ({point_count} points)",
            object_ids=[endpoint.wire_id],
        )
    attributes[f"Object{index_suffix}"] = wire_element.get("Id", "")
    attributes[f"SubObject{index_suffix}"] = str(point_index)
    return attributes


def _apply_add_wire(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddWireOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "add_wire")
    _require_sheet(document, operation.sheet)
    net_element = _schematic_net_element(document, operation.net)
    if net_element is None:
        raise ObjectNotFoundError(f"Net was not found: {operation.net}")
    wires = net_element.find("./Wires")
    if wires is None:
        wires = ET.SubElement(net_element, "Wires")
    wire_id = _next_numeric_id(wires.findall("./Wire"))
    attributes = {
        "Id": wire_id,
        "Sheet": str(operation.sheet),
        **_wire_endpoint_attributes(1, operation.start, document, snapshot, net_element),
        **_wire_endpoint_attributes(2, operation.end, document, snapshot, net_element),
        "HiddenPower": "Y" if operation.hidden_power else "N",
        "CanUnhide": "N",
        "Arrows": "None",
        "Group": "-1",
        "Selected": "N",
    }
    wire = ET.SubElement(wires, "Wire", attributes)
    points = ET.SubElement(wire, "Points")
    previous: tuple[float, float] | None = None
    for point in operation.points:
        if previous is None:
            direction = "-1"
        else:
            dx = point.x - previous[0]
            dy = point.y - previous[1]
            if dx != 0 and dy == 0:
                direction = "0"
            elif dy != 0 and dx == 0:
                direction = "1"
            else:
                direction = "-1"
        previous = (point.x, point.y)
        ET.SubElement(
            points,
            "Point",
            {
                "X": f"{from_mm(point.x, document.units):.9g}",
                "Y": f"{from_mm(point.y, document.units):.9g}",
                "Dir": direction,
            },
        )
    stable = stable_id("wire", document.source_type, f"xml:{wire_id}")
    changed_ids.append(stable)
    target = ObjectRecord(
        stable_id=stable,
        kind="wire",
        label=f"{operation.net} wire {wire_id}",
        xml_id=wire_id,
        net_id=net_element.get("Id") or None,
        net_name=operation.net,
    )
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [],
        [
            {
                "id": stable,
                "net": operation.net,
                "point_count": len(operation.points),
                "start": operation.start.model_dump(mode="json"),
                "end": operation.end.model_dump(mode="json"),
            }
        ],
        document,
    ), 1


def _apply_delete_wire(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: DeleteWireOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "delete_wire")
    targets = _select_records(snapshot, operation.selector, {"wire"})
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    patch_count = 0
    for record in targets:
        wire_element = _resolved_element(snapshot, record)
        before.append({"id": record.stable_id, "attributes": dict(wire_element.attrib)})
        after.append({"id": record.stable_id, "deleted": True})
        net_element: ET.Element | None = None
        net_ids = record.relationships.get("net", [])
        if net_ids:
            net_element = snapshot.elements.get(net_ids[0])
        if net_element is None:
            net_element = _net_of_wire(document, wire_element)
        wires = net_element.find("./Wires") if net_element is not None else None
        if wires is None or wire_element not in list(wires):
            raise EditError(
                "Cannot resolve the parent net of the wire",
                object_ids=[record.stable_id],
            )
        wires.remove(wire_element)
        changed_ids.append(record.stable_id)
        patch_count += 1
    return _operation_preview(
        index, operation.kind, targets, before, after, document
    ), patch_count


def _apply_add_net_label(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddNetLabelOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_schematic(document, "add_net_label")
    _require_sheet(document, operation.sheet)
    net_element = _schematic_net_element(document, operation.net)
    if net_element is None:
        raise ObjectNotFoundError(f"Net was not found: {operation.net}")
    shapes = document.container.find("./Shapes")
    if shapes is None:
        shapes = ET.SubElement(document.container, "Shapes")
    shape_id = _next_numeric_id(shapes.findall("./Shape"))
    shape = ET.SubElement(
        shapes,
        "Shape",
        {
            "Enabled": "Y",
            "Id": shape_id,
            "Type": "Text",
            "Sheet": str(operation.sheet),
            "Angle": "0",
            "HorzAlign": "Left",
            "VertAlign": "Bottom",
            "TextAlign": "Left",
            "FontVector": "Y",
            "FontSize": str(operation.font_size),
            "FontWidth": "-2",
            "FontScale": "1",
            "LineSpacing": "1.2",
            "NetId": net_element.get("Id", ""),
            "BusId": "-1",
            "Group": "-1",
            "Selected": "N",
            "Locked": "N",
        },
    )
    points = ET.SubElement(shape, "Points")
    ET.SubElement(
        points,
        "Point",
        {
            "X": f"{from_mm(operation.x, document.units):.9g}",
            "Y": f"{from_mm(operation.y, document.units):.9g}",
        },
    )
    lines = ET.SubElement(shape, "TextLines")
    label_text = operation.text or operation.net
    ET.SubElement(lines, "TextLine").text = label_text
    stable = stable_id("net-label", document.source_type, f"xml:{shape_id}")
    changed_ids.append(stable)
    target = ObjectRecord(
        stable_id=stable,
        kind="net_label",
        label=label_text,
        name=label_text,
        net_id=net_element.get("Id") or None,
        net_name=operation.net,
        position=Point(operation.x, operation.y).as_dict(),
    )
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [],
        [
            {
                "id": stable,
                "net": operation.net,
                "text": label_text,
                "position": Point(operation.x, operation.y).as_dict(),
            }
        ],
        document,
    ), 1


def _apply_set_panelization(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetPanelizationOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_pcb(document, "set_panelization")

    def dim(value_mm: float) -> str:
        return f"{from_mm(value_mm, document.units):.9g}"

    panel = document.container.find("./Panel")
    patch_count = 0
    created = False
    if panel is None:
        panel = ET.Element("Panel")
        outline = document.container.find("./BoardOutline")
        if outline is not None:
            document.container.insert(list(document.container).index(outline) + 1, panel)
        else:
            document.container.insert(0, panel)
        created = True
        patch_count += 1
    rails = (operation.rail_left, operation.rail_right, operation.rail_top, operation.rail_bottom)
    attributes = {
        "Type": operation.panel_type,
        "Columns": str(operation.columns),
        "Rows": str(operation.rows),
        "ColumnSpacing": dim(operation.column_spacing),
        "RowSpacing": dim(operation.row_spacing),
        "PanelizeSingle": "N",
        "RailShow": "Y" if any(value > 0 for value in rails) else "N",
        "RailLeft": dim(operation.rail_left),
        "RailRight": dim(operation.rail_right),
        "RailTop": dim(operation.rail_top),
        "RailBottom": dim(operation.rail_bottom),
        "TabWidth": dim(operation.tab_width),
        "TabRadius": dim(operation.tab_radius),
        "TabStep": dim(operation.tab_step),
        "HoleDiam": dim(operation.hole_diameter),
        "HoleStep": dim(operation.hole_step),
        "HoleInset": dim(operation.hole_inset),
        "HoleKeepout": dim(operation.hole_keepout),
        "TabsDone": "N",
        "CombinedRadius": dim(operation.combined_radius),
        "KeepMaterial": "Y" if operation.keep_material else "N",
        "BorderTabs": str(operation.border_tabs),
    }
    before_attributes = dict(panel.attrib)
    for name, rendered in attributes.items():
        if panel.get(name) != rendered:
            panel.set(name, rendered)
            if not created:
                patch_count += 1
    # Manual tab coordinates belong to the previous layout; let DipTrace
    # recompute them from the new parameters (TabsDone="N").
    for child_tag in ("HorzTabsX", "VertTabsY"):
        child = panel.find(f"./{child_tag}")
        if child is not None:
            panel.remove(child)
            patch_count += 1
    stable = stable_id("panel", document.source_type, "xml:panel")
    changed_ids.append(stable)
    target = ObjectRecord(stable_id=stable, kind="panel", label="Panelization")
    before = [] if created else [{"id": stable, "attributes": before_attributes}]
    return _operation_preview(
        index,
        operation.kind,
        [target],
        before,
        [{"id": stable, "attributes": attributes}],
        document,
    ), patch_count


def _apply_clear_panelization(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: ClearPanelizationOperation,
    changed_ids: list[str],
) -> tuple[dict[str, Any], int]:
    _require_pcb(document, "clear_panelization")
    panel = document.container.find("./Panel")
    if panel is None:
        raise ObjectNotFoundError("The document has no panelization settings")
    before_attributes = dict(panel.attrib)
    document.container.remove(panel)
    stable = stable_id("panel", document.source_type, "xml:panel")
    changed_ids.append(stable)
    target = ObjectRecord(stable_id=stable, kind="panel", label="Panelization")
    return _operation_preview(
        index,
        operation.kind,
        [target],
        [{"id": stable, "attributes": before_attributes}],
        [{"id": stable, "deleted": True}],
        document,
    ), 1
