from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "src" / "diptrace_mcp" / "sessions.py"
INIT = ROOT / "src" / "diptrace_mcp" / "__init__.py"
COMPAT = ROOT / "src" / "diptrace_mcp" / "_live_path_compat.py"
ALLOWLIST = ROOT / "scripts" / "release_artifact_allowlist.txt"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-live-exchange-path-direct-fix.yml"
SELF = Path(__file__)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


text = SESSIONS.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from pathlib import Path\n",
    "from pathlib import Path, PureWindowsPath\n",
    "pathlib import",
)
text = replace_once(
    text,
    'BridgeImportMode = Literal["All", "None", "Unknown"]\n'
    'BridgeProcessLiveness = Literal["alive", "dead", "unknown"]\n',
    'BridgeImportMode = Literal["All", "None", "Unknown"]\n'
    'ExchangePathPlatform = Literal["windows", "posix"]\n'
    'BridgeProcessLiveness = Literal["alive", "dead", "unknown"]\n',
    "exchange path platform type",
)

helpers = r'''

def _current_exchange_path_platform() -> ExchangePathPlatform:
    """Return the native path syntax used by the process creating a session."""

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
    """Resolve immutable bridge-native metadata in this process namespace.

    Windows bridge metadata remains Windows-native. A WSL MCP process derives
    its /mnt/<drive>/ view in memory only and never persists the derived path.
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
'''
text = replace_once(
    text,
    "\n\nclass SessionStore(RecordStore):",
    helpers + "\n\nclass SessionStore(RecordStore):",
    "runtime path helpers",
)

old_method = '''    def _read_bound_exchange(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path, bytes]:
        if self.allowed_roots is None:
            raise SessionError(
                "Session apply requires configured allowed roots",
                code="path_access_denied",
            )
        raw_path = metadata.get("exchange_path")
        original_sha256 = metadata.get("original_sha256")
        session_id = metadata.get("session_id")
        if (
            not isinstance(raw_path, str)
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
        exchange_path, exchange = self._read_exchange_path(Path(raw_path))
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
'''
new_method = '''    def _read_bound_exchange(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path, bytes]:
        if self.allowed_roots is None:
            raise SessionError(
                "Session apply requires configured allowed roots",
                code="path_access_denied",
            )
        raw_path = metadata.get("exchange_path")
        raw_platform = metadata.get("exchange_path_platform")
        original_sha256 = metadata.get("original_sha256")
        session_id = metadata.get("session_id")
        if (
            not isinstance(raw_path, str)
            or not isinstance(raw_platform, str)
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
        local_path = _exchange_path_for_runtime(raw_path, raw_platform)
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
'''
text = replace_once(text, old_method, new_method, "bound exchange method")
text = replace_once(
    text,
    '            "exchange_path": str(exchange_path),\n'
    '            "working_path": str(working),\n',
    '            "exchange_path": str(exchange_path),\n'
    '            "exchange_path_platform": _current_exchange_path_platform(),\n'
    '            "working_path": str(working),\n',
    "session metadata platform",
)
SESSIONS.write_text(text, encoding="utf-8")

INIT.write_text(
    '''from importlib.metadata import PackageNotFoundError, version\n\n'''
    '''try:\n'''
    '''    __version__ = version("diptrace-mcp")\n'''
    '''except PackageNotFoundError:\n'''
    '''    __version__ = "0.1.0"\n\n'''
    '''__all__ = ["__version__"]\n''',
    encoding="utf-8",
)
COMPAT.unlink(missing_ok=True)

allowlist = ALLOWLIST.read_text(encoding="utf-8")
allowlist = allowlist.replace("src/diptrace_mcp/_live_path_compat.py\n", "")
ALLOWLIST.write_text(allowlist, encoding="utf-8")

WORKFLOW.unlink(missing_ok=True)
SELF.unlink(missing_ok=True)
