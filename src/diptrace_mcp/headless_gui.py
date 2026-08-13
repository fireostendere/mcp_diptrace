"""Isolated DipTrace GUI worker for Windows hidden desktops.

The public MCP tool surface intentionally does not depend on this module.  It is a
host/runtime helper for native DipTrace operations that cannot be completed from
XML alone.  The worker never switches the user's input desktop and deliberately
has no physical mouse/keyboard fallback.
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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

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
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_STILL_ACTIVE = 259


class HeadlessGuiError(RuntimeError):
    """A bounded, user-actionable hidden-GUI runtime error."""


@dataclass(frozen=True, slots=True)
class RoundtripRequest:
    diptrace_root: Path
    project: Path
    editor: str
    timeout_seconds: float = 30.0
    save_menu: str = "File->Save"

    def __post_init__(self) -> None:
        normalized_editor = self.editor.strip().lower()
        if normalized_editor not in _EDITOR_EXECUTABLES:
            choices = ", ".join(sorted(_EDITOR_EXECUTABLES))
            raise ValueError(f"editor must be one of: {choices}")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("timeout_seconds must be > 0 and <= 300")
        if not self.save_menu.strip():
            raise ValueError("save_menu must not be empty")
        object.__setattr__(self, "editor", normalized_editor)
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
        }

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> RoundtripRequest:
        return cls(
            diptrace_root=Path(_required_string(value, "diptrace_root")),
            project=Path(_required_string(value, "project")),
            editor=_required_string(value, "editor"),
            timeout_seconds=float(value.get("timeout_seconds", 30.0)),
            save_menu=str(value.get("save_menu", "File->Save")),
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

    def as_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> RoundtripResult:
        return cls(
            ok=bool(value.get("ok", False)),
            editor=_required_string(value, "editor"),
            executable=_required_string(value, "executable"),
            project=_required_string(value, "project"),
            worker_pid=int(value.get("worker_pid", 0)),
            diptrace_pid=_optional_int(value.get("diptrace_pid")),
            automation_backend=str(value.get("automation_backend", "unknown")),
            desktop_name=_required_string(value, "desktop_name"),
            input_desktop_before=_optional_string(value.get("input_desktop_before")),
            input_desktop_after=_optional_string(value.get("input_desktop_after")),
            sha256_before=_optional_string(value.get("sha256_before")),
            sha256_after=_optional_string(value.get("sha256_after")),
            forced_termination=bool(value.get("forced_termination", False)),
            error=_optional_string(value.get("error")),
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
        return asdict(self)


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
            raise HeadlessGuiError("headless GUI isolation is available only on Windows")
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise HeadlessGuiError("Windows ctypes bindings are unavailable")
        self.user32: Any = win_dll("user32", use_last_error=True)
        self.kernel32: Any = win_dll("kernel32", use_last_error=True)
        self._configure_prototypes()

    def _configure_prototypes(self) -> None:
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
        self.user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.user32.OpenInputDesktop.restype = wintypes.HANDLE
        self.user32.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetUserObjectInformationW.restype = wintypes.BOOL
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

    def error(self, operation: str) -> HeadlessGuiError:
        code = ctypes.get_last_error()
        message = ctypes.FormatError(code).strip() if code else "unknown Windows error"
        return HeadlessGuiError(f"{operation} failed ({code}): {message}")


class CreatedProcess:
    def __init__(self, api: _Win32Api, process_info: _PROCESS_INFORMATION) -> None:
        self._api = api
        self._process_handle = process_info.hProcess
        self._thread_handle = process_info.hThread
        self.pid = int(process_info.dwProcessId)
        self._closed = False

    def wait(self, timeout_seconds: float) -> int | None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")
        milliseconds = min(round(timeout_seconds * 1000), 0xFFFFFFFE)
        result = int(self._api.kernel32.WaitForSingleObject(self._process_handle, milliseconds))
        if result == _WAIT_TIMEOUT:
            return None
        if result != _WAIT_OBJECT_0:
            raise self._api.error("WaitForSingleObject")
        exit_code = wintypes.DWORD(_STILL_ACTIVE)
        if not self._api.kernel32.GetExitCodeProcess(
            self._process_handle,
            ctypes.byref(exit_code),
        ):
            raise self._api.error("GetExitCodeProcess")
        return int(exit_code.value)

    def terminate(self, exit_code: int = 1) -> None:
        if not self._api.kernel32.TerminateProcess(self._process_handle, exit_code):
            raise self._api.error("TerminateProcess")

    def close(self) -> None:
        if self._closed:
            return
        if self._thread_handle:
            self._api.kernel32.CloseHandle(self._thread_handle)
        if self._process_handle:
            self._api.kernel32.CloseHandle(self._process_handle)
        self._closed = True

    def __enter__(self) -> CreatedProcess:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


class HiddenDesktop:
    """A WinSta0 desktop that is never switched onto the physical input device."""

    def __init__(self, name: str) -> None:
        _validate_desktop_name(name)
        self.name = name
        self._api = _Win32Api()
        self._handle: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"WinSta0\\{self.name}"

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
        if not argv or not str(argv[0]).strip():
            raise ValueError("argv must contain an executable")
        application = str(argv[0])
        command_line = subprocess.list2cmdline([str(item) for item in argv])
        command_buffer = ctypes.create_unicode_buffer(command_line)
        desktop_buffer = ctypes.create_unicode_buffer(self.qualified_name)
        startup = _STARTUPINFOW()
        startup.cb = ctypes.sizeof(_STARTUPINFOW)
        startup.lpDesktop = ctypes.cast(desktop_buffer, wintypes.LPWSTR)
        process_info = _PROCESS_INFORMATION()
        current_directory = str(cwd) if cwd is not None else None
        created = self._api.kernel32.CreateProcessW(
            application,
            command_buffer,
            None,
            None,
            False,
            0,
            None,
            current_directory,
            ctypes.byref(startup),
            ctypes.byref(process_info),
        )
        if not created:
            raise self._api.error("CreateProcessW")
        return CreatedProcess(self._api, process_info)

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


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _validate_desktop_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("desktop name must not be empty")
    if "\\" in name or "/" in name:
        raise ValueError("desktop name must not contain path separators")
    if len(name) > 128:
        raise ValueError("desktop name is too long")


def _desktop_object_name(handle: int) -> str:
    api = _Win32Api()
    required = wintypes.DWORD()
    api.user32.GetUserObjectInformationW(handle, _UOI_NAME, None, 0, ctypes.byref(required))
    if required.value == 0:
        raise api.error("GetUserObjectInformationW(size)")
    char_count = required.value // ctypes.sizeof(ctypes.c_wchar) + 1
    buffer = ctypes.create_unicode_buffer(max(1, char_count))
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
    """Return the current physical input desktop name, or None when unavailable."""

    api = _Win32Api()
    handle = api.user32.OpenInputDesktop(0, False, _DESKTOP_READOBJECTS)
    if not handle:
        return None
    try:
        return _desktop_object_name(int(handle))
    finally:
        api.user32.CloseDesktop(handle)


def _entry_argv(subcommand: str, *args: str, frozen: bool | None = None) -> list[str]:
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HeadlessGuiError(f"cannot read worker JSON: {path}") from exc
    if not isinstance(value, dict):
        raise HeadlessGuiError(f"worker JSON root must be an object: {path}")
    return value


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


def desktop_smoke_test(*, timeout_seconds: float = 15.0) -> DesktopSmokeResult:
    if os.name != "nt":
        return DesktopSmokeResult(
            ok=False,
            desktop_name="",
            child_desktop_name=None,
            input_desktop_before=None,
            input_desktop_after=None,
            child_exit_code=None,
            error="headless GUI isolation is available only on Windows",
        )
    desktop_name = f"DipTraceMCP-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    before = input_desktop_name()
    child_name: str | None = None
    child_exit: int | None = None
    error: str | None = None
    with tempfile.TemporaryDirectory(prefix="diptrace-headless-smoke-") as raw_temp:
        result_path = Path(raw_temp) / "probe.json"
        try:
            with HiddenDesktop(desktop_name) as desktop:
                argv = _entry_argv("_probe", "--result", str(result_path))
                with desktop.launch(argv) as child:
                    child_exit = child.wait(timeout_seconds)
                    if child_exit is None:
                        child.terminate(124)
                        child_exit = child.wait(2.0)
                        raise HeadlessGuiError("hidden desktop probe timed out")
            probe = _load_json(result_path)
            child_name = _required_string(probe, "desktop_name")
            if child_name.casefold() != desktop_name.casefold():
                raise HeadlessGuiError(
                    f"child connected to unexpected desktop: {child_name!r} != {desktop_name!r}"
                )
            if child_exit != 0:
                raise HeadlessGuiError(f"hidden desktop probe exited with code {child_exit}")
        except (HeadlessGuiError, OSError, ValueError) as exc:
            error = str(exc)
    after = input_desktop_name()
    if error is None and before is not None and after is not None and before != after:
        error = f"input desktop changed unexpectedly: {before!r} -> {after!r}"
    return DesktopSmokeResult(
        ok=error is None,
        desktop_name=desktop_name,
        child_desktop_name=child_name,
        input_desktop_before=before,
        input_desktop_after=after,
        child_exit_code=child_exit,
        error=error,
    )


def _validated_request(request: RoundtripRequest) -> RoundtripRequest:
    try:
        installation = validate_diptrace_directory(request.diptrace_root)
    except ConfiguratorError as exc:
        raise HeadlessGuiError(str(exc)) from exc
    executable = installation.root / _EDITOR_EXECUTABLES[request.editor]
    if not executable.is_file():
        raise HeadlessGuiError(
            f"selected DipTrace editor is missing: {executable}. "
            "Choose the matching editor or installation root."
        )
    project = request.project.expanduser().resolve(strict=False)
    if not project.is_file():
        raise HeadlessGuiError(f"project file does not exist: {project}")
    return RoundtripRequest(
        diptrace_root=installation.root,
        project=project,
        editor=request.editor,
        timeout_seconds=request.timeout_seconds,
        save_menu=request.save_menu,
    )


def run_native_roundtrip(request: RoundtripRequest) -> RoundtripResult:
    if os.name != "nt":
        raise HeadlessGuiError("native headless round-trip is available only on Windows")
    request = _validated_request(request)
    desktop_name = f"DipTraceMCP-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    before = input_desktop_name()
    with tempfile.TemporaryDirectory(prefix="diptrace-headless-") as raw_temp:
        temp = Path(raw_temp)
        request_path = temp / "request.json"
        result_path = temp / "result.json"
        _write_json(request_path, request.as_json())
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
            raise HeadlessGuiError(f"headless worker exited with code {exit_code} without a result")
        result = RoundtripResult.from_json(_load_json(result_path))
    after = input_desktop_name()
    if before is not None and after is not None and before != after:
        raise HeadlessGuiError(f"input desktop changed unexpectedly: {before!r} -> {after!r}")
    if result.input_desktop_before != before or result.input_desktop_after != after:
        result = replace(
            result,
            input_desktop_before=before,
            input_desktop_after=after,
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
    try:
        windows = app.windows()
    except Exception:
        return titles
    for window in windows:
        try:
            title = str(window.window_text()).strip()
        except Exception:
            continue
        if title:
            titles.append(title)
    return titles


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
    diptrace_pid: int | None = None
    forced = False
    error: str | None = None
    try:
        command_line = subprocess.list2cmdline([str(request.executable), str(request.project)])
        app = application_class(backend="win32").start(
            command_line,
            timeout=request.timeout_seconds,
        )
        diptrace_pid = int(app.process)
        window = app.top_window()
        window.wait("exists visible enabled ready", timeout=request.timeout_seconds)
        window.menu_select(request.save_menu)
        time.sleep(0.8)
        window.close()
        try:
            app.wait_for_process_exit(timeout=min(10.0, request.timeout_seconds))
        except Exception:
            forced = True
            app.kill(soft=False)
    except Exception as exc:
        titles = _window_titles(app) if app is not None else []
        suffix = f"; open windows: {titles!r}" if titles else ""
        error = f"{type(exc).__name__}: {exc}{suffix}"
        if app is not None:
            try:
                forced = True
                app.kill(soft=False)
            except Exception:
                pass
    after = input_desktop_name()
    sha_after = _sha256(request.project)
    if before is not None and after is not None and before != after:
        error = error or f"input desktop changed unexpectedly: {before!r} -> {after!r}"
    return RoundtripResult(
        ok=error is None,
        editor=request.editor,
        executable=str(request.executable),
        project=str(request.project),
        worker_pid=os.getpid(),
        diptrace_pid=diptrace_pid,
        automation_backend="pywinauto-win32-message",
        desktop_name=desktop_name,
        input_desktop_before=before,
        input_desktop_after=after,
        sha256_before=sha_before,
        sha256_after=sha_after,
        forced_termination=forced,
        error=error,
    )


def _cmd_probe(args: argparse.Namespace) -> int:
    result_path = Path(str(args.result))
    try:
        value: dict[str, object] = {
            "desktop_name": thread_desktop_name(),
            "pid": os.getpid(),
        }
        _write_json(result_path, value)
        return 0
    except (HeadlessGuiError, OSError, ValueError) as exc:
        _write_json(result_path, {"error": str(exc), "pid": os.getpid()})
        return 1


def _cmd_worker(args: argparse.Namespace) -> int:
    request_path = Path(str(args.request))
    result_path = Path(str(args.result))
    desktop_name = str(args.desktop_name)
    try:
        request = RoundtripRequest.from_json(_load_json(request_path))
        actual_desktop = thread_desktop_name()
        if actual_desktop.casefold() != desktop_name.casefold():
            raise HeadlessGuiError(
                f"worker connected to unexpected desktop: {actual_desktop!r} != {desktop_name!r}"
            )
        result = _perform_worker_roundtrip(request, desktop_name=desktop_name)
    except Exception as exc:
        result = RoundtripResult(
            ok=False,
            editor="unknown",
            executable="",
            project="",
            worker_pid=os.getpid(),
            diptrace_pid=None,
            automation_backend="pywinauto-win32-message",
            desktop_name=desktop_name,
            input_desktop_before=input_desktop_name() if os.name == "nt" else None,
            input_desktop_after=input_desktop_name() if os.name == "nt" else None,
            sha256_before=None,
            sha256_after=None,
            error=f"{type(exc).__name__}: {exc}",
        )
    _write_json(result_path, result.as_json())
    return 0 if result.ok else 1


def _cmd_smoke(args: argparse.Namespace) -> int:
    result = desktop_smoke_test(timeout_seconds=float(args.timeout))
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
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _cmd_roundtrip(args: argparse.Namespace) -> int:
    request = RoundtripRequest(
        diptrace_root=Path(str(args.diptrace_root)),
        project=Path(str(args.project)),
        editor=str(args.editor),
        timeout_seconds=float(args.timeout),
        save_menu=str(args.save_menu),
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
        description="Run bounded DipTrace native GUI operations on an isolated Win32 desktop.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke", help="verify hidden desktop process isolation")
    smoke.add_argument("--timeout", type=float, default=15.0)
    smoke.set_defaults(handler=_cmd_smoke)

    doctor = subparsers.add_parser(
        "doctor",
        help="check Windows, DipTrace and automation readiness",
    )
    doctor.add_argument("--diptrace-root")
    doctor.add_argument("--timeout", type=float, default=15.0)
    doctor.add_argument("--require-automation", action="store_true")
    doctor.set_defaults(handler=_cmd_doctor)

    roundtrip = subparsers.add_parser("roundtrip", help="open, native-save and close a project")
    roundtrip.add_argument("--diptrace-root", required=True)
    roundtrip.add_argument("--project", required=True)
    roundtrip.add_argument("--editor", choices=sorted(_EDITOR_EXECUTABLES), required=True)
    roundtrip.add_argument("--timeout", type=float, default=30.0)
    roundtrip.add_argument("--save-menu", default="File->Save")
    roundtrip.set_defaults(handler=_cmd_roundtrip)

    worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--request", required=True)
    worker.add_argument("--result", required=True)
    worker.add_argument("--desktop-name", required=True)
    worker.set_defaults(handler=_cmd_worker)

    probe = subparsers.add_parser("_probe", help=argparse.SUPPRESS)
    probe.add_argument("--result", required=True)
    probe.set_defaults(handler=_cmd_probe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
