from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot
from .advanced_review import register_advanced_checks
from .clearance import clearance_rule_status, clearance_source_label, resolve_clearance
from .domain import ObjectRecord
from .errors import CapabilityUnavailableError, NetClassResolutionError
from .findings import Finding, make_finding
from .geometry import BBox, Point, point_in_polygon, segment_distance
from .geometry_backend import line_to_shape_distance, shapely_available
from .numeric_inputs import xml_number_mm
from .spatial import SpatialIndex

CheckFunction = Callable[[DocumentSnapshot], tuple[list[Finding], dict[str, Any]]]

MAX_SKIPPED_PAIR_REASONS = 100


def _append_bounded_reason(
    reasons: list[dict[str, Any]],
    reason: dict[str, Any],
    *,
    total: int,
) -> int:
    next_total = total + 1
    if len(reasons) < MAX_SKIPPED_PAIR_REASONS:
        reasons.append(reason)
    return next_total


@dataclass(frozen=True, slots=True)
class RegisteredCheck:
    check_id: str
    category: str
    source_kind: str
    function: CheckFunction


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, RegisteredCheck] = {}

    def register(
        self, check_id: str, category: str, source_kind: str
    ) -> Callable[[CheckFunction], CheckFunction]:
        def decorator(function: CheckFunction) -> CheckFunction:
            if check_id in self._checks:
                raise ValueError(f"Duplicate review check: {check_id}")
            self._checks[check_id] = RegisteredCheck(check_id, category, source_kind, function)
            return function

        return decorator

    def checks(self, source_kind: str, categories: set[str] | None = None) -> list[RegisteredCheck]:
        return [
            check
            for check in self._checks.values()
            if check.source_kind == source_kind
            and (categories is None or check.category in categories)
        ]

    def ids(self) -> list[str]:
        return sorted(self._checks)


registry = CheckRegistry()
register_advanced_checks(registry)


@registry.register("pcb.component_overlap", "placement", "pcb")
def check_component_overlap(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    objects = [
        item for item in [*snapshot.board.components, *snapshot.board.testpoints] if item.bbox
    ]
    index = SpatialIndex(cell_size_mm=5.0)
    for item in objects:
        index.insert(item)
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for item in objects:
        assert item.bbox is not None
        for other in index.query(BBox(**item.bbox)):
            first, second = sorted((item.stable_id, other.stable_id))
            pair = (first, second)
            if item.stable_id == other.stable_id or pair in seen:
                continue
            seen.add(pair)
            if item.side != other.side or other.bbox is None:
                continue
            a = BBox(**item.bbox)
            b = BBox(**other.bbox)
            overlap_x = min(a.max_x, b.max_x) - max(a.min_x, b.min_x)
            overlap_y = min(a.max_y, b.max_y) - max(a.min_y, b.min_y)
            if overlap_x > 0 and overlap_y > 0:
                findings.append(
                    make_finding(
                        "pcb.component_overlap",
                        "placement",
                        "error",
                        "Component geometry overlaps",
                        f"{item.label} and {other.label} overlap on {item.side}.",
                        object_ids=[item.stable_id, other.stable_id],
                        layer=item.side,
                        bbox={
                            "min_x": max(a.min_x, b.min_x),
                            "min_y": max(a.min_y, b.min_y),
                            "max_x": min(a.max_x, b.max_x),
                            "max_y": min(a.max_y, b.max_y),
                        },
                        confidence=min(item.confidence, other.confidence),
                        suggested_actions=["Move one object and rerun localized clearance checks."],
                    )
                )
    return findings, {"objects_checked": len(objects), "pairs_checked": len(seen)}


@registry.register("pcb.component_edge", "placement", "pcb")
def check_component_edge(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    outline_data = snapshot.board.outline
    if outline_data is None:
        return [], {"skipped": "board_outline_missing"}
    polygon = [Point(**item) for item in outline_data.get("points", [])]
    findings: list[Finding] = []
    checked = 0
    for item in [*snapshot.board.components, *snapshot.board.testpoints]:
        if item.bbox is None:
            continue
        checked += 1
        box = BBox(**item.bbox)
        corners = [
            Point(box.min_x, box.min_y),
            Point(box.min_x, box.max_y),
            Point(box.max_x, box.min_y),
            Point(box.max_x, box.max_y),
        ]
        if not all(point_in_polygon(point, polygon) for point in corners):
            findings.append(
                make_finding(
                    "pcb.component_edge",
                    "placement",
                    "error",
                    "Component crosses board outline",
                    f"{item.label} is not fully contained by the board outline.",
                    object_ids=[item.stable_id],
                    layer=item.side,
                    bbox=item.bbox,
                    confidence=item.confidence,
                    suggested_actions=["Move the object inward and preserve edge clearance."],
                )
            )
    return findings, {"objects_checked": checked}


@registry.register("pcb.net_without_traces", "connectivity", "pcb")
def check_nets_without_traces(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    findings: list[Finding] = []
    for net in snapshot.board.nets:
        endpoint_count = int(net.attributes.get("endpoint_count", 0))
        trace_count = int(net.attributes.get("trace_count", 0))
        if endpoint_count > 1 and trace_count == 0:
            findings.append(
                make_finding(
                    "pcb.net_without_traces",
                    "connectivity",
                    "error",
                    "Net has no routed trace",
                    f"Net {net.name!r} has {endpoint_count} endpoints and no traces.",
                    object_ids=[net.stable_id],
                    net_ids=[net.stable_id],
                    confidence=1.0,
                    suggested_actions=["Route the net or document why it is intentionally open."],
                )
            )
    return findings, {"nets_checked": len(snapshot.board.nets)}


@registry.register("pcb.degenerate_trace_path", "connectivity", "pcb")
def check_degenerate_trace_paths(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    findings: list[Finding] = []
    for trace in snapshot.board.traces:
        length = float(trace.attributes.get("length_mm", 0.0))
        points = trace.attributes.get("points", [])
        if len(points) < 2 or length <= 0:
            findings.append(
                make_finding(
                    "pcb.degenerate_trace_path",
                    "connectivity",
                    "error",
                    "Trace path has no usable length",
                    "Trace contains fewer than two points or has zero path length.",
                    object_ids=[trace.stable_id],
                    net_ids=[trace.parent_id] if trace.parent_id else [],
                    layer=trace.layer,
                    bbox=trace.bbox,
                )
            )
    return findings, {"traces_checked": len(snapshot.board.traces)}


@registry.register("pcb.trace_clearance", "clearance", "pcb")
def check_trace_clearance(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    clearance_by_layer = {
        element.get("Lay", ""): xml_number_mm(
            snapshot.document,
            element,
            "TraceToTrace",
        )
        for element in snapshot.document.container.findall("./DRC/LayClearances/LayClearance")
        if element.get("TraceToTrace") is not None
    }
    netclass_clearances = [
        xml_number_mm(snapshot.document, item, "Clearance")
        for net_class in snapshot.document.container.findall("./NetClasses/NetClass")
        for item in net_class.findall("./LayProperties/LayProperty")
        if item.get("Clearance") is not None
    ]
    base_status = clearance_rule_status(snapshot, operation="offline_clearance_review")
    rules_available = bool(clearance_by_layer or netclass_clearances)
    if not rules_available:
        unavailable_warning_codes = ["trace_clearance_rules_unavailable"]
        final_status = {
            **base_status,
            "clearance_review_complete": False,
            "partial_review": True,
            "warning_code": unavailable_warning_codes[0],
            "warning_codes": unavailable_warning_codes,
        }
        segment_count = sum(
            max(0, len(trace.attributes.get("points", [])) - 1) for trace in snapshot.board.traces
        )
        return [], {
            "segments_checked": segment_count,
            "candidate_pairs_checked": 0,
            "candidate_pairs_not_enumerated": True,
            "evaluated_pairs": 0,
            "skipped_unresolved_net_pairs": 0,
            "skipped_clearance_resolution_pairs": 0,
            "skipped_netclass_pairs": 0,
            "skipped_pair_reasons": [
                {
                    "reason_code": "trace_clearance_rules_unavailable",
                    "scope": "check",
                }
            ],
            "skipped_pair_reasons_total": 1,
            "skipped_pair_reasons_truncated": False,
            "warning_codes": unavailable_warning_codes,
            "clearance_review_complete": False,
            "clearance_rule_status": final_status,
            "partial_skipped": "trace_clearance_rules_unavailable",
        }
    maximum_clearance = max([*clearance_by_layer.values(), *netclass_clearances], default=0.0)
    segment_records: list[ObjectRecord] = []
    segment_geometry: dict[str, tuple[Point, Point, float, str, str]] = {}
    for trace in snapshot.board.traces:
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        widths = [float(item) for item in trace.attributes.get("segment_widths_mm", [])]
        layers = trace.attributes.get("segment_layers", [])
        for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            width = widths[segment_index] if segment_index < len(widths) else 0.0
            layer = str(layers[segment_index]) if segment_index < len(layers) else trace.layer or ""
            digest = hashlib.sha256(f"{trace.stable_id}:{segment_index}".encode()).hexdigest()[:16]
            segment_id = f"trace-segment_{digest}"
            box = BBox.from_points([start, end]).expand(width / 2.0 + maximum_clearance)
            segment_records.append(
                ObjectRecord(
                    stable_id=segment_id,
                    kind="trace_segment",
                    parent_id=trace.stable_id,
                    net_id=trace.net_id,
                    net_name=trace.net_name,
                    layer=layer,
                    bbox=box.as_dict(),
                    geometry_source="xml-trace-points",
                )
            )
            segment_geometry[segment_id] = (start, end, width, trace.stable_id, layer)
    index = SpatialIndex.build(segment_records, cell_size_mm=5.0)
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    net_by_id = {item.xml_id: item for item in snapshot.board.nets if item.xml_id is not None}
    candidate_pairs_checked = 0
    evaluated_pairs = 0
    skipped_unresolved_net_pairs = 0
    skipped_clearance_resolution_pairs = 0
    skipped_pair_reasons: list[dict[str, Any]] = []
    skipped_pair_reasons_total = 0
    warning_codes: set[str] = set()
    for segment in segment_records:
        assert segment.bbox is not None
        candidates = index.query(
            BBox(**segment.bbox),
            layers={segment.layer or ""},
        )
        for other in candidates:
            if segment.stable_id == other.stable_id:
                continue
            if (
                segment.net_id is not None
                and other.net_id is not None
                and segment.net_id == other.net_id
                and segment.net_id in net_by_id
            ):
                continue
            first, second = sorted((segment.stable_id, other.stable_id))
            pair = (first, second)
            if pair in seen:
                continue
            seen.add(pair)
            candidate_pairs_checked += 1
            a1, a2, width_a, trace_a, layer = segment_geometry[segment.stable_id]
            b1, b2, width_b, trace_b, _ = segment_geometry[other.stable_id]
            net_a = net_by_id.get(segment.net_id or "")
            net_b = net_by_id.get(other.net_id or "")
            if net_a is None or net_b is None:
                unresolved_sides = [
                    {
                        "side": side,
                        "segment_id": item.stable_id,
                        "net_id": item.net_id,
                    }
                    for side, item, net in (
                        ("a", segment, net_a),
                        ("b", other, net_b),
                    )
                    if net is None
                ]
                skipped_unresolved_net_pairs += 1
                warning_codes.add("trace_net_unresolved")
                skipped_pair_reasons_total = _append_bounded_reason(
                    skipped_pair_reasons,
                    {
                        "reason_code": "trace_net_unresolved",
                        "pair_segment_ids": [first, second],
                        "unresolved_sides": unresolved_sides,
                    },
                    total=skipped_pair_reasons_total,
                )
                continue
            try:
                resolution = resolve_clearance(
                    snapshot,
                    [layer],
                    None,
                    nets=[net_a, net_b],
                )
            except NetClassResolutionError as exc:
                skipped_clearance_resolution_pairs += 1
                warning_codes.add("trace_netclass_unresolved")
                skipped_pair_reasons_total = _append_bounded_reason(
                    skipped_pair_reasons,
                    {
                        "reason_code": "trace_netclass_unresolved",
                        "pair_segment_ids": [first, second],
                        "details": {
                            "net_ids": [value for value in (segment.net_id, other.net_id) if value],
                            "unresolved_class_reference": str(
                                exc.details.get("unresolved_class_reference", "unknown")
                            ),
                        },
                    },
                    total=skipped_pair_reasons_total,
                )
                continue
            except CapabilityUnavailableError:
                skipped_clearance_resolution_pairs += 1
                unavailable_code = (
                    "trace_clearance_rules_unavailable"
                    if not rules_available
                    else "trace_clearance_resolution_unavailable"
                )
                warning_codes.add(unavailable_code)
                skipped_pair_reasons_total = _append_bounded_reason(
                    skipped_pair_reasons,
                    {
                        "reason_code": unavailable_code,
                        "pair_segment_ids": [first, second],
                        "details": {
                            "layer_id": layer,
                            "net_ids": [value for value in (segment.net_id, other.net_id) if value],
                        },
                    },
                    total=skipped_pair_reasons_total,
                )
                continue
            required = resolution.effective_clearance_mm
            measured = max(
                0.0,
                segment_distance(a1, a2, b1, b2) - (width_a + width_b) / 2.0,
            )
            evaluated_pairs += 1
            if measured + 1e-9 < required:
                findings.append(
                    make_finding(
                        "pcb.trace_clearance",
                        "clearance",
                        "error",
                        "Trace-to-trace clearance violation",
                        f"Copper edge clearance is {measured:.4g} mm; "
                        f"{required:.4g} mm is required.",
                        object_ids=[trace_a, trace_b],
                        net_ids=[value for value in (segment.net_id, other.net_id) if value],
                        layer=layer,
                        measured=measured,
                        required=required,
                        units="mm",
                        rule_source=clearance_source_label(
                            resolution.clearance_sources,
                            required_clearance_mm=resolution.required_clearance_mm,
                            effective_clearance_mm=resolution.effective_clearance_mm,
                            requested_clearance_mm=resolution.requested_clearance_mm,
                        ),
                        rule_sources=list(resolution.clearance_sources),
                        clearance_rule_status=dict(resolution.clearance_rule_status),
                        required_clearance_mm=resolution.required_clearance_mm,
                        requested_clearance_mm=resolution.requested_clearance_mm,
                        effective_clearance_mm=resolution.effective_clearance_mm,
                        suggested_actions=[
                            "Reroute one segment or change the applicable rule explicitly."
                        ],
                    )
                )
    partial = bool(skipped_unresolved_net_pairs or skipped_clearance_resolution_pairs)
    final_status = {
        **base_status,
        "clearance_review_complete": not partial,
    }
    if partial:
        final_status.update(
            {
                "partial_review": True,
                "warning_code": sorted(warning_codes)[0],
                "warning_codes": sorted(warning_codes),
            }
        )
    metrics = {
        "segments_checked": len(segment_records),
        "candidate_pairs_checked": candidate_pairs_checked,
        "evaluated_pairs": evaluated_pairs,
        "skipped_unresolved_net_pairs": skipped_unresolved_net_pairs,
        "skipped_clearance_resolution_pairs": skipped_clearance_resolution_pairs,
        "skipped_netclass_pairs": skipped_clearance_resolution_pairs,
        "skipped_pair_reasons": skipped_pair_reasons,
        "skipped_pair_reasons_total": skipped_pair_reasons_total,
        "skipped_pair_reasons_truncated": (skipped_pair_reasons_total > len(skipped_pair_reasons)),
        "candidate_pairs_not_enumerated": False,
        "warning_codes": sorted(warning_codes),
        "clearance_review_complete": not partial,
        "clearance_rule_status": final_status,
    }
    if partial:
        metrics["partial_skipped"] = "trace_clearance_partial"
    return findings, metrics


@registry.register("pcb.trace_object_clearance", "clearance", "pcb")
def check_trace_object_clearance(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    rules = {
        element.get("Lay", ""): {
            key: xml_number_mm(snapshot.document, element, key)
            for key in ("TraceToPad", "TraceToVia", "TraceToCopper")
            if element.get(key) is not None
        }
        for element in snapshot.document.container.findall("./DRC/LayClearances/LayClearance")
    }
    maximum = max(
        (value for layer in rules.values() for value in layer.values()),
        default=0.0,
    )
    if maximum <= 0.0:
        return [], {
            "skipped": "trace_to_copper_rules_unavailable",
            "clearance_rule_status": clearance_rule_status(
                snapshot, operation="trace_object_clearance"
            ),
        }
    obstacles = [
        item
        for item in [
            *snapshot.board.pads,
            *snapshot.board.vias,
            *snapshot.board.copper_pours,
        ]
        if item.bbox is not None and (item.geometry is not None or item.kind == "copper_pour")
    ]
    index_records = [
        item.model_copy(update={"bbox": BBox(**item.bbox).expand(maximum).as_dict()})
        for item in obstacles
        if item.bbox is not None
    ]
    index = SpatialIndex.build(index_records, cell_size_mm=5.0)
    findings: list[Finding] = []
    candidates = 0
    skipped_geometry = 0
    pour_candidates = 0
    pour_boundary_count = len(snapshot.board.copper_pours)
    for trace in snapshot.board.traces:
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        widths = [float(item) for item in trace.attributes.get("segment_widths_mm", [])]
        layers = trace.attributes.get("segment_layers", [])
        for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            width = widths[segment_index] if segment_index < len(widths) else 0.0
            layer_id = (
                str(layers[segment_index]) if segment_index < len(layers) else trace.layer or ""
            )
            search_box = BBox.from_points([start, end]).expand(width / 2.0 + maximum)
            for indexed in index.query(search_box):
                obstacle = snapshot.get_object(indexed.stable_id)
                if obstacle.net_id == trace.net_id or not _copper_on_layer(
                    snapshot, obstacle, layer_id
                ):
                    continue
                if obstacle.kind == "copper_pour":
                    rule_name = "TraceToCopper"
                    required = rules.get(layer_id, {}).get(rule_name)
                    rule_source = "DRC/LayClearances/LayClearance.TraceToCopper"
                else:
                    rule_name = "TraceToVia" if obstacle.kind == "via" else "TraceToPad"
                    required = rules.get(layer_id, {}).get(rule_name)
                    rule_source = f"DRC/LayClearances/LayClearance.{rule_name}"
                if required is None:
                    continue
                if obstacle.geometry is None:
                    skipped_geometry += 1
                    continue
                if not shapely_available() and obstacle.geometry.kind not in {"circle", "polygon"}:
                    skipped_geometry += 1
                    continue
                candidates += 1
                if obstacle.kind == "copper_pour":
                    pour_candidates += 1
                measured = line_to_shape_distance(start, end, width, obstacle.geometry)
                if measured + 1e-9 >= required:
                    continue
                findings.append(
                    make_finding(
                        "pcb.trace_object_clearance",
                        "clearance",
                        "error",
                        (
                            "Trace-to-copper-pour clearance violation"
                            if obstacle.kind == "copper_pour"
                            else f"Trace-to-{obstacle.kind} clearance violation"
                        ),
                        f"Copper edge clearance is {measured:.4g} mm; "
                        f"{required:.4g} mm is required.",
                        object_ids=[trace.stable_id, obstacle.stable_id],
                        net_ids=[value for value in (trace.parent_id, obstacle.net_id) if value],
                        layer=layer_id,
                        measured=measured,
                        required=required,
                        units="mm",
                        rule_source=rule_source,
                        confidence=(
                            min(trace.confidence, obstacle.confidence)
                            if obstacle.kind == "copper_pour" and shapely_available()
                            else 0.5
                            if obstacle.kind == "copper_pour"
                            else 1.0
                            if shapely_available()
                            else 0.95
                        ),
                        pour_geometry=("boundary_only" if obstacle.kind == "copper_pour" else None),
                        geometry_accuracy=(
                            "exact"
                            if obstacle.kind == "copper_pour" and shapely_available()
                            else "approximate"
                            if obstacle.kind == "copper_pour"
                            else None
                        ),
                        suggested_actions=[
                            "Reroute the segment or change the applicable clearance rule."
                        ],
                    )
                )
    return findings, {
        "obstacles_indexed": len(obstacles),
        "candidate_pairs_checked": candidates,
        "pour_boundaries_indexed": pour_boundary_count,
        "pour_candidate_pairs_checked": pour_candidates,
        "pour_boundaries_without_trace_to_copper_rule": sum(
            rules.get(str(item.layer or ""), {}).get("TraceToCopper") is None
            for item in snapshot.board.copper_pours
        ),
        "pour_geometry": "boundary_only" if pour_boundary_count else None,
        "pour_geometry_accuracy": (
            "exact"
            if pour_boundary_count and shapely_available()
            else "aabb_approximate"
            if pour_boundary_count
            else None
        ),
        "skipped_geometry": skipped_geometry,
        "geometry_backend": "shapely_geos" if shapely_available() else "pure_python",
        "clearance_rule_status": clearance_rule_status(
            snapshot, operation="trace_object_clearance"
        ),
    }


def _copper_on_layer(
    snapshot: DocumentSnapshot,
    obstacle: ObjectRecord,
    layer_id: str,
) -> bool:
    if obstacle.kind == "via":
        return True
    if obstacle.kind == "copper_pour":
        return obstacle.layer == layer_id
    style = obstacle.attributes.get("pad_style") or {}
    if str(style.get("pad_type", "")).casefold() != "surface":
        return True
    assert snapshot.board is not None
    layer = next(
        (item for item in snapshot.board.layers if str(item.get("id", "")) == layer_id),
        None,
    )
    return bool(
        layer is not None
        and str(layer.get("name", "")).casefold().startswith((obstacle.side or "Top").casefold())
    )


@registry.register("pcb.silk_overlap", "silkscreen", "pcb")
def check_silkscreen_overlap(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    silk = [item for item in snapshot.board.texts if "Silk" in (item.layer or "") and item.bbox]
    findings: list[Finding] = []
    for index, item in enumerate(silk):
        assert item.bbox is not None
        box = BBox(**item.bbox)
        for other in silk[index + 1 :]:
            if other.bbox is None or item.side != other.side:
                continue
            if box.intersects(BBox(**other.bbox)):
                findings.append(
                    make_finding(
                        "pcb.silk_overlap",
                        "silkscreen",
                        "warning",
                        "Silkscreen texts overlap",
                        f"{item.label!r} overlaps {other.label!r}.",
                        object_ids=[item.stable_id, other.stable_id],
                        layer=item.layer,
                        confidence=min(item.confidence, other.confidence),
                        suggested_actions=["Move one label while retaining component association."],
                    )
                )
    return findings, {"texts_checked": len(silk)}


@registry.register("schematic.unconnected_pin", "connectivity", "schematic")
def check_unconnected_pins(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.schematic is not None
    findings: list[Finding] = []
    for pin in snapshot.schematic.pins:
        attributes = pin.attributes
        if attributes.get("NetId", "-1") == "-1" and attributes.get("NotConnected", "N") != "Y":
            findings.append(
                make_finding(
                    "schematic.unconnected_pin",
                    "connectivity",
                    "warning",
                    "Pin is unconnected without no-connect marker",
                    f"{pin.refdes} {pin.label} is neither connected nor intentionally marked.",
                    object_ids=[pin.stable_id],
                    confidence=1.0,
                    suggested_actions=["Connect the pin or add an intentional no-connect marker."],
                )
            )
    return findings, {"pins_checked": len(snapshot.schematic.pins)}


@registry.register("schematic.missing_value", "metadata", "schematic")
def check_missing_values(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.schematic is not None
    findings = [
        make_finding(
            "schematic.missing_value",
            "metadata",
            "warning",
            "Schematic part has no value",
            f"{part.refdes or part.label} has an empty value.",
            object_ids=[part.stable_id],
        )
        for part in snapshot.schematic.parts
        if not (part.value or "").strip()
    ]
    return findings, {"parts_checked": len(snapshot.schematic.parts)}


def run_checks(
    snapshot: DocumentSnapshot,
    *,
    categories: set[str] | None = None,
) -> tuple[list[Finding], dict[str, Any], list[dict[str, str]], int]:
    checks = registry.checks(snapshot.document.kind, categories)
    findings: list[Finding] = []
    metrics: dict[str, Any] = {
        "clearance_rule_status": clearance_rule_status(
            snapshot, operation="offline_clearance_review"
        ),
        "netclass_rules_ignored": False,
        "clearance_review_complete": True,
    }
    skipped: list[dict[str, str]] = []
    for check in checks:
        check_findings, check_metrics = check.function(snapshot)
        reason = check_metrics.pop("skipped", None)
        partial_reason = check_metrics.pop("partial_skipped", None)
        if reason is not None:
            skipped.append({"check_id": check.check_id, "reason": str(reason)})
        else:
            findings.extend(check_findings)
            if partial_reason is not None:
                skipped.append({"check_id": check.check_id, "reason": str(partial_reason)})
        metrics[check.check_id] = check_metrics
        check_status = check_metrics.get("clearance_rule_status")
        check_incomplete = check_metrics.get("clearance_review_complete") is False
        if check_incomplete:
            metrics["clearance_review_complete"] = False
            if isinstance(check_status, dict):
                warning_codes = check_status.get("warning_codes", [])
                if not isinstance(warning_codes, list):
                    warning_codes = []
                warning_code = check_status.get("warning_code")
                if warning_code is not None and warning_code not in warning_codes:
                    warning_codes = [*warning_codes, warning_code]
                metrics["clearance_rule_status"] = {
                    **metrics["clearance_rule_status"],
                    "clearance_review_complete": False,
                    "partial_review": True,
                    "warning_code": warning_code,
                    "warning_codes": warning_codes,
                }
        if isinstance(check_status, dict) and check_status.get("netclass_rules_ignored", False):
            metrics["netclass_rules_ignored"] = True
            metrics["clearance_rule_status"] = {
                **metrics["clearance_rule_status"],
                "netclass_rules_ignored": True,
            }
    return findings, metrics, skipped, len(checks)
