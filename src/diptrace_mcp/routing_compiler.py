from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TypeAlias

from .adapters import DocumentSnapshot, stable_id
from .domain import ObjectRecord, QuerySelector, ResolvedCopperLayer
from .errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    ConnectivityRegressionError,
    GeometryError,
    LockedObjectError,
    ObjectNotFoundError,
    RoutingError,
)
from .geometry import (
    BBox,
    Point,
    distance,
    from_mm,
    point_in_polygon,
    point_to_segment_distance,
    segment_distance,
    segment_intersects_bbox,
    to_mm,
)
from .geometry_backend import line_to_shape_distance, shapely_available
from .operations import (
    AddDifferentialPairRouteOperation,
    AddTraceOperation,
    AddViaOperation,
    DeleteTraceOperation,
    DeleteViaOperation,
    MoveViaOperation,
    ReplaceTraceOperation,
    SetTraceWidthOperation,
    SetViaStyleOperation,
    TracePathPoint,
)
from .via_styles import (
    resolve_via_span,
    select_via_style,
    validate_via_geometry,
    validate_via_transition,
)
from .xml_document import DipTraceDocument

RoutingOperation: TypeAlias = (
    AddDifferentialPairRouteOperation
    | AddTraceOperation
    | ReplaceTraceOperation
    | DeleteTraceOperation
    | SetTraceWidthOperation
    | AddViaOperation
    | MoveViaOperation
    | DeleteViaOperation
    | SetViaStyleOperation
)
ROUTING_OPERATION_TYPES = (
    AddDifferentialPairRouteOperation,
    AddTraceOperation,
    ReplaceTraceOperation,
    DeleteTraceOperation,
    SetTraceWidthOperation,
    AddViaOperation,
    MoveViaOperation,
    DeleteViaOperation,
    SetViaStyleOperation,
)


def apply_routing_operation(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: RoutingOperation,
) -> tuple[dict[str, object], int, list[str]]:
    if isinstance(operation, AddDifferentialPairRouteOperation):
        return _add_differential_pair_route(index, document, snapshot, operation)
    if isinstance(operation, AddTraceOperation):
        return _add_trace(index, document, snapshot, operation)
    if isinstance(operation, ReplaceTraceOperation):
        return _replace_trace(index, document, snapshot, operation)
    if isinstance(operation, DeleteTraceOperation):
        return _delete_traces(index, document, snapshot, operation)
    if isinstance(operation, SetTraceWidthOperation):
        return _set_trace_width(index, document, snapshot, operation)
    if isinstance(operation, AddViaOperation):
        return _add_via(index, document, snapshot, operation)
    if isinstance(operation, MoveViaOperation):
        return _move_vias(index, document, snapshot, operation)
    if isinstance(operation, DeleteViaOperation):
        return _delete_vias(index, document, snapshot, operation)
    return _set_via_style(index, document, snapshot, operation)


def _select(
    snapshot: DocumentSnapshot, selector: QuerySelector, kind: str
) -> list[ObjectRecord]:
    if selector.is_empty():
        raise ObjectNotFoundError(f"An explicit {kind} selector is required")
    records = snapshot.select(selector, kinds={kind})
    if not records:
        raise ObjectNotFoundError(f"No matching {kind} objects were found")
    return records


def _element(snapshot: DocumentSnapshot, record: ObjectRecord) -> ET.Element:
    try:
        return snapshot.elements[record.stable_id]
    except KeyError as exc:
        raise ObjectNotFoundError(
            f"XML element is unavailable for {record.stable_id}",
            object_ids=[record.stable_id],
        ) from exc


def _net(snapshot: DocumentSnapshot, value: str) -> ObjectRecord:
    matches = [
        item
        for item in snapshot.objects.values()
        if item.kind == "net"
        and (
            item.stable_id == value
            or item.xml_id == value
            or (item.name or "").casefold() == value.casefold()
        )
    ]
    if not matches:
        raise ObjectNotFoundError(f"Net was not found: {value}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(f"Net selector is ambiguous: {value}")
    return matches[0]


def _trace(snapshot: DocumentSnapshot, trace_id: str) -> ObjectRecord:
    record = snapshot.get_object(trace_id)
    if record.kind != "trace":
        raise ObjectNotFoundError(
            f"Object is not a trace: {trace_id}", object_ids=[trace_id]
        )
    return record


def _ensure_net_unlocked(snapshot: DocumentSnapshot, trace_or_net: ObjectRecord) -> ObjectRecord:
    net = (
        trace_or_net
        if trace_or_net.kind == "net"
        else snapshot.get_object(trace_or_net.parent_id or "")
    )
    if net.locked:
        raise LockedObjectError(f"Net is locked: {net.name}", object_ids=[net.stable_id])
    return net


def _layer_id(snapshot: DocumentSnapshot, value: str) -> str:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Routing operations require a PCB document")
    matches = [
        item
        for item in snapshot.board.layers
        if str(item.get("id", "")) == value
        or str(item.get("name", "")).casefold() == value.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(f"Copper layer was not found: {value}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(f"Copper layer is ambiguous: {value}")
    return str(matches[0]["id"])


def _layer_type(snapshot: DocumentSnapshot, layer_id: str) -> str:
    """Return the layer type ('Signal', 'Plane', or 'Unknown') for a given layer id."""
    if snapshot.board is None:
        return "Unknown"
    for item in snapshot.board.layers:
        if str(item.get("id", "")) == layer_id:
            return str(item.get("type", "Unknown"))
    return "Unknown"


def resolve_copper_layer(
    snapshot: DocumentSnapshot,
    value: str,
) -> ResolvedCopperLayer:
    """Resolve a copper layer by name or id and return validated metadata.

    Resolves by case-insensitive name or exact id match. Raises
    ObjectNotFoundError if no match, AmbiguousSelectorError if multiple.
    """
    if snapshot.board is None:
        raise CapabilityUnavailableError("Routing operations require a PCB document")
    matches = [
        item
        for item in snapshot.board.layers
        if str(item.get("id", "")) == value
        or str(item.get("name", "")).casefold() == value.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(f"Copper layer was not found: {value}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(f"Copper layer is ambiguous: {value}")
    item = matches[0]
    layer_id = str(item["id"])
    layer_name = str(item.get("name", ""))
    layer_type = str(item.get("type", "Unknown"))
    return ResolvedCopperLayer(
        layer_id=layer_id,
        layer_name=layer_name,
        layer_type=layer_type,
        input_value=value,
    )


def _validate_routing_layer(snapshot: DocumentSnapshot, layer_id: str, context: str) -> None:
    """Reject routing on plane or unknown layer types."""
    layer_type = _layer_type(snapshot, layer_id)
    if layer_type == "Plane":
        layer_name = "Unknown"
        if snapshot.board is not None:
            for item in snapshot.board.layers:
                if str(item.get("id", "")) == layer_id:
                    layer_name = str(item.get("name", "Unknown"))
                    break
        raise RoutingError(
            f"Trace routing is not supported on plane layer {layer_name!r}",
            details={"layer_id": layer_id, "layer_type": layer_type, "context": context},
        )
    if layer_type == "Unknown" and layer_id != "0":
        raise RoutingError(
            "Trace routing is not supported on layer with unknown type",
            details={"layer_id": layer_id, "layer_type": layer_type, "context": context},
        )


def require_routing_layer(resolved: ResolvedCopperLayer, context: str) -> None:
    """Validate a resolved layer is suitable for active trace routing."""
    if resolved.is_plane:
        raise RoutingError(
            f"Trace routing is not supported on plane layer {resolved.layer_name!r}",
            details={
                "layer_id": resolved.layer_id,
                "layer_type": resolved.layer_type,
                "context": context,
            },
        )
    if resolved.layer_type == "Unknown" and resolved.layer_id != "0":
        raise RoutingError(
            "Trace routing is not supported on layer with unknown type",
            details={
                "layer_id": resolved.layer_id,
                "layer_type": resolved.layer_type,
                "context": context,
            },
        )


def _validate_via_layer(snapshot: DocumentSnapshot, layer_id: str, context: str) -> None:
    """Reject via transitions that land on a plane layer.

    Less strict than _validate_routing_layer: Unknown types are allowed because
    via transition layers are just identifiers, not active routing targets.
    """
    layer_type = _layer_type(snapshot, layer_id)
    if layer_type == "Plane":
        layer_name = "Unknown"
        if snapshot.board is not None:
            for item in snapshot.board.layers:
                if str(item.get("id", "")) == layer_id:
                    layer_name = str(item.get("name", "Unknown"))
                    break
        raise RoutingError(
            f"Via transition is not supported on plane layer {layer_name!r}",
            details={"layer_id": layer_id, "layer_type": layer_type, "context": context},
        )


def require_via_layer(resolved: ResolvedCopperLayer, context: str) -> None:
    """Validate a resolved layer is suitable for via transitions."""
    if resolved.is_plane:
        raise RoutingError(
            f"Via transition is not supported on plane layer {resolved.layer_name!r}",
            details={
                "layer_id": resolved.layer_id,
                "layer_type": resolved.layer_type,
                "context": context,
            },
        )


def _via_style_id(snapshot: DocumentSnapshot, value: str) -> str:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Via operations require a PCB document")
    return select_via_style(snapshot.board, value).id


def _endpoint(
    snapshot: DocumentSnapshot, endpoint_id: str, net: ObjectRecord
) -> tuple[dict[str, str], ObjectRecord]:
    endpoint = snapshot.get_object(endpoint_id)
    if endpoint.kind != "pad" or endpoint.parent_id is None or endpoint.xml_id is None:
        raise CapabilityUnavailableError(
            "Trace endpoints currently require normalized component pads",
            object_ids=[endpoint_id],
        )
    if endpoint.net_id != net.xml_id:
        raise ConnectivityRegressionError(
            f"Pad {endpoint.label} does not belong to net {net.name}",
            details={"pad_net_id": endpoint.net_id, "target_net_id": net.xml_id},
            object_ids=[endpoint.stable_id, net.stable_id],
        )
    parent = snapshot.get_object(endpoint.parent_id)
    if parent.xml_id is None:
        raise GeometryError(
            f"Endpoint component has no XML id: {parent.stable_id}",
            object_ids=[parent.stable_id],
        )
    return {
        "Connected": "Pad",
        "Object": parent.xml_id,
        "SubObject": endpoint.xml_id,
        "Point": "-1",
    }, endpoint


def _minimum_width(document: DipTraceDocument, layer_id: str) -> float | None:
    for item in document.container.findall("./DRC/LaySizes/LaySize"):
        if item.get("Lay") == layer_id and item.get("MinTrace") is not None:
            return to_mm(float(item.get("MinTrace", "0")), document.units)
    return None


def _clearance(
    document: DipTraceDocument, layer_id: str, requested: float | None
) -> float:
    if requested is not None:
        return requested
    for item in document.container.findall("./DRC/LayClearances/LayClearance"):
        if item.get("Lay") == layer_id and item.get("TraceToTrace") is not None:
            return to_mm(float(item.get("TraceToTrace", "0")), document.units)
    routing = document.container.find("./Settings/Routing")
    if routing is not None and routing.get("TraceClearance") is not None:
        return to_mm(float(routing.get("TraceClearance", "0")), document.units)
    return 0.0


def _path(
    snapshot: DocumentSnapshot,
    points: list[TracePathPoint],
    default_layer: str,
    default_width: float,
) -> tuple[list[Point], list[str], list[float], list[str | None]]:
    geometry = [Point(item.x, item.y) for item in points]
    layers = [
        resolve_copper_layer(snapshot, item.layer or default_layer).layer_id
        for item in points[1:]
    ]
    widths = [item.width or default_width for item in points[1:]]
    via_styles = [
        _via_style_id(snapshot, item.via_style) if item.via_style else None
        for item in points[1:]
    ]
    return geometry, layers, widths, via_styles


def _validate_path(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    net: ObjectRecord,
    points: list[Point],
    layers: list[str],
    widths: list[float],
    via_styles: list[str | None],
    requested_clearance: float | None,
    *,
    exclude_trace_id: str | None = None,
    ignored_net_xml_ids: set[str | None] | None = None,
) -> None:
    if snapshot.board is None or snapshot.board.outline is None:
        raise GeometryError("Board outline is required for safe trace insertion")
    polygon = [Point(**item) for item in snapshot.board.outline.get("points", [])]
    if not all(point_in_polygon(point, polygon) for point in points):
        raise GeometryError("Trace path leaves the board outline")
    if via_styles and via_styles[-1] is not None:
        raise GeometryError("A via cannot be attached to the final trace point")
    style_by_id = {style.id: style for style in snapshot.board.via_styles}
    for index, (before, after) in enumerate(zip(layers, layers[1:], strict=False)):
        has_via = via_styles[index] is not None
        if before != after and not has_via:
            raise GeometryError(
                "Trace layer changes require a via on the transition point",
                details={"point_index": index + 1, "before": before, "after": after},
            )
        if before == after and has_via:
            raise GeometryError(
                "Via insertion must change the active trace layer",
                details={"point_index": index + 1, "layer": before},
            )
        if has_via:
            style_id = via_styles[index]
            style = style_by_id.get(style_id or "")
            if style is None:
                raise GeometryError(
                    "Trace references an unavailable via style",
                    details={"point_index": index + 1, "via_style": style_id},
                )
            validate_via_transition(snapshot.board, style, before, after)
    for layer_id, width in zip(layers, widths, strict=True):
        minimum = _minimum_width(document, layer_id)
        if minimum is not None and width + 1e-9 < minimum:
            raise GeometryError(
                f"Trace width {width:g} mm is below {minimum:g} mm on layer {layer_id}",
                details={"measured": width, "required": minimum, "units": "mm"},
            )
    for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
        if start == end:
            raise GeometryError(f"Trace segment {segment_index} has zero length")
        layer_id = layers[segment_index]
        width = widths[segment_index]
        required = _clearance(document, layer_id, requested_clearance)
        for keepout in snapshot.board.keepouts:
            if keepout.bbox is not None and segment_intersects_bbox(
                start, end, BBox(**keepout.bbox).expand(width / 2.0)
            ):
                raise GeometryError(
                    "Trace path intersects a route keepout",
                    object_ids=[keepout.stable_id],
                    details={"segment_index": segment_index},
                )
        for obstacle in [*snapshot.board.pads, *snapshot.board.vias]:
            if obstacle.bbox is None or obstacle.net_id in (
                ignored_net_xml_ids or {net.xml_id}
            ):
                continue
            exact_violation = (
                shapely_available()
                and obstacle.geometry is not None
                and line_to_shape_distance(start, end, width, obstacle.geometry)
                + 1e-9
                < required
            )
            fallback_violation = obstacle.geometry is None or not shapely_available()
            if exact_violation or (
                fallback_violation
                and segment_intersects_bbox(
                    start,
                    end,
                    BBox(**obstacle.bbox).expand(width / 2.0 + required),
                )
            ):
                raise GeometryError(
                    "Trace path violates clearance to pad or via copper",
                    object_ids=[obstacle.stable_id],
                    details={"segment_index": segment_index, "required": required},
                )
        for existing in snapshot.board.traces:
            if existing.stable_id == exclude_trace_id or existing.net_id in (
                ignored_net_xml_ids or {net.xml_id}
            ):
                continue
            existing_points = [Point(**item) for item in existing.attributes.get("points", [])]
            existing_layers = existing.attributes.get("segment_layers", [])
            existing_widths = existing.attributes.get("segment_widths_mm", [])
            for other_index, (left, right) in enumerate(
                zip(existing_points, existing_points[1:], strict=False)
            ):
                other_layer = (
                    str(existing_layers[other_index])
                    if other_index < len(existing_layers)
                    else existing.layer or ""
                )
                if other_layer != layer_id:
                    continue
                other_width = (
                    float(existing_widths[other_index])
                    if other_index < len(existing_widths)
                    else 0.0
                )
                measured = segment_distance(start, end, left, right) - (
                    width + other_width
                ) / 2.0
                if measured + 1e-9 < required:
                    raise GeometryError(
                        "Trace path violates clearance to existing copper",
                        details={
                            "segment_index": segment_index,
                            "existing_trace_id": existing.stable_id,
                            "measured": max(0.0, measured),
                            "required": required,
                            "units": "mm",
                        },
                        object_ids=[existing.stable_id],
                    )

    for segment_index, via_style in enumerate(via_styles):
        if via_style is None:
            continue
        style = style_by_id.get(via_style)
        if style is None:
            raise GeometryError(
                "Trace references an unavailable via style",
                details={"point_index": segment_index + 1, "via_style": via_style},
            )
        diameter, _hole = validate_via_geometry(style)
        span = resolve_via_span(snapshot.board, style)
        point = points[segment_index + 1]
        via_box = BBox(point.x, point.y, point.x, point.y).expand(diameter / 2.0)
        if not all(point_in_polygon(corner, polygon) for corner in _bbox_corners(via_box)):
            raise GeometryError(
                "Via copper leaves the board outline",
                details={"point_index": segment_index + 1, "diameter_mm": diameter},
            )
        required = max(
            _clearance(document, layer_id, requested_clearance) for layer_id in span
        )
        for obstacle in [*snapshot.board.pads, *snapshot.board.vias]:
            if obstacle.bbox is None or obstacle.net_id in (
                ignored_net_xml_ids or {net.xml_id}
            ):
                continue
            if via_box.expand(required).intersects(BBox(**obstacle.bbox)):
                raise GeometryError(
                    "Via violates clearance to pad or via copper",
                    object_ids=[obstacle.stable_id],
                    details={"point_index": segment_index + 1, "required": required},
                )
        for existing in snapshot.board.traces:
            if existing.stable_id == exclude_trace_id or existing.net_id in (
                ignored_net_xml_ids or {net.xml_id}
            ):
                continue
            existing_points = [Point(**item) for item in existing.attributes.get("points", [])]
            existing_layers = existing.attributes.get("segment_layers", [])
            existing_widths = existing.attributes.get("segment_widths_mm", [])
            for other_index, (left, right) in enumerate(
                zip(existing_points, existing_points[1:], strict=False)
            ):
                other_layer = (
                    str(existing_layers[other_index])
                    if other_index < len(existing_layers)
                    else existing.layer or ""
                )
                if other_layer not in span:
                    continue
                other_width = (
                    float(existing_widths[other_index])
                    if other_index < len(existing_widths)
                    else 0.0
                )
                measured = point_to_segment_distance(point, left, right) - (
                    diameter + other_width
                ) / 2.0
                if measured + 1e-9 < required:
                    raise GeometryError(
                        "Via violates clearance to existing trace copper",
                        object_ids=[existing.stable_id],
                        details={
                            "point_index": segment_index + 1,
                            "measured": max(0.0, measured),
                            "required": required,
                        },
                    )


def _bbox_corners(box: BBox) -> tuple[Point, Point, Point, Point]:
    return (
        Point(box.min_x, box.min_y),
        Point(box.min_x, box.max_y),
        Point(box.max_x, box.min_y),
        Point(box.max_x, box.max_y),
    )


def _write_points(
    document: DipTraceDocument,
    trace: ET.Element,
    points: list[Point],
    layers: list[str],
    widths: list[float],
    via_styles: list[str | None],
) -> int:
    container = trace.find("./Points")
    if container is None:
        container = ET.SubElement(trace, "Points")
    else:
        for child in list(container):
            container.remove(child)
    for point_index, point in enumerate(points):
        attributes = {
            "Id": str(point_index),
            "X": f"{from_mm(point.x, document.units):.9g}",
            "Y": f"{from_mm(point.y, document.units):.9g}",
        }
        if point_index:
            attributes.update(
                {
                    "Lay": layers[point_index - 1],
                    "Width": f"{from_mm(widths[point_index - 1], document.units):.9g}",
                    "Jumper": "0",
                    "Arc": "N",
                    "ViaStyle": via_styles[point_index - 1] or "-1",
                    "Selected": "N",
                }
            )
        ET.SubElement(container, "Point", attributes)
    return len(points) + 1


def _next_id(elements: list[ET.Element]) -> str:
    ids = [int(item.get("Id", "-1")) for item in elements if item.get("Id", "").isdigit()]
    return str(max(ids, default=-1) + 1)


def _trace_point_transition(
    snapshot: DocumentSnapshot,
    trace: ObjectRecord,
    point: ET.Element,
) -> tuple[str, str]:
    points = _element(snapshot, trace).findall("./Points/Point")
    try:
        index = points.index(point)
    except ValueError as exc:
        raise GeometryError("Via point does not belong to the selected trace") from exc
    if index == 0 or index + 1 >= len(points):
        raise GeometryError("A via transition requires incoming and outgoing trace segments")
    before = point.get("Lay")
    after = points[index + 1].get("Lay")
    if before is None or after is None:
        raise GeometryError(
            "Via transition lacks explicit incoming or outgoing segment layer",
            details={"point_index": index},
        )
    if before == after:
        raise GeometryError(
            "Via insertion must change the active trace layer",
            details={"point_index": index, "layer": before},
        )
    return before, after


def _preview(
    index: int,
    operation: RoutingOperation,
    targets: list[str],
    before: object,
    after: object,
    document: DipTraceDocument,
) -> dict[str, object]:
    return {
        "index": index,
        "kind": operation.kind,
        "target_ids": targets,
        "before": before,
        "after": after,
        "source_sha256": document.sha256,
    }


def _prune_satisfied_ratlines(document: DipTraceDocument) -> tuple[int, int]:
    """Remove ratlines made redundant by confirmed pad-to-pad trace connectivity.

    DipTrace treats ``Board/Ratlines`` as a connectivity spanning forest, not as a
    historical list of every connection emitted by schematic synchronization.  Keeping
    a ratline after its endpoints become connected can create a cycle and causes the GUI
    to discard and reinitialize the complete ratline structure on import.

    Trace-to-trace branches are left conservative here: only exported pad-to-pad trace
    endpoints participate in the union-find seed.  Existing ratlines are then retained
    in document order only when they join two previously disconnected pad groups.
    """

    ratlines = document.container.find("./Ratlines")
    if ratlines is None:
        return 0, 0

    endpoint_net: dict[tuple[str, str], str] = {}
    nets: dict[str, ET.Element] = {}
    for net in document.container.findall("./Nets/Net"):
        net_id = net.get("Id", "")
        if not net_id:
            continue
        nets[net_id] = net
        for item in net.findall("./Pads/Item"):
            endpoint_net[(item.get("Comp", ""), item.get("Pad", ""))] = net_id

    parent: dict[tuple[str, str], tuple[str, str]] = {
        endpoint: endpoint for endpoint in endpoint_net
    }

    def find(endpoint: tuple[str, str]) -> tuple[str, str]:
        root = parent[endpoint]
        while root != parent[root]:
            root = parent[root]
        while endpoint != root:
            next_endpoint = parent[endpoint]
            parent[endpoint] = root
            endpoint = next_endpoint
        return root

    def union(left: tuple[str, str], right: tuple[str, str]) -> bool:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return False
        parent[right_root] = left_root
        return True

    for net_id, net in nets.items():
        for trace in net.findall("./Traces/Trace"):
            if trace.get("Connected1") != "Pad" or trace.get("Connected2") != "Pad":
                continue
            left = (trace.get("Object1", ""), trace.get("SubObject1", ""))
            right = (trace.get("Object2", ""), trace.get("SubObject2", ""))
            if endpoint_net.get(left) == net_id and endpoint_net.get(right) == net_id:
                union(left, right)

    removed = 0
    for ratline in list(ratlines.findall("./Ratline")):
        left = (ratline.get("Comp1", ""), ratline.get("Pad1", ""))
        right = (ratline.get("Comp2", ""), ratline.get("Pad2", ""))
        left_net = endpoint_net.get(left)
        if left_net is None or left_net != endpoint_net.get(right):
            continue
        if not union(left, right):
            ratlines.remove(ratline)
            removed += 1
    renumbered = 0
    for ratline_id, ratline in enumerate(ratlines.findall("./Ratline")):
        normalized_id = str(ratline_id)
        if ratline.get("Id") != normalized_id:
            ratline.set("Id", normalized_id)
            renumbered += 1
    return removed, renumbered


def _restore_trace_ratline(document: DipTraceDocument, trace: ET.Element) -> int:
    """Restore a pad-to-pad ratline before a routed connection is removed."""

    if trace.get("Connected1") != "Pad" or trace.get("Connected2") != "Pad":
        return 0
    points = trace.findall("./Points/Point")
    if not points:
        return 0
    left = (trace.get("Object1", ""), trace.get("SubObject1", ""))
    right = (trace.get("Object2", ""), trace.get("SubObject2", ""))
    if not all((*left, *right)) or left == right:
        return 0
    ratlines = document.container.find("./Ratlines")
    if ratlines is None:
        ratlines = ET.SubElement(document.container, "Ratlines")
    existing_pairs = {
        frozenset(
            {
                (item.get("Comp1", ""), item.get("Pad1", "")),
                (item.get("Comp2", ""), item.get("Pad2", "")),
            }
        )
        for item in ratlines.findall("./Ratline")
    }
    if frozenset({left, right}) in existing_pairs:
        return 0
    ET.SubElement(
        ratlines,
        "Ratline",
        {
            "Id": _next_id(list(ratlines.findall("./Ratline"))),
            "Hidden": "N",
            "X1": points[0].get("X", "0"),
            "Y1": points[0].get("Y", "0"),
            "X2": points[-1].get("X", "0"),
            "Y2": points[-1].get("Y", "0"),
            "Comp1": left[0],
            "Pad1": left[1],
            "Comp2": right[0],
            "Pad2": right[1],
        },
    )
    return 1


def _add_trace(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddTraceOperation,
) -> tuple[dict[str, object], int, list[str]]:
    net = _ensure_net_unlocked(snapshot, _net(snapshot, operation.net))
    start_attrs, start = _endpoint(snapshot, operation.start_object_id, net)
    end_attrs, end = _endpoint(snapshot, operation.end_object_id, net)
    if start.position is None or end.position is None:
        raise CapabilityUnavailableError(
            "Endpoint positions require ratline coordinates or pattern geometry",
            object_ids=[start.stable_id, end.stable_id],
        )
    points, layers, widths, via_styles = _path(
        snapshot, operation.points, operation.layer, operation.width
    )
    # Validate that no segment is on a plane or unknown layer type.
    # Through-via spans across plane layers are allowed; active segments on
    # plane layers are not.
    for layer_id in dict.fromkeys(layers):
        resolved = resolve_copper_layer(snapshot, layer_id)
        require_routing_layer(resolved, context="add_trace")
    if distance(points[0], Point(**start.position)) > 1e-6 or distance(
        points[-1], Point(**end.position)
    ) > 1e-6:
        raise GeometryError(
            "Trace path endpoints do not match selected pad anchors",
            object_ids=[start.stable_id, end.stable_id],
        )
    _validate_path(
        document,
        snapshot,
        net,
        points,
        layers,
        widths,
        via_styles,
        operation.clearance,
    )
    trace_id, generated_id, point_patches = _insert_trace(
        document,
        snapshot,
        net,
        start_attrs,
        end_attrs,
        points,
        layers,
        widths,
        via_styles,
    )
    removed_ratlines, renumbered_ratlines = _prune_satisfied_ratlines(document)
    length = sum(
        distance(left, right) for left, right in zip(points, points[1:], strict=False)
    )
    return (
        _preview(
            index,
            operation,
            [net.stable_id, start.stable_id, end.stable_id],
            {"trace_count": net.attributes.get("trace_count", 0)},
            {
                "trace_id": generated_id,
                "xml_id": trace_id,
                "length_mm": length,
                "removed_ratline_count": removed_ratlines,
                "renumbered_ratline_count": renumbered_ratlines,
            },
            document,
        ),
        1 + point_patches + removed_ratlines + renumbered_ratlines,
        [net.stable_id, generated_id],
    )


def _insert_trace(
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    net: ObjectRecord,
    start_attrs: dict[str, str],
    end_attrs: dict[str, str],
    points: list[Point],
    layers: list[str],
    widths: list[float],
    via_styles: list[str | None],
) -> tuple[str, str, int]:
    net_element = _element(snapshot, net)
    traces = net_element.find("./Traces")
    if traces is None:
        traces = ET.SubElement(net_element, "Traces")
    trace_id = _next_id(list(traces.findall("./Trace")))
    attributes = {
        "Id": trace_id,
        **{f"{key}1": value for key, value in start_attrs.items()},
        **{f"{key}2": value for key, value in end_attrs.items()},
        "Group": "-1",
        "PairSeparateTrace": "-1",
        "Selected": "N",
    }
    trace_element = ET.SubElement(traces, "Trace", attributes)
    point_patches = _write_points(
        document, trace_element, points, layers, widths, via_styles
    )
    generated_id = stable_id("trace", document.source_type, net.stable_id, f"xml:{trace_id}")
    return trace_id, generated_id, point_patches


def _add_differential_pair_route(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddDifferentialPairRouteOperation,
) -> tuple[dict[str, object], int, list[str]]:
    if snapshot.board is None:
        raise CapabilityUnavailableError("Differential-pair routing requires a PCB document")
    pairs = [
        item
        for item in snapshot.board.differential_pairs
        if item.stable_id == operation.pair
        or item.xml_id == operation.pair
        or item.name.casefold() == operation.pair.casefold()
    ]
    if len(pairs) != 1:
        raise ObjectNotFoundError(f"Unique differential pair was not found: {operation.pair}")
    pair = pairs[0]
    positive_net = _ensure_net_unlocked(snapshot, _net(snapshot, operation.positive_net))
    negative_net = _ensure_net_unlocked(snapshot, _net(snapshot, operation.negative_net))
    expected_nets = {pair.positive_net_xml_id, pair.negative_net_xml_id}
    if {positive_net.xml_id, negative_net.xml_id} != expected_nets:
        raise ConnectivityRegressionError(
            "Operation nets do not match the selected differential pair",
            object_ids=[pair.stable_id, positive_net.stable_id, negative_net.stable_id],
        )
    positive_start_attrs, positive_start = _endpoint(
        snapshot, operation.positive_start_object_id, positive_net
    )
    positive_end_attrs, positive_end = _endpoint(
        snapshot, operation.positive_end_object_id, positive_net
    )
    negative_start_attrs, negative_start = _endpoint(
        snapshot, operation.negative_start_object_id, negative_net
    )
    negative_end_attrs, negative_end = _endpoint(
        snapshot, operation.negative_end_object_id, negative_net
    )
    positive = _path(snapshot, operation.positive_points, operation.layer, operation.width)
    negative = _path(snapshot, operation.negative_points, operation.layer, operation.width)
    # Validate that no segment is on a plane or unknown layer type.
    for points_path in (positive, negative):
        for layer_id in dict.fromkeys(points_path[1]):
            resolved = resolve_copper_layer(snapshot, layer_id)
            require_routing_layer(resolved, context="diff_pair_route")
    for points, start, end in (
        (positive[0], positive_start, positive_end),
        (negative[0], negative_start, negative_end),
    ):
        if start.position is None or end.position is None:
            raise CapabilityUnavailableError(
                "Differential-pair endpoint positions are unavailable",
                object_ids=[start.stable_id, end.stable_id],
            )
        if distance(points[0], Point(**start.position)) > 1e-6 or distance(
            points[-1], Point(**end.position)
        ) > 1e-6:
            raise GeometryError(
                "Differential-pair path endpoints do not match selected pads",
                object_ids=[start.stable_id, end.stable_id],
            )
    ignored_nets = {positive_net.xml_id, negative_net.xml_id}
    _validate_path(
        document,
        snapshot,
        positive_net,
        *positive,
        operation.clearance,
        ignored_net_xml_ids=ignored_nets,
    )
    _validate_path(
        document,
        snapshot,
        negative_net,
        *negative,
        operation.clearance,
        ignored_net_xml_ids=ignored_nets,
    )
    pair_element = next(
        (
            item
            for item in document.container.findall("./DifferentialPairs/DifferentialPair")
            if item.get("Id") == pair.xml_id
        ),
        None,
    )
    if pair_element is None:
        raise ObjectNotFoundError(
            "Differential-pair XML element is unavailable", object_ids=[pair.stable_id]
        )
    pad_point_ids = {
        item.get("Id", "") for item in pair_element.findall("./PadPoints/PadPoint")
    }
    if not {operation.start_pad_point_id, operation.end_pad_point_id} <= pad_point_ids:
        raise GeometryError(
            "Differential-pair PadPoint references are invalid",
            details={"available_pad_point_ids": sorted(pad_point_ids)},
        )
    segments = pair_element.find("./Segments")
    if segments is None:
        segments = ET.SubElement(pair_element, "Segments")
    for segment in segments.findall("./Segment"):
        existing = {segment.get("StartPoint"), segment.get("EndPoint")}
        if existing == {operation.start_pad_point_id, operation.end_pad_point_id}:
            raise ConnectivityRegressionError(
                "A differential-pair segment already connects these PadPoints",
                object_ids=[pair.stable_id],
            )
    positive_trace_id, positive_generated_id, positive_patches = _insert_trace(
        document,
        snapshot,
        positive_net,
        positive_start_attrs,
        positive_end_attrs,
        *positive,
    )
    negative_trace_id, negative_generated_id, negative_patches = _insert_trace(
        document,
        snapshot,
        negative_net,
        negative_start_attrs,
        negative_end_attrs,
        *negative,
    )
    segment = ET.SubElement(
        segments,
        "Segment",
        {
            "PosTrace": positive_trace_id,
            "NegTrace": negative_trace_id,
            "StartPoint": operation.start_pad_point_id,
            "EndPoint": operation.end_pad_point_id,
            "StartSegment": "-1",
            "EndSegment": "-1",
        },
    )
    center_points = ET.SubElement(segment, "CenterPoints")
    for center in operation.center_points:
        resolved_center = resolve_copper_layer(snapshot, center.layer)
        layer_id = resolved_center.layer_id
        via_style = _via_style_id(snapshot, center.via_style) if center.via_style else "-1"
        center_element = ET.SubElement(
            center_points,
            "CenterPoint",
            {
                "X": f"{from_mm(center.x, document.units):.9g}",
                "Y": f"{from_mm(center.y, document.units):.9g}",
                "Lay": layer_id,
                "ViaStyle": via_style,
                "Type": "Paired",
                "Necked": "N",
                "Selected": "N",
                "PhaseError": "N",
            },
        )
        for tag, item_tag, dx, dy in (
            ("PosPoints", "PosPoint", center.positive_dx, center.positive_dy),
            ("NegPoints", "NegPoint", center.negative_dx, center.negative_dy),
        ):
            container = ET.SubElement(center_element, tag)
            ET.SubElement(
                container,
                item_tag,
                {
                    "X": f"{from_mm(dx, document.units):.9g}",
                    "Y": f"{from_mm(dy, document.units):.9g}",
                    "Lay": layer_id,
                    "ViaStyle": via_style,
                    "Necked": "N",
                    "Arc": "N",
                },
            )
    changed = [
        pair.stable_id,
        positive_net.stable_id,
        negative_net.stable_id,
        positive_generated_id,
        negative_generated_id,
    ]
    preview = _preview(
        index,
        operation,
        changed,
        {"segment_count": len(pair.segments)},
        {
            "positive_trace_id": positive_generated_id,
            "negative_trace_id": negative_generated_id,
            "center_point_count": len(operation.center_points),
        },
        document,
    )
    patches = positive_patches + negative_patches + len(operation.center_points) * 3 + 5
    return preview, patches, changed


def _replace_trace(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: ReplaceTraceOperation,
) -> tuple[dict[str, object], int, list[str]]:
    trace = _trace(snapshot, operation.trace_id)
    net = _ensure_net_unlocked(snapshot, trace)
    points, layers, widths, via_styles = _path(
        snapshot, operation.points, operation.layer, operation.width
    )
    # Validate that no segment is on a plane or unknown layer type.
    for layer_id in dict.fromkeys(layers):
        resolved = resolve_copper_layer(snapshot, layer_id)
        require_routing_layer(resolved, context="replace_trace")
    previous = [Point(**item) for item in trace.attributes.get("points", [])]
    if len(previous) < 2 or points[0] != previous[0] or points[-1] != previous[-1]:
        raise ConnectivityRegressionError(
            "replace_trace must preserve both existing endpoints",
            object_ids=[trace.stable_id],
        )
    _validate_path(
        document,
        snapshot,
        net,
        points,
        layers,
        widths,
        via_styles,
        operation.clearance,
        exclude_trace_id=trace.stable_id,
    )
    patches = _write_points(
        document, _element(snapshot, trace), points, layers, widths, via_styles
    )
    return (
        _preview(
            index,
            operation,
            [trace.stable_id],
            {"points": [point.as_dict() for point in previous]},
            {"points": [point.as_dict() for point in points]},
            document,
        ),
        patches,
        [trace.stable_id],
    )


def _delete_traces(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: DeleteTraceOperation,
) -> tuple[dict[str, object], int, list[str]]:
    traces = _select(snapshot, operation.selector, "trace")
    grouped: dict[str, list[ObjectRecord]] = {}
    for trace in traces:
        _ensure_net_unlocked(snapshot, trace)
        grouped.setdefault(trace.parent_id or "", []).append(trace)
    if not operation.allow_connectivity_regression:
        for net_id, selected in grouped.items():
            net = snapshot.get_object(net_id)
            if int(net.attributes.get("endpoint_count", 0)) > 1 and len(selected) >= int(
                net.attributes.get("trace_count", 0)
            ):
                raise ConnectivityRegressionError(
                    f"Deleting traces would leave net {net.name} unrouted",
                    object_ids=[net.stable_id, *[trace.stable_id for trace in selected]],
                )
    before: list[dict[str, str | None]] = []
    ratline_patches = 0
    for trace in traces:
        net = snapshot.get_object(trace.parent_id or "")
        container = _element(snapshot, net).find("./Traces")
        if container is None:
            raise GeometryError(f"Trace container is missing: {trace.stable_id}")
        trace_element = _element(snapshot, trace)
        ratline_patches += _restore_trace_ratline(document, trace_element)
        container.remove(trace_element)
        before.append({"id": trace.stable_id, "xml_id": trace.xml_id})
    removed_ratlines, renumbered_ratlines = _prune_satisfied_ratlines(document)
    ratline_patches += removed_ratlines + renumbered_ratlines
    ids = [trace.stable_id for trace in traces]
    return (
        _preview(index, operation, ids, before, [], document),
        len(ids) + ratline_patches,
        ids,
    )


def _set_trace_width(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetTraceWidthOperation,
) -> tuple[dict[str, object], int, list[str]]:
    traces = _select(snapshot, operation.selector, "trace")
    before: list[dict[str, object]] = []
    patches = 0
    for trace in traces:
        _ensure_net_unlocked(snapshot, trace)
        points = _element(snapshot, trace).findall("./Points/Point")[1:]
        selected = operation.segment_indices or list(range(len(points)))
        if any(item >= len(points) for item in selected):
            raise GeometryError(
                f"Trace segment index is out of range: {trace.stable_id}",
                details={"segment_count": len(points), "requested": selected},
            )
        previous: dict[int, float] = {}
        for segment_index in selected:
            point = points[segment_index]
            minimum = _minimum_width(document, point.get("Lay", ""))
            if minimum is not None and operation.width + 1e-9 < minimum:
                raise GeometryError(
                    "Trace width is below the DRC minimum",
                    details={"measured": operation.width, "required": minimum},
                )
            previous[segment_index] = to_mm(float(point.get("Width", "0")), document.units)
            point.set("Width", f"{from_mm(operation.width, document.units):.9g}")
            patches += 1
        before.append({"id": trace.stable_id, "segment_widths": previous})
    ids = [trace.stable_id for trace in traces]
    return (
        _preview(
            index,
            operation,
            ids,
            before,
            {"width_mm": operation.width, "segment_indices": operation.segment_indices},
            document,
        ),
        patches,
        ids,
    )


def _add_via(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: AddViaOperation,
) -> tuple[dict[str, object], int, list[str]]:
    trace = _trace(snapshot, operation.trace_id)
    _ensure_net_unlocked(snapshot, trace)
    if snapshot.board is None:
        raise CapabilityUnavailableError("Via operations require a PCB document")
    style = select_via_style(snapshot.board, operation.via_style)
    validate_via_geometry(style)
    style_id = style.id
    container = _element(snapshot, trace).find("./Points")
    if container is None:
        raise GeometryError(f"Trace has no points: {trace.stable_id}")
    elements = container.findall("./Point")
    points = [
        Point(
            to_mm(float(item.get("X", "0")), document.units),
            to_mm(float(item.get("Y", "0")), document.units),
        )
        for item in elements
    ]
    target = Point(operation.x, operation.y)
    existing = next(
        (item for item, point in enumerate(points) if distance(point, target) <= 1e-6),
        None,
    )
    inserted = False
    if existing is not None:
        if existing == 0:
            raise GeometryError("A via cannot be encoded on the first ignored trace point")
        via_point = elements[existing]
    else:
        segment = next(
            (
                item
                for item, (start, end) in enumerate(zip(points, points[1:], strict=False))
                if point_to_segment_distance(target, start, end) <= 1e-6
                and min(start.x, end.x) - 1e-6 <= target.x <= max(start.x, end.x) + 1e-6
                and min(start.y, end.y) - 1e-6 <= target.y <= max(start.y, end.y) + 1e-6
            ),
            None,
        )
        if segment is None:
            raise GeometryError("Via position is not on the selected trace")
        next_point = elements[segment + 1]
        attributes = dict(next_point.attrib)
        attributes.update(
            {
                "Id": _next_id(elements),
                "X": f"{from_mm(target.x, document.units):.9g}",
                "Y": f"{from_mm(target.y, document.units):.9g}",
            }
        )
        via_point = ET.Element("Point", attributes)
        container.insert(segment + 1, via_point)
        inserted = True
    previous = via_point.get("ViaStyle", "-1")
    via_point.set("ViaStyle", style_id)
    if operation.layer_before is not None:
        resolved_before = resolve_copper_layer(snapshot, operation.layer_before)
        require_via_layer(resolved_before, context="add_via_layer_before")
        via_point.set("Lay", resolved_before.layer_id)
    if operation.layer_after is not None:
        resolved_after = resolve_copper_layer(snapshot, operation.layer_after)
        require_via_layer(resolved_after, context="add_via_layer_after")
        updated_points = container.findall("./Point")
        via_index = updated_points.index(via_point)
        if via_index + 1 >= len(updated_points):
            raise GeometryError("A via cannot be attached to the final trace point")
        updated_points[via_index + 1].set(
            "Lay", resolved_after.layer_id
        )
    before_layer, after_layer = _trace_point_transition(snapshot, trace, via_point)
    validate_via_transition(snapshot.board, style, before_layer, after_layer)
    return (
        _preview(
            index,
            operation,
            [trace.stable_id],
            {"position": target.as_dict(), "via_style": previous},
            {
                "position": target.as_dict(),
                "via_style": style_id,
                "inserted_point": inserted,
            },
            document,
        ),
        2 if inserted else 1,
        [trace.stable_id],
    )


def _move_vias(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: MoveViaOperation,
) -> tuple[dict[str, object], int, list[str]]:
    vias = _select(snapshot, operation.selector, "via")
    before: list[dict[str, object]] = []
    after: list[dict[str, object]] = []
    for via in vias:
        _ensure_net_unlocked(snapshot, snapshot.get_object(via.parent_id or ""))
        if via.position is None:
            raise GeometryError(f"Via has no position: {via.stable_id}")
        point = Point(**via.position)
        moved = Point(
            operation.absolute_x if operation.absolute_x is not None else point.x + operation.dx,
            operation.absolute_y if operation.absolute_y is not None else point.y + operation.dy,
        )
        element = _element(snapshot, via)
        element.set("X", f"{from_mm(moved.x, document.units):.9g}")
        element.set("Y", f"{from_mm(moved.y, document.units):.9g}")
        before.append({"id": via.stable_id, "position": point.as_dict()})
        after.append({"id": via.stable_id, "position": moved.as_dict()})
    ids = [via.stable_id for via in vias]
    return _preview(index, operation, ids, before, after, document), 2 * len(vias), ids


def _delete_vias(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: DeleteViaOperation,
) -> tuple[dict[str, object], int, list[str]]:
    vias = _select(snapshot, operation.selector, "via")
    before: list[dict[str, str]] = []
    for via in vias:
        if via.attributes.get("representation") == "static_component":
            raise CapabilityUnavailableError(
                "delete_via currently supports routed trace transitions, not static vias"
            )
        trace = snapshot.get_object(via.parent_id or "")
        _ensure_net_unlocked(snapshot, trace)
        element = _element(snapshot, via)
        before.append({"id": via.stable_id, "via_style": element.get("ViaStyle", "-1")})
        points = _element(snapshot, trace).findall("./Points/Point")
        try:
            point_index = points.index(element)
        except ValueError as exc:
            raise GeometryError("Via point does not belong to its parent trace") from exc
        if point_index + 1 >= len(points) or element.get("Lay") is None:
            raise GeometryError("Via deletion requires an explicit following trace segment")
        # Removing the transition keeps the outgoing segment on the incoming layer. If the
        # following point carries another ViaStyle, that point becomes the next real transition.
        points[point_index + 1].set("Lay", str(element.get("Lay")))
        element.set("ViaStyle", "-1")
    ids = [via.stable_id for via in vias]
    return _preview(index, operation, ids, before, [], document), 2 * len(vias), ids


def _set_via_style(
    index: int,
    document: DipTraceDocument,
    snapshot: DocumentSnapshot,
    operation: SetViaStyleOperation,
) -> tuple[dict[str, object], int, list[str]]:
    vias = _select(snapshot, operation.selector, "via")
    if snapshot.board is None:
        raise CapabilityUnavailableError("Via operations require a PCB document")
    style = select_via_style(snapshot.board, operation.via_style)
    validate_via_geometry(style)
    style_id = style.id
    before: list[dict[str, str]] = []
    for via in vias:
        trace = snapshot.get_object(via.parent_id or "")
        _ensure_net_unlocked(snapshot, trace)
        element = _element(snapshot, via)
        layer_before, layer_after = _trace_point_transition(snapshot, trace, element)
        validate_via_transition(snapshot.board, style, layer_before, layer_after)
        before.append({"id": via.stable_id, "via_style": element.get("ViaStyle", "-1")})
        element.set("ViaStyle", style_id)
    ids = [via.stable_id for via in vias]
    return (
        _preview(index, operation, ids, before, {"via_style": style_id}, document),
        len(vias),
        ids,
    )
