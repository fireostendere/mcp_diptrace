from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from diptrace_mcp import cinematic_preflight, cinematic_preflight_cli, headless_gui
from diptrace_mcp.cinematic_preflight import CinematicSafetyBudget
from diptrace_mcp.headless_gui import (
    DesktopSmokeResult,
    HeadlessGuiError,
    RoundtripRequest,
    RoundtripResult,
)


def _minimal_manifest(*, desktop: object | None = None) -> dict[str, object]:
    payload: dict[str, object] = {}
    if desktop is not None:
        payload["desktop"] = desktop
    return {
        "format": "diptrace-cinematic-v1",
        "cue_count": 1,
        "duration_ms": 10,
        "cues": [
            {
                "index": 0,
                "start_ms": 0,
                "end_ms": 5,
                "settle_until_ms": 10,
                "event": {"payload": payload},
            }
        ],
    }


def test_cinematic_preflight_helper_validation_and_warning() -> None:
    assert cinematic_preflight._desktop_steps({}) == []
    desktop = {"desktop": {"text": "x"}}
    assert cinematic_preflight._desktop_steps(desktop) == [{"text": "x"}]
    with pytest.raises(ValueError, match="desktop payload"):
        cinematic_preflight._desktop_steps({"desktop": "bad"})
    for steps in ("bad", [], ["bad"]):
        with pytest.raises(ValueError):
            cinematic_preflight._desktop_steps({"desktop": {"steps": steps}})

    with pytest.raises(ValueError, match="no cues array"):
        cinematic_preflight._validated_cues({})
    with pytest.raises(ValueError, match="invalid cue"):
        cinematic_preflight._validated_cues({"cues": [None]})
    with pytest.raises(ValueError, match="no event object"):
        cinematic_preflight._validated_cues({"cues": [{}]})

    result = cinematic_preflight.preflight_cinematic_manifest(_minimal_manifest())
    assert result.desktop_command_count == 0
    assert result.warnings and "no desktop commands" in result.warnings[0]


def test_cinematic_preflight_rejects_manifest_shape_and_timing_edges() -> None:
    base = _minimal_manifest()

    bad = dict(base, format="other")
    with pytest.raises(ValueError, match="format"):
        cinematic_preflight.preflight_cinematic_manifest(bad)

    with pytest.raises(ValueError, match="cue count exceeds"):
        cinematic_preflight.preflight_cinematic_manifest(
            base, CinematicSafetyBudget(max_cues=1)
        ) if False else cinematic_preflight.preflight_cinematic_manifest(
            {**base, "cues": [base["cues"][0], base["cues"][0]], "cue_count": 2},
            CinematicSafetyBudget(max_cues=1),
        )

    with pytest.raises(ValueError, match="cue_count"):
        cinematic_preflight.preflight_cinematic_manifest({**base, "cue_count": 2})

    cue = dict(base["cues"][0])  # type: ignore[index]
    with pytest.raises(ValueError, match="index mismatch"):
        cinematic_preflight.preflight_cinematic_manifest(
            {**base, "cues": [{**cue, "index": 1}]}
        )
    with pytest.raises(ValueError, match="negative timing"):
        cinematic_preflight.preflight_cinematic_manifest(
            {**base, "cues": [{**cue, "start_ms": -1}]}
        )
    with pytest.raises(ValueError, match="overlapping or invalid timing"):
        cinematic_preflight.preflight_cinematic_manifest(
            {**base, "cues": [{**cue, "start_ms": 6, "end_ms": 5}]}
        )
    with pytest.raises(ValueError, match="settle gap exceeds"):
        cinematic_preflight.preflight_cinematic_manifest(
            {**base, "duration_ms": 100, "cues": [{**cue, "settle_until_ms": 100}]},
            CinematicSafetyBudget(max_settle_gap_ms=5),
        )


def test_cinematic_preflight_rejects_desktop_payload_edges() -> None:
    with pytest.raises(ValueError, match="payload must be an object"):
        manifest = _minimal_manifest()
        cue = manifest["cues"][0]  # type: ignore[index]
        cue["event"] = {"payload": "bad"}  # type: ignore[index]
        cinematic_preflight.preflight_cinematic_manifest(manifest)

    cases = [
        ({"path": "bad"}, "path must be an array"),
        ({"text": 7}, "text must be a string"),
        ({"hotkey": "ctrl+a"}, "hotkey must be an array"),
    ]
    for step, message in cases:
        with pytest.raises(ValueError, match=message):
            cinematic_preflight.preflight_cinematic_manifest(
                _minimal_manifest(desktop={"steps": [step]})
            )

    with pytest.raises(ValueError, match="hotkey exceeds"):
        cinematic_preflight.preflight_cinematic_manifest(
            _minimal_manifest(desktop={"steps": [{"hotkey": ["x", "y"]}]}),
            CinematicSafetyBudget(max_hotkey_keys=1),
        )

    with pytest.raises(ValueError, match="path-point count"):
        cinematic_preflight.preflight_cinematic_manifest(
            _minimal_manifest(desktop={"steps": [{"path": [[0, 0], [1, 1]]}]}),
            CinematicSafetyBudget(max_path_points=1),
        )
    with pytest.raises(ValueError, match="typed-text count"):
        cinematic_preflight.preflight_cinematic_manifest(
            _minimal_manifest(desktop={"steps": [{"text": "xx"}]}),
            CinematicSafetyBudget(max_text_characters=1),
        )
    with pytest.raises(ValueError, match="desktop command count"):
        cinematic_preflight.preflight_cinematic_manifest(
            _minimal_manifest(desktop={"steps": [{}, {}]}),
            CinematicSafetyBudget(max_desktop_commands=1),
        )
    with pytest.raises(ValueError, match="duration exceeds"):
        cinematic_preflight.preflight_cinematic_manifest(
            _minimal_manifest(), CinematicSafetyBudget(max_duration_ms=5)
        )


def test_cinematic_preflight_cli_success_and_root_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_minimal_manifest()), encoding="utf-8")
    assert cinematic_preflight_cli.main([str(manifest)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cue_count"] == 1

    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="root must be an object"):
        cinematic_preflight_cli.main([str(manifest)])


def test_headless_scalar_helpers_and_json_failures(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        headless_gui._required_string({}, "name")
    assert headless_gui._required_string({"name": " x "}, "name") == " x "
    assert headless_gui._string_or_default(1, "d") == "d"
    assert headless_gui._optional_string(1) is None
    assert headless_gui._optional_string("x") == "x"
    assert headless_gui._coerce_int(True, 5) == 5
    assert headless_gui._coerce_int(7, 5) == 7
    assert headless_gui._coerce_int("8", 5) == 8
    assert headless_gui._coerce_int("bad", 5) == 5
    assert headless_gui._optional_int(None) is None
    assert headless_gui._optional_int("9") == 9
    assert headless_gui._optional_int("bad") is None
    assert headless_gui._coerce_float(True, 1.5) == 1.5
    assert headless_gui._coerce_float(2, 1.5) == 2.0
    assert headless_gui._coerce_float("2.5", 1.5) == 2.5
    assert headless_gui._coerce_float("bad", 1.5) == 1.5

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(HeadlessGuiError, match="cannot read worker JSON"):
        headless_gui._load_json(bad)


def test_created_process_wait_terminate_close_and_context() -> None:
    class Kernel:
        def __init__(self) -> None:
            self.wait_result = headless_gui._WAIT_TIMEOUT
            self.exit_ok = True
            self.terminate_ok = True
            self.closed: list[int] = []

        def WaitForSingleObject(self, _process: int, _timeout: int) -> int:
            return self.wait_result

        def GetExitCodeProcess(self, _process: int, code: Any) -> bool:
            code._obj.value = 23
            return self.exit_ok

        def TerminateProcess(self, _process: int, _code: int) -> bool:
            return self.terminate_ok

        def CloseHandle(self, handle: int) -> bool:
            self.closed.append(int(handle))
            return True

    kernel = Kernel()
    api = SimpleNamespace(kernel32=kernel, error=lambda op: HeadlessGuiError(op))
    info = headless_gui._PROCESS_INFORMATION()
    info.hProcess = 11
    info.hThread = 12
    info.dwProcessId = 42
    process = headless_gui.CreatedProcess(api, info)
    assert process.pid == 42
    assert process.wait(-10) is None

    kernel.wait_result = 999
    with pytest.raises(HeadlessGuiError, match="WaitForSingleObject"):
        process.wait(1)
    kernel.wait_result = headless_gui._WAIT_OBJECT_0
    kernel.exit_ok = False
    with pytest.raises(HeadlessGuiError, match="GetExitCodeProcess"):
        process.wait(1)
    kernel.exit_ok = True
    assert process.wait(1) == 23

    kernel.terminate_ok = False
    with pytest.raises(HeadlessGuiError, match="TerminateProcess"):
        process.terminate()
    kernel.terminate_ok = True
    process.terminate(7)
    with process as same:
        assert same is process
    assert kernel.closed == [12, 11]
    process.close()
    assert kernel.closed == [12, 11]


def test_hidden_desktop_open_launch_and_close_with_fake_win32(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class User:
        create = 100
        close_ok = True

        def CreateDesktopW(self, *_args: object) -> int:
            return self.create

        def CloseDesktop(self, _handle: int) -> bool:
            return self.close_ok

    class Kernel:
        create_ok = True

        def CreateProcessW(self, *_args: object) -> bool:
            if self.create_ok:
                info = _args[-1]._obj
                info.hProcess = 21
                info.hThread = 22
                info.dwProcessId = 77
            return self.create_ok

        def CloseHandle(self, _handle: int) -> bool:
            return True

    api = SimpleNamespace(
        user32=User(),
        kernel32=Kernel(),
        error=lambda op: HeadlessGuiError(op),
    )
    monkeypatch.setattr(headless_gui, "_Win32Api", lambda: api)

    desktop = headless_gui.HiddenDesktop("unit")
    assert desktop.qualified_name == "WinSta0\\unit"
    with pytest.raises(HeadlessGuiError, match="not open"):
        desktop.launch(["x"])
    assert desktop.open() is desktop
    assert desktop.open() is desktop
    with pytest.raises(ValueError, match="argv"):
        desktop.launch([])
    with desktop.launch(["python", "-V"]) as process:
        assert process.pid == 77

    api.kernel32.create_ok = False
    with pytest.raises(HeadlessGuiError, match="CreateProcessW"):
        desktop.launch(["python"])
    api.kernel32.create_ok = True
    api.user32.close_ok = False
    with pytest.raises(HeadlessGuiError, match="CloseDesktop"):
        desktop.close()
    api.user32.close_ok = True
    desktop.close()
    desktop.close()

    api.user32.create = 0
    with pytest.raises(HeadlessGuiError, match="CreateDesktopW"):
        headless_gui.HiddenDesktop("other").open()


def test_desktop_name_helpers_with_fake_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    class User:
        input_handle = 51
        closed: list[int] = []

        def GetUserObjectInformationW(
            self, _handle: int, _kind: int, buffer: Any, _size: int, required: Any
        ) -> bool:
            if buffer is None:
                required._obj.value = 32
                return True
            buffer.value = "Default"
            return True

        def GetThreadDesktop(self, _thread_id: int) -> int:
            return 50

        def OpenInputDesktop(self, *_args: object) -> int:
            return self.input_handle

        def CloseDesktop(self, handle: int) -> bool:
            self.closed.append(int(handle))
            return True

    class Kernel:
        def GetCurrentThreadId(self) -> int:
            return 7

    user = User()
    api = SimpleNamespace(user32=user, kernel32=Kernel(), error=lambda op: HeadlessGuiError(op))
    monkeypatch.setattr(headless_gui, "_Win32Api", lambda: api)
    assert headless_gui.thread_desktop_name() == "Default"
    assert headless_gui.input_desktop_name() == "Default"
    assert user.closed == [51]
    user.input_handle = 0
    assert headless_gui.input_desktop_name() is None

    user.GetThreadDesktop = lambda _tid: 0  # type: ignore[method-assign]
    with pytest.raises(HeadlessGuiError, match="GetThreadDesktop"):
        headless_gui.thread_desktop_name()


def test_validated_request_success_and_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DipTrace"
    root.mkdir()
    project = tmp_path / "board.dip"
    project.write_text("x", encoding="utf-8")
    request = RoundtripRequest(root, project, "pcb")

    monkeypatch.setattr(
        headless_gui,
        "validate_diptrace_directory",
        lambda _root: SimpleNamespace(root=root),
    )
    with pytest.raises(HeadlessGuiError, match="editor is missing"):
        headless_gui._validated_request(request)

    (root / "Pcb.exe").write_bytes(b"exe")
    project.unlink()
    with pytest.raises(HeadlessGuiError, match="project file does not exist"):
        headless_gui._validated_request(request)

    project.write_text("x", encoding="utf-8")
    validated = headless_gui._validated_request(request)
    assert validated.project == project.resolve()

    def fail(_root: Path) -> object:
        raise headless_gui.ConfiguratorError("bad install")

    monkeypatch.setattr(headless_gui, "validate_diptrace_directory", fail)
    with pytest.raises(HeadlessGuiError, match="bad install"):
        headless_gui._validated_request(request)


def test_headless_command_handlers_and_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result_path = tmp_path / "probe.json"
    monkeypatch.setattr(headless_gui, "thread_desktop_name", lambda: "hidden")
    assert headless_gui._cmd_probe(argparse.Namespace(result=str(result_path))) == 0
    assert headless_gui._load_json(result_path)["desktop_name"] == "hidden"

    def broken_desktop() -> str:
        raise HeadlessGuiError("boom")

    monkeypatch.setattr(headless_gui, "thread_desktop_name", broken_desktop)
    assert headless_gui._cmd_probe(argparse.Namespace(result=str(result_path))) == 1
    assert "boom" in str(headless_gui._load_json(result_path)["error"])

    smoke = DesktopSmokeResult(True, "h", "h", "Default", "Default", 0)
    monkeypatch.setattr(headless_gui, "desktop_smoke_test", lambda timeout_seconds=1: smoke)
    assert headless_gui._cmd_smoke(argparse.Namespace(timeout=1)) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    monkeypatch.setattr(
        headless_gui,
        "detect_diptrace_installations",
        lambda: [SimpleNamespace(root=Path("/diptrace"))],
    )
    assert headless_gui._resolve_diptrace_root(None) == Path("/diptrace")
    assert headless_gui._resolve_diptrace_root("/explicit") == Path("/explicit")
    monkeypatch.setattr(headless_gui, "detect_diptrace_installations", lambda: [])
    assert headless_gui._resolve_diptrace_root(None) is None

    fake_os = SimpleNamespace(name="posix", getpid=lambda: 123, replace=os.replace)
    monkeypatch.setattr(headless_gui, "os", fake_os)
    assert headless_gui._cmd_doctor(
        argparse.Namespace(timeout=1, diptrace_root=None, require_automation=False)
    ) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "Windows is required"


def test_cmd_roundtrip_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = argparse.Namespace(
        diptrace_root=str(tmp_path),
        project=str(tmp_path / "x.dip"),
        editor="pcb",
        timeout=1,
        save_menu="File->Save",
    )
    result = RoundtripResult(
        True,
        "pcb",
        "Pcb.exe",
        "x.dip",
        1,
        2,
        "test",
        "hidden",
        "Default",
        "Default",
        "a",
        "b",
    )
    monkeypatch.setattr(headless_gui, "run_native_roundtrip", lambda _request: result)
    assert headless_gui._cmd_roundtrip(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    def fail(_request: RoundtripRequest) -> RoundtripResult:
        raise HeadlessGuiError("failed")

    monkeypatch.setattr(headless_gui, "run_native_roundtrip", fail)
    assert headless_gui._cmd_roundtrip(args) == 1
    assert "failed" in json.loads(capsys.readouterr().out)["error"]


def test_window_titles_and_missing_pywinauto(monkeypatch: pytest.MonkeyPatch) -> None:
    class Window:
        def __init__(self, value: object, fail: bool = False) -> None:
            self.value = value
            self.fail = fail

        def window_text(self) -> object:
            if self.fail:
                raise RuntimeError("ignored")
            return self.value

    class App:
        def windows(self) -> list[Window]:
            return [Window(" Main "), Window(""), Window("x", fail=True)]

    assert headless_gui._window_titles(App()) == ["Main"]
    monkeypatch.setattr(headless_gui.importlib.util, "find_spec", lambda _name: None)
    with pytest.raises(HeadlessGuiError, match="pywinauto is not installed"):
        headless_gui._pywinauto_application()


def test_main_dispatches_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(headless_gui, "_cmd_smoke", lambda _args: 7)
    assert headless_gui.main(["smoke", "--timeout", "1"]) == 7
