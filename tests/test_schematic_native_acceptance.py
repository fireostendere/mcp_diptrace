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
    assert profile == "schematic-5.3.0.3-en-File-11-d85632b2"
    build_5351 = next(sha for sha, build in native._BUILDS.items() if build[0] == "5.3.5.1")
    monkeypatch.setattr(native.hg, "_sha256", lambda *a: build_5351)
    executable = tmp_path / "Schematic.exe"
    profile = native._menu(window, executable, "Verification", "Electrical Rule Check")
    assert profile == "schematic-5.3.5.1-en-Verification-285-0ba7c412"
    assert checked[-1] == ((285, 286, 287), frozenset())


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
        is_enabled=lambda: True,
        process_id=lambda: processes[-1].pid,
        is_visible=lambda: True,
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
        lambda *a, **k: SimpleNamespace(
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
    assert all(step["status"] == "completed" for step in result["native_steps"])

    # A failed Save As phase must never be recorded as completed or saved.
    failed_folder = tmp_path / "failed-save"
    failed_folder.mkdir()
    (failed_folder / "input.dchxml").write_bytes(b"immutable source")
    request["output_dir"] = str(failed_folder)
    with monkeypatch.context() as patch:
        def fail_save(*args, **kwargs):
            raise native.hg.HeadlessGuiError("unexpected Save As dialog")
        patch.setattr(native.hg, "_visible_dialog", fail_save)
        modal = SimpleNamespace(
            handle=80, window_text=lambda: "Import warning", class_name=lambda: "TFMyMessage",
            is_visible=lambda: True, is_enabled=lambda: True, menu=lambda: None,
            process_id=lambda: 10, parent=lambda: window, descendants=lambda: [],
        )
        hidden = [SimpleNamespace(handle=100 + i, is_visible=lambda: False) for i in range(70)]
        # Only after Save As is requested; hidden windows enumerate before the rejected modal.
        def failing_menu(*args):
            app.windows = lambda **k: [modal] if k.get("visible_only") else [*hidden, modal]
            return "verified-test-profile"
        patch.setattr(native, "_menu", failing_menu)
        patch.setattr(native, "_capture", lambda *args: "d" * 64)
        failed = native._worker(request)
    assert not failed["completed"]
    assert failed["native_steps"][0]["status"] == "failed"
    assert "exported" not in failed["native_steps"][0]
    assert failed["error_windows"][0] == {
        "handle": 80, "title": "Import warning", "class": "TFMyMessage",
        "visible": True, "enabled": True, "pid": 10, "owner_handle": 7, "controls": [],
        "client_image": str(failed_folder / "rejected-dialog-0.client.png"),
        "client_sha256": "d" * 64,
    }
    app.windows = lambda **k: []
    request["output_dir"] = str(tmp_path)

    dialog = SimpleNamespace(
        handle=8,
        class_name=lambda: "TFMyMessage",
        window_text=lambda: "Schematics",
        descendants=lambda: [],
        is_visible=lambda: True,
        is_enabled=lambda: True,
        parent=lambda: window,
        process_id=lambda: 10,
    )
    def erc_menu(*args):
        app.windows = lambda **k: [dialog]
        return "verified-test-profile"
    monkeypatch.setattr(native, "_menu", erc_menu)
    def close_erc(*args):
        posted.append(args)
        app.windows = lambda **k: []
    monkeypatch.setattr(native.hg, "_post_window_message", close_erc)
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

    # Every supplied variant is exact: a neighboring/unknown digest remains refused.
    button = SimpleNamespace(
        handle=9, class_name=lambda: "TButton", window_text=lambda: "OK",
        is_enabled=lambda: True, is_visible=lambda: True,
    )
    window.descendants = lambda: [button]
    # BM_CLICK is asynchronous: dismissal happens only when wait_not observes the HWND.
    def wait_for_acknowledged_dialog(*args, **kwargs):
        assert window.menu() is None
        assert posted[-1][1] == 0x00F5
        window.menu = lambda: object()
        window.class_name = lambda: "TForm1"
    app.window = lambda **k: SimpleNamespace(wait_not=wait_for_acknowledged_dialog)
    for index, fingerprint in enumerate(["a" * 64, "b" * 64, "c" * 64]):
        folder = tmp_path / f"startup-{index}"
        folder.mkdir()
        (folder / "input.dchxml").write_bytes(b"immutable source")
        request.update(inspect=True, output_dir=str(folder),
                       startup_dialog_sha256=["a" * 64, "b" * 64])
        window.menu = lambda: None
        window.class_name = lambda: "TFMyMessage"
        monkeypatch.setattr(native, "_capture", lambda *a, value=fingerprint: value)
        def acknowledge(*args):
            posted.append(args)
        monkeypatch.setattr(native.hg, "_post_window_message", acknowledge)
        posted.clear()
        result = native._worker(request)
        assert result["completed"] == (index < 2)
        assert any(message[1] == 0x00F5 for message in posted) == (index < 2)

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
def test_startup_authorization_requires_exact_reviewed_hashes():
    first, second = "a" * 64, "b" * 64
    assert native._startup_hashes(None) == []
    assert native._startup_hashes(first) == [first]
    assert native._startup_hashes([first, second]) == [first, second]
    for invalid in ("", "A" * 64, "a" * 63, [first, "invalid"], 123):
        with pytest.raises(ValueError, match="startup"):
            native._startup_hashes(invalid)


def test_menu_readiness_rejects_late_or_unknown_owned_modal():
    window = SimpleNamespace(handle=7, is_enabled=lambda: True, menu=lambda: object())
    app = SimpleNamespace(process=42, windows=lambda **kwargs: [])
    native._require_menu_ready(app, window)
    modal = SimpleNamespace(
        handle=8, is_visible=lambda: True, class_name=lambda: "UnknownImport",
        parent=lambda: window, process_id=lambda: 42,
    )
    app.windows = lambda **kwargs: [modal]
    with pytest.raises(native.hg.HeadlessGuiError, match="blocked"):
        native._require_menu_ready(app, window)
    app.windows = lambda **kwargs: []
    window.is_enabled = lambda: False
    with pytest.raises(native.hg.HeadlessGuiError, match="blocked"):
        native._require_menu_ready(app, window)
