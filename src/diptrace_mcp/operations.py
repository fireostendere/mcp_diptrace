from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .domain import QuerySelector, StrictModel


class SemanticOperation(StrictModel):
    kind: str


class SelectorOperation(SemanticOperation):
    selector: QuerySelector = Field(default_factory=QuerySelector)


class MoveComponentsOperation(SelectorOperation):
    kind: Literal["move_components"] = "move_components"
    dx: float = Field(default=0.0, allow_inf_nan=False)
    dy: float = Field(default=0.0, allow_inf_nan=False)
    absolute_x: float | None = Field(default=None, allow_inf_nan=False)
    absolute_y: float | None = Field(default=None, allow_inf_nan=False)
    anchor: Literal["center", "origin"] = "center"
    grid_snap: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    allow_locked: bool = False

    @model_validator(mode="after")
    def reject_noop(self) -> MoveComponentsOperation:
        if self.absolute_x is None and self.absolute_y is None and self.dx == 0 and self.dy == 0:
            raise ValueError("move_components requires an offset or absolute coordinate")
        return self


class RotateComponentsOperation(SelectorOperation):
    kind: Literal["rotate_components"] = "rotate_components"
    angle_deg: float = Field(allow_inf_nan=False)
    mode: Literal["absolute", "relative"] = "relative"
    allowed_angles: list[float] = Field(default_factory=list, max_length=360)
    allow_locked: bool = False


class SetComponentSideOperation(SelectorOperation):
    kind: Literal["set_component_side"] = "set_component_side"
    side: Literal["Top", "Bottom"]
    allow_locked: bool = False


class SetComponentLockOperation(SelectorOperation):
    kind: Literal["set_component_lock"] = "set_component_lock"
    locked: bool


class SetComponentValueOperation(SelectorOperation):
    kind: Literal["set_component_value"] = "set_component_value"
    value: str = Field(max_length=4_096)


class SetComponentPropertiesOperation(SelectorOperation):
    kind: Literal["set_component_properties"] = "set_component_properties"
    name: str | None = Field(default=None, max_length=4_096)
    value: str | None = Field(default=None, max_length=4_096)
    refdes: str | None = Field(default=None, min_length=1, max_length=256)
    fields: dict[str, str] = Field(default_factory=dict)
    allow_locked: bool = False

    @model_validator(mode="after")
    def require_property(self) -> SetComponentPropertiesOperation:
        if self.name is None and self.value is None and self.refdes is None and not self.fields:
            raise ValueError("at least one component property is required")
        if any(not key.strip() for key in self.fields):
            raise ValueError("component field names cannot be empty")
        return self


class SetComponentPatternOperation(SelectorOperation):
    kind: Literal["set_component_pattern"] = "set_component_pattern"
    pattern_style: str = Field(min_length=1, max_length=1_000)
    allow_locked: bool = False
    validation_mode: Literal[
        "strict_embedded_pattern",
        "external_pattern_reference",
    ] = "strict_embedded_pattern"


class GroupComponentsOperation(SelectorOperation):
    kind: Literal["group_components"] = "group_components"
    group_id: int | None = Field(default=None, ge=0)
    allow_locked: bool = False


class UngroupComponentsOperation(SelectorOperation):
    kind: Literal["ungroup_components"] = "ungroup_components"
    remove_empty_groups: bool = True
    allow_locked: bool = False


class MoveBoardTextsOperation(SelectorOperation):
    kind: Literal["move_board_texts"] = "move_board_texts"
    dx: float = Field(default=0.0, allow_inf_nan=False)
    dy: float = Field(default=0.0, allow_inf_nan=False)
    absolute_x: float | None = Field(default=None, allow_inf_nan=False)
    absolute_y: float | None = Field(default=None, allow_inf_nan=False)
    allow_locked: bool = False

    @model_validator(mode="after")
    def reject_noop(self) -> MoveBoardTextsOperation:
        if self.absolute_x is None and self.absolute_y is None and self.dx == 0 and self.dy == 0:
            raise ValueError("move_board_texts requires an offset or absolute coordinate")
        return self


class RotateBoardTextsOperation(SelectorOperation):
    kind: Literal["rotate_board_texts"] = "rotate_board_texts"
    angle_deg: float = Field(allow_inf_nan=False)
    mode: Literal["absolute", "relative"] = "relative"
    allow_locked: bool = False


class SetTextVisibilityOperation(SelectorOperation):
    kind: Literal["set_text_visibility"] = "set_text_visibility"
    visibility: Literal["Show", "Hide", "Common"]
    allow_locked: bool = False


class SetTextStyleOperation(SelectorOperation):
    kind: Literal["set_text_style"] = "set_text_style"
    font_size: int | None = Field(default=None, ge=1, le=1_000)
    font_width: float | None = Field(default=None, allow_inf_nan=False)
    horizontal_align: Literal["Left", "Center", "Right"] | None = None
    vertical_align: Literal["Top", "Center", "Bottom"] | None = None
    mirrored: bool | None = None
    allow_locked: bool = False

    @model_validator(mode="after")
    def require_style(self) -> SetTextStyleOperation:
        if all(
            value is None
            for value in (
                self.font_size,
                self.font_width,
                self.horizontal_align,
                self.vertical_align,
                self.mirrored,
            )
        ):
            raise ValueError("at least one text style property is required")
        return self


class SetPinNoConnectOperation(SelectorOperation):
    kind: Literal["set_pin_no_connect"] = "set_pin_no_connect"
    no_connect: bool


class RenameNetOperation(SelectorOperation):
    kind: Literal["rename_net"] = "rename_net"
    new_name: str = Field(min_length=1, max_length=1_000)


class UpdateNetClassRulesOperation(SemanticOperation):
    kind: Literal["update_net_class_rules"] = "update_net_class_rules"
    class_name: str = Field(min_length=1, max_length=256)
    layer: str | None = Field(default=None, max_length=256)
    width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    min_width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    max_width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    clearance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    neck_width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    differential_gap: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    max_uncoupled_length: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    tolerance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    check_length: bool | None = None
    fixed_length: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    length_delta: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_rules(self) -> UpdateNetClassRulesOperation:
        values = (
            self.width,
            self.min_width,
            self.max_width,
            self.clearance,
            self.neck_width,
            self.differential_gap,
            self.max_uncoupled_length,
            self.tolerance,
            self.check_length,
            self.fixed_length,
            self.length_delta,
        )
        if all(value is None for value in values):
            raise ValueError("at least one net class rule is required")
        if (
            self.min_width is not None
            and self.max_width is not None
            and self.min_width > self.max_width
        ):
            raise ValueError("min_width cannot exceed max_width")
        if self.width is not None and self.min_width is not None and self.width < self.min_width:
            raise ValueError("width cannot be smaller than min_width")
        if self.width is not None and self.max_width is not None and self.width > self.max_width:
            raise ValueError("width cannot exceed max_width")
        return self


class AssignNetsToClassOperation(SelectorOperation):
    kind: Literal["assign_nets_to_class"] = "assign_nets_to_class"
    class_name: str = Field(min_length=1, max_length=256)


class AddTestpointOperation(SemanticOperation):
    kind: Literal["add_testpoint"] = "add_testpoint"
    net: str = Field(min_length=1, max_length=1_000)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    side: Literal["Top", "Bottom"] = "Top"
    pad_diameter: float = Field(gt=0.0, allow_inf_nan=False)
    hole_diameter: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    refdes: str | None = Field(default=None, pattern=r"^TP[A-Za-z0-9_.-]*$", max_length=256)

    @model_validator(mode="after")
    def validate_geometry(self) -> AddTestpointOperation:
        if self.hole_diameter >= self.pad_diameter:
            raise ValueError("hole_diameter must be smaller than pad_diameter")
        return self


class MoveTestpointsOperation(SelectorOperation):
    kind: Literal["move_testpoints"] = "move_testpoints"
    dx: float = Field(default=0.0, allow_inf_nan=False)
    dy: float = Field(default=0.0, allow_inf_nan=False)
    absolute_x: float | None = Field(default=None, allow_inf_nan=False)
    absolute_y: float | None = Field(default=None, allow_inf_nan=False)
    grid_snap: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    allow_locked: bool = False

    @model_validator(mode="after")
    def reject_noop(self) -> MoveTestpointsOperation:
        if self.absolute_x is None and self.absolute_y is None and self.dx == 0 and self.dy == 0:
            raise ValueError("move_testpoints requires an offset or absolute coordinate")
        return self


class RemoveTestpointsOperation(SelectorOperation):
    kind: Literal["remove_testpoints"] = "remove_testpoints"
    allow_locked: bool = False


class TracePathPoint(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    layer: str | None = Field(default=None, min_length=1, max_length=256)
    width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    via_style: str | None = Field(default=None, min_length=1, max_length=256)


class AddTraceOperation(SemanticOperation):
    kind: Literal["add_trace"] = "add_trace"
    net: str = Field(min_length=1, max_length=1_000)
    start_object_id: str = Field(min_length=1)
    end_object_id: str = Field(min_length=1)
    points: list[TracePathPoint] = Field(min_length=2, max_length=10_000)
    layer: str = Field(min_length=1, max_length=256)
    width: float = Field(gt=0.0, allow_inf_nan=False)
    clearance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_path(self) -> AddTraceOperation:
        if self.start_object_id == self.end_object_id:
            raise ValueError("trace endpoints must be different objects")
        if all(
            left.x == right.x and left.y == right.y
            for left, right in zip(self.points, self.points[1:], strict=False)
        ):
            raise ValueError("trace path must contain a non-zero segment")
        return self


class DifferentialPairCenterPoint(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    layer: str = Field(min_length=1, max_length=256)
    via_style: str | None = Field(default=None, min_length=1, max_length=256)
    positive_dx: float = Field(allow_inf_nan=False)
    positive_dy: float = Field(allow_inf_nan=False)
    negative_dx: float = Field(allow_inf_nan=False)
    negative_dy: float = Field(allow_inf_nan=False)


class AddDifferentialPairRouteOperation(SemanticOperation):
    kind: Literal["add_differential_pair_route"] = "add_differential_pair_route"
    pair: str = Field(min_length=1, max_length=1_000)
    positive_net: str = Field(min_length=1, max_length=1_000)
    negative_net: str = Field(min_length=1, max_length=1_000)
    positive_start_object_id: str = Field(min_length=1)
    positive_end_object_id: str = Field(min_length=1)
    negative_start_object_id: str = Field(min_length=1)
    negative_end_object_id: str = Field(min_length=1)
    positive_points: list[TracePathPoint] = Field(min_length=2, max_length=10_000)
    negative_points: list[TracePathPoint] = Field(min_length=2, max_length=10_000)
    center_points: list[DifferentialPairCenterPoint] = Field(
        min_length=2, max_length=10_000
    )
    start_pad_point_id: str = Field(min_length=1, max_length=256)
    end_pad_point_id: str = Field(min_length=1, max_length=256)
    layer: str = Field(min_length=1, max_length=256)
    width: float = Field(gt=0.0, allow_inf_nan=False)
    clearance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_coupled_paths(self) -> AddDifferentialPairRouteOperation:
        lengths = {
            len(self.positive_points),
            len(self.negative_points),
            len(self.center_points),
        }
        if len(lengths) != 1:
            raise ValueError("positive, negative and center paths must have equal point counts")
        if self.positive_net == self.negative_net:
            raise ValueError("differential pair nets must be different")
        return self


class ReplaceTraceOperation(SemanticOperation):
    kind: Literal["replace_trace"] = "replace_trace"
    trace_id: str = Field(min_length=1)
    points: list[TracePathPoint] = Field(min_length=2, max_length=10_000)
    layer: str = Field(min_length=1, max_length=256)
    width: float = Field(gt=0.0, allow_inf_nan=False)
    clearance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)


class DeleteTraceOperation(SelectorOperation):
    kind: Literal["delete_trace"] = "delete_trace"
    allow_connectivity_regression: bool = False


class SetTraceWidthOperation(SelectorOperation):
    kind: Literal["set_trace_width"] = "set_trace_width"
    width: float = Field(gt=0.0, allow_inf_nan=False)
    segment_indices: list[int] = Field(default_factory=list, max_length=10_000)

    @field_validator("segment_indices")
    @classmethod
    def validate_segment_indices(cls, values: list[int]) -> list[int]:
        if any(value < 0 for value in values):
            raise ValueError("segment indices cannot be negative")
        return sorted(set(values))


class AddViaOperation(SemanticOperation):
    kind: Literal["add_via"] = "add_via"
    trace_id: str = Field(min_length=1)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    via_style: str = Field(min_length=1, max_length=256)
    layer_before: str | None = Field(default=None, min_length=1, max_length=256)
    layer_after: str | None = Field(default=None, min_length=1, max_length=256)


class MoveViaOperation(SelectorOperation):
    kind: Literal["move_via"] = "move_via"
    dx: float = Field(default=0.0, allow_inf_nan=False)
    dy: float = Field(default=0.0, allow_inf_nan=False)
    absolute_x: float | None = Field(default=None, allow_inf_nan=False)
    absolute_y: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def reject_noop(self) -> MoveViaOperation:
        if self.absolute_x is None and self.absolute_y is None and self.dx == 0 and self.dy == 0:
            raise ValueError("move_via requires an offset or absolute coordinate")
        return self


class DeleteViaOperation(SelectorOperation):
    kind: Literal["delete_via"] = "delete_via"


class SetViaStyleOperation(SelectorOperation):
    kind: Literal["set_via_style"] = "set_via_style"
    via_style: str = Field(min_length=1, max_length=256)


class AddSheetOperation(SemanticOperation):
    kind: Literal["add_sheet"] = "add_sheet"
    name: str = Field(min_length=1, max_length=256)
    sheet_type: Literal["Normal", "Hierarchy Block"] = "Normal"


class PlacePartOperation(SemanticOperation):
    kind: Literal["place_part"] = "place_part"
    component_style: str = Field(min_length=1, max_length=1_000)
    refdes: str = Field(min_length=1, max_length=256)
    name: str | None = Field(default=None, max_length=1_000)
    value: str = Field(default="", max_length=4_096)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    sheet: int = Field(default=0, ge=0)
    pin_count: int = Field(ge=0, le=10_000)
    angle_deg: float = Field(default=0.0, allow_inf_nan=False)
    component_part: int = Field(default=0, ge=0)
    part_number: int = Field(default=0, ge=0)
    part_refdes: str | None = Field(default=None, max_length=256)
    part_name: str | None = Field(default=None, max_length=1_000)
    allow_shared_refdes: bool = False


class PcbSyncComponent(StrictModel):
    refdes: str = Field(min_length=1, max_length=256)
    name: str = Field(default="", max_length=1_000)
    value: str = Field(default="", max_length=4_096)
    pattern_style: str = Field(min_length=1, max_length=1_000)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    side: Literal["Top", "Bottom"] = "Top"
    pad_numbers: list[str] = Field(min_length=1, max_length=10_000)
    fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("pad_numbers")
    @classmethod
    def validate_pad_numbers(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("PCB pad numbers cannot be empty")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("PCB pad numbers must be unique within a component")
        return normalized


class PcbSyncEndpoint(StrictModel):
    refdes: str = Field(min_length=1, max_length=256)
    pad_number: str = Field(min_length=1, max_length=256)


class PcbSyncNet(StrictModel):
    name: str = Field(min_length=1, max_length=1_000)
    endpoints: list[PcbSyncEndpoint] = Field(min_length=1, max_length=100_000)


class SyncSchematicToPcbOperation(SemanticOperation):
    kind: Literal["sync_schematic_to_pcb"] = "sync_schematic_to_pcb"
    schematic_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    components: list[PcbSyncComponent] = Field(min_length=1, max_length=10_000)
    nets: list[PcbSyncNet] = Field(default_factory=list, max_length=100_000)
    pattern_xml: list[str] = Field(default_factory=list, max_length=10_000)
    pad_style_xml: list[str] = Field(default_factory=list, max_length=10_000)
    update_existing_properties: bool = True
    create_ratlines: bool = True
    allow_reconnect: bool = False
    reconciliation_mode: Literal["additive", "exact"] = "additive"
    allow_locked_reconciliation: bool = False

    @model_validator(mode="after")
    def validate_unique_names(self) -> SyncSchematicToPcbOperation:
        refdes = [item.refdes.casefold() for item in self.components]
        if len(set(refdes)) != len(refdes):
            raise ValueError("sync components must have unique RefDes values")
        nets = [item.name.casefold() for item in self.nets]
        if len(set(nets)) != len(nets):
            raise ValueError("sync nets must have unique names")
        definitions = [*self.pattern_xml, *self.pad_style_xml]
        if sum(len(item) for item in definitions) > 64 * 1024 * 1024:
            raise ValueError("embedded pattern definitions exceed 64 MiB")
        if any(
            "<!doctype" in item.casefold() or "<!entity" in item.casefold()
            for item in definitions
        ):
            raise ValueError("DTD and ENTITY declarations are forbidden in pattern definitions")
        return self


class PinEndpoint(StrictModel):
    refdes: str | None = Field(default=None, min_length=1, max_length=256)
    part_id: str | None = Field(default=None, min_length=1, max_length=512)
    pin: int = Field(ge=0, le=100_000)

    @model_validator(mode="after")
    def require_single_reference(self) -> PinEndpoint:
        if (self.refdes is None) == (self.part_id is None):
            raise ValueError("exactly one of refdes or part_id is required")
        return self


class ConnectPinsOperation(SemanticOperation):
    kind: Literal["connect_pins"] = "connect_pins"
    net: str = Field(min_length=1, max_length=1_000)
    pins: list[PinEndpoint] = Field(min_length=1, max_length=10_000)
    allow_reconnect: bool = False


class DisconnectPinsOperation(SelectorOperation):
    kind: Literal["disconnect_pins"] = "disconnect_pins"


class WireEndpoint(StrictModel):
    type: Literal["Pin", "Wire", "Free"]
    refdes: str | None = Field(default=None, min_length=1, max_length=256)
    part_id: str | None = Field(default=None, min_length=1, max_length=512)
    pin: int | None = Field(default=None, ge=0, le=100_000)
    wire_id: str | None = Field(default=None, min_length=1, max_length=512)
    point_index: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_reference(self) -> WireEndpoint:
        if self.type == "Pin":
            if (self.refdes is None) == (self.part_id is None):
                raise ValueError("a Pin endpoint requires exactly one of refdes or part_id")
            if self.pin is None:
                raise ValueError("a Pin endpoint requires a pin index")
        elif self.type == "Wire":
            if self.wire_id is None:
                raise ValueError("a Wire endpoint requires wire_id")
        return self


class WirePathPoint(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class AddWireOperation(SemanticOperation):
    kind: Literal["add_wire"] = "add_wire"
    net: str = Field(min_length=1, max_length=1_000)
    sheet: int = Field(default=0, ge=0)
    points: list[WirePathPoint] = Field(min_length=2, max_length=10_000)
    start: WireEndpoint
    end: WireEndpoint
    hidden_power: bool = False


class DeleteWireOperation(SelectorOperation):
    kind: Literal["delete_wire"] = "delete_wire"


class AddNetLabelOperation(SemanticOperation):
    kind: Literal["add_net_label"] = "add_net_label"
    net: str = Field(min_length=1, max_length=1_000)
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    sheet: int = Field(default=0, ge=0)
    text: str | None = Field(default=None, min_length=1, max_length=1_000)
    font_size: int = Field(default=10, ge=1, le=1_000)


class SetPanelizationOperation(SemanticOperation):
    kind: Literal["set_panelization"] = "set_panelization"
    panel_type: Literal["V-Scoring", "Tab Routing"] = "V-Scoring"
    columns: int = Field(default=2, ge=1, le=100)
    rows: int = Field(default=1, ge=1, le=100)
    column_spacing: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    row_spacing: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    rail_left: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    rail_right: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    rail_top: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    rail_bottom: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    tab_width: float = Field(default=13.5, gt=0.0, le=500.0, allow_inf_nan=False)
    tab_radius: float = Field(default=3.6, ge=0.0, le=100.0, allow_inf_nan=False)
    tab_step: float = Field(default=225.0, gt=0.0, le=10_000.0, allow_inf_nan=False)
    hole_diameter: float = Field(default=2.4, gt=0.0, le=100.0, allow_inf_nan=False)
    hole_step: float = Field(default=3.6, gt=0.0, le=1_000.0, allow_inf_nan=False)
    hole_inset: float = Field(default=0.0, ge=0.0, le=500.0, allow_inf_nan=False)
    hole_keepout: float = Field(default=3.0, ge=0.0, le=500.0, allow_inf_nan=False)
    combined_radius: float = Field(default=1.5, ge=0.0, le=100.0, allow_inf_nan=False)
    keep_material: bool = False
    border_tabs: Literal[0, 1, 2] = 0


class ClearPanelizationOperation(SemanticOperation):
    kind: Literal["clear_panelization"] = "clear_panelization"


_OPERATION_TYPES: dict[str, type[SemanticOperation]] = {
    "move_components": MoveComponentsOperation,
    "rotate_components": RotateComponentsOperation,
    "set_component_side": SetComponentSideOperation,
    "set_component_lock": SetComponentLockOperation,
    "set_component_value": SetComponentValueOperation,
    "set_component_properties": SetComponentPropertiesOperation,
    "set_component_pattern": SetComponentPatternOperation,
    "group_components": GroupComponentsOperation,
    "ungroup_components": UngroupComponentsOperation,
    "move_board_texts": MoveBoardTextsOperation,
    "rotate_board_texts": RotateBoardTextsOperation,
    "set_text_visibility": SetTextVisibilityOperation,
    "set_text_style": SetTextStyleOperation,
    "set_pin_no_connect": SetPinNoConnectOperation,
    "rename_net": RenameNetOperation,
    "update_net_class_rules": UpdateNetClassRulesOperation,
    "assign_nets_to_class": AssignNetsToClassOperation,
    "add_testpoint": AddTestpointOperation,
    "move_testpoints": MoveTestpointsOperation,
    "remove_testpoints": RemoveTestpointsOperation,
    "add_trace": AddTraceOperation,
    "add_differential_pair_route": AddDifferentialPairRouteOperation,
    "replace_trace": ReplaceTraceOperation,
    "delete_trace": DeleteTraceOperation,
    "set_trace_width": SetTraceWidthOperation,
    "add_via": AddViaOperation,
    "move_via": MoveViaOperation,
    "delete_via": DeleteViaOperation,
    "set_via_style": SetViaStyleOperation,
    "add_sheet": AddSheetOperation,
    "place_part": PlacePartOperation,
    "sync_schematic_to_pcb": SyncSchematicToPcbOperation,
    "connect_pins": ConnectPinsOperation,
    "disconnect_pins": DisconnectPinsOperation,
    "add_wire": AddWireOperation,
    "delete_wire": DeleteWireOperation,
    "add_net_label": AddNetLabelOperation,
    "set_panelization": SetPanelizationOperation,
    "clear_panelization": ClearPanelizationOperation,
}


def parse_semantic_operations(payload: list[dict[str, Any]]) -> list[SemanticOperation]:
    operations: list[SemanticOperation] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise TypeError(f"Operation {index} must be a mapping")
        kind = item.get("kind")
        operation_type = _OPERATION_TYPES.get(str(kind))
        if operation_type is None:
            raise ValueError(f"Unsupported semantic operation kind: {kind!r}")
        operations.append(operation_type.model_validate(item))
    return operations
