"""Bounded raw XML edit and preview orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..backups import BackupStore
from ..errors import EditError, Sha256MismatchError
from ..previews import RawPreviewStore
from ..services.context import (
    DocumentGateway,
    ServiceContext,
)
from ..services.context import (
    bounded_text as _bounded_text,
)
from ..services.context import (
    json_size as _json_size,
)
from ..sessions import SessionStore
from ..write_limits import require_write_impact, write_impact
from ..xml_document import (
    DipTraceDocument,
    XmlEdit,
    sha256_bytes,
    unified_xml_diff_preview,
    utc_now,
    write_with_backup,
)

RAW_EDIT_RESPONSE_BYTE_LIMIT = 128 * 1024
RAW_EDIT_XPATH_CHARACTER_LIMIT = 128


class RawPreviewStoreProvider(Protocol):
    def __call__(self) -> RawPreviewStore: ...


class RequireCurrentTargetSha256(Protocol):
    def __call__(self, target: Path, expected_sha256: str) -> None: ...


class AtomicWriteBytes(Protocol):
    def __call__(self, path: Path, data: bytes) -> None: ...


class InvalidatedDocumentProvenance(Protocol):
    def __call__(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str,
    ) -> Any: ...


class WriteProvenanceSidecar(Protocol):
    def __call__(self, document_path: Path, provenance: Any) -> None: ...


class InvalidateDocumentTrust(Protocol):
    def __call__(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str = "mcp_write",
    ) -> None: ...


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


class XmlWriteService:
    """Implementation for bounded raw XML writes and diff resources."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        backup_store: BackupStore,
        session_store: SessionStore,
        raw_preview_store_provider: RawPreviewStoreProvider,
        require_current_target_sha256: RequireCurrentTargetSha256,
        atomic_write_bytes: AtomicWriteBytes,
        invalidated_document_provenance: InvalidatedDocumentProvenance,
        write_provenance_sidecar: WriteProvenanceSidecar,
        invalidate_document_trust_after_write: InvalidateDocumentTrust,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.backup_store = backup_store
        self.session_store = session_store
        self.raw_preview_store_provider = raw_preview_store_provider
        self.require_current_target_sha256 = require_current_target_sha256
        self.atomic_write_bytes = atomic_write_bytes
        self.invalidated_document_provenance = invalidated_document_provenance
        self.write_provenance_sidecar = write_provenance_sidecar
        self.invalidate_document_trust_after_write = invalidate_document_trust_after_write

    def apply_edits(
        self,
        edits: list[XmlEdit],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self.context.policy.require_write(dry_run=dry_run, operation="apply_xml_edits")
        if len(edits) > 50:
            raise EditError("A single call can contain at most 50 edits")
        if not dry_run and not expected_sha256:
            raise EditError("expected_sha256 from a dry-run is required when dry_run=false")
        document, target = self.gateway.load(path)
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
            self.require_current_target_sha256(target.path, expected_sha256)
        diff, diff_metadata = unified_xml_diff_preview(before, after)
        preview_id, diff_resource = self.raw_preview_store_provider().store(diff, diff_metadata)
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
                DipTraceDocument.load(target.path, self.context.settings.max_document_bytes)
                sidecar_path = target.path.with_suffix(target.path.suffix + ".provenance.json")
                try:
                    previous_sidecar = sidecar_path.read_bytes()
                except FileNotFoundError:
                    previous_sidecar = None
                prepared = self.invalidated_document_provenance(
                    target.path,
                    after_sha256,
                    operation_name="mcp_apply_xml_edits",
                )
                attempted_sidecar = prepared.model_dump_json(indent=2).encode()
                try:
                    self.write_provenance_sidecar(target.path, prepared)
                except Exception:
                    try:
                        current_sidecar = sidecar_path.read_bytes()
                    except FileNotFoundError:
                        current_sidecar = None
                    if current_sidecar == attempted_sidecar:
                        if previous_sidecar is None:
                            sidecar_path.unlink(missing_ok=True)
                        else:
                            self.atomic_write_bytes(sidecar_path, previous_sidecar)
                    raise

            mutation = self.session_store.mutate_working(
                target.live_session_id,
                expected_sha256=expected_sha256,
                replacement=after,
                after_write=finalize_live_raw_edit,
            )
            backup = mutation.backup
        else:
            self.require_current_target_sha256(target.path, expected_sha256)
            backup = write_with_backup(
                target.path,
                after,
                self.backup_store,
                expected_sha256=expected_sha256,
            )
            DipTraceDocument.load(target.path, self.context.settings.max_document_bytes)
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

    def raw_preview_diff_resource(self, preview_id: str) -> str:
        return self.raw_preview_store_provider().read_diff(preview_id)
