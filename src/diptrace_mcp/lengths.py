from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot
from .domain import (
    DifferentialPairAnalysis,
    DifferentialPairModel,
    NetLengthMeasurement,
    ObjectRecord,
)
from .errors import DocumentError, ObjectNotFoundError
from .geometry import BBox, Point, distance, segment_distance, trace_path_length

_C_MM_PER_PS = 0.299792458


@dataclass(frozen=True, slots=True)
class _TraceSegment:
    start: Point
    end: Point
    layer: str
    width_mm: float | None

    @property
    def length(self) -> float:
        return distance(self.start, self.end)

    @property
    def bbox(self) -> BBox:
        return BBox.from_points((self.start, self.end))


def resolve_net(snapshot: DocumentSnapshot, reference: str) -> ObjectRecord:
    if snapshot.board is None:
        raise DocumentError("Net-length analysis requires a PCB document")
    folded = reference.casefold()
    matches = [
        net
        for net in snapshot.board.nets
        if net.stable_id == reference
        or net.xml_id == reference
        or (net.name or "").casefold() == folded
    ]
    if len(matches) != 1:
        raise ObjectNotFoundError(
            f"Unique PCB net was not found: {reference}",
            details={"reference": reference, "matched_count": len(matches)},
        )
    return matches[0]


def resolve_differential_pair(
    snapshot: DocumentSnapshot, reference: str
) -> DifferentialPairModel:
    if snapshot.board is None:
        raise DocumentError("Differential-pair analysis requires a PCB document")
    folded = reference.casefold()
    matches = [
        pair
        for pair in snapshot.board.differential_pairs
        if pair.stable_id == reference
        or pair.xml_id == reference
        or pair.name.casefold() == folded
    ]
    if len(matches) != 1:
        raise ObjectNotFoundError(
            f"Unique differential pair was not found: {reference}",
            details={"reference": reference, "matched_count": len(matches)},
        )
    return matches[0]


def _trace_chunks(trace: ObjectRecord) -> list[tuple[float, str, bool]]:
    points = [Point(**point) for point in trace.attributes.get("points", [])]
    arc_middle = [bool(value) for value in trace.attributes.get("point_arc_middle", [])]
    if len(arc_middle) != len(points):
        arc_middle = [False] * len(points)
    layers = [
        str(value) if value is not None else trace.layer or ""
        for value in trace.attributes.get("segment_layers", [])
    ]
    chunks: list[tuple[float, str, bool]] = []
    index = 0
    while index < len(points) - 1:
        if index + 2 < len(points) and arc_middle[index + 1]:
            arc_length = trace_path_length(
                points[index : index + 3], [False, True, False]
            )
            layer = layers[index] if index < len(layers) else trace.layer or ""
            chunks.append((arc_length, layer, True))
            index += 2
        else:
            layer = layers[index] if index < len(layers) else trace.layer or ""
            chunks.append((distance(points[index], points[index + 1]), layer, False))
            index += 1
    return chunks


def measure_net_length(
    snapshot: DocumentSnapshot,
    net_reference: str,
    *,
    effective_dielectric_constant: float | None = None,
) -> NetLengthMeasurement:
    net = resolve_net(snapshot, net_reference)
    assert snapshot.board is not None
    traces = [trace for trace in snapshot.board.traces if trace.parent_id == net.stable_id]
    per_layer: dict[str, float] = {}
    geometric_length = 0.0
    arc_count = 0
    for trace in traces:
        for chunk_length, layer, is_arc in _trace_chunks(trace):
            geometric_length += chunk_length
            per_layer[layer] = per_layer.get(layer, 0.0) + chunk_length
            arc_count += int(is_arc)
    transition_via_ids = {
        via_id
        for trace in traces
        for via_id in trace.relationships.get("vias", [])
    }
    physical_via_ids = {
        via.stable_id
        for via in snapshot.board.vias
        if via.net_id == net.xml_id or via.net_name == net.name
    }
    via_ids = sorted(transition_via_ids | physical_via_ids)
    electrical_length: float | None = None
    delay_ps: float | None = None
    warnings: list[str] = []
    if effective_dielectric_constant is not None:
        if not math.isfinite(effective_dielectric_constant) or effective_dielectric_constant <= 1:
            raise DocumentError("effective_dielectric_constant must be greater than 1")
        velocity_factor = math.sqrt(effective_dielectric_constant)
        electrical_length = geometric_length * velocity_factor
        delay_ps = electrical_length / _C_MM_PER_PS
        warnings.append(
            "Electrical length and delay use one caller-supplied effective dielectric "
            "constant for every routed layer."
        )
    if arc_count:
        warnings.append(
            "DipTrace Arc=Y midpoint triples are measured as circular arcs; malformed "
            "collinear triples fall back to two straight segments."
        )
    return NetLengthMeasurement(
        net_id=net.stable_id,
        net_xml_id=net.xml_id,
        net_name=net.name,
        geometric_length_mm=geometric_length,
        per_layer_length_mm=per_layer,
        trace_count=len(traces),
        via_count=len(via_ids),
        via_ids=via_ids,
        layer_transition_count=len(transition_via_ids),
        arc_count=arc_count,
        electrical_length_mm=electrical_length,
        delay_ps=delay_ps,
        warnings=warnings,
    )


def _linear_segments(snapshot: DocumentSnapshot, net_id: str) -> tuple[list[_TraceSegment], int]:
    assert snapshot.board is not None
    layer_names = {
        str(layer.get("id", "")): str(layer.get("name", ""))
        for layer in snapshot.board.layers
    }
    result: list[_TraceSegment] = []
    skipped_arcs = 0
    for trace in snapshot.board.traces:
        if trace.parent_id != net_id:
            continue
        points = [Point(**point) for point in trace.attributes.get("points", [])]
        layers = trace.attributes.get("segment_layers", [])
        widths = trace.attributes.get("segment_widths_mm", [])
        arcs = trace.attributes.get("point_arc_middle", [False] * len(points))
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            if bool(arcs[index]) or (index + 1 < len(arcs) and bool(arcs[index + 1])):
                skipped_arcs += 1
                continue
            width_value = widths[index] if index < len(widths) else None
            width = float(width_value) if width_value is not None else None
            layer_value = layers[index] if index < len(layers) else trace.layer
            result.append(
                _TraceSegment(
                    start=start,
                    end=end,
                    layer=layer_names.get(str(layer_value or ""), str(layer_value or "")),
                    width_mm=width,
                )
            )
    return result, skipped_arcs


def _parallel_angle_deg(left: _TraceSegment, right: _TraceSegment) -> float:
    left_dx = left.end.x - left.start.x
    left_dy = left.end.y - left.start.y
    right_dx = right.end.x - right.start.x
    right_dy = right.end.y - right.start.y
    denominator = left.length * right.length
    if denominator <= 1e-12:
        return 90.0
    cosine = abs((left_dx * right_dx + left_dy * right_dy) / denominator)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine))))


def _projected_overlap(left: _TraceSegment, right: _TraceSegment) -> float:
    if left.length <= 1e-12:
        return 0.0
    unit_x = (left.end.x - left.start.x) / left.length
    unit_y = (left.end.y - left.start.y) / left.length
    projections = [
        (point.x - left.start.x) * unit_x + (point.y - left.start.y) * unit_y
        for point in (right.start, right.end)
    ]
    return max(0.0, min(left.length, max(projections)) - max(0.0, min(projections)))


def _coupling_metrics(
    positive: list[_TraceSegment], negative: list[_TraceSegment]
) -> tuple[float, list[tuple[float, float, str]]]:
    coupled_length = 0.0
    gaps: list[tuple[float, float, str]] = []
    for pos_segment in positive:
        candidates: list[tuple[float, float, _TraceSegment]] = []
        for neg_segment in negative:
            if pos_segment.layer != neg_segment.layer:
                continue
            if _parallel_angle_deg(pos_segment, neg_segment) > 5.0:
                continue
            overlap = _projected_overlap(pos_segment, neg_segment)
            if overlap <= 1e-9:
                continue
            center_distance = segment_distance(
                pos_segment.start,
                pos_segment.end,
                neg_segment.start,
                neg_segment.end,
            )
            candidates.append((center_distance, -overlap, neg_segment))
        if not candidates:
            continue
        center_distance, negative_overlap, neg_segment = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        overlap = -negative_overlap
        edge_gap = center_distance - (
            (pos_segment.width_mm or 0.0) + (neg_segment.width_mm or 0.0)
        ) / 2.0
        coupled_length += overlap
        gaps.append((max(0.0, edge_gap), overlap, pos_segment.layer))
    return coupled_length, gaps


def _rule_check(
    check_id: str,
    measured: float,
    required: float,
    passed: bool,
    unit: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "measured": measured,
        "required": required,
        "delta": measured - required,
        "unit": unit,
    }


def analyze_differential_pair(
    snapshot: DocumentSnapshot, pair_reference: str
) -> DifferentialPairAnalysis:
    pair = resolve_differential_pair(snapshot, pair_reference)
    if pair.positive_net_id is None or pair.negative_net_id is None:
        raise DocumentError(
            f"Differential pair {pair.name} references missing nets",
            code="schema_parse_error",
            details={"pair_id": pair.stable_id, "warnings": pair.warnings},
        )
    positive = measure_net_length(snapshot, pair.positive_net_id)
    negative = measure_net_length(snapshot, pair.negative_net_id)
    signed_skew = positive.geometric_length_mm - negative.geometric_length_mm
    absolute_skew = abs(signed_skew)
    positive_segments, positive_arc_segments = _linear_segments(snapshot, positive.net_id)
    negative_segments, negative_arc_segments = _linear_segments(snapshot, negative.net_id)
    coupled_length, weighted_gaps = _coupling_metrics(positive_segments, negative_segments)
    shorter_length = min(positive.geometric_length_mm, negative.geometric_length_mm)
    uncoupled_length = max(0.0, shorter_length - coupled_length)
    checks: list[dict[str, Any]] = []
    if pair.rules.length_tolerance_mm is not None:
        checks.append(
            _rule_check(
                "diff_pair.length_tolerance",
                absolute_skew,
                pair.rules.length_tolerance_mm,
                absolute_skew <= pair.rules.length_tolerance_mm,
                "mm",
            )
        )
    if pair.rules.max_uncoupled_length_mm is not None:
        checks.append(
            _rule_check(
                "diff_pair.max_uncoupled_length",
                uncoupled_length,
                pair.rules.max_uncoupled_length_mm,
                uncoupled_length <= pair.rules.max_uncoupled_length_mm,
                "mm",
            )
        )
    via_balance = positive.via_count - negative.via_count
    checks.append(
        _rule_check(
            "diff_pair.via_balance", abs(via_balance), 0.0, via_balance == 0, "count"
        )
    )
    expected_gaps = {
        rule.layer_name: rule.gap_mm
        for rule in pair.rules.layer_rules
        if rule.gap_mm is not None
    }
    for layer, expected_gap in expected_gaps.items():
        layer_values = [gap for gap, _weight, item_layer in weighted_gaps if item_layer == layer]
        if not layer_values:
            continue
        max_error = max(abs(value - expected_gap) for value in layer_values)
        tolerance = max(0.025, expected_gap * 0.1)
        checks.append(
            _rule_check(
                f"diff_pair.gap.{layer}",
                max_error,
                tolerance,
                max_error <= tolerance,
                "mm error",
            )
        )
    total_weight = sum(weight for _gap, weight, _layer in weighted_gaps)
    minimum_gap = min((gap for gap, _weight, _layer in weighted_gaps), default=None)
    maximum_gap = max((gap for gap, _weight, _layer in weighted_gaps), default=None)
    average_gap = (
        sum(gap * weight for gap, weight, _layer in weighted_gaps) / total_weight
        if total_weight > 0
        else None
    )
    all_layers = set(positive.per_layer_length_mm) | set(negative.per_layer_length_mm)
    per_layer_delta = {
        layer: positive.per_layer_length_mm.get(layer, 0.0)
        - negative.per_layer_length_mm.get(layer, 0.0)
        for layer in sorted(all_layers)
    }
    warnings = list(pair.warnings)
    if positive_arc_segments or negative_arc_segments:
        warnings.append(
            "Arc length is included in total skew, but arc sections are excluded from "
            "coupled-length and gap estimation."
        )
    if not weighted_gaps:
        warnings.append("No parallel same-layer linear segments were found for gap estimation.")
    return DifferentialPairAnalysis(
        pair_id=pair.stable_id,
        pair_name=pair.name,
        positive=positive,
        negative=negative,
        signed_skew_mm=signed_skew,
        absolute_skew_mm=absolute_skew,
        coupled_length_mm=min(coupled_length, shorter_length),
        estimated_uncoupled_length_mm=uncoupled_length,
        gap_mm={"min": minimum_gap, "max": maximum_gap, "weighted_average": average_gap},
        via_balance=via_balance,
        per_layer_delta_mm=per_layer_delta,
        checks=checks,
        assumptions=[
            "Coupled length uses parallel (<=5 degree) same-layer linear projections.",
            "Gap is copper-edge distance derived from exported centerlines and widths.",
            "This is a geometry review, not an electromagnetic field solution.",
        ],
        warnings=warnings,
        confidence="medium" if weighted_gaps else "low",
    )
