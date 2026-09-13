"""Coverage for the platform-neutral validation logic of the native
acceptance/export modules. Win32 boundaries are faked so the same tests run
on every platform."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from diptrace_mcp import headless_gui as hg
from diptrace_mcp import pcb_native_acceptance as pna
from diptrace_mcp import schematic_native_acceptance as sna

HeadlessGuiError = hg.HeadlessGuiError

# ---------------------------------------------------------------------------
# schematic_native_acceptance: _menu
# ---------------------------------------------------------------------------


class _FakeItem:
    def __init__(self, sub_menu: Any = None) -> None:
        self._sub_menu = sub_menu

    def sub_menu(self) -> Any:
        return self._sub_menu


def _patch_menu_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    named: list[Any],
    pinned: list[Any] | None = None,
) -> list[Any]:
    posted: list[Any] = []
    monkeypatch.setattr(sna.cr, "_find_exact_menu_item", lambda *a, **k: object())
    monkeypatch.setattr(sna.cr, "_initialized_submenu", lambda *a, **k: object())
    monkeypatch.setattr(sna.cr, "_menu_items_named", lambda *a, **k: named)
    if pinned is not None:
        monkeypatch.setattr(sna.cr, "_pinned_menu_items", lambda *a, **k: pinned)
    monkeypatch.setattr(sna.cr, "_menu_snapshot", lambda *a, **k: [])
    monkeypatch.setattr(sna.hg, "_post_menu_item", lambda w, item: posted.append(item))
    return posted


def test_menu_exact_text_path_posts_the_single_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _FakeItem()
    posted = _patch_menu_stack(monkeypatch, named=[item])

    result = sna._menu(_window(), Path("schematic.exe"), "File", "Save As...")

    assert result == "exact-text-path"
    assert posted == [item]


def test_menu_rejects_ambiguous_or_missing_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_menu_stack(monkeypatch, named=[])

    with pytest.raises(HeadlessGuiError, match="unverified File->Export menu"):
        sna._menu(_window(), Path("schematic.exe"), "File", "Export")


def test_menu_profile_requires_the_pinned_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_menu_stack(monkeypatch, named=[])
    executable = tmp_path / "Schematic.exe"
    executable.write_bytes(b"not the pinned build")

    with pytest.raises(HeadlessGuiError, match="unverified schematic menu executable"):
        sna._menu(_window(), executable, "File", "Save As...")


def test_menu_profile_posts_the_pinned_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned = [_FakeItem() for _ in range(22)]
    posted = _patch_menu_stack(monkeypatch, named=[], pinned=pinned)
    executable = tmp_path / "Schematic.exe"
    executable.write_bytes(b"exe")
    monkeypatch.setattr(sna.hg, "_sha256", lambda path: sna._EXE_SHA)

    result = sna._menu(_window(), executable, "File", "Save As...")

    assert result == "schematic-5.3.0.3-en-File-11-d85632b2"
    assert posted == [pinned[4]]


def test_menu_profile_rejects_a_submenu_in_the_leaf_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned = [_FakeItem() for _ in range(22)]
    pinned[4] = _FakeItem(sub_menu=object())
    _patch_menu_stack(monkeypatch, named=[], pinned=pinned)
    executable = tmp_path / "Schematic.exe"
    executable.write_bytes(b"exe")
    monkeypatch.setattr(sna.hg, "_sha256", lambda path: sna._EXE_SHA)

    with pytest.raises(HeadlessGuiError, match="expected schematic menu leaf"):
        sna._menu(_window(), executable, "File", "Save As...")


# ---------------------------------------------------------------------------
# schematic_native_acceptance: _validate_source
# ---------------------------------------------------------------------------

_SCHEMATIC = (
    b'<Source Type="DipTrace-Schematic" Version="5.3.0.3" Units="mm">'
    b"<Schematic><Components /></Schematic></Source>"
)


def test_validate_source_rejects_bad_suffix_and_missing_files(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / "board.dip"
    wrong.write_bytes(_SCHEMATIC)

    with pytest.raises(ValueError, match="regular schematic XML file"):
        sna._validate_source(wrong, "0" * 64)
    with pytest.raises(ValueError, match="regular schematic XML file"):
        sna._validate_source(tmp_path / "absent.dchxml", "0" * 64)


def test_validate_source_rejects_wrong_sha(tmp_path: Path) -> None:
    source = tmp_path / "board.dchxml"
    source.write_bytes(_SCHEMATIC)

    with pytest.raises(ValueError, match="SHA-256 guard failed"):
        sna._validate_source(source, "0" * 64)


def test_validate_source_accepts_the_exact_schematic(tmp_path: Path) -> None:
    source = tmp_path / "board.dchxml"
    source.write_bytes(_SCHEMATIC)
    digest = hashlib.sha256(_SCHEMATIC).hexdigest()

    sna._validate_source(source, digest)


# ---------------------------------------------------------------------------
# schematic_native_acceptance: _capture guards
# ---------------------------------------------------------------------------


def test_capture_requires_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: None)

    with pytest.raises(HeadlessGuiError, match="ffmpeg is required"):
        sna._capture(object(), tmp_path, "shot")


def test_capture_refuses_existing_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    (tmp_path / "shot.png").write_bytes(b"old")

    with pytest.raises(FileExistsError, match="capture output already exists"):
        sna._capture(object(), tmp_path, "shot")


def test_capture_requires_win32(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.delattr(ctypes, "windll", raising=False)

    with pytest.raises(HeadlessGuiError, match="Win32 API is required"):
        sna._capture(object(), tmp_path, "shot")


# ---------------------------------------------------------------------------
# schematic_native_acceptance: _capture deep paths with a faked Win32 stack
# ---------------------------------------------------------------------------


def _fake_windll(rect_ok: bool) -> Any:
    def get_window_rect(hwnd: int, ref: Any) -> int:
        if not rect_ok:
            return 0
        rect = ctypes.cast(ref, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 100, 80
        return 1

    def get_client_rect(hwnd: int, ref: Any) -> int:
        rect = ctypes.cast(ref, ctypes.POINTER(wintypes.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 90, 70
        return 1

    def client_to_screen(hwnd: int, ref: Any) -> int:
        point = ctypes.cast(ref, ctypes.POINTER(wintypes.POINT)).contents
        point.x, point.y = 5, 5
        return 1

    user32 = SimpleNamespace(
        GetWindowRect=get_window_rect,
        GetClientRect=get_client_rect,
        ClientToScreen=client_to_screen,
    )
    return SimpleNamespace(user32=user32)


def _window() -> Any:
    return SimpleNamespace(handle=42, menu=lambda: object())


class _CompletedRun:
    returncode = 0

    def __init__(self, creates: list[Path]) -> None:
        for path in creates:
            path.write_bytes(b"png-bytes")


def test_capture_returns_client_hash_when_stack_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(sna.ctypes, "windll", _fake_windll(True), raising=False)
    created = [tmp_path / "shot.png", tmp_path / "shot.client.png"]

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _CompletedRun(created)

    monkeypatch.setattr(sna.subprocess, "run", fake_run)

    def fake_record(**kwargs: Any) -> int:
        kwargs["prepare"](lambda: b"frame", 100, 80)
        return 0

    monkeypatch.setattr(sna.cr, "_record_printwindow_video", fake_record)

    digest = sna._capture(_window(), tmp_path, "shot")

    assert digest == hg._sha256(tmp_path / "shot.client.png")


def test_capture_raises_when_client_image_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(sna.ctypes, "windll", _fake_windll(True), raising=False)
    monkeypatch.setattr(
        sna.subprocess, "run", lambda cmd, **kwargs: _CompletedRun([])
    )
    monkeypatch.setattr(sna.cr, "_record_printwindow_video", lambda **kwargs: 0)

    with pytest.raises(HeadlessGuiError, match="client image"):
        sna._capture(_window(), tmp_path, "shot")


def test_capture_rejects_window_rect_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sna.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(sna.ctypes, "windll", _fake_windll(False), raising=False)

    def fake_record(**kwargs: Any) -> int:
        kwargs["prepare"](lambda: b"frame", 100, 80)
        return 0

    monkeypatch.setattr(sna.cr, "_record_printwindow_video", fake_record)

    with pytest.raises(HeadlessGuiError, match="cannot bind captured client rectangle"):
        sna._capture(_window(), tmp_path, "shot")


# ---------------------------------------------------------------------------
# schematic_native_acceptance: run() guards
# ---------------------------------------------------------------------------


def _run_args(tmp_path: Path, source: Path, **updates: Any) -> argparse.Namespace:
    payload: dict[str, Any] = {
        "project": str(source),
        "output_dir": str(tmp_path / "evidence"),
        "expected_sha256": hashlib.sha256(_SCHEMATIC).hexdigest(),
        "diptrace_root": str(tmp_path / "root"),
        "timeout": 90.0,
        "inspect": False,
        "capture": False,
        "erc": False,
        "startup_dialog_sha256": None,
    }
    payload.update(updates)
    return argparse.Namespace(**payload)


def _valid_source(tmp_path: Path) -> Path:
    source = tmp_path / "board.dchxml"
    source.write_bytes(_SCHEMATIC)
    return source


def test_run_rejects_timeout_outside_bounds(tmp_path: Path) -> None:
    source = _valid_source(tmp_path)

    with pytest.raises(ValueError, match="timeout must be finite"):
        sna.run(_run_args(tmp_path, source, timeout=5.0))


def test_run_requires_non_elevated_windows(tmp_path: Path) -> None:
    source = _valid_source(tmp_path)

    with pytest.raises(HeadlessGuiError, match="non-elevated Windows process"):
        sna.run(_run_args(tmp_path, source))


def test_run_rejects_unverified_schematic_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _valid_source(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / "Schematic.exe").write_bytes(b"not pinned")
    monkeypatch.setattr(sna, "_validate_source", lambda *args: None)
    monkeypatch.setattr(sna, "Path", type(tmp_path))
    monkeypatch.setattr(sna.os, "name", "nt")
    monkeypatch.setattr(sna.hg, "process_is_elevated", lambda: False)

    with pytest.raises(HeadlessGuiError, match="unverified Schematic.exe build"):
        sna.run(_run_args(tmp_path, source))


def test_run_rejects_symlinked_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _valid_source(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / "Schematic.exe").write_bytes(b"exe")
    monkeypatch.setattr(sna, "_validate_source", lambda *args: None)
    monkeypatch.setattr(sna, "Path", type(tmp_path))
    monkeypatch.setattr(sna.os, "name", "nt")
    monkeypatch.setattr(sna.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(sna.hg, "_sha256", lambda path: sna._EXE_SHA)
    monkeypatch.setattr(type(tmp_path), "is_symlink", lambda self: True)

    with pytest.raises(ValueError, match="must not traverse symlinks"):
        sna.run(_run_args(tmp_path, source))


# ---------------------------------------------------------------------------
# schematic_native_acceptance: main() dispatch
# ---------------------------------------------------------------------------


def test_main_worker_mode_writes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "request.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sna, "_worker", lambda request: {"completed": True})
    monkeypatch.setattr(sys, "argv", ["prog", "_worker", str(tmp_path)])

    assert sna.main() == 0
    written = json.loads((tmp_path / "worker-result.json").read_text(encoding="utf-8"))
    assert written == {"completed": True}


def test_main_cli_mode_reports_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--diptrace-root",
            "C:/DipTrace",
            "--project",
            "board.dchxml",
            "--expected-sha256",
            "a" * 64,
            "--output-dir",
            "out",
        ],
    )
    monkeypatch.setattr(sna, "run", lambda args: {"completed": False})

    assert sna.main() == 1
    assert '"completed": false' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# pcb_native_acceptance: _validate_request
# ---------------------------------------------------------------------------


def _pcb_request(tmp_path: Path, **updates: Any) -> pna.PcbNativeAcceptanceRequest:
    payload: dict[str, Any] = {
        "diptrace_root": tmp_path / "root",
        "project": tmp_path / "board.dip",
        "output_xml": tmp_path / "out" / "board.dipxml",
    }
    payload.update(updates)
    return pna.PcbNativeAcceptanceRequest(**payload)


def _fake_validator(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(
        pna,
        "validate_diptrace_directory",
        lambda value: SimpleNamespace(root=root),
    )


def _prepared_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "Pcb.exe").write_bytes(b"MZ")
    (tmp_path / "board.dip").write_bytes(b"<Board/>")
    _fake_validator(monkeypatch, root)
    return root


def test_validate_request_wraps_configurator_errors(tmp_path: Path) -> None:
    # The real validator rejects a directory without a DipTrace installation.
    with pytest.raises(HeadlessGuiError):
        pna._validate_request(_pcb_request(tmp_path))


def test_validate_request_requires_pcb_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _fake_validator(monkeypatch, root)

    with pytest.raises(HeadlessGuiError, match="PCB Layout is missing"):
        pna._validate_request(_pcb_request(tmp_path))


def test_validate_request_requires_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "Pcb.exe").write_bytes(b"MZ")
    _fake_validator(monkeypatch, root)

    with pytest.raises(HeadlessGuiError, match="project does not exist"):
        pna._validate_request(_pcb_request(tmp_path))


def test_validate_request_refuses_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepared_root(tmp_path, monkeypatch)
    output = tmp_path / "out" / "board.dipxml"
    output.parent.mkdir()
    output.write_bytes(b"<Board/>")

    with pytest.raises(HeadlessGuiError, match="output XML already exists"):
        pna._validate_request(_pcb_request(tmp_path))


def test_validate_request_requires_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepared_root(tmp_path, monkeypatch)

    with pytest.raises(HeadlessGuiError, match="baseline XML does not exist"):
        pna._validate_request(
            _pcb_request(tmp_path, baseline_xml=tmp_path / "missing.dipxml")
        )


def test_validate_request_resolves_and_prepares_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _prepared_root(tmp_path, monkeypatch)
    baseline = tmp_path / "baseline.dipxml"
    baseline.write_bytes(b"<Board/>")

    validated = pna._validate_request(_pcb_request(tmp_path, baseline_xml=baseline))

    assert validated.diptrace_root == root.resolve()
    assert validated.project == (tmp_path / "board.dip").resolve()
    assert validated.output_xml.parent.is_dir()
    assert validated.baseline_xml == baseline.resolve()
