from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import BBox, Point, distance
from .operations import MoveComponentsOperation, SemanticOperation

_EPS = 1e-9
PartRole = Literal[
    "active",
    "power_control",
    "connector",
    "support",
    "protection",
    "timing",
    "control",
    "other",
]
NetRole = Literal["ground", "power", "clock", "reset", "interface", "signal", "unknown"]
BlockRole = Literal["connector", "power", "functional", "generic"]


class SchematicPartIntent(StrictModel):
    part_id: str
    refdes: str | None = None
    role: PartRole
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class SchematicNetIntent(StrictModel):
    net_id: str
    name: str | None = None
    role: NetRole
    confidence: float = Field(ge=0.0, le=1.0)
    part_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SchematicFunctionalBlock(StrictModel):
    block_id: str
    role: BlockRole
    anchor_part_ids: list[str] = Field(default_factory=list)
    member_part_ids: list[str] = Field(default_factory=list)
    support_part_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class ReferenceMotifConstraint(StrictModel):
    first_key: str = Field(min_length=1, max_length=128)
    second_key: str = Field(min_length=1, max_length=128)
    relation: Literal[
        "near",
        "left_of",
        "right_of",
        "above",
        "below",
        "same_row",
        "same_column",
    ]
    max_distance_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    tolerance_mm: float = Field(default=2.5, ge=0.0, allow_inf_nan=False)
    weight: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_constraint(self) -> ReferenceMotifConstraint:
        if self.first_key == self.second_key:
            raise ValueError("motif constraint endpoints must be different")
        if self.relation == "near" and self.max_distance_mm is None:
            raise ValueError("near motif constraint requires max_distance_mm")
        return self


class ReferenceMotif(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=2_048)
    source_kind: Literal["datasheet", "reference_design", "project", "builtin"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    constraints: list[ReferenceMotifConstraint] = Field(default_factory=list)


class BoundReferenceMotif(StrictModel):
    motif: ReferenceMotif
    bindings: dict[str, str] = Field(default_factory=dict)


class SchematicDesignIntent(StrictModel):
    document_id: str
    parts: list[SchematicPartIntent] = Field(default_factory=list)
    nets: list[SchematicNetIntent] = Field(default_factory=list)
    blocks: list[SchematicFunctionalBlock] = Field(default_factory=list)
    motifs: list[BoundReferenceMotif] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SchematicLayoutWeights(StrictModel):
    part_overlap: float = Field(default=10_000.0, ge=0.0)
    wire_overlap: float = Field(default=5_000.0, ge=0.0)
    wire_crossing: float = Field(default=1_000.0, ge=0.0)
    diagonal_segment: float = Field(default=250.0, ge=0.0)
    bend: float = Field(default=1.0, ge=0.0)
    wire_length: float = Field(default=0.05, ge=0.0)
    block_span: float = Field(default=0.2, ge=0.0)
    occupied_area: float = Field(default=0.001, ge=0.0)
    motif_violation: float = Field(default=100.0, ge=0.0)


class SchematicLayoutMetrics(StrictModel):
    part_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    wire_count: int = Field(ge=0)
    part_overlap_count: int = Field(ge=0)
    wire_overlap_count: int = Field(ge=0)
    wire_crossing_count: int = Field(ge=0)
    diagonal_segment_count: int = Field(ge=0)
    bend_count: int = Field(ge=0)
    total_wire_length_mm: float = Field(ge=0.0)
    occupied_width_mm: float = Field(ge=0.0)
    occupied_height_mm: float = Field(ge=0.0)
    occupied_area_mm2: float = Field(ge=0.0)
    content_area_mm2: float = Field(ge=0.0)
    density_ratio: float = Field(ge=0.0)
    mean_block_span_mm: float = Field(ge=0.0)
    max_block_span_mm: float = Field(ge=0.0)
    motif_violation_count: int = Field(ge=0)
    score_terms: dict[str, float] = Field(default_factory=dict)
    score: float = Field(ge=0.0)


class SchematicLayoutAnalysis(StrictModel):
    intent: SchematicDesignIntent
    metrics: SchematicLayoutMetrics
    motif_results: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SchematicPlacementConfig(StrictModel):
    grid_mm: float = Field(default=2.5, gt=0.0, le=100.0)
    origin_x_mm: float = Field(default=20.0, allow_inf_nan=False)
    origin_y_mm: float = Field(default=20.0, allow_inf_nan=False)
    block_gap_x_mm: float = Field(default=20.0, gt=0.0, le=500.0)
    block_gap_y_mm: float = Field(default=15.0, gt=0.0, le=500.0)
    anchor_gap_y_mm: float = Field(default=10.0, gt=0.0, le=500.0)
    member_gap_x_mm: float = Field(default=15.0, gt=0.0, le=500.0)
    member_gap_y_mm: float = Field(default=10.0, gt=0.0, le=500.0)
    target_row_width_mm: float = Field(default=140.0, gt=20.0, le=2_000.0)
    max_parts: int = Field(default=200, ge=1, le=2_000)
    allow_existing_wires: bool = False
    weights: SchematicLayoutWeights = Field(default_factory=SchematicLayoutWeights)


@dataclass(frozen=True, slots=True)
class SchematicPlacementPlan:
    operations: list[SemanticOperation]
    placements: dict[str, Point]
    before: SchematicLayoutAnalysis
    after: SchematicLayoutAnalysis
    changed_part_ids: list[str]
    unresolved: list[dict[str, Any]]
    assumptions: list[str]
    warnings: list[str]
    limitations: list[str]


@dataclass(frozen=True, slots=True)
class _Segment:
    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @property
    def horizontal(self) -> bool:
        return math.isclose(self.start.y, self.end.y, abs_tol=_EPS)

    @property
    def vertical(self) -> bool:
        return math.isclose(self.start.x, self.end.x, abs_tol=_EPS)


def _require_schematic(snapshot: DocumentSnapshot) -> None:
    if snapshot.schematic is None:
        raise CapabilityUnavailableError("Schematic layout analysis requires a schematic document")


def _part_role(part: ObjectRecord) -> SchematicPartIntent:
    refdes = (part.refdes or "").upper()
    prefix_match = re.match(r"[A-Z]+", refdes)
    prefix = prefix_match.group(0) if prefix_match else ""
    text = " ".join(
        value
        for value in (
            part.refdes,
            part.name,
            part.value,
            str(part.attributes.get("part_name", "")),
        )
        if value
    ).upper()
    if prefix in {"J", "P", "CN", "CON"} or any(
        token in text for token in ("CONNECTOR", "HEADER", "USB-C", "TYPE-C")
    ):
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="connector",
            confidence=0.9,
            reasons=["connector-like RefDes/name"],
        )
    if prefix in {"U", "IC"}:
        if any(
            token in text
            for token in ("LDO", "BUCK", "BOOST", "REGULATOR", "PMIC", "CONVERTER", "DCDC", "DC/DC")
        ):
            return SchematicPartIntent(
                part_id=part.stable_id,
                refdes=part.refdes,
                role="power_control",
                confidence=0.85,
                reasons=["active device with power-conversion/regulation keyword"],
            )
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="active",
            confidence=0.8,
            reasons=["IC-style RefDes"],
        )
    if prefix in {"Q", "T", "K"}:
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="active",
            confidence=0.7,
            reasons=["active-device RefDes"],
        )
    if prefix in {"Y", "X"} or any(token in text for token in ("XTAL", "CRYSTAL", "OSCILLATOR")):
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="timing",
            confidence=0.85,
            reasons=["timing-source RefDes/name"],
        )
    if prefix == "F" or any(token in text for token in ("TVS", "ESD", "FUSE")):
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="protection",
            confidence=0.8,
            reasons=["protection-device RefDes/name"],
        )
    if prefix in {"SW", "S"} or "SWITCH" in text or "BUTTON" in text:
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="control",
            confidence=0.75,
            reasons=["human/control-device RefDes/name"],
        )
    if prefix in {"R", "C", "L", "D", "FB", "NTC", "RT", "LED"}:
        return SchematicPartIntent(
            part_id=part.stable_id,
            refdes=part.refdes,
            role="support",
            confidence=0.75,
            reasons=["passive/support RefDes"],
        )
    return SchematicPartIntent(
        part_id=part.stable_id,
        refdes=part.refdes,
        role="other",
        confidence=0.4,
        reasons=["no stronger deterministic role signal"],
    )


def _net_role(net: ObjectRecord, part_ids: list[str]) -> SchematicNetIntent:
    name = (net.name or net.net_name or "").strip()
    folded = name.upper().replace(" ", "")
    if not folded:
        return SchematicNetIntent(
            net_id=net.stable_id,
            name=None,
            role="unknown",
            confidence=0.2,
            part_ids=part_ids,
            reasons=["net has no usable name"],
        )
    if re.match(r"^(GND|AGND|DGND|PGND|0V|VSS)([_-].*)?$", folded):
        role: NetRole = "ground"
        confidence = 0.98
        reason = "ground-name pattern"
    elif re.match(r"^(\+?-?[0-9]+V[0-9]*|VCC|VDD|VIN|VOUT|VBAT|VSYS|VREF)([_-].*)?$", folded):
        role = "power"
        confidence = 0.92
        reason = "power-rail name pattern"
    elif any(token in folded for token in ("CLK", "CLOCK", "XTAL", "OSC")):
        role = "clock"
        confidence = 0.9
        reason = "clock/timing keyword"
    elif any(token in folded for token in ("RESET", "NRST", "RST")):
        role = "reset"
        confidence = 0.9
        reason = "reset keyword"
    elif any(
        token in folded
        for token in (
            "USB",
            "CAN",
            "I2C",
            "SCL",
            "SDA",
            "SPI",
            "MOSI",
            "MISO",
            "SCK",
            "UART",
            "TX",
            "RX",
            "SWD",
            "JTAG",
        )
    ):
        role = "interface"
        confidence = 0.8
        reason = "common interface keyword"
    else:
        role = "signal"
        confidence = 0.55
        reason = "named net without a stronger deterministic class"
    return SchematicNetIntent(
        net_id=net.stable_id,
        name=name,
        role=role,
        confidence=confidence,
        part_ids=part_ids,
        reasons=[reason],
    )


def _net_parts(snapshot: DocumentSnapshot) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    assert snapshot.schematic is not None
    pins = {pin.stable_id: pin for pin in snapshot.schematic.pins}
    net_parts: dict[str, list[str]] = {}
    part_nets: dict[str, set[str]] = defaultdict(set)
    for net in snapshot.schematic.nets:
        owners: set[str] = set()
        for endpoint_id in net.relationships.get("endpoints", []):
            pin = pins.get(endpoint_id)
            if pin is not None and pin.parent_id is not None:
                owners.add(pin.parent_id)
        ordered = sorted(owners)
        net_parts[net.stable_id] = ordered
        for part_id in ordered:
            part_nets[part_id].add(net.stable_id)
    return net_parts, part_nets


def _block_id(member_ids: list[str]) -> str:
    digest = hashlib.sha256("\0".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:16]
    return f"schematic-block-{digest}"


def _block_role(anchor_roles: set[PartRole]) -> BlockRole:
    if "connector" in anchor_roles:
        return "connector"
    if "power_control" in anchor_roles:
        return "power"
    if "active" in anchor_roles:
        return "functional"
    return "generic"


def infer_schematic_design_intent(
    snapshot: DocumentSnapshot,
    *,
    motifs: list[BoundReferenceMotif] | None = None,
) -> SchematicDesignIntent:
    """Infer a conservative, deterministic schematic intent model.

    The baseline intentionally relies only on information already present in the
    normalized schematic. It does not invent datasheet knowledge. Ambiguous
    support-part assignment is left unresolved instead of being guessed.
    """
    _require_schematic(snapshot)
    assert snapshot.schematic is not None
    part_intents = [_part_role(part) for part in snapshot.schematic.parts]
    part_intent_by_id = {item.part_id: item for item in part_intents}
    net_parts, part_nets = _net_parts(snapshot)
    net_intents = [
        _net_role(net, net_parts.get(net.stable_id, [])) for net in snapshot.schematic.nets
    ]
    net_role_by_id = {item.net_id: item.role for item in net_intents}

    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    anchor_roles: set[PartRole] = {"active", "power_control", "connector"}
    anchor_groups: dict[str, list[str]] = defaultdict(list)
    for part in snapshot.schematic.parts:
        role = part_intent_by_id[part.stable_id].role
        if role not in anchor_roles:
            continue
        group_key = (part.refdes or part.stable_id).casefold()
        anchor_groups[group_key].append(part.stable_id)

    assigned: set[str] = set()
    block_members: dict[str, list[str]] = {}
    block_anchors: dict[str, list[str]] = {}
    block_reasons: dict[str, list[str]] = {}
    for key, anchor_ids in sorted(anchor_groups.items()):
        ordered = sorted(anchor_ids)
        block_members[key] = list(ordered)
        block_anchors[key] = list(ordered)
        block_reasons[key] = ["block seeded by active/connector anchor"]
        assigned.update(ordered)

    support_roles: set[PartRole] = {"support", "protection", "timing", "control", "other"}
    for part in sorted(snapshot.schematic.parts, key=lambda item: item.stable_id):
        if part.stable_id in assigned:
            continue
        if part_intent_by_id[part.stable_id].role not in support_roles:
            continue
        scores: list[tuple[int, str]] = []
        own_nets = part_nets.get(part.stable_id, set())
        for key, anchor_ids in anchor_groups.items():
            anchor_nets: set[str] = set()
            for anchor_id in anchor_ids:
                anchor_nets.update(part_nets.get(anchor_id, set()))
            score = 0
            for net_id in own_nets & anchor_nets:
                role = net_role_by_id.get(net_id, "unknown")
                score += 1 if role in {"ground", "power"} else 10
            if score > 0:
                scores.append((score, key))
        if not scores:
            continue
        best_score = max(score for score, _key in scores)
        winners = sorted(key for score, key in scores if score == best_score)
        if len(winners) != 1:
            continue
        winner = winners[0]
        block_members[winner].append(part.stable_id)
        block_reasons[winner].append(
            f"support part {part.refdes or part.stable_id} assigned by unique connectivity score"
        )
        assigned.add(part.stable_id)

    adjacency: dict[str, set[str]] = {part.stable_id: set() for part in snapshot.schematic.parts}
    for net_intent in net_intents:
        if net_intent.role in {"ground", "power"}:
            continue
        members = [part_id for part_id in net_intent.part_ids if part_id not in assigned]
        for index, first in enumerate(members):
            adjacency[first].update(members[:index])
            adjacency[first].update(members[index + 1 :])

    unassigned = sorted(set(parts_by_id) - assigned)
    seen: set[str] = set()
    generic_index = 0
    for start in unassigned:
        if start in seen:
            continue
        stack = [start]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(sorted(adjacency.get(current, set()) - seen, reverse=True))
        key = f"generic-{generic_index:04d}"
        generic_index += 1
        block_members[key] = sorted(component)
        block_anchors[key] = []
        block_reasons[key] = ["no unique active/connector anchor was inferable"]

    blocks: list[SchematicFunctionalBlock] = []
    for key in sorted(block_members):
        members = sorted(block_members[key])
        anchors = sorted(block_anchors.get(key, []))
        anchor_role_set = {part_intent_by_id[item].role for item in anchors}
        support_ids = sorted(set(members) - set(anchors))
        confidence = (
            min((part_intent_by_id[item].confidence for item in anchors), default=0.45)
            if anchors
            else 0.4
        )
        blocks.append(
            SchematicFunctionalBlock(
                block_id=_block_id(members),
                role=_block_role(anchor_role_set),
                anchor_part_ids=anchors,
                member_part_ids=members,
                support_part_ids=support_ids,
                confidence=confidence,
                reasons=block_reasons[key],
            )
        )

    warnings: list[str] = []
    unresolved_support = [
        part
        for part in part_intents
        if part.role in support_roles
        and all(part.part_id not in block.anchor_part_ids for block in blocks)
        and any(
            part.part_id in block.member_part_ids and block.role == "generic" for block in blocks
        )
    ]
    if unresolved_support:
        warnings.append(
            f"{len(unresolved_support)} support/other parts could not be assigned "
            "to a unique anchor"
        )
    return SchematicDesignIntent(
        document_id=snapshot.schematic.document_id,
        parts=part_intents,
        nets=net_intents,
        blocks=blocks,
        motifs=list(motifs or []),
        assumptions=[
            "Intent inference uses only schematic XML topology, names and RefDes conventions.",
            "Power and ground nets are weak grouping evidence because they commonly "
            "span many blocks.",
            "Reference motifs are never invented from a component name; they must be "
            "supplied explicitly.",
        ],
        warnings=warnings,
    )


def _position_for(part: ObjectRecord, placements: Mapping[str, Point] | None) -> Point | None:
    if placements is not None and part.stable_id in placements:
        return placements[part.stable_id]
    if part.position is None:
        return None
    return Point(**part.position)


def _bbox_for(part: ObjectRecord, placements: Mapping[str, Point] | None) -> BBox | None:
    if part.bbox is None:
        return None
    box = BBox(**part.bbox)
    if placements is None or part.stable_id not in placements or part.position is None:
        return box
    original = Point(**part.position)
    target = placements[part.stable_id]
    return BBox(
        box.min_x + target.x - original.x,
        box.min_y + target.y - original.y,
        box.max_x + target.x - original.x,
        box.max_y + target.y - original.y,
    )


def _wire_points(wire: ObjectRecord) -> list[Point]:
    raw = wire.attributes.get("points", [])
    if not isinstance(raw, list):
        return []
    return [
        Point(float(item["x"]), float(item["y"]))
        for item in raw
        if isinstance(item, dict) and "x" in item and "y" in item
    ]


def _same_point(first: Point, second: Point) -> bool:
    return math.isclose(first.x, second.x, abs_tol=_EPS) and math.isclose(
        first.y, second.y, abs_tol=_EPS
    )


def _cross(first: Point, second: Point, third: Point) -> float:
    return (second.x - first.x) * (third.y - first.y) - (
        second.y - first.y
    ) * (third.x - first.x)


def _point_on_segment(point: Point, segment: _Segment) -> bool:
    return (
        abs(_cross(segment.start, segment.end, point)) <= _EPS
        and min(segment.start.x, segment.end.x) - _EPS
        <= point.x
        <= max(segment.start.x, segment.end.x) + _EPS
        and min(segment.start.y, segment.end.y) - _EPS
        <= point.y
        <= max(segment.start.y, segment.end.y) + _EPS
    )


def _segments_intersect(first: _Segment, second: _Segment) -> bool:
    c1 = _cross(first.start, first.end, second.start)
    c2 = _cross(first.start, first.end, second.end)
    c3 = _cross(second.start, second.end, first.start)
    c4 = _cross(second.start, second.end, first.end)
    if (
        ((c1 > _EPS and c2 < -_EPS) or (c1 < -_EPS and c2 > _EPS))
        and ((c3 > _EPS and c4 < -_EPS) or (c3 < -_EPS and c4 > _EPS))
    ):
        return True
    return (
        (abs(c1) <= _EPS and _point_on_segment(second.start, first))
        or (abs(c2) <= _EPS and _point_on_segment(second.end, first))
        or (abs(c3) <= _EPS and _point_on_segment(first.start, second))
        or (abs(c4) <= _EPS and _point_on_segment(first.end, second))
    )


def _collinear_overlap_length(first: _Segment, second: _Segment) -> float:
    if abs(_cross(first.start, first.end, second.start)) > _EPS or abs(
        _cross(first.start, first.end, second.end)
    ) > _EPS:
        return 0.0
    if first.horizontal and second.horizontal:
        return max(
            0.0,
            min(max(first.start.x, first.end.x), max(second.start.x, second.end.x))
            - max(min(first.start.x, first.end.x), min(second.start.x, second.end.x)),
        )
    if first.vertical and second.vertical:
        return max(
            0.0,
            min(max(first.start.y, first.end.y), max(second.start.y, second.end.y))
            - max(min(first.start.y, first.end.y), min(second.start.y, second.end.y)),
        )
    return 0.0


def _wire_metrics(wires: list[ObjectRecord]) -> tuple[int, int, int, int, float, list[Point]]:
    wire_segments: list[tuple[str | None, int, _Segment]] = []
    diagonal_count = 0
    bend_count = 0
    total_length = 0.0
    all_points: list[Point] = []
    for wire_index, wire in enumerate(wires):
        points = _wire_points(wire)
        all_points.extend(points)
        segments = [
            _Segment(first, second)
            for first, second in zip(points, points[1:], strict=False)
            if not _same_point(first, second)
        ]
        total_length += sum(segment.length for segment in segments)
        diagonal_count += sum(
            not (segment.horizontal or segment.vertical) for segment in segments
        )
        for first, second in zip(segments, segments[1:], strict=False):
            first_dx = first.end.x - first.start.x
            first_dy = first.end.y - first.start.y
            second_dx = second.end.x - second.start.x
            second_dy = second.end.y - second.start.y
            if abs(first_dx * second_dy - first_dy * second_dx) > _EPS:
                bend_count += 1
        wire_segments.extend((wire.net_name, wire_index, segment) for segment in segments)

    crossing_count = 0
    overlap_count = 0
    for index, (first_net, first_wire, first) in enumerate(wire_segments):
        for second_net, second_wire, second in wire_segments[index + 1 :]:
            if first_wire == second_wire:
                continue
            overlap = _collinear_overlap_length(first, second)
            if overlap > _EPS:
                overlap_count += 1
                continue
            if not _segments_intersect(first, second):
                continue
            if (
                _same_point(first.start, second.start)
                or _same_point(first.start, second.end)
                or _same_point(first.end, second.start)
                or _same_point(first.end, second.end)
            ):
                continue
            if first_net == second_net:
                continue
            crossing_count += 1
    return overlap_count, crossing_count, diagonal_count, bend_count, total_length, all_points


def _motif_relation_error(
    first: Point,
    second: Point,
    constraint: ReferenceMotifConstraint,
) -> float:
    if constraint.relation == "near":
        assert constraint.max_distance_mm is not None
        return max(0.0, distance(first, second) - constraint.max_distance_mm)
    if constraint.relation == "left_of":
        return max(0.0, first.x - second.x + constraint.tolerance_mm)
    if constraint.relation == "right_of":
        return max(0.0, second.x - first.x + constraint.tolerance_mm)
    if constraint.relation == "above":
        return max(0.0, first.y - second.y + constraint.tolerance_mm)
    if constraint.relation == "below":
        return max(0.0, second.y - first.y + constraint.tolerance_mm)
    if constraint.relation == "same_row":
        return max(0.0, abs(first.y - second.y) - constraint.tolerance_mm)
    return max(0.0, abs(first.x - second.x) - constraint.tolerance_mm)


def score_reference_motif(
    snapshot: DocumentSnapshot,
    bound: BoundReferenceMotif,
    *,
    placements: Mapping[str, Point] | None = None,
) -> dict[str, Any]:
    _require_schematic(snapshot)
    assert snapshot.schematic is not None
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    violations: list[dict[str, Any]] = []
    score = 0.0
    for constraint in bound.motif.constraints:
        first_id = bound.bindings.get(constraint.first_key)
        second_id = bound.bindings.get(constraint.second_key)
        if first_id is None or second_id is None:
            violations.append(
                {"constraint": constraint.model_dump(mode="json"), "reason": "unbound_motif_key"}
            )
            score += constraint.weight
            continue
        first_part = parts_by_id.get(first_id)
        second_part = parts_by_id.get(second_id)
        if first_part is None or second_part is None:
            violations.append(
                {"constraint": constraint.model_dump(mode="json"), "reason": "bound_part_missing"}
            )
            score += constraint.weight
            continue
        first = _position_for(first_part, placements)
        second = _position_for(second_part, placements)
        if first is None or second is None:
            violations.append(
                {"constraint": constraint.model_dump(mode="json"), "reason": "position_missing"}
            )
            score += constraint.weight
            continue
        error = _motif_relation_error(first, second, constraint)
        if error <= _EPS:
            continue
        contribution = error * constraint.weight
        score += contribution
        violations.append(
            {
                "constraint": constraint.model_dump(mode="json"),
                "error_mm": error,
                "contribution": contribution,
            }
        )
    return {
        "name": bound.motif.name,
        "source": bound.motif.source,
        "source_kind": bound.motif.source_kind,
        "score": score,
        "violation_count": len(violations),
        "violations": violations,
    }


def analyze_schematic_layout(
    snapshot: DocumentSnapshot,
    *,
    intent: SchematicDesignIntent | None = None,
    placements: Mapping[str, Point] | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    weights: SchematicLayoutWeights | None = None,
) -> SchematicLayoutAnalysis:
    """Measure deterministic readability/layout properties of a schematic."""
    _require_schematic(snapshot)
    assert snapshot.schematic is not None
    weights = weights or SchematicLayoutWeights()
    intent = intent or infer_schematic_design_intent(snapshot, motifs=motifs)
    if motifs is None:
        motifs = intent.motifs

    parts = snapshot.schematic.parts
    part_overlap_count = 0
    part_boxes: list[tuple[str, BBox]] = []
    content_area = 0.0
    extent_points: list[Point] = []
    for part in parts:
        position = _position_for(part, placements)
        if position is not None:
            extent_points.append(position)
        box = _bbox_for(part, placements)
        if box is None:
            continue
        content_area += box.area
        part_boxes.append((str(part.attributes.get("sheet", "0")), box))
        extent_points.extend([Point(box.min_x, box.min_y), Point(box.max_x, box.max_y)])
    for index, (first_sheet, first) in enumerate(part_boxes):
        for second_sheet, second in part_boxes[index + 1 :]:
            if first_sheet == second_sheet and first.overlap_area(second) > _EPS:
                part_overlap_count += 1

    (
        wire_overlap_count,
        wire_crossing_count,
        diagonal_segment_count,
        bend_count,
        total_wire_length,
        wire_extent_points,
    ) = _wire_metrics(snapshot.schematic.wires)
    extent_points.extend(wire_extent_points)

    if extent_points:
        min_x = min(point.x for point in extent_points)
        min_y = min(point.y for point in extent_points)
        max_x = max(point.x for point in extent_points)
        max_y = max(point.y for point in extent_points)
        occupied_width = max_x - min_x
        occupied_height = max_y - min_y
        occupied_area = occupied_width * occupied_height
    else:
        occupied_width = occupied_height = occupied_area = 0.0
    density = content_area / occupied_area if occupied_area > _EPS else 0.0

    parts_by_id = {part.stable_id: part for part in parts}
    block_spans: list[float] = []
    for block in intent.blocks:
        positions = [
            point
            for part_id in block.member_part_ids
            if (part := parts_by_id.get(part_id)) is not None
            and (point := _position_for(part, placements)) is not None
        ]
        if len(positions) < 2:
            block_spans.append(0.0)
            continue
        block_box = BBox.from_points(positions)
        block_spans.append(
            math.hypot(block_box.max_x - block_box.min_x, block_box.max_y - block_box.min_y)
        )
    mean_block_span = sum(block_spans) / len(block_spans) if block_spans else 0.0
    max_block_span = max(block_spans, default=0.0)

    motif_results = [
        score_reference_motif(snapshot, bound, placements=placements) for bound in motifs
    ]
    motif_violation_count = sum(int(result["violation_count"]) for result in motif_results)
    motif_score = sum(float(result["score"]) for result in motif_results)

    score_terms = {
        "part_overlap": part_overlap_count * weights.part_overlap,
        "wire_overlap": wire_overlap_count * weights.wire_overlap,
        "wire_crossing": wire_crossing_count * weights.wire_crossing,
        "diagonal_segment": diagonal_segment_count * weights.diagonal_segment,
        "bend": bend_count * weights.bend,
        "wire_length": total_wire_length * weights.wire_length,
        "block_span": mean_block_span * weights.block_span,
        "occupied_area": occupied_area * weights.occupied_area,
        "motif_violation": motif_score * weights.motif_violation,
    }
    metrics = SchematicLayoutMetrics(
        part_count=len(parts),
        block_count=len(intent.blocks),
        wire_count=len(snapshot.schematic.wires),
        part_overlap_count=part_overlap_count,
        wire_overlap_count=wire_overlap_count,
        wire_crossing_count=wire_crossing_count,
        diagonal_segment_count=diagonal_segment_count,
        bend_count=bend_count,
        total_wire_length_mm=total_wire_length,
        occupied_width_mm=occupied_width,
        occupied_height_mm=occupied_height,
        occupied_area_mm2=occupied_area,
        content_area_mm2=content_area,
        density_ratio=density,
        mean_block_span_mm=mean_block_span,
        max_block_span_mm=max_block_span,
        motif_violation_count=motif_violation_count,
        score_terms=score_terms,
        score=sum(score_terms.values()),
    )
    warnings = list(intent.warnings)
    if placements and snapshot.schematic.wires:
        warnings.append(
            "Wire geometry was measured at its current coordinates while placement "
            "overrides were supplied."
        )
    return SchematicLayoutAnalysis(
        intent=intent,
        metrics=metrics,
        motif_results=motif_results,
        assumptions=[
            "Lower score is better only within the disclosed deterministic score terms.",
            "Part geometry uses the currently normalized schematic bounding boxes.",
        ],
        warnings=warnings,
        limitations=[
            "Current schematic part bounds are conservative position proxies, not "
            "authoritative symbol extents.",
            "Exact pin graphics/coordinates are not normalized, so pin-facing quality "
            "is not yet scored.",
            "Same-net wire intersections are not counted as crossings because junction "
            "intent is not yet normalized.",
            "Reference motifs are structured constraints; automatic datasheet ingestion "
            "is not implemented.",
        ],
    )


def _snap(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _local_block_layout(
    block: SchematicFunctionalBlock,
    config: SchematicPlacementConfig,
) -> tuple[dict[str, Point], float, float]:
    placements: dict[str, Point] = {}
    anchors = list(block.anchor_part_ids)
    anchor_set = set(anchors)
    supports = [item for item in block.member_part_ids if item not in anchor_set]
    for index, part_id in enumerate(anchors):
        placements[part_id] = Point(0.0, index * config.anchor_gap_y_mm)
    if anchors:
        anchor_height = max(config.anchor_gap_y_mm, len(anchors) * config.anchor_gap_y_mm)
        support_origin_x = config.member_gap_x_mm
        for index, part_id in enumerate(supports):
            row = index % 4
            column = index // 4
            placements[part_id] = Point(
                support_origin_x + column * config.member_gap_x_mm,
                row * config.member_gap_y_mm,
            )
        width = config.member_gap_x_mm * (1 + max(1, math.ceil(len(supports) / 4)))
        height = max(
            anchor_height,
            config.member_gap_y_mm * max(1, min(4, len(supports))),
        )
    else:
        for index, part_id in enumerate(block.member_part_ids):
            row = index % 4
            column = index // 4
            placements[part_id] = Point(
                column * config.member_gap_x_mm,
                row * config.member_gap_y_mm,
            )
        width = config.member_gap_x_mm * max(1, math.ceil(len(block.member_part_ids) / 4))
        height = config.member_gap_y_mm * max(1, min(4, len(block.member_part_ids)))
    return placements, max(width, config.member_gap_x_mm), max(height, config.member_gap_y_mm)


def plan_schematic_placement(
    snapshot: DocumentSnapshot,
    *,
    intent: SchematicDesignIntent | None = None,
    motifs: list[BoundReferenceMotif] | None = None,
    config: SchematicPlacementConfig | None = None,
) -> SchematicPlacementPlan:
    """Create a deterministic first-pass placement plan for an unwired schematic.

    This is deliberately a hierarchical block placer, not the final joint
    placement/wiring optimizer. Existing wires are refused by default because
    moving their endpoint symbols without rerouting would degrade the drawing.
    """
    _require_schematic(snapshot)
    assert snapshot.schematic is not None
    config = config or SchematicPlacementConfig()
    if len(snapshot.schematic.parts) > config.max_parts:
        raise CapabilityUnavailableError(
            f"Schematic placement is limited to {config.max_parts} parts per plan"
        )
    if snapshot.schematic.wires and not config.allow_existing_wires:
        raise CapabilityUnavailableError(
            "Schematic placement refuses existing wires until joint placement/rerouting is enabled"
        )
    intent = intent or infer_schematic_design_intent(snapshot, motifs=motifs)
    before = analyze_schematic_layout(
        snapshot,
        intent=intent,
        motifs=motifs,
        weights=config.weights,
    )
    parts_by_id = {part.stable_id: part for part in snapshot.schematic.parts}
    role_rank: dict[BlockRole, int] = {
        "connector": 0,
        "power": 1,
        "functional": 2,
        "generic": 3,
    }
    blocks = sorted(intent.blocks, key=lambda block: (role_rank[block.role], block.block_id))

    targets: dict[str, Point] = {}
    unresolved: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor_x = config.origin_x_mm
    cursor_y = config.origin_y_mm
    row_height = 0.0
    for block in blocks:
        local, width, height = _local_block_layout(block, config)
        if (
            cursor_x > config.origin_x_mm
            and cursor_x + width - config.origin_x_mm > config.target_row_width_mm
        ):
            cursor_x = config.origin_x_mm
            cursor_y += row_height + config.block_gap_y_mm
            row_height = 0.0
        block_origin = Point(cursor_x, cursor_y)
        locked_members = [
            part_id
            for part_id in block.member_part_ids
            if (part := parts_by_id.get(part_id)) is not None and part.locked
        ]
        if locked_members:
            warnings.append(
                f"Block {block.block_id} contains {len(locked_members)} locked part(s); "
                "they are preserved."
            )
        for part_id, offset in local.items():
            part = parts_by_id.get(part_id)
            if part is None:
                unresolved.append({"part_id": part_id, "reason": "part_missing"})
                continue
            if part.locked:
                current = _position_for(part, None)
                if current is not None:
                    targets[part_id] = current
                else:
                    unresolved.append({"part_id": part_id, "reason": "locked_position_missing"})
                continue
            targets[part_id] = Point(
                _snap(block_origin.x + offset.x, config.grid_mm),
                _snap(block_origin.y + offset.y, config.grid_mm),
            )
        cursor_x += width + config.block_gap_x_mm
        row_height = max(row_height, height)

    operations: list[SemanticOperation] = []
    changed: list[str] = []
    for part_id in sorted(targets):
        part = parts_by_id[part_id]
        current = _position_for(part, None)
        target = targets[part_id]
        if current is None:
            unresolved.append({"part_id": part_id, "reason": "position_missing"})
            continue
        if _same_point(current, target):
            continue
        operations.append(
            MoveComponentsOperation(
                selector=QuerySelector(ids=[part_id]),
                absolute_x=target.x,
                absolute_y=target.y,
            )
        )
        changed.append(part_id)

    after = analyze_schematic_layout(
        snapshot,
        intent=intent,
        placements=targets,
        motifs=motifs,
        weights=config.weights,
    )
    return SchematicPlacementPlan(
        operations=operations,
        placements=targets,
        before=before,
        after=after,
        changed_part_ids=changed,
        unresolved=unresolved,
        assumptions=[
            "Blocks are packed deterministically left-to-right and wrapped by a target row width.",
            "Anchor parts are placed first; support parts are packed near the anchor block.",
            "Existing part rotation is preserved because exact schematic pin geometry "
            "is not normalized.",
        ],
        warnings=warnings,
        limitations=[
            "This first-pass placer does not yet reroute existing wires.",
            "Datasheet motifs affect scoring only; motif-driven candidate generation "
            "is a later phase.",
            "Locked parts are preserved but are not yet used as hard packing obstacles "
            "for other blocks.",
            "The planner does not yet generate multiple global placement candidates.",
        ],
    )
