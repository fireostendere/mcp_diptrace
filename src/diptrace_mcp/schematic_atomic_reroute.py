from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import DocumentSnapshot, build_snapshot
from .domain import QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import Point
from .operations import (
    AddWireOperation,
    DeleteWireOperation,
    MoveComponentsOperation,
    SemanticOperation,
    WireEndpoint,
)
from .schematic_joint_optimizer import (
    _append_completed_net_routes,
    _initial_points,
    _mst_endpoint_edges,
    _net_names,
    _virtual_endpoints,
    _virtualize_snapshot,
)
from .schematic_optimizer import SchematicPlacementCandidate
from .schematic_pin_geometry import (
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .schematic_wire_planner import SchematicWirePlannerConfig, plan_schematic_wire_candidate
from .xml_document import DipTraceDocument

_EPS = 1e-9


class SchematicAtomicRerouteConfig(StrictModel):
    """Bounds and policy for one placement + affected-wire replacement transaction."""

    max_moved_parts: int = Field(default=256, ge=1, le=10_000)
    max_affected_net_groups: int = Field(default=256, ge=1, le=10_000)
    max_deleted_wires: int = Field(default=2_048, ge=1, le=50_000)
    max_added_wires: int = Field(default=2_048, ge=1, le=50_000)
    include_unwired_affected_nets: bool = False
    wire_planner: SchematicWirePlannerConfig = Field(default_factory=SchematicWirePlannerConfig)


class SchematicAffectedNetGroup(StrictModel):
    net_id: str
    net_name: str
    sheet: int = Field(ge=0)
    moved_part_ids: list[str] = Field(default_factory=list)
    pin_ids: list[str] = Field(default_factory=list)
    deleted_wire_ids: list[str] = Field(default_factory=list)
    replacement_edge_count: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class SchematicAtomicReroutePlan:
    """Typed, non-mutating plan ready for the existing semantic transaction path."""

    operations: list[SemanticOperation]
    moved_part_ids: list[str]
    deleted_wire_ids: list[str]
    added_wire_count: int
    affected_net_groups: list[SchematicAffectedNetGroup]
    warnings: list[str]
    limitations: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "operations": [item.model_dump(mode="json") for item in self.operations],
            "moved_part_ids": list(self.moved_part_ids),
            "deleted_wire_ids": list(self.deleted_wire_ids),
            "added_wire_count": self.added_wire_count,
            "affected_net_groups": [
                item.model_dump(mode="json") for item in self.affected_net_groups
            ],
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def _part_sheet(snapshot: DocumentSnapshot, part_id: str) -> int | None:
    assert snapshot.schematic is not None
    part = next(
        (item for item in snapshot.schematic.parts if item.stable_id == part_id),
        None,
    )
    if part is None:
        return None
    try:
        value = int(str(part.attributes.get("sheet", "0")))
    except ValueError:
        return None
    return value if value >= 0 else None


def _wire_sheet(wire: Any) -> int | None:
    try:
        value = int(str(wire.attributes.get("sheet", "0")))
    except (AttributeError, ValueError):
        return None
    return value if value >= 0 else None


def _moved_parts(
    snapshot: DocumentSnapshot,
    candidate: SchematicPlacementCandidate,
) -> tuple[list[str], list[MoveComponentsOperation]]:
    assert snapshot.schematic is not None
    parts = {item.stable_id: item for item in snapshot.schematic.parts}
    moved: list[str] = []
    operations: list[MoveComponentsOperation] = []
    for part_id, raw in sorted(candidate.placements.items()):
        part = parts.get(part_id)
        if part is None:
            raise CapabilityUnavailableError(
                f"Placement candidate references missing schematic part {part_id}"
            )
        if part.position is None:
            raise CapabilityUnavailableError(
                f"Schematic part {part_id} has no source position for atomic reroute"
            )
        target = Point(float(raw["x"]), float(raw["y"]))
        current = Point(**part.position)
        if math.isclose(current.x, target.x, abs_tol=_EPS) and math.isclose(
            current.y, target.y, abs_tol=_EPS
        ):
            continue
        if part.locked:
            raise CapabilityUnavailableError(
                f"Atomic schematic reroute refuses to move locked part {part_id}"
            )
        moved.append(part_id)
        operations.append(
            MoveComponentsOperation(
                selector=QuerySelector(ids=[part_id]),
                absolute_x=target.x,
                absolute_y=target.y,
            )
        )
    return moved, operations


def _affected_groups(
    snapshot: DocumentSnapshot,
    moved_part_ids: list[str],
    *,
    include_unwired: bool,
) -> dict[tuple[str, int], dict[str, Any]]:
    assert snapshot.schematic is not None
    moved = set(moved_part_ids)
    existing_by_group: dict[tuple[str, int], list[str]] = {}
    for wire in snapshot.schematic.wires:
        if wire.net_id is None:
            continue
        sheet = _wire_sheet(wire)
        if sheet is None:
            continue
        existing_by_group.setdefault((wire.net_id, sheet), []).append(wire.stable_id)

    groups: dict[tuple[str, int], dict[str, Any]] = {}
    parts = {item.stable_id: item for item in snapshot.schematic.parts}
    for pin in snapshot.schematic.pins:
        if pin.parent_id not in moved or pin.net_id is None:
            continue
        part = parts.get(pin.parent_id)
        if part is None:
            continue
        sheet = _part_sheet(snapshot, part.stable_id)
        if sheet is None:
            raise CapabilityUnavailableError(
                f"Part {part.stable_id} has an invalid sheet index"
            )
        key = (pin.net_id, sheet)
        if not include_unwired and not existing_by_group.get(key):
            continue
        group = groups.setdefault(
            key,
            {
                "moved_part_ids": set(),
                "deleted_wire_ids": list(existing_by_group.get(key, [])),
            },
        )
        group["moved_part_ids"].add(part.stable_id)
    return groups


def _remove_affected_wires(
    snapshot: DocumentSnapshot,
    affected: set[tuple[str, int]],
) -> None:
    if snapshot.schematic is None:
        return
    removed = {
        wire.stable_id
        for wire in snapshot.schematic.wires
        if wire.net_id is not None
        and _wire_sheet(wire) is not None
        and (wire.net_id, int(_wire_sheet(wire))) in affected
    }
    snapshot.schematic.wires = [
        wire for wire in snapshot.schematic.wires if wire.stable_id not in removed
    ]
    for stable_id in removed:
        snapshot.objects.pop(stable_id, None)


def plan_atomic_schematic_placement_reroute(
    document: DipTraceDocument,
    candidate: SchematicPlacementCandidate,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicAtomicRerouteConfig | None = None,
) -> SchematicAtomicReroutePlan:
    """Plan one all-or-nothing placement and selective affected-net reroute.

    The function is deliberately non-mutating.  It returns ordinary semantic operations in
    dependency-safe order: delete affected wire geometry, move parts, then author replacement
    wires.  Passing the complete list to the existing semantic-operations transaction path keeps
    the placement and reroute atomic under the same SHA/preview/commit boundary.
    """

    config = config or SchematicAtomicRerouteConfig()
    snapshot = build_snapshot(document)
    if snapshot.schematic is None:
        raise CapabilityUnavailableError(
            "Atomic schematic placement/reroute requires a schematic document"
        )

    moved_part_ids, move_operations = _moved_parts(snapshot, candidate)
    if not moved_part_ids:
        return SchematicAtomicReroutePlan(
            operations=[],
            moved_part_ids=[],
            deleted_wire_ids=[],
            added_wire_count=0,
            affected_net_groups=[],
            warnings=["Placement candidate does not move any schematic part."],
            limitations=[],
        )
    if len(moved_part_ids) > config.max_moved_parts:
        raise CapabilityUnavailableError(
            f"Atomic reroute moved-part count exceeds {config.max_moved_parts}"
        )

    group_state = _affected_groups(
        snapshot,
        moved_part_ids,
        include_unwired=config.include_unwired_affected_nets,
    )
    if len(group_state) > config.max_affected_net_groups:
        raise CapabilityUnavailableError(
            "Atomic reroute affected-net-group count exceeds the configured bound"
        )

    deleted_wire_ids = sorted(
        {
            wire_id
            for state in group_state.values()
            for wire_id in state["deleted_wire_ids"]
        }
    )
    if len(deleted_wire_ids) > config.max_deleted_wires:
        raise CapabilityUnavailableError(
            f"Atomic reroute would replace more than {config.max_deleted_wires} wires"
        )

    delete_operations: list[SemanticOperation] = [
        DeleteWireOperation(selector=QuerySelector(ids=[wire_id]))
        for wire_id in deleted_wire_ids
    ]
    if not group_state:
        return SchematicAtomicReroutePlan(
            operations=[*move_operations],
            moved_part_ids=moved_part_ids,
            deleted_wire_ids=[],
            added_wire_count=0,
            affected_net_groups=[],
            warnings=[
                "Moved parts touch no explicit wire geometry under the current selective-reroute policy."
            ],
            limitations=[
                "Unwired affected nets are preserved as connectivity-only nets unless "
                "include_unwired_affected_nets is enabled."
            ],
        )

    pin_geometry = pin_geometry or resolve_document_schematic_pin_geometry(document)
    virtual, virtualization_warnings = _virtualize_snapshot(snapshot, candidate.placements)
    affected_keys = set(group_state)
    _remove_affected_wires(virtual, affected_keys)
    endpoint_groups, endpoint_warnings = _virtual_endpoints(snapshot, virtual, pin_geometry)
    net_names = _net_names(snapshot)

    add_operations: list[SemanticOperation] = []
    reports: list[SchematicAffectedNetGroup] = []
    warnings = [*virtualization_warnings, *endpoint_warnings, *pin_geometry.warnings]

    for net_id, sheet in sorted(affected_keys):
        endpoints = endpoint_groups.get((net_id, sheet), [])
        if len(endpoints) < 2:
            raise CapabilityUnavailableError(
                f"Affected net {net_names.get(net_id, net_id)!r} on sheet {sheet} "
                "does not have at least two resolvable endpoints; refusing destructive reroute"
            )
        edges = _mst_endpoint_edges(endpoints)
        if len(add_operations) + len(edges) > config.max_added_wires:
            raise CapabilityUnavailableError(
                f"Atomic reroute would author more than {config.max_added_wires} wires"
            )
        net_name = net_names.get(net_id, net_id)
        group_plans = []
        for start, end in edges:
            operation = AddWireOperation(
                net=net_name,
                sheet=sheet,
                points=_initial_points(start.point, end.point),
                start=WireEndpoint(
                    type="Pin",
                    part_id=start.part.stable_id,
                    pin=start.pin_index,
                ),
                end=WireEndpoint(
                    type="Pin",
                    part_id=end.part.stable_id,
                    pin=end.pin_index,
                ),
            )
            plan = plan_schematic_wire_candidate(
                document,
                virtual,
                operation,
                config=config.wire_planner,
            )
            if not plan.accept_route:
                metrics = plan.selected.metrics
                raise CapabilityUnavailableError(
                    f"Selective reroute rejected {net_name!r} on sheet {sheet}: "
                    f"obstacle_hits={metrics.obstacle_hits}, overlaps={metrics.overlaps}, "
                    f"crossings={metrics.crossings}, diagonals={metrics.diagonals}"
                )
            add_operations.append(plan.selected.operation)
            group_plans.append((net_id, sheet, plan))
            _append_completed_net_routes(virtual, [(net_id, sheet, plan)])

        pin_ids = sorted(item.pin.stable_id for item in endpoints)
        state = group_state[(net_id, sheet)]
        reports.append(
            SchematicAffectedNetGroup(
                net_id=net_id,
                net_name=net_name,
                sheet=sheet,
                moved_part_ids=sorted(state["moved_part_ids"]),
                pin_ids=pin_ids,
                deleted_wire_ids=sorted(state["deleted_wire_ids"]),
                replacement_edge_count=len(group_plans),
            )
        )

    operations: list[SemanticOperation] = [
        *delete_operations,
        *move_operations,
        *add_operations,
    ]
    return SchematicAtomicReroutePlan(
        operations=operations,
        moved_part_ids=moved_part_ids,
        deleted_wire_ids=deleted_wire_ids,
        added_wire_count=len(add_operations),
        affected_net_groups=reports,
        warnings=sorted(set(warnings)),
        limitations=[
            "Selective reroute replaces explicit wire geometry only on sheet-local nets touched "
            "by moved parts; unaffected wire geometry is left byte-semantically untouched by the plan.",
            "Affected wire geometry is rebuilt from resolved pin endpoints using deterministic MST "
            "edges; existing manual junction topology is not preserved as a visual constraint.",
            "The planner is non-mutating. Atomicity is provided when the complete returned operation "
            "list is previewed/committed through the existing guarded semantic transaction path.",
        ],
    )
