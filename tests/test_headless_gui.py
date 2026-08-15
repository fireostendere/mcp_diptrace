from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

from diptrace_mcp import headless_gui
from diptrace_mcp.headless_gui import (
    DesktopSmokeResult,
    RoundtripRequest,
    RoundtripResult,
)


def test_roundtrip_request_normalizes_editor_and_paths(tmp_path: Path) -> None:
    request = RoundtripRequest(
        diptrace_root=tmp_path / "DipTrace",
        project=tmp_path / "board.dip",
        editor=" PCB ",
        timeout_seconds=12,
    )
    assert request.editor == "pcb"
    assert request.executable.name == "Pcb.exe"
    restored = RoundtripRequest.from_json(request.as_json())
    assert restored == request


@pytest.mark.parametrize("editor", ["", "pcb-layout", "unknown"])
def test_roundtrip_request_rejects_unknown_editor(tmp_path: Path, editor: str) -> None:
    with pytest.raises(ValueError, match="editor must be one of"):
        RoundtripRequest(tmp_path, tmp_path / "x", editor)


@pytest.mark.parametrize("timeout", [0, -1, 301])
def test_roundtrip_request_rejects_unsafe_timeout(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        RoundtripRequest(tmp_path, tmp_path / "x", "pcb", timeout_seconds=timeout)


def test_desktop_name_validation() -> None:
    for value in ["", "a\\b", "a/b", "x" * 129]:
        with pytest.raises(ValueError):
            headless_gui._validate_desktop_name(value)
    headless_gui._validate_desktop_name("DipTraceMCP-test")


def test_entry_argv_supports_python_and_frozen_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "executable", r"C:\\Python312\\python.exe")
    assert headless_gui._entry_argv("_probe", "--result", "x", frozen=False) == [
        r"C:\\Python312\\python.exe",
        "-m",
        "diptrace_mcp.headless_gui",
        "_probe",
        "--result",
        "x",
    ]
    assert headless_gui._entry_argv("_probe", "--result", "x", frozen=True) == [
        r"C:\\Python312\\python.exe",
        "_probe",
        "--result",
        "x",
    ]


def test_roundtrip_result_json_roundtrip() -> None:
    result = RoundtripResult(
        ok=True,
        editor="pcb",
        executable=r"C:\\DipTrace\\Pcb.exe",
        project=r"C:\\work\\board.dip",
        worker_pid=10,
        diptrace_pid=11,
        automation_backend="pywinauto-win32-message",
        desktop_name="DipTraceMCP-test",
        input_desktop_before="Default",
        input_desktop_after="Default",
        sha256_before="a",
        sha256_after="b",
    )
    assert RoundtripResult.from_json(result.as_json()) == result


def test_json_helpers_are_atomic_and_typed(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    headless_gui._write_json(path, {"hello": "мир"})
    assert headless_gui._load_json(path) == {"hello": "мир"}
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(headless_gui.HeadlessGuiError, match="root must be an object"):
        headless_gui._load_json(path)


def test_sha256_handles_missing_and_existing_files(tmp_path: Path) -> None:
    path = tmp_path / "file.bin"
    assert headless_gui._sha256(path) is None
    path.write_bytes(b"abc")
    assert headless_gui._sha256(path) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_smoke_reports_platform_error_outside_windows() -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract")
    result = headless_gui.desktop_smoke_test()
    assert not result.ok
    assert "only on Windows" in (result.error or "")


def test_smoke_result_json_shape() -> None:
    result = DesktopSmokeResult(
        ok=True,
        desktop_name="hidden",
        child_desktop_name="hidden",
        input_desktop_before="Default",
        input_desktop_after="Default",
        child_exit_code=0,
    )
    payload = result.as_json()
    assert json.loads(json.dumps(payload))["ok"] is True


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 desktop objects")
def test_real_hidden_desktop_smoke() -> None:
    result = headless_gui.desktop_smoke_test(timeout_seconds=20)
    assert result.ok, result.error
    assert result.child_exit_code == 0
    assert result.child_desktop_name == result.desktop_name
    if result.input_desktop_before is not None and result.input_desktop_after is not None:
        assert result.input_desktop_before == result.input_desktop_after


def test_cli_help_and_non_windows_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        headless_gui.main(["--help"])
    assert exc.value.code == 0
    assert "isolated Win32 desktop" in capsys.readouterr().out


def test_roundtrip_request_desktop_mode_default_and_validation(tmp_path: Path) -> None:
    assert RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb").desktop_mode == "hidden"
    assert (
        RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode=" NATIVE ").desktop_mode
        == "native"
    )
    with pytest.raises(ValueError, match="desktop_mode must be one of"):
        RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode="virtual")


def test_roundtrip_request_json_desktop_mode_backward_compatible(tmp_path: Path) -> None:
    request = RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode="native")
    payload = request.as_json()
    assert payload["desktop_mode"] == "native"
    legacy = {key: value for key, value in payload.items() if key != "desktop_mode"}
    assert RoundtripRequest.from_json(legacy).desktop_mode == "hidden"
    assert RoundtripRequest.from_json(payload).desktop_mode == "native"


def test_roundtrip_result_json_desktop_mode() -> None:
    result = RoundtripResult(
        ok=True,
        editor="pcb",
        executable="x",
        project="y",
        worker_pid=1,
        diptrace_pid=2,
        automation_backend="pywinauto-win32-message",
        desktop_name="WinSta0\\DipTraceMCP-x",
        input_desktop_before="Default",
        input_desktop_after="Default",
        sha256_before=None,
        sha256_after=None,
        desktop_mode="native",
    )
    assert RoundtripResult.from_json(result.as_json()) == result
    legacy = dict(result.as_json())
    legacy.pop("desktop_mode")
    assert RoundtripResult.from_json(legacy).desktop_mode == "hidden"


def test_cli_roundtrip_desktop_argument_defaults_and_rejects_invalid() -> None:
    parser = headless_gui._build_parser()
    base = ["roundtrip", "--diptrace-root", "r", "--project", "p", "--editor", "pcb"]
    assert parser.parse_args(base).desktop == "hidden"
    assert parser.parse_args([*base, "--desktop", "native"]).desktop == "native"
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--desktop", "virtual"])


class _FakeWorker:
    def __init__(self, argv: list[str], payload: dict[str, object]) -> None:
        self.argv = list(argv)
        self.payload = payload
        self.terminated = False

    def wait(self, timeout: float) -> int:
        index = self.argv.index("--result")
        Path(self.argv[index + 1]).write_text(
            json.dumps(self.payload), encoding="utf-8"
        )
        return 0

    def terminate(self, exit_code: int = 1) -> None:
        self.terminated = True

    def close(self) -> None:
        return None

    def __enter__(self) -> _FakeWorker:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _result_payload(desktop_name: str, desktop_mode: str) -> dict[str, object]:
    return RoundtripResult(
        ok=True,
        editor="pcb",
        executable="x",
        project="y",
        worker_pid=1,
        diptrace_pid=2,
        automation_backend="pywinauto-win32-message",
        desktop_name=desktop_name,
        input_desktop_before="Default",
        input_desktop_after="Default",
        sha256_before=None,
        sha256_after=None,
        desktop_mode=desktop_mode,
    ).as_json()


def test_run_native_roundtrip_hidden_mode_launches_worker_on_hidden_desktop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode="hidden")
    fake_os = types.ModuleType("os")
    fake_os.__dict__.update(os.__dict__)
    fake_os.name = "nt"
    monkeypatch.setattr(headless_gui, "os", fake_os)
    monkeypatch.setattr(headless_gui, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(headless_gui, "_validated_request", lambda request: request)
    launched: dict[str, object] = {}

    class FakeDesktop:
        def __init__(self, name: str) -> None:
            self.name = name
            launched["desktop"] = name

        def launch(self, argv, cwd=None):
            launched["argv"] = list(argv)
            return _FakeWorker(list(argv), _result_payload(self.name, "hidden"))

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

    def fail_plain(argv, cwd=None):
        raise AssertionError("native launcher must not be used in hidden mode")

    monkeypatch.setattr(headless_gui, "HiddenDesktop", FakeDesktop)
    monkeypatch.setattr(headless_gui, "_launch_on_current_desktop", fail_plain)

    result = headless_gui.run_native_roundtrip(request)

    assert result.ok is True
    assert str(launched["desktop"]).startswith("DipTraceMCP-")
    assert result.desktop_name == launched["desktop"]
    assert result.desktop_mode == "hidden"
    assert "DipTraceMCP-" in str(launched["argv"])


def test_run_native_roundtrip_native_mode_uses_current_desktop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode="native")
    fake_os = types.ModuleType("os")
    fake_os.__dict__.update(os.__dict__)
    fake_os.name = "nt"
    monkeypatch.setattr(headless_gui, "os", fake_os)
    monkeypatch.setattr(headless_gui, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(headless_gui, "_validated_request", lambda request: request)
    launched: dict[str, object] = {}

    def fake_plain(argv, cwd=None):
        launched["argv"] = list(argv)
        return _FakeWorker(list(argv), _result_payload("Default", "native"))

    def fail_hidden(name: str):
        raise AssertionError("hidden desktop must not be created in native mode")

    monkeypatch.setattr(headless_gui, "_launch_on_current_desktop", fake_plain)
    monkeypatch.setattr(headless_gui, "HiddenDesktop", fail_hidden)

    result = headless_gui.run_native_roundtrip(request)

    assert result.ok is True
    assert result.desktop_name == "Default"
    assert result.desktop_mode == "native"
    argv = launched["argv"]
    assert argv[argv.index("--desktop-name") + 1] == "Default"


def test_run_native_roundtrip_native_mode_declined_without_input_desktop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = RoundtripRequest(tmp_path, tmp_path / "b.dip", "pcb", desktop_mode="native")
    fake_os = types.ModuleType("os")
    fake_os.__dict__.update(os.__dict__)
    fake_os.name = "nt"
    monkeypatch.setattr(headless_gui, "os", fake_os)
    monkeypatch.setattr(headless_gui, "input_desktop_name", lambda: None)
    monkeypatch.setattr(headless_gui, "_validated_request", lambda request: request)

    with pytest.raises(headless_gui.HeadlessGuiError, match="native launch declined"):
        headless_gui.run_native_roundtrip(request)
