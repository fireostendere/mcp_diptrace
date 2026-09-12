from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import schematic_native_acceptance as native


def test_unknown_or_ambiguous_menu_never_posts(monkeypatch, tmp_path):
    posted = []
    window = SimpleNamespace(menu=lambda: object())
    monkeypatch.setattr(native.cr, "_find_exact_menu_item", lambda *a, **k: object())
    monkeypatch.setattr(native.cr, "_initialized_submenu", lambda *a: object())
    monkeypatch.setattr(native.cr, "_menu_snapshot", lambda *a: {"items": []})
    monkeypatch.setattr(native.hg, "_post_menu_item", lambda *a: posted.append(a))
    monkeypatch.setattr(native.hg, "_sha256", lambda *a: native._EXE_SHA)

    def reject(*args, **kwargs):
        raise native.hg.HeadlessGuiError("unverified menu structure")

    monkeypatch.setattr(native.cr, "_pinned_menu_items", reject)
    for matches in ([], [object(), object()]):
        monkeypatch.setattr(native.cr, "_menu_items_named", lambda *a, matches=matches: matches)
        with pytest.raises(native.hg.HeadlessGuiError, match="unverified"):
            native._menu(window, tmp_path / "Schematic.exe", "File", "Save As...")
    assert not posted


def test_pinned_save_as_requires_verified_binary_and_structure(monkeypatch, tmp_path):
    posted = []
    checked = []
    leaf = SimpleNamespace(sub_menu=lambda: None)
    window = SimpleNamespace(menu=lambda: object())
    monkeypatch.setattr(native.cr, "_find_exact_menu_item", lambda *a, **k: object())
    monkeypatch.setattr(native.cr, "_initialized_submenu", lambda *a: object())
    monkeypatch.setattr(native.cr, "_menu_items_named", lambda *a: [])
    monkeypatch.setattr(native.hg, "_post_menu_item", lambda *a: posted.append(a))

    def verified(menu, ids, separators, **kwargs):
        checked.append((ids, separators))
        return [leaf] * len(ids)

    monkeypatch.setattr(native.cr, "_pinned_menu_items", verified)
    monkeypatch.setattr(native.hg, "_sha256", lambda *a: "wrong")
    with pytest.raises(native.hg.HeadlessGuiError, match="executable"):
        native._menu(window, tmp_path / "Schematic.exe", "File", "Save As...")
    assert not posted and not checked
    monkeypatch.setattr(native.hg, "_sha256", lambda *a: native._EXE_SHA)
    profile = native._menu(window, tmp_path / "Schematic.exe", "File", "Save As...")
    assert posted == [(window, leaf)] and checked
    assert "File-11" in profile


def test_exclusive_evidence_and_source_guards(tmp_path):
    path = tmp_path / "evidence.json"
    native._write_new(path, {"first": True})
    with pytest.raises(FileExistsError):
        native._write_new(path, {"first": False})
    assert '"first": true' in path.read_text()
    with pytest.raises(ValueError, match="regular schematic"):
        native._validate_source(path, native.hg._sha256(path))
    xml = tmp_path / "source.dchxml"
    xml.write_text("<Source/>")
    with pytest.raises(ValueError, match="SHA-256"):
        native._validate_source(xml, "0" * 64)


def test_worker_lifecycle_and_unreviewed_dialog(monkeypatch, tmp_path):
    processes, opened, posted = [], [], []
    window = SimpleNamespace(
        handle=7,
        menu=lambda: object(),
        wait=lambda *a, **k: None,
        class_name=lambda: "TForm1",
    )
    app = SimpleNamespace(connect=lambda **k: None, windows=lambda **k: [])
    monkeypatch.setattr(native.hg, "_pywinauto_application", lambda: lambda **k: app)
    monkeypatch.setattr(native.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(native.hg, "thread_desktop_name", lambda: "owned")
    monkeypatch.setattr(native.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(native.hg, "process_session_id", lambda: 1)
    sha256 = native.hg._sha256
    monkeypatch.setattr(
        native.hg, "_sha256", lambda p: native._EXE_SHA if p.name == "Schematic.exe" else sha256(p)
    )
    monkeypatch.setattr(native, "_validate_source", lambda *a: None)
    monkeypatch.setattr(
        native.DipTraceDocument, "load", lambda *a: SimpleNamespace(kind="schematic")
    )

    def launch(argv, desktop):
        assert desktop == "WinSta0\\owned"
        process = SimpleNamespace(pid=len(processes) + 10, closed=False, terminated=False)
        process.wait = lambda seconds: 0
        process.close = lambda: setattr(process, "closed", True)
        process.terminate = lambda code: setattr(process, "terminated", True)
        processes.append(process)
        opened.append(Path(argv[1]).name)
        return process

    monkeypatch.setattr(native.hg, "_launch_process_on_desktop", launch)
    monkeypatch.setattr(native.hg, "_main_window", lambda *a: window)
    monkeypatch.setattr(native.hg, "_post_window_message", lambda *a: posted.append(a))
    monkeypatch.setattr(native.cr, "_find_exact_menu_item", lambda *a, **k: object())
    monkeypatch.setattr(native.cr, "_initialized_submenu", lambda *a: object())
    monkeypatch.setattr(native.cr, "_menu_snapshot", lambda *a: {"items": []})
    monkeypatch.setattr(native, "_menu", lambda *a: "verified-test-profile")
    monkeypatch.setattr(
        native.hg,
        "_visible_dialog",
        lambda *a: SimpleNamespace(
            handle=8,
            class_name=lambda: "#32770",
        ),
    )
    monkeypatch.setattr(native.hg, "_save_dialog_as_xml", lambda h, p: p.write_bytes(b"native XML"))
    monkeypatch.setattr(native.hg, "_wait_for_export", lambda *a: None)

    request = {
        "output_dir": str(tmp_path),
        "diptrace_root": str(tmp_path),
        "desktop_name": "owned",
        "station": "WinSta0",
        "session": 1,
        "inspect": False,
        "capture": False,
        "erc": False,
    }
    source = tmp_path / "input.dchxml"
    source.write_bytes(b"immutable source")
    request["source_sha256"] = sha256(source)
    result = native._worker(request)
    assert result["completed"] and not result["forced_termination"]
    assert opened == ["input.dchxml", "open-save.dchxml", "reexport.dchxml"]
    assert all(p.closed and not p.terminated for p in processes)
    assert source.read_bytes() == b"immutable source"

    dialog = SimpleNamespace(
        handle=8,
        class_name=lambda: "TFMyMessage",
        window_text=lambda: "Schematics",
        descendants=lambda: [],
    )
    app.windows = lambda **k: [dialog]
    app.window = lambda **k: SimpleNamespace(wait_not=lambda *a, **k: None)
    request.update(erc=True, inspect=True)
    for index, (fingerprint, status) in enumerate(
        [
            (native._ERC_CLEAR_SHA, "no_errors_found"),
            ("different image", "review_required"),
        ]
    ):
        folder = tmp_path / f"erc-{index}"
        folder.mkdir()
        (folder / "input.dchxml").write_bytes(b"immutable source")
        request["output_dir"] = str(folder)
        monkeypatch.setattr(native, "_capture", lambda *a, value=fingerprint: value)
        result = native._worker(request)
        assert result["completed"] and result["erc_status"] == status
        assert not result["forced_termination"]
    request.update(erc=False, output_dir=str(tmp_path))
    app.windows = lambda **k: []

    window.menu = lambda: None
    window.class_name = lambda: "TFMyMessage"
    monkeypatch.setattr(native, "_capture", lambda *a: "unreviewed")
    posted.clear()
    result = native._worker(request)
    assert not result["completed"] and "acknowledgement refused" in result["error"]
    assert all(message[1] == 0x0010 for message in posted)
    assert all(p.closed for p in processes)

    window.menu = lambda: object()
    window.class_name = lambda: "TForm1"
    request["inspect"] = True
    request["output_dir"] = str(tmp_path / "hung")
    Path(request["output_dir"]).mkdir()
    (Path(request["output_dir"]) / "input.dchxml").write_bytes(b"immutable source")
    original_launch = launch

    def hung_launch(*args):
        process = original_launch(*args)
        process.wait = lambda seconds: None
        return process

    monkeypatch.setattr(native.hg, "_launch_process_on_desktop", hung_launch)
    result = native._worker(request)
    assert not result["completed"] and result["forced_termination"]
    assert processes[-1].closed and processes[-1].terminated
