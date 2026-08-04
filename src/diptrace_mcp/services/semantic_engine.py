"""Central semantic write execution and deterministic preview engine."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from ..adapters import build_snapshot
from ..errors import (
    ConfirmationRequiredError,
    ConnectivityRegressionError,
    DrcRegressionError,
    EditError,
    Sha256MismatchError,
    TransactionConflictError,
)
from ..operations import (
    DeleteTraceOperation,
    SemanticOperation,
    SyncSchematicToPcbOperation,
    parse_semantic_operations,
)
from ..preview import render_preview_json, render_preview_svg
from ..review import run_checks
from ..services.context import DocumentGateway, ServiceContext
from ..services.transactions import (
    _apply_bounded_semantic_operations,
    _require_transaction_capacity,
)
from ..transactions import (
    TransactionStore,
)
from ..xml_document import DipTraceDocument, unified_xml_diff_preview

PreviewTransaction = Callable[[str], dict[str, Any]]


class CommitTransaction(Protocol):
    def __call__(
        self,
        txid: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]: ...


LoadSnapshotRecord = Callable[[Any], DipTraceDocument]
SessionIdFromWorking = Callable[[Path], str | None]


class SemanticEngineService:
    """Implementation for semantic operation execution and preview validation."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        transaction_store: TransactionStore,
        preview_transaction: PreviewTransaction,
        commit_transaction: CommitTransaction,
        load_snapshot_record: LoadSnapshotRecord,
        session_id_from_working: SessionIdFromWorking,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.transaction_store = transaction_store
        self.preview_transaction = preview_transaction
        self.commit_transaction = commit_transaction
        self.load_snapshot_record = load_snapshot_record
        self.session_id_from_working = session_id_from_working

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
        self.context.policy.require_write(
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
            document, target = self.gateway.load(path)
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
            tx_record = self.transaction_store.create(
                snapshot.info,
                target.path,
                source_sha256=snapshot.info.sha256,
                expected_sha256=expected_sha256 or snapshot.info.sha256,
                notes=[operation.kind for operation in operations],
            )
            txid = tx_record.txid
            self.transaction_store.store_snapshot(txid, document.raw_bytes)
            self.transaction_store.update(
                txid,
                status="staged",
                operations=incoming_operations,
                compiled_patch_count=len(operations),
                snapshot_path=str(self.transaction_store.snapshot_path(txid)),
            )
        else:
            existing = self.transaction_store.read(txid)
            if existing.status not in {"staged", "validated"}:
                raise TransactionConflictError(
                    f"Transaction cannot be edited in state {existing.status}: {txid}",
                    txid=txid,
                )
            if path is not None:
                supplied_target = self.gateway.resolve_target(path)
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
            source = self.load_snapshot_record(existing)
            _apply_bounded_semantic_operations(
                source,
                parse_semantic_operations(combined_operations),
                live_session=(self.session_id_from_working(Path(existing.target_path)) is not None),
            )
            if existing.operations != incoming_operations:
                self.transaction_store.update(
                    txid,
                    status="staged",
                    operations=combined_operations,
                    compiled_patch_count=len(combined_operations),
                    snapshot_path=existing.snapshot_path
                    or str(self.transaction_store.snapshot_path(txid)),
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
