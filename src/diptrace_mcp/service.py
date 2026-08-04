from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from . import __version__
from .adapters import build_snapshot
from .backups import BackupStore
from .capabilities import capability_report as build_capability_report
from .config import Settings
from .design_compare import compare_schematic_to_pcb as compare_design_snapshots
from .domain import (
    BoardModelSection,
    DocumentInfo,
    DocumentProvenance,
    PlanStatus,
    SemanticComparisonEvidence,
    TransactionRecord,
    ValidatedEvidence,
)
from .errors import (
    ConfirmationRequiredError,
    ConnectivityRegressionError,
    DocumentError,
    DrcRegressionError,
    EditError,
    Sha256MismatchError,
    TransactionConflictError,
)
from .exports import (
    ExportStore,
)
from .external_adapters import ExternalJobManager
from .findings import FindingStore
from .jobs import JobStore
from .model_cache import ModelCache
from .multirouter import (
    RoutingOrder,
)
from .operations import (
    DeleteTraceOperation,
    SemanticOperation,
    SyncSchematicToPcbOperation,
    parse_semantic_operations,
)
from .plans import PlanStore
from .policy import Policy
from .preview import (
    PREVIEW_COPPER_POINT_LIMIT,
    PREVIEW_COPPER_RECORD_LIMIT,
    render_preview_json,
    render_preview_svg,
)
from .previews import RawPreviewStore
from .provenance_registry import (
    TrustedProvenanceRegistry,
)
from .review import run_checks
from .scaffolding import (
    DEFAULT_FORMAT_VERSION,
)
from .services.bom import BomService
from .services.context import (
    DocumentGateway,
    DocumentTarget,
    ServiceContext,
    read_success,
    validate_page,
)
from .services.context import (
    bounded_text as _bounded_text,
)
from .services.context import (
    json_size as _json_size,
)
from .services.discovery import DiscoveryService
from .services.documents import DocumentService
from .services.evidence import (
    EffectiveTrust,
    EvidenceService,
    RoundtripEvidenceEvaluation,
    _fail_closed_trust,  # noqa: F401 - preserved private compatibility import
    _semantic_roundtrip_check,  # noqa: F401 - preserved private compatibility import
)
from .services.exports import ExportService
from .services.external_jobs import ExternalJobsService
from .services.jobs import JobService
from .services.placement import PlacementService
from .services.review import ReviewService
from .services.routing import RoutingService
from .services.scaffolding import ScaffoldingService
from .services.semantic_operations import SemanticOperationsService
from .services.transactions import (
    TransactionService,
    _apply_bounded_semantic_operations,
    _require_transaction_capacity,
    transaction_response_summary,
)
from .sessions import LiveWorkingGuard, SessionAction, SessionStore
from .specctra import (
    dsn_export_limitations,
)
from .synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from .transactions import (
    TransactionStore,
)
from .write_limits import require_write_impact, write_impact
from .xml_document import (
    DEFAULT_DIFF_CHARACTER_LIMIT,
    DEFAULT_DIFF_LINE_LIMIT,
    DipTraceDocument,
    XmlEdit,
    atomic_write_bytes,
    sha256_bytes,
    unified_xml_diff_preview,
    utc_now,
    write_with_backup,
)

_CANDIDATE_SUFFIXES = {".xml", ".dip", ".dch", ".eli", ".lib"}
_SOURCE_TAG = re.compile(rb"<(?:Source|Library)\b([^>]*)>", re.IGNORECASE)
_SOURCE_ATTRIBUTE = re.compile(rb"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*['\"]([^'\"]*)['\"]")
BOARD_MODEL_RESPONSE_BYTE_LIMIT = 256 * 1024
BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT = 32 * 1024
RAW_EDIT_RESPONSE_BYTE_LIMIT = 128 * 1024
RAW_EDIT_XPATH_CHARACTER_LIMIT = 128


def _finalize_raw_edit_response(result: dict[str, Any]) -> dict[str, Any]:
    result["response_byte_limit"] = RAW_EDIT_RESPONSE_BYTE_LIMIT
    result["serialized_response_bytes"] = 0
    for _ in range(8):
        serialized_size = _json_size(result)
        if result["serialized_response_bytes"] == serialized_size:
            break
        result["serialized_response_bytes"] = serialized_size
    if (
        result["serialized_response_bytes"] != _json_size(result)
        or _json_size(result) > RAW_EDIT_RESPONSE_BYTE_LIMIT
    ):
        raise EditError("apply_xml_edits response metadata exceeds its payload cap")
    return result


def _bounded_raw_edit_previews(
    previews: list[dict[str, object]],
) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for preview in previews:
        xpath = str(preview["xpath"])
        xpath_preview, xpath_truncated = _bounded_text(
            xpath,
            RAW_EDIT_XPATH_CHARACTER_LIMIT,
        )
        bounded.append(
            {
                "index": preview["index"],
                "operation": preview["operation"],
                "xpath": xpath_preview,
                "xpath_character_count": len(xpath),
                "xpath_truncated": xpath_truncated,
                "matches": preview["matches"],
                "expected_matches": preview["expected_matches"],
                "before_count": preview["before_count"],
                "after_count": preview["after_count"],
            }
        )
    return bounded


class DipTraceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = Policy(settings.active_policy)
        retention = settings.retention_policy
        self.sessions = SessionStore(
            settings.state_dir,
            settings.max_document_bytes,
            allowed_roots=settings.allowed_roots,
            retention=retention,
            active_ttl_seconds=settings.live_session_ttl_seconds,
        )
        self.transactions = TransactionStore(settings.state_dir, retention=retention)
        self._raw_preview_retention = retention
        self._raw_previews: RawPreviewStore | None = None
        self.plans = PlanStore(settings.state_dir, retention=retention)
        self.findings = FindingStore(settings.state_dir, retention=retention)
        self.jobs = JobStore(settings.state_dir, retention=retention)
        self.exports = ExportStore(
            settings.state_dir,
            settings.max_document_bytes,
            retention=retention,
        )
        self.backups = BackupStore(settings.state_dir, retention=retention)
        self.external_jobs = ExternalJobManager(settings, self.jobs)
        self.models = ModelCache(max_bytes=settings.model_cache_max_bytes)
        # This package-owned file is the only production root for registry
        # authority. Workspace and state-directory data cannot replace it.
        self._trusted_provenance_registry = TrustedProvenanceRegistry.load_embedded()
        self._service_context = ServiceContext(
            settings=settings,
            policy=self.policy,
            model_cache=self.models,
            transaction_store=self.transactions,
            session_store=self.sessions,
            finding_store=self.findings,
        )
        self._document_gateway = DocumentGateway(settings, self.sessions)
        self._document_targets = self._document_gateway.targets
        self._discovery_service = DiscoveryService(settings)
        self._export_service = ExportService(
            self._service_context,
            self._document_gateway,
            self.exports,
        )
        self._job_service = JobService(settings, self.jobs, self.external_jobs)
        self._document_service = DocumentService(
            self._service_context,
            self._document_gateway,
        )
        self._bom_service = BomService(self._service_context, self._document_gateway)
        self._review_service = ReviewService(
            self._service_context,
            self._document_gateway,
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
        self._evidence_service = EvidenceService(
            self._service_context,
            self._document_gateway,
            self._trusted_provenance_registry,
            self._atomic_write_bytes,
            self._write_provenance_sidecar_callback,
            self._evaluate_roundtrip_evidence_callback,
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
        )
        self._transaction_service = TransactionService(
            self._service_context,
            self._document_gateway,
            self.transactions,
            self.sessions,
            self._preview_semantic_operations,
            self._require_current_target_sha256,
            self._atomic_write_bytes,
            self.invalidate_document_trust_after_write,
            self._load_and_validate_evidence_manifest,
            self._load_and_authorize_trusted_registry_evidence,
        )
        self._workflow_prompt_names: tuple[str, ...] = ()

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        atomic_write_bytes(path, data)

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

    @property
    def raw_previews(self) -> RawPreviewStore:
        """Create the optional raw-preview store only when a raw diff is requested."""

        if self._raw_previews is None:
            self._raw_previews = RawPreviewStore(
                self.settings.state_dir,
                retention=self._raw_preview_retention,
            )
        return self._raw_previews

    def set_workflow_prompt_names(self, names: Sequence[str]) -> None:
        """Record the prompt names registered by the concrete MCP server."""

        self._workflow_prompt_names = tuple(sorted(set(names)))

    def _load_seed_provenance(self, seed_path: Path) -> DocumentProvenance | None:
        """Load and validate the provenance sidecar for a seed file.

        Returns the validated DocumentProvenance if a valid sidecar exists,
        or None if no sidecar is present or it fails validation.
        """
        return self._evidence_service._load_seed_provenance(seed_path)

    def _load_and_validate_evidence_manifest(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence:
        """Load and fully validate an evidence manifest referenced by a sidecar.

        This is the single point of truth for trusting evidence-backed sidecars.
        It verifies:
          1. manifest path exists and is within allowed roots
          2. manifest file SHA matches the sidecar's evidence_manifest_sha256
          3. manifest parses as valid JSON matching the expected schema
          4. manifest contains a record for the current document
          5. document SHA in manifest matches the actual document SHA
          6. source_type matches
          7. validation_level matches the claimed level
          8. trust invariants for the level are satisfied
          9. evidence authority boundary is respected

        Raises EditError on any failure (fail-closed).
        """
        return self._evidence_service._load_and_validate_evidence_manifest(
            document_path, provenance
        )

    def _load_and_authorize_trusted_registry_evidence(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence:
        """Resolve high trust only through an exact embedded-registry binding."""
        return self._evidence_service._load_and_authorize_trusted_registry_evidence(
            document_path, provenance
        )

    def _write_provenance_sidecar(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> None:
        """Write a validated provenance sidecar next to a document."""
        sidecar = document_path.with_suffix(document_path.suffix + ".provenance.json")
        atomic_write_bytes(sidecar, provenance.model_dump_json(indent=2).encode())

    def resolve_effective_document_trust(
        self,
        document_path: Path,
        document_sha256: str,
    ) -> EffectiveTrust:
        """Central trust resolution: revalidates sidecar + evidence on every read.

        All trust consumers (document_info, create_document_from_seed, export
        workflows, capability reporting) must use this method.

        Returns an EffectiveTrust with:
          - fail-closed result on any validation failure
          - revalidated evidence manifest SHA binding
          - authority boundary enforcement
        """
        return self._evidence_service.resolve_effective_document_trust(
            document_path, document_sha256
        )

    def invalidate_document_trust_after_write(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str = "mcp_write",
    ) -> None:
        """Downgrade trust after any MCP write operation.

        After an MCP-modified write, the bytes are no longer the original
        DipTrace export.  This helper updates (or creates) the sidecar to
        reflect the synthetic state while preserving parent provenance.
        """
        return self._evidence_service.invalidate_document_trust_after_write(
            document_path, document_sha256, operation_name=operation_name
        )

    def _invalidated_document_provenance(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str,
    ) -> DocumentProvenance:
        """Build the exact trust downgrade before a guarded sidecar replace."""
        return self._evidence_service._invalidated_document_provenance(
            document_path, document_sha256, operation_name=operation_name
        )

    def resolve_target(self, path: str | None) -> DocumentTarget:
        return self._document_gateway.resolve_target(path)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load(path)

    def _load_overwrite_target(
        self,
        target: Path,
        *,
        overwrite: bool,
        expected_sha256: str | None,
    ) -> DipTraceDocument | None:
        """Bind an explicit overwrite to the caller's view of the existing bytes."""

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
        """Repeat a caller-SHA check immediately before replacing design bytes."""

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
        """Refuse if a path appeared while a new document was being validated."""

        if target.exists():
            raise EditError(
                "Target appeared while document creation was being validated; "
                "reload it and retry through the overwrite SHA gate",
                code="path_exists",
                details={"path": str(target)},
            )

    def load_document_id(self, document_id: str) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load_document_id(document_id)

    def status(self) -> dict[str, Any]:
        active = self.sessions.active_metadata()
        if active is not None:
            session_id = str(active["session_id"])
            working = self.sessions.working_path(session_id)
            active = {
                **active,
                "working_path": str(working),
                "working_sha256": self.sessions.working_sha256(session_id),
            }
        capabilities = self.get_capabilities()
        return {
            "server": "diptrace-mcp",
            "version": __version__,
            "configuration": self.settings.as_dict(),
            "active_session": active,
            "last_session_transition": self.sessions.last_session_transition(),
            "model_cache": self.models.stats(),
            "capabilities": capabilities,
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
        effective_trust = self.resolve_effective_document_trust(
            target.path,
            snapshot.info.sha256,
        )
        report = build_capability_report(
            snapshot,
            workflow_prompt_names=self._workflow_prompt_names,
            document_trust={
                "validation_level": effective_trust.validation_level.value,
                "trust_authority": effective_trust.authority,
                "requires_diptrace_verification": (effective_trust.requires_diptrace_verification),
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
        """Disclose the exact repository-owned high-trust registry state."""

        return self._trusted_provenance_registry.report()

    def _add_runtime_capabilities(self, report: dict[str, Any]) -> dict[str, Any]:
        """Add configured adapter, resource-limit and policy state once."""

        probe = self.external_jobs.freerouting.probe()
        report["external_adapters"]["freerouting"] = probe.as_dict()
        report["external_adapters"]["ngspice"] = self.external_jobs.ngspice.probe().as_dict()
        openems_probe = self.external_jobs.openems.probe()
        report["external_adapters"]["openems"] = openems_probe.as_dict()
        report["limits"]["max_document_bytes"] = self.settings.max_document_bytes
        report["limits"]["max_model_cache_bytes"] = self.settings.model_cache_max_bytes
        report["limits"]["max_external_log_bytes"] = self.settings.max_external_log_bytes
        report["limits"]["max_external_processes"] = self.settings.max_external_processes
        report["limits"]["max_external_result_bytes"] = self.settings.max_external_result_bytes
        report["limits"]["max_board_model_response_bytes"] = BOARD_MODEL_RESPONSE_BYTE_LIMIT
        report["limits"]["max_board_model_item_detail_bytes"] = BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT
        report["limits"]["max_raw_edit_response_bytes"] = RAW_EDIT_RESPONSE_BYTE_LIMIT
        report["limits"]["max_raw_edit_xpath_characters"] = RAW_EDIT_XPATH_CHARACTER_LIMIT
        report["limits"]["max_diff_lines"] = DEFAULT_DIFF_LINE_LIMIT
        report["limits"]["max_diff_characters"] = DEFAULT_DIFF_CHARACTER_LIMIT
        report["limits"]["max_preview_copper_records"] = PREVIEW_COPPER_RECORD_LIMIT
        report["limits"]["max_preview_copper_points"] = PREVIEW_COPPER_POINT_LIMIT
        report["limits"]["retention_max_records"] = self.settings.retention_max_records
        report["limits"]["retention_max_age_days"] = self.settings.retention_max_age_days
        report["limits"]["live_session_ttl_seconds"] = self.settings.live_session_ttl_seconds
        registry_report = self.trusted_provenance_registry_report()
        report["trust_model"]["trusted_registry"] = registry_report
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

    def document_info(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        info = self.models.get(document, live_session=target.is_live).info
        result = info.model_dump()
        # Revalidate trust through the central resolver (§8)
        effective = self.resolve_effective_document_trust(target.path, info.sha256)
        result["validation_level"] = effective.validation_level.value
        result["requires_diptrace_verification"] = effective.requires_diptrace_verification
        result["trust_authority"] = effective.authority
        if effective.evidence_manifest_path:
            result["evidence_manifest_path"] = effective.evidence_manifest_path
        if effective.evidence_manifest_sha256:
            result["evidence_manifest_sha256"] = effective.evidence_manifest_sha256
        if effective.warnings:
            result["trust_warnings"] = effective.warnings
        return self._read_success(info, result)

    def board_model(
        self,
        path: str | None = None,
        *,
        section: BoardModelSection = "summary",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.board_model(path, section=section, offset=offset, limit=limit)

    def schematic_model(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.schematic_model(path)

    def library_model(self, path: str) -> dict[str, Any]:
        return self._bom_service.library_model(path)

    def scan_component_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._discovery_service._scan_libraries("DipTrace-ComponentLibrary", root, recursive)

    def scan_pattern_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._discovery_service._scan_libraries("DipTrace-PatternLibrary", root, recursive)

    def query_library_items(
        self,
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._bom_service.query_library_items(path, query, offset, limit)

    def get_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.get_library_component(path, stable_id_value, name)

    def get_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.get_library_pattern(path, stable_id_value, name)

    def validate_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_library_component(path, stable_id_value, name)

    def validate_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_library_pattern(path, stable_id_value, name)

    def validate_pin_pad_mapping(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_pin_pad_mapping(path, stable_id_value, name)

    def get_bom(
        self,
        path: str | None = None,
        *,
        grouped: bool = False,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self._bom_service.get_bom(path, grouped=grouped, include_dnp=include_dnp)

    def export_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self._export_service.export_bom(path, include_dnp=include_dnp)

    def export_fabrication_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        return self._export_service.export_fabrication_outputs(
            path, include_dnp=include_dnp, request_native_outputs=request_native_outputs
        )

    def export_assembly_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = False,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        return self._export_service.export_assembly_outputs(
            path, include_dnp=include_dnp, request_native_outputs=request_native_outputs
        )

    def _export_release_manifest(
        self,
        path: str | None,
        *,
        export_type: Literal["fabrication_manifest", "assembly_manifest"],
        include_dnp: bool,
    ) -> dict[str, Any]:
        return self._export_service._export_release_manifest(
            path, export_type=export_type, include_dnp=include_dnp
        )

    def review_bom(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.review_bom(path)

    def compare_bom_to_design(
        self,
        external_records: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.compare_bom_to_design(external_records, path=path)

    def find_missing_component_fields(
        self,
        required_fields: list[str],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.find_missing_component_fields(required_fields, path=path)

    def group_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self._bom_service.group_bom(path, include_dnp=include_dnp)

    def detect_duplicate_bom_items(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.detect_duplicate_bom_items(path)

    def validate_mpn_consistency(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.validate_mpn_consistency(path)

    def validate_value_pattern_consistency(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.validate_value_pattern_consistency(path)

    def compare_schematic_to_pcb(self, schematic_path: str, pcb_path: str) -> dict[str, Any]:
        schematic_document, schematic_target = self.load(schematic_path)
        pcb_document, pcb_target = self.load(pcb_path)
        schematic = self.models.get(schematic_document, live_session=schematic_target.is_live)
        pcb = self.models.get(pcb_document, live_session=pcb_target.is_live)
        result = compare_design_snapshots(schematic, pcb)
        return self._read_success(
            schematic.info,
            {
                **result,
                "pcb_document": pcb.info.model_dump(mode="json"),
            },
            limitations=result["limitations"],
        )

    def sync_schematic_to_pcb(
        self,
        schematic_path: str,
        pcb_path: str,
        *,
        component_mappings: list[dict[str, Any]] | None = None,
        placement: dict[str, Any] | None = None,
        pattern_library_paths: list[str] | None = None,
        update_existing_properties: bool = True,
        create_ratlines: bool = True,
        allow_reconnect: bool = False,
        reconciliation_mode: Literal["additive", "exact"] = "additive",
        allow_locked_reconciliation: bool = False,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        schematic_document, _ = self.load(schematic_path)
        pcb_document, _ = self.load(pcb_path)
        pattern_documents = [self.load(path)[0] for path in pattern_library_paths or []]
        plan = build_sync_plan(
            schematic_document,
            pcb_document,
            mappings=[
                ComponentSyncMapping.model_validate(item) for item in component_mappings or []
            ],
            placement=SyncPlacement.model_validate(placement or {}),
            pattern_documents=pattern_documents,
            update_existing_properties=update_existing_properties,
            create_ratlines=create_ratlines,
            allow_reconnect=allow_reconnect,
            reconciliation_mode=reconciliation_mode,
            allow_locked_reconciliation=allow_locked_reconciliation,
        )
        response = self._run_semantic_write(
            plan.operation,
            pcb_path,
            dry_run,
            expected_sha256,
            txid,
        )
        response["warnings"] = [*plan.warnings, *response.get("warnings", [])]
        response["limitations"] = [
            *plan.limitations,
            *response.get("limitations", []),
        ]
        response.setdefault("result", {})["schematic_source"] = {
            "path": str(schematic_document.path),
            "sha256": schematic_document.sha256,
        }
        return response

    def query_objects(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "stable_id",
    ) -> dict[str, Any]:
        return self._document_service.query_objects(path, selector, offset, limit, sort_by)

    def get_object(self, stable_id_value: str, path: str | None = None) -> dict[str, Any]:
        return self._document_service.get_object(stable_id_value, path)

    def get_connectivity_graph(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.get_connectivity_graph(path)

    def document_resource(self, document_id: str, resource: str) -> str:
        return self._document_service.document_resource(document_id, resource)

    def transaction_summary_resource(self, txid: str) -> str:
        return json.dumps(
            transaction_response_summary(self.transactions.read(txid)),
            ensure_ascii=False,
            indent=2,
        )

    def raw_preview_diff_resource(self, preview_id: str) -> str:
        return self.raw_previews.read_diff(preview_id)

    def summarize(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.summarize(path)

    def components(
        self,
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.components(path, query, offset, limit)

    def component(self, refdes: str, path: str | None = None) -> dict[str, Any]:
        return self._document_service.component(refdes, path)

    def nets(
        self,
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.nets(path, query, include_endpoints, offset, limit)

    def rules(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.rules(path)

    def read_xml(
        self,
        path: str | None = None,
        xpath: str = ".",
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        return self._document_service.read_xml(path, xpath, max_matches, max_characters)

    def apply_edits(
        self,
        edits: list[XmlEdit],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=dry_run, operation="apply_xml_edits")
        if len(edits) > 50:
            raise EditError("A single call can contain at most 50 edits")
        if not dry_run and not expected_sha256:
            raise EditError("expected_sha256 from a dry-run is required when dry_run=false")
        document, target = self.load(path)
        before = document.raw_bytes
        before_document = DipTraceDocument.from_bytes(document.path, before)
        before_sha256 = sha256_bytes(before)
        if expected_sha256 and before_sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {before_sha256}",
                details={"expected_sha256": expected_sha256, "current_sha256": before_sha256},
            )
        after, previews = document.apply_edits(edits)
        impact = write_impact(before_document, document)
        require_write_impact(impact, operation="apply_xml_edits")
        after_sha256 = sha256_bytes(after)
        changed = before != after
        if not dry_run and changed:
            assert expected_sha256 is not None
            self._require_current_target_sha256(target.path, expected_sha256)
        diff, diff_metadata = unified_xml_diff_preview(before, after)
        preview_id, diff_resource = self.raw_previews.store(diff, diff_metadata)
        bounded_previews = _bounded_raw_edit_previews(previews)
        result: dict[str, Any] = {
            "path": str(target.path),
            "live_session": target.is_live,
            "session_id": target.live_session_id,
            "dry_run": dry_run,
            "changed": changed,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "operations": bounded_previews,
            "operations_metadata": {
                "edit_count": len(bounded_previews),
                "total_match_count": sum(int(preview["matches"]) for preview in bounded_previews),
                "snippets_inline": False,
                "xpath_character_limit": RAW_EDIT_XPATH_CHARACTER_LIMIT,
            },
            "changed_ids": list(impact.changed_ids),
            "write_object_count": impact.object_count,
            "diff": {
                "inline": False,
                "preview_id": preview_id,
                "resource_uri": diff_resource,
                "mime_type": "text/plain",
                **diff_metadata,
            },
            "resources": [diff_resource],
        }
        if dry_run or not changed:
            result["written"] = False
            return _finalize_raw_edit_response(result)

        # Refuse before touching the design if even worst-case bounded write
        # metadata could exceed the public response contract. JSON escaping can
        # expand one character to six bytes, hence the control-character probe.
        preflight = dict(result)
        preflight.update(
            {
                "written": True,
                "backup": "\x00" * 4_096,
                "backup_character_count": 4_096,
                "backup_truncated": True,
                "written_at": utc_now(),
            }
        )
        _finalize_raw_edit_response(preflight)

        assert expected_sha256 is not None
        if target.live_session_id:

            def finalize_live_raw_edit(_mutation: object) -> None:
                DipTraceDocument.load(target.path, self.settings.max_document_bytes)
                sidecar_path = target.path.with_suffix(target.path.suffix + ".provenance.json")
                try:
                    previous_sidecar = sidecar_path.read_bytes()
                except FileNotFoundError:
                    previous_sidecar = None
                prepared = self._invalidated_document_provenance(
                    target.path,
                    after_sha256,
                    operation_name="mcp_apply_xml_edits",
                )
                attempted_sidecar = prepared.model_dump_json(indent=2).encode()
                try:
                    self._write_provenance_sidecar(target.path, prepared)
                except Exception:
                    try:
                        current_sidecar = sidecar_path.read_bytes()
                    except FileNotFoundError:
                        current_sidecar = None
                    if current_sidecar == attempted_sidecar:
                        if previous_sidecar is None:
                            sidecar_path.unlink(missing_ok=True)
                        else:
                            atomic_write_bytes(sidecar_path, previous_sidecar)
                    raise

            mutation = self.sessions.mutate_working(
                target.live_session_id,
                expected_sha256=expected_sha256,
                replacement=after,
                after_write=finalize_live_raw_edit,
            )
            backup = mutation.backup
        else:
            self._require_current_target_sha256(target.path, expected_sha256)
            backup = write_with_backup(
                target.path,
                after,
                self.backups,
                expected_sha256=expected_sha256,
            )
            DipTraceDocument.load(target.path, self.settings.max_document_bytes)
            # Invalidate trust after MCP modification
            self.invalidate_document_trust_after_write(
                target.path,
                after_sha256,
                operation_name="mcp_apply_xml_edits",
            )
        backup_text = str(backup)
        backup_preview, backup_truncated = _bounded_text(backup_text, 4_096)
        result.update(
            {
                "written": True,
                "backup": backup_preview,
                "backup_character_count": len(backup_text),
                "backup_truncated": backup_truncated,
                "written_at": utc_now(),
            }
        )
        return _finalize_raw_edit_response(result)

    def create_document(
        self,
        kind: str,
        path: str,
        *,
        sheets: list[str] | None = None,
        pcb: dict[str, Any] | None = None,
        units: str = "mm",
        format_version: str = DEFAULT_FORMAT_VERSION,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a brand-new synthetic DipTrace-shaped XML document."""
        return self._scaffolding_service.create_document(
            kind,
            path,
            sheets=sheets,
            pcb=pcb,
            units=units,
            format_version=format_version,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )

    def create_document_from_seed(
        self,
        seed_path: str,
        target_path: str,
        *,
        expected_seed_sha256: str | None = None,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a new document by copying an existing DipTrace-shaped XML seed.

        The seed file must be valid DipTrace XML (PCB, Schematic, ComponentLibrary,
        or PatternLibrary). The copy preserves all unknown XML, line endings, and
        unsupported sections.

        **Trust model:** The client cannot assign a validation level.  Trust is
        derived exclusively from verifiable metadata (provenance sidecar or
        fixture manifest) found alongside the seed.  If no metadata is present,
        the copy defaults to ``synthetic_parser_only``.
        """
        return self._scaffolding_service.create_document_from_seed(
            seed_path,
            target_path,
            expected_seed_sha256=expected_seed_sha256,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )

    def begin_transaction(
        self,
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._transaction_service.begin_transaction(path, expected_sha256, notes)

    def stage_operations(self, txid: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        return self._transaction_service.stage_operations(txid, operations)

    def preview_transaction(self, txid: str) -> dict[str, Any]:
        return self._transaction_service.preview_transaction(txid)

    def validate_transaction(self, txid: str) -> dict[str, Any]:
        return self._transaction_service.validate_transaction(txid)

    def commit_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        return self._transaction_service.commit_transaction(
            txid, expected_sha256, _live_session_id=_live_session_id, _live_guard=_live_guard
        )

    def rollback_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        return self._transaction_service.rollback_transaction(
            txid, expected_sha256, _live_session_id=_live_session_id, _live_guard=_live_guard
        )

    def list_transactions(self) -> dict[str, Any]:
        return self._transaction_service.list_transactions()

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
        """Validate evidence roles once for both read-only preview and recording."""
        return self._evidence_service._evaluate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

    @staticmethod
    def _semantic_evidence_record(
        comparison: dict[str, Any] | None,
    ) -> SemanticComparisonEvidence | None:
        return EvidenceService._semantic_evidence_record(comparison)

    def _require_evidence_evaluation_unchanged(
        self,
        evaluation: RoundtripEvidenceEvaluation,
    ) -> None:
        """Repeat allowed-root, bounded-parse, role, and SHA gates before writes."""
        return self._evidence_service._require_evidence_evaluation_unchanged(evaluation)

    @staticmethod
    def _evidence_manifest_path(document_path: Path) -> Path:
        return EvidenceService._evidence_manifest_path(document_path)

    @staticmethod
    def _evidence_sidecar_path(document_path: Path) -> Path:
        return EvidenceService._evidence_sidecar_path(document_path)

    @classmethod
    def _require_evidence_output_paths_safe(
        cls,
        evaluation: RoundtripEvidenceEvaluation,
    ) -> None:
        """Refuse metadata outputs that alias a document or evidence input."""
        return EvidenceService._require_evidence_output_paths_safe(evaluation)

    def _roundtrip_evidence_response(
        self,
        evaluation: RoundtripEvidenceEvaluation,
        *,
        written: bool,
        manifest_path: Path | None = None,
        manifest_sha256: str | None = None,
    ) -> dict[str, Any]:
        return self._evidence_service._roundtrip_evidence_response(
            evaluation,
            written=written,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
        )

    def validate_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None = None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Validate SHA-bound user evidence without writing any file."""
        return self._evidence_service.validate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

    def record_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None = None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Write user-supplied evidence metadata without granting high trust."""
        return self._evidence_service.record_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

    def move_components(
        self,
        selector: dict[str, Any] | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        grid_snap: float | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_components(
            selector,
            dx,
            dy,
            absolute_x,
            absolute_y,
            path,
            dry_run,
            expected_sha256,
            txid,
            grid_snap,
            allow_locked,
        )

    def set_component_value(
        self,
        selector: dict[str, Any] | None,
        value: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_value(
            selector, value, path, dry_run, expected_sha256, txid
        )

    def rotate_components(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allowed_angles: list[float] | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rotate_components(
            selector,
            angle_deg,
            mode,
            path,
            dry_run,
            expected_sha256,
            txid,
            allowed_angles,
            allow_locked,
        )

    def set_component_side(
        self,
        selector: dict[str, Any] | None,
        side: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_side(
            selector, side, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_component_lock(
        self,
        selector: dict[str, Any] | None,
        locked: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_lock(
            selector, locked, path, dry_run, expected_sha256, txid
        )

    def set_component_properties(
        self,
        selector: dict[str, Any] | None,
        *,
        name: str | None = None,
        value: str | None = None,
        refdes: str | None = None,
        fields: dict[str, str] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_properties(
            selector,
            name=name,
            value=value,
            refdes=refdes,
            fields=fields,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def set_component_pattern(
        self,
        selector: dict[str, Any],
        pattern_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_pattern(
            selector,
            pattern_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def align_components(
        self,
        selector: dict[str, Any],
        alignment: str,
        *,
        target_value: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.align_components(
            selector,
            alignment,
            target_value=target_value,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def distribute_components(
        self,
        selector: dict[str, Any],
        axis: str,
        *,
        mode: str = "centers",
        spacing: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.distribute_components(
            selector,
            axis,
            mode=mode,
            spacing=spacing,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def group_components(
        self,
        selector: dict[str, Any],
        *,
        group_id: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.group_components(
            selector,
            group_id=group_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def ungroup_components(
        self,
        selector: dict[str, Any],
        *,
        remove_empty_groups: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.ungroup_components(
            selector,
            remove_empty_groups=remove_empty_groups,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def list_board_texts(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.list_board_texts(path, selector)

    def move_board_texts(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_board_texts(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def rotate_board_texts(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rotate_board_texts(
            selector, angle_deg, mode, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_text_visibility(
        self,
        selector: dict[str, Any] | None,
        visibility: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_text_visibility(
            selector, visibility, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_text_style(
        self,
        selector: dict[str, Any] | None,
        *,
        font_size: int | None = None,
        font_width: float | None = None,
        horizontal_align: str | None = None,
        vertical_align: str | None = None,
        mirrored: bool | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_text_style(
            selector,
            font_size=font_size,
            font_width=font_width,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            mirrored=mirrored,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def set_pin_no_connect(
        self,
        selector: dict[str, Any] | None,
        no_connect: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_pin_no_connect(
            selector, no_connect, path, dry_run, expected_sha256, txid
        )

    def rename_net(
        self,
        selector: dict[str, Any] | None,
        new_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rename_net(
            selector, new_name, path, dry_run, expected_sha256, txid
        )

    def add_sheet(
        self,
        name: str,
        sheet_type: str = "Normal",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_sheet(
            name, sheet_type, path, dry_run, expected_sha256, txid
        )

    def place_part(
        self,
        component_style: str,
        refdes: str,
        x: float,
        y: float,
        *,
        pin_count: int,
        name: str | None = None,
        value: str = "",
        sheet: int = 0,
        angle_deg: float = 0.0,
        component_part: int = 0,
        part_number: int = 0,
        part_refdes: str | None = None,
        part_name: str | None = None,
        allow_shared_refdes: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.place_part(
            component_style,
            refdes,
            x,
            y,
            pin_count=pin_count,
            name=name,
            value=value,
            sheet=sheet,
            angle_deg=angle_deg,
            component_part=component_part,
            part_number=part_number,
            part_refdes=part_refdes,
            part_name=part_name,
            allow_shared_refdes=allow_shared_refdes,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def connect_pins(
        self,
        net: str,
        pins: list[dict[str, Any]],
        allow_reconnect: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.connect_pins(
            net, pins, allow_reconnect, path, dry_run, expected_sha256, txid
        )

    def disconnect_pins(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.disconnect_pins(
            selector, path, dry_run, expected_sha256, txid
        )

    def add_wire(
        self,
        net: str,
        points: list[dict[str, Any]],
        start: dict[str, Any],
        end: dict[str, Any],
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_wire(
            net, points, start, end, sheet, hidden_power, path, dry_run, expected_sha256, txid
        )

    def delete_wire(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_wire(
            selector, path, dry_run, expected_sha256, txid
        )

    def add_net_label(
        self,
        net: str,
        x: float,
        y: float,
        sheet: int = 0,
        text: str | None = None,
        font_size: int = 10,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_net_label(
            net, x, y, sheet, text, font_size, path, dry_run, expected_sha256, txid
        )

    def set_panelization(
        self,
        panel: dict[str, Any],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_panelization(
            panel, path, dry_run, expected_sha256, txid
        )

    def clear_panelization(
        self,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.clear_panelization(
            path, dry_run, expected_sha256, txid
        )

    def update_net_class_rules(
        self,
        class_name: str,
        *,
        layer: str | None = None,
        width: float | None = None,
        min_width: float | None = None,
        max_width: float | None = None,
        clearance: float | None = None,
        neck_width: float | None = None,
        differential_gap: float | None = None,
        max_uncoupled_length: float | None = None,
        tolerance: float | None = None,
        check_length: bool | None = None,
        fixed_length: float | None = None,
        length_delta: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.update_net_class_rules(
            class_name,
            layer=layer,
            width=width,
            min_width=min_width,
            max_width=max_width,
            clearance=clearance,
            neck_width=neck_width,
            differential_gap=differential_gap,
            max_uncoupled_length=max_uncoupled_length,
            tolerance=tolerance,
            check_length=check_length,
            fixed_length=fixed_length,
            length_delta=length_delta,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def assign_nets_to_class(
        self,
        selector: dict[str, Any] | None,
        class_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.assign_nets_to_class(
            selector, class_name, path, dry_run, expected_sha256, txid
        )

    def list_testpoints(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.list_testpoints(path, selector)

    def find_testpoint_candidates(
        self,
        target_nets: list[str],
        *,
        path: str | None = None,
        side: str = "Top",
        probe_diameter: float = 1.0,
        clearance: float = 0.5,
        grid: float = 2.54,
        candidates_per_net: int = 10,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.find_testpoint_candidates(
            target_nets,
            path=path,
            side=side,
            probe_diameter=probe_diameter,
            clearance=clearance,
            grid=grid,
            candidates_per_net=candidates_per_net,
        )

    def add_testpoints(
        self,
        testpoints: list[dict[str, Any]],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_testpoints(
            testpoints, path, dry_run, expected_sha256, txid
        )

    def move_testpoints(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        grid_snap: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_testpoints(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            grid_snap=grid_snap,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def remove_testpoints(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.remove_testpoints(
            selector, path, dry_run, expected_sha256, txid, allow_locked
        )

    def review_testpoint_coverage(
        self,
        target_nets: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.review_testpoint_coverage(target_nets, path)

    def add_trace(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[dict[str, Any]],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_trace(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            points=points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def replace_trace(
        self,
        trace_id: str,
        points: list[dict[str, Any]],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.replace_trace(
            trace_id,
            points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def delete_trace(
        self,
        selector: dict[str, Any],
        *,
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_trace(
            selector,
            allow_connectivity_regression=allow_connectivity_regression,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def set_trace_width(
        self,
        selector: dict[str, Any],
        width: float,
        *,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_trace_width(
            selector,
            width,
            segment_indices=segment_indices,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def add_via(
        self,
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        *,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_via(
            trace_id,
            x,
            y,
            via_style,
            layer_before=layer_before,
            layer_after=layer_after,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def move_via(
        self,
        selector: dict[str, Any],
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_via(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def delete_via(
        self,
        selector: dict[str, Any],
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_via(
            selector, path=path, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

    def set_via_style(
        self,
        selector: dict[str, Any],
        via_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_via_style(
            selector,
            via_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def list_unrouted_connections(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.list_unrouted_connections(path, nets=nets)

    def get_route_details(
        self,
        *,
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.get_route_details(trace_id=trace_id, net=net, path=path)

    def get_stackup(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.get_stackup(path)

    def measure_net_lengths(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        return self._review_service.measure_net_lengths(
            path,
            nets=nets,
            effective_dielectric_constant=effective_dielectric_constant,
        )

    def analyze_length_group(
        self,
        nets: list[str],
        *,
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_length_group(nets, tolerance_mm=tolerance_mm, path=path)

    def list_differential_pairs(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._review_service.list_differential_pairs(path, offset=offset, limit=limit)

    def get_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.get_differential_pair(pair, path)

    def analyze_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_differential_pair(pair, path)

    def analyze_differential_pairs(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_differential_pairs(path)

    def validate_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.validate_differential_pair(pair, path)

    def calculate_impedance(
        self,
        *,
        structure: str,
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        return self._review_service.calculate_impedance(
            structure=structure,
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            gap_mm=gap_mm,
            frequency_hz=frequency_hz,
            target_ohm=target_ohm,
            tolerance_ohm=tolerance_ohm,
        )

    def suggest_trace_geometry_for_impedance(
        self,
        *,
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        return self._review_service.suggest_trace_geometry_for_impedance(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )

    def analyze_stackup_for_impedance(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_stackup_for_impedance(path)

    def validate_impedance_constraints(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.validate_impedance_constraints(constraints, path=path)

    def analyze_controlled_impedance_nets(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_controlled_impedance_nets(constraints, path=path)

    def list_copper_pours(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._review_service.list_copper_pours(path, offset=offset, limit=limit)

    def analyze_plane_continuity(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_plane_continuity(path)

    def analyze_return_path(
        self,
        path: str | None = None,
        *,
        stitching_radius_mm: float,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_return_path(
            path,
            stitching_radius_mm=stitching_radius_mm,
            nets=nets,
            reference_nets=reference_nets,
        )

    def route_connection(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        bend_cost: float = 0.2,
        preferred_layers: list[str] | None = None,
        start_layer: str | None = None,
        end_layer: str | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        max_detour: float = 3.0,
        max_nodes: int = 100_000,
        time_budget_ms: int = 5_000,
        avoid_component_bodies: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.route_connection(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers,
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def route_net(
        self,
        net: str,
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.route_net(
            net,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def route_diff_pair(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.route_diff_pair(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def plan_diff_pair_route(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.plan_diff_pair_route(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
        )

    def plan_route_nets(
        self,
        nets: list[str],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.plan_route_nets(
            nets,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
        )

    def apply_route_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._routing_service.apply_route_plan(
            plan_id, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

    def export_autorouter_dsn(
        self,
        path: str | None = None,
        *,
        design_name: str | None = None,
    ) -> dict[str, Any]:
        return self._external_jobs_service.export_autorouter_dsn(path, design_name=design_name)

    def run_external_autorouter(
        self,
        path: str | None = None,
        *,
        dsn_job_id: str | None = None,
        dsn_path: str | None = None,
        max_passes: int = 100,
        threads: int = 1,
        timeout_seconds: int | None = None,
        ignore_net_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._external_jobs_service.run_external_autorouter(
            path,
            dsn_job_id=dsn_job_id,
            dsn_path=dsn_path,
            max_passes=max_passes,
            threads=threads,
            timeout_seconds=timeout_seconds,
            ignore_net_classes=ignore_net_classes,
        )

    def inspect_autorouter_result(
        self,
        jobid: str,
        path: str | None = None,
        *,
        via_style: str | None = None,
    ) -> dict[str, Any]:
        return self._external_jobs_service.inspect_autorouter_result(
            jobid, path, via_style=via_style
        )

    def import_autorouter_ses(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._external_jobs_service.import_autorouter_ses(
            plan_id, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

    def route_connections(
        self,
        connections: list[dict[str, Any]],
        *,
        ripup_retry: bool = True,
        max_ripup_attempts: int = 4,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route multiple connections sequentially with bounded rip-up/retry."""
        return self._routing_service.route_connections(
            connections,
            ripup_retry=ripup_retry,
            max_ripup_attempts=max_ripup_attempts,
            ordering=ordering,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def analyze_routing_congestion(
        self,
        connections: list[dict[str, Any]],
        *,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
    ) -> dict[str, Any]:
        """Rank routing connections deterministically without changing the document."""
        return self._routing_service.analyze_routing_congestion(
            connections, ordering=ordering, path=path
        )

    def run_ngspice_simulation(
        self,
        *,
        netlist: str | None = None,
        netlist_path: str | None = None,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Run a user-supplied ngspice netlist as a bounded external batch job."""
        return self._external_jobs_service.run_ngspice_simulation(
            netlist=netlist, netlist_path=netlist_path, path=path, timeout_seconds=timeout_seconds
        )

    def run_openems_stripline_analysis(
        self,
        *,
        width_mm: float,
        copper_thickness_mm: float,
        lower_dielectric_height_mm: float,
        upper_dielectric_height_mm: float,
        dielectric_constant: float,
        frequencies_hz: list[float],
        dielectric_loss_tangent: float = 0.0,
        conductor_conductivity_s_per_m: float = 58_000_000.0,
        trace_length_mm: float = 20.0,
        port_impedance_ohm: float = 50.0,
        mesh_cells_per_wavelength: int = 30,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Start a bounded off-center/centered stripline field-solver job."""
        return self._external_jobs_service.run_openems_stripline_analysis(
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            lower_dielectric_height_mm=lower_dielectric_height_mm,
            upper_dielectric_height_mm=upper_dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            frequencies_hz=frequencies_hz,
            dielectric_loss_tangent=dielectric_loss_tangent,
            conductor_conductivity_s_per_m=conductor_conductivity_s_per_m,
            trace_length_mm=trace_length_mm,
            port_impedance_ohm=port_impedance_ohm,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
            path=path,
            timeout_seconds=timeout_seconds,
        )

    def get_job_status(self, jobid: str) -> dict[str, Any]:
        return self._job_service.get_job_status(jobid)

    def get_job_result(self, jobid: str) -> dict[str, Any]:
        return self._job_service.get_job_result(jobid)

    def cancel_job(self, jobid: str) -> dict[str, Any]:
        return self._job_service.cancel_job(jobid)

    def list_jobs(self, status: str | None = None) -> dict[str, Any]:
        return self._job_service.list_jobs(status)

    def list_exports(self) -> dict[str, Any]:
        return self._export_service.list_exports()

    def export_resource(self, export_id: str, artifact: str) -> str:
        return self._export_service.export_resource(export_id, artifact)

    def job_resource(self, jobid: str, artifact: str) -> str:
        return self._job_service.job_resource(jobid, artifact)

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
        return self._placement_service.plan_silkscreen(
            path,
            selector=selector,
            clearance=clearance,
            board_edge_clearance=board_edge_clearance,
            grid=grid,
            search_steps=search_steps,
            include_board_texts=include_board_texts,
            avoid_component_bodies=avoid_component_bodies,
        )

    def analyze_placement(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        return self._placement_service.analyze_placement(
            path, selector=selector, spacing=spacing, board_edge_clearance=board_edge_clearance
        )

    def generate_placement_candidates(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        return self._placement_service.generate_placement_candidates(selector, path, **options)

    def score_placement(
        self,
        placements: list[dict[str, Any]],
        path: str | None = None,
        *,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        return self._placement_service.score_placement(
            placements,
            path,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=weights,
        )

    def plan_component_placement(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        return self._placement_service.plan_component_placement(selector, path, **options)

    def apply_component_placement_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._placement_service.apply_component_placement_plan(
            plan_id, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

    def apply_silkscreen_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._placement_service.apply_silkscreen_plan(
            plan_id, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

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
                "Document changed after the silkscreen plan was generated",
                details={
                    "plan_sha256": plan.source_sha256,
                    "current_sha256": document.sha256,
                },
            )
        if expected_sha256 is not None and expected_sha256 != plan.source_sha256:
            raise Sha256MismatchError(
                "Provided SHA does not match the silkscreen plan source",
                details={
                    "plan_sha256": plan.source_sha256,
                    "provided_sha256": expected_sha256,
                },
            )
        operations = parse_semantic_operations(plan.operations)
        if not operations:
            raise EditError("Silkscreen plan contains no changes")
        response = self._run_semantic_operations(
            operations,
            str(target_path),
            dry_run,
            expected_sha256,
            txid,
        )
        transaction = response.get("transaction") or {}
        transaction_id = transaction.get("txid")
        status: PlanStatus = "committed" if transaction.get("status") == "committed" else "staged"
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
                f"Unknown plan resource: {resource}", code="object_not_found"
            ) from exc
        if not resource_path.is_file():
            raise DocumentError(
                f"Plan resource is unavailable: {resource}", code="object_not_found"
            )
        return resource_path.read_text(encoding="utf-8")

    def run_review(
        self,
        path: str | None = None,
        *,
        profile: str,
        categories: set[str] | None = None,
    ) -> dict[str, Any]:
        return self._review_service.run_review(path, profile=profile, categories=categories)

    def get_findings(self, report_id: str) -> dict[str, Any]:
        return self._review_service.get_findings(report_id)

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        return self._review_service.get_finding(finding_id)

    def review_resource(self, report_id: str) -> str:
        return self._review_service.review_resource(report_id)

    def findings_resource(self, document_id: str) -> str:
        return self._review_service.findings_resource(document_id)

    def finish_live_session(
        self,
        action: SessionAction,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        if action == "apply":
            self.policy.require_write(dry_run=False, operation="finish_live_session")
        request = self.sessions.request_finish(action, expected_sha256)
        return self.sessions.wait_for_finish_outcome(request)

    def abandon_live_session(self, reason: str) -> dict[str, Any]:
        """Terminate stale local session state without applying working XML."""

        metadata = self.sessions.abandon_active(reason)
        return {
            "session_id": metadata["session_id"],
            "outcome": "abandoned",
            "local_bridge_status": "abandoned",
            "written": False,
            "reason": metadata["abandon_reason"],
            "diptrace_host_acknowledged": False,
            "acknowledgement_scope": "local_session_state_only",
            "message": (
                "The local session was abandoned without applying working XML or "
                "replacing the exchange file."
            ),
        }

    def scan_documents(self, root: str | None = None, recursive: bool = True) -> dict[str, Any]:
        return self._discovery_service.scan_documents(root, recursive)

    def _scan_libraries(
        self,
        source_type: str,
        root: str | None,
        recursive: bool,
    ) -> dict[str, Any]:
        return self._discovery_service._scan_libraries(source_type, root, recursive)

    def _get_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        return self._bom_service._get_library_item(path, kind, stable_id_value, name)

    def _validate_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        return self._bom_service._validate_library_item(path, kind, stable_id_value, name)

    def _run_semantic_write(
        self,
        operation: SemanticOperation,
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        return self._run_semantic_operations([operation], path, dry_run, expected_sha256, txid)

    def _run_semantic_operations(
        self,
        operations: Sequence[SemanticOperation],
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        if not operations:
            raise EditError("At least one semantic operation is required")
        self.policy.require_write(
            dry_run=dry_run,
            operation=operations[0].kind if len(operations) == 1 else "semantic_operations",
        )
        if not dry_run and expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required for semantic writes",
                txid=txid,
            )
        incoming_operations = [operation.model_dump() for operation in operations]
        _require_transaction_capacity(len(incoming_operations))
        if txid is None:
            document, target = self.load(path)
            snapshot = build_snapshot(document, live_session=target.is_live)
            if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
                raise Sha256MismatchError(
                    "Document changed before the semantic operation was planned",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": snapshot.info.sha256,
                    },
                )
            _apply_bounded_semantic_operations(
                document,
                list(operations),
                live_session=target.is_live,
            )
            tx_record = self.transactions.create(
                snapshot.info,
                target.path,
                source_sha256=snapshot.info.sha256,
                expected_sha256=expected_sha256 or snapshot.info.sha256,
                notes=[operation.kind for operation in operations],
            )
            txid = tx_record.txid
            self.transactions.store_snapshot(txid, document.raw_bytes)
            self.transactions.update(
                txid,
                status="staged",
                operations=incoming_operations,
                compiled_patch_count=len(operations),
                snapshot_path=str(self.transactions.snapshot_path(txid)),
            )
        else:
            existing = self.transactions.read(txid)
            if existing.status not in {"staged", "validated"}:
                raise TransactionConflictError(
                    f"Transaction cannot be edited in state {existing.status}: {txid}",
                    txid=txid,
                )
            if path is not None:
                supplied_target = self.resolve_target(path)
                if supplied_target.path != Path(existing.target_path):
                    raise TransactionConflictError(
                        "The supplied path does not match the transaction target",
                        details={
                            "transaction_path": existing.target_path,
                            "supplied_path": str(supplied_target.path),
                        },
                        txid=txid,
                    )
            combined_operations = (
                [*existing.operations, *incoming_operations]
                if existing.operations != incoming_operations
                else list(existing.operations)
            )
            _require_transaction_capacity(len(combined_operations))
            source = self._load_snapshot_record(existing)
            _apply_bounded_semantic_operations(
                source,
                parse_semantic_operations(combined_operations),
                live_session=(
                    self._session_id_from_working(Path(existing.target_path)) is not None
                ),
            )
            if existing.operations != incoming_operations:
                self.transactions.update(
                    txid,
                    status="staged",
                    operations=combined_operations,
                    compiled_patch_count=len(combined_operations),
                    snapshot_path=existing.snapshot_path
                    or str(self.transactions.snapshot_path(txid)),
                    changed_ids=[],
                    validation_before={},
                    validation_after_preview={},
                    preview_resources=[],
                    preview_metadata={},
                )
        preview = self.preview_transaction(txid)
        if dry_run:
            return preview
        return self.commit_transaction(
            txid,
            expected_sha256=expected_sha256,
        )

    def _preview_semantic_operations(
        self,
        document: DipTraceDocument,
        operations: list[SemanticOperation],
    ) -> dict[str, Any]:
        before = build_snapshot(document)
        result = _apply_bounded_semantic_operations(document, operations)
        after = build_snapshot(result.document)
        before_findings, _, _, _ = run_checks(before)
        after_findings, _, _, _ = run_checks(after)
        before_errors: dict[str, int] = {}
        after_errors: dict[str, int] = {}
        for finding in before_findings:
            if finding.severity == "error":
                before_errors[finding.category] = before_errors.get(finding.category, 0) + 1
        for finding in after_findings:
            if finding.severity == "error":
                after_errors[finding.category] = after_errors.get(finding.category, 0) + 1
        allow_connectivity_regression = any(
            (
                isinstance(operation, DeleteTraceOperation)
                and operation.allow_connectivity_regression
            )
            or isinstance(operation, SyncSchematicToPcbOperation)
            for operation in operations
        )
        if (
            after_errors.get("connectivity", 0) > before_errors.get("connectivity", 0)
            and not allow_connectivity_regression
        ):
            raise ConnectivityRegressionError(
                "Semantic preview introduces new connectivity errors",
                details={"before": before_errors, "after": after_errors},
                object_ids=result.changed_ids,
            )
        non_connectivity_categories = (set(before_errors) | set(after_errors)) - {"connectivity"}
        regressions = {
            category: {
                "before": before_errors.get(category, 0),
                "after": after_errors.get(category, 0),
            }
            for category in sorted(non_connectivity_categories)
            if after_errors.get(category, 0) > before_errors.get(category, 0)
        }
        if regressions:
            raise DrcRegressionError(
                "Semantic preview introduces new deterministic review errors",
                details={"regressions": regressions},
                object_ids=result.changed_ids,
            )
        svg = render_preview_svg(before, after, result.changed_ids)
        preview_json = render_preview_json(before, after, result.changed_ids)
        preview_json["review_validation"] = {
            "errors_before": before_errors,
            "errors_after": after_errors,
            "allow_connectivity_regression": allow_connectivity_regression,
        }
        diff, diff_metadata = unified_xml_diff_preview(
            before.document.raw_bytes,
            result.raw_bytes,
        )
        return {
            "svg": svg,
            "json": preview_json,
            "diff": diff,
            "diff_metadata": diff_metadata,
            "patch_count": result.patch_count,
            "changed_ids": result.changed_ids,
            "validation_before": {
                **before.info.model_dump(),
                "review_errors": before_errors,
            },
            "validation_after_preview": {
                **after.info.model_dump(),
                "review_errors": after_errors,
            },
            "warnings": result.warnings,
            "limitations": (
                ["geometry for components without footprint dimensions is estimated"]
                if before.info.kind == "pcb"
                else []
            ),
        }

    def _load_snapshot_record(self, record: TransactionRecord) -> DipTraceDocument:
        return self._transaction_service._load_snapshot_record(record)

    def _session_id_from_working(self, path: Path) -> str | None:
        return self._transaction_service._session_id_from_working(path)

    def _read_source_header(self, path: Path) -> dict[str, str] | None:
        return self._discovery_service._read_source_header(path)

    @staticmethod
    def _read_success(
        info: DocumentInfo,
        result: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        limitations: list[str] | None = None,
        resources: list[str] | None = None,
    ) -> dict[str, Any]:
        return read_success(
            info,
            result,
            warnings=warnings,
            limitations=limitations,
            resources=resources,
        )

    @staticmethod
    def _validate_page(offset: int, limit: int) -> None:
        validate_page(offset, limit)
