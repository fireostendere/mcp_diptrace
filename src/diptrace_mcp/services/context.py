"""Small, typed infrastructure shared by the internal domain services."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..adapters import document_id_for
from ..config import Settings
from ..domain import DocumentInfo
from ..errors import DocumentError, ObjectNotFoundError, SessionError
from ..findings import FindingStore
from ..model_cache import ModelCache
from ..policy import Policy
from ..sessions import SessionStore
from ..transactions import TransactionStore
from ..xml_document import DipTraceDocument


@dataclass(frozen=True, slots=True)
class DocumentTarget:
    """Resolved document path and its optional live-session identity."""

    path: Path
    live_session_id: str | None = None

    @property
    def is_live(self) -> bool:
        return self.live_session_id is not None


@dataclass(frozen=True, slots=True)
class ServiceContext:
    """Shared server-instance dependencies; stores are never created here."""

    settings: Settings
    policy: Policy
    model_cache: ModelCache
    transaction_store: TransactionStore
    session_store: SessionStore
    finding_store: FindingStore


@dataclass(slots=True)
class DocumentGateway:
    """The one document loader and target registry for a server instance."""

    settings: Settings
    session_store: SessionStore
    targets: dict[str, DocumentTarget] = field(default_factory=dict)

    def resolve_target(self, path: str | None) -> DocumentTarget:
        if path:
            try:
                resolved = self.settings.resolve_allowed_path(path)
            except FileNotFoundError as exc:
                raise ObjectNotFoundError(
                    "The requested document does not exist",
                    details={"resource": "document"},
                    cause=exc,
                ) from exc
            return DocumentTarget(
                resolved,
                self.session_store.session_id_for_working_path(resolved),
            )
        active = self.session_store.active_metadata()
        if active is None:
            raise SessionError(
                "No active DipTrace session. Pass an XML path or launch Tools > Plugins > "
                "DipTrace MCP Bridge in DipTrace."
            )
        session_id = str(active["session_id"])
        return DocumentTarget(self.session_store.working_path(session_id), session_id)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        target = self.resolve_target(path)
        document = DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        self.targets[document_id_for(document)] = target
        return document, target

    def load_document_id(self, document_id: str) -> tuple[DipTraceDocument, DocumentTarget]:
        try:
            target = self.targets[document_id]
        except KeyError as exc:
            raise DocumentError(
                f"Document id is not registered in this server process: {document_id}",
                code="document_not_found",
                details={"document_id": document_id},
            ) from exc
        document = DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        if document_id_for(document) != document_id:
            raise DocumentError(
                f"Document identity changed for registered path: {target.path}",
                code="document_not_found",
                details={"document_id": document_id},
            )
        return document, target


def json_size(value: Any) -> int:
    """Return the canonical serialized size used by bounded responses."""

    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def bounded_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def read_success(
    info: DocumentInfo,
    result: dict[str, Any],
    *,
    warnings: list[str] | None = None,
    limitations: list[str] | None = None,
    resources: list[str] | None = None,
) -> dict[str, Any]:
    """Build the stable read response envelope used by the existing Facade."""

    return {
        "ok": True,
        "document": info.model_dump(),
        "result": result,
        "warnings": list(warnings or []),
        "limitations": list(limitations or info.compatibility.get("limitations", [])),
        "resources": list(resources or []),
        "transaction": None,
        "job": None,
    }


def validate_page(offset: int, limit: int) -> None:
    if offset < 0:
        raise DocumentError("offset cannot be negative")
    if not 1 <= limit <= 500:
        raise DocumentError("limit must be between 1 and 500")

