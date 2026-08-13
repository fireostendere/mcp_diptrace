from __future__ import annotations

import json
import os
import sys
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
