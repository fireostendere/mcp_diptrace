"""Transaction state machine and guarded semantic write commits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from ..adapters import build_snapshot
from ..capability_model import MAX_TRANSACTION_OPERATIONS
from ..domain import (
    _HIGH_TRUST_LEVELS,
    DocumentProvenance,
    FixtureValidationLevel,
    ProvenanceAuthority,
    TransactionRecord,
)
from ..errors import (
    ConfirmationRequiredError,
    DipTraceMcpError,
    EditError,
    RoundtripValidationError,
    Sha256MismatchError,
    TransactionConflictError,
)
from ..evidence_status import component_angle_evidence_warnings
from ..operations import SemanticOperation, parse_semantic_operations
from ..semantic_compiler import SemanticApplyResult, apply_semantic_operations
from ..services.context import (
    DocumentGateway,
    ServiceContext,
)
from ..services.context import (
    bounded_text as _bounded_text,
)
from ..sessions import LiveWorkingGuard, SessionStore
from ..transactions import (
    TransactionStore,
    default_risk,
    tx_preview_resources,
    tx_summary_resources,
)
from ..write_limits import require_write_impact, write_impact
from ..xml_document import (
    DipTraceDocument,
    sha256_bytes,
)

TRANSACTION_CHANGED_ID_PREVIEW_LIMIT = 500
TRANSACTION_MESSAGE_PREVIEW_LIMIT = 100
TRANSACTION_MESSAGE_CHARACTER_LIMIT = 1_000


class PreviewSemanticOperations(Protocol):
    def __call__(
        self,
        document: DipTraceDocument,
        operations: list[SemanticOperation],
    ) -> dict[str, Any]: ...


class RequireCurrentTargetSha256(Protocol):
    def __call__(self, target: Path, expected_sha256: str) -> None: ...


class AtomicWriteBytes(Protocol):
    def __call__(self, path: Path, data: bytes) -> None: ...


class InvalidateDocumentTrust(Protocol):
    def __call__(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str = "mcp_write",
    ) -> None: ...


class LoadAndValidateEvidenceManifest(Protocol):
    def __call__(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> Any: ...


class LoadAndAuthorizeTrustedRegistryEvidence(Protocol):
    def __call__(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> Any: ...


def _validation_response_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("document_id", "kind", "sha256", "review_errors")
        if key in value
    }


def _bounded_messages(values: list[str]) -> tuple[list[str], dict[str, Any]]:
    rendered: list[str] = []
    truncated_characters = False
    for value in values[:TRANSACTION_MESSAGE_PREVIEW_LIMIT]:
        bounded, truncated = _bounded_text(value, TRANSACTION_MESSAGE_CHARACTER_LIMIT)
        rendered.append(bounded)
        truncated_characters = truncated_characters or truncated
    return rendered, {
        "total_count": len(values),
        "returned_count": len(rendered),
        "truncated": len(rendered) < len(values) or truncated_characters,
    }


def _bounded_changed_ids(values: list[str]) -> dict[str, Any]:
    rendered = values[:TRANSACTION_CHANGED_ID_PREVIEW_LIMIT]
    return {
        "changed_ids": rendered,
        "changed_id_count": len(values),
        "changed_ids_truncated": len(rendered) < len(values),
    }


def transaction_response_summary(record: TransactionRecord) -> dict[str, Any]:
    """Return stable transaction state without echoing staged operation payloads."""

    changed_id_summary = _bounded_changed_ids(record.changed_ids)
    target_path, target_path_truncated = _bounded_text(record.target_path, 4_096)
    error: dict[str, Any] | None = None
    if record.error:
        error = {}
        if "code" in record.error:
            error["code"] = record.error["code"]
        message = record.error.get("message")
        if isinstance(message, str):
            error["message"], error["message_truncated"] = _bounded_text(
                message,
                TRANSACTION_MESSAGE_CHARACTER_LIMIT,
            )
    return {
        "txid": record.txid,
        "document_id": record.document_id,
        "status": record.status,
        "target_path": target_path,
        "target_path_truncated": target_path_truncated,
        "source_sha256": record.source_sha256,
        "expected_sha256": record.expected_sha256,
        "committed_sha256": record.committed_sha256,
        "rolled_back_sha256": record.rolled_back_sha256,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "operation_count": len(record.operations),
        "compiled_patch_count": record.compiled_patch_count,
        **changed_id_summary,
        "risk": record.risk.model_dump(mode="json"),
        "validation_before": _validation_response_summary(record.validation_before),
        "validation_after_preview": _validation_response_summary(record.validation_after_preview),
        "preview_resources": record.preview_resources,
        "preview_metadata": record.preview_metadata,
        "backup_available": record.backup_path is not None,
        "error": error,
        "note_count": len(record.notes),
        "summary_resource": f"diptrace://transaction/{record.txid}/summary",
        "operations_resource": f"diptrace://transaction/{record.txid}/operations",
    }


def _require_transaction_capacity(operation_count: int) -> None:
    if operation_count > MAX_TRANSACTION_OPERATIONS:
        raise EditError(
            "Transaction would exceed "
            f"{MAX_TRANSACTION_OPERATIONS} operations limit ({operation_count} staged)"
        )


def _apply_bounded_semantic_operations(
    document: DipTraceDocument,
    operations: list[SemanticOperation],
    *,
    live_session: bool = False,
) -> SemanticApplyResult:
    """Compile a semantic write and enforce the independent object cap."""

    result = apply_semantic_operations(
        document,
        operations,
        live_session=live_session,
    )
    impact = write_impact(
        document,
        result.document,
        compiler_changed_ids=result.changed_ids,
    )
    require_write_impact(impact, operation="semantic write")
    result.changed_ids = list(impact.changed_ids)
    return result


class TransactionService:
    """Implementation for guarded transaction lifecycle operations."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        transaction_store: TransactionStore,
        session_store: SessionStore,
        preview_semantic_operations: PreviewSemanticOperations,
        require_current_target_sha256: RequireCurrentTargetSha256,
        atomic_write_bytes: AtomicWriteBytes,
        invalidate_document_trust_after_write: InvalidateDocumentTrust,
        load_and_validate_evidence_manifest: LoadAndValidateEvidenceManifest,
        load_and_authorize_trusted_registry_evidence: LoadAndAuthorizeTrustedRegistryEvidence,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.transaction_store = transaction_store
        self.session_store = session_store
        self.preview_semantic_operations = preview_semantic_operations
        self.require_current_target_sha256 = require_current_target_sha256
        self.atomic_write_bytes = atomic_write_bytes
        self.invalidate_document_trust_after_write = invalidate_document_trust_after_write
        self.load_and_validate_evidence_manifest = load_and_validate_evidence_manifest
        self.load_and_authorize_trusted_registry_evidence = (
            load_and_authorize_trusted_registry_evidence
        )

    @staticmethod
    def _read_optional_transaction_file(
        path: Path,
        *,
        txid: str,
        phase: str,
    ) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise TransactionConflictError(
                f"Cannot read transaction-bound file during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "current_sha256": None,
                },
                txid=txid,
            ) from exc

    @classmethod
    def _require_optional_transaction_file_unchanged(
        cls,
        path: Path,
        expected: bytes | None,
        *,
        txid: str,
        phase: str,
    ) -> None:
        current = cls._read_optional_transaction_file(path, txid=txid, phase=phase)
        if current != expected:
            raise TransactionConflictError(
                f"Transaction-bound file changed during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "expected_sha256": (sha256_bytes(expected) if expected is not None else None),
                    "current_sha256": (sha256_bytes(current) if current is not None else None),
                },
                txid=txid,
            )

    def _compensate_transaction_file(
        self,
        path: Path,
        *,
        written: bytes,
        previous: bytes | None,
        txid: str,
        phase: str,
    ) -> None:
        """Restore pre-call bytes only while this call still owns the current bytes."""

        current = self._read_optional_transaction_file(path, txid=txid, phase=phase)
        if current == previous:
            return
        if current != written:
            raise TransactionConflictError(
                f"Refusing to overwrite unexpected bytes during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "written_sha256": sha256_bytes(written),
                    "previous_sha256": (sha256_bytes(previous) if previous is not None else None),
                    "current_sha256": (sha256_bytes(current) if current is not None else None),
                },
                txid=txid,
            )
        try:
            if previous is None:
                path.unlink()
            else:
                self.atomic_write_bytes(path, previous)
        except OSError as exc:
            after_error = self._read_optional_transaction_file(
                path,
                txid=txid,
                phase=phase,
            )
            if after_error == previous:
                return
            raise TransactionConflictError(
                f"Cannot restore transaction-bound file during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "written_sha256": sha256_bytes(written),
                    "previous_sha256": (sha256_bytes(previous) if previous is not None else None),
                    "current_sha256": (
                        sha256_bytes(after_error) if after_error is not None else None
                    ),
                },
                txid=txid,
            ) from exc
        self._require_optional_transaction_file_unchanged(
            path,
            previous,
            txid=txid,
            phase=phase,
        )

    def _load_transaction_backup_bytes(
        self,
        txid: str,
        *,
        expected_sha256: str,
        phase: str,
    ) -> bytes:
        backup_path = self.transaction_store.require_backup(txid)
        try:
            backup_bytes = backup_path.read_bytes()
        except OSError as exc:
            raise TransactionConflictError(
                "Transaction backup cannot be read during recovery",
                details={
                    "phase": phase,
                    "path": str(backup_path),
                    "expected_sha256": expected_sha256,
                    "current_sha256": None,
                },
                txid=txid,
            ) from exc
        backup_sha256 = sha256_bytes(backup_bytes)
        if backup_sha256 != expected_sha256:
            raise TransactionConflictError(
                "Transaction backup does not match its source SHA-256",
                details={
                    "phase": phase,
                    "path": str(backup_path),
                    "expected_sha256": expected_sha256,
                    "current_sha256": backup_sha256,
                },
                txid=txid,
            )
        return backup_bytes

    def begin_transaction(
        self,
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=True, operation="begin_transaction")
        document, target = self.gateway.load(path)
        snapshot = build_snapshot(document, live_session=target.is_live)
        if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {snapshot.info.sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        record = self.transaction_store.create(
            snapshot.info,
            target.path,
            source_sha256=snapshot.info.sha256,
            expected_sha256=expected_sha256 or snapshot.info.sha256,
            notes=notes,
        )
        self.transaction_store.store_snapshot(record.txid, document.raw_bytes)
        # Backup existing provenance sidecar for rollback restoration
        sidecar_path = target.path.with_suffix(target.path.suffix + ".provenance.json")
        provenance_backup: str | None = None
        provenance_backup_sha: str | None = None
        if sidecar_path.exists():
            try:
                prov_bytes = sidecar_path.read_bytes()
                prov_backup = self.transaction_store.store_provenance_backup(
                    record.txid,
                    prov_bytes,
                )
                provenance_backup = str(prov_backup)
                provenance_backup_sha = sha256_bytes(prov_bytes)
            except OSError:
                provenance_backup = None
                provenance_backup_sha = None
        updated = self.transaction_store.update(
            record.txid,
            status="staged",
            snapshot_path=str(self.transaction_store.snapshot_path(record.txid)),
            provenance_backup_path=provenance_backup,
            provenance_backup_sha256=provenance_backup_sha,
        )
        return {
            "ok": True,
            "written": False,
            "document": snapshot.info.model_dump(),
            "transaction": transaction_response_summary(updated),
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def stage_operations(self, txid: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=True, operation="stage_operations")
        record = self.transaction_store.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot accept operations in state {record.status}: {txid}",
                txid=txid,
            )
        parsed = parse_semantic_operations(operations)
        if not parsed:
            raise EditError("At least one semantic operation is required")
        staged = [*record.operations, *(operation.model_dump() for operation in parsed)]
        _require_transaction_capacity(len(staged))
        source = self._load_snapshot_record(record)
        _apply_bounded_semantic_operations(
            source,
            parse_semantic_operations(staged),
            live_session=self._session_id_from_working(Path(record.target_path)) is not None,
        )
        updated = self.transaction_store.update(
            txid,
            status="staged",
            operations=staged,
            compiled_patch_count=len(staged),
            changed_ids=[],
            validation_before={},
            validation_after_preview={},
            preview_resources=[],
            preview_metadata={},
        )
        return {
            "ok": True,
            "written": False,
            "transaction": transaction_response_summary(updated),
            "result": {"staged_count": len(staged)},
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def preview_transaction(self, txid: str) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=True, operation="preview_transaction")
        record = self.transaction_store.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot be previewed in state {record.status}: {txid}",
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self.preview_semantic_operations(source, operations)
        preview_resources = tx_preview_resources(txid)
        response_resources = [
            *tx_summary_resources(txid)[:2],
            *preview_resources,
        ]
        preview_metadata = {
            "inline": False,
            "artifacts": {
                "svg": {
                    "resource_uri": preview_resources[0],
                    "mime_type": "image/svg+xml",
                },
                "json": {
                    "resource_uri": preview_resources[1],
                    "mime_type": "application/json",
                },
                "diff": {
                    "resource_uri": preview_resources[2],
                    "mime_type": "text/plain",
                    **preview["diff_metadata"],
                },
            },
        }
        self.transaction_store.store_preview(
            txid,
            preview["svg"],
            preview["json"],
            preview["diff"],
        )
        updated = self.transaction_store.update(
            txid,
            status="validated",
            changed_ids=preview["changed_ids"],
            validation_before=preview["validation_before"],
            validation_after_preview=preview["validation_after_preview"],
            preview_resources=preview_resources,
            preview_metadata=preview_metadata,
            risk=default_risk("limited_write", "semantic operation preview generated"),
            compiled_patch_count=preview["patch_count"],
        )
        warnings, warning_metadata = _bounded_messages(preview["warnings"])
        limitations, limitation_metadata = _bounded_messages(preview["limitations"])
        validation_before = _validation_response_summary(preview["validation_before"])
        validation_after = _validation_response_summary(preview["validation_after_preview"])
        angle_evidence_warnings = (
            component_angle_evidence_warnings()
            if any(operation.kind == "rotate_components" for operation in operations)
            else []
        )
        return {
            "ok": True,
            "written": False,
            "transaction": transaction_response_summary(updated),
            "result": {
                **_bounded_changed_ids(preview["changed_ids"]),
                "validation_before": validation_before,
                "validation_after_preview": validation_after,
                "warnings_metadata": warning_metadata,
                "limitations_metadata": limitation_metadata,
                **(
                    {"evidence_warnings": angle_evidence_warnings}
                    if angle_evidence_warnings
                    else {}
                ),
            },
            "warnings": warnings,
            "limitations": limitations,
            "resources": response_resources,
            "preview": preview_metadata,
            **({"evidence_warnings": angle_evidence_warnings} if angle_evidence_warnings else {}),
        }

    def validate_transaction(self, txid: str) -> dict[str, Any]:
        return self.preview_transaction(txid)

    def commit_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=False, operation="commit_transaction")
        record = self.transaction_store.read(txid)
        if record.status != "validated":
            raise TransactionConflictError(
                f"Transaction must be validated before commit: {txid}",
                details={"current_status": record.status},
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        if expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required when committing a transaction",
                txid=txid,
            )
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self.preview_semantic_operations(source, operations)
        target_path = self.context.settings.resolve_allowed_path(record.target_path)
        current = DipTraceDocument.load(target_path, self.context.settings.max_document_bytes)
        current_sha256 = current.sha256
        expected = record.expected_sha256 or record.source_sha256
        if expected_sha256 != expected or current_sha256 != expected:
            raise Sha256MismatchError(
                "Commit refused: SHA-256 confirmation or current document mismatch",
                details={
                    "transaction_expected_sha256": expected,
                    "provided_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                },
                txid=txid,
            )
        session_id = (
            _live_session_id
            if _live_session_id is not None
            else self._session_id_from_working(target_path)
        )
        if session_id is not None and _live_guard is None:
            with self.session_store.guard_working_mutation(
                session_id,
                expected_sha256=expected,
            ) as live_guard:
                return self.commit_transaction(
                    txid,
                    expected_sha256,
                    _live_session_id=session_id,
                    _live_guard=live_guard,
                )
        is_live = session_id is not None
        applied = _apply_bounded_semantic_operations(
            current,
            operations,
            live_session=is_live,
        )
        self.require_current_target_sha256(target_path, expected)
        source_bytes = current.raw_bytes
        backup = self.transaction_store.store_backup(txid, source_bytes)
        self.require_current_target_sha256(target_path, expected)
        try:
            self.atomic_write_bytes(target_path, applied.raw_bytes)
            reparsed = DipTraceDocument.load(target_path, self.context.settings.max_document_bytes)
            committed_sha256 = reparsed.sha256
            if committed_sha256 != sha256_bytes(applied.raw_bytes):
                raise RoundtripValidationError(
                    "Committed XML SHA does not match compiled transaction output",
                    txid=txid,
                )
            self.require_current_target_sha256(target_path, committed_sha256)
            if _live_guard is not None:
                _live_guard.record_edit(
                    working_sha256=committed_sha256,
                    backup=backup,
                )
        except Exception as exc:
            compensation_error: TransactionConflictError | None = None
            try:
                recovery_bytes = self._load_transaction_backup_bytes(
                    txid,
                    expected_sha256=expected,
                    phase="commit_compensation",
                )
                self._compensate_transaction_file(
                    target_path,
                    written=applied.raw_bytes,
                    previous=recovery_bytes,
                    txid=txid,
                    phase="commit_compensation",
                )
            except TransactionConflictError as recovery_exc:
                compensation_error = recovery_exc
            failure_payload = {
                "code": getattr(exc, "code", "schema_write_error"),
                "message": str(exc),
                "phase": "commit_write",
                "source_restored": compensation_error is None,
            }
            try:
                failed_record = self.transaction_store.mark_failed(txid, failure_payload)
            except Exception as state_exc:
                try:
                    latest = self.transaction_store.read(txid)
                except DipTraceMcpError as read_exc:
                    current_bytes = self._read_optional_transaction_file(
                        target_path,
                        txid=txid,
                        phase="commit_failure_state_read",
                    )
                    raise TransactionConflictError(
                        "Commit failed and transaction state is unreadable",
                        details={
                            "phase": "commit_failure_state_read",
                            "source_restored": compensation_error is None,
                            "current_sha256": (
                                sha256_bytes(current_bytes) if current_bytes is not None else None
                            ),
                            "source_sha256": sha256_bytes(source_bytes),
                            "attempted_sha256": sha256_bytes(applied.raw_bytes),
                            "state_error": type(state_exc).__name__,
                            "read_error": type(read_exc).__name__,
                        },
                        txid=txid,
                    ) from state_exc
                if latest.status != "failed":
                    current_bytes = self._read_optional_transaction_file(
                        target_path,
                        txid=txid,
                        phase="commit_failure_state",
                    )
                    raise TransactionConflictError(
                        "Commit failed and its failure state could not be persisted",
                        details={
                            "phase": "commit_failure_state",
                            "transaction_status": latest.status,
                            "source_restored": compensation_error is None,
                            "current_sha256": (
                                sha256_bytes(current_bytes) if current_bytes is not None else None
                            ),
                            "source_sha256": sha256_bytes(source_bytes),
                            "attempted_sha256": sha256_bytes(applied.raw_bytes),
                            "state_error": type(state_exc).__name__,
                        },
                        txid=txid,
                    ) from state_exc
                failed_record = latest
            if compensation_error is not None:
                raise compensation_error from exc
            if isinstance(exc, DipTraceMcpError):
                raise
            raise TransactionConflictError(
                "Transaction commit write failed; authenticated source bytes were restored",
                details={
                    "phase": "commit_write",
                    "transaction_status": failed_record.status,
                    "source_restored": True,
                    "current_sha256": sha256_bytes(source_bytes),
                    "source_sha256": sha256_bytes(source_bytes),
                    "attempted_sha256": sha256_bytes(applied.raw_bytes),
                    "write_error": type(exc).__name__,
                },
                txid=txid,
            ) from exc
        try:
            updated = self.transaction_store.mark_committed(
                txid,
                committed_sha256=committed_sha256,
                changed_ids=applied.changed_ids,
                compiled_patch_count=applied.patch_count,
                preview_resources=tx_preview_resources(txid),
                backup_path=backup,
            )
        except Exception as state_exc:
            try:
                latest = self.transaction_store.read(txid)
            except DipTraceMcpError as read_exc:
                current_bytes = self._read_optional_transaction_file(
                    target_path,
                    txid=txid,
                    phase="commit_state_read",
                )
                raise TransactionConflictError(
                    "Commit state write failed and transaction state is unreadable",
                    details={
                        "phase": "commit_state_read",
                        "current_sha256": (
                            sha256_bytes(current_bytes) if current_bytes is not None else None
                        ),
                        "source_sha256": sha256_bytes(source_bytes),
                        "attempted_sha256": committed_sha256,
                        "state_error": type(state_exc).__name__,
                        "read_error": type(read_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
            if latest.status == "committed" and latest.committed_sha256 == committed_sha256:
                updated = latest
            else:
                recovery_bytes = self._load_transaction_backup_bytes(
                    txid,
                    expected_sha256=expected,
                    phase="commit_state_compensation",
                )
                self._compensate_transaction_file(
                    target_path,
                    written=applied.raw_bytes,
                    previous=recovery_bytes,
                    txid=txid,
                    phase="commit_state_compensation",
                )
                raise TransactionConflictError(
                    "Commit state was not persisted; authenticated source bytes were restored",
                    details={
                        "phase": "commit_state_write",
                        "transaction_status": latest.status,
                        "source_restored": True,
                        "current_sha256": sha256_bytes(source_bytes),
                        "source_sha256": sha256_bytes(source_bytes),
                        "attempted_sha256": committed_sha256,
                        "state_error": type(state_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
        if _live_guard is not None:
            _live_guard.commit()
        # Invalidate trust after MCP modification
        self.invalidate_document_trust_after_write(
            target_path, committed_sha256, operation_name="mcp_transaction_commit"
        )
        warnings, warning_metadata = _bounded_messages(applied.warnings)
        limitations, limitation_metadata = _bounded_messages(preview["limitations"])
        angle_evidence_warnings = (
            component_angle_evidence_warnings()
            if any(operation.kind == "rotate_components" for operation in operations)
            else []
        )
        return {
            "ok": True,
            "written": True,
            "transaction": transaction_response_summary(updated),
            "result": {
                **_bounded_changed_ids(applied.changed_ids),
                "compiled_patch_count": applied.patch_count,
                "warnings_metadata": warning_metadata,
                "limitations_metadata": limitation_metadata,
                **(
                    {"evidence_warnings": angle_evidence_warnings}
                    if angle_evidence_warnings
                    else {}
                ),
            },
            "warnings": warnings,
            "limitations": limitations,
            "resources": tx_preview_resources(txid),
            **({"evidence_warnings": angle_evidence_warnings} if angle_evidence_warnings else {}),
        }

    @staticmethod
    def _synthetic_rollback_provenance_bytes(
        restored_sha256: str,
        *,
        provenance: str,
    ) -> bytes:
        sidecar = DocumentProvenance(
            provenance=provenance,
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            current_document_sha256=restored_sha256,
            last_modified_by="mcp_rollback_transaction",
        )
        return sidecar.model_dump_json(indent=2).encode()

    def _prepare_rollback_provenance_bytes(
        self,
        record: TransactionRecord,
        target_path: Path,
        restored_sha256: str,
    ) -> bytes:
        if not record.provenance_backup_sha256:
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_no_backup",
            )
        try:
            provenance_backup = self.transaction_store.require_provenance_backup(record.txid)
        except TransactionConflictError:
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_no_backup",
            )
        try:
            provenance_bytes = provenance_backup.read_bytes()
            if sha256_bytes(provenance_bytes) != record.provenance_backup_sha256:
                raise ValueError("provenance backup SHA mismatch")
            restored_sidecar = DocumentProvenance.model_validate_json(provenance_bytes)
            if restored_sidecar.current_document_sha256 != restored_sha256:
                raise ValueError("restored provenance document SHA mismatch")
            if restored_sidecar.authority == ProvenanceAuthority.user_supplied_evidence:
                self.load_and_validate_evidence_manifest(target_path, restored_sidecar)
            if restored_sidecar.authority == ProvenanceAuthority.trusted_registry:
                self.load_and_authorize_trusted_registry_evidence(
                    target_path,
                    restored_sidecar,
                )
            if (
                restored_sidecar.authority == ProvenanceAuthority.fixture_manifest
                and restored_sidecar.validation_level in _HIGH_TRUST_LEVELS
            ):
                raise ValueError("unauthenticated fixture high trust cannot be restored")
            return provenance_bytes
        except (OSError, json.JSONDecodeError, ValueError, EditError):
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_synthetic",
            )

    @staticmethod
    def _transaction_file_sha256(path: Path) -> str | None:
        try:
            return sha256_bytes(path.read_bytes())
        except OSError:
            return None

    def _compensate_rollback_files(
        self,
        *,
        txid: str,
        target_path: Path,
        restored_document_bytes: bytes,
        committed_document_bytes: bytes,
        sidecar_path: Path,
        restored_sidecar_bytes: bytes,
        committed_sidecar_bytes: bytes | None,
        cause: Exception,
        phase: str,
    ) -> None:
        failures: list[dict[str, Any]] = []
        for path, written, previous, file_phase in (
            (
                sidecar_path,
                restored_sidecar_bytes,
                committed_sidecar_bytes,
                "rollback_sidecar_compensation",
            ),
            (
                target_path,
                restored_document_bytes,
                committed_document_bytes,
                "rollback_design_compensation",
            ),
        ):
            try:
                self._compensate_transaction_file(
                    path,
                    written=written,
                    previous=previous,
                    txid=txid,
                    phase=file_phase,
                )
            except TransactionConflictError as exc:
                failures.append(exc.payload.as_dict())
        details = {
            "phase": phase,
            "compensated": not failures,
            "cause_type": type(cause).__name__,
            "cause_code": getattr(cause, "code", None),
            "current_sha256": self._transaction_file_sha256(target_path),
            "current_sidecar_sha256": self._transaction_file_sha256(sidecar_path),
            "committed_sha256": sha256_bytes(committed_document_bytes),
            "restored_sha256": sha256_bytes(restored_document_bytes),
            "compensation_failures": failures,
        }
        if failures:
            raise TransactionConflictError(
                "Rollback failed and unexpected external bytes blocked compensation",
                details=details,
                txid=txid,
            ) from cause
        raise TransactionConflictError(
            "Rollback failed; the exact pre-call document and provenance were restored",
            details=details,
            txid=txid,
        ) from cause

    def rollback_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=False, operation="rollback_transaction")
        record = self.transaction_store.read(txid)
        if record.status == "rolled_back":
            raise TransactionConflictError("Transaction is already rolled back", txid=txid)
        restored_sha256: str | None = None
        target_path: Path | None = None
        committed_document_bytes: bytes | None = None
        restored_document_bytes: bytes | None = None
        sidecar_path: Path | None = None
        committed_sidecar_bytes: bytes | None = None
        restored_sidecar_bytes: bytes | None = None
        if record.status == "committed":
            if expected_sha256 is None:
                raise ConfirmationRequiredError(
                    "expected_sha256 is required to roll back a committed transaction",
                    txid=txid,
                )
            target_path = self.context.settings.resolve_allowed_path(record.target_path)
            current = DipTraceDocument.load(target_path, self.context.settings.max_document_bytes)
            if expected_sha256 != record.committed_sha256 or current.sha256 != expected_sha256:
                raise Sha256MismatchError(
                    "Rollback refused: SHA-256 confirmation or current document mismatch",
                    details={
                        "transaction_commit_sha256": record.committed_sha256,
                        "provided_sha256": expected_sha256,
                        "current_sha256": current.sha256,
                    },
                    txid=txid,
                )
            session_id = (
                _live_session_id
                if _live_session_id is not None
                else self._session_id_from_working(target_path)
            )
            if session_id is not None and _live_guard is None:
                with self.session_store.guard_working_mutation(
                    session_id,
                    expected_sha256=expected_sha256,
                ) as live_guard:
                    return self.rollback_transaction(
                        txid,
                        expected_sha256,
                        _live_session_id=session_id,
                        _live_guard=live_guard,
                    )
            restored_document_bytes = self._load_transaction_backup_bytes(
                txid,
                expected_sha256=record.source_sha256,
                phase="rollback_prepare",
            )
            DipTraceDocument.from_bytes(target_path, restored_document_bytes)
            restored_sha256 = sha256_bytes(restored_document_bytes)
            committed_document_bytes = current.raw_bytes
            sidecar_path = target_path.with_suffix(target_path.suffix + ".provenance.json")
            committed_sidecar_bytes = self._read_optional_transaction_file(
                sidecar_path,
                txid=txid,
                phase="rollback_prepare",
            )
            restored_sidecar_bytes = self._prepare_rollback_provenance_bytes(
                record,
                target_path,
                restored_sha256,
            )
            try:
                self.require_current_target_sha256(target_path, expected_sha256)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    committed_sidecar_bytes,
                    txid=txid,
                    phase="rollback_prewrite",
                )
                self.atomic_write_bytes(target_path, restored_document_bytes)
                self.require_current_target_sha256(target_path, restored_sha256)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    committed_sidecar_bytes,
                    txid=txid,
                    phase="rollback_sidecar_prewrite",
                )
                self.atomic_write_bytes(sidecar_path, restored_sidecar_bytes)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    restored_sidecar_bytes,
                    txid=txid,
                    phase="rollback_sidecar_verify",
                )
                if _live_guard is not None:
                    _live_guard.record_edit(
                        working_sha256=restored_sha256,
                    )
            except Exception as exc:
                self._compensate_rollback_files(
                    txid=txid,
                    target_path=target_path,
                    restored_document_bytes=restored_document_bytes,
                    committed_document_bytes=committed_document_bytes,
                    sidecar_path=sidecar_path,
                    restored_sidecar_bytes=restored_sidecar_bytes,
                    committed_sidecar_bytes=committed_sidecar_bytes,
                    cause=exc,
                    phase="rollback_apply",
                )
        try:
            updated = self.transaction_store.mark_rolled_back(
                txid,
                rolled_back_sha256=restored_sha256,
                reason="explicit rollback",
            )
        except Exception as state_exc:
            try:
                latest = self.transaction_store.read(txid)
            except DipTraceMcpError as read_exc:
                raise TransactionConflictError(
                    "Rollback state write failed and transaction state is unreadable",
                    details={
                        "phase": "rollback_state_read",
                        "current_sha256": (
                            self._transaction_file_sha256(target_path)
                            if target_path is not None
                            else None
                        ),
                        "current_sidecar_sha256": (
                            self._transaction_file_sha256(sidecar_path)
                            if sidecar_path is not None
                            else None
                        ),
                        "state_error": type(state_exc).__name__,
                        "read_error": type(read_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
            if latest.status == "rolled_back":
                updated = latest
            elif (
                target_path is not None
                and committed_document_bytes is not None
                and restored_document_bytes is not None
                and sidecar_path is not None
                and restored_sidecar_bytes is not None
            ):
                self._compensate_rollback_files(
                    txid=txid,
                    target_path=target_path,
                    restored_document_bytes=restored_document_bytes,
                    committed_document_bytes=committed_document_bytes,
                    sidecar_path=sidecar_path,
                    restored_sidecar_bytes=restored_sidecar_bytes,
                    committed_sidecar_bytes=committed_sidecar_bytes,
                    cause=state_exc,
                    phase="rollback_state_write",
                )
            else:
                raise TransactionConflictError(
                    "Rollback state was not persisted",
                    details={
                        "phase": "rollback_state_write",
                        "transaction_status": latest.status,
                        "current_sha256": None,
                        "current_sidecar_sha256": None,
                        "state_error": type(state_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
        if _live_guard is not None:
            _live_guard.commit()
        return {
            "ok": True,
            "written": restored_sha256 is not None,
            "transaction": transaction_response_summary(updated),
            "result": {
                "rolled_back": True,
                "document_restored": restored_sha256 is not None,
                "restored_sha256": restored_sha256,
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def list_transactions(self) -> dict[str, Any]:
        return {
            "ok": True,
            "transactions": [
                transaction_response_summary(item) for item in self.transaction_store.list()
            ],
        }

    def transaction_summary_resource(self, txid: str) -> str:
        return json.dumps(
            transaction_response_summary(self.transaction_store.read(txid)),
            ensure_ascii=False,
            indent=2,
        )

    def _load_snapshot_record(self, record: TransactionRecord) -> DipTraceDocument:
        snapshot_path = self.transaction_store.require_snapshot(record.txid)
        snapshot = DipTraceDocument.load(snapshot_path, self.context.settings.max_document_bytes)
        if snapshot.sha256 != record.source_sha256:
            raise TransactionConflictError(
                "Transaction snapshot does not match its source SHA-256",
                details={
                    "expected_sha256": record.source_sha256,
                    "snapshot_sha256": snapshot.sha256,
                },
                txid=record.txid,
            )
        return snapshot

    def _session_id_from_working(self, path: Path) -> str | None:
        return self.session_store.session_id_for_working_path(path)
