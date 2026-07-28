from __future__ import annotations

import math
from typing import Any, Literal

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, ReturnPathAnalysis, ReturnPathIssue
from .errors import DocumentError
from .geometry import Point, distance, point_in_polygon
from .lengths import record_belongs_to_net, resolve_net


def _reference_layers(
    snapshot: DocumentSnapshot,
) -> tuple[dict[str, str], set[str]]:
    """Resolve an adjacent reference layer only when one side is unambiguous.

    Stack order and the normalized material type are the only available facts.
    A lexical layer id or an inferred preference is not physical evidence, so
    candidates on both sides are deliberately reported as unknown.
    """

    assert snapshot.board is not None
    result: dict[str, str] = {}
    ambiguous: set[str] = set()
    layers = snapshot.board.stackup.layers
    for index, layer in enumerate(layers):
        if layer.layer_id is None or layer.material.material_type not in {
            "conductor",
            "plane",
        }:
            continue
        candidates: list[str] = []
        for direction in (-1, 1):
            cursor = index + direction
            crossed_dielectric = False
            while 0 <= cursor < len(layers):
                candidate = layers[cursor]
                if candidate.material.material_type == "dielectric":
                    crossed_dielectric = True
                    cursor += direction
                    continue
                if candidate.material.material_type in {"conductor", "plane"}:
                    if candidate.layer_id is not None and crossed_dielectric:
                        candidates.append(candidate.layer_id)
                    break
                cursor += direction
        if not candidates:
            continue
        candidate_ids = set(candidates)
        if len(candidate_ids) == 1:
            result[layer.layer_id] = next(iter(candidate_ids))
        else:
            ambiguous.add(layer.layer_id)
    return result, ambiguous


def _resolve_reference_nets(
    snapshot: DocumentSnapshot, references: list[str] | None
) -> tuple[list[ObjectRecord], list[dict[str, str]]]:
    assert snapshot.board is not None
    if references is not None:
        return [resolve_net(snapshot, reference) for reference in references], []
    selected: list[ObjectRecord] = []
    skipped: list[dict[str, str]] = []
    for default_name in ("GND", "GROUND", "0V"):
        matches = [
            net
            for net in snapshot.board.nets
            if (net.name or "").casefold() == default_name.casefold()
        ]
        if len(matches) == 1:
            selected.append(matches[0])
        elif len(matches) > 1:
            skipped.append(
                {
                    "check_id": "reference_net_resolution",
                    "reason": f"ambiguous_default_name:{default_name}",
                }
            )
    return selected, skipped


def _matches_any_net(record: ObjectRecord, nets: list[ObjectRecord]) -> bool:
    return any(record_belongs_to_net(record, net) for net in nets)


def _pours_by_layer(
    snapshot: DocumentSnapshot, reference_nets: list[ObjectRecord]
) -> dict[str, list[list[Point]]]:
    assert snapshot.board is not None
    result: dict[str, list[list[Point]]] = {}
    for pour in snapshot.board.copper_pours:
        if not bool(pour.attributes.get("poured")):
            continue
        if not _matches_any_net(pour, reference_nets):
            continue
        points = [Point(**item) for item in pour.attributes.get("points", [])]
        if len(points) >= 3:
            result.setdefault(pour.layer or "", []).append(points)
    return result


def _covered(point: Point, polygons: list[list[Point]]) -> bool:
    return any(point_in_polygon(point, polygon) for polygon in polygons)


def _trace_segment_layers(trace: ObjectRecord) -> list[str]:
    points = trace.attributes.get("points", [])
    raw_layers = trace.attributes.get("segment_layers", [])
    return [
        str(raw_layers[index] if index < len(raw_layers) else trace.layer or "")
        for index in range(max(0, len(points) - 1))
    ]


def _normalized_transition_at(
    snapshot: DocumentSnapshot, trace: ObjectRecord, location: Point
) -> ObjectRecord | None:
    assert snapshot.board is not None
    candidates = [
        via
        for via in snapshot.board.vias
        if via.parent_id == trace.stable_id
        and via.attributes.get("representation") == "trace_layer_transition"
        and via.position is not None
        and Point(**via.position) == location
    ]
    return candidates[0] if len(candidates) == 1 else None


def _via_bridges_layers(via: ObjectRecord, first: str, second: str) -> bool:
    if via.attributes.get("span_source") != "explicit":
        return False
    span = [str(value) for value in via.attributes.get("span_layer_ids", [])]
    return first in span and second in span


def analyze_return_path(
    snapshot: DocumentSnapshot,
    *,
    stitching_radius_mm: float,
    nets: list[str] | None = None,
    reference_nets: list[str] | None = None,
) -> ReturnPathAnalysis:
    if snapshot.board is None:
        raise DocumentError("Return-path analysis requires a PCB document")
    if not math.isfinite(stitching_radius_mm) or stitching_radius_mm <= 0:
        raise DocumentError("stitching_radius_mm must be finite and positive")
    selected_nets = (
        [resolve_net(snapshot, reference) for reference in nets]
        if nets
        else list(snapshot.board.nets)
    )
    resolved_reference_nets, skipped = _resolve_reference_nets(
        snapshot, reference_nets
    )
    reference_layers, ambiguous_reference_layers = _reference_layers(snapshot)
    pours = _pours_by_layer(snapshot, resolved_reference_nets)
    layer_names = {
        str(layer.get("id", "")): str(layer.get("name", ""))
        for layer in snapshot.board.layers
    }
    issues: list[ReturnPathIssue] = []
    segment_count = 0
    observed_transition_count = 0
    unresolved_transitions: set[tuple[str, int]] = set()
    selected_ids = {net.stable_id for net in selected_nets}
    reference_vias = [
        via
        for via in snapshot.board.vias
        if _matches_any_net(via, resolved_reference_nets)
        and via.position is not None
    ]
    for trace in snapshot.board.traces:
        if trace.parent_id not in selected_ids:
            continue
        net = snapshot.get_object(trace.parent_id)
        points = [Point(**point) for point in trace.attributes.get("points", [])]
        layers = _trace_segment_layers(trace)
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            segment_count += 1
            signal_layer = layers[index] if index < len(layers) else ""
            reference_layer = reference_layers.get(signal_layer)
            location = Point((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
            if (
                reference_layer is None
                or signal_layer in ambiguous_reference_layers
            ):
                reason = (
                    "More than one adjacent physical reference layer is available; "
                    "the XML provides no basis for choosing one."
                    if signal_layer in ambiguous_reference_layers
                    else "No adjacent physical reference layer can be resolved."
                )
                issues.append(
                    ReturnPathIssue(
                        issue_type="reference_unknown",
                        net_id=net.stable_id,
                        net_name=net.name,
                        trace_id=trace.stable_id,
                        layer=layer_names.get(signal_layer, signal_layer),
                        segment_index=index,
                        location=location.as_dict(),
                        confidence=1.0,
                        explanation=reason,
                        suggested_actions=[
                            "Complete LayerStackItems or explicitly inspect the reference layer."
                        ],
                    )
                )
                continue
            polygons = pours.get(reference_layer, [])
            if not polygons:
                issues.append(
                    ReturnPathIssue(
                        issue_type="unreferenced_segment",
                        net_id=net.stable_id,
                        net_name=net.name,
                        trace_id=trace.stable_id,
                        layer=layer_names.get(signal_layer, signal_layer),
                        reference_layer=layer_names.get(
                            reference_layer, reference_layer
                        ),
                        segment_index=index,
                        location=location.as_dict(),
                        estimated_detour_mm=distance(start, end),
                        confidence=0.4,
                        explanation=(
                            "No poured boundary on a resolved reference net covers the "
                            "adjacent layer."
                        ),
                        suggested_actions=[
                            "Inspect the actual plane/pour in DipTrace and add or repair "
                            "the reference copper."
                        ],
                    )
                )
                continue
            # This bounded observation deliberately remains a heuristic. The result
            # discloses the three-point limit instead of treating it as full geometry.
            samples = (start, location, end)
            coverage = [_covered(sample, polygons) for sample in samples]
            if not all(coverage):
                issue_type: Literal[
                    "unreferenced_segment", "possible_split_crossing"
                ] = (
                    "possible_split_crossing"
                    if coverage[0] and coverage[2]
                    else "unreferenced_segment"
                )
                issues.append(
                    ReturnPathIssue(
                        issue_type=issue_type,
                        net_id=net.stable_id,
                        net_name=net.name,
                        trace_id=trace.stable_id,
                        layer=layer_names.get(signal_layer, signal_layer),
                        reference_layer=layer_names.get(
                            reference_layer, reference_layer
                        ),
                        segment_index=index,
                        location=location.as_dict(),
                        estimated_detour_mm=distance(start, end),
                        confidence=0.4,
                        explanation=(
                            "Three sampled segment points are not fully contained by the "
                            "exported reference-pour boundary."
                        ),
                        suggested_actions=[
                            "Move the route, repair the plane, or provide a deliberate "
                            "return path."
                        ],
                    )
                )

        for index, (first_layer, second_layer) in enumerate(
            zip(layers, layers[1:], strict=False)
        ):
            if not first_layer or not second_layer or first_layer == second_layer:
                continue
            observed_transition_count += 1
            transition_location = points[index + 1]
            if _normalized_transition_at(snapshot, trace, transition_location) is None:
                unresolved_transitions.add((trace.stable_id, index))
                skipped.append(
                    {
                        "check_id": "return_path.layer_transition",
                        "reason": "normalized_signal_via_missing",
                    }
                )
            first_reference = reference_layers.get(first_layer)
            second_reference = reference_layers.get(second_layer)
            if (
                first_reference is None
                or second_reference is None
                or first_layer in ambiguous_reference_layers
                or second_layer in ambiguous_reference_layers
            ):
                unresolved_transitions.add((trace.stable_id, index))
                issues.append(
                    ReturnPathIssue(
                        issue_type="reference_unknown",
                        net_id=net.stable_id,
                        net_name=net.name,
                        trace_id=trace.stable_id,
                        layer=(
                            f"{layer_names.get(first_layer, first_layer)} -> "
                            f"{layer_names.get(second_layer, second_layer)}"
                        ),
                        segment_index=index,
                        location=transition_location.as_dict(),
                        confidence=1.0,
                        explanation=(
                            "The reference-layer transition cannot be resolved from the "
                            "exported physical stack."
                        ),
                        suggested_actions=[
                            "Inspect the stack and return-current transition in DipTrace."
                        ],
                    )
                )
                continue
            if first_reference == second_reference:
                continue
            compatible = [
                via
                for via in reference_vias
                if _via_bridges_layers(via, first_reference, second_reference)
            ]
            nearest = min(
                (
                    distance(transition_location, Point(**candidate.position))
                    for candidate in compatible
                    if candidate.position is not None
                ),
                default=None,
            )
            if nearest is not None and nearest <= stitching_radius_mm:
                continue
            issues.append(
                ReturnPathIssue(
                    issue_type="transition_without_return_via",
                    net_id=net.stable_id,
                    net_name=net.name,
                    trace_id=trace.stable_id,
                    layer=(
                        f"{layer_names.get(first_layer, first_layer)} -> "
                        f"{layer_names.get(second_layer, second_layer)}"
                    ),
                    location=transition_location.as_dict(),
                    estimated_detour_mm=nearest,
                    confidence=0.5,
                    explanation=(
                        "No resolved reference-net via with an explicit compatible span "
                        f"is within the caller-supplied {stitching_radius_mm:g} mm radius."
                    ),
                    suggested_actions=[
                        "Review connector/plane context and add a return via if "
                        "electrically valid."
                    ],
                )
            )

    if snapshot.board.stackup.source == "missing":
        skipped.append(
            {
                "check_id": "adjacent_reference_layers",
                "reason": "physical_stackup_missing",
            }
        )
    if not snapshot.board.copper_pours:
        skipped.append(
            {
                "check_id": "reference_pour_coverage",
                "reason": "copper_pours_missing",
            }
        )
    if not resolved_reference_nets:
        skipped.append(
            {
                "check_id": "reference_net_resolution",
                "reason": "no_reference_net_resolved",
            }
        )
    unique_skipped = [
        {"check_id": check_id, "reason": reason}
        for check_id, reason in sorted(
            {(item["check_id"], item["reason"]) for item in skipped}
        )
    ]
    return ReturnPathAnalysis(
        net_count=len(selected_nets),
        segment_count=segment_count,
        transition_count=observed_transition_count,
        unresolved_transition_count=len(unresolved_transitions),
        issues=issues,
        suggested_stitching_locations=[
            issue.location
            for issue in issues
            if issue.issue_type == "transition_without_return_via"
            and issue.location is not None
        ],
        assumptions=[
            "Reference coverage uses exported CopperPour boundary polygons, not final refill.",
            "Coverage observes only segment start, midpoint and end; crossings between "
            "those samples can be missed.",
            "Only explicit normalized via spans establish a reference-layer bridge.",
            "The stitching radius is supplied by the caller; no built-in engineering "
            "threshold is applied.",
            "Antipads, voids and plane connectivity not represented in XML are unavailable.",
            "This is a low-confidence geometry heuristic, not a full-wave result.",
        ],
        skipped=unique_skipped,
        confidence="low",
    )


def analyze_plane_continuity(snapshot: DocumentSnapshot) -> dict[str, Any]:
    if snapshot.board is None:
        raise DocumentError("Plane-continuity analysis requires a PCB document")
    items: list[dict[str, Any]] = []
    for pour in snapshot.board.copper_pours:
        points = [Point(**point) for point in pour.attributes.get("points", [])]
        area = 0.0
        if len(points) >= 3:
            area = abs(
                sum(
                    left.x * right.y - right.x * left.y
                    for left, right in zip(
                        points, [*points[1:], points[0]], strict=True
                    )
                )
            ) / 2.0
        items.append(
            {
                "pour_id": pour.stable_id,
                "net": pour.net_name,
                "layer": pour.layer,
                "boundary_area_mm2": area,
                "poured": bool(pour.attributes.get("poured")),
                "regions_done": bool(pour.attributes.get("regions_done")),
                "bbox": pour.bbox,
                "confidence": 0.6,
            }
        )
    return {
        "pour_count": len(items),
        "items": items,
        "limitations": [
            "Boundary area is not final refilled copper area.",
            "Plane islands, antipads and electrical continuity require DipTrace refill "
            "or manufacturing geometry.",
        ],
    }
