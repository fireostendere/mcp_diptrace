from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import diptrace_mcp.bridge as bridge
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import SessionError

_SOURCE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm"><Board/></Source>\n'
)


def _controller(tmp_path: Path) -> bridge.BridgeController:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes(_SOURCE)
    return bridge.BridgeController(
        exchange,
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        ),
    )


def test_preview_summary_caches_valid_payload_and_exposes_inspected_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)
    sha = "a" * 64
    payload = {
        "available": True,
        "complete": True,
        "working_sha256": sha,
        "modified": False,
        "normalized_object_count": 1,
        "structural_element_count": 2,
        "object_count": 3,
        "changed_ids": [],
    }
    calls = 0

    def current() -> str:
        return sha

    def summary(_session_id: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return payload

    monkeypatch.setattr(controller, "current_sha256", current)
    monkeypatch.setattr(controller.store, "live_preview_summary", summary)

    assert controller.inspected_sha256() is None
    assert controller.preview_summary() is payload
    assert controller.preview_summary() is payload
    assert calls == 1
    assert controller.inspected_sha256() == sha


def test_preview_summary_fails_closed_on_exception_and_invalid_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)

    def explode() -> str:
        raise RuntimeError("preview exploded")

    monkeypatch.setattr(controller, "current_sha256", explode)
    failed = controller.preview_summary()
    assert failed["available"] is False
    assert failed["working_sha256"] is None
    assert "preview exploded" in failed["reason"]

    monkeypatch.setattr(controller, "current_sha256", lambda: "b" * 64)
    monkeypatch.setattr(
        controller.store,
        "live_preview_summary",
        lambda _session_id: {"available": True, "working_sha256": "NOT-A-SHA"},
    )
    invalid = controller.preview_summary()
    assert invalid["available"] is False
    assert invalid["reason"] == "invalid working_sha256 in preview summary"
    assert controller.inspected_sha256() is None


def test_finish_is_idempotent_and_reject_request_requires_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)
    finalized: list[tuple[object, ...]] = []
    rejected: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        controller.store,
        "finalize",
        lambda session_id, action, expected: finalized.append((session_id, action, expected))
        or {"status": action},
    )
    monkeypatch.setattr(
        controller.store,
        "read_metadata",
        lambda session_id: {"session_id": session_id, "status": "cached"},
    )
    monkeypatch.setattr(
        controller.store,
        "reject_finish_request",
        lambda session_id, message, expected_request_id: rejected.append(
            ("request", session_id, message, expected_request_id)
        ),
    )
    monkeypatch.setattr(
        controller.store,
        "reject_malformed_finish_request",
        lambda session_id, message, expected_control_sha256: rejected.append(
            ("control", session_id, message, expected_control_sha256)
        ),
    )

    assert controller.finish("cancel")["status"] == "cancel"
    assert controller.finish("cancel")["status"] == "cached"
    assert len(finalized) == 1

    controller.reject_request("bad", request_id="request-1")
    controller.reject_request("bad-control", control_sha256="c" * 64)
    assert rejected[0][-1] == "request-1"
    assert rejected[1][-1] == "c" * 64
    with pytest.raises(ValueError, match="control_sha256"):
        controller.reject_request("missing")


def test_bridge_text_and_request_validation_helpers(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge.os, "name", "posix")
    bridge._show_fatal("fatal message")
    assert "fatal message" in capsys.readouterr().err

    runtime_payload = bridge._fatal_error_payload(RuntimeError("boom"))
    assert runtime_payload["code"] == "bridge_runtime_error"
    domain_payload = bridge._fatal_error_payload(SessionError("no session"))
    assert domain_payload["code"] == "no_active_session"

    unavailable = bridge._preview_details_text("session-x", {"available": False})
    assert "Preview: unavailable/incomplete" in unavailable
    assert "working XML could not be parsed" in unavailable

    available = bridge._preview_details_text(
        "session-x",
        {
            "available": True,
            "complete": False,
            "modified": True,
            "normalized_object_count": 2,
            "structural_element_count": 3,
            "object_count": 5,
            "changed_ids": ["a", "b"],
        },
    )
    assert "Working XML: modified" in available
    assert "a, b" in available
    assert "incomplete/truncated" in available

    valid = {
        "request_id": "req",
        "action": "apply",
        "expected_sha256": "a" * 64,
        "requested_at": "2026-08-10T12:00:00Z",
    }
    assert bridge._valid_finish_request(valid) is True
    for update in (
        {"request_id": None},
        {"action": "erase"},
        {"expected_sha256": "a" * 63},
        {"expected_sha256": "g" * 64},
        {"requested_at": ""},
    ):
        assert bridge._valid_finish_request({**valid, **update}) is False


def test_show_fatal_uses_windows_message_box_and_falls_back_to_stderr(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    fake_ctypes = types.ModuleType("ctypes")
    fake_ctypes.windll = types.SimpleNamespace(  # type: ignore[attr-defined]
        user32=types.SimpleNamespace(
            MessageBoxW=lambda *args: calls.append(args),
        )
    )
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    monkeypatch.setattr(bridge.os, "name", "nt")

    bridge._show_fatal("windows fatal")
    assert calls == [(0, "windows fatal", "DipTrace MCP Bridge", 0x10)]
    assert capsys.readouterr().err == ""

    def fail_message_box(*_args: object) -> None:
        raise RuntimeError("GUI unavailable")

    fake_ctypes.windll.user32.MessageBoxW = fail_message_box  # type: ignore[attr-defined]
    bridge._show_fatal("fallback fatal")
    assert "fallback fatal" in capsys.readouterr().err


def test_headless_request_helper_success_rejection_and_missing_hash() -> None:
    class FakeController:
        def __init__(self) -> None:
            self.finished: list[tuple[str, str | None]] = []
            self.rejected: list[tuple[str, str | None, str | None]] = []
            self.fail = False

        def finish(self, action: str, expected: str | None) -> None:
            if self.fail:
                raise SessionError("stale")
            self.finished.append((action, expected))

        def reject_request(
            self,
            message: str,
            *,
            request_id: str | None = None,
            control_sha256: str | None = None,
        ) -> None:
            self.rejected.append((message, request_id, control_sha256))

    request = {
        "request_id": "req",
        "action": "cancel",
        "expected_sha256": "a" * 64,
        "requested_at": "now",
        "_control_sha256": "b" * 64,
    }
    controller = FakeController()
    assert bridge._handle_headless_request(controller, request) is True
    assert controller.finished == [("cancel", "a" * 64)]

    controller.fail = True
    assert bridge._handle_headless_request(controller, request) is False
    assert controller.rejected[-1][1] == "req"

    malformed = {**request, "action": "erase"}
    controller.fail = False
    assert bridge._handle_headless_request(controller, malformed) is False
    assert controller.rejected[-1][2] == "b" * 64

    with pytest.raises(ValueError, match="control hash"):
        bridge._handle_headless_request(controller, {"action": "erase"})


def test_fatal_log_is_bounded_and_write_failures_are_non_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes(_SOURCE)

    log_path = bridge._write_fatal_log(exchange, OSError("disk unavailable"))
    assert log_path == tmp_path / bridge.BRIDGE_ERROR_LOG_NAME
    assert log_path is not None
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["error"]["code"] == "bridge_io_error"

    monkeypatch.setattr(bridge, "BRIDGE_ERROR_LOG_MAX_BYTES", 512)
    long_path = bridge._write_fatal_log(exchange, RuntimeError("x" * 10_000))
    assert long_path is not None
    assert long_path.stat().st_size <= 512
    bounded = json.loads(long_path.read_text(encoding="utf-8"))
    assert bounded["error"]["details"]["bridge_log_truncated"] is True

    def fail_write(_path: Path, _data: bytes) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(bridge, "atomic_write_bytes", fail_write)
    assert bridge._write_fatal_log(exchange, RuntimeError("boom")) is None


def test_timeout_helpers_cover_defaults_overrides_and_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert bridge._positive_timeout("3") == 3
    for value, message in (("bad", "integer"), ("0", "greater than zero")):
        with pytest.raises(argparse.ArgumentTypeError, match=message):
            bridge._positive_timeout(value)

    monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)
    assert bridge._timeout_from_environment() == bridge.DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "7")
    assert bridge._timeout_from_environment() == 7
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "invalid")
    with pytest.raises(bridge.ConfigurationError, match="DIPTRACE_MCP_SESSION_TIMEOUT"):
        bridge._timeout_from_environment()

    args = bridge._build_parser().parse_args(["exchange.xml", "--headless", "--timeout", "9"])
    assert args.exchange_file == "exchange.xml"
    assert args.headless is True
    assert args.timeout == 9


def test_run_headless_handles_immediate_request_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {
        "request_id": "req",
        "action": "cancel",
        "expected_sha256": "a" * 64,
        "requested_at": "now",
        "_control_sha256": "b" * 64,
    }

    class FakeController:
        def __init__(self, requests: list[dict[str, Any] | None]) -> None:
            self.requests = requests
            self.finished: list[tuple[str, str | None]] = []

        def poll_request(self) -> dict[str, Any] | None:
            return self.requests.pop(0) if self.requests else None

        def finish(self, action: str, expected: str | None = None) -> None:
            self.finished.append((action, expected))

        def reject_request(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("unexpected rejection")

    immediate = FakeController([request])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)
    assert bridge.run_headless(immediate, 1) == 0
    assert immediate.finished == [("cancel", "a" * 64)]

    values = iter((0.0, 2.0))
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(values))
    expired = FakeController([None])
    assert bridge.run_headless(expired, 1) == 2
    assert expired.finished == [("cancel", None)]


def test_bridge_main_headless_success_and_error_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes(_SOURCE)

    class FakeSettings:
        def resolve_allowed_path(self, value: str, *, must_exist: bool) -> Path:
            assert value == str(exchange)
            assert must_exist is True
            return exchange

    fake_settings = FakeSettings()
    monkeypatch.setattr(
        bridge.Settings,
        "from_env",
        classmethod(lambda _cls: fake_settings),
    )
    fake_controller = object()
    monkeypatch.setattr(bridge, "BridgeController", lambda *_args: fake_controller)
    monkeypatch.setattr(
        bridge,
        "run_headless",
        lambda controller, timeout: 17 if controller is fake_controller and timeout == 3 else 99,
    )
    assert bridge.main([str(exchange), "--headless", "--timeout", "3"]) == 17

    def fail_settings(_cls: type[Settings]) -> Settings:
        raise RuntimeError("configuration exploded")

    monkeypatch.setattr(bridge.Settings, "from_env", classmethod(fail_settings))
    assert bridge.main([str(exchange), "--headless"]) == 1
    assert "configuration exploded" in capsys.readouterr().err


def _install_fake_tk(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[Any]]:
    roots: list[Any] = []
    widgets: list[Any] = []
    tkinter = types.ModuleType("tkinter")
    messagebox = types.ModuleType("tkinter.messagebox")
    messagebox.askyesno = lambda *_args, **_kwargs: True  # type: ignore[attr-defined]

    class Variable:
        def __init__(self, *, value: str = "") -> None:
            self.value = value

        def set(self, value: str) -> None:
            self.value = value

    class Widget:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            self.command = kwargs.get("command")
            self.state = kwargs.get("state")
            widgets.append(self)

        def pack(self, **_kwargs: object) -> None:
            return None

        def configure(self, **kwargs: object) -> None:
            if "state" in kwargs:
                self.state = kwargs["state"]

    class Root(Widget):
        def __init__(self) -> None:
            super().__init__()
            self.callbacks: list[Any] = []
            self.protocols: dict[str, Any] = {}
            self.destroyed = False
            roots.append(self)

        def title(self, _value: str) -> None:
            return None

        def resizable(self, _width: bool, _height: bool) -> None:
            return None

        def protocol(self, name: str, callback: Any) -> None:
            self.protocols[name] = callback

        def after(self, _delay: int, callback: Any) -> None:
            self.callbacks.append(callback)

        def destroy(self) -> None:
            self.destroyed = True

        def mainloop(self) -> None:
            iterations = 0
            while self.callbacks and not self.destroyed:
                iterations += 1
                assert iterations < 20
                callback = self.callbacks.pop(0)
                callback()

    tkinter.Tk = Root  # type: ignore[attr-defined]
    tkinter.StringVar = Variable  # type: ignore[attr-defined]
    tkinter.Frame = Widget  # type: ignore[attr-defined]
    tkinter.Label = Widget  # type: ignore[attr-defined]
    tkinter.Button = Widget  # type: ignore[attr-defined]
    tkinter.messagebox = messagebox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tkinter", tkinter)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", messagebox)
    return roots, widgets


def test_run_gui_processes_valid_apply_request_with_fake_tk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots, widgets = _install_fake_tk(monkeypatch)

    class Controller:
        session_id = "session-gui"
        can_apply = True

        def __init__(self) -> None:
            self.finished = False
            self.finishes: list[tuple[str, str | None]] = []
            self.requested = False

        def preview_summary(self) -> dict[str, Any]:
            return {
                "available": True,
                "complete": True,
                "modified": True,
                "normalized_object_count": 2,
                "structural_element_count": 1,
                "object_count": 3,
                "changed_ids": ["component_1"],
            }

        def inspected_sha256(self) -> str:
            return "a" * 64

        def poll_request(self) -> dict[str, Any] | None:
            if self.requested:
                return None
            self.requested = True
            return {
                "request_id": "req-gui",
                "action": "apply",
                "expected_sha256": "a" * 64,
                "requested_at": "now",
                "_control_sha256": "b" * 64,
            }

        def finish(self, action: str, expected: str | None = None) -> dict[str, str]:
            self.finishes.append((action, expected))
            self.finished = True
            return {"status": action}

        def reject_request(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("valid request must not be rejected")

    controller = Controller()
    monkeypatch.setattr(bridge.time, "monotonic", lambda: 0.0)
    assert bridge.run_gui(controller, 10) == 0
    assert controller.finishes == [("apply", "a" * 64)]
    assert roots and roots[0].destroyed is True
    assert any(widget.state == "normal" for widget in widgets)
    roots[0].protocols["WM_DELETE_WINDOW"]()


def test_run_gui_rejects_malformed_request_then_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots, _widgets = _install_fake_tk(monkeypatch)
    monotonic = iter((0.0, 0.2, 2.0))
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(monotonic))

    class Controller:
        session_id = "session-read-only"
        can_apply = False

        def __init__(self) -> None:
            self.finished = False
            self.finishes: list[tuple[str, str | None]] = []
            self.rejections: list[tuple[str, str | None]] = []
            self.polls = 0

        def preview_summary(self) -> dict[str, Any]:
            return {"available": False, "reason": "synthetic parse failure"}

        def inspected_sha256(self) -> None:
            return None

        def poll_request(self) -> dict[str, Any] | None:
            self.polls += 1
            if self.polls == 1:
                return {
                    "request_id": "broken",
                    "action": "erase",
                    "expected_sha256": "a" * 64,
                    "requested_at": "now",
                    "_control_sha256": "c" * 64,
                }
            return None

        def finish(self, action: str, expected: str | None = None) -> dict[str, str]:
            self.finishes.append((action, expected))
            self.finished = True
            return {"status": action}

        def reject_request(
            self,
            message: str,
            *,
            request_id: str | None = None,
            control_sha256: str | None = None,
        ) -> None:
            self.rejections.append((message, control_sha256 or request_id))

    controller = Controller()
    assert bridge.run_gui(controller, 1) == 0
    assert controller.rejections == [("Unknown finish action: erase", "c" * 64)]
    assert controller.finishes == [("cancel", None)]
    assert roots[0].destroyed is True
