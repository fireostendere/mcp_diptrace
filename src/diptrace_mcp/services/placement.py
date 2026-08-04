"""Placement analysis and safe placement-plan orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..adapters import build_snapshot
from ..domain import QuerySelector
from ..errors import DrcRegressionError
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
        return read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
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
        return read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
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
