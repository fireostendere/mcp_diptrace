from __future__ import annotations

import os
import sys
from pathlib import Path, PureWindowsPath
from typing import Any, cast

from .errors import SessionError
from .xml_document import sha256_bytes


def _current_exchange_path_platform() -> str:
    """Return the native path syntax used by the process creating the session."""

    return "windows" if os.name == "nt" else "posix"


def _is_wsl_runtime(runtime_platform: str) -> bool:
    if not runtime_platform.startswith("linux"):
        return False
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="ascii")
    except OSError:
        return False
    return "microsoft" in release.casefold()


def _exchange_path_for_runtime(
    raw_path: str,
    origin_platform: str,
    *,
    runtime_os_name: str | None = None,
    runtime_platform: str | None = None,
) -> Path:
    """Resolve bridge-native exchange metadata in the current process namespace.

    A Windows bridge keeps its authoritative ``C:\\...`` path in metadata. A WSL
    MCP process derives ``/mnt/<drive>/...`` only in memory, so the derived path
    can never be persisted and later interpreted by Windows as
    ``C:\\mnt\\<drive>\\...``.
    """

    local_os_name = os.name if runtime_os_name is None else runtime_os_name
    local_platform = sys.platform if runtime_platform is None else runtime_platform

    if origin_platform == "windows":
        windows_path = PureWindowsPath(raw_path)
        if (
            not windows_path.is_absolute()
            or len(windows_path.drive) != 2
            or windows_path.drive[1] != ":"
        ):
            raise SessionError(
                "Session exchange path does not match its recorded platform",
                code="session_state_invalid",
            )
        if local_os_name == "nt":
            return Path(raw_path)
        if not _is_wsl_runtime(local_platform):
            raise SessionError(
                "Windows session exchange path is accessible only from Windows or WSL",
                code="path_access_denied",
            )
        mount_root = Path(
            os.environ.get("DIPTRACE_MCP_WSL_MOUNT_ROOT", "/mnt")
        )
        if not mount_root.is_absolute():
            raise SessionError(
                "DIPTRACE_MCP_WSL_MOUNT_ROOT must be absolute",
                code="path_access_denied",
            )
        drive = windows_path.drive[0].lower()
        return mount_root / drive / Path(*windows_path.parts[1:])

    if origin_platform == "posix":
        posix_path = Path(raw_path)
        if not posix_path.is_absolute():
            raise SessionError(
                "Session exchange path does not match its recorded platform",
                code="session_state_invalid",
            )
        if local_os_name == "nt":
            raise SessionError(
                "Windows bridge refuses a POSIX session exchange path",
                code="session_state_invalid",
            )
        return posix_path

    raise SessionError(
        "Session metadata has no valid exchange-path platform",
        code="session_state_invalid",
    )


def install() -> None:
    """Install the compatibility boundary without rewriting session metadata."""

    from . import sessions as sessions_module

    if getattr(sessions_module, "_live_path_compat_installed", False):
        return

    session_store: Any = sessions_module.SessionStore
    original_create_unlocked = session_store._create_unlocked

    def create_unlocked(self: Any, exchange_path: Path) -> dict[str, Any]:
        metadata = original_create_unlocked(self, exchange_path)
        updated = self.update_metadata(
            str(metadata["session_id"]),
            exchange_path_platform=_current_exchange_path_platform(),
        )
        return cast(dict[str, Any], updated)

    def read_bound_exchange(
        self: Any,
        metadata: dict[str, Any],
    ) -> tuple[Path, bytes]:
        if self.allowed_roots is None:
            raise SessionError(
                "Session apply requires configured allowed roots",
                code="path_access_denied",
            )
        raw_path = metadata.get("exchange_path")
        origin_platform = metadata.get("exchange_path_platform")
        original_sha256 = metadata.get("original_sha256")
        session_id = metadata.get("session_id")
        if (
            not isinstance(raw_path, str)
            or not isinstance(origin_platform, str)
            or not isinstance(original_sha256, str)
            or not isinstance(session_id, str)
        ):
            raise SessionError(
                "Session metadata has no valid exchange-file binding",
                code="session_state_invalid",
            )
        try:
            original = self._read_original_bytes(session_id)
        except SessionError as exc:
            raise SessionError(
                "Session original XML is unavailable or redirected",
                code="session_state_invalid",
            ) from exc
        recorded_original_sha256 = sha256_bytes(original)
        if original_sha256 != recorded_original_sha256:
            raise SessionError(
                "Session metadata does not match the captured original XML",
                code="session_state_invalid",
            )

        local_path = _exchange_path_for_runtime(raw_path, origin_platform)
        exchange_path, exchange = self._read_exchange_path(local_path)
        current_sha256 = sha256_bytes(exchange)
        if current_sha256 != recorded_original_sha256:
            raise SessionError(
                "External exchange file changed after the live session started",
                code="sha256_mismatch",
                details={
                    "expected_sha256": recorded_original_sha256,
                    "current_sha256": current_sha256,
                },
            )
        return exchange_path, exchange

    session_store._create_unlocked = create_unlocked
    session_store._read_bound_exchange = read_bound_exchange
    sessions_module.__dict__["_current_exchange_path_platform"] = (
        _current_exchange_path_platform
    )
    sessions_module.__dict__["_exchange_path_for_runtime"] = _exchange_path_for_runtime
    sessions_module.__dict__["_live_path_compat_installed"] = True
