from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import capability_report as build_capability_report
from .config import Settings
from .domain import DocumentProvenance, PlanStatus, TransactionRecord
from .errors import ConfirmationRequiredError, DocumentError, EditError, Sha256MismatchError
from .operations import SemanticOperation, parse_semantic_operations
from .preview import PREVIEW_COPPER_POINT_LIMIT, PREVIEW_COPPER_RECORD_LIMIT
from .previews import RawPreviewStore
from .provenance_registry import TrustedProvenanceRegistry
from .services.bom import BomService
from .services.container import build_service_container
from .services.context import DocumentTarget, validate_page
from .services.discovery import DiscoveryService
from .services.documents import DocumentService
from .services.evidence import (
    EvidenceService,
    RoundtripEvidenceEvaluation,
    _fail_closed_trust,  # noqa: F401 - proven compatibility export
    _semantic_roundtrip_check,  # noqa: F401 - proven compatibility export
)
from .services.exports import ExportService
from .services.external_jobs import ExternalJobsService
from .services.intelligence import IntelligenceService
from .services.jobs import JobService
from .services.live_sessions import LiveSessionService
from .services.placement import PlacementService
from .services.review import ReviewService
from .services.routing import RoutingService
from .services.scaffolding import ScaffoldingService
from .services.semantic_engine import SemanticEngineService
from .services.semantic_operations import SemanticOperationsService
from .services.synchronization import SynchronizationService
from .services.transactions import TransactionService
from .services.xml_writes import (
    RAW_EDIT_RESPONSE_BYTE_LIMIT,
    RAW_EDIT_XPATH_CHARACTER_LIMIT,
    XmlWriteService,
)
from .sessions import LiveWorkingGuard
from .specctra import dsn_export_limitations
from .write_limits import WriteImpact, require_write_impact
from .xml_document import (
    DEFAULT_DIFF_CHARACTER_LIMIT,
    DEFAULT_DIFF_LINE_LIMIT,
    DipTraceDocument,
    atomic_write_bytes,
    sha256_bytes,
)

BOARD_MODEL_RESPONSE_BYTE_LIMIT = 256 * 1024
BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT = 32 * 1024


class DipTraceService:
    """Internal application composition root used by the MCP runtime."""

    _validate_page = staticmethod(validate_page)

    def __init__(self, settings: Settings):
        container = build_service_container(settings)
        self.settings = settings
        self.policy = container.policy
        self.sessions = container.sessions
        self.transactions = container.transactions
        self.plans = container.plans
        self.findings = container.findings
        self.jobs = container.jobs
        self.exports = container.exports
        self.backups = container.backups
        self.external_jobs = container.external_jobs
        self.models = container.models
        self._trusted_provenance_registry = container.trusted_provenance_registry
        self._service_context = container.service_context
        self._document_gateway = container.document_gateway
        self._raw_preview_retention = settings.retention_policy
        self._raw_previews: RawPreviewStore | None = None
        self._workflow_prompt_names: tuple[str, ...] = ()

        self._discovery_service = DiscoveryService(settings)
        self._export_service = ExportService(
            self._service_context,
            self._document_gateway,
            self.exports,
        )
        self._job_service = JobService(settings, self.jobs, self.external_jobs)
        self._bom_service = BomService(self._service_context, self._document_gateway)
        self._intelligence_service = IntelligenceService(
            self._service_context, self._document_gateway
        )
        self._review_service = ReviewService(self._service_context, self._document_gateway)
        self._evidence_service = EvidenceService(
            self._service_context,
            self._document_gateway,
            self._trusted_provenance_registry_provider,
            self._atomic_write_bytes,
            self._write_provenance_sidecar_callback,
            self._evaluate_roundtrip_evidence_callback,
        )
        self._document_service = DocumentService(
            self._service_context,
            self._document_gateway,
            self._evidence_service.resolve_effective_document_trust,
        )
        self._semantic_engine_service = SemanticEngineService(
            self._service_context,
            self._document_gateway,
            self.transactions,
            self.preview_transaction,
            self.commit_transaction,
            self._load_snapshot_record,
            self._session_id_from_working,
        )
        self._semantic_operations_service = SemanticOperationsService(
            self._service_context,
            self._document_gateway,
            self._run_semantic_write,
            self._run_semantic_operations,
        )
        self._external_jobs_service = ExternalJobsService(
            self._service_context,
            self._document_gateway,
            self.plans,
            self.jobs,
            self.external_jobs,
            self._preview_semantic_operations,
            self._apply_stored_plan,
        )
        self._routing_service = RoutingService(
            self._service_context,
            self._document_gateway,
            self.plans,
            self._run_semantic_write,
            self._run_semantic_operations,
            self._preview_semantic_operations,
            self._apply_stored_plan,
        )
        self._placement_service = PlacementService(
            self._service_context,
            self._document_gateway,
            self.plans,
            self._preview_semantic_operations,
            self._apply_stored_plan,
        )
        self._xml_write_service = XmlWriteService(
            self._service_context,
            self._document_gateway,
            self.backups,
            self.sessions,
            self._raw_preview_store_provider,
            self._require_current_target_sha256,
            self._atomic_write_bytes,
            self._invalidated_document_provenance_callback,
            self._write_provenance_sidecar_callback,
            self._invalidate_document_trust_after_write_callback,
        )
        self._live_session_service = LiveSessionService(self._service_context, self.sessions)
        self._synchronization_service = SynchronizationService(
            self._service_context,
            self._document_gateway,
            self._run_semantic_write,
        )
        self._scaffolding_service = ScaffoldingService(
            self._service_context,
            self.backups,
            self._load_overwrite_target,
            self._require_current_target_sha256,
            self._require_target_still_absent,
            self._load_seed_provenance,
            self._load_and_validate_evidence_manifest,
            self._load_and_authorize_trusted_registry_evidence,
            self._write_provenance_sidecar_callback,
            self._require_write_impact_callback,
        )
        self._transaction_service = TransactionService(
            self._service_context,
            self._document_gateway,
            self.transactions,
            self.sessions,
            self._preview_semantic_operations,
            self._require_current_target_sha256,
            self._atomic_write_bytes,
            self._invalidate_document_trust_after_write_callback,
            self._load_and_validate_evidence_manifest,
            self._load_and_authorize_trusted_registry_evidence,
        )

        self._delegates: tuple[object, ...] = (
            self._document_service,
            self._bom_service,
            self._intelligence_service,
            self._review_service,
            self._semantic_operations_service,
            self._routing_service,
            self._placement_service,
            self._export_service,
            self._external_jobs_service,
            self._job_service,
            self._evidence_service,
            self._xml_write_service,
            self._live_session_service,
            self._synchronization_service,
            self._transaction_service,
            self._scaffolding_service,
            self._discovery_service,
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        for service in self.__dict__.get("_delegates", ()):
            try:
                return getattr(service, name)
            except AttributeError:
                continue
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        """Late-bind the module writer so fault-injection tests exercise real recovery."""
        atomic_write_bytes(path, data)

    @staticmethod
    def _require_write_impact_callback(impact: WriteImpact, *, operation: str) -> None:
        """Late-bind the impact gate for race-injection tests."""
        require_write_impact(impact, operation=operation)

    def _write_provenance_sidecar_callback(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> None:
        self._write_provenance_sidecar(document_path, provenance)

    def _evaluate_roundtrip_evidence_callback(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None,
        reexport_path: str | None,
        reexport_sha256: str | None,
    ) -> RoundtripEvidenceEvaluation:
        return self._evaluate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

    def _invalidated_document_provenance_callback(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str,
    ) -> DocumentProvenance:
        return self._evidence_service._invalidated_document_provenance(
            document_path,
            document_sha256,
            operation_name=operation_name,
        )

    def _invalidate_document_trust_after_write_callback(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str = "mcp_write",
    ) -> None:
        self._evidence_service.invalidate_document_trust_after_write(
            document_path,
            document_sha256,
            operation_name=operation_name,
        )

    @property
    def raw_previews(self) -> RawPreviewStore:
        if self._raw_previews is None:
            self._raw_previews = RawPreviewStore(
                self.settings.state_dir,
                retention=self._raw_preview_retention,
            )
        return self._raw_previews

    def _raw_preview_store_provider(self) -> RawPreviewStore:
        return self.raw_previews

    def _trusted_provenance_registry_provider(self) -> TrustedProvenanceRegistry:
        return self._trusted_provenance_registry

    @staticmethod
    def _write_provenance_sidecar(
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> None:
        sidecar = document_path.with_suffix(document_path.suffix + ".provenance.json")
        atomic_write_bytes(sidecar, provenance.model_dump_json(indent=2).encode())

    def _load_seed_provenance(self, seed_path: Path) -> DocumentProvenance | None:
        return self._evidence_service._load_seed_provenance(seed_path)

    def _load_and_validate_evidence_manifest(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> Any:
        return self._evidence_service._load_and_validate_evidence_manifest(
            document_path,
            provenance,
        )

    def _load_and_authorize_trusted_registry_evidence(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> Any:
        return self._evidence_service._load_and_authorize_trusted_registry_evidence(
            document_path,
            provenance,
        )

    def _evaluate_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> RoundtripEvidenceEvaluation:
        return self._evidence_service._evaluate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

    def set_workflow_prompt_names(self, names: Sequence[str]) -> None:
        self._workflow_prompt_names = tuple(sorted(set(names)))

    def resolve_target(self, path: str | None) -> DocumentTarget:
        return self._document_gateway.resolve_target(path)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load(path)

    def load_document_id(self, document_id: str) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load_document_id(document_id)

    def document_info(self, path: str | None = None) -> dict[str, Any]:
        """Explicit seam retained for error-boundary fault injection."""
        return self._document_service.document_info(path)

    def _load_overwrite_target(
        self,
        target: Path,
        *,
        overwrite: bool,
        expected_sha256: str | None,
    ) -> DipTraceDocument | None:
        if not target.exists():
            return None
        if not overwrite:
            raise EditError(
                f"Target already exists (pass overwrite=true to replace): {target}",
                code="path_exists",
                details={"path": str(target)},
            )
        if expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required when overwrite=true replaces an existing target",
                details={"path": str(target)},
            )
        document = DipTraceDocument.load(target, self.settings.max_document_bytes)
        if document.sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {document.sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": document.sha256,
                    "path": str(target),
                },
            )
        return document

    @staticmethod
    def _require_current_target_sha256(target: Path, expected_sha256: str) -> None:
        try:
            current_sha256 = sha256_bytes(target.read_bytes())
        except OSError as exc:
            raise EditError(
                f"Cannot read target before write: {target}",
                details={"path": str(target)},
            ) from exc
        if current_sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {current_sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                    "path": str(target),
                },
            )

    @staticmethod
    def _require_target_still_absent(target: Path) -> None:
        if target.exists():
            raise EditError(
                "Target appeared while document creation was being validated; "
                "reload it and retry through the overwrite SHA gate",
                code="path_exists",
                details={"path": str(target)},
            )

    def status(self) -> dict[str, Any]:
        active = self.sessions.active_metadata()
        if active is not None:
            session_id = str(active["session_id"])
            active = {
                **active,
                "working_path": str(self.sessions.working_path(session_id)),
                "working_sha256": self.sessions.working_sha256(session_id),
            }
        return {
            "server": "diptrace-mcp",
            "version": __version__,
            "configuration": self.settings.as_dict(),
            "active_session": active,
            "last_session_transition": self.sessions.last_session_transition(),
            "model_cache": self.models.stats(),
            "capabilities": self.get_capabilities(),
        }

    def get_capabilities(self, path: str | None = None) -> dict[str, Any]:
        if path is None:
            active = self.sessions.active_metadata()
            if active is None:
                report = build_capability_report(
                    None,
                    workflow_prompt_names=self._workflow_prompt_names,
                ).model_dump()
                return self._add_runtime_capabilities(report)
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        effective_trust = self._evidence_service.resolve_effective_document_trust(
            target.path,
            snapshot.info.sha256,
        )
        report = build_capability_report(
            snapshot,
            workflow_prompt_names=self._workflow_prompt_names,
            document_trust={
                "validation_level": effective_trust.validation_level.value,
                "trust_authority": effective_trust.authority,
                "requires_diptrace_verification": effective_trust.requires_diptrace_verification,
                "evidence_manifest_path": effective_trust.evidence_manifest_path,
                "evidence_manifest_sha256": effective_trust.evidence_manifest_sha256,
                "warnings": effective_trust.warnings,
            },
        ).model_dump()
        report = self._add_runtime_capabilities(report)
        dsn_reasons = dsn_export_limitations(snapshot)
        report["write_capabilities"]["autorouter_dsn_export"] = not dsn_reasons
        if dsn_reasons:
            report["reasons_unavailable"].append(
                {
                    "feature": "autorouter_dsn_export",
                    "code": "capability_unavailable",
                    "message": (
                        "Current document cannot be represented by the bounded DSN serializer."
                    ),
                    "details": {"reasons": dsn_reasons},
                }
            )
        return report

    def trusted_provenance_registry_report(self) -> dict[str, object]:
        return self._trusted_provenance_registry.report()

    def _add_runtime_capabilities(self, report: dict[str, Any]) -> dict[str, Any]:
        probe = self.external_jobs.freerouting.probe()
        report["external_adapters"]["freerouting"] = probe.as_dict()
        report["external_adapters"]["ngspice"] = self.external_jobs.ngspice.probe().as_dict()
        openems_probe = self.external_jobs.openems.probe()
        report["external_adapters"]["openems"] = openems_probe.as_dict()
        report["limits"].update(
            {
                "max_document_bytes": self.settings.max_document_bytes,
                "max_model_cache_bytes": self.settings.model_cache_max_bytes,
                "max_external_log_bytes": self.settings.max_external_log_bytes,
                "max_external_processes": self.settings.max_external_processes,
                "max_external_result_bytes": self.settings.max_external_result_bytes,
                "max_board_model_response_bytes": BOARD_MODEL_RESPONSE_BYTE_LIMIT,
                "max_board_model_item_detail_bytes": BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT,
                "max_raw_edit_response_bytes": RAW_EDIT_RESPONSE_BYTE_LIMIT,
                "max_raw_edit_xpath_characters": RAW_EDIT_XPATH_CHARACTER_LIMIT,
                "max_diff_lines": DEFAULT_DIFF_LINE_LIMIT,
                "max_diff_characters": DEFAULT_DIFF_CHARACTER_LIMIT,
                "max_preview_copper_records": PREVIEW_COPPER_RECORD_LIMIT,
                "max_preview_copper_points": PREVIEW_COPPER_POINT_LIMIT,
                "retention_max_records": self.settings.retention_max_records,
                "retention_max_age_days": self.settings.retention_max_age_days,
                "live_session_ttl_seconds": self.settings.live_session_ttl_seconds,
            }
        )
        report["trust_model"]["trusted_registry"] = self.trusted_provenance_registry_report()
        report["trust_model"]["high_trust_authority"] = (
            "trusted_registry_exact_hash_allowlist"
            if self._trusted_provenance_registry.entry_count > 0
            else "trusted_registry_available_no_reviewed_entries"
        )
        report["policy"].update(self.policy.capability_payload())
        if probe.available:
            report["reasons_unavailable"] = [
                item
                for item in report["reasons_unavailable"]
                if item.get("feature") != "external_autorouting"
            ]
        if openems_probe.available:
            report["reasons_unavailable"] = [
                item
                for item in report["reasons_unavailable"]
                if item.get("feature") != "external_si_pi_solver"
            ]
        return report

    def scan_component_libraries(
        self,
        root: str | None = None,
        recursive: bool = True,
    ) -> dict[str, Any]:
        return self._discovery_service._scan_libraries("DipTrace-ComponentLibrary", root, recursive)

    def scan_pattern_libraries(
        self,
        root: str | None = None,
        recursive: bool = True,
    ) -> dict[str, Any]:
        return self._discovery_service._scan_libraries("DipTrace-PatternLibrary", root, recursive)

    def preview_transaction(self, txid: str) -> dict[str, Any]:
        return self._transaction_service.preview_transaction(txid)

    def commit_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        return self._transaction_service.commit_transaction(
            txid,
            expected_sha256,
            _live_session_id=_live_session_id,
            _live_guard=_live_guard,
        )

    def _load_snapshot_record(self, record: TransactionRecord) -> DipTraceDocument:
        return self._transaction_service._load_snapshot_record(record)

    def _session_id_from_working(self, path: Path) -> str | None:
        return self._transaction_service._session_id_from_working(path)

    def _run_semantic_write(
        self,
        operation: SemanticOperation,
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        return self._semantic_engine_service._run_semantic_write(
            operation,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    def _run_semantic_operations(
        self,
        operations: Sequence[SemanticOperation],
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        return self._semantic_engine_service._run_semantic_operations(
            operations,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    def _preview_semantic_operations(
        self,
        document: DipTraceDocument,
        operations: list[SemanticOperation],
    ) -> dict[str, Any]:
        return self._semantic_engine_service._preview_semantic_operations(document, operations)

    def _apply_stored_plan(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        plan = self.plans.read(plan_id)
        if plan.plan_type != expected_plan_type:
            raise DocumentError(
                f"Unexpected plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
                details={
                    "expected_plan_type": expected_plan_type,
                    "actual_plan_type": plan.plan_type,
                },
            )
        target_path = self.settings.resolve_allowed_path(plan.target_path)
        document = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
        if document.sha256 != plan.source_sha256:
            self.plans.update(plan_id, status="obsolete", transaction_id=plan.transaction_id)
            raise Sha256MismatchError(
                "Document changed after the plan was generated",
                details={
                    "plan_sha256": plan.source_sha256,
                    "current_sha256": document.sha256,
                },
            )
        if expected_sha256 is not None and expected_sha256 != plan.source_sha256:
            raise Sha256MismatchError(
                "Provided SHA does not match the plan source",
                details={
                    "plan_sha256": plan.source_sha256,
                    "provided_sha256": expected_sha256,
                },
            )
        operations = parse_semantic_operations(plan.operations)
        if not operations:
            if plan.status != "noop":
                raise EditError("Plan contains no changes")
            # Documented no-op contract: the planner stored this plan as
            # no_changes, so apply is an idempotent success without a write or
            # a transaction, and the document SHA must not change.
            return {
                "ok": True,
                "changed": False,
                "changed_ids": [],
                "changed_id_count": 0,
                "changed_ids_truncated": False,
                "transaction": None,
                "plan": plan.model_dump(mode="json"),
                "warnings": [],
                "limitations": [
                    "Plan contains no operations; apply is a documented no-op."
                ],
            }
        response = self._run_semantic_operations(
            operations,
            str(target_path),
            dry_run,
            expected_sha256,
            txid,
        )
        transaction = response.get("transaction") or {}
        transaction_id = transaction.get("txid")
        status: PlanStatus = (
            "committed" if transaction.get("status") == "committed" else "staged"
        )
        updated = self.plans.update(
            plan_id,
            status=status,
            transaction_id=transaction_id,
        )
        response["plan"] = updated.model_dump(mode="json")
        return response

    def plan_resource(self, plan_id: str, resource: str) -> str:
        if resource == "summary":
            return json.dumps(
                self.plans.read(plan_id).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        paths = {
            "preview.svg": self.plans.preview_svg_path(plan_id),
            "preview.json": self.plans.preview_json_path(plan_id),
            "diff": self.plans.diff_path(plan_id),
        }
        try:
            resource_path = paths[resource]
        except KeyError as exc:
            raise DocumentError(
                f"Unknown plan resource: {resource}",
                code="object_not_found",
            ) from exc
        if not resource_path.is_file():
            raise DocumentError(
                f"Plan resource is unavailable: {resource}",
                code="object_not_found",
            )
        return resource_path.read_text(encoding="utf-8")
