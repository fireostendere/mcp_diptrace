from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from .adapters import build_snapshot
from .domain import QuerySelector, StrictModel
from .errors import CapabilityUnavailableError
from .operations import (
    AddWireOperation,
    DeleteWireOperation,
    SemanticOperation,
    WireEndpoint,
)
from .schematic_joint_optimizer import (
    _affected_groups,
    _append_completed_net_routes,
    _initial_points,
    _moved_parts,
    _mst_endpoint_edges,
    _net_names,
    _remove_affected_wires,
    _virtual_endpoints,
    _virtualize_snapshot,
)
from .schematic_optimizer import SchematicPlacementCandidate
from .schematic_pin_geometry import (
    SchematicPinGeometryResolution,
    resolve_document_schematic_pin_geometry,
)
from .schematic_wire_planner import (
    SchematicWirePlannerConfig,
    plan_schematic_wire_candidate,
)
from .xml_document import DipTraceDocument

_EPS = 1e-9


class SchematicAtomicRerouteConfig(StrictModel):
    """Bounds and policy for one placement + affected-wire replacement transaction."""

    max_moved_parts: int = Field(default=256, ge=1, le=10_000)
    max_affected_net_groups: int = Field(default=256, ge=1, le=10_000)
    max_deleted_wires: int = Field(default=2_048, ge=1, le=50_000)
    max_added_wires: int = Field(default=2_048, ge=1, le=50_000)
    include_unwired_affected_nets: bool = False
    wire_planner: SchematicWirePlannerConfig = Field(
        default_factory=SchematicWirePlannerConfig
    )


class SchematicAffectedNetGroup(StrictModel):
    net_id: str
    net_name: str
    sheet: int = Field(ge=0)
    moved_part_ids: list[str] = Field(default_factory=list)
    pin_ids: list[str] = Field(default_factory=list)
    deleted_wire_ids: list[str] = Field(default_factory=list)
    replacement_edge_count: int = Field(ge=0)
    quality_feedback: list[str] = Field(default_factory=list)


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


def _readability_feedback(
    *,
    net_name: str,
    sheet: int,
    route_index: int,
    plan: Any,
) -> str:
    reasons = list(plan.placement_feedback.reasons)
    if not reasons:
        metrics = plan.selected.metrics
        reasons = [
            f"obstacle_hits={metrics.obstacle_hits}",
            f"overlaps={metrics.overlaps}",
            f"crossings={metrics.crossings}",
            f"self_intersections={metrics.self_intersections}",
            f"diagonals={metrics.diagonals}",
            f"bends={metrics.bends}",
            f"detour_ratio={metrics.detour_ratio:.3g}",
        ]
    return (
        f"Selective reroute readability feedback for {net_name!r} on sheet {sheet}, "
        f"replacement edge {route_index}: {'; '.join(reasons)}. Connectivity-safe "
        "replacement is retained for the atomic transaction; readability remains "
        "explicit review/repair feedback."
    )


def plan_atomic_schematic_placement_reroute(
    document: DipTraceDocument,
    candidate: SchematicPlacementCandidate,
    *,
    pin_geometry: SchematicPinGeometryResolution | None = None,
    config: SchematicAtomicRerouteConfig | None = None,
) -> SchematicAtomicReroutePlan:
    """Plan one all-or-nothing placement and selective affected-net reroute.

    The function is deliberately non-mutating. It returns ordinary semantic
    operations in dependency-safe order: delete affected wire geometry, move parts,
    then author replacement wires. Passing the complete list to the existing
    semantic-operations transaction path keeps the placement and reroute atomic under
    the same SHA/preview/commit boundary.

    Connectivity/safety failures remain fail-closed. Wire-planner readability
    thresholds are preserved as explicit quality feedback instead of being promoted
    into destructive-reroute failures when a valid endpoint-to-endpoint replacement
    can still be authored.
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
                (
                    "Moved parts touch no explicit wire geometry under the current "
                    "selective-reroute policy."
                )
            ],
            limitations=[
                (
                    "Unwired affected nets are preserved as connectivity-only nets "
                    "unless include_unwired_affected_nets is enabled."
                )
            ],
        )

    pin_geometry = pin_geometry or resolve_document_schematic_pin_geometry(document)
    virtual, virtualization_warnings = _virtualize_snapshot(
        snapshot,
        candidate.placements,
    )
    affected_keys = set(group_state)
    _remove_affected_wires(virtual, affected_keys)
    endpoint_groups, endpoint_warnings = _virtual_endpoints(
        snapshot,
        virtual,
        pin_geometry,
    )
    net_names = _net_names(snapshot)

    add_operations: list[SemanticOperation] = []
    reports: list[SchematicAffectedNetGroup] = []
    warnings = [*virtualization_warnings, *endpoint_warnings, *pin_geometry.warnings]

    for net_id, sheet in sorted(affected_keys):
        endpoints = endpoint_groups.get((net_id, sheet), [])
        if len(endpoints) < 2:
            raise CapabilityUnavailableError(
                f"Affected net {net_names.get(net_id, net_id)!r} on sheet {sheet} "
                "does not have at least two resolvable endpoints; refusing "
                "destructive reroute"
            )
        edges = _mst_endpoint_edges(endpoints)
        if len(add_operations) + len(edges) > config.max_added_wires:
            raise CapabilityUnavailableError(
                f"Atomic reroute would author more than {config.max_added_wires} wires"
            )
        net_name = net_names.get(net_id, net_id)
        group_plans = []
        group_quality_feedback: list[str] = []
        for route_index, (start, end) in enumerate(edges, 1):
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
                feedback = _readability_feedback(
                    net_name=net_name,
                    sheet=sheet,
                    route_index=route_index,
                    plan=plan,
                )
                group_quality_feedback.append(feedback)
                warnings.append(feedback)
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
                quality_feedback=group_quality_feedback,
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
            (
                "Selective reroute replaces explicit wire geometry only on "
                "sheet-local nets touched by moved parts; unaffected wire geometry "
                "is left byte-semantically untouched by the plan."
            ),
            (
                "Affected wire geometry is rebuilt from resolved pin endpoints using "
                "deterministic MST edges; existing manual junction topology is not "
                "preserved as a visual constraint."
            ),
            (
                "Unresolved or insufficient endpoints remain fail-closed. Readability "
                "threshold failures from the wire planner are surfaced as explicit "
                "quality feedback and do not by themselves discard an otherwise "
                "connectivity-safe replacement."
            ),
            (
                "The planner is non-mutating. Atomicity is provided when the complete "
                "returned operation list is previewed/committed through the existing "
                "guarded semantic transaction path."
            ),
        ],
    )
