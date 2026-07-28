from __future__ import annotations

import math
import sys
from collections import deque
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
# A computational bound, not an electrical or manufacturing rule. Above this
# bound the estimator reports itself unavailable instead of returning a partial
# answer or risking unbounded work on hostile geometry.
_MAX_COUPLING_PARTITION_POINTS = 10_000
_FLOAT_DIRECTION_TOLERANCE = 64.0 * sys.float_info.epsilon


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


@dataclass(frozen=True, slots=True)
class _LinearGeometry:
    segments: list[_TraceSegment]
    active_layers: set[str]
    arc_layers: set[str]
    unavailable_reasons: list[str]


@dataclass(frozen=True, slots=True)
class _CouplingResult:
    coupled_length_mm: float | None
    gaps: list[tuple[float, float, str]]
    unavailable_reason: str | None = None


def _resolve_by_identity(
    records: list[ObjectRecord], reference: str, *, kind: str
) -> ObjectRecord:
    exact = [
        record
        for record in records
        if record.stable_id == reference or record.xml_id == reference
    ]
    matches = exact
    if not exact:
        folded = reference.casefold()
        matches = [
            record for record in records if (record.name or "").casefold() == folded
        ]
    if len(matches) != 1:
        raise ObjectNotFoundError(
            f"Unique {kind} was not found: {reference}",
            details={"reference": reference, "matched_count": len(matches)},
        )
    return matches[0]


def resolve_net(snapshot: DocumentSnapshot, reference: str) -> ObjectRecord:
    if snapshot.board is None:
        raise DocumentError("Net-length analysis requires a PCB document")
    return _resolve_by_identity(snapshot.board.nets, reference, kind="PCB net")


def resolve_differential_pair(
    snapshot: DocumentSnapshot, reference: str
) -> DifferentialPairModel:
    if snapshot.board is None:
        raise DocumentError("Differential-pair analysis requires a PCB document")
    pairs = snapshot.board.differential_pairs
    exact = [
        pair
        for pair in pairs
        if pair.stable_id == reference or pair.xml_id == reference
    ]
    matches = exact
    if not exact:
        folded = reference.casefold()
        matches = [pair for pair in pairs if pair.name.casefold() == folded]
    if len(matches) != 1:
        raise ObjectNotFoundError(
            f"Unique differential pair was not found: {reference}",
            details={"reference": reference, "matched_count": len(matches)},
        )
    return matches[0]


def record_belongs_to_net(record: ObjectRecord, net: ObjectRecord) -> bool:
    """Match normalized relationships before XML ids, and names only as fallback.

    Duplicate human-readable net names are legal input. A stable relationship or
    XML id therefore wins and a conflicting name must never pull an object into a
    different net's measurement.
    """

    relationships = record.relationships.get("net", [])
    if relationships:
        return net.stable_id in relationships
    if record.net_id is not None:
        return net.xml_id is not None and record.net_id == net.xml_id
    return (
        record.net_name is not None
        and net.name is not None
        and record.net_name.casefold() == net.name.casefold()
    )


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


def _stackup_copper_centers(
    snapshot: DocumentSnapshot,
) -> tuple[dict[str, float] | None, str | None]:
    assert snapshot.board is not None
    stackup = snapshot.board.stackup
    if stackup.source == "missing" or not stackup.layers:
        return None, "physical_stackup_missing"
    indices = [layer.index for layer in stackup.layers]
    if indices != list(range(len(indices))):
        return None, "stackup_items_missing"
    if any(
        layer.material.material_type == "unknown"
        or layer.material.thickness_mm is None
        for layer in stackup.layers
    ):
        return None, "stackup_material_or_thickness_missing"

    conductive_indices = [
        index
        for index, layer in enumerate(stackup.layers)
        if layer.material.material_type in {"conductor", "plane"}
    ]
    if len(conductive_indices) < 2:
        return None, "multiple_copper_layers_unavailable"
    for left, right in zip(conductive_indices, conductive_indices[1:], strict=False):
        between = stackup.layers[left + 1 : right]
        if not between or not any(
            layer.material.material_type == "dielectric" for layer in between
        ):
            return None, "dielectric_separation_missing"

    centers: dict[str, float] = {}
    cursor = 0.0
    for layer in stackup.layers:
        thickness = layer.material.thickness_mm
        assert thickness is not None
        if layer.material.material_type in {"conductor", "plane"}:
            if layer.layer_id is None:
                return None, "copper_layer_id_missing"
            if layer.layer_id in centers:
                return None, "duplicate_copper_layer_id"
            centers[layer.layer_id] = cursor + thickness / 2.0
        cursor += thickness
    return centers, None


def _trace_segment_layers(trace: ObjectRecord) -> tuple[list[str], bool]:
    points = trace.attributes.get("points", [])
    raw_layers = trace.attributes.get("segment_layers", [])
    layers: list[str] = []
    incomplete = False
    for index in range(max(0, len(points) - 1)):
        value = raw_layers[index] if index < len(raw_layers) else trace.layer
        if value in {None, ""}:
            incomplete = True
            layers.append("")
        else:
            layers.append(str(value))
    return layers, incomplete


def _routed_via_barrel_length(
    snapshot: DocumentSnapshot, traces: list[ObjectRecord]
) -> tuple[float | None, int, list[str]]:
    assert snapshot.board is not None
    observed: list[tuple[ObjectRecord, Point, str, str]] = []
    incomplete_layers = False
    for trace in traces:
        layers, incomplete = _trace_segment_layers(trace)
        incomplete_layers = incomplete_layers or incomplete
        points = [
            Point(**point) for point in trace.attributes.get("points", [])
        ]
        observed.extend(
            (trace, points[index + 1], left, right)
            for index, (left, right) in enumerate(
                zip(layers, layers[1:], strict=False)
            )
            if left and right and left != right
        )
    observed_transitions = len(observed)
    if observed_transitions == 0:
        reasons = ["trace_layer_sequence_incomplete"] if incomplete_layers else []
        return (None if reasons else 0.0), 0, reasons
    if incomplete_layers:
        return None, observed_transitions, ["trace_layer_sequence_incomplete"]

    centers, stack_reason = _stackup_copper_centers(snapshot)
    if centers is None:
        return None, observed_transitions, [stack_reason or "physical_stackup_unavailable"]
    barrel = 0.0
    used_vias: set[str] = set()
    for trace, location, first_layer, second_layer in observed:
        candidates = [
            via
            for via in snapshot.board.vias
            if via.stable_id not in used_vias
            and via.parent_id == trace.stable_id
            and via.attributes.get("representation") == "trace_layer_transition"
            and via.position is not None
            and Point(**via.position) == location
        ]
        if len(candidates) != 1:
            return None, observed_transitions, ["normalized_layer_transition_missing"]
        via = candidates[0]
        used_vias.add(via.stable_id)
        if via.attributes.get("span_source") != "explicit":
            return None, observed_transitions, ["explicit_via_span_missing"]
        span = [str(value) for value in via.attributes.get("span_layer_ids", [])]
        if (
            len(span) < 2
            or first_layer not in span
            or second_layer not in span
            or first_layer not in centers
            or second_layer not in centers
        ):
            return None, observed_transitions, ["via_span_not_in_physical_stackup"]
        barrel += abs(centers[second_layer] - centers[first_layer])
    return barrel, observed_transitions, []


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
        if record_belongs_to_net(via, net)
    }
    via_ids = sorted(transition_via_ids | physical_via_ids)
    barrel_length, observed_transitions, unavailable_reasons = (
        _routed_via_barrel_length(snapshot, traces)
    )
    routed_length = (
        geometric_length + barrel_length if barrel_length is not None else None
    )
    electrical_length: float | None = None
    delay_ps: float | None = None
    warnings: list[str] = []
    if effective_dielectric_constant is not None:
        if (
            not math.isfinite(effective_dielectric_constant)
            or effective_dielectric_constant <= 1
        ):
            raise DocumentError("effective_dielectric_constant must be greater than 1")
        if routed_length is None:
            warnings.append(
                "Electrical length and delay are unavailable because routed 3D length "
                "could not be established."
            )
        else:
            velocity_factor = math.sqrt(effective_dielectric_constant)
            electrical_length = routed_length * velocity_factor
            delay_ps = electrical_length / _C_MM_PER_PS
            warnings.append(
                "Electrical length and delay use one caller-supplied effective dielectric "
                "constant for every routed layer and via."
            )
    if arc_count:
        warnings.append(
            "DipTrace Arc=Y midpoint triples are measured as circular arcs; malformed "
            "collinear triples fall back to two straight segments."
        )
    if unavailable_reasons:
        warnings.append(
            "Routed 3D length is unavailable: " + ", ".join(unavailable_reasons) + "."
        )
    return NetLengthMeasurement(
        net_id=net.stable_id,
        net_xml_id=net.xml_id,
        net_name=net.name,
        geometric_length_mm=geometric_length,
        routed_length_3d_mm=routed_length,
        via_barrel_length_mm=barrel_length,
        routed_length_status="available" if routed_length is not None else "unavailable",
        routed_length_unavailable_reasons=unavailable_reasons,
        per_layer_length_mm=per_layer,
        trace_count=len(traces),
        via_count=len(via_ids),
        via_ids=via_ids,
        layer_transition_count=observed_transitions,
        arc_count=arc_count,
        electrical_length_mm=electrical_length,
        delay_ps=delay_ps,
        warnings=warnings,
    )


def _linear_segments(snapshot: DocumentSnapshot, net_id: str) -> _LinearGeometry:
    assert snapshot.board is not None
    layer_names = {
        str(layer.get("id", "")): str(layer.get("name", ""))
        for layer in snapshot.board.layers
    }
    result: list[_TraceSegment] = []
    active_layers: set[str] = set()
    arc_layers: set[str] = set()
    unavailable_reasons: list[str] = []
    for trace in snapshot.board.traces:
        if trace.parent_id != net_id:
            continue
        points = [Point(**point) for point in trace.attributes.get("points", [])]
        layers = trace.attributes.get("segment_layers", [])
        widths = trace.attributes.get("segment_widths_mm", [])
        arcs = trace.attributes.get("point_arc_middle", [False] * len(points))
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            layer_value = layers[index] if index < len(layers) else trace.layer
            layer = layer_names.get(
                str(layer_value or ""), str(layer_value or "")
            )
            if layer:
                active_layers.add(layer)
            if bool(arcs[index]) or (
                index + 1 < len(arcs) and bool(arcs[index + 1])
            ):
                if layer:
                    arc_layers.add(layer)
                continue
            width_value = widths[index] if index < len(widths) else None
            width = float(width_value) if width_value is not None else None
            if width is None or not math.isfinite(width) or width <= 0:
                unavailable_reasons.append("trace_width_unavailable")
            if distance(start, end) == 0:
                continue
            result.append(
                _TraceSegment(
                    start=start,
                    end=end,
                    layer=layer,
                    width_mm=width,
                )
            )
    if not active_layers:
        unavailable_reasons.append("routed_geometry_unavailable")
    return _LinearGeometry(
        segments=result,
        active_layers=active_layers,
        arc_layers=arc_layers,
        unavailable_reasons=sorted(set(unavailable_reasons)),
    )


def _parallel(left: _TraceSegment, right: _TraceSegment) -> bool:
    left_dx = left.end.x - left.start.x
    left_dy = left.end.y - left.start.y
    right_dx = right.end.x - right.start.x
    right_dy = right.end.y - right.start.y
    scale = left.length * right.length
    if scale == 0:
        return False
    cross = abs(left_dx * right_dy - left_dy * right_dx)
    return cross <= _FLOAT_DIRECTION_TOLERANCE * scale


def _axis(segment: _TraceSegment) -> tuple[float, float]:
    dx = (segment.end.x - segment.start.x) / segment.length
    dy = (segment.end.y - segment.start.y) / segment.length
    if dx < 0 or (dx == 0 and dy < 0):
        return -dx, -dy
    return dx, dy


def _interval(segment: _TraceSegment, axis: tuple[float, float]) -> tuple[float, float]:
    ux, uy = axis
    values = (
        segment.start.x * ux + segment.start.y * uy,
        segment.end.x * ux + segment.end.y * uy,
    )
    return min(values), max(values)


def _maximum_matching(
    left_nodes: list[int],
    edges: dict[int, list[int]],
) -> dict[int, int]:
    """Return a maximum bipartite matching without recursive augmentation."""

    matched_right: dict[int, int] = {}
    for start in left_nodes:
        queue: deque[int] = deque([start])
        previous_left: dict[int, int | None] = {start: None}
        previous_right: dict[int, int] = {}
        terminal: int | None = None
        while queue and terminal is None:
            left = queue.popleft()
            for right in edges.get(left, []):
                if right in previous_right:
                    continue
                previous_right[right] = left
                owner = matched_right.get(right)
                if owner is None:
                    terminal = right
                    break
                if owner not in previous_left:
                    previous_left[owner] = right
                    queue.append(owner)
        if terminal is None:
            continue
        right = terminal
        while True:
            left = previous_right[right]
            matched_right[right] = left
            prior_right = previous_left[left]
            if prior_right is None:
                break
            right = prior_right
    return {left: right for right, left in matched_right.items()}


def _coupling_metrics(
    positive: _LinearGeometry, negative: _LinearGeometry
) -> _CouplingResult:
    reasons = sorted(
        set(positive.unavailable_reasons) | set(negative.unavailable_reasons)
    )
    if reasons:
        return _CouplingResult(None, [], ",".join(reasons))
    if not positive.segments or not negative.segments:
        return _CouplingResult(None, [], "linear_routed_geometry_unavailable")

    coupled_length = 0.0
    gaps: list[tuple[float, float, str]] = []
    work_items = 0
    unassigned = set(range(len(positive.segments)))
    found_projection = False
    while unassigned:
        seed_index = min(unassigned)
        seed = positive.segments[seed_index]
        group_positive = sorted(
            index
            for index in unassigned
            if positive.segments[index].layer == seed.layer
            and _parallel(seed, positive.segments[index])
        )
        unassigned.difference_update(group_positive)
        group_negative = [
            index
            for index, segment in enumerate(negative.segments)
            if segment.layer == seed.layer and _parallel(seed, segment)
        ]
        if not group_negative:
            continue
        axis = _axis(seed)
        intervals = {
            ("p", index): _interval(positive.segments[index], axis)
            for index in group_positive
        }
        intervals.update(
            {
                ("n", index): _interval(negative.segments[index], axis)
                for index in group_negative
            }
        )
        partition = sorted(
            {
                endpoint
                for interval in intervals.values()
                for endpoint in interval
            }
        )
        if len(partition) > _MAX_COUPLING_PARTITION_POINTS:
            return _CouplingResult(None, [], "coupling_partition_limit_exceeded")
        for start, end in zip(partition, partition[1:], strict=False):
            if end <= start:
                continue
            middle = (start + end) / 2.0
            active_positive = [
                index
                for index in group_positive
                if intervals[("p", index)][0] < middle < intervals[("p", index)][1]
            ]
            active_negative = [
                index
                for index in group_negative
                if intervals[("n", index)][0] < middle < intervals[("n", index)][1]
            ]
            if not active_positive or not active_negative:
                continue
            edge_gaps: dict[tuple[int, int], float] = {}
            edges: dict[int, list[int]] = {}
            for pos_index in active_positive:
                pos = positive.segments[pos_index]
                assert pos.width_mm is not None
                candidates: list[tuple[float, int]] = []
                for neg_index in active_negative:
                    neg = negative.segments[neg_index]
                    assert neg.width_mm is not None
                    center_distance = segment_distance(
                        pos.start, pos.end, neg.start, neg.end
                    )
                    gap = center_distance - (pos.width_mm + neg.width_mm) / 2.0
                    edge_gaps[(pos_index, neg_index)] = gap
                    candidates.append((gap, neg_index))
                edges[pos_index] = [
                    index for _gap, index in sorted(candidates)
                ]
            work_items += sum(len(items) for items in edges.values())
            if work_items > _MAX_COUPLING_PARTITION_POINTS:
                return _CouplingResult(
                    None, [], "coupling_partition_limit_exceeded"
                )
            matching = _maximum_matching(active_positive, edges)
            if not matching:
                continue
            found_projection = True
            atom_length = end - start
            coupled_length += atom_length * len(matching)
            gaps.extend(
                (
                    edge_gaps[(pos_index, neg_index)],
                    atom_length,
                    seed.layer,
                )
                for pos_index, neg_index in matching.items()
            )
    if not found_projection:
        return _CouplingResult(None, [], "parallel_projection_unavailable")
    return _CouplingResult(coupled_length, gaps)


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


def _skip(check_id: str, reason: str) -> dict[str, str]:
    return {"check_id": check_id, "reason": reason}


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
    positive_geometry = _linear_segments(snapshot, positive.net_id)
    negative_geometry = _linear_segments(snapshot, negative.net_id)
    coupling = _coupling_metrics(positive_geometry, negative_geometry)
    shorter_length = min(positive.geometric_length_mm, negative.geometric_length_mm)
    coupled_length = (
        min(coupling.coupled_length_mm, shorter_length)
        if coupling.coupled_length_mm is not None
        else None
    )
    uncoupled_length = (
        max(0.0, shorter_length - coupled_length)
        if coupled_length is not None
        else None
    )
    checks: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
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
        if uncoupled_length is None:
            skipped.append(
                _skip(
                    "diff_pair.max_uncoupled_length",
                    coupling.unavailable_reason or "coupling_estimate_unavailable",
                )
            )
        else:
            checks.append(
                _rule_check(
                    "diff_pair.max_uncoupled_length",
                    uncoupled_length,
                    pair.rules.max_uncoupled_length_mm,
                    uncoupled_length <= pair.rules.max_uncoupled_length_mm,
                    "mm",
                )
            )
    if coupling.unavailable_reason is not None:
        skipped.append(
            _skip("diff_pair.coupling_estimate", coupling.unavailable_reason)
        )

    weighted_gaps = coupling.gaps
    active_layers = positive_geometry.active_layers | negative_geometry.active_layers
    arc_layers = positive_geometry.arc_layers | negative_geometry.arc_layers
    for rule in pair.rules.layer_rules:
        if rule.layer_name not in active_layers:
            continue
        if rule.gap_mm is not None:
            layer_values = [
                gap
                for gap, _weight, item_layer in weighted_gaps
                if item_layer == rule.layer_name
            ]
            if not layer_values:
                reason = (
                    "arc_geometry_not_supported"
                    if rule.layer_name in arc_layers
                    else "exact_parallel_gap_projection_unavailable"
                )
                skipped.append(_skip(f"diff_pair.gap.{rule.layer_name}", reason))
            else:
                maximum_error = max(
                    abs(value - rule.gap_mm) for value in layer_values
                )
                numeric_tolerance = (
                    sys.float_info.epsilon
                    * 64.0
                    * max(1.0, abs(rule.gap_mm))
                )
                checks.append(
                    _rule_check(
                        f"diff_pair.gap.{rule.layer_name}",
                        maximum_error,
                        0.0,
                        maximum_error <= numeric_tolerance,
                        "mm error",
                    )
                )
        for field_name, value in (
            ("width", rule.width_mm),
            ("min_width", rule.min_width_mm),
            ("max_width", rule.max_width_mm),
            ("clearance_to_others", rule.clearance_to_others_mm),
            ("neck_width", rule.neck_width_mm),
            ("neck_gap", rule.neck_gap_mm),
            ("max_neck_length", rule.max_neck_length_mm),
        ):
            if value is not None:
                skipped.append(
                    _skip(
                        f"diff_pair.{field_name}.{rule.layer_name}",
                        "not_implemented",
                    )
                )
    if pair.rules.target_impedance_ohm is not None:
        skipped.append(_skip("diff_pair.target_impedance", "not_implemented"))
    if pair.rules.phase_tolerance is not None:
        skipped.append(_skip("diff_pair.phase_tolerance", "not_implemented"))
    if pair.rules.phase_error_length_mm is not None:
        skipped.append(_skip("diff_pair.phase_error_length", "not_implemented"))
    if pair.rules.check_length:
        if pair.rules.fixed_length_mm is None and pair.rules.length_delta_mm is None:
            skipped.append(
                _skip("diff_pair.class_length", "enabled_rule_parameters_missing")
            )
        else:
            if pair.rules.fixed_length_mm is not None:
                skipped.append(_skip("diff_pair.fixed_length", "not_implemented"))
            if pair.rules.length_delta_mm is not None:
                skipped.append(_skip("diff_pair.length_delta", "not_implemented"))

    total_weight = sum(weight for _gap, weight, _layer in weighted_gaps)
    minimum_gap = min((gap for gap, _weight, _layer in weighted_gaps), default=None)
    maximum_gap = max((gap for gap, _weight, _layer in weighted_gaps), default=None)
    average_gap = (
        sum(gap * weight for gap, weight, _layer in weighted_gaps) / total_weight
        if total_weight > 0
        else None
    )
    all_layers = set(positive.per_layer_length_mm) | set(
        negative.per_layer_length_mm
    )
    per_layer_delta = {
        layer: positive.per_layer_length_mm.get(layer, 0.0)
        - negative.per_layer_length_mm.get(layer, 0.0)
        for layer in sorted(all_layers)
    }
    warnings = list(pair.warnings)
    if arc_layers:
        warnings.append(
            "Arc length is included in planar skew, but arc sections are excluded from "
            "coupled-length and gap estimation."
        )
    if coupling.unavailable_reason is not None:
        warnings.append(
            "Coupled-length and exact-gap estimates are unavailable: "
            f"{coupling.unavailable_reason}."
        )
    if (
        positive.routed_length_status == "unavailable"
        or negative.routed_length_status == "unavailable"
    ):
        warnings.append(
            "Time-domain skew is unavailable because at least one routed 3D length "
            "is unavailable."
        )
    via_balance = positive.via_count - negative.via_count
    return DifferentialPairAnalysis(
        pair_id=pair.stable_id,
        pair_name=pair.name,
        positive=positive,
        negative=negative,
        signed_skew_mm=signed_skew,
        absolute_skew_mm=absolute_skew,
        coupled_length_mm=coupled_length,
        estimated_uncoupled_length_mm=uncoupled_length,
        gap_mm={
            "min": minimum_gap,
            "max": maximum_gap,
            "weighted_average": average_gap,
        },
        via_balance=via_balance,
        per_layer_delta_mm=per_layer_delta,
        checks=checks,
        skipped_checks=skipped,
        fully_evaluated=not skipped,
        assumptions=[
            "Planar skew follows exported trace centerlines.",
            "Coupled length uses only numerically parallel same-layer linear projections.",
            "Gap is copper-edge distance derived from exported centerlines and widths.",
            "No unverified angular, spacing, or via-balance engineering threshold is applied.",
            "This is a geometry review, not an electromagnetic field solution.",
        ],
        warnings=warnings,
        confidence="low" if skipped else "medium",
    )
