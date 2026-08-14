"""Placement analysis and safe placement-plan orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..adapters import DocumentSnapshot, build_snapshot
from ..capability_model import MAX_TRANSACTION_OPERATIONS
from ..domain import QuerySelector
from ..errors import CapabilityUnavailableError, DrcRegressionError, EditError
from ..geometry import Point
from ..operations import SemanticOperation
from ..placement import (
    PlacementConfig,
    PlacementProposal,
    PlacementWeights,
    analyze_placement,
    generate_placement_candidates,
    plan_component_placement,
    score_placement_proposal,
)
from ..plans import PlanStore
from ..preview import render_preview_json, render_preview_svg
from ..review import run_checks
from ..schematic_atomic_reroute import plan_atomic_schematic_placement_reroute
from ..schematic_joint_optimizer import SchematicJointRouteConfig
from ..schematic_layout import analyze_schematic_layout
from ..schematic_optimizer import SchematicPlacementCandidate
from ..schematic_placement_repair import (
    SchematicPlacementRepairConfig,
    repair_schematic_placement_from_route_feedback,
)
from ..semantic_compiler import apply_semantic_operations
from ..silkscreen import SilkscreenPlanConfig, plan_silkscreen
from ..xml_document import DipTraceDocument
from .context import DocumentGateway, ServiceContext, read_success

PreviewSemanticOperations = Callable[[DipTraceDocument, list[SemanticOperation]], dict[str, Any]]


class ApplyStoredPlan(Protocol):
    def __call__(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]: ...


class PlacementService:
    """Implementation for placement analysis and placement plans."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        plan_store: PlanStore,
        preview_semantic_operations: PreviewSemanticOperations,
        apply_stored_plan: ApplyStoredPlan,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.plan_store = plan_store
        self.preview_semantic_operations = preview_semantic_operations
        self.apply_stored_plan = apply_stored_plan

    def plan_silkscreen(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = False,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = SilkscreenPlanConfig.model_validate(
            {
                "selector": selector or {},
                "clearance": clearance,
                "board_edge_clearance": board_edge_clearance,
                "grid": grid,
                "search_steps": search_steps,
                "include_board_texts": include_board_texts,
                "avoid_component_bodies": avoid_component_bodies,
            }
        )
        planned = plan_silkscreen(snapshot, config)
        record = self.plan_store.create(
            plan_type="silkscreen",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=planned.metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        if planned.operations:
            preview = self.preview_semantic_operations(document, planned.operations)
        else:
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        resources = self.plan_store.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
            },
            diff=preview["diff"],
        )
        record = self.plan_store.read(record.plan_id)
        if not planned.operations:
            record = self.plan_store.update(
                record.plan_id, status="noop", transaction_id=None
            )
        return read_success(
            snapshot.info,
            {
                "plan": record.model_dump(mode="json"),
                "no_changes": not planned.operations,
            },
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def analyze_placement(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = analyze_placement(
            snapshot,
            QuerySelector.model_validate(selector or {}),
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
        )
        return read_success(
            snapshot.info,
            result,
            limitations=["Component bounds are estimated when body/courtyard geometry is absent."],
        )

    def generate_placement_candidates(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        candidates = generate_placement_candidates(snapshot, config)
        return read_success(
            snapshot.info,
            {
                "matched_count": len(candidates),
                "config": config.model_dump(mode="json"),
                "items": candidates,
            },
            limitations=["Candidate geometry uses normalized component bounds."],
        )

    def score_placement(
        self,
        placements: list[dict[str, Any]],
        path: str | None = None,
        *,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = PlacementConfig(
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=PlacementWeights.model_validate(weights or {}),
        )
        proposals = [PlacementProposal.model_validate(item) for item in placements]
        score, violations = score_placement_proposal(snapshot, proposals, config)
        return read_success(
            snapshot.info,
            {"score": score, "violations": violations},
            limitations=["Ratsnest cost uses component anchors, not exact pad anchors."],
        )

    def plan_component_placement(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        planned = plan_component_placement(snapshot, config)
        before_findings, _, _, _ = run_checks(snapshot, categories={"placement"})
        if planned.operations:
            applied = apply_semantic_operations(
                document, planned.operations, live_session=target.is_live
            )
            after_snapshot = build_snapshot(applied.document, live_session=target.is_live)
            after_findings, _, _, _ = run_checks(after_snapshot, categories={"placement"})
            preview = self.preview_semantic_operations(document, planned.operations)
        else:
            after_findings = before_findings
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        before_errors = sum(item.severity == "error" for item in before_findings)
        after_errors = sum(item.severity == "error" for item in after_findings)
        if after_errors > before_errors:
            raise DrcRegressionError(
                "Placement plan introduces new placement DRC errors",
                details={
                    "errors_before": before_errors,
                    "errors_after": after_errors,
                },
                object_ids=planned.changed_ids,
            )
        metrics = {
            **planned.metrics,
            "validation": {
                "placement_errors_before": before_errors,
                "placement_errors_after": after_errors,
                "no_new_placement_errors": after_errors <= before_errors,
            },
        }
        record = self.plan_store.create(
            plan_type="component_placement",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        resources = self.plan_store.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
                "validation": metrics["validation"],
            },
            diff=preview["diff"],
        )
        record = self.plan_store.read(record.plan_id)
        if not planned.operations:
            record = self.plan_store.update(
                record.plan_id, status="noop", transaction_id=None
            )
        return read_success(
            snapshot.info,
            {
                "plan": record.model_dump(mode="json"),
                "no_changes": not planned.operations,
            },
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def apply_component_placement_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self.apply_stored_plan(
            plan_id,
            expected_plan_type="component_placement",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def plan_schematic_placement_repair(
        self,
        path: str | None = None,
        *,
        moves: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.schematic is None:
            raise CapabilityUnavailableError(
                "Schematic placement repair requires a schematic document"
            )
        base = self._current_layout_candidate(snapshot)
        fixed_moves: dict[str, dict[str, float]] = {}
        if moves:
            fixed_moves = self._resolve_schematic_moves(snapshot, moves)
            base = base.model_copy(deep=True)
            base.placements = {**base.placements, **fixed_moves}
        repair_config = SchematicPlacementRepairConfig(
            joint_route=SchematicJointRouteConfig(allow_existing_wires=True),
            fixed_part_ids=tuple(fixed_moves),
        )
        repair = repair_schematic_placement_from_route_feedback(
            document, base, config=repair_config
        )
        final_candidate = (
            repair.selected.candidate if repair.selected is not None else repair.base_candidate
        )
        if fixed_moves:
            # Repair search is constrained to never move fixed parts; verify the
            # invariant fail-closed instead of silently re-applying coordinates.
            for part_id, requested in fixed_moves.items():
                actual = final_candidate.placements.get(part_id)
                if actual != requested:
                    raise EditError(
                        "Schematic placement repair violated an operator-fixed "
                        f"coordinate for part {part_id}"
                    )
        reroute = plan_atomic_schematic_placement_reroute(document, final_candidate)
        if len(reroute.operations) > MAX_TRANSACTION_OPERATIONS:
            raise EditError(
                "Schematic placement repair plan would exceed the "
                f"{MAX_TRANSACTION_OPERATIONS} operations transaction limit "
                f"({len(reroute.operations)} planned); reduce the affected scope"
            )
        if reroute.operations:
            preview = self.preview_semantic_operations(document, reroute.operations)
        else:
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        metrics = {
            "repair": {
                "improved": repair.improved,
                "selected_action_feedback_kind": (
                    repair.selected.action.feedback_kind if repair.selected else None
                ),
                "feedback_edge_count": repair.feedback_edge_count,
                "generated_candidate_count": repair.generated_candidate_count,
                "rejected_overlap_candidate_count": repair.rejected_overlap_candidate_count,
            },
            "reroute": {
                "moved_part_count": len(reroute.moved_part_ids),
                "deleted_wire_count": len(reroute.deleted_wire_ids),
                "added_wire_count": reroute.added_wire_count,
                "affected_net_group_count": len(reroute.affected_net_groups),
            },
        }
        warnings = [
            *repair.warnings,
            *reroute.warnings,
        ]
        limitations = [
            "Affected explicit nets are rebuilt from resolved pin endpoints through "
            "deterministic MST edges; hand-authored junction topology is not preserved "
            "as a visual constraint.",
            *repair.limitations,
            *reroute.limitations,
        ]
        record = self.plan_store.create(
            plan_type="schematic_placement_repair",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config={"moves": list(moves or [])},
            operations=[operation.model_dump(mode="json") for operation in reroute.operations],
            changed_ids=[*reroute.moved_part_ids, *reroute.deleted_wire_ids],
            unresolved=list(base.unresolved),
            candidates=[],
            score={
                "placement_total_score": repair.base_score.placement_total_score,
            },
            metrics=metrics,
            assumptions=list(repair.assumptions),
            warnings=warnings,
            limitations=limitations,
        )
        resources = self.plan_store.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "metrics": metrics,
            },
            diff=preview["diff"],
        )
        record = self.plan_store.read(record.plan_id)
        if not reroute.operations:
            record = self.plan_store.update(
                record.plan_id, status="noop", transaction_id=None
            )
        return read_success(
            snapshot.info,
            {
                "plan": record.model_dump(mode="json"),
                "no_changes": not reroute.operations,
            },
            warnings=warnings,
            limitations=limitations,
            resources=resources,
        )

    def apply_schematic_placement_repair_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self.apply_stored_plan(
            plan_id,
            expected_plan_type="schematic_placement_repair",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @staticmethod
    def _current_layout_candidate(snapshot: DocumentSnapshot) -> SchematicPlacementCandidate:
        """Build a repair baseline from the document's actual current placement.

        Unlike optimizer candidate generation this accepts already-wired
        schematics, which is exactly the repair-plus-reroute target case.
        """
        assert snapshot.schematic is not None
        placements: dict[str, Point] = {}
        for part in snapshot.schematic.parts:
            position = part.position
            if position is not None:
                placements[part.stable_id] = Point(float(position["x"]), float(position["y"]))
        layout = analyze_schematic_layout(snapshot, placements=placements)
        return SchematicPlacementCandidate(
            candidate_id="current-layout",
            order_strategy="role_then_id",
            local_style="support_balanced",
            row_width_mm=1.0,
            placements={
                part_id: {"x": point.x, "y": point.y} for part_id, point in placements.items()
            },
            estimated_interconnect_length_mm=0.0,
            estimated_crossing_count=0,
            backward_connector_flow_count=0,
            movement_mm=0.0,
            score_terms={},
            total_score=0.0,
            layout=layout,
        )

    @staticmethod
    def _resolve_schematic_moves(
        snapshot: Any,
        moves: list[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        """Resolve operator moves fail-closed.

        Contract: a part may be selected by its stable object ID (exact) or by
        RefDes (case-insensitive). A RefDes shared by several schematic parts
        (for example a multi-part component section) is ambiguous and refused;
        the caller must select the exact stable ID instead. Duplicate moves for
        one part are always refused, including identical duplicates.
        """
        assert snapshot.schematic is not None
        by_refdes: dict[str, list[str]] = {}
        stable_ids: set[str] = set()
        for part in snapshot.schematic.parts:
            stable_ids.add(part.stable_id)
            if part.refdes:
                by_refdes.setdefault(part.refdes.upper(), []).append(part.stable_id)
        resolved: dict[str, dict[str, float]] = {}
        for move in moves:
            raw_part = str(move.get("part", "")).strip()
            if not raw_part:
                raise EditError(
                    "Each schematic repair move needs a non-empty part identifier"
                )
            try:
                position = {
                    "x": float(move["x_mm"]),
                    "y": float(move["y_mm"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise EditError("Each schematic repair move needs numeric x_mm and y_mm") from exc
            if raw_part in stable_ids:
                stable_id = raw_part
            else:
                matches = sorted(by_refdes.get(raw_part.upper(), []))
                if not matches:
                    raise EditError(
                        f"Schematic repair move references unknown part '{raw_part}'"
                    )
                if len(matches) > 1:
                    bounded = matches[:8]
                    suffix = f" (+{len(matches) - len(bounded)} more)" if len(matches) > 8 else ""
                    raise EditError(
                        f"Schematic repair move selector '{raw_part}' is ambiguous: "
                        "RefDes matches multiple schematic parts "
                        f"{bounded}{suffix}; select one exact stable object ID"
                    )
                stable_id = matches[0]
            if stable_id in resolved:
                raise EditError(
                    f"Schematic repair moves contain duplicate entries for part "
                    f"'{raw_part}' ({stable_id}); conflicting duplicate moves are refused"
                )
            resolved[stable_id] = position
        return resolved


    def apply_silkscreen_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self.apply_stored_plan(
            plan_id,
            expected_plan_type="silkscreen",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @staticmethod
    def _placement_config(selector: dict[str, Any], options: dict[str, Any]) -> PlacementConfig:
        payload = {"selector": selector, **options}
        if "weights" in payload:
            payload["weights"] = PlacementWeights.model_validate(payload["weights"] or {})
        return PlacementConfig.model_validate(payload)
