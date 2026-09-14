from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from diptrace_mcp import headless_gui as hg
from diptrace_mcp import native_xml_export as nxe
from diptrace_mcp import pcb_native_acceptance as pna
from diptrace_mcp import schematic_native_acceptance as sna
from diptrace_mcp import sessions
from diptrace_mcp.xml_document import sha256_bytes


class _Call:
    def __init__(self, result: Any = 1, handler: Any = None) -> None:
        self.result = result
        self.handler = handler
        self.argtypes: Any = None
        self.restype: Any = None
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> Any:
        self.calls.append(args)
        return self.handler(*args) if self.handler is not None else self.result


class _Dll:
    def __init__(self) -> None:
        self.calls: dict[str, _Call] = {}

    def __getattr__(self, name: str) -> _Call:
        return self.calls.setdefault(name, _Call())


def test_win32_api_configures_all_boundaries_and_formats_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    libraries = {name: _Dll() for name in ("user32", "kernel32", "shell32")}
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        hg.ctypes,
        "WinDLL",
        lambda name, **_kwargs: libraries[name],
        raising=False,
    )
    api = hg._Win32Api()

    assert api.user32.CreateDesktopW.argtypes
    assert api.kernel32.CreateProcessW.argtypes
    assert api.shell32.IsUserAnAdmin.restype is not None

    monkeypatch.setattr(hg.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(hg.ctypes, "FormatError", lambda code: f" error {code} ", raising=False)
    assert "error 5" in str(api.error("CreateDesktopW"))
    monkeypatch.setattr(hg.ctypes, "get_last_error", lambda: 0, raising=False)
    assert "unknown Windows error" in str(api.error("CreateDesktopW"))


def test_win32_api_rejects_missing_platform_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="posix"))
    with pytest.raises(hg.HeadlessGuiError, match="only on Windows"):
        hg._Win32Api()

    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt"))
    monkeypatch.delattr(hg.ctypes, "WinDLL", raising=False)
    with pytest.raises(hg.HeadlessGuiError, match="bindings are unavailable"):
        hg._Win32Api()


def test_desktop_identity_queries_and_interactive_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"size": True, "read": True}

    def user_object(_handle, _index, buffer, _size, required) -> int:
        required._obj.value = 32 if state["size"] else 0
        if buffer is not None:
            buffer.value = "Default"
            return int(state["read"])
        return 1

    def session_id(_pid, result) -> int:
        result._obj.value = 7
        return 1

    user32 = SimpleNamespace(
        GetUserObjectInformationW=user_object,
        GetProcessWindowStation=lambda: 12,
    )
    kernel32 = SimpleNamespace(
        GetCurrentProcessId=lambda: 99,
        ProcessIdToSessionId=session_id,
    )
    api = SimpleNamespace(
        user32=user32,
        kernel32=kernel32,
        shell32=SimpleNamespace(IsUserAnAdmin=lambda: 1),
        error=lambda operation: hg.HeadlessGuiError(operation),
    )
    monkeypatch.setattr(hg, "_Win32Api", lambda: api)

    assert hg._desktop_object_name(12) == "Default"
    assert hg.process_window_station_name() == "Default"
    assert hg.process_session_id() == 7
    assert hg.process_session_id(123) == 7
    assert hg.process_is_elevated()

    state["size"] = False
    with pytest.raises(hg.HeadlessGuiError, match="size"):
        hg._desktop_object_name(12)
    state.update(size=True, read=False)
    with pytest.raises(hg.HeadlessGuiError, match="GetUserObjectInformationW"):
        hg._desktop_object_name(12)

    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 7)
    assert hg._interactive_context() == ("Default", "WinSta0", 7)
    monkeypatch.setattr(hg, "input_desktop_name", lambda: None)
    with pytest.raises(hg.HeadlessGuiError, match="input desktop"):
        hg._interactive_context()
    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "Other")
    with pytest.raises(hg.HeadlessGuiError, match="WinSta0"):
        hg._interactive_context()


def test_launch_on_current_desktop_checks_elevation_and_child_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Child:
        pid = 22

        def __init__(self) -> None:
            self.terminated: list[int] = []
            self.closed = False

        def terminate(self, code: int) -> None:
            self.terminated.append(code)

        def close(self) -> None:
            self.closed = True

    child = Child()
    monkeypatch.setattr(hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(hg, "_interactive_context", lambda: ("Default", "WinSta0", 7))
    monkeypatch.setattr(hg, "_launch_process_on_desktop", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 7)
    assert hg._launch_on_current_desktop(["worker"]) is child

    monkeypatch.setattr(hg, "process_is_elevated", lambda: True)
    with pytest.raises(hg.HeadlessGuiError, match="elevated"):
        hg._launch_on_current_desktop(["worker"])

    monkeypatch.setattr(hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 8)
    with pytest.raises(hg.HeadlessGuiError, match="session mismatch"):
        hg._launch_on_current_desktop(["worker"])
    assert child.terminated == [126] and child.closed


class _ProbeChild:
    def __init__(
        self, argv: list[str], payload: dict[str, object], waits: list[int | None]
    ) -> None:
        self.result_path = Path(argv[argv.index("--result") + 1])
        self.payload = payload
        self.waits = iter(waits)
        self.terminated: list[int] = []

    def __enter__(self) -> _ProbeChild:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def wait(self, _timeout: float) -> int | None:
        result = next(self.waits)
        if result is not None and not self.result_path.exists():
            self.result_path.write_text(json.dumps(self.payload), encoding="utf-8")
        return result

    def terminate(self, code: int) -> None:
        self.terminated.append(code)


def test_hidden_desktop_smoke_success_timeout_and_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    mode = {"kind": "success"}

    class Desktop:
        def __init__(self, name: str) -> None:
            self.name = name

        def __enter__(self) -> Desktop:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def launch(self, argv: list[str]) -> _ProbeChild:
            payload = {"desktop_name": self.name if mode["kind"] != "mismatch" else "Other"}
            waits = [None, 124] if mode["kind"] == "timeout" else [0]
            return _ProbeChild(argv, payload, waits)

    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt", getpid=os.getpid, replace=os.replace))
    monkeypatch.setattr(hg, "HiddenDesktop", Desktop)
    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    assert hg.desktop_smoke_test(timeout_seconds=1).ok

    mode["kind"] = "mismatch"
    assert "unexpected desktop" in (hg.desktop_smoke_test(timeout_seconds=1).error or "")
    mode["kind"] = "timeout"
    assert "timed out" in (hg.desktop_smoke_test(timeout_seconds=1).error or "")

    mode["kind"] = "success"
    desktops = iter(("Before", "After"))
    monkeypatch.setattr(hg, "input_desktop_name", lambda: next(desktops))
    assert "changed unexpectedly" in (hg.desktop_smoke_test(timeout_seconds=1).error or "")


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"desktop_name": "Default", "window_station_name": "WinSta0", "session_id": 7}, None),
        ({"desktop_name": "Other", "window_station_name": "WinSta0", "session_id": 7}, "desktop"),
        ({"desktop_name": "Default", "window_station_name": "Other", "session_id": 7}, "station"),
        ({"desktop_name": "Default", "window_station_name": "WinSta0", "session_id": 8}, "session"),
    ],
)
def test_native_desktop_smoke_validates_child_identity(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    error: str | None,
) -> None:
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(hg, "_interactive_context", lambda: ("Default", "WinSta0", 7))
    monkeypatch.setattr(
        hg,
        "_launch_on_current_desktop",
        lambda argv, **_kwargs: _ProbeChild(list(argv), payload, [0]),
    )
    result = hg.native_desktop_smoke_test(timeout_seconds=1)
    assert result.ok is (error is None)
    if error is not None:
        assert error in (result.error or "")


def test_native_desktop_smoke_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"desktop_name": "Default", "window_station_name": "WinSta0", "session_id": 7}
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(hg, "_interactive_context", lambda: ("Default", "WinSta0", 7))
    monkeypatch.setattr(
        hg,
        "_launch_on_current_desktop",
        lambda argv, **_kwargs: _ProbeChild(list(argv), payload, [None, 124]),
    )
    assert "timed out" in (hg.native_desktop_smoke_test(timeout_seconds=1).error or "")


def test_save_dialog_control_discovery_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def class_name(hwnd: int, buffer: Any, _size: int) -> int:
        buffer.value = "Edit" if hwnd == 11 else "ComboBox"
        return len(buffer.value)

    user32 = SimpleNamespace(
        GetClassNameW=class_name,
        GetDlgCtrlID=lambda hwnd: hg._SAVE_FILE_NAME_ID if hwnd == 11 else hg._SAVE_FILE_TYPE_ID,
        EnumChildWindows=lambda _dialog, callback, _data: callback(11, 0) and callback(12, 0),
    )
    monkeypatch.setattr(hg, "_Win32Api", lambda: SimpleNamespace(user32=user32))
    monkeypatch.setattr(
        hg.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )
    assert hg._save_dialog_controls(10) == (11, 12)

    monkeypatch.delattr(hg.ctypes, "WINFUNCTYPE", raising=False)
    with pytest.raises(hg.HeadlessGuiError, match="callback bindings"):
        hg._save_dialog_controls(10)


def test_save_dialog_as_xml_reports_missing_format_and_post_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hg, "_save_dialog_controls", lambda _handle: (11, 12))
    api = SimpleNamespace(
        user32=SimpleNamespace(SendMessageW=lambda *_args: 0, PostMessageW=lambda *_args: 1),
        error=lambda operation: hg.HeadlessGuiError(operation),
    )
    monkeypatch.setattr(hg, "_Win32Api", lambda: api)
    with pytest.raises(hg.HeadlessGuiError, match="no XML"):
        hg._save_dialog_as_xml(10, tmp_path / "out.elixml")

    def message(_handle: int, code: int, _wparam: int, lparam: int) -> int:
        if code == hg._CB_GETCOUNT:
            return 1
        if code == hg._CB_GETLBTEXT:
            pointer = ctypes.cast(lparam, ctypes.POINTER(ctypes.c_wchar))
            for index, character in enumerate("XML library\0"):
                pointer[index] = character
        return 1

    api.user32.SendMessageW = message
    api.user32.PostMessageW = lambda *_args: 0
    with pytest.raises(hg.HeadlessGuiError, match="notification"):
        hg._save_dialog_as_xml(10, tmp_path / "out.elixml")


def _roundtrip_result(ok: bool = True) -> hg.RoundtripResult:
    return hg.RoundtripResult(
        ok,
        "pcb",
        "Pcb.exe",
        "board.dip",
        1,
        2,
        "pywinauto-win32-message",
        "Hidden",
        None,
        None,
        None,
        None,
    )


def test_worker_command_success_and_failure_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(
        json.dumps(
            {
                "diptrace_root": str(tmp_path),
                "project": str(tmp_path / "board.dip"),
                "editor": "pcb",
                "desktop_mode": "hidden",
                "_expected_window_station": "WinSta0",
                "_expected_session_id": 7,
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(request=request, result=result, desktop_name="Hidden")
    monkeypatch.setattr(hg, "thread_desktop_name", lambda: "Hidden")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 7)
    monkeypatch.setattr(
        hg, "_perform_worker_roundtrip", lambda *_args, **_kwargs: _roundtrip_result()
    )
    assert hg._cmd_worker(args) == 0
    assert json.loads(result.read_text(encoding="utf-8"))["session_id"] == 7

    request.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(
        hg,
        "os",
        SimpleNamespace(name="nt", getpid=os.getpid, replace=os.replace),
    )
    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    assert hg._cmd_worker(args) == 1
    failed = json.loads(result.read_text(encoding="utf-8"))
    assert failed["desktop_name"] == "Hidden" and "cannot read worker JSON" in failed["error"]


def test_doctor_builds_windows_report(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    smoke = hg.DesktopSmokeResult(True, "Hidden", "Hidden", "Default", "Default", 0)
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(hg, "desktop_smoke_test", lambda **_kwargs: smoke)
    monkeypatch.setattr(hg, "_resolve_diptrace_root", lambda _raw: Path("DipTrace"))
    monkeypatch.setattr(hg.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(
        hg,
        "validate_diptrace_directory",
        lambda root: SimpleNamespace(root=root),
    )
    args = argparse.Namespace(timeout=1, diptrace_root=None, require_automation=True)
    assert hg._cmd_doctor(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_windows_process_snapshot_classifies_kernel_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _Dll()
    errors = {"current": 0, "open": 87}
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel, raising=False)
    monkeypatch.setattr(
        ctypes, "set_last_error", lambda value: errors.update(current=value), raising=False
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: errors["current"], raising=False)

    kernel.OpenProcess = _Call(handler=lambda *_args: errors.update(current=errors["open"]) or 0)
    assert sessions._windows_process_snapshot(999) == ("dead", None)
    errors["open"] = 5
    assert sessions._windows_process_snapshot(999) == ("unknown", None)

    kernel.OpenProcess = _Call(10)

    def exit_code(_handle: int, pointer: Any) -> int:
        pointer._obj.value = 259
        return 1

    def process_times(
        _handle: int,
        creation: Any,
        _exit_time: Any,
        _kernel_time: Any,
        _user_time: Any,
    ) -> int:
        creation._obj.dwHighDateTime = 0x12
        creation._obj.dwLowDateTime = 0x34
        return 1

    kernel.GetExitCodeProcess = _Call(handler=exit_code)
    kernel.GetProcessTimes = _Call(handler=process_times)
    kernel.CloseHandle = _Call()
    assert sessions._windows_process_snapshot(10) == ("alive", "0000001200000034")
    assert kernel.CloseHandle.calls[-1] == (10,)

    kernel.GetExitCodeProcess = _Call(0)
    assert sessions._windows_process_snapshot(10) == ("unknown", None)
    kernel.GetExitCodeProcess = _Call(
        handler=lambda _handle, pointer: setattr(pointer._obj, "value", 1) or 1
    )
    assert sessions._windows_process_snapshot(10) == ("dead", None)
    kernel.GetExitCodeProcess = _Call(handler=exit_code)
    kernel.GetProcessTimes = _Call(0)
    assert sessions._windows_process_snapshot(10) == ("unknown", None)

    monkeypatch.setattr(ctypes, "WinDLL", None, raising=False)
    assert sessions._windows_process_snapshot(10) == ("unknown", None)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
        raising=False,
    )
    assert sessions._windows_process_snapshot(10) == ("unknown", None)


def test_windows_liveness_and_wsl_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions, "_windows_process_snapshot", lambda _pid: ("alive", "token"))
    assert sessions._windows_process_liveness(1, "token") == "alive"

    monkeypatch.delenv("WSL_INTEROP", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    assert sessions._is_wsl_runtime("darwin") is False
    monkeypatch.setenv("WSL_INTEROP", "1")
    assert sessions._is_wsl_runtime("linux") is True
    monkeypatch.delenv("WSL_INTEROP")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "Linux microsoft-standard")
    assert sessions._is_wsl_runtime("linux") is True
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert sessions._is_wsl_runtime("linux") is False


@pytest.mark.parametrize("payload", [b"{", b"[]"])
def test_finish_request_reader_fails_closed_on_malformed_json(
    tmp_path: Path,
    payload: bytes,
) -> None:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes((Path(__file__).parent / "fixtures" / "pcb.xml").read_bytes())
    store = sessions.SessionStore(tmp_path / "state", 10_000_000, allowed_roots=(tmp_path,))
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])
    working = store.working_path(session_id)
    store.request_finish("apply", sha256_bytes(working.read_bytes()))
    store.control_path(session_id).write_bytes(payload)

    request = store.read_finish_request(session_id)

    assert "_parse_error" in request
    assert len(request["_control_sha256"]) == 64


def test_schematic_acceptance_host_pipeline_without_native_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "board.dchxml"
    source.write_bytes((Path(__file__).parent / "fixtures" / "schematic.xml").read_bytes())
    source_sha = hg._sha256(source)
    assert source_sha is not None
    root = tmp_path / "DipTrace"
    root.mkdir()
    (root / "Schematic.exe").write_bytes(b"exe")
    output = tmp_path / "evidence"
    calls: list[str] = []

    class Job:
        @classmethod
        def create(cls) -> Job:
            return cls()

        def terminate_and_close(self) -> None:
            calls.append("job-close")

    class Child:
        def __init__(self, argv: list[str]) -> None:
            self.folder = Path(argv[-1])

        def __enter__(self) -> Child:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def wait(self, _timeout: float) -> int:
            (self.folder / "worker-result.json").write_text(
                json.dumps({"completed": True}), encoding="utf-8"
            )
            return 0

    class Desktop:
        def __init__(self, _name: str) -> None:
            pass

        def __enter__(self) -> Desktop:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def launch(self, argv: list[str], **_kwargs: object) -> Child:
            return Child(argv)

    real_sha = hg._sha256
    monkeypatch.setattr(sna, "os", SimpleNamespace(name="nt", getpid=os.getpid))
    monkeypatch.setattr(sna.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(
        sna.hg,
        "_sha256",
        lambda path: sna._EXE_SHA if Path(path).name == "Schematic.exe" else real_sha(Path(path)),
    )
    monkeypatch.setattr(sna.hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(sna.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(sna.hg, "process_session_id", lambda: 7)
    monkeypatch.setattr(sna.hg, "HiddenDesktop", Desktop)
    monkeypatch.setattr(sna, "KillOnCloseJob", Job)
    args = argparse.Namespace(
        project=str(source),
        output_dir=str(output),
        expected_sha256=source_sha,
        timeout=30.0,
        diptrace_root=str(root),
        inspect=False,
        capture=False,
        erc=False,
        startup_dialog_sha256=None,
    )

    report = sna.run(args)

    assert report["completed"] is True
    assert report["mode"] == "export"
    assert (output / "result.json").is_file()
    assert calls == ["job-close"]


@pytest.mark.parametrize("desktop_mode", ["hidden", "native"])
def test_pcb_acceptance_host_pipeline_without_native_gui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    desktop_mode: str,
) -> None:
    request = pna.PcbNativeAcceptanceRequest(
        diptrace_root=tmp_path,
        project=tmp_path / "board.dip",
        output_xml=tmp_path / "roundtrip.dipxml",
        desktop_mode=desktop_mode,
    )
    worker_payload = pna.NativePcbWorkerEvidence(
        completed=True,
        project=str(request.project),
        output_xml=str(request.output_xml),
        project_sha256_before="a" * 64,
        project_sha256_after="a" * 64,
        output_xml_sha256="b" * 64,
        drc_status="pass",
        worker_pid=1,
        diptrace_pids=[2],
        desktop_mode=desktop_mode,
        desktop_name="Default",
        window_station_name="WinSta0",
        session_id=7,
    )

    class Child:
        def __init__(self, argv: list[str]) -> None:
            self.argv = argv

        def __enter__(self) -> Child:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def wait(self, _timeout: float) -> int:
            result = Path(self.argv[self.argv.index("--result") + 1])
            result.write_text(worker_payload.model_dump_json(), encoding="utf-8")
            return 0

    class Desktop:
        def __init__(self, _name: str) -> None:
            pass

        def __enter__(self) -> Desktop:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def launch(self, argv: list[str]) -> Child:
            return Child(argv)

    monkeypatch.setattr(pna, "os", SimpleNamespace(name="nt", getpid=os.getpid))
    monkeypatch.setattr(pna, "_validate_request", lambda value: value)
    monkeypatch.setattr(pna, "process_is_elevated", lambda: False)
    monkeypatch.setattr(pna, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(pna, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(pna, "process_session_id", lambda: 7)
    monkeypatch.setattr(pna, "_interactive_context", lambda: ("Default", "WinSta0", 7))
    monkeypatch.setattr(pna, "_immutable_baseline", lambda *_args: None)
    monkeypatch.setattr(pna, "HiddenDesktop", Desktop)
    monkeypatch.setattr(pna, "_launch_on_current_desktop", lambda argv: Child(argv))
    monkeypatch.setattr(pna, "_finalize_result", lambda *_args, **_kwargs: "finalized")

    assert pna.run_pcb_native_acceptance(request) == "finalized"


def test_headless_remaining_validation_and_menu_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="save_menu"):
        hg.RoundtripRequest(tmp_path, tmp_path / "x.dip", "pcb", save_menu=" ")
    with pytest.raises(ValueError, match="window station"):
        hg._launch_process_on_desktop(["worker"], "Default")

    api = SimpleNamespace(
        user32=SimpleNamespace(
            GetProcessWindowStation=lambda: 0,
            PostMessageW=lambda *_args: 0,
            SendMessageW=lambda *_args: 7,
        ),
        kernel32=SimpleNamespace(
            GetCurrentProcessId=lambda: 1,
            ProcessIdToSessionId=lambda *_args: 0,
        ),
        error=lambda operation: hg.HeadlessGuiError(operation),
    )
    monkeypatch.setattr(hg, "_Win32Api", lambda: api)
    with pytest.raises(hg.HeadlessGuiError, match="GetProcessWindowStation"):
        hg.process_window_station_name()
    with pytest.raises(hg.HeadlessGuiError, match="ProcessIdToSessionId"):
        hg.process_session_id()
    with pytest.raises(hg.HeadlessGuiError, match="PostMessageW"):
        hg._post_window_message(1, 2)
    assert hg._send_window_message(1, 2) == 7

    assert hg._confirm_shift_origin(SimpleNamespace(window_text=lambda: "Other")) is False
    vanished = SimpleNamespace(
        window_text=lambda: "Shift Origin",
        children=lambda: (_ for _ in ()).throw(RuntimeError("gone")),
        handle=1,
    )
    api.user32.IsWindow = lambda _handle: 0
    assert hg._confirm_shift_origin(vanished) is True
    api.user32.IsWindow = lambda _handle: 1
    with pytest.raises(RuntimeError, match="gone"):
        hg._confirm_shift_origin(vanished)
    with pytest.raises(hg.HeadlessGuiError, match="unique enabled"):
        hg._confirm_shift_origin(
            SimpleNamespace(window_text=lambda: "Shift Origin", children=lambda: [], handle=1)
        )

    window = SimpleNamespace(handle=1)
    disabled = SimpleNamespace(is_enabled=lambda: False)
    with pytest.raises(hg.HeadlessGuiError, match="disabled"):
        hg._post_menu_item(window, disabled)
    bad_id = SimpleNamespace(
        is_enabled=lambda: True,
        menu=SimpleNamespace(COMMAND=hg._WM_COMMAND),
        item_id=lambda: 0,
    )
    with pytest.raises(hg.HeadlessGuiError, match="command ID"):
        hg._post_menu_item(window, bad_id)
    bad_position = SimpleNamespace(
        is_enabled=lambda: True,
        menu=SimpleNamespace(COMMAND=hg._WM_MENUCOMMAND, handle=0),
        index=lambda: -1,
    )
    with pytest.raises(hg.HeadlessGuiError, match="position"):
        hg._post_menu_item(window, bad_position)
    unsupported = SimpleNamespace(
        is_enabled=lambda: True,
        menu=SimpleNamespace(COMMAND=999),
    )
    with pytest.raises(hg.HeadlessGuiError, match="unsupported"):
        hg._post_menu_item(window, unsupported)

    with pytest.raises(hg.HeadlessGuiError, match="no native menu"):
        hg._save_window(SimpleNamespace(menu=lambda: None), "File->Save")
    bad_menu = SimpleNamespace(
        menu=lambda: object(),
        menu_item=lambda _path: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    with pytest.raises(hg.HeadlessGuiError, match="was not found"):
        hg._save_window(bad_menu, "File->Other")

    api.user32.EnumChildWindows = lambda *_args: 1
    monkeypatch.setattr(
        hg.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )
    with pytest.raises(hg.HeadlessGuiError, match="controls were not found"):
        hg._save_dialog_controls(1)


def test_library_export_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="posix"))
    with pytest.raises(hg.HeadlessGuiError, match="only on Windows"):
        hg.export_component_library_xml(tmp_path, tmp_path / "x.eli", tmp_path / "x.elixml")
    with pytest.raises(hg.HeadlessGuiError, match="only on Windows"):
        hg.run_native_roundtrip(hg.RoundtripRequest(tmp_path, tmp_path / "x.dip", "pcb"))

    root = tmp_path / "DipTrace"
    root.mkdir()
    monkeypatch.setattr(
        hg,
        "validate_diptrace_directory",
        lambda _root: (_ for _ in ()).throw(hg.ConfiguratorError("bad install")),
    )
    with pytest.raises(hg.HeadlessGuiError, match="bad install"):
        hg._validated_library_export(root, tmp_path / "x.eli", tmp_path / "x.elixml")
    monkeypatch.setattr(
        hg,
        "validate_diptrace_directory",
        lambda _root: SimpleNamespace(root=root),
    )
    with pytest.raises(hg.HeadlessGuiError, match="Component Editor is missing"):
        hg._validated_library_export(root, tmp_path / "x.eli", tmp_path / "x.elixml")
    (root / "CompEdit.exe").write_bytes(b"exe")
    (root / "Lib").mkdir()
    source = root / "Lib" / "x.eli"
    source.write_bytes(b"library")
    target = tmp_path / "x.elixml"
    target.write_bytes(b"exists")
    with pytest.raises(hg.HeadlessGuiError, match="already exists"):
        hg._validated_library_export(root, source, target)


@pytest.mark.parametrize("desktop_mode", ["hidden", "native"])
def test_native_roundtrip_timeout_and_identity_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    desktop_mode: str,
) -> None:
    request = hg.RoundtripRequest(
        tmp_path,
        tmp_path / "board.dip",
        "pcb",
        timeout_seconds=1,
        desktop_mode=desktop_mode,
    )
    child: _ProbeChild | None = None

    class Desktop:
        def __init__(self, _name: str) -> None:
            pass

        def __enter__(self) -> Desktop:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def launch(self, argv: list[str]) -> _ProbeChild:
            nonlocal child
            child = _ProbeChild(argv, {}, [None, 124])
            return child

    def launch(argv: list[str]) -> _ProbeChild:
        nonlocal child
        child = _ProbeChild(argv, {}, [None, 124])
        return child

    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt", getpid=os.getpid, replace=os.replace))
    monkeypatch.setattr(hg, "_validated_request", lambda value: value)
    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(hg, "process_session_id", lambda: 7)
    monkeypatch.setattr(hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(hg, "_validate_desktop_name", lambda _name: None)
    monkeypatch.setattr(hg, "HiddenDesktop", Desktop)
    monkeypatch.setattr(hg, "_launch_on_current_desktop", launch)
    with pytest.raises(hg.HeadlessGuiError, match="timed out"):
        hg.run_native_roundtrip(request)
    assert child is not None and child.terminated == [124]


def test_worker_rejects_identity_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    payload = {
        "diptrace_root": str(tmp_path),
        "project": str(tmp_path / "board.dip"),
        "editor": "pcb",
        "desktop_mode": "native",
        "_expected_window_station": "WinSta0",
        "_expected_session_id": 7,
    }
    request.write_text(json.dumps(payload), encoding="utf-8")
    args = argparse.Namespace(request=request, result=result, desktop_name="Default")
    monkeypatch.setattr(hg, "os", SimpleNamespace(name="nt", getpid=os.getpid, replace=os.replace))
    monkeypatch.setattr(hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(hg, "thread_desktop_name", lambda: "Other")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 7)
    monkeypatch.setattr(hg, "process_is_elevated", lambda: False)
    assert hg._cmd_worker(args) == 1
    assert "unexpected desktop" in json.loads(result.read_text())["error"]

    monkeypatch.setattr(hg, "thread_desktop_name", lambda: "Default")
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "Other")
    assert hg._cmd_worker(args) == 1
    assert "window station" in json.loads(result.read_text())["error"]
    monkeypatch.setattr(hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 8)
    assert hg._cmd_worker(args) == 1
    assert "session" in json.loads(result.read_text())["error"]
    monkeypatch.setattr(hg, "process_session_id", lambda _pid=None: 7)
    monkeypatch.setattr(hg, "process_is_elevated", lambda: True)
    assert hg._cmd_worker(args) == 1
    assert "elevated" in json.loads(result.read_text())["error"]


def test_pcb_acceptance_summary_menu_and_dialog_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schematic = tmp_path / "schematic.xml"
    schematic.write_bytes((Path(__file__).parent / "fixtures" / "schematic.xml").read_bytes())
    with pytest.raises(ValueError, match="expected DipTrace PCB"):
        pna.summarize_pcb_xml(schematic)

    window = SimpleNamespace(
        menu=lambda: object(),
        menu_item=lambda _path: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    with pytest.raises(hg.HeadlessGuiError, match="was not found"):
        pna._post_menu_path(window, "Route->Check")

    posted: list[int] = []
    dialog = SimpleNamespace(
        handle=7,
        descendants=lambda: [],
        is_visible=lambda: (_ for _ in ()).throw(RuntimeError("gone")),
    )
    monkeypatch.setattr(pna, "_post_window_message", lambda handle, *_args: posted.append(handle))
    pna._dismiss_dialog(dialog, 1)
    assert posted == [7]

    monkeypatch.setattr(pna.time, "monotonic", lambda: 2.0)
    visible = SimpleNamespace(handle=8, descendants=lambda: [], is_visible=lambda: True)
    with pytest.raises(hg.HeadlessGuiError, match="did not close"):
        pna._dismiss_dialog(visible, 0)


def test_native_xml_export_copy_and_hidden_worker_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "board.dip"
    project.write_bytes(b"native")
    output = tmp_path / "board.dipxml"
    monkeypatch.setattr(nxe, "_MAX_BYTES", 1)
    with pytest.raises(ValueError, match="size limit"):
        nxe.export_native_xml(tmp_path, project, output)

    monkeypatch.setattr(nxe, "_MAX_BYTES", 1_000)
    hashes = iter(("a", "b"))
    monkeypatch.setattr(nxe.hg, "_sha256", lambda _path: next(hashes))
    with pytest.raises(RuntimeError, match="changed while copying"):
        nxe.export_native_xml(tmp_path, project, output)

    monkeypatch.setattr(nxe, "os", SimpleNamespace(name="posix"))
    with pytest.raises(hg.HeadlessGuiError, match="requires Windows"):
        nxe._run_hidden(tmp_path, project, output, 1)


def test_native_xml_hidden_result_identity_and_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "board.dip"
    source.write_bytes(b"native")
    output = tmp_path / "board.dipxml"
    monkeypatch.setattr(nxe, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(nxe, "validate_diptrace_directory", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr(nxe.hg, "process_is_elevated", lambda: False)
    desktops = iter(("Default", "Default"))
    monkeypatch.setattr(nxe.hg, "input_desktop_name", lambda: next(desktops))
    monkeypatch.setattr(nxe.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(nxe.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(nxe.hg, "_write_json", lambda *_args: None)
    monkeypatch.setattr(nxe.hg, "_load_json", lambda _path: {"ok": True})

    class Worker:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def wait(self, _timeout):
            return 3

    class Desktop:
        def __init__(self, _name):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def launch(self, _argv, *, job):
            return Worker()

    monkeypatch.setattr(nxe.hg, "HiddenDesktop", Desktop)
    monkeypatch.setattr(
        nxe.KillOnCloseJob,
        "create",
        lambda: SimpleNamespace(terminate_and_close=lambda: None),
    )
    result = nxe._run_hidden(tmp_path, source, output, 1)
    assert result["ok"] is False and result["desktop_changed"] is False
