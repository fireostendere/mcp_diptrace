from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

import diptrace_mcp.bridge as bridge
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import ConfigurationError, SessionError

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


def test_bridge_timeout_helpers_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert bridge._positive_timeout("1") == 1
    with pytest.raises(bridge.argparse.ArgumentTypeError, match="integer"):
        bridge._positive_timeout("x")
    with pytest.raises(bridge.argparse.ArgumentTypeError, match="greater than zero"):
        bridge._positive_timeout("0")

    monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)
    assert bridge._timeout_from_environment() == bridge.DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "17")
    assert bridge._timeout_from_environment() == 17
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "bad")
    with pytest.raises(ConfigurationError, match="DIPTRACE_MCP_SESSION_TIMEOUT"):
        bridge._timeout_from_environment()


def test_run_headless_handles_immediate_delayed_and_timeout_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = {
        "request_id": "req",
        "action": "cancel",
        "expected_sha256": "a" * 64,
        "requested_at": "now",
        "_control_sha256": "b" * 64,
    }

    class Controller:
        def __init__(self, requests: list[dict[str, Any] | None]) -> None:
            self.requests = list(requests)
            self.finished: list[tuple[str, str | None]] = []

        def poll_request(self) -> dict[str, Any] | None:
            return self.requests.pop(0) if self.requests else None

        def finish(self, action: str, expected: str | None = None) -> None:
            self.finished.append((action, expected))

        def reject_request(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("request should not be rejected")

    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)
    immediate = Controller([valid])
    assert bridge.run_headless(immediate, 10) == 0
    assert immediate.finished == [("cancel", "a" * 64)]

    times = iter([0.0, 0.0, 0.1, 0.2, 0.3])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(times))
    delayed = Controller([None, valid])
    assert bridge.run_headless(delayed, 1) == 0

    times = iter([0.0, 2.0])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(times))
    timed_out = Controller([None])
    assert bridge.run_headless(timed_out, 1) == 2
    assert timed_out.finished == [("cancel", None)]


def _install_fake_tk(monkeypatch: pytest.MonkeyPatch, *, close_on_mainloop: bool = False) -> Any:
    module = types.ModuleType("tkinter")
    roots: list[Any] = []

    class Variable:
        def __init__(self, value: object = None) -> None:
            self.value = value

        def set(self, value: object) -> None:
            self.value = value

    class Widget:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            self.command = kwargs.get("command")
            self.state = kwargs.get("state")

        def pack(self, **_kwargs: object) -> None:
            return None

        def configure(self, **kwargs: object) -> None:
            if "state" in kwargs:
                self.state = kwargs["state"]

    class Root(Widget):
        def __init__(self) -> None:
            super().__init__()
            self.callbacks: list[Any] = []
            self.protocol_callback: Any = None
            self.destroyed = False
            roots.append(self)

        def title(self, _value: str) -> None:
            return None

        def resizable(self, *_args: object) -> None:
            return None

        def protocol(self, _name: str, callback: Any) -> None:
            self.protocol_callback = callback

        def after(self, _delay: int, callback: Any) -> None:
            self.callbacks.append(callback)

        def destroy(self) -> None:
            self.destroyed = True

        def mainloop(self) -> None:
            if close_on_mainloop and self.protocol_callback is not None:
                self.protocol_callback()
                return
            guard = 0
            while self.callbacks and not self.destroyed and guard < 8:
                callback = self.callbacks.pop(0)
                callback()
                guard += 1

    messagebox = types.SimpleNamespace(askyesno=lambda *_args: True)
    module.Tk = Root  # type: ignore[attr-defined]
    module.StringVar = Variable  # type: ignore[attr-defined]
    module.Frame = Widget  # type: ignore[attr-defined]
    module.Label = Widget  # type: ignore[attr-defined]
    module.Button = Widget  # type: ignore[attr-defined]
    module.messagebox = messagebox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tkinter", module)
    return roots


def test_run_gui_processes_valid_request_and_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    roots = _install_fake_tk(monkeypatch)

    class Controller:
        session_id = "session"
        can_apply = True
        finished = False

        def __init__(self) -> None:
            self.actions: list[tuple[str, str | None]] = []

        def preview_summary(self) -> dict[str, Any]:
            return {
                "available": True,
                "complete": True,
                "modified": True,
                "normalized_object_count": 1,
                "structural_element_count": 2,
                "object_count": 3,
                "changed_ids": ["obj"],
            }

        def poll_request(self) -> dict[str, Any]:
            return {
                "request_id": "req",
                "action": "apply",
                "expected_sha256": "a" * 64,
                "requested_at": "now",
                "_control_sha256": "b" * 64,
            }

        def finish(self, action: str, expected: str | None = None) -> None:
            self.actions.append((action, expected))
            self.finished = True

        def reject_request(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("unexpected rejection")

        def inspected_sha256(self) -> str:
            return "a" * 64

    controller = Controller()
    assert bridge.run_gui(controller, 10) == 0
    assert controller.actions == [("apply", "a" * 64)]
    assert roots[0].destroyed is True


def test_run_gui_rejects_malformed_then_cancels_on_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_tk(monkeypatch, close_on_mainloop=True)

    class Controller:
        session_id = "session"
        can_apply = False
        finished = False

        def __init__(self) -> None:
            self.actions: list[str] = []

        def preview_summary(self) -> dict[str, Any]:
            return {"available": False, "reason": "none"}

        def poll_request(self) -> None:
            return None

        def finish(self, action: str, _expected: str | None = None) -> None:
            self.actions.append(action)
            self.finished = True

        def reject_request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def inspected_sha256(self) -> None:
            return None

    controller = Controller()
    assert bridge.run_gui(controller, 10) == 0
    assert controller.actions == ["cancel"]


def test_run_gui_rejects_malformed_control_and_recovers_finish_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_tk(monkeypatch)
    requests: list[dict[str, Any]] = [
        {
            "request_id": "req-bad",
            "action": "erase",
            "expected_sha256": "a" * 64,
            "requested_at": "now",
            "_control_sha256": "b" * 64,
        },
        {
            "request_id": "req-good",
            "action": "cancel",
            "expected_sha256": "a" * 64,
            "requested_at": "now",
            "_control_sha256": "c" * 64,
        },
        {
            "request_id": "req-good-2",
            "action": "cancel",
            "expected_sha256": "a" * 64,
            "requested_at": "now",
            "_control_sha256": "d" * 64,
        },
    ]

    class Controller:
        session_id = "session"
        can_apply = True
        finished = False

        def __init__(self) -> None:
            self.rejections: list[tuple[str, dict[str, Any]]] = []
            self.fail_once = True

        def preview_summary(self) -> dict[str, Any]:
            return {
                "available": True,
                "complete": False,
                "modified": False,
                "normalized_object_count": 0,
                "structural_element_count": 0,
                "object_count": 0,
                "changed_ids": [],
            }

        def poll_request(self) -> dict[str, Any] | None:
            return requests.pop(0) if requests else None

        def finish(self, _action: str, _expected: str | None = None) -> None:
            if self.fail_once:
                self.fail_once = False
                raise SessionError("stale")
            self.finished = True

        def reject_request(self, message: str, **kwargs: Any) -> None:
            self.rejections.append((message, kwargs))

        def inspected_sha256(self) -> str:
            return "a" * 64

    controller = Controller()
    assert bridge.run_gui(controller, 10) == 0
    assert "Unknown finish action" in controller.rejections[0][0]
    assert controller.rejections[1][1]["request_id"] == "req-good"


def test_bridge_main_headless_success_and_error_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes(_SOURCE)
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    monkeypatch.setattr(bridge.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(bridge, "run_headless", lambda _controller, timeout: 7 if timeout == 3 else 8)
    assert bridge.main([str(exchange), "--headless", "--timeout", "3"]) == 7

    monkeypatch.setattr(
        settings,
        "resolve_allowed_path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SessionError("bad exchange")),
    )
    assert bridge.main([str(exchange), "--headless"]) == 1
    assert "bad exchange" in capsys.readouterr().err
