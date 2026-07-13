from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError, PathAccessError

_WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_WSL_USER_PATH = re.compile(r"^/mnt/([A-Za-z])/Users/([^/]+)(?:/|$)")


def platform_path(value: str | os.PathLike[str]) -> Path:
    raw = os.path.expandvars(os.path.expanduser(os.fspath(value)))
    match = _WINDOWS_PATH.match(raw)
    if os.name != "nt" and match:
        drive, tail = match.groups()
        parts = [part for part in re.split(r"[\\/]", tail) if part]
        return Path("/mnt") / drive.lower() / Path(*parts)
    return Path(raw)


def _default_state_dir(workspace: Path) -> Path:
    configured = os.environ.get("DIPTRACE_MCP_STATE_DIR")
    if configured:
        return platform_path(configured).resolve()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data) / "DipTraceMCP").resolve()
        return (Path.home() / "AppData" / "Local" / "DipTraceMCP").resolve()

    for candidate in (workspace, Path.cwd()):
        match = _WSL_USER_PATH.match(candidate.resolve().as_posix())
        if match:
            drive, username = match.groups()
            return (
                Path("/mnt")
                / drive.lower()
                / "Users"
                / username
                / "AppData"
                / "Local"
                / "DipTraceMCP"
            )

    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return (Path(xdg_state) / "diptrace-mcp").resolve()
    return (Path.home() / ".local" / "state" / "diptrace-mcp").resolve()


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class Settings:
    workspace: Path
    allowed_roots: tuple[Path, ...]
    state_dir: Path
    max_document_bytes: int = 128 * 1024 * 1024
    max_scan_files: int = 500

    @classmethod
    def from_env(cls) -> Settings:
        workspace = platform_path(
            os.environ.get("DIPTRACE_MCP_WORKSPACE", os.getcwd())
        ).resolve()
        roots = [workspace]
        configured_roots = os.environ.get("DIPTRACE_MCP_ALLOWED_ROOTS")
        if configured_roots:
            roots.extend(
                platform_path(item).resolve()
                for item in configured_roots.split(os.pathsep)
                if item.strip()
            )
        unique_roots = tuple(dict.fromkeys(roots))
        return cls(
            workspace=workspace,
            allowed_roots=unique_roots,
            state_dir=_default_state_dir(workspace),
            max_document_bytes=_positive_int(
                "DIPTRACE_MCP_MAX_DOCUMENT_BYTES", 128 * 1024 * 1024
            ),
            max_scan_files=_positive_int("DIPTRACE_MCP_MAX_SCAN_FILES", 500),
        )

    def resolve_allowed_path(
        self,
        value: str | os.PathLike[str],
        *,
        must_exist: bool = True,
    ) -> Path:
        candidate = platform_path(value)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        candidate = candidate.resolve(strict=must_exist)
        if not any(_is_within(candidate, root) for root in self.allowed_roots):
            roots = ", ".join(str(root) for root in self.allowed_roots)
            raise PathAccessError(f"Path is outside allowed roots ({roots}): {candidate}")
        return candidate

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace": str(self.workspace),
            "allowed_roots": [str(root) for root in self.allowed_roots],
            "state_dir": str(self.state_dir),
            "max_document_bytes": self.max_document_bytes,
            "max_scan_files": self.max_scan_files,
        }
