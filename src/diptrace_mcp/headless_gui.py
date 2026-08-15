"""Run bounded DipTrace GUI work on Windows.

This module is a host/runtime helper, not a new public MCP tool surface. Hidden
mode uses a separate WinSta0 desktop to avoid interfering with the operator's
input desktop; native mode is explicit and visible. Neither mode provides a
process, filesystem, network, token, or privilege sandbox, and there is no
physical mouse/keyboard fallback.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from .windows_configurator import (
    ConfiguratorError,
    detect_diptrace_installations,
    validate_diptrace_directory,
)

_EDITOR_EXECUTABLES = {
    "pcb": "Pcb.exe",
    "schematic": "Schematic.exe",
    "component": "CompEdit.exe",
    "pattern": "PattEdit.exe",
}

_DESKTOP_READOBJECTS = 0x0001
_DESKTOP_CREATEWINDOW = 0x0002
_DESKTOP_CREATEMENU = 0x0004
_DESKTOP_ENUMERATE = 0x0040
_DESKTOP_WRITEOBJECTS = 0x0080
_HIDDEN_DESKTOP_ACCESS = (
    _DESKTOP_READOBJECTS
    | _DESKTOP_CREATEWINDOW
    | _DESKTOP_CREATEMENU
    | _DESKTOP_ENUMERATE
    | _DESKTOP_WRITEOBJECTS
)
_UOI_NAME = 2
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102
_STILL_ACTIVE = 259
_WM_CLOSE = 0x0010
_WM_COMMAND = 0x0111
_WM_MENUCOMMAND = 0x0126
_DESKTOP_MODES = ("hidden", "native")
_INTERACTIVE_WINDOW_STATION = "WinSta0"


class HeadlessGuiError(RuntimeError):
    """Raised when the bounded native-GUI worker cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class RoundtripRequest:
    diptrace_root: Path
    project: Path
    editor: str
    timeout_seconds: float = 30.0
    save_menu: str = "File->Save"
    desktop_mode: str = "hidden"

    def __post_init__(self) -> None:
        editor = self.editor.strip().lower()
        if editor not in _EDITOR_EXECUTABLES:
            choices = ", ".join(sorted(_EDITOR_EXECUTABLES))
            raise ValueError(f"editor must be one of: {choices}")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("timeout_seconds must be > 0 and <= 300")
        if not self.save_menu.strip():
            raise ValueError("save_menu must not be empty")
        desktop_mode = self.desktop_mode.strip().lower()
        if desktop_mode not in _DESKTOP_MODES:
            choices = ", ".join(sorted(_DESKTOP_MODES))
            raise ValueError(f"desktop_mode must be one of: {choices}")
        object.__setattr__(self, "editor", editor)
        object.__setattr__(self, "desktop_mode", desktop_mode)
        object.__setattr__(self, "diptrace_root", Path(self.diptrace_root))
        object.__setattr__(self, "project", Path(self.project))

    @property
    def executable(self) -> Path:
        return self.diptrace_root / _EDITOR_EXECUTABLES[self.editor]

    def as_json(self) -> dict[str, object]:
        return {
            "diptrace_root": str(self.diptrace_root),
            "project": str(self.project),
            "editor": self.editor,
            "timeout_seconds": self.timeout_seconds,
            "save_menu": self.save_menu,
            "desktop_mode": self.desktop_mode,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> RoundtripRequest:
        return cls(
            diptrace_root=Path(_required_string(value, "diptrace_root")),
            project=Path(_required_string(value, "project")),
            editor=_required_string(value, "editor"),
            timeout_seconds=_coerce_float(value.get("timeout_seconds"), 30.0),
            save_menu=_string_or_default(value.get("save_menu"), "File->Save"),
            desktop_mode=_string_or_default(value.get("desktop_mode"), "hidden"),
        )


@dataclass(frozen=True, slots=True)
class RoundtripResult:
    ok: bool
    editor: str
    executable: str
    project: str
    worker_pid: int
    diptrace_pid: int | None
    automation_backend: str
    desktop_name: str
    input_desktop_before: str | None
    input_desktop_after: str | None
    sha256_before: str | None
    sha256_after: str | None
    forced_termination: bool = False
    error: str | None = None
    desktop_mode: str = "hidden"
    window_station_name: str | None = None
    session_id: int | None = None
    desktop_changed: bool = False

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> RoundtripResult:
        return cls(
            ok=bool(value.get("ok", False)),
            editor=_string_or_default(value.get("editor"), "unknown"),
            executable=_string_or_default(value.get("executable"), ""),
            project=_string_or_default(value.get("project"), ""),
            worker_pid=_coerce_int(value.get("worker_pid"), 0),
            diptrace_pid=_optional_int(value.get("diptrace_pid")),
            automation_backend=_string_or_default(
                value.get("automation_backend"), "unknown"
            ),
            desktop_name=_string_or_default(value.get("desktop_name"), "unknown"),
            input_desktop_before=_optional_string(value.get("input_desktop_before")),
            input_desktop_after=_optional_string(value.get("input_desktop_after")),
            sha256_before=_optional_string(value.get("sha256_before")),
            sha256_after=_optional_string(value.get("sha256_after")),
            forced_termination=bool(value.get("forced_termination", False)),
            error=_optional_string(value.get("error")),
            desktop_mode=_string_or_default(value.get("desktop_mode"), "hidden"),
            window_station_name=_optional_string(value.get("window_station_name")),
            session_id=_optional_int(value.get("session_id")),
            desktop_changed=bool(value.get("desktop_changed", False)),
        )


@dataclass(frozen=True, slots=True)
class DesktopSmokeResult:
    ok: bool
    desktop_name: str
    child_desktop_name: str | None
    input_desktop_before: str | None
    input_desktop_after: str | None
    child_exit_code: int | None
    error: str | None = None

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))


@dataclass(frozen=True, slots=True)
class NativeDesktopSmokeResult:
    ok: bool
    desktop_name: str | None
    child_desktop_name: str | None
    window_station_name: str | None
    child_window_station_name: str | None
    session_id: int | None
    child_session_id: int | None
    child_exit_code: int | None
    error: str | None = None

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _Win32Api:
    def __init__(self) -> None:
        if os.name != "nt":
            raise HeadlessGuiError("Windows GUI worker is available only on Windows")
        win_dll = ctypes.__dict__.get("WinDLL")
        if win_dll is None:
            raise HeadlessGuiError("Windows ctypes bindings are unavailable")
        self.user32: Any = win_dll("user32", use_last_error=True)
        self.kernel32: Any = win_dll("kernel32", use_last_error=True)
        self.shell32: Any = win_dll("shell32", use_last_error=True)
        self._configure()

    def _configure(self) -> None:
        self.user32.CreateDesktopW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.user32.CreateDesktopW.restype = wintypes.HANDLE
        self.user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.user32.CloseDesktop.restype = wintypes.BOOL
        self.user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
        self.user32.GetThreadDesktop.restype = wintypes.HANDLE
        self.user32.OpenInputDesktop.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.user32.OpenInputDesktop.restype = wintypes.HANDLE
        self.user32.GetProcessWindowStation.argtypes = []
        self.user32.GetProcessWindowStation.restype = wintypes.HANDLE
        self.user32.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetUserObjectInformationW.restype = wintypes.BOOL
        self.user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.PostMessageW.restype = wintypes.BOOL
        self.kernel32.CreateProcessW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOW),
            ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        self.kernel32.CreateProcessW.restype = wintypes.BOOL
        self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel32.TerminateProcess.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.GetCurrentThreadId.argtypes = []
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.kernel32.GetCurrentProcessId.argtypes = []
        self.kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        self.kernel32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        self.shell32.IsUserAnAdmin.argtypes = []
        self.shell32.IsUserAnAdmin.restype = wintypes.BOOL

    def error(self, operation: str) -> HeadlessGuiError:
        code = ctypes.get_last_error()
        detail = ctypes.FormatError(code).strip() if code else "unknown Windows error"
        return HeadlessGuiError(f"{operation} failed ({code}): {detail}")


class CreatedProcess:
    def __init__(self, api: _Win32Api, info: _PROCESS_INFORMATION) -> None:
        self._api = api
        self._process = info.hProcess
        self._thread = info.hThread
        self.pid = int(info.dwProcessId)
        self._closed = False

    def wait(self, timeout_seconds: float) -> int | None:
        milliseconds = min(round(max(timeout_seconds, 0) * 1000), 0xFFFFFFFE)
        result = int(self._api.kernel32.WaitForSingleObject(self._process, milliseconds))
        if result == _WAIT_TIMEOUT:
            return None
        if result != _WAIT_OBJECT_0:
            raise self._api.error("WaitForSingleObject")
        code = wintypes.DWORD(_STILL_ACTIVE)
        if not self._api.kernel32.GetExitCodeProcess(self._process, ctypes.byref(code)):
            raise self._api.error("GetExitCodeProcess")
        return int(code.value)

    def terminate(self, exit_code: int = 1) -> None:
        if not self._api.kernel32.TerminateProcess(self._process, exit_code):
            raise self._api.error("TerminateProcess")

    def close(self) -> None:
        if self._closed:
            return
        if self._thread:
            self._api.kernel32.CloseHandle(self._thread)
        if self._process:
            self._api.kernel32.CloseHandle(self._process)
        self._closed = True

    def __enter__(self) -> CreatedProcess:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


class HiddenDesktop:
    """A separate WinSta0 desktop that is never made the physical input desktop."""

    def __init__(self, name: str) -> None:
        _validate_desktop_name(name)
        self.name = name
        self._api = _Win32Api()
        self._handle: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"{_INTERACTIVE_WINDOW_STATION}\\{self.name}"

    def open(self) -> HiddenDesktop:
        if self._handle is not None:
            return self
        handle = self._api.user32.CreateDesktopW(
            self.name,
            None,
            None,
            0,
            _HIDDEN_DESKTOP_ACCESS,
            None,
        )
        if not handle:
            raise self._api.error("CreateDesktopW")
        self._handle = int(handle)
        return self

    def launch(self, argv: Sequence[str], *, cwd: Path | None = None) -> CreatedProcess:
        if self._handle is None:
            raise HeadlessGuiError("hidden desktop is not open")
        return _launch_process_on_desktop(argv, self.qualified_name, cwd=cwd)

    def close(self) -> None:
        if self._handle is None:
            return
        if not self._api.user32.CloseDesktop(self._handle):
            raise self._api.error("CloseDesktop")
        self._handle = None

    def __enter__(self) -> HiddenDesktop:
        return self.open()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


def _required_string(value: Mapping[str, object], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return raw


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        with suppress(ValueError):
            return int(value)
    return default


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    result = _coerce_int(value, -1)
    return None if result < 0 else result


def _coerce_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        with suppress(ValueError):
            return float(value)
    return default


def _validate_desktop_name(name: str) -> None:
    if not name.strip():
        raise ValueError("desktop name must not be empty")
    if "\\" in name or "/" in name or "\x00" in name:
        raise ValueError("desktop name must not contain path separators or NUL")
    if len(name) > 128:
        raise ValueError("desktop name is too long")


def _desktop_object_name(handle: int) -> str:
    api = _Win32Api()
    required = wintypes.DWORD()
    api.user32.GetUserObjectInformationW(
        handle,
        _UOI_NAME,
        None,
        0,
        ctypes.byref(required),
    )
    if required.value == 0:
        raise api.error("GetUserObjectInformationW(size)")
    chars = required.value // ctypes.sizeof(ctypes.c_wchar) + 1
    buffer = ctypes.create_unicode_buffer(max(chars, 1))
    if not api.user32.GetUserObjectInformationW(
        handle,
        _UOI_NAME,
        buffer,
        ctypes.sizeof(buffer),
        ctypes.byref(required),
    ):
        raise api.error("GetUserObjectInformationW")
    return buffer.value


def thread_desktop_name() -> str:
    api = _Win32Api()
    thread_id = int(api.kernel32.GetCurrentThreadId())
    handle = api.user32.GetThreadDesktop(thread_id)
    if not handle:
        raise api.error("GetThreadDesktop")
    return _desktop_object_name(int(handle))


def input_desktop_name() -> str | None:
    api = _Win32Api()
    handle = api.user32.OpenInputDesktop(0, False, _DESKTOP_READOBJECTS)
    if not handle:
        return None
    try:
        return _desktop_object_name(int(handle))
    finally:
        api.user32.CloseDesktop(handle)


def process_window_station_name() -> str:
    api = _Win32Api()
    handle = api.user32.GetProcessWindowStation()
    if not handle:
        raise api.error("GetProcessWindowStation")
    return _desktop_object_name(int(handle))


def process_session_id(pid: int | None = None) -> int:
    api = _Win32Api()
    process_id = int(api.kernel32.GetCurrentProcessId()) if pid is None else int(pid)
    session_id = wintypes.DWORD()
    if not api.kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
        raise api.error("ProcessIdToSessionId")
    return int(session_id.value)


def process_is_elevated() -> bool:
    api = _Win32Api()
    return bool(api.shell32.IsUserAnAdmin())


def _interactive_context() -> tuple[str, str, int]:
    desktop = input_desktop_name()
    if desktop is None:
        raise HeadlessGuiError(
            "cannot determine the current input desktop; native launch declined"
        )
    _validate_desktop_name(desktop)
    station = process_window_station_name()
    if station.casefold() != _INTERACTIVE_WINDOW_STATION.casefold():
        raise HeadlessGuiError(
            f"native launch requires {_INTERACTIVE_WINDOW_STATION}; "
            f"current window station is {station!r}"
        )
    return desktop, station, process_session_id()


def _launch_process_on_desktop(
    argv: Sequence[str],
    qualified_desktop: str,
    *,
    cwd: Path | None = None,
) -> CreatedProcess:
    if not argv or not str(argv[0]).strip():
        raise ValueError("argv must contain an executable")
    if "\\" not in qualified_desktop:
        raise ValueError("qualified desktop must include a window station")
    api = _Win32Api()
    application = str(argv[0])
    command = ctypes.create_unicode_buffer(
        subprocess.list2cmdline([str(item) for item in argv])
    )
    desktop_buffer = ctypes.create_unicode_buffer(qualified_desktop)
    startup = _STARTUPINFOW()
    startup.cb = ctypes.sizeof(_STARTUPINFOW)
    startup.lpDesktop = ctypes.cast(desktop_buffer, wintypes.LPWSTR)
    info = _PROCESS_INFORMATION()
    created = api.kernel32.CreateProcessW(
        application,
        command,
        None,
        None,
        False,
        0,
        None,
        str(cwd) if cwd is not None else None,
        ctypes.byref(startup),
        ctypes.byref(info),
    )
    if not created:
        raise api.error("CreateProcessW")
    return CreatedProcess(api, info)


def _launch_on_current_desktop(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    require_non_elevated: bool = True,
) -> CreatedProcess:
    """Launch on the verified current WinSta0 input desktop.

    Native mode is visible and is intentionally refused from an elevated caller.
    It does not inherit an unspecified desktop: STARTUPINFO.lpDesktop explicitly
    targets the current ``WinSta0\\<input-desktop>``.
    """
    if require_non_elevated and process_is_elevated():
        raise HeadlessGuiError(
            "native launch declined from an elevated process; run the GUI worker "
            "with the normal user token"
        )
    desktop, station, session = _interactive_context()
    child = _launch_process_on_desktop(argv, f"{station}\\{desktop}", cwd=cwd)
    try:
        child_session = process_session_id(child.pid)
        if child_session != session:
            raise HeadlessGuiError(
                f"native child session mismatch: {child_session} != {session}"
            )
        return child
    except Exception:
        with suppress(Exception):
            child.terminate(126)
        child.close()
        raise


def _entry_argv(subcommand: str, *args: str, frozen: bool | None = None) -> list[str]:
    if frozen is None:
        frozen = bool(sys.__dict__.get("frozen", False))
    if frozen:
        return [sys.executable, subcommand, *args]
    return [sys.executable, "-m", "diptrace_mcp.headless_gui", subcommand, *args]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HeadlessGuiError(f"cannot read worker JSON: {path}") from exc
    if not isinstance(value, dict):
        raise HeadlessGuiError(f"worker JSON root must be an object: {path}")
    return cast(dict[str, object], value)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_error(existing: str | None, extra: str) -> str:
    return f"{existing}; {extra}" if existing else extra


def desktop_smoke_test(*, timeout_seconds: float = 15.0) -> DesktopSmokeResult:
    if os.name != "nt":
        return DesktopSmokeResult(
            False,
            "",
            None,
            None,
            None,
            None,
            "headless GUI isolation is available only on Windows",
        )
    name = f"DipTraceMCP-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    before = input_desktop_name()
    child_name: str | None = None
    child_exit: int | None = None
    error: str | None = None
    with tempfile.TemporaryDirectory(prefix="diptrace-headless-smoke-") as raw_temp:
        result_path = Path(raw_temp) / "probe.json"
        try:
            with HiddenDesktop(name) as desktop:
                argv = _entry_argv("_probe", "--result", str(result_path))
                with desktop.launch(argv) as child:
                    child_exit = child.wait(timeout_seconds)
                    if child_exit is None:
                        child.terminate(124)
                        child_exit = child.wait(2.0)
                        raise HeadlessGuiError("hidden desktop probe timed out")
            probe = _load_json(result_path)
            child_name = _required_string(probe, "desktop_name")
            if child_name.casefold() != name.casefold():
                raise HeadlessGuiError(
                    f"child connected to unexpected desktop: {child_name!r} != {name!r}"
                )
            if child_exit != 0:
                raise HeadlessGuiError(f"hidden desktop probe exited with code {child_exit}")
        except (HeadlessGuiError, OSError, ValueError) as exc:
            error = str(exc)
    after = input_desktop_name()
    if error is None and before is not None and after is not None and before != after:
        error = f"input desktop changed unexpectedly: {before!r} -> {after!r}"
    return DesktopSmokeResult(
        error is None,
        name,
        child_name,
        before,
        after,
        child_exit,
        error,
    )


def native_desktop_smoke_test(
    *, timeout_seconds: float = 15.0
) -> NativeDesktopSmokeResult:
    if os.name != "nt":
        return NativeDesktopSmokeResult(
            False, None, None, None, None, None, None, None, "Windows is required"
        )
    desktop: str | None = None
    station: str | None = None
    session: int | None = None
    child_desktop: str | None = None
    child_station: str | None = None
    child_session: int | None = None
    child_exit: int | None = None
    error: str | None = None
    with tempfile.TemporaryDirectory(prefix="diptrace-native-smoke-") as raw_temp:
        result_path = Path(raw_temp) / "probe.json"
        try:
            desktop, station, session = _interactive_context()
            argv = _entry_argv("_probe", "--result", str(result_path))
            # This probe performs no DipTrace or UI mutation. It may run on an
            # elevated CI runner so the Win32 desktop/session primitive is still
            # exercised there; real native round-trips remain non-elevated only.
            with _launch_on_current_desktop(
                argv, require_non_elevated=False
            ) as child:
                child_exit = child.wait(timeout_seconds)
                if child_exit is None:
                    child.terminate(124)
                    child_exit = child.wait(2.0)
                    raise HeadlessGuiError("native desktop probe timed out")
            probe = _load_json(result_path)
            child_desktop = _required_string(probe, "desktop_name")
            child_station = _required_string(probe, "window_station_name")
            child_session = _coerce_int(probe.get("session_id"), -1)
            if child_exit != 0:
                raise HeadlessGuiError(f"native desktop probe exited with code {child_exit}")
            if child_desktop.casefold() != desktop.casefold():
                raise HeadlessGuiError(
                    f"native child desktop mismatch: {child_desktop!r} != {desktop!r}"
                )
            if child_station.casefold() != station.casefold():
                raise HeadlessGuiError(
                    f"native child window station mismatch: {child_station!r} != {station!r}"
                )
            if child_session != session:
                raise HeadlessGuiError(
                    f"native child session mismatch: {child_session} != {session}"
                )
        except (HeadlessGuiError, OSError, ValueError) as exc:
            error = str(exc)
    return NativeDesktopSmokeResult(
        error is None,
        desktop,
        child_desktop,
        station,
        child_station,
        session,
        child_session,
        child_exit,
        error,
    )


def _validated_request(request: RoundtripRequest) -> RoundtripRequest:
    try:
        installation = validate_diptrace_directory(request.diptrace_root)
    except ConfiguratorError as exc:
        raise HeadlessGuiError(str(exc)) from exc
    executable = installation.root / _EDITOR_EXECUTABLES[request.editor]
    if not executable.is_file():
        raise HeadlessGuiError(f"selected DipTrace editor is missing: {executable}")
    project = request.project.expanduser().resolve(strict=False)
    if not project.is_file():
        raise HeadlessGuiError(f"project file does not exist: {project}")
    return RoundtripRequest(
        installation.root,
        project,
        request.editor,
        request.timeout_seconds,
        request.save_menu,
        request.desktop_mode,
    )


def run_native_roundtrip(request: RoundtripRequest) -> RoundtripResult:
    if os.name != "nt":
        raise HeadlessGuiError("native headless round-trip is available only on Windows")
    request = _validated_request(request)
    desktop_name = f"DipTraceMCP-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    before = input_desktop_name()
    station_before = process_window_station_name()
    session_before = process_session_id()
    if request.desktop_mode == "native":
        if process_is_elevated():
            raise HeadlessGuiError(
                "native launch declined from an elevated process; run the GUI worker "
                "with the normal user token"
            )
        if before is None:
            raise HeadlessGuiError(
                "cannot determine the current input desktop; native launch declined"
            )
        _validate_desktop_name(before)
        if station_before.casefold() != _INTERACTIVE_WINDOW_STATION.casefold():
            raise HeadlessGuiError(
                f"native launch requires {_INTERACTIVE_WINDOW_STATION}; "
                f"current window station is {station_before!r}"
            )
    with tempfile.TemporaryDirectory(prefix="diptrace-headless-") as raw_temp:
        temp = Path(raw_temp)
        request_path = temp / "request.json"
        result_path = temp / "result.json"
        request_payload = request.as_json()
        request_payload["_expected_window_station"] = station_before
        request_payload["_expected_session_id"] = session_before
        _write_json(request_path, request_payload)
        if request.desktop_mode == "native":
            assert before is not None
            argv = _entry_argv(
                "_worker",
                "--request",
                str(request_path),
                "--result",
                str(result_path),
                "--desktop-name",
                before,
            )
            with _launch_on_current_desktop(argv) as worker:
                exit_code = worker.wait(request.timeout_seconds + 20.0)
                if exit_code is None:
                    worker.terminate(124)
                    worker.wait(2.0)
                    raise HeadlessGuiError("native DipTrace worker timed out")
        else:
            with HiddenDesktop(desktop_name) as desktop:
                argv = _entry_argv(
                    "_worker",
                    "--request",
                    str(request_path),
                    "--result",
                    str(result_path),
                    "--desktop-name",
                    desktop_name,
                )
                with desktop.launch(argv) as worker:
                    exit_code = worker.wait(request.timeout_seconds + 20.0)
                    if exit_code is None:
                        worker.terminate(124)
                        worker.wait(2.0)
                        raise HeadlessGuiError("headless DipTrace worker timed out")
        if not result_path.is_file():
            raise HeadlessGuiError(
                f"headless worker exited with code {exit_code} without a result"
            )
        result = RoundtripResult.from_json(_load_json(result_path))

    after = input_desktop_name()
    station_after = process_window_station_name()
    session_after = process_session_id()
    evidence_error: str | None = None
    desktop_changed = False
    if before is not None and after is not None and before != after:
        desktop_changed = True
        evidence_error = (
            f"input desktop changed unexpectedly after worker side effects: "
            f"{before!r} -> {after!r}"
        )
    elif request.desktop_mode == "native" and after is None:
        evidence_error = (
            "cannot determine input desktop after native worker side effects; "
            "result retained as failed evidence"
        )
    if station_after.casefold() != station_before.casefold():
        evidence_error = _append_error(
            evidence_error,
            f"window station changed unexpectedly: {station_before!r} -> {station_after!r}",
        )
    if session_after != session_before:
        evidence_error = _append_error(
            evidence_error,
            f"session changed unexpectedly: {session_before} -> {session_after}",
        )
    result = replace(
        result,
        input_desktop_before=before,
        input_desktop_after=after,
        window_station_name=station_after,
        session_id=session_after,
        desktop_changed=desktop_changed,
    )
    if evidence_error is not None:
        result = replace(
            result,
            ok=False,
            error=_append_error(result.error, evidence_error),
        )
    return result


def _pywinauto_application() -> Any:
    if importlib.util.find_spec("pywinauto") is None:
        raise HeadlessGuiError(
            "pywinauto is not installed; install diptrace-mcp[headless-gui] "
            "or use the bundled Windows headless GUI executable"
        )
    from pywinauto.application import Application

    return Application


def _window_titles(app: Any) -> list[str]:
    titles: list[str] = []
    with suppress(Exception):
        for window in app.windows():
            with suppress(Exception):
                title = str(window.window_text()).strip()
                if title:
                    titles.append(title)
    return titles


def _main_window(app: Any, project: Path, timeout_seconds: float) -> Any:
    identifiers = {project.name.casefold(), project.stem.casefold()}
    deadline = time.monotonic() + timeout_seconds
    while True:
        fallback_handle: int | None = None
        for window in app.windows(visible_only=False, enabled_only=True):
            with suppress(Exception):
                title = str(window.window_text()).casefold()
                if any(identifier and identifier in title for identifier in identifiers):
                    fallback_handle = int(window.handle)
                    if window.menu() is not None:
                        return app.window(handle=fallback_handle)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if fallback_handle is not None:
                return app.window(handle=fallback_handle)
            raise HeadlessGuiError(
                f"DipTrace main window for {project.name!r} was not found"
            )
        time.sleep(min(0.1, remaining))


def _post_window_message(hwnd: int, message: int, wparam: int = 0, lparam: int = 0) -> None:
    api = _Win32Api()
    if not api.user32.PostMessageW(hwnd, message, wparam, lparam):
        raise api.error("PostMessageW")


def _save_window(window: Any, save_menu: str) -> None:
    menu: Any = None
    with suppress(Exception):
        menu = window.menu()
    if menu is None:
        raise HeadlessGuiError("DipTrace project window has no native menu")
    normalized_path = "->".join(
        part.replace("&", "").strip().casefold() for part in save_menu.split("->")
    )
    try:
        item = window.menu_item(save_menu)
        enabled = item.is_enabled()
    except Exception as exc:
        if normalized_path != "file->save":
            raise HeadlessGuiError(f"native menu item {save_menu!r} was not found") from exc
        item = window.menu_item("#0->#4")
        enabled = item.is_enabled()
    if not enabled:
        raise HeadlessGuiError(f"native menu item {save_menu!r} is disabled")
    command = int(item.menu.COMMAND)
    if command == _WM_COMMAND:
        command_id = int(item.item_id())
        if not 1 <= command_id <= 0xFFFF:
            raise HeadlessGuiError(f"invalid native menu command ID: {command_id}")
        wparam, lparam = command_id, 0
    elif command == _WM_MENUCOMMAND:
        wparam, lparam = int(item.index()), int(item.menu.handle)
        if wparam < 0 or lparam <= 0:
            raise HeadlessGuiError("invalid native menu position or handle")
    else:
        raise HeadlessGuiError(f"unsupported native menu command: {command:#x}")
    _post_window_message(int(window.handle), command, wparam, lparam)


def _perform_worker_roundtrip(
    request: RoundtripRequest,
    *,
    desktop_name: str,
) -> RoundtripResult:
    request = _validated_request(request)
    before = input_desktop_name()
    sha_before = _sha256(request.project)
    application_class = _pywinauto_application()
    app: Any = None
    pid: int | None = None
    forced = False
    error: str | None = None
    try:
        command = subprocess.list2cmdline([str(request.executable), str(request.project)])
        app = application_class(backend="win32").start(
            command,
            timeout=request.timeout_seconds,
        )
        pid = int(app.process)
        window = _main_window(app, request.project, request.timeout_seconds)
        window.wait("exists enabled", timeout=request.timeout_seconds)
        _save_window(window, request.save_menu)
        # Both messages target the same GUI queue, so WM_CLOSE cannot overtake Save.
        _post_window_message(int(window.handle), _WM_CLOSE)
        try:
            app.wait_for_process_exit(timeout=min(10.0, request.timeout_seconds))
        except Exception as exc:
            forced = True
            raise HeadlessGuiError("DipTrace did not exit after Save/Close") from exc
    except Exception as exc:
        titles = _window_titles(app) if app is not None else []
        suffix = f"; open windows: {titles!r}" if titles else ""
        error = f"{type(exc).__name__}: {exc}{suffix}"
        if app is not None:
            with suppress(Exception):
                forced = True
                app.kill(soft=False)
    after = input_desktop_name()
    if before is not None and after is not None and before != after:
        error = error or f"input desktop changed unexpectedly: {before!r} -> {after!r}"
    return RoundtripResult(
        ok=error is None,
        editor=request.editor,
        executable=str(request.executable),
        project=str(request.project),
        worker_pid=os.getpid(),
        diptrace_pid=pid,
        automation_backend="pywinauto-win32-message",
        desktop_name=desktop_name,
        input_desktop_before=before,
        input_desktop_after=after,
        sha256_before=sha_before,
        sha256_after=_sha256(request.project),
        forced_termination=forced,
        error=error,
        desktop_mode=request.desktop_mode,
        window_station_name=process_window_station_name(),
        session_id=process_session_id(),
    )


def _cmd_probe(args: argparse.Namespace) -> int:
    result_path = Path(str(args.result))
    try:
        _write_json(
            result_path,
            {
                "desktop_name": thread_desktop_name(),
                "window_station_name": process_window_station_name(),
                "session_id": process_session_id(),
                "elevated": process_is_elevated(),
                "pid": os.getpid(),
            },
        )
        return 0
    except (HeadlessGuiError, OSError, ValueError) as exc:
        _write_json(result_path, {"error": str(exc), "pid": os.getpid()})
        return 1


def _cmd_worker(args: argparse.Namespace) -> int:
    result_path = Path(str(args.result))
    desktop_name = str(args.desktop_name)
    request_payload: dict[str, object] = {}
    try:
        request_payload = _load_json(Path(str(args.request)))
        request = RoundtripRequest.from_json(request_payload)
        actual = thread_desktop_name()
        if actual.casefold() != desktop_name.casefold():
            raise HeadlessGuiError(
                f"worker connected to unexpected desktop: {actual!r} != {desktop_name!r}"
            )
        expected_station = _required_string(
            request_payload, "_expected_window_station"
        )
        actual_station = process_window_station_name()
        if actual_station.casefold() != expected_station.casefold():
            raise HeadlessGuiError(
                f"worker connected to unexpected window station: "
                f"{actual_station!r} != {expected_station!r}"
            )
        expected_session = _coerce_int(
            request_payload.get("_expected_session_id"), -1
        )
        actual_session = process_session_id()
        if expected_session < 0 or actual_session != expected_session:
            raise HeadlessGuiError(
                f"worker connected to unexpected session: "
                f"{actual_session} != {expected_session}"
            )
        if request.desktop_mode == "native" and process_is_elevated():
            raise HeadlessGuiError("native worker unexpectedly has an elevated token")
        result = _perform_worker_roundtrip(request, desktop_name=desktop_name)
        result = replace(
            result,
            window_station_name=actual_station,
            session_id=actual_session,
        )
    except Exception as exc:
        current_input = input_desktop_name() if os.name == "nt" else None
        current_station: str | None = None
        current_session: int | None = None
        if os.name == "nt":
            with suppress(Exception):
                current_station = process_window_station_name()
            with suppress(Exception):
                current_session = process_session_id()
        result = RoundtripResult(
            False,
            "unknown",
            "",
            "",
            os.getpid(),
            None,
            "pywinauto-win32-message",
            desktop_name,
            current_input,
            current_input,
            None,
            None,
            error=f"{type(exc).__name__}: {exc}",
            desktop_mode=_string_or_default(
                request_payload.get("desktop_mode"), "hidden"
            ),
            window_station_name=current_station,
            session_id=current_session,
        )
    _write_json(result_path, result.as_json())
    return 0 if result.ok else 1


def _cmd_smoke(args: argparse.Namespace) -> int:
    result = desktop_smoke_test(timeout_seconds=float(args.timeout))
    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _cmd_native_smoke(args: argparse.Namespace) -> int:
    result = native_desktop_smoke_test(timeout_seconds=float(args.timeout))
    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _resolve_diptrace_root(raw: str | None) -> Path | None:
    if raw:
        return Path(raw)
    installations = detect_diptrace_installations()
    return installations[0].root if installations else None


def _cmd_doctor(args: argparse.Namespace) -> int:
    if os.name != "nt":
        print(json.dumps({"ok": False, "error": "Windows is required"}, indent=2))
        return 1
    smoke = desktop_smoke_test(timeout_seconds=float(args.timeout))
    root = _resolve_diptrace_root(args.diptrace_root)
    pywinauto_available = importlib.util.find_spec("pywinauto") is not None
    installation_error: str | None = None
    if root is not None:
        try:
            root = validate_diptrace_directory(root).root
        except ConfiguratorError as exc:
            installation_error = str(exc)
    ok = smoke.ok and installation_error is None
    if args.require_automation:
        ok = ok and root is not None and pywinauto_available
    report = {
        "ok": ok,
        "hidden_desktop": smoke.as_json(),
        "diptrace_root": str(root) if root is not None else None,
        "diptrace_error": installation_error,
        "pywinauto_available": pywinauto_available,
        "physical_input_fallback": False,
        "desktop_is_security_sandbox": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _cmd_roundtrip(args: argparse.Namespace) -> int:
    request = RoundtripRequest(
        Path(str(args.diptrace_root)),
        Path(str(args.project)),
        str(args.editor),
        float(args.timeout),
        str(args.save_menu),
        str(args.desktop),
    )
    try:
        result = run_native_roundtrip(request)
    except (HeadlessGuiError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-headless-gui",
        description=(
            "Run bounded DipTrace GUI work; hidden mode uses an isolated Win32 desktop."
        ),
    )
    subs = parser.add_subparsers(dest="command", required=True)

    smoke = subs.add_parser("smoke", help="verify hidden desktop isolation")
    smoke.add_argument("--timeout", type=float, default=15.0)
    smoke.set_defaults(handler=_cmd_smoke)

    native_smoke = subs.add_parser(
        "native-smoke",
        help="verify native WinSta0 desktop, window-station and session targeting",
    )
    native_smoke.add_argument("--timeout", type=float, default=15.0)
    native_smoke.set_defaults(handler=_cmd_native_smoke)

    doctor = subs.add_parser("doctor", help="check Windows and DipTrace readiness")
    doctor.add_argument("--diptrace-root")
    doctor.add_argument("--timeout", type=float, default=15.0)
    doctor.add_argument("--require-automation", action="store_true")
    doctor.set_defaults(handler=_cmd_doctor)

    roundtrip = subs.add_parser("roundtrip", help="open, native-save and close a project")
    roundtrip.add_argument("--diptrace-root", required=True)
    roundtrip.add_argument("--project", required=True)
    roundtrip.add_argument("--editor", choices=sorted(_EDITOR_EXECUTABLES), required=True)
    roundtrip.add_argument("--timeout", type=float, default=30.0)
    roundtrip.add_argument("--save-menu", default="File->Save")
    roundtrip.add_argument("--desktop", choices=tuple(_DESKTOP_MODES), default="hidden")
    roundtrip.set_defaults(handler=_cmd_roundtrip)

    worker = subs.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--request", required=True)
    worker.add_argument("--result", required=True)
    worker.add_argument("--desktop-name", required=True)
    worker.set_defaults(handler=_cmd_worker)

    probe = subs.add_parser("_probe", help=argparse.SUPPRESS)
    probe.add_argument("--result", required=True)
    probe.set_defaults(handler=_cmd_probe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
