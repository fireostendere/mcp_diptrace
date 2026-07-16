from __future__ import annotations

from typing import Any, Literal

from .adapters import DocumentSnapshot
from .domain import ReturnPathAnalysis, ReturnPathIssue
from .errors import DocumentError
from .geometry import Point, distance, point_in_polygon
from .lengths import resolve_net


def _reference_layers(snapshot: DocumentSnapshot) -> dict[str, str]:
    assert snapshot.board is not None
    result: dict[str, str] = {}
    layers = snapshot.board.stackup.layers
    for index, layer in enumerate(layers):
        if layer.layer_id is None or layer.material.material_type not in {
            "conductor",
            "plane",
        }:
            continue
        candidates: list[tuple[int, int, str]] = []
        for direction in (-1, 1):
            cursor = index + direction
            dielectric_count = 0
            while 0 <= cursor < len(layers):
                candidate = layers[cursor]
                if candidate.material.material_type == "dielectric":
                    dielectric_count += 1
                    cursor += direction
                    continue
                if candidate.material.material_type in {"conductor", "plane"}:
                    if candidate.layer_id is not None and dielectric_count:
                        plane_preference = int(candidate.material.material_type != "plane")
                        candidates.append(
                            (dielectric_count, plane_preference, candidate.layer_id)
                        )
                    break
                cursor += direction
        if candidates:
            result[layer.layer_id] = min(candidates)[2]
    return result


def _pours_by_layer(
    snapshot: DocumentSnapshot, reference_nets: set[str]
) -> dict[str, list[list[Point]]]:
    assert snapshot.board is not None
    result: dict[str, list[list[Point]]] = {}
    for pour in snapshot.board.copper_pours:
        if not bool(pour.attributes.get("poured")):
            continue
        if (pour.net_name or "").casefold() not in reference_nets:
            continue
        points = [Point(**item) for item in pour.attributes.get("points", [])]
        if len(points) >= 3:
            result.setdefault(pour.layer or "", []).append(points)
    return result


def _covered(point: Point, polygons: list[list[Point]]) -> bool:
    return any(point_in_polygon(point, polygon) for polygon in polygons)


def analyze_return_path(
    snapshot: DocumentSnapshot,
    *,
    nets: list[str] | None = None,
    reference_nets: list[str] | None = None,
    stitching_radius_mm: float = 2.0,
) -> ReturnPathAnalysis:
    if snapshot.board is None:
        raise DocumentError("Return-path analysis requires a PCB document")
    if stitching_radius_mm <= 0:
        raise DocumentError("stitching_radius_mm must be positive")
    selected_nets = (
        [resolve_net(snapshot, reference) for reference in nets]
        if nets
        else list(snapshot.board.nets)
    )
    reference_names = {
        name.casefold() for name in (reference_nets or ["GND", "GROUND", "0V"])
    }
    reference_layers = _reference_layers(snapshot)
    pours = _pours_by_layer(snapshot, reference_names)
    layer_names = {
        str(layer.get("id", "")): str(layer.get("name", ""))
        for layer in snapshot.board.layers
    }
    issues: list[ReturnPathIssue] = []
    skipped: list[dict[str, str]] = []
    segment_count = 0
    selected_ids = {net.stable_id for net in selected_nets}
    for trace in snapshot.board.traces:
        if trace.parent_id not in selected_ids:
            continue
        net = snapshot.get_object(trace.parent_id)
        points = [Point(**point) for point in trace.attributes.get("points", [])]
        layers = trace.attributes.get("segment_layers", [])
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            segment_count += 1
            signal_layer = (
                str(layers[index]) if index < len(layers) else trace.layer or ""
            )
            reference_layer = reference_layers.get(signal_layer)
            location = Point((start.x + end.x) / 2.0, (start.y + end.y) / 2.0)
            if reference_layer is None:
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
                        explanation="No adjacent physical reference layer can be resolved.",
                        suggested_actions=["Complete LayerStackItems or select a reference layer."],
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
                        reference_layer=layer_names.get(reference_layer, reference_layer),
                        segment_index=index,
                        location=location.as_dict(),
                        estimated_detour_mm=distance(start, end),
                        confidence=0.65,
                        explanation=(
                            "No poured boundary on an explicit reference net covers the "
                            "adjacent layer."
                        ),
                        suggested_actions=[
                            "Inspect the actual plane/pour in DipTrace and add or repair the "
                            "reference copper."
                        ],
                    )
                )
                continue
            samples = (start, location, end)
            coverage = [_covered(sample, polygons) for sample in samples]
            if not all(coverage):
                issue_type: Literal["unreferenced_segment", "possible_split_crossing"] = (
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
                        reference_layer=layer_names.get(reference_layer, reference_layer),
                        segment_index=index,
                        location=location.as_dict(),
                        estimated_detour_mm=distance(start, end),
                        confidence=0.7,
                        explanation=(
                            "Sampled segment points are not fully contained by the exported "
                            "reference-pour boundary."
                        ),
                        suggested_actions=[
                            "Move the route, repair the plane, or provide a deliberate return path."
                        ],
                    )
                )
    reference_vias = [
        via
        for via in snapshot.board.vias
        if (via.net_name or "").casefold() in reference_names and via.position is not None
    ]
    selected_vias = [
        via
        for via in snapshot.board.vias
        if via.net_name
        and any((net.name or "").casefold() == via.net_name.casefold() for net in selected_nets)
        and via.position is not None
    ]
    stitching_locations: list[dict[str, float]] = []
    for via in selected_vias:
        assert via.position is not None
        point = Point(**via.position)
        nearest = min(
            (
                distance(point, Point(**candidate.position))
                for candidate in reference_vias
                if candidate.position is not None
            ),
            default=None,
        )
        if nearest is not None and nearest <= stitching_radius_mm:
            continue
        net = resolve_net(snapshot, via.net_name or "")
        stitching_locations.append(point.as_dict())
        issues.append(
            ReturnPathIssue(
                issue_type="transition_without_return_via",
                net_id=net.stable_id,
                net_name=net.name,
                trace_id=via.parent_id,
                layer="through",
                location=point.as_dict(),
                estimated_detour_mm=nearest,
                confidence=0.8,
                explanation=(
                    f"No {', '.join(sorted(reference_names))} via is within "
                    f"{stitching_radius_mm:g} mm of the signal transition."
                ),
                suggested_actions=[
                    "Review connector/plane context and add a return via if electrically valid."
                ],
            )
        )
    if snapshot.board.stackup.source == "missing":
        skipped.append(
            {"check_id": "adjacent_reference_layers", "reason": "physical_stackup_missing"}
        )
    if not snapshot.board.copper_pours:
        skipped.append(
            {"check_id": "reference_pour_coverage", "reason": "copper_pours_missing"}
        )
    return ReturnPathAnalysis(
        net_count=len(selected_nets),
        segment_count=segment_count,
        transition_count=len(selected_vias),
        issues=issues,
        suggested_stitching_locations=stitching_locations,
        assumptions=[
            "Reference coverage uses exported CopperPour boundary polygons, not final refill.",
            "Antipads, voids and plane connectivity not represented in XML are unavailable.",
            "This is a geometry-based heuristic, not a full-wave result.",
        ],
        skipped=skipped,
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
                    for left, right in zip(points, [*points[1:], points[0]], strict=True)
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
            "Plane islands, antipads and electrical continuity require DipTrace refill or "
            "manufacturing geometry."
        ],
    }
