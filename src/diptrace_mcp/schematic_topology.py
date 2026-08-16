from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass

from .adapters import DocumentSnapshot
from .errors import CapabilityUnavailableError
from .geometry import Point, distance
from .schematic_pin_geometry import SchematicPinGeometryResolution

_POINT_DIGITS = 6

NodeKey = tuple[float, float]


@dataclass(frozen=True, slots=True)
class ProvenSchematicTopology:
    """A sheet-local wire graph proven from literal existing wire geometry.

    Only acyclic connected branched graphs are considered reconstructable. This is
    deliberately conservative: ambiguous cycles, free leaves and endpoint mappings
    are refused rather than silently rewritten into an MST.
    """

    node_points: dict[NodeKey, Point]
    adjacency: dict[NodeKey, frozenset[NodeKey]]
    pin_nodes: dict[str, NodeKey]
    junction_nodes: frozenset[NodeKey]
    wire_ids: tuple[str, ...]

    @property
    def edge_count(self) -> int:
        return sum(len(value) for value in self.adjacency.values()) // 2

    @property
    def node_count(self) -> int:
        return len(self.node_points)


def _key(point: Point) -> NodeKey:
    return (round(point.x, _POINT_DIGITS), round(point.y, _POINT_DIGITS))


def _wire_points(raw: object) -> list[Point]:
    if not isinstance(raw, list):
        return []
    points: list[Point] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            points.append(Point(float(item["x"]), float(item["y"])))
        except (KeyError, TypeError, ValueError):
            return []
    return points


def _connected(adjacency: dict[NodeKey, set[NodeKey]]) -> bool:
    if not adjacency:
        return False
    first = next(iter(adjacency))
    visited = {first}
    queue: deque[NodeKey] = deque([first])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited == set(adjacency)


def _nearest_node(
    point: Point,
    node_points: dict[NodeKey, Point],
    tolerance_mm: float,
) -> NodeKey | None:
    matches = sorted(
        (
            (distance(point, candidate), key)
            for key, candidate in node_points.items()
            if distance(point, candidate) <= tolerance_mm
        ),
        key=lambda item: (item[0], item[1]),
    )
    if not matches:
        return None
    if len(matches) > 1 and abs(matches[0][0] - matches[1][0]) <= 1e-9:
        return None
    return matches[0][1]


def build_proven_schematic_topology(
    snapshot: DocumentSnapshot,
    wire_ids: Iterable[str],
    pin_geometry: SchematicPinGeometryResolution,
    *,
    match_tolerance_mm: float = 0.5,
) -> ProvenSchematicTopology | None:
    """Extract an unambiguous existing wire tree and bind exact pin endpoints.

    ``None`` means the selected geometry contains no intentional branch node and the
    caller may use its ordinary two-terminal routing path. Branched graphs fail closed
    if they are cyclic, disconnected, malformed, contain unattributed leaves, or
    cannot be bound one-to-one to resolved pin coordinates.
    """

    if snapshot.schematic is None:
        raise CapabilityUnavailableError(
            "Schematic topology requires a schematic snapshot"
        )
    selected_ids = tuple(sorted(set(wire_ids)))
    selected = [
        wire for wire in snapshot.schematic.wires if wire.stable_id in selected_ids
    ]
    if not selected:
        return None

    node_points: dict[NodeKey, Point] = {}
    adjacency_mutable: dict[NodeKey, set[NodeKey]] = defaultdict(set)
    for wire in selected:
        points = _wire_points(wire.attributes.get("points"))
        if len(points) < 2:
            raise CapabilityUnavailableError(
                f"Existing wire {wire.stable_id} lacks complete point geometry"
            )
        for point in points:
            node_points.setdefault(_key(point), point)
            adjacency_mutable.setdefault(_key(point), set())
        for first, second in zip(points, points[1:], strict=False):
            first_key = _key(first)
            second_key = _key(second)
            if first_key == second_key:
                continue
            adjacency_mutable[first_key].add(second_key)
            adjacency_mutable[second_key].add(first_key)

    junction_nodes = frozenset(
        node for node, neighbors in adjacency_mutable.items() if len(neighbors) >= 3
    )
    if not junction_nodes:
        return None
    if not _connected(adjacency_mutable):
        raise CapabilityUnavailableError(
            "Existing branched schematic topology is disconnected or ambiguous"
        )
    edge_count = sum(len(value) for value in adjacency_mutable.values()) // 2
    if edge_count != len(adjacency_mutable) - 1:
        raise CapabilityUnavailableError(
            "Existing branched schematic topology contains a cycle; atomic reroute "
            "refuses it"
        )

    resolved_by_pin = {
        item.pin_id: Point(**item.absolute_position)
        for item in pin_geometry.pins
        if item.absolute_position is not None
    }
    pin_nodes: dict[str, NodeKey] = {}
    node_pins: dict[NodeKey, list[str]] = defaultdict(list)
    for pin in snapshot.schematic.pins:
        resolved_point = resolved_by_pin.get(pin.stable_id)
        if resolved_point is None:
            continue
        node = _nearest_node(resolved_point, node_points, match_tolerance_mm)
        if node is not None:
            pin_nodes[pin.stable_id] = node
            node_pins[node].append(pin.stable_id)

    ambiguous_nodes = {
        node: sorted(pin_ids)
        for node, pin_ids in node_pins.items()
        if len(pin_ids) > 1
    }
    if ambiguous_nodes:
        raise CapabilityUnavailableError(
            "Branched schematic topology maps multiple pins to one graph node; "
            "atomic reroute refuses ambiguous endpoint ownership"
        )

    # Every leaf in an authored wire tree must be attributable to exactly one pin.
    # A free leaf may encode an implicit/manual construct we cannot safely preserve.
    leaves = {
        node for node, neighbors in adjacency_mutable.items() if len(neighbors) == 1
    }
    bound_nodes = set(pin_nodes.values())
    if not leaves.issubset(bound_nodes):
        raise CapabilityUnavailableError(
            "Branched schematic topology has an unbound/free leaf; atomic reroute "
            "refuses it"
        )

    return ProvenSchematicTopology(
        node_points=node_points,
        adjacency={
            key: frozenset(value) for key, value in adjacency_mutable.items()
        },
        pin_nodes=pin_nodes,
        junction_nodes=junction_nodes,
        wire_ids=selected_ids,
    )


def topology_junction_path(
    topology: ProvenSchematicTopology,
    start_pin_id: str,
    end_pin_id: str,
) -> list[Point]:
    """Return every proven junction on the unique original pin-to-pin tree path."""

    try:
        start = topology.pin_nodes[start_pin_id]
        end = topology.pin_nodes[end_pin_id]
    except KeyError as exc:
        raise CapabilityUnavailableError(
            "Branched schematic topology cannot bind an affected pin to the original "
            "graph"
        ) from exc

    parent: dict[NodeKey, NodeKey | None] = {start: None}
    queue: deque[NodeKey] = deque([start])
    while queue and end not in parent:
        node = queue.popleft()
        for neighbor in sorted(topology.adjacency[node]):
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    if end not in parent:
        raise CapabilityUnavailableError(
            "Affected pins are disconnected in the proven original schematic topology"
        )

    path: list[NodeKey] = []
    current: NodeKey | None = end
    while current is not None:
        path.append(current)
        current = parent[current]
    path.reverse()
    return [
        topology.node_points[node]
        for node in path[1:-1]
        if node in topology.junction_nodes
    ]
