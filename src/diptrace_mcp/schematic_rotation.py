from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Literal, TypeAlias

from pydantic import Field

from .adapters import build_snapshot
from .domain import StrictModel
from .geometry import Point, distance
from .schematic_pin_geometry import (
    ResolvedSchematicPinGeometry,
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .xml_document import DipTraceDocument

CardinalAngle: TypeAlias = Literal[0, 90, 180, 270]


def _default_cardinal_angles() -> list[CardinalAngle]:
    return [0, 90, 180, 270]


class SchematicRotationConfig(StrictModel):
    enabled_angles_deg: list[CardinalAngle] = Field(
        default_factory=_default_cardinal_angles
    )
    minimum_pin_confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    pin_facing_penalty_mm: float = Field(default=10.0, ge=0.0)


class SchematicRotationCandidate(StrictModel):
    part_id: str
    refdes: str | None = None
    source_angle_deg: float
    target_angle_deg: CardinalAngle
    pin_geometry_confidence: float = Field(ge=0.0, le=1.0)
    pin_facing_score: float = Field(ge=0.0, le=1.0)
    estimated_interconnect_length_mm: float = Field(ge=0.0)
    score_terms: dict[str, float] = Field(default_factory=dict)
    total_score: float = Field(ge=0.0)


class SchematicRotationCandidateSet(StrictModel):
    schema_version: Literal["diptrace-schematic-rotation-candidates-v1"] = (
        "diptrace-schematic-rotation-candidates-v1"
    )
    candidates: list[SchematicRotationCandidate] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    enabled_by_default: Literal[False] = False
    required_manual_gate: Literal["M2"] = "M2"
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _rotate(point: Point, center: Point, delta_deg: float) -> Point:
    radians = math.radians(delta_deg)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    dx = point.x - center.x
    dy = point.y - center.y
    return Point(
        center.x + dx * cos_value - dy * sin_value,
        center.y + dx * sin_value + dy * cos_value,
    )


def _facing_score(origin: Point, orientation_deg: float, target: Point) -> float:
    dx = target.x - origin.x
    dy = target.y - origin.y
    if math.isclose(dx, 0.0, abs_tol=1e-12) and math.isclose(
        dy, 0.0, abs_tol=1e-12
    ):
        return 1.0
    desired = math.degrees(math.atan2(dy, dx))
    delta = math.radians((orientation_deg - desired) % 360.0)
    return max(0.0, min(1.0, (1.0 + math.cos(delta)) / 2.0))


def _resolved_by_part(
    resolution: SchematicPinGeometryResolution,
) -> dict[str, list[ResolvedSchematicPinGeometry]]:
    result: dict[str, list[ResolvedSchematicPinGeometry]] = defaultdict(list)
    for item in resolution.pins:
        result[item.part_id].append(item)
    return result


def generate_schematic_rotation_candidates(
    document: DipTraceDocument,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicRotationConfig | None = None,
) -> SchematicRotationCandidateSet:
    """Score cardinal rotations without enabling or applying them.

    Candidates are emitted only for unlocked parts whose complete resolved pin
    geometry meets the configured confidence threshold. Facing and route
    estimates use only literal connected peer geometry; ambiguous symbols retain
    their source angle by producing no automatic candidate.
    """

    config = config or SchematicRotationConfig()
    snapshot = build_snapshot(document)
    if snapshot.schematic is None:
        return SchematicRotationCandidateSet(
            skipped=[{"reason": "document_has_no_schematic"}]
        )
    resolution = pin_geometry or resolve_document_schematic_pin_geometry(document)
    by_part = _resolved_by_part(resolution)
    schematic_pin_ids_by_part: dict[str, set[str]] = defaultdict(set)
    for pin in snapshot.schematic.pins:
        if pin.parent_id is not None:
            schematic_pin_ids_by_part[pin.parent_id].add(pin.stable_id)
    pins_by_net: dict[str, list[ResolvedSchematicPinGeometry]] = defaultdict(list)
    pin_record_by_id = {item.stable_id: item for item in snapshot.schematic.pins}
    for resolved in resolution.pins:
        record = pin_record_by_id.get(resolved.pin_id)
        if record is not None and record.net_id is not None:
            pins_by_net[record.net_id].append(resolved)

    candidates: list[SchematicRotationCandidate] = []
    skipped: list[dict[str, Any]] = []
    for part in sorted(snapshot.schematic.parts, key=lambda item: item.stable_id):
        if part.locked:
            skipped.append({"part_id": part.stable_id, "reason": "locked_part"})
            continue
        if part.position is None:
            skipped.append({"part_id": part.stable_id, "reason": "missing_part_position"})
            continue
        part_pins = by_part.get(part.stable_id, [])
        expected_pin_ids = schematic_pin_ids_by_part.get(part.stable_id, set())
        resolved_pin_ids = {item.pin_id for item in part_pins}
        if not expected_pin_ids or resolved_pin_ids != expected_pin_ids:
            skipped.append(
                {"part_id": part.stable_id, "reason": "incomplete_pin_geometry"}
            )
            continue
        if any(
            item.absolute_position is None
            or item.absolute_orientation_deg is None
            or item.confidence < config.minimum_pin_confidence
            for item in part_pins
        ):
            skipped.append(
                {
                    "part_id": part.stable_id,
                    "reason": "insufficient_pin_geometry_confidence",
                }
            )
            continue
        peer_map: dict[str, list[ResolvedSchematicPinGeometry]] = {}
        for item in part_pins:
            record = pin_record_by_id.get(item.pin_id)
            if record is None or record.net_id is None:
                continue
            peer_candidates = [
                peer
                for peer in pins_by_net[record.net_id]
                if peer.part_id != part.stable_id and peer.absolute_position is not None
            ]
            if peer_candidates:
                peer_map[item.pin_id] = peer_candidates
        if not peer_map:
            skipped.append(
                {"part_id": part.stable_id, "reason": "no_resolved_connected_peers"}
            )
            continue

        center = Point(**part.position)
        source_angle = float(part.rotation_deg)
        confidence = min(item.confidence for item in part_pins)
        for target_angle in sorted(set(config.enabled_angles_deg)):
            delta = float(target_angle) - source_angle
            total_length = 0.0
            facing_values: list[float] = []
            for item in part_pins:
                pin_peers = peer_map.get(item.pin_id)
                if (
                    not pin_peers
                    or item.absolute_position is None
                    or item.absolute_orientation_deg is None
                ):
                    continue
                pin_point = _rotate(Point(**item.absolute_position), center, delta)
                peer = min(
                    pin_peers,
                    key=lambda value: distance(
                        pin_point,
                        Point(**value.absolute_position),  # type: ignore[arg-type]
                    ),
                )
                peer_point = Point(**peer.absolute_position)  # type: ignore[arg-type]
                total_length += distance(pin_point, peer_point)
                facing_values.append(
                    _facing_score(
                        pin_point,
                        (item.absolute_orientation_deg + delta) % 360.0,
                        peer_point,
                    )
                )
            if not facing_values:
                continue
            facing = sum(facing_values) / len(facing_values)
            facing_penalty = (1.0 - facing) * config.pin_facing_penalty_mm
            candidates.append(
                SchematicRotationCandidate(
                    part_id=part.stable_id,
                    refdes=part.refdes,
                    source_angle_deg=source_angle,
                    target_angle_deg=target_angle,
                    pin_geometry_confidence=confidence,
                    pin_facing_score=facing,
                    estimated_interconnect_length_mm=total_length,
                    score_terms={
                        "estimated_interconnect_length_mm": total_length,
                        "pin_facing_penalty_mm": facing_penalty,
                    },
                    total_score=total_length + facing_penalty,
                )
            )

    candidates.sort(
        key=lambda item: (item.part_id, item.total_score, item.target_angle_deg)
    )
    return SchematicRotationCandidateSet(
        candidates=candidates,
        skipped=skipped,
        assumptions=[
            "Only resolved literal peer-pin geometry contributes to rotation scoring.",
            (
                "Cardinal DipTrace rotation convention is treated as package-level "
                "evidence only until M2."
            ),
        ],
        limitations=[
            "Candidates are not enabled or applied automatically.",
            (
                "Each symbol family still requires focused native M2 acceptance "
                "before a rotation claim."
            ),
        ],
    )
