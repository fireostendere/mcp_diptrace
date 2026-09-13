"""Synthetic safety checks; these do not claim native DipTrace acceptance."""

import pytest

from diptrace_mcp import native_xml_export as nx
from diptrace_mcp.errors import DocumentError


@pytest.mark.parametrize(
    ("suffix", "xml_suffix", "source_type"),
    [(".dch", ".dchxml", "DipTrace-Schematic"), (".dip", ".dipxml", "DipTrace-PCB")],
)
def test_export_opens_copy_and_preserves_original(
    tmp_path, monkeypatch, suffix, xml_suffix, source_type
):
    source = tmp_path / ("original" + suffix)
    source.write_bytes(b"native source")
    target = tmp_path / ("export" + xml_suffix)

    def run(root, copy, output, timeout, approval):
        assert copy != source
        assert copy.read_bytes() == b"native source"
        copy.write_bytes(b"editor may save its private copy")
        output.write_text(f'<Source Type="{source_type}" Version="5.3.0.3" Units="mm"/>')
        return {"ok": True, "desktop_changed": False}

    monkeypatch.setattr(nx, "_run_hidden", run)
    result = nx.export_native_xml(tmp_path, source, target)
    assert result["ok"] is True
    assert result["source_type"] == source_type
    assert result["source_sha256_before"] == result["source_sha256_after"]
    assert source.read_bytes() == b"native source"
    assert target.is_file()
    assert not list(tmp_path.glob(".diptrace-export-*"))


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 301])
def test_invalid_timeout_fails_before_launch(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))
    with pytest.raises(ValueError):
        nx.export_native_xml(tmp_path, tmp_path / "board.dip", tmp_path / "out.dipxml", timeout)


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dip", tmp_path / "out.dipxml"
    source.write_bytes(b"source")
    target.write_bytes(b"existing")
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))
    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, target)
    assert target.read_bytes() == b"existing"


@pytest.mark.parametrize("contents", ["not XML", '<Source Type="DipTrace-PCB"/>'])
def test_bad_export_is_not_published(tmp_path, monkeypatch, contents):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text(contents)
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises((DocumentError, ValueError)):
        nx.export_native_xml(tmp_path, source, target)
    assert not target.exists()


def test_worker_failure_does_not_publish_partial_xml(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        return {"ok": False, "error": "native dialog blocked export"}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(RuntimeError, match="native dialog"):
        nx.export_native_xml(tmp_path, source, target)
    assert not target.exists()


def test_output_race_preserves_other_file(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        target.write_bytes(b"created by someone else")
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, target)
    assert target.read_bytes() == b"created by someone else"


def test_changed_original_is_reported_not_restored(tmp_path, monkeypatch):
    source, target = tmp_path / "board.dch", tmp_path / "out.dchxml"
    source.write_bytes(b"source")

    def run(root, copy, output, timeout, approval):
        output.write_text('<Source Type="DipTrace-Schematic"/>')
        source.write_bytes(b"concurrent user edit")
        return {"ok": True}

    monkeypatch.setattr(nx, "_run_hidden", run)
    with pytest.raises(RuntimeError, match="source changed"):
        nx.export_native_xml(tmp_path, source, target)
    assert source.read_bytes() == b"concurrent user edit"
    assert not target.exists()


def test_export_rejects_invalid_startup_dialog_sha256(tmp_path, monkeypatch):
    """Test that invalid SHA-256 for startup dialog is rejected."""
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        nx.export_native_xml(
            tmp_path, source, target, startup_dialog_sha256="invalid_sha"
        )


def test_export_rejects_symlink_project(tmp_path, monkeypatch):
    """Test that symlink project files are rejected."""
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    symlink = tmp_path / "link.dch"
    symlink.symlink_to(source)
    target = tmp_path / "out.dchxml"
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))

    with pytest.raises(ValueError, match="regular native"):
        nx.export_native_xml(tmp_path, symlink, target)


def test_export_rejects_symlink_output(tmp_path, monkeypatch):
    """Test that symlink output files are rejected."""
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"
    target.write_bytes(b"existing")
    symlink = tmp_path / "link.dchxml"
    symlink.symlink_to(target)
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))

    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, symlink)


def test_export_rejects_wrong_output_suffix(tmp_path, monkeypatch):
    """Test that wrong output XML suffix is rejected."""
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.xml"  # Wrong suffix
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))

    with pytest.raises(ValueError, match="output must be a separate"):
        nx.export_native_xml(tmp_path, source, target)


def test_export_rejects_output_same_as_source(tmp_path, monkeypatch):
    """Test that output path same as source is rejected with FileExistsError.

    The check order in export_native_xml is:
    1. output_xml.is_symlink() or output_xml.exists() -> FileExistsError
    2. target.suffix or target == source -> ValueError

    If output_xml == source, the file exists, so FileExistsError is raised first.
    """
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    monkeypatch.setattr(nx, "_run_hidden", lambda *args: pytest.fail("must not launch"))

    # When output_xml == source, the file exists, so FileExistsError is raised
    with pytest.raises(FileExistsError):
        nx.export_native_xml(tmp_path, source, source)


def test_run_hidden_raises_on_non_windows(tmp_path, monkeypatch):
    """Test that _run_hidden raises on non-Windows platforms."""
    monkeypatch.setattr(nx.os, "name", "posix")
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"

    with pytest.raises(nx.hg.HeadlessGuiError, match="requires Windows"):
        nx._run_hidden(tmp_path, source, target, 90.0)


def test_run_hidden_raises_on_elevated_process(tmp_path, monkeypatch):
    """Test that _run_hidden raises when process is elevated."""
    monkeypatch.setattr(nx.os, "name", "nt")
    monkeypatch.setattr(nx.hg, "process_is_elevated", lambda: True)
    monkeypatch.setattr(
        nx, "validate_diptrace_directory", lambda root: type("obj", (), {"root": root})()
    )
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"

    with pytest.raises(nx.hg.HeadlessGuiError, match="normal user token"):
        nx._run_hidden(tmp_path, source, target, 90.0)


def test_save_as_raises_on_no_menu(tmp_path):
    """Test that _save_as raises when window has no menu."""
    from types import SimpleNamespace

    window = SimpleNamespace(menu=lambda: None, handle=123)
    executable = tmp_path / "Schematic.exe"

    with pytest.raises(nx.hg.HeadlessGuiError, match="not menu-ready"):
        nx._save_as(window, executable)


def test_save_as_raises_on_no_unique_file_menu(tmp_path, monkeypatch):
    """Test that _save_as raises when File menu is not unique."""
    from types import SimpleNamespace

    menu = SimpleNamespace(
        items=lambda: [
            SimpleNamespace(text=lambda: "File", sub_menu=lambda: None, index=lambda: 0)
        ]
        * 2  # Two File menus
    )
    window = SimpleNamespace(menu=lambda: menu, handle=123)
    executable = tmp_path / "Schematic.exe"

    with pytest.raises(nx.hg.HeadlessGuiError, match="no unique File menu"):
        nx._save_as(window, executable)


def test_save_as_posts_menu_item_on_text_match(tmp_path, monkeypatch):
    """Test that _save_as posts menu item when text matches."""
    from types import SimpleNamespace

    posted = []
    save_as_item = SimpleNamespace(
        text=lambda: "Save As...", item_id=lambda: 4, is_enabled=lambda: True
    )
    submenu = SimpleNamespace(
        items=lambda: [save_as_item], handle=456
    )
    file_item = SimpleNamespace(
        text=lambda: "File", sub_menu=lambda: submenu, index=lambda: 0
    )
    menu = SimpleNamespace(items=lambda: [file_item])
    window = SimpleNamespace(menu=lambda: menu, handle=123)
    executable = tmp_path / "Schematic.exe"

    monkeypatch.setattr(nx.hg, "_post_menu_item", lambda w, item: posted.append(item))
    monkeypatch.setattr(nx.hg, "_send_window_message", lambda *args: None)

    nx._save_as(window, executable)
    assert len(posted) == 1
    assert posted[0] == save_as_item


def test_worker_raises_on_windll_none(tmp_path):
    """Test that _worker returns error when ctypes.windll is None (Linux).

    On Linux, getattr(ctypes, "windll", None) returns None automatically.
    The _worker function catches this in try/except and returns a result dict
    with ok=False and error message, rather than raising an exception.
    """
    # Create the source file
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")

    request = {
        "source": str(source),
        "output": str(tmp_path / "out.dchxml"),
        "root": str(tmp_path),
        "desktop": "test_desktop",
        "station": "WinSta0",
        "session": 1,
        "timeout": 90.0,
    }

    # On Linux, windll is None, so _worker should return error result
    result = nx._worker(request)
    assert result["ok"] is False
    assert "Windows bindings are unavailable" in result["error"]


def test_worker_desktop_mismatch_not_testable_on_linux():
    """Desktop mismatch check is not testable on Linux.

    The _worker function checks windll first (line 246-247), and on Linux
    getattr(ctypes, "windll", None) returns None, so the windll check
    raises HeadlessGuiError before reaching the desktop mismatch check
    (line 248-254). This test documents this platform limitation.
    """
    pytest.skip("Desktop mismatch check is unreachable on Linux due to windll check")


def test_main_worker_mode(tmp_path, monkeypatch):
    """Test main() in worker mode."""
    import json
    import sys

    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps({"ok": True}))

    monkeypatch.setattr(
        sys,
        "argv",
        ["native_xml_export", "_worker", str(request_path), str(result_path)],
    )
    monkeypatch.setattr(nx.hg, "_load_json", lambda p: json.loads(p.read_text()))
    monkeypatch.setattr(nx.hg, "_write_json", lambda p, d: p.write_text(json.dumps(d)))
    monkeypatch.setattr(nx, "_worker", lambda req: {"ok": True})

    result = nx.main()
    assert result == 0
    assert result_path.exists()


def test_main_argparse_mode_error(tmp_path, monkeypatch, capsys):
    """Test main() in argparse mode with error."""
    import sys

    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "native_xml_export",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(source),
            "--output-xml",
            str(target),
            "--timeout",
            "0",  # Invalid timeout
        ],
    )

    result = nx.main()
    assert result == 1
    captured = capsys.readouterr()
    assert '"ok": false' in captured.out
    assert "timeout" in captured.out


def test_main_argparse_mode_success(tmp_path, monkeypatch, capsys):
    """Test main() in argparse mode with successful export."""
    import sys
    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    target = tmp_path / "out.dchxml"

    mock_result = {
        "ok": True,
        "source": str(source),
        "output_xml": str(target),
        "source_sha256_before": "abc",
        "source_sha256_after": "abc",
        "source_type": "DipTrace-Schematic",
        "xml_sha256": "def",
        "xml_version": "5.3.0.3",
        "erc_drc": "not_run",
    }

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "native_xml_export",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(source),
            "--output-xml",
            str(target),
        ],
    )
    monkeypatch.setattr(nx, "export_native_xml", lambda *a, **k: mock_result)

    result = nx.main()
    assert result == 0
    captured = capsys.readouterr()
    assert '"ok": true' in captured.out


def test_save_as_unverified_menu_raises(tmp_path, monkeypatch):
    """Test _save_as raises when menu cannot be verified."""
    from types import SimpleNamespace

    # Create menu items with mismatched IDs
    items = [
        SimpleNamespace(text=lambda: "", item_id=lambda: 999, is_enabled=lambda: True),
    ]

    submenu = SimpleNamespace(items=lambda: items, handle=456)
    file_item = SimpleNamespace(
        text=lambda: "File", sub_menu=lambda: submenu, index=lambda: 0
    )
    menu = SimpleNamespace(items=lambda: [file_item])
    window = SimpleNamespace(menu=lambda: menu, handle=123)
    executable = tmp_path / "Schematic.exe"

    monkeypatch.setattr(nx.hg, "_send_window_message", lambda *args: None)
    monkeypatch.setattr(nx.hg, "_sha256", lambda p: "wrong_sha")

    with pytest.raises(nx.hg.HeadlessGuiError, match="unverified Save As menu"):
        nx._save_as(window, executable)


def test_worker_success_path(tmp_path, monkeypatch):
    """Test _worker success path with mocked Win32 components."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    source = tmp_path / "board.dch"
    source.write_bytes(b"source")
    output = tmp_path / "out.dchxml"

    request = {
        "source": str(source),
        "output": str(output),
        "root": str(tmp_path),
        "desktop": "test_desktop",
        "station": "WinSta0",
        "session": 1,
        "timeout": 90.0,
    }

    # Mock windll
    mock_windll = SimpleNamespace(user32=SimpleNamespace())
    monkeypatch.setattr(nx.ctypes, "windll", mock_windll, raising=False)

    # Mock desktop/session checks
    monkeypatch.setattr(nx.hg, "thread_desktop_name", lambda: "test_desktop")
    monkeypatch.setattr(nx.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(nx.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(nx.hg, "process_is_elevated", lambda: False)

    # Mock pywinauto application
    mock_window = SimpleNamespace(
        menu=lambda: SimpleNamespace(),
        handle=123,
    )
    mock_app = SimpleNamespace(
        process=456,
        start=MagicMock(),
        wait_for_process_exit=MagicMock(),
    )
    monkeypatch.setattr(
        nx.hg, "_pywinauto_application", lambda: lambda backend="win32": mock_app
    )
    monkeypatch.setattr(nx.hg, "_main_window", lambda app, src, timeout: mock_window)

    # Mock menu operations
    monkeypatch.setattr(nx, "_save_as", lambda w, e: None)
    monkeypatch.setattr(
        nx.hg,
        "_visible_dialog",
        lambda app, timeout: SimpleNamespace(
            handle=789, class_name=lambda: "#32770"
        ),
    )
    monkeypatch.setattr(
        nx.hg,
        "_save_dialog_as_xml",
        lambda handle, path: path.write_bytes(b"<xml/>")
    )
    monkeypatch.setattr(nx.hg, "_wait_for_export", lambda app, path, timeout: None)
    monkeypatch.setattr(nx.hg, "_post_window_message", lambda *args: None)

    result = nx._worker(request)
    assert result["ok"] is True
    assert result["editor"] == "schematic"
    assert result["diptrace_pid"] == 456
    assert result["desktop_name"] == "test_desktop"
