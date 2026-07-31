from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "src" / "diptrace_mcp" / "sessions.py"
DOCS = ROOT / "docs" / "WINDOWS_WSL_LOCK_INTEROP.md"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-live-exchange-path-fix.yml"


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


text = SESSIONS.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from pathlib import Path\n",
    "from pathlib import Path, PureWindowsPath\n",
    label="pathlib import",
)
text = replace_once(
    text,
    'BridgeImportMode = Literal["All", "None", "Unknown"]\n'
    'BridgeProcessLiveness = Literal["alive", "dead", "unknown"]\n',
    'BridgeImportMode = Literal["All", "None", "Unknown"]\n'
    'ExchangePathPlatform = Literal["windows", "posix"]\n'
    'BridgeProcessLiveness = Literal["alive", "dead", "unknown"]\n',
    label="exchange path platform type",
)

helpers = r'''

def _current_exchange_path_platform() -> ExchangePathPlatform:
    """Record the native path syntax used by the bridge that created a session."""

    return "windows" if os.name == "nt" else "posix"


def _is_wsl_runtime(runtime_platform: str) -> bool:
    if not runtime_platform.startswith("linux"):
        return False
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(
            encoding="ascii",
        )
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
    """Resolve an immutable bridge-native path in the current process namespace.

    Windows bridge metadata remains Windows-native. A WSL MCP process derives its
    /mnt/<drive>/ view in memory only; it never persists that derived path back into
    session metadata. This keeps the Windows bridge from treating /mnt/c/... as the
    relative phantom target C:\\mnt\\c\\....
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
    label="runtime path helpers",
)
text = replace_once(
    text,
    "        exchange_path, exchange = self._read_exchange_path(Path(raw_path))\n",
    "        raw_platform = metadata.get(\"exchange_path_platform\")\n"
    "        if not isinstance(raw_platform, str):\n"
    "            raise SessionError(\n"
    "                \"Session metadata has no valid exchange-path platform\",\n"
    "                code=\"session_state_invalid\",\n"
    "            )\n"
    "        local_exchange_path = _exchange_path_for_runtime(\n"
    "            raw_path,\n"
    "            raw_platform,\n"
    "        )\n"
    "        exchange_path, exchange = self._read_exchange_path(local_exchange_path)\n",
    label="bound exchange resolution",
)
text = replace_once(
    text,
    '            "exchange_path": str(exchange_path),\n'
    '            "working_path": str(working),\n',
    '            "exchange_path": str(exchange_path),\n'
    '            "exchange_path_platform": _current_exchange_path_platform(),\n'
    '            "working_path": str(working),\n',
    label="session metadata platform",
)
SESSIONS.write_text(text, encoding="utf-8")

note = """

## Native exchange-path binding across Windows and WSL

A live session records the exchange path in the native syntax of the bridge
that created it. The Windows bridge therefore keeps a `C:\\...` path in
`metadata.json`. A WSL MCP server derives `/mnt/<drive>/...` only in memory for
its own validation and never writes that derived value back to session state.

`DIPTRACE_MCP_WSL_MOUNT_ROOT` may override the default `/mnt` drive-mount root.
It must be an absolute path. A path whose syntax disagrees with the recorded
platform fails closed before `control.json` is published, preventing Windows
from resolving `/mnt/c/...` as a phantom `C:\\mnt\\c\\...` target.
"""
docs = DOCS.read_text(encoding="utf-8")
if "## Native exchange-path binding across Windows and WSL" not in docs:
    DOCS.write_text(docs.rstrip() + note + "\n", encoding="utf-8")

WORKFLOW.unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
