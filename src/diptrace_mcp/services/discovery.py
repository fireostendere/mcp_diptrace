from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import (
    DocumentError,
    PathAccessError,
)

_CANDIDATE_SUFFIXES = {".xml", ".dip", ".dch", ".eli", ".lib"}
_SOURCE_TAG = re.compile(rb"<(?:Source|Library)\b([^>]*)>", re.IGNORECASE)
_SOURCE_ATTRIBUTE = re.compile(rb"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*['\"]([^'\"]*)['\"]")


class DiscoveryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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

    def _scan_libraries(
        self,
        source_type: str,
        root: str | None,
        recursive: bool,
    ) -> dict[str, Any]:
        scanned = self.scan_documents(root, recursive)
        items = [item for item in scanned["documents"] if item.get("type") == source_type]
        return {
            "ok": True,
            "document": None,
            "result": {
                "source_type": source_type,
                "matched_count": len(items),
                "items": items,
                "truncated": scanned["truncated"],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
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
            "source_type": source_type,
            "version": attributes.get("Version", ""),
            "units": attributes.get("Units", ""),
        }
