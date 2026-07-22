from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StableId = str
SourceType = Literal[
    "DipTrace-PCB",
    "DipTrace-Schematic",
    "DipTrace-ComponentLibrary",
    "DipTrace-PatternLibrary",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Unit(str, Enum):
    MM = "mm"
    INCH = "inch"
    MIL = "mil"
    UNKNOWN = "unknown"


class DocumentTarget(StrictModel):
    path: str | None = None
    document_id: str | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class DocumentInfo(StrictModel):
    document_id: str = Field(pattern=r"^doc_[0-9a-f]{16}$")
    source_type: str
    kind: str
    version: str
    units: str
    coordinate_units: Literal["mm"] = "mm"
    path: str
    live_session: bool = False
    size_bytes: int = Field(default=0, ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parse_warnings: list[str] = Field(default_factory=list)
    compatibility: dict[str, Any] = Field(default_factory=dict)


class GeometryShape(StrictModel):
    kind: Literal["circle", "ellipse", "rectangle", "obround", "polygon", "line"]
    center: dict[str, float] | None = None
    width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    height: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    rotation_deg: float = Field(default=0.0, allow_inf_nan=False)
    points: list[dict[str, float]] = Field(default_factory=list)
    line_width: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    approximation: str | None = None

    @field_validator("center")
    @classmethod
    def validate_center(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and set(value) != {"x", "y"}:
            raise ValueError("geometry center must contain exactly x and y")
        return value

    @field_validator("points")
    @classmethod
    def validate_points(cls, value: list[dict[str, float]]) -> list[dict[str, float]]:
        if any(set(point) != {"x", "y"} for point in value):
            raise ValueError("geometry points must contain exactly x and y")
        return value


class ObjectRecord(StrictModel):
    stable_id: StableId = Field(pattern=r"^[a-z][a-z0-9_-]*_[0-9a-f]{16}$")
    kind: str = Field(min_length=1, max_length=64)
    label: str | None = None
    name: str | None = None
    value: str | None = None
    refdes: str | None = None
    xml_id: str | None = None
    parent_id: StableId | None = None
    net_id: str | None = None
    net_name: str | None = None
    layer: str | None = None
    side: str | None = None
    locked: bool = False
    selected: bool = False
    position: dict[str, float] | None = None
    bbox: dict[str, float] | None = None
    geometry: GeometryShape | None = None
    rotation_deg: float = 0.0
    mirrored: bool = False
    geometry_source: str = "unknown"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    relationships: dict[str, list[StableId]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and set(value) != {"x", "y"}:
            raise ValueError("position must contain exactly x and y")
        return value

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        required = {"min_x", "min_y", "max_x", "max_y"}
        if set(value) != required:
            raise ValueError("bbox must contain min_x, min_y, max_x and max_y")
        if value["min_x"] > value["max_x"] or value["min_y"] > value["max_y"]:
            raise ValueError("bbox minimums must not exceed maximums")
        return value


class StackupMaterial(StrictModel):
    material_type: Literal["conductor", "plane", "dielectric", "unknown"]
    name: str = ""
    variable_thickness: bool = False
    thickness_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    dielectric_constant: float | None = Field(default=None, gt=1.0, allow_inf_nan=False)
    material_constant_raw: float | None = Field(default=None, allow_inf_nan=False)
    trace_width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    attributes: dict[str, str] = Field(default_factory=dict)


class StackupLayer(StrictModel):
    index: int = Field(ge=0)
    layer_id: str | None = None
    layer_name: str | None = None
    material: StackupMaterial


class StackupModel(StrictModel):
    name: str = ""
    source: Literal["LayerStackItems", "missing"] = "missing"
    layers: list[StackupLayer] = Field(default_factory=list)
    total_thickness_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    completeness: Literal["complete", "partial", "missing"] = "missing"
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DifferentialPairLayerRules(StrictModel):
    layer_name: str
    width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    min_width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    max_width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    clearance_to_others_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    gap_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    neck_width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    neck_gap_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    max_neck_length_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)


class DifferentialPairRules(StrictModel):
    target_impedance_ohm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    max_uncoupled_length_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    length_tolerance_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    phase_tolerance: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    phase_error_length_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    check_length: bool = False
    fixed_length_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    length_delta_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    layer_rules: list[DifferentialPairLayerRules] = Field(default_factory=list)


class DifferentialPairPadPair(StrictModel):
    xml_id: str | None = None
    positive_component_id: str | None = None
    positive_pad_id: str | None = None
    negative_component_id: str | None = None
    negative_pad_id: str | None = None


class DifferentialPairSegment(StrictModel):
    index: int = Field(ge=0)
    positive_trace_xml_id: str | None = None
    negative_trace_xml_id: str | None = None
    center_points: list[dict[str, Any]] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)


class DifferentialPairModel(StrictModel):
    stable_id: StableId
    xml_id: str | None = None
    name: str
    positive_net_id: StableId | None = None
    positive_net_xml_id: str | None = None
    positive_net_name: str | None = None
    negative_net_id: StableId | None = None
    negative_net_xml_id: str | None = None
    negative_net_name: str | None = None
    net_class_id: str | None = None
    net_class_name: str | None = None
    route_mode: str = ""
    auto_pad_points: bool = False
    pad_pairs: list[DifferentialPairPadPair] = Field(default_factory=list)
    segments: list[DifferentialPairSegment] = Field(default_factory=list)
    rules: DifferentialPairRules = Field(default_factory=DifferentialPairRules)
    attributes: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class NetLengthMeasurement(StrictModel):
    net_id: StableId
    net_xml_id: str | None = None
    net_name: str | None = None
    geometric_length_mm: float = Field(ge=0.0, allow_inf_nan=False)
    per_layer_length_mm: dict[str, float] = Field(default_factory=dict)
    trace_count: int = Field(ge=0)
    via_count: int = Field(ge=0)
    via_ids: list[StableId] = Field(default_factory=list)
    layer_transition_count: int = Field(ge=0)
    arc_count: int = Field(ge=0)
    electrical_length_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    delay_ps: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    warnings: list[str] = Field(default_factory=list)


class DifferentialPairAnalysis(StrictModel):
    pair_id: StableId
    pair_name: str
    positive: NetLengthMeasurement
    negative: NetLengthMeasurement
    signed_skew_mm: float = Field(allow_inf_nan=False)
    absolute_skew_mm: float = Field(ge=0.0, allow_inf_nan=False)
    coupled_length_mm: float = Field(ge=0.0, allow_inf_nan=False)
    estimated_uncoupled_length_mm: float = Field(ge=0.0, allow_inf_nan=False)
    gap_mm: dict[str, float | None] = Field(default_factory=dict)
    via_balance: int
    per_layer_delta_mm: dict[str, float] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class ReturnPathIssue(StrictModel):
    issue_type: Literal[
        "reference_unknown",
        "unreferenced_segment",
        "possible_split_crossing",
        "transition_without_return_via",
    ]
    net_id: StableId
    net_name: str | None = None
    trace_id: StableId | None = None
    layer: str | None = None
    reference_layer: str | None = None
    segment_index: int | None = Field(default=None, ge=0)
    location: dict[str, float] | None = None
    estimated_detour_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    suggested_actions: list[str] = Field(default_factory=list)


class ReturnPathAnalysis(StrictModel):
    net_count: int = Field(ge=0)
    segment_count: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    issues: list[ReturnPathIssue] = Field(default_factory=list)
    suggested_stitching_locations: list[dict[str, float]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class BomRecord(StrictModel):
    stable_id: StableId
    refdes: list[str] = Field(default_factory=list)
    quantity: int = Field(ge=1)
    value: str = ""
    pattern: str = ""
    manufacturer: str = ""
    mpn: str = ""
    dnp: bool = False
    variant: str = ""
    source_object_ids: list[StableId] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ConnectivityGraph(StrictModel):
    document_id: str
    source_kind: Literal["pcb", "schematic"]
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    nets: list[dict[str, Any]] = Field(default_factory=list)
    connected_components: list[list[StableId]] = Field(default_factory=list)
    unrouted_connections: list[dict[str, Any]] = Field(default_factory=list)
    endpoint_mapping: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ViaStyleModel(StrictModel):
    id: str = Field(min_length=1)
    name: str = ""
    diameter_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    hole_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    layer_start_id: str | None = None
    layer_end_id: str | None = None
    span_layer_ids: list[str] = Field(default_factory=list)
    span_source: Literal["explicit", "unspecified", "invalid"] = "unspecified"
    attributes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_geometry_and_span(self) -> ViaStyleModel:
        if (
            self.diameter_mm is not None
            and self.hole_mm is not None
            and self.diameter_mm <= self.hole_mm
        ):
            raise ValueError("via diameter must be greater than hole diameter")
        if self.span_source == "explicit" and len(self.span_layer_ids) < 2:
            raise ValueError("an explicit via span must contain at least two layers")
        if self.span_source != "explicit" and self.span_layer_ids:
            raise ValueError("only an explicit via span may contain normalized layers")
        return self


class BoardModel(StrictModel):
    document_id: str
    outline: dict[str, Any] | None = None
    cutouts: list[dict[str, Any]] = Field(default_factory=list)
    components: list[ObjectRecord] = Field(default_factory=list)
    pads: list[ObjectRecord] = Field(default_factory=list)
    holes: list[ObjectRecord] = Field(default_factory=list)
    nets: list[ObjectRecord] = Field(default_factory=list)
    traces: list[ObjectRecord] = Field(default_factory=list)
    vias: list[ObjectRecord] = Field(default_factory=list)
    copper_pours: list[ObjectRecord] = Field(default_factory=list)
    keepouts: list[ObjectRecord] = Field(default_factory=list)
    layers: list[dict[str, Any]] = Field(default_factory=list)
    patterns: list[LibraryPattern] = Field(default_factory=list)
    pad_styles: list[LibraryPadStyle] = Field(default_factory=list)
    via_styles: list[ViaStyleModel] = Field(default_factory=list)
    net_classes: list[dict[str, Any]] = Field(default_factory=list)
    differential_pairs: list[DifferentialPairModel] = Field(default_factory=list)
    ratlines: list[dict[str, Any]] = Field(default_factory=list)
    texts: list[ObjectRecord] = Field(default_factory=list)
    testpoints: list[ObjectRecord] = Field(default_factory=list)
    rules: dict[str, Any] = Field(default_factory=dict)
    stackup: StackupModel = Field(default_factory=StackupModel)
    warnings: list[str] = Field(default_factory=list)


class SchematicModel(StrictModel):
    document_id: str
    sheets: list[dict[str, Any]] = Field(default_factory=list)
    parts: list[ObjectRecord] = Field(default_factory=list)
    pins: list[ObjectRecord] = Field(default_factory=list)
    nets: list[ObjectRecord] = Field(default_factory=list)
    wires: list[ObjectRecord] = Field(default_factory=list)
    buses: list[dict[str, Any]] = Field(default_factory=list)
    ports: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[ObjectRecord] = Field(default_factory=list)
    differential_pairs: list[dict[str, Any]] = Field(default_factory=list)
    erc: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class LibraryPin(StrictModel):
    stable_id: StableId
    part_index: int = Field(ge=0)
    xml_id: str
    name: str
    number: str
    pad_id: str | None = None
    electrical_type: str = "Undefined"
    pin_type: str = "Default"
    position: dict[str, float] | None = None
    orientation_deg: float = 0.0
    locked: bool = False


class LibraryPadStyle(StrictModel):
    name: str = Field(min_length=1)
    pad_type: str
    side: str
    shape: str
    width: float = Field(ge=0.0)
    height: float = Field(ge=0.0)
    x_offset: float = Field(default=0.0, allow_inf_nan=False)
    y_offset: float = Field(default=0.0, allow_inf_nan=False)
    corner_percent: float = Field(default=0.0, ge=0.0, le=50.0)
    polygon_points: list[dict[str, float]] = Field(default_factory=list)
    hole_type: str | None = None
    hole_width: float | None = Field(default=None, ge=0.0)
    hole_height: float | None = Field(default=None, ge=0.0)
    mask_paste: dict[str, str] = Field(default_factory=dict)
    mask_paste_segments: dict[str, list[dict[str, float]]] = Field(default_factory=dict)
    custom_swell: float | None = Field(default=None, allow_inf_nan=False)
    custom_shrink: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)


class LibraryPad(StrictModel):
    stable_id: StableId
    xml_id: str
    number: str
    style: str
    position: dict[str, float]
    rotation_deg: float = 0.0
    side: str = "Top"
    locked: bool = False
    bbox: dict[str, float] | None = None
    geometry: GeometryShape | None = None
    mask_geometry: dict[str, list[GeometryShape]] = Field(default_factory=dict)
    paste_geometry: dict[str, list[GeometryShape]] = Field(default_factory=dict)


class LibraryPattern(StrictModel):
    stable_id: StableId
    index: int = Field(ge=0)
    style: str | None = None
    name: str
    unique_name: str = ""
    value: str = ""
    refdes: str = ""
    mounting: str = "None"
    manufacturer: str = ""
    datasheet: str = ""
    fields: dict[str, str] = Field(default_factory=dict)
    pads: list[LibraryPad] = Field(default_factory=list)
    holes: list[dict[str, Any]] = Field(default_factory=list)
    shapes: list[dict[str, Any]] = Field(default_factory=list)
    courtyard_geometry: dict[str, list[GeometryShape]] = Field(default_factory=dict)
    model_3d: dict[str, Any] | None = None
    bbox: dict[str, float] | None = None


class LibraryComponent(StrictModel):
    stable_id: StableId
    index: int = Field(ge=0)
    name: str
    refdes: str = ""
    value: str = ""
    manufacturer: str = ""
    datasheet: str = ""
    fields: dict[str, str] = Field(default_factory=dict)
    pattern_style: str | None = None
    part_count: int = Field(ge=0)
    pins: list[LibraryPin] = Field(default_factory=list)


class LibraryValidationFinding(StrictModel):
    code: str = Field(min_length=1)
    severity: Literal["error", "warning", "info"]
    message: str
    object_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LibraryModel(StrictModel):
    document_id: str
    source_type: str
    name: str = ""
    hint: str = ""
    version: str = ""
    source_units: str = "mm"
    coordinate_units: Literal["mm"] = "mm"
    components: list[LibraryComponent] = Field(default_factory=list)
    patterns: list[LibraryPattern] = Field(default_factory=list)
    pad_styles: list[LibraryPadStyle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QuerySelector(StrictModel):
    ids: list[str] = Field(default_factory=list, max_length=1_000)
    kinds: list[str] = Field(default_factory=list, max_length=100)
    refdes: list[str] = Field(default_factory=list, max_length=1_000)
    refdes_glob: str | None = Field(default=None, max_length=256)
    refdes_regex: str | None = Field(default=None, max_length=256)
    names: list[str] = Field(default_factory=list, max_length=1_000)
    name_regex: str | None = Field(default=None, max_length=256)
    values: list[str] = Field(default_factory=list, max_length=1_000)
    fields: dict[str, str] = Field(default_factory=dict)
    nets: list[str] = Field(default_factory=list, max_length=1_000)
    layers: list[str] = Field(default_factory=list, max_length=100)
    sides: list[str] = Field(default_factory=list, max_length=10)
    text: str | None = Field(default=None, max_length=1_000)
    selected: bool | None = None
    locked: bool | None = None
    bbox: dict[str, float] | None = None
    near: dict[str, float] | None = None
    max_distance: float | None = Field(default=None, ge=0.0)

    @field_validator("refdes_regex", "name_regex")
    @classmethod
    def validate_regex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regular expression: {exc}") from exc
        return value

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        return ObjectRecord.validate_bbox(value)

    @field_validator("near")
    @classmethod
    def validate_near(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is not None and set(value) != {"x", "y"}:
            raise ValueError("near must contain exactly x and y")
        return value

    @model_validator(mode="after")
    def validate_distance(self) -> QuerySelector:
        if self.max_distance is not None and self.near is None:
            raise ValueError("max_distance requires near")
        return self

    def is_empty(self) -> bool:
        return not any(
            (
                self.ids,
                self.kinds,
                self.refdes,
                self.refdes_glob,
                self.refdes_regex,
                self.names,
                self.name_regex,
                self.values,
                self.fields,
                self.nets,
                self.layers,
                self.sides,
                self.text,
                self.selected is not None,
                self.locked is not None,
                self.bbox is not None,
                self.near is not None,
            )
        )


class QueryRequest(StrictModel):
    selector: QuerySelector = Field(default_factory=QuerySelector)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
    sort_by: Literal["stable_id", "kind", "label", "name", "value", "refdes", "layer"] = (
        "stable_id"
    )
    include_geometry: bool = True
    include_relationships: bool = True


class QueryResult(StrictModel):
    document_id: str
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    items: list[ObjectRecord] = Field(default_factory=list)


class WriteScope(StrictModel):
    object_ids: list[str] = Field(default_factory=list)
    refdes: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    bbox: dict[str, float] | None = None
    whole_document: bool = False
    include_locked: bool = False
    respect_keepouts: bool = True
    preserve_unselected: bool = True

    @model_validator(mode="after")
    def require_scope(self) -> WriteScope:
        if not self.whole_document and not any(
            (self.object_ids, self.refdes, self.nets, self.layers, self.bbox)
        ):
            raise ValueError("an explicit scope or whole_document=true is required")
        return self


TransactionStatus = Literal[
    "planned",
    "staged",
    "validated",
    "committed",
    "rolled_back",
    "failed",
]


RiskClass = Literal[
    "safe_read",
    "analysis",
    "guarded_plan",
    "limited_write",
    "elevated_write",
    "external_execution",
    "manufacturing_export",
]


class TransactionRisk(StrictModel):
    level: Literal["low", "medium", "high"] = "low"
    risk_class: RiskClass = "guarded_plan"
    reasons: list[str] = Field(default_factory=list)


class TransactionRecord(StrictModel):
    txid: str = Field(pattern=r"^tx_[0-9a-f-]{36}$")
    document_id: str
    status: TransactionStatus
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_path: str
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    created_at: str
    updated_at: str
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    changed_ids: list[str] = Field(default_factory=list)
    compiled_patch_count: int = Field(default=0, ge=0)
    risk: TransactionRisk = Field(default_factory=TransactionRisk)
    validation_before: dict[str, Any] = Field(default_factory=dict)
    validation_after_preview: dict[str, Any] = Field(default_factory=dict)
    preview_resources: list[str] = Field(default_factory=list)
    snapshot_path: str | None = None
    backup_path: str | None = None
    committed_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rolled_back_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)


PlanStatus = Literal["planned", "staged", "committed", "obsolete"]


class PlanRecord(StrictModel):
    plan_id: str = Field(pattern=r"^plan_[0-9a-f]{32}$")
    plan_type: str = Field(min_length=1, max_length=64)
    status: PlanStatus = "planned"
    document_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_path: str
    created_at: str
    updated_at: str
    config: dict[str, Any] = Field(default_factory=dict)
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    changed_ids: list[str] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    score: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    preview_resources: list[str] = Field(default_factory=list)
    transaction_id: str | None = Field(default=None, pattern=r"^tx_[0-9a-f-]{36}$")


class CapabilityReport(StrictModel):
    server_version: str
    source_types: dict[str, Any] = Field(default_factory=dict)
    read_capabilities: dict[str, Any] = Field(default_factory=dict)
    write_capabilities: dict[str, Any] = Field(default_factory=dict)
    experimental_capabilities: dict[str, Any] = Field(default_factory=dict)
    external_adapters: dict[str, Any] = Field(default_factory=dict)
    geometry_backend: dict[str, Any] = Field(default_factory=dict)
    preview_formats: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    reasons_unavailable: list[dict[str, Any]] = Field(default_factory=list)
    registered_checks: list[str] = Field(default_factory=list)
    workflow_prompts: list[dict[str, Any]] = Field(default_factory=list)


ImpedanceStructure = Literal[
    "microstrip",
    "differential_microstrip",
    "symmetric_stripline",
]


class ImpedanceInput(StrictModel):
    structure: ImpedanceStructure
    width_mm: float = Field(gt=0.0, allow_inf_nan=False)
    copper_thickness_mm: float = Field(ge=0.0, allow_inf_nan=False)
    dielectric_height_mm: float = Field(gt=0.0, allow_inf_nan=False)
    dielectric_constant: float = Field(gt=1.0, allow_inf_nan=False)
    gap_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    frequency_hz: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    target_ohm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    tolerance_ohm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    source: str = "explicit"

    @model_validator(mode="after")
    def require_differential_gap(self) -> ImpedanceInput:
        if self.structure == "differential_microstrip" and self.gap_mm is None:
            raise ValueError("gap_mm is required for differential_microstrip")
        return self


class ImpedanceResult(StrictModel):
    structure: ImpedanceStructure
    estimated_impedance_ohm: float = Field(gt=0.0, allow_inf_nan=False)
    effective_dielectric_constant: float | None = Field(
        default=None, gt=1.0, allow_inf_nan=False
    )
    method: str
    inputs: ImpedanceInput
    confidence: Literal["low", "medium", "high"]
    preliminary_only: bool = True
    delta_to_target_ohm: float | None = Field(default=None, allow_inf_nan=False)
    within_tolerance: bool | None = None
    sensitivity_ohm_per_percent: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validity: dict[str, Any] = Field(default_factory=dict)


class FieldSolverRequest(StrictModel):
    """Typed quasi-TEM/full-wave stripline request for an external solver backend."""

    schema_version: Literal["diptrace-field-solver-request-v1"] = (
        "diptrace-field-solver-request-v1"
    )
    structure: Literal["stripline"] = "stripline"
    width_mm: float = Field(gt=0.0, allow_inf_nan=False)
    copper_thickness_mm: float = Field(gt=0.0, allow_inf_nan=False)
    lower_dielectric_height_mm: float = Field(gt=0.0, allow_inf_nan=False)
    upper_dielectric_height_mm: float = Field(gt=0.0, allow_inf_nan=False)
    dielectric_constant: float = Field(gt=1.0, allow_inf_nan=False)
    dielectric_loss_tangent: float = Field(default=0.0, ge=0.0, lt=1.0, allow_inf_nan=False)
    conductor_conductivity_s_per_m: float = Field(
        default=58_000_000.0, gt=0.0, allow_inf_nan=False
    )
    frequencies_hz: list[float] = Field(min_length=1, max_length=1001)
    trace_length_mm: float = Field(default=20.0, gt=0.0, allow_inf_nan=False)
    port_impedance_ohm: float = Field(default=50.0, gt=0.0, allow_inf_nan=False)
    mesh_cells_per_wavelength: int = Field(default=30, ge=10, le=100)

    @model_validator(mode="after")
    def validate_frequency_sweep(self) -> FieldSolverRequest:
        if any(not math.isfinite(value) or value <= 0.0 for value in self.frequencies_hz):
            raise ValueError("frequencies_hz must contain finite positive values")
        if self.frequencies_hz != sorted(set(self.frequencies_hz)):
            raise ValueError("frequencies_hz must be strictly increasing and unique")
        return self


class FieldSolverPoint(StrictModel):
    frequency_hz: float = Field(gt=0.0, allow_inf_nan=False)
    characteristic_impedance_real_ohm: float = Field(gt=0.0, allow_inf_nan=False)
    characteristic_impedance_imag_ohm: float = Field(allow_inf_nan=False)
    propagation_alpha_np_per_m: float = Field(ge=0.0, allow_inf_nan=False)
    propagation_beta_rad_per_m: float = Field(gt=0.0, allow_inf_nan=False)
    conductor_loss_db_per_m: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    dielectric_loss_db_per_m: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)


class FieldSolverResult(StrictModel):
    schema_version: Literal["diptrace-field-solver-result-v1"]
    backend: Literal["openems"]
    solver_version: str = Field(min_length=1, max_length=128)
    converged: bool
    points: list[FieldSolverPoint] = Field(min_length=1, max_length=1001)
    mesh: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=100)


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class JobRecord(StrictModel):
    jobid: str = Field(pattern=r"^job_[0-9a-f]{32}$")
    job_type: str = Field(min_length=1, max_length=64)
    status: JobStatus
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    document_id: str | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    target_path: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    phase: str = "queued"
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    command: list[str] = Field(default_factory=list, max_length=64)
    artifacts: dict[str, str] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    partial_result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class ExportRecord(StrictModel):
    export_id: str = Field(pattern=r"^export_[0-9a-f]{32}$")
    export_type: Literal["bom", "fabrication_manifest", "assembly_manifest", "si_geometry"]
    document_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class SpecctraWire(StrictModel):
    layer: str = Field(min_length=1, max_length=256)
    width_mm: float = Field(gt=0.0)
    points: list[dict[str, float]] = Field(min_length=2, max_length=100_000)


class SpecctraVia(StrictModel):
    padstack: str = Field(min_length=1, max_length=256)
    position: dict[str, float]


class SpecctraNetRoute(StrictModel):
    name: str = Field(min_length=1, max_length=1_000)
    wires: list[SpecctraWire] = Field(default_factory=list, max_length=100_000)
    vias: list[SpecctraVia] = Field(default_factory=list, max_length=100_000)


class SpecctraSession(StrictModel):
    name: str
    base_design: str
    resolution_unit: str
    resolution: float = Field(gt=0.0)
    routes: list[SpecctraNetRoute] = Field(default_factory=list, max_length=100_000)
    padstacks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
