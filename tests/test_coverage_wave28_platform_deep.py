# ruff: noqa: E501

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import cinematic_recording, sessions
from diptrace_mcp import native_xml_export as export
from diptrace_mcp import pcb_native_acceptance as pcb
from diptrace_mcp import schematic_native_acceptance as schematic


def test_session_io_reaper_and_mutation_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state"
    path.write_bytes(b"abc")
    real_read = sessions.os.read
    monkeypatch.setattr(sessions.os, "read", lambda fd, size: (_ for _ in ()).throw(OSError("nope")))
    with pytest.raises(sessions.SessionError, match="Cannot read"):
        sessions._stable_regular_file_bytes(path, 10, purpose="state")
    monkeypatch.setattr(sessions.os, "read", real_read)
    assert sessions._stable_regular_file_bytes(path, 10, purpose="state") == b"abc"



def test_native_xml_worker_dialog_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")
    image_hash = "a" * 64
    child = SimpleNamespace(
        class_name=lambda: "TButton", window_text=lambda: "OK", is_visible=lambda: True,
        is_enabled=lambda: True, handle=8,
    )
    dialog = SimpleNamespace(
        menu=lambda: None, class_name=lambda: "TFMyMessage", descendants=lambda: [child], handle=7,
    )
    main = SimpleNamespace(menu=lambda: object(), class_name=lambda: "TForm1", handle=9)
    app = SimpleNamespace(process=12, start=lambda *_a, **_k: None, wait_for_process_exit=lambda **_k: None)
    windll = SimpleNamespace(uxtheme=SimpleNamespace(SetWindowTheme=lambda *_a: 0), user32=object())
    monkeypatch.setattr(export.ctypes, "windll", windll, raising=False)
    monkeypatch.setattr(export.hg, "thread_desktop_name", lambda: "desk")
    monkeypatch.setattr(export.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(export.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(export.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(export.hg, "_pywinauto_application", lambda: lambda **_k: app)
    monkeypatch.setattr(export.hg, "_main_window", lambda *_a: dialog if not getattr(app, "seen", False) else main)
    monkeypatch.setattr(cinematic_recording, "_record_printwindow_video", lambda **_k: setattr(app, "seen", True))
    monkeypatch.setattr(export.shutil, "which", lambda _name: "ffmpeg")
    monkeypatch.setattr(export.hg, "_sha256", lambda _path: image_hash)
    monkeypatch.setattr(export, "_save_as", lambda *_a: None)
    monkeypatch.setattr(export.hg, "_visible_dialog", lambda *_a: SimpleNamespace(class_name=lambda: "#32770", handle=5))
    monkeypatch.setattr(export.hg, "_save_dialog_as_xml", lambda _h, p: p.write_text("<xml/>", encoding="utf-8"))
    monkeypatch.setattr(export.hg, "_wait_for_export", lambda *_a: None)
    monkeypatch.setattr(export.hg, "_post_window_message", lambda *_a: None)
    result = export._worker({"source": str(source), "output": str(output), "root": str(tmp_path), "desktop": "desk", "station": "WinSta0", "session": 1, "timeout": 10, "startup_dialog_sha256": image_hash})
    assert result["ok"] and result["acknowledged_dialog_sha256"] == image_hash

    app.windows = lambda **_k: [SimpleNamespace(is_visible=lambda: True, window_text=lambda: "bad", class_name=lambda: "D", is_enabled=lambda: True, menu=lambda: None, descendants=lambda: [])]
    app.kill = lambda **_k: setattr(app, "killed", True)
    app.start = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("start failed"))
    failed = export._worker({"source": str(source), "output": str(output), "root": str(tmp_path), "desktop": "desk", "station": "WinSta0", "session": 1, "timeout": 10})
    assert not failed["ok"] and failed["forced_termination"] and app.killed


def test_schematic_run_worker_timeout_and_identity_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, folder = tmp_path / "source.dchxml", tmp_path / "evidence"
    source.write_text('<Source Type="DipTrace-Schematic"/>', encoding="utf-8")
    args = SimpleNamespace(project=str(source), output_dir=str(folder), expected_sha256="a" * 64, timeout=30, diptrace_root=str(tmp_path), inspect=False, capture=False, erc=False, startup_dialog_sha256=None)
    monkeypatch.setattr(schematic, "_validate_source", lambda *_a: None)
    monkeypatch.setattr(schematic, "os", SimpleNamespace(name="nt", getpid=lambda: 1))
    monkeypatch.setattr(schematic.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(schematic.hg, "_sha256", lambda p: schematic._EXE_SHA if p.name == "Schematic.exe" else "a" * 64)
    monkeypatch.setattr(schematic.hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(schematic.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(schematic.hg, "process_session_id", lambda: 1)

    class Job:
        def terminate_and_close(self) -> None: pass
    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *_a): return None
        def launch(self, _argv, job): return Worker()
    class Worker:
        def __enter__(self): return self
        def __exit__(self, *_a): return None
    monkeypatch.setattr(schematic.hg, "HiddenDesktop", lambda _n: Desktop())
    monkeypatch.setattr(schematic.KillOnCloseJob, "create", lambda: Job())
    result = schematic.run(args)
    assert not result["completed"] and "AttributeError" in result["error"]


def test_schematic_worker_captures_owned_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.dchxml"
    source.write_text("<Source/>", encoding="utf-8")
    window = SimpleNamespace(
        handle=7,
        menu=lambda: object(),
        class_name=lambda: "TForm1",
        wait=lambda *_a, **_k: None,
        move_window=lambda **_k: None,
    )
    process = SimpleNamespace(pid=2, wait=lambda _seconds: 0, close=lambda: None)
    app = SimpleNamespace(connect=lambda **_k: None, windows=lambda **_k: [])
    monkeypatch.setattr(schematic.hg, "thread_desktop_name", lambda: "desk")
    monkeypatch.setattr(schematic.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(schematic.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(schematic.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(schematic.hg, "_sha256", lambda _path: schematic._EXE_SHA)
    monkeypatch.setattr(schematic, "_validate_source", lambda *_a: None)
    monkeypatch.setattr(schematic.hg, "_launch_process_on_desktop", lambda *_a: process)
    monkeypatch.setattr(schematic.hg, "_pywinauto_application", lambda: lambda **_k: app)
    monkeypatch.setattr(schematic.hg, "_main_window", lambda *_a: window)
    monkeypatch.setattr(schematic.hg, "_post_window_message", lambda *_a: None)
    monkeypatch.setattr(schematic.cr, "_find_exact_menu_item", lambda *_a, **_k: object())
    monkeypatch.setattr(schematic.cr, "_initialized_submenu", lambda *_a: object())
    monkeypatch.setattr(schematic.cr, "_menu_snapshot", lambda *_a: {})
    monkeypatch.setattr(schematic.cr, "_physical_pixel_dpi_context", lambda _a: nullcontext())
    monkeypatch.setattr(schematic.cr, "_zoom_extents_via_native_menu", lambda *_a: None)
    monkeypatch.setattr(schematic, "_capture", lambda *_a: "capture")
    monkeypatch.setattr(schematic.time, "sleep", lambda _a: None)
    monkeypatch.setattr(
        schematic.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(ShowWindow=lambda *_a: None)),
        raising=False,
    )
    result = schematic._worker(
        {
            "output_dir": str(tmp_path),
            "diptrace_root": str(tmp_path),
            "source_sha256": schematic._EXE_SHA,
            "desktop_name": "desk",
            "station": "WinSta0",
            "session": 1,
            "inspect": True,
            "capture": True,
            "erc": False,
            "startup_dialog_sha256": None,
        }
    )
    assert result["completed"] and result["native_steps"][0]["closed"]


def test_pcb_native_timeout_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = pcb.PcbNativeAcceptanceRequest.model_validate({"diptrace_root": tmp_path, "project": tmp_path / "board.dip", "output_xml": tmp_path / "out.dipxml", "desktop_mode": "hidden"})
    monkeypatch.setattr(pcb, "os", SimpleNamespace(name="nt", getpid=lambda: 1))
    monkeypatch.setattr(pcb, "_validate_request", lambda value: value)
    monkeypatch.setattr(pcb, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(pcb, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(pcb, "process_session_id", lambda: 1)
    monkeypatch.setattr(pcb, "_immutable_baseline", lambda *_a: None)
    class Process:
        def wait(self, _timeout): return None
        def terminate(self, _code): self.terminated = True
    class Desktop:
        def __enter__(self): return self
        def __exit__(self, *_a): return None
        def launch(self, _argv): return ProcessContext()
    class ProcessContext:
        def __enter__(self): return Process()
        def __exit__(self, *_a): return None
    monkeypatch.setattr(pcb, "HiddenDesktop", lambda _name: Desktop())
    with pytest.raises(pcb.HeadlessGuiError, match="timed out"):
        pcb.run_pcb_native_acceptance(request)
