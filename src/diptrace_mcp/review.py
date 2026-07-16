from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .adapters import DocumentSnapshot
from .advanced_review import register_advanced_checks
from .domain import ObjectRecord
from .findings import Finding, make_finding
from .geometry import BBox, Point, point_in_polygon, segment_distance, to_mm
from .geometry_backend import line_to_shape_distance, shapely_available
from .spatial import SpatialIndex

CheckFunction = Callable[[DocumentSnapshot], tuple[list[Finding], dict[str, Any]]]


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
            self._checks[check_id] = RegisteredCheck(
                check_id, category, source_kind, function
            )
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


@registry.register("pcb.unrouted_net", "connectivity", "pcb")
def check_unrouted_nets(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    findings: list[Finding] = []
    for net in snapshot.board.nets:
        endpoint_count = int(net.attributes.get("endpoint_count", 0))
        trace_count = int(net.attributes.get("trace_count", 0))
        if endpoint_count > 1 and trace_count == 0:
            findings.append(
                make_finding(
                    "pcb.unrouted_net",
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


@registry.register("pcb.dangling_trace", "connectivity", "pcb")
def check_dangling_traces(snapshot: DocumentSnapshot) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    findings: list[Finding] = []
    for trace in snapshot.board.traces:
        length = float(trace.attributes.get("length_mm", 0.0))
        points = trace.attributes.get("points", [])
        if len(points) < 2 or length <= 0:
            findings.append(
                make_finding(
                    "pcb.dangling_trace",
                    "connectivity",
                    "error",
                    "Trace has no usable path",
                    "Trace contains fewer than two distinct path points.",
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
        element.get("Lay", ""): to_mm(
            float(element.get("TraceToTrace", "0")), snapshot.document.units
        )
        for element in snapshot.document.container.findall("./DRC/LayClearances/LayClearance")
        if element.get("TraceToTrace") is not None
    }
    if not clearance_by_layer:
        return [], {"skipped": "trace_clearance_rules_unavailable"}
    maximum_clearance = max(clearance_by_layer.values())
    segment_records: list[ObjectRecord] = []
    segment_geometry: dict[str, tuple[Point, Point, float, str, str]] = {}
    for trace in snapshot.board.traces:
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        widths = [float(item) for item in trace.attributes.get("segment_widths_mm", [])]
        layers = trace.attributes.get("segment_layers", [])
        for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            width = widths[segment_index] if segment_index < len(widths) else 0.0
            layer = str(layers[segment_index]) if segment_index < len(layers) else trace.layer or ""
            digest = hashlib.sha256(
                f"{trace.stable_id}:{segment_index}".encode()
            ).hexdigest()[:16]
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
    for segment in segment_records:
        assert segment.bbox is not None
        for other in index.query(BBox(**segment.bbox), layers={segment.layer or ""}):
            if segment.stable_id == other.stable_id or segment.net_id == other.net_id:
                continue
            first, second = sorted((segment.stable_id, other.stable_id))
            pair = (first, second)
            if pair in seen:
                continue
            seen.add(pair)
            a1, a2, width_a, trace_a, layer = segment_geometry[segment.stable_id]
            b1, b2, width_b, trace_b, _ = segment_geometry[other.stable_id]
            required = clearance_by_layer.get(layer, maximum_clearance)
            measured = max(
                0.0,
                segment_distance(a1, a2, b1, b2) - (width_a + width_b) / 2.0,
            )
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
                        rule_source="DRC/LayClearances/LayClearance.TraceToTrace",
                        suggested_actions=[
                            "Reroute one segment or change the applicable rule explicitly."
                        ],
                    )
                )
    return findings, {
        "segments_checked": len(segment_records),
        "candidate_pairs_checked": len(seen),
    }


@registry.register("pcb.trace_object_clearance", "clearance", "pcb")
def check_trace_object_clearance(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    rules = {
        element.get("Lay", ""): {
            key: to_mm(float(value), snapshot.document.units)
            for key in ("TraceToPad", "TraceToVia")
            if (value := element.get(key)) is not None
        }
        for element in snapshot.document.container.findall("./DRC/LayClearances/LayClearance")
    }
    maximum = max(
        (value for layer in rules.values() for value in layer.values()), default=0.0
    )
    if maximum <= 0.0:
        return [], {"skipped": "trace_to_pad_via_rules_unavailable"}
    obstacles = [
        item
        for item in [*snapshot.board.pads, *snapshot.board.vias]
        if item.bbox is not None and item.geometry is not None
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
    for trace in snapshot.board.traces:
        points = [Point(**item) for item in trace.attributes.get("points", [])]
        widths = [float(item) for item in trace.attributes.get("segment_widths_mm", [])]
        layers = trace.attributes.get("segment_layers", [])
        for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            width = widths[segment_index] if segment_index < len(widths) else 0.0
            layer_id = (
                str(layers[segment_index])
                if segment_index < len(layers)
                else trace.layer or ""
            )
            search_box = BBox.from_points([start, end]).expand(width / 2.0 + maximum)
            for indexed in index.query(search_box):
                obstacle = snapshot.get_object(indexed.stable_id)
                if obstacle.net_id == trace.net_id or not _copper_on_layer(
                    snapshot, obstacle, layer_id
                ):
                    continue
                rule_name = "TraceToVia" if obstacle.kind == "via" else "TraceToPad"
                required = rules.get(layer_id, {}).get(rule_name)
                if required is None:
                    continue
                assert obstacle.geometry is not None
                if not shapely_available() and obstacle.geometry.kind not in {"circle"}:
                    skipped_geometry += 1
                    continue
                candidates += 1
                measured = line_to_shape_distance(start, end, width, obstacle.geometry)
                if measured + 1e-9 >= required:
                    continue
                findings.append(
                    make_finding(
                        "pcb.trace_object_clearance",
                        "clearance",
                        "error",
                        f"Trace-to-{obstacle.kind} clearance violation",
                        f"Copper edge clearance is {measured:.4g} mm; "
                        f"{required:.4g} mm is required.",
                        object_ids=[trace.stable_id, obstacle.stable_id],
                        net_ids=[
                            value for value in (trace.parent_id, obstacle.net_id) if value
                        ],
                        layer=layer_id,
                        measured=measured,
                        required=required,
                        units="mm",
                        rule_source=f"DRC/LayClearances/LayClearance.{rule_name}",
                        confidence=1.0 if shapely_available() else 0.95,
                        suggested_actions=[
                            "Reroute the segment or change the applicable clearance rule."
                        ],
                    )
                )
    return findings, {
        "obstacles_indexed": len(obstacles),
        "candidate_pairs_checked": candidates,
        "skipped_geometry": skipped_geometry,
        "geometry_backend": "shapely_geos" if shapely_available() else "pure_python",
    }


def _copper_on_layer(
    snapshot: DocumentSnapshot,
    obstacle: ObjectRecord,
    layer_id: str,
) -> bool:
    if obstacle.kind == "via":
        return True
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
        and str(layer.get("name", "")).casefold().startswith(
            (obstacle.side or "Top").casefold()
        )
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
    metrics: dict[str, Any] = {}
    skipped: list[dict[str, str]] = []
    for check in checks:
        check_findings, check_metrics = check.function(snapshot)
        reason = check_metrics.pop("skipped", None)
        if reason is not None:
            skipped.append({"check_id": check.check_id, "reason": str(reason)})
        else:
            findings.extend(check_findings)
        metrics[check.check_id] = check_metrics
    return findings, metrics, skipped, len(checks)
