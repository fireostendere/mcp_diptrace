"""Synthetic timeout check: only the exporter-owned process tree is terminated."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from diptrace_mcp import native_xml_export as nx


def test_visible_project_dialog_is_returned_without_waiting_for_timeout(monkeypatch):
    dialog = SimpleNamespace(
        handle=42,
        window_text=lambda: "PCB Layout - board.dip",
        menu=lambda: None,
        is_visible=lambda: True,
        class_name=lambda: "TFMyMessage",
    )
    app = SimpleNamespace(windows=lambda **kw: [dialog], window=lambda **kw: dialog)
    monkeypatch.setattr(
        nx.hg.time,
        "sleep",
        lambda seconds: pytest.fail("active modal must not be polled until timeout"),
    )
    assert nx.hg._main_window(app, Path("board.dip"), 30) is dialog


def test_timeout_closes_job_containing_worker_and_editor(tmp_path, monkeypatch):
    events = []
    owned_job = SimpleNamespace(terminate_and_close=lambda: events.append("job_closed"))

    @contextmanager
    def launch(argv, *, job=None):
        assert job is owned_job
        assert "diptrace_mcp.native_xml_export" in argv
        yield SimpleNamespace(wait=lambda seconds: None, terminate=lambda code: events.append(code))

    @contextmanager
    def desktop(name):
        yield SimpleNamespace(launch=launch)

    monkeypatch.setattr(nx, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(nx, "validate_diptrace_directory", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr(nx.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(nx.hg, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(nx.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(nx.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(nx.hg, "HiddenDesktop", desktop)
    monkeypatch.setattr(
        nx, "KillOnCloseJob", SimpleNamespace(create=lambda: owned_job), raising=False
    )
    with pytest.raises(nx.hg.HeadlessGuiError, match="timed out"):
        nx._run_hidden(tmp_path, tmp_path / "source.dip", tmp_path / "result.dipxml", 1)
    assert events == [124, "job_closed"]


@pytest.mark.parametrize("dialog_class", ["TFMyMessage", "OtherDialog"])
def test_only_owned_message_ok_button_theme_is_stabilized(monkeypatch, dialog_class):
    theme = Mock(return_value=0)
    monkeypatch.setattr(
        nx.ctypes,
        "windll",
        SimpleNamespace(uxtheme=SimpleNamespace(SetWindowTheme=theme)),
        raising=False,
    )
    monkeypatch.setattr(nx.hg, "thread_desktop_name", lambda: "Owned")
    monkeypatch.setattr(nx.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(nx.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(nx.hg, "process_is_elevated", lambda: False)
    ok = SimpleNamespace(handle=10, class_name=lambda: "TButton", window_text=lambda: "OK")
    cancel = SimpleNamespace(handle=11, class_name=lambda: "TButton", window_text=lambda: "Cancel")
    window = SimpleNamespace(
        menu=lambda: None, class_name=lambda: dialog_class, descendants=lambda: [ok, cancel]
    )
    app = SimpleNamespace(
        start=lambda *a, **k: None, process=123, windows=lambda **k: [], kill=lambda **k: None
    )
    monkeypatch.setattr(nx.hg, "_pywinauto_application", lambda: lambda **kw: app)
    monkeypatch.setattr(nx.hg, "_main_window", lambda *a: window)
    monkeypatch.setattr(nx.shutil, "which", lambda name: None)
    posted = Mock()
    monkeypatch.setattr(nx.hg, "_post_window_message", posted)

    def stop_before_export(*args):
        raise nx.hg.HeadlessGuiError("unreviewed dialog")

    monkeypatch.setattr(nx, "_save_as", stop_before_export)
    result = nx._worker(
        {
            "source": "synthetic.dch",
            "output": "synthetic.dchxml",
            "root": ".",
            "desktop": "Owned",
            "station": "WinSta0",
            "session": 1,
            "timeout": 30,
        }
    )
    assert not result["ok"]
    posted.assert_not_called()
    if dialog_class == "TFMyMessage":
        theme.assert_called_once_with(10, "", "")
    else:
        theme.assert_not_called()
