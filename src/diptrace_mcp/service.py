from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import inspector
from .config import Settings
from .errors import DocumentError, EditError, PathAccessError, SessionError
from .sessions import SessionAction, SessionStore
from .xml_document import (
    DipTraceDocument,
    XmlEdit,
    sha256_bytes,
    unified_xml_diff,
    utc_now,
    write_with_backup,
)

_CANDIDATE_SUFFIXES = {".xml", ".dip", ".dch", ".eli", ".lib"}
_SOURCE_TAG = re.compile(br"<Source\b([^>]*)>", re.IGNORECASE)
_SOURCE_ATTRIBUTE = re.compile(br"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*['\"]([^'\"]*)['\"]")


@dataclass(frozen=True)
class DocumentTarget:
    path: Path
    live_session_id: str | None = None

    @property
    def is_live(self) -> bool:
        return self.live_session_id is not None


class DipTraceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions = SessionStore(settings.state_dir, settings.max_document_bytes)

    def resolve_target(self, path: str | None) -> DocumentTarget:
        if path:
            return DocumentTarget(self.settings.resolve_allowed_path(path))
        active = self.sessions.active_metadata()
        if active is None:
            raise SessionError(
                "No active DipTrace session. Pass an XML path or launch Tools > Plugins > "
                "DipTrace MCP Bridge in DipTrace."
            )
        session_id = str(active["session_id"])
        return DocumentTarget(self.sessions.working_path(session_id), session_id)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        target = self.resolve_target(path)
        return (
            DipTraceDocument.load(target.path, self.settings.max_document_bytes),
            target,
        )

    def status(self) -> dict[str, Any]:
        active = self.sessions.active_metadata()
        if active is not None:
            session_id = str(active["session_id"])
            working = self.sessions.working_path(session_id)
            active = {
                **active,
                "working_path": str(working),
                "working_sha256": sha256_bytes(working.read_bytes()),
            }
        return {
            "server": "diptrace-mcp",
            "configuration": self.settings.as_dict(),
            "active_session": active,
        }

    def scan_documents(self, root: str | None = None, recursive: bool = True) -> dict[str, Any]:
        scan_root = self.settings.resolve_allowed_path(root or str(self.settings.workspace))
        if not scan_root.is_dir():
            raise DocumentError(f"Scan root is not a directory: {scan_root}")
        iterator = scan_root.rglob("*") if recursive else scan_root.glob("*")
        results: list[dict[str, Any]] = []
        examined = 0
        truncated = False
        for candidate in iterator:
            if not candidate.is_file() or candidate.suffix.lower() not in _CANDIDATE_SUFFIXES:
                continue
            try:
                candidate = self.settings.resolve_allowed_path(candidate)
            except PathAccessError:
                continue
            examined += 1
            if examined > self.settings.max_scan_files:
                truncated = True
                break
            header = self._read_source_header(candidate)
            if header is None:
                continue
            try:
                relative = candidate.relative_to(self.settings.workspace)
                relative_path = str(relative)
            except ValueError:
                relative_path = None
            results.append(
                {
                    "path": str(candidate),
                    "relative_path": relative_path,
                    "size_bytes": candidate.stat().st_size,
                    **header,
                }
            )
        return {
            "root": str(scan_root),
            "recursive": recursive,
            "examined_candidates": min(examined, self.settings.max_scan_files),
            "truncated": truncated,
            "documents": results,
        }

    def _read_source_header(self, path: Path) -> dict[str, str] | None:
        try:
            with path.open("rb") as stream:
                prefix = stream.read(16 * 1024)
        except OSError:
            return None
        match = _SOURCE_TAG.search(prefix)
        if not match:
            return None
        attributes = {
            key.decode("ascii", errors="ignore"): value.decode("utf-8", errors="replace")
            for key, value in _SOURCE_ATTRIBUTE.findall(match.group(1))
        }
        source_type = attributes.get("Type", "")
        if not source_type.startswith("DipTrace-"):
            return None
        return {
            "type": source_type,
            "version": attributes.get("Version", ""),
            "units": attributes.get("Units", ""),
        }

    def summarize(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        return {**inspector.summarize(document), "live_session": target.is_live}

    def components(
        self,
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        return {
            **inspector.components(document, query, offset, limit),
            "live_session": target.is_live,
        }

    def component(self, refdes: str, path: str | None = None) -> dict[str, Any]:
        if not refdes.strip():
            raise DocumentError("refdes cannot be empty")
        document, target = self.load(path)
        return {**inspector.component(document, refdes), "live_session": target.is_live}

    def nets(
        self,
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        return {
            **inspector.nets(document, query, include_endpoints, offset, limit),
            "live_session": target.is_live,
        }

    def rules(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        return {**inspector.design_rules(document), "live_session": target.is_live}

    def read_xml(
        self,
        path: str | None = None,
        xpath: str = ".",
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        if not 1 <= max_matches <= 100:
            raise DocumentError("max_matches must be between 1 and 100")
        if not 1 <= max_characters <= 100_000:
            raise DocumentError("max_characters must be between 1 and 100000")
        document, target = self.load(path)
        fragments = document.xml_fragments(xpath, max_matches)
        rendered = "\n\n".join(fragments)
        truncated = len(rendered) > max_characters
        if truncated:
            rendered = rendered[:max_characters] + "\n... XML output truncated ..."
        return {
            "path": str(document.path),
            "live_session": target.is_live,
            "xpath": xpath,
            "match_count": len(fragments),
            "truncated": truncated,
            "xml": rendered,
        }

    def apply_edits(
        self,
        edits: list[XmlEdit],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        if len(edits) > 50:
            raise EditError("A single call can contain at most 50 edits")
        if not dry_run and not expected_sha256:
            raise EditError("expected_sha256 from a dry-run is required when dry_run=false")
        document, target = self.load(path)
        before = document.raw_bytes
        before_sha256 = sha256_bytes(before)
        if expected_sha256 and before_sha256 != expected_sha256:
            raise EditError(
                f"Document changed: expected {expected_sha256}, current {before_sha256}"
            )
        after, previews = document.apply_edits(edits)
        after_sha256 = sha256_bytes(after)
        changed = before != after
        result: dict[str, Any] = {
            "path": str(target.path),
            "live_session": target.is_live,
            "session_id": target.live_session_id,
            "dry_run": dry_run,
            "changed": changed,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "operations": previews,
            "diff": unified_xml_diff(before, after),
        }
        if dry_run or not changed:
            result["written"] = False
            return result

        if target.live_session_id:
            backup_dir = self.sessions.backups_dir(target.live_session_id)
        else:
            backup_dir = target.path.parent / ".diptrace-mcp-backups"
        backup = write_with_backup(target.path, after, backup_dir)
        DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        if target.live_session_id:
            self.sessions.record_edit(target.live_session_id, after_sha256, backup)
        result.update(
            {
                "written": True,
                "backup": str(backup),
                "written_at": utc_now(),
            }
        )
        return result

    def finish_live_session(self, action: SessionAction) -> dict[str, Any]:
        return self.sessions.request_finish(action)

    @staticmethod
    def _validate_page(offset: int, limit: int) -> None:
        if offset < 0:
            raise DocumentError("offset cannot be negative")
        if not 1 <= limit <= 500:
            raise DocumentError("limit must be between 1 and 500")
