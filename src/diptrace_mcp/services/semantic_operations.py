from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from ..domain import (
    ObjectRecord,
    QuerySelector,
)
from ..errors import (
    DocumentError,
)
from ..geometry import BBox, Point, distance, point_in_polygon
from ..operations import (
    AddNetLabelOperation,
    AddSheetOperation,
    AddTestpointOperation,
    AddTraceOperation,
    AddViaOperation,
    AddWireOperation,
    AssignNetsToClassOperation,
    ClearPanelizationOperation,
    ConnectPinsOperation,
    DeleteTraceOperation,
    DeleteViaOperation,
    DeleteWireOperation,
    DisconnectPinsOperation,
    GroupComponentsOperation,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    MoveViaOperation,
    PlacePartOperation,
    RemoveTestpointsOperation,
    RenameNetOperation,
    ReplaceTraceOperation,
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
    SetTraceWidthOperation,
    SetViaStyleOperation,
    UngroupComponentsOperation,
    UpdateNetClassRulesOperation,
)
from .context import DocumentGateway, ServiceContext, read_success

SemanticWrite = Callable[
    [SemanticOperation, str | None, bool, str | None, str | None], dict[str, Any]
]
SemanticOperations = Callable[
    [Sequence[SemanticOperation], str | None, bool, str | None, str | None], dict[str, Any]
]


class SemanticOperationsService:
    """Facade implementation for guarded semantic component and board operations."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        semantic_write: SemanticWrite,
        semantic_operations: SemanticOperations,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.semantic_write = semantic_write
        self.semantic_operations = semantic_operations

    def move_components(
        self,
        selector: dict[str, Any] | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        grid_snap: float | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        op = MoveComponentsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "grid_snap": grid_snap,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(op, path, dry_run, expected_sha256, txid)

    def set_component_value(
        self,
        selector: dict[str, Any] | None,
        value: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        op = SetComponentValueOperation.model_validate({"selector": selector or {}, "value": value})
        return self.semantic_write(op, path, dry_run, expected_sha256, txid)

    def rotate_components(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allowed_angles: list[float] | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RotateComponentsOperation.model_validate(
            {
                "selector": selector or {},
                "angle_deg": angle_deg,
                "mode": mode,
                "allowed_angles": allowed_angles or [],
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_side(
        self,
        selector: dict[str, Any] | None,
        side: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetComponentSideOperation.model_validate(
            {"selector": selector or {}, "side": side, "allow_locked": allow_locked}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_lock(
        self,
        selector: dict[str, Any] | None,
        locked: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetComponentLockOperation.model_validate(
            {"selector": selector or {}, "locked": locked}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_properties(
        self,
        selector: dict[str, Any] | None,
        *,
        name: str | None = None,
        value: str | None = None,
        refdes: str | None = None,
        fields: dict[str, str] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetComponentPropertiesOperation.model_validate(
            {
                "selector": selector or {},
                "name": name,
                "value": value,
                "refdes": refdes,
                "fields": fields or {},
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_pattern(
        self,
        selector: dict[str, Any],
        pattern_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetComponentPatternOperation.model_validate(
            {
                "selector": selector,
                "pattern_style": pattern_style,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def align_components(
        self,
        selector: dict[str, Any],
        alignment: str,
        *,
        target_value: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        valid = {"left", "center_x", "right", "top", "center_y", "bottom"}
        if alignment not in valid:
            raise DocumentError(
                f"alignment must be one of {sorted(valid)}", code="geometry_invalid"
            )
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Component alignment requires a PCB document")
        query = QuerySelector.model_validate(selector)
        records = snapshot.select(query, kinds={"component"})
        if len(records) < 2:
            raise DocumentError(
                "Component alignment requires at least two matched components",
                code="scope_required",
            )
        if any(record.position is None or record.bbox is None for record in records):
            raise DocumentError(
                "All aligned components require position and bbox geometry",
                code="geometry_invalid",
            )
        records.sort(key=lambda item: item.stable_id)

        def coordinate(record: ObjectRecord) -> float:
            box = record.bbox
            assert box is not None
            return {
                "left": box["min_x"],
                "center_x": (box["min_x"] + box["max_x"]) / 2.0,
                "right": box["max_x"],
                "top": box["min_y"],
                "center_y": (box["min_y"] + box["max_y"]) / 2.0,
                "bottom": box["max_y"],
            }[alignment]

        aligned_value = target_value if target_value is not None else coordinate(records[0])
        x_axis = alignment in {"left", "center_x", "right"}
        operations: list[SemanticOperation] = []
        for record in records:
            assert record.position is not None
            delta = aligned_value - coordinate(record)
            operations.append(
                MoveComponentsOperation(
                    selector=QuerySelector(ids=[record.stable_id]),
                    absolute_x=record.position["x"] + delta if x_axis else None,
                    absolute_y=record.position["y"] + delta if not x_axis else None,
                    allow_locked=allow_locked,
                )
            )
        return self.semantic_operations(
            operations,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    def distribute_components(
        self,
        selector: dict[str, Any],
        axis: str,
        *,
        mode: str = "centers",
        spacing: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        if axis not in {"x", "y"} or mode not in {"centers", "gaps"}:
            raise DocumentError(
                "axis must be x/y and mode must be centers/gaps", code="geometry_invalid"
            )
        if spacing is not None and spacing < 0:
            raise DocumentError("spacing cannot be negative", code="geometry_invalid")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Component distribution requires a PCB document")
        records = snapshot.select(QuerySelector.model_validate(selector), kinds={"component"})
        if len(records) < 3:
            raise DocumentError(
                "Component distribution requires at least three matched components",
                code="scope_required",
            )
        if any(record.position is None or record.bbox is None for record in records):
            raise DocumentError(
                "All distributed components require position and bbox geometry",
                code="geometry_invalid",
            )
        center_key = "x" if axis == "x" else "y"
        minimum_key = "min_x" if axis == "x" else "min_y"
        maximum_key = "max_x" if axis == "x" else "max_y"
        records.sort(
            key=lambda record: (
                record.position[center_key] if record.position is not None else 0.0,
                record.stable_id,
            )
        )

        def position(record: ObjectRecord) -> dict[str, float]:
            assert record.position is not None
            return record.position

        def box(record: ObjectRecord) -> dict[str, float]:
            assert record.bbox is not None
            return record.bbox

        targets: list[float] = []
        if mode == "centers":
            first = position(records[0])[center_key]
            step = (
                spacing
                if spacing is not None
                else (position(records[-1])[center_key] - first) / (len(records) - 1)
            )
            targets = [first + index * step for index in range(len(records))]
        else:
            boxes = [box(record) for record in records]
            first_edge = boxes[0][minimum_key]
            total_size = sum(item[maximum_key] - item[minimum_key] for item in boxes)
            gap = (
                spacing
                if spacing is not None
                else (boxes[-1][maximum_key] - first_edge - total_size) / (len(records) - 1)
            )
            cursor = first_edge
            for item in boxes:
                size = item[maximum_key] - item[minimum_key]
                targets.append(cursor + size / 2.0)
                cursor += size + gap
        operations = []
        for record, target_coordinate in zip(records, targets, strict=True):
            operations.append(
                MoveComponentsOperation(
                    selector=QuerySelector(ids=[record.stable_id]),
                    absolute_x=target_coordinate if axis == "x" else None,
                    absolute_y=target_coordinate if axis == "y" else None,
                    allow_locked=allow_locked,
                )
            )
        return self.semantic_operations(
            operations,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    def group_components(
        self,
        selector: dict[str, Any],
        *,
        group_id: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = GroupComponentsOperation.model_validate(
            {
                "selector": selector,
                "group_id": group_id,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def ungroup_components(
        self,
        selector: dict[str, Any],
        *,
        remove_empty_groups: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = UngroupComponentsOperation.model_validate(
            {
                "selector": selector,
                "remove_empty_groups": remove_empty_groups,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def list_board_texts(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        query = QuerySelector.model_validate(selector or {})
        records = snapshot.select(query, kinds={"component_text", "board_text"})
        return read_success(
            snapshot.info,
            {"matched_count": len(records), "items": [item.model_dump() for item in records]},
        )

    def move_board_texts(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = MoveBoardTextsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def rotate_board_texts(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RotateBoardTextsOperation.model_validate(
            {
                "selector": selector or {},
                "angle_deg": angle_deg,
                "mode": mode,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_text_visibility(
        self,
        selector: dict[str, Any] | None,
        visibility: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetTextVisibilityOperation.model_validate(
            {
                "selector": selector or {},
                "visibility": visibility,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_text_style(
        self,
        selector: dict[str, Any] | None,
        *,
        font_size: int | None = None,
        font_width: float | None = None,
        horizontal_align: str | None = None,
        vertical_align: str | None = None,
        mirrored: bool | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetTextStyleOperation.model_validate(
            {
                "selector": selector or {},
                "font_size": font_size,
                "font_width": font_width,
                "horizontal_align": horizontal_align,
                "vertical_align": vertical_align,
                "mirrored": mirrored,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_pin_no_connect(
        self,
        selector: dict[str, Any] | None,
        no_connect: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetPinNoConnectOperation.model_validate(
            {"selector": selector or {}, "no_connect": no_connect}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def rename_net(
        self,
        selector: dict[str, Any] | None,
        new_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = RenameNetOperation.model_validate(
            {"selector": selector or {}, "new_name": new_name}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def add_sheet(
        self,
        name: str,
        sheet_type: str = "Normal",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AddSheetOperation.model_validate({"name": name, "sheet_type": sheet_type})
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def place_part(
        self,
        component_style: str,
        refdes: str,
        x: float,
        y: float,
        *,
        pin_count: int,
        name: str | None = None,
        value: str = "",
        sheet: int = 0,
        angle_deg: float = 0.0,
        component_part: int = 0,
        part_number: int = 0,
        part_refdes: str | None = None,
        part_name: str | None = None,
        allow_shared_refdes: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = PlacePartOperation.model_validate(
            {
                "component_style": component_style,
                "refdes": refdes,
                "x": x,
                "y": y,
                "pin_count": pin_count,
                "name": name,
                "value": value,
                "sheet": sheet,
                "angle_deg": angle_deg,
                "component_part": component_part,
                "part_number": part_number,
                "part_refdes": part_refdes,
                "part_name": part_name,
                "allow_shared_refdes": allow_shared_refdes,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def connect_pins(
        self,
        net: str,
        pins: list[dict[str, Any]],
        allow_reconnect: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = ConnectPinsOperation.model_validate(
            {"net": net, "pins": pins, "allow_reconnect": allow_reconnect}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def disconnect_pins(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DisconnectPinsOperation.model_validate({"selector": selector or {}})
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def add_wire(
        self,
        net: str,
        points: list[dict[str, Any]],
        start: dict[str, Any],
        end: dict[str, Any],
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AddWireOperation.model_validate(
            {
                "net": net,
                "points": points,
                "start": start,
                "end": end,
                "sheet": sheet,
                "hidden_power": hidden_power,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def delete_wire(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DeleteWireOperation.model_validate({"selector": selector or {}})
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def add_net_label(
        self,
        net: str,
        x: float,
        y: float,
        sheet: int = 0,
        text: str | None = None,
        font_size: int = 4,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        horizontal_align: str = "Left",
    ) -> dict[str, Any]:
        operation = AddNetLabelOperation.model_validate(
            {
                "net": net,
                "x": x,
                "y": y,
                "sheet": sheet,
                "text": text,
                "font_size": font_size,
                "horizontal_align": horizontal_align,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_panelization(
        self,
        panel: dict[str, Any],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetPanelizationOperation.model_validate(panel)
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def clear_panelization(
        self,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = ClearPanelizationOperation.model_validate({})
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def update_net_class_rules(
        self,
        class_name: str,
        *,
        layer: str | None = None,
        width: float | None = None,
        min_width: float | None = None,
        max_width: float | None = None,
        clearance: float | None = None,
        neck_width: float | None = None,
        differential_gap: float | None = None,
        max_uncoupled_length: float | None = None,
        tolerance: float | None = None,
        check_length: bool | None = None,
        fixed_length: float | None = None,
        length_delta: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = UpdateNetClassRulesOperation.model_validate(
            {
                "class_name": class_name,
                "layer": layer,
                "width": width,
                "min_width": min_width,
                "max_width": max_width,
                "clearance": clearance,
                "neck_width": neck_width,
                "differential_gap": differential_gap,
                "max_uncoupled_length": max_uncoupled_length,
                "tolerance": tolerance,
                "check_length": check_length,
                "fixed_length": fixed_length,
                "length_delta": length_delta,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def assign_nets_to_class(
        self,
        selector: dict[str, Any] | None,
        class_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AssignNetsToClassOperation.model_validate(
            {"selector": selector or {}, "class_name": class_name}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def list_testpoints(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        query = QuerySelector.model_validate(selector or {})
        records = snapshot.select(query, kinds={"testpoint"})
        net_names = {
            record.xml_id: record.name
            for record in snapshot.objects.values()
            if record.kind == "net" and record.xml_id is not None
        }
        items = []
        for record in records:
            payload = record.model_dump()
            payload["net_name"] = (
                net_names.get(record.net_id) if record.net_id is not None else None
            )
            items.append(payload)
        return read_success(
            snapshot.info,
            {"matched_count": len(items), "items": items},
        )

    def find_testpoint_candidates(
        self,
        target_nets: list[str],
        *,
        path: str | None = None,
        side: str = "Top",
        probe_diameter: float = 1.0,
        clearance: float = 0.5,
        grid: float = 2.54,
        candidates_per_net: int = 10,
    ) -> dict[str, Any]:
        if not target_nets:
            raise DocumentError("target_nets cannot be empty", code="scope_required")
        if side not in {"Top", "Bottom"}:
            raise DocumentError("side must be Top or Bottom", code="geometry_invalid")
        if probe_diameter <= 0 or clearance < 0 or grid <= 0:
            raise DocumentError("probe_diameter and grid must be positive")
        if not 1 <= candidates_per_net <= 100:
            raise DocumentError("candidates_per_net must be between 1 and 100")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None or snapshot.board.outline is None:
            raise DocumentError("A PCB board outline is required", code="geometry_invalid")
        outline = [Point(**item) for item in snapshot.board.outline.get("points", [])]
        board_box = BBox(**snapshot.board.outline["bbox"])
        obstacles = [
            BBox(**record.bbox).expand(clearance + probe_diameter / 2.0)
            for record in snapshot.objects.values()
            if record.kind in {"component", "testpoint", "keepout"}
            and record.bbox is not None
            and (record.side in {None, side} or record.kind == "keepout")
        ]
        free_points: list[Point] = []
        x = math.ceil(board_box.min_x / grid) * grid
        while x <= board_box.max_x and len(free_points) < 5_000:
            y = math.ceil(board_box.min_y / grid) * grid
            while y <= board_box.max_y and len(free_points) < 5_000:
                point = Point(x, y)
                if point_in_polygon(point, outline) and not any(
                    obstacle.contains_point(point) for obstacle in obstacles
                ):
                    free_points.append(point)
                y += grid
            x += grid
        net_records = [
            record
            for record in snapshot.objects.values()
            if record.kind == "net"
            and any(
                candidate.casefold()
                in {(record.name or "").casefold(), record.stable_id.casefold()}
                for candidate in target_nets
            )
        ]
        missing = [
            candidate
            for candidate in target_nets
            if not any(
                candidate.casefold()
                in {(record.name or "").casefold(), record.stable_id.casefold()}
                for record in net_records
            )
        ]
        if missing:
            raise DocumentError(
                "Some target nets were not found",
                code="object_not_found",
                details={"missing_nets": missing},
            )
        candidates: list[dict[str, Any]] = []
        for net in net_records:
            endpoints = [
                snapshot.objects[object_id]
                for object_id in net.relationships.get("endpoints", [])
                if object_id in snapshot.objects
                and snapshot.objects[object_id].position is not None
            ]
            ranked = sorted(
                free_points,
                key=lambda point: min(
                    (
                        distance(point, Point(**endpoint.position))
                        for endpoint in endpoints
                        if endpoint.position is not None
                    ),
                    default=0.0,
                ),
            )[:candidates_per_net]
            for rank, point in enumerate(ranked, start=1):
                candidates.append(
                    {
                        "candidate_id": f"tpc_{net.stable_id}_{rank}",
                        "net_id": net.stable_id,
                        "net_name": net.name,
                        "position": point.as_dict(),
                        "side": side,
                        "probe_diameter": probe_diameter,
                        "clearance": clearance,
                    }
                )
        return read_success(
            snapshot.info,
            {
                "matched_net_count": len(net_records),
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
            limitations=[
                "Candidates use exported bbox geometry; enclosure and fixture shadowing "
                "are not modeled."
            ],
        )

    def add_testpoints(
        self,
        testpoints: list[dict[str, Any]],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        if not testpoints:
            raise DocumentError("testpoints cannot be empty", code="scope_required")
        operations = [AddTestpointOperation.model_validate(item) for item in testpoints]
        return self.semantic_operations(operations, path, dry_run, expected_sha256, txid)

    def move_testpoints(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        grid_snap: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = MoveTestpointsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "grid_snap": grid_snap,
                "allow_locked": allow_locked,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def remove_testpoints(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RemoveTestpointsOperation.model_validate(
            {"selector": selector or {}, "allow_locked": allow_locked}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def review_testpoint_coverage(
        self,
        target_nets: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        nets = [record for record in snapshot.objects.values() if record.kind == "net"]
        if target_nets:
            requested = {name.casefold() for name in target_nets}
            nets = [record for record in nets if (record.name or "").casefold() in requested]
        testpoint_net_ids = {
            record.net_id
            for record in snapshot.objects.values()
            if record.kind == "testpoint" and record.net_id is not None
        }
        covered = [record for record in nets if record.xml_id in testpoint_net_ids]
        uncovered = [record for record in nets if record.xml_id not in testpoint_net_ids]
        coverage = len(covered) / len(nets) if nets else 1.0
        return read_success(
            snapshot.info,
            {
                "target_net_count": len(nets),
                "covered_count": len(covered),
                "coverage": coverage,
                "covered_nets": [record.name for record in covered],
                "uncovered_nets": [record.name for record in uncovered],
            },
            limitations=["Coverage counts explicit MCP/DipTrace standalone pad testpoints only."],
        )

    def add_trace(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[dict[str, Any]],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AddTraceOperation.model_validate(
            {
                "net": net,
                "start_object_id": start_object_id,
                "end_object_id": end_object_id,
                "points": points,
                "layer": layer,
                "width": width,
                "clearance": clearance,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def replace_trace(
        self,
        trace_id: str,
        points: list[dict[str, Any]],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = ReplaceTraceOperation.model_validate(
            {
                "trace_id": trace_id,
                "points": points,
                "layer": layer,
                "width": width,
                "clearance": clearance,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def delete_trace(
        self,
        selector: dict[str, Any],
        *,
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DeleteTraceOperation.model_validate(
            {
                "selector": selector,
                "allow_connectivity_regression": allow_connectivity_regression,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_trace_width(
        self,
        selector: dict[str, Any],
        width: float,
        *,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetTraceWidthOperation.model_validate(
            {
                "selector": selector,
                "width": width,
                "segment_indices": segment_indices or [],
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def add_via(
        self,
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        *,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AddViaOperation.model_validate(
            {
                "trace_id": trace_id,
                "x": x,
                "y": y,
                "via_style": via_style,
                "layer_before": layer_before,
                "layer_after": layer_after,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def move_via(
        self,
        selector: dict[str, Any],
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = MoveViaOperation.model_validate(
            {
                "selector": selector,
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def delete_via(
        self,
        selector: dict[str, Any],
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DeleteViaOperation.model_validate({"selector": selector})
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_via_style(
        self,
        selector: dict[str, Any],
        via_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetViaStyleOperation.model_validate(
            {"selector": selector, "via_style": via_style}
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, txid)
