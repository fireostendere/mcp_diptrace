from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from .errors import ConfigurationError, PathAccessError
from .retention import (
    DEFAULT_RETENTION_MAX_AGE_DAYS,
    DEFAULT_RETENTION_MAX_RECORDS,
    RetentionPolicy,
)

_WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_WSL_USER_PATH = re.compile(
    r"^/mnt/([A-Za-z])/Users/([^/]+)(?:/|$)",
    re.IGNORECASE,
)
PolicyProfile = Literal[
    "read_only", "review", "interactive_edit", "automation", "manufacturing"
]
DEFAULT_MODEL_CACHE_MAX_BYTES = 256 * 1024 * 1024
_POLICY_PROFILES = {
    "read_only",
    "review",
    "interactive_edit",
    "automation",
    "manufacturing",
}


def platform_path(value: str | os.PathLike[str]) -> Path:
    """Translate path syntax without expanding caller-controlled placeholders."""

    raw = os.fspath(value)
    match = _WINDOWS_PATH.match(raw)
    if os.name != "nt" and match:
        drive, tail = match.groups()
        parts = [part for part in re.split(r"[\\/]", tail) if part]
        return Path("/mnt") / drive.lower() / Path(*parts)
    return Path(raw)


def _configured_platform_path(value: str | os.PathLike[str]) -> Path:
    """Expand server-owned configuration before applying platform translation."""

    configured = os.path.expandvars(os.path.expanduser(os.fspath(value)))
    return platform_path(configured)


def _default_state_dir(workspace: Path) -> Path:
    configured = os.environ.get("DIPTRACE_MCP_STATE_DIR")
    if configured:
        return _configured_platform_path(configured).resolve()

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


def _policy_profile() -> PolicyProfile:
    value = os.environ.get("DIPTRACE_MCP_POLICY", "interactive_edit")
    if value not in _POLICY_PROFILES:
        choices = ", ".join(sorted(_POLICY_PROFILES))
        raise ConfigurationError(f"DIPTRACE_MCP_POLICY must be one of: {choices}")
    return cast(PolicyProfile, value)


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
    model_cache_max_bytes: int = DEFAULT_MODEL_CACHE_MAX_BYTES
    max_scan_files: int = 500
    freerouting_executable: Path | None = None
    java_executable: Path | None = None
    ngspice_executable: Path | None = None
    openems_runner: Path | None = None
    external_timeout_seconds: int = 3600
    max_external_processes: int = 2
    max_external_result_bytes: int = 16 * 1024 * 1024
    max_external_log_bytes: int = 4 * 1024 * 1024
    retention_max_records: int = DEFAULT_RETENTION_MAX_RECORDS
    retention_max_age_days: int = DEFAULT_RETENTION_MAX_AGE_DAYS
    active_policy: PolicyProfile = "interactive_edit"

    @classmethod
    def from_env(cls) -> Settings:
        workspace = _configured_platform_path(
            os.environ.get("DIPTRACE_MCP_WORKSPACE", os.getcwd())
        ).resolve()
        roots = [workspace]
        configured_roots = os.environ.get("DIPTRACE_MCP_ALLOWED_ROOTS")
        if configured_roots:
            roots.extend(
                _configured_platform_path(item).resolve()
                for item in configured_roots.split(os.pathsep)
                if item.strip()
            )
        unique_roots = tuple(dict.fromkeys(roots))
        freerouting_raw = os.environ.get("DIPTRACE_MCP_FREEROUTING")
        freerouting = (
            _configured_platform_path(freerouting_raw).resolve()
            if freerouting_raw
            else None
        )
        java_raw = os.environ.get("DIPTRACE_MCP_JAVA")
        java_found = java_raw or shutil.which("java")
        java = _configured_platform_path(java_found).resolve() if java_found else None
        ngspice_raw = os.environ.get("DIPTRACE_MCP_NGSPICE")
        ngspice_found = ngspice_raw or shutil.which("ngspice")
        ngspice = (
            _configured_platform_path(ngspice_found).resolve() if ngspice_found else None
        )
        openems_raw = os.environ.get("DIPTRACE_MCP_OPENEMS_RUNNER")
        openems_runner = (
            _configured_platform_path(openems_raw).resolve() if openems_raw else None
        )
        return cls(
            workspace=workspace,
            allowed_roots=unique_roots,
            state_dir=_default_state_dir(workspace),
            max_document_bytes=_positive_int(
                "DIPTRACE_MCP_MAX_DOCUMENT_BYTES", 128 * 1024 * 1024
            ),
            model_cache_max_bytes=_positive_int(
                "DIPTRACE_MCP_MODEL_CACHE_MAX_BYTES",
                DEFAULT_MODEL_CACHE_MAX_BYTES,
            ),
            max_scan_files=_positive_int("DIPTRACE_MCP_MAX_SCAN_FILES", 500),
            freerouting_executable=freerouting,
            java_executable=java,
            ngspice_executable=ngspice,
            openems_runner=openems_runner,
            external_timeout_seconds=_positive_int(
                "DIPTRACE_MCP_EXTERNAL_TIMEOUT", 3600
            ),
            max_external_processes=_positive_int(
                "DIPTRACE_MCP_MAX_EXTERNAL_PROCESSES", 2
            ),
            max_external_result_bytes=_positive_int(
                "DIPTRACE_MCP_MAX_EXTERNAL_RESULT_BYTES", 16 * 1024 * 1024
            ),
            max_external_log_bytes=_positive_int(
                "DIPTRACE_MCP_MAX_EXTERNAL_LOG_BYTES", 4 * 1024 * 1024
            ),
            retention_max_records=_positive_int(
                "DIPTRACE_MCP_RETENTION_MAX_RECORDS",
                DEFAULT_RETENTION_MAX_RECORDS,
            ),
            retention_max_age_days=_positive_int(
                "DIPTRACE_MCP_RETENTION_MAX_AGE_DAYS",
                DEFAULT_RETENTION_MAX_AGE_DAYS,
            ),
            active_policy=_policy_profile(),
        )

    @property
    def retention_policy(self) -> RetentionPolicy:
        return RetentionPolicy(
            max_records=self.retention_max_records,
            max_age_days=self.retention_max_age_days,
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
            "model_cache_max_bytes": self.model_cache_max_bytes,
            "max_scan_files": self.max_scan_files,
            "freerouting_executable": (
                str(self.freerouting_executable) if self.freerouting_executable else None
            ),
            "java_executable": str(self.java_executable) if self.java_executable else None,
            "ngspice_executable": (
                str(self.ngspice_executable) if self.ngspice_executable else None
            ),
            "openems_runner": str(self.openems_runner) if self.openems_runner else None,
            "external_timeout_seconds": self.external_timeout_seconds,
            "max_external_processes": self.max_external_processes,
            "max_external_result_bytes": self.max_external_result_bytes,
            "max_external_log_bytes": self.max_external_log_bytes,
            "retention_max_records": self.retention_max_records,
            "retention_max_age_days": self.retention_max_age_days,
            "active_policy": self.active_policy,
        }
