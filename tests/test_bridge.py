from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from diptrace_mcp import bridge
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS, Settings
from diptrace_mcp.errors import SessionError

_SOURCE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm"><Board/></Source>\n'
)
_MODIFIED = _SOURCE.replace(b"</Source>", b"<!-- changed -->\n</Source>")
_COMPONENT_LIBRARY_SOURCE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Library Type="DipTrace-ComponentLibrary" Version="4.3.0.3" Units="mm"></Library>\n'
)


def _controller(tmp_path: Path) -> tuple[bridge.BridgeController, Path]:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes(_SOURCE)
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    return bridge.BridgeController(exchange, settings), exchange


def _library_controller(tmp_path: Path) -> tuple[bridge.BridgeController, Path]:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes(_COMPONENT_LIBRARY_SOURCE)
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    return bridge.BridgeController(exchange, settings), exchange


def test_bridge_timeout_default_is_shared_by_cli_capabilities_and_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)

    args = bridge._build_parser().parse_args(["exchange.xml"])
    limits = get_capabilities().limits
    usage = (Path(__file__).parents[1] / "docs" / "USAGE.md").read_text(
        encoding="utf-8"
    )

    assert args.timeout is None
    assert bridge._timeout_from_environment() == DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    assert (
        limits["default_live_session_timeout_seconds"]
        == DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    )
    assert (
        f"| `DIPTRACE_MCP_SESSION_TIMEOUT` | "
        f"`{DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS}` |"
    ) in usage


def test_bridge_timeout_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "2400")

    args = bridge._build_parser().parse_args(["exchange.xml"])

    assert args.timeout is None
    assert bridge._timeout_from_environment() == 2400


def test_bridge_timeout_cli_override_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "2400")

    args = bridge._build_parser().parse_args(
        ["exchange.xml", "--timeout", "45"]
    )

    assert args.timeout == 45


@pytest.mark.parametrize(
    "arguments",
    [
        ["exchange.xml", "--timeout", "-1"],
        ["exchange.xml", "--timeout", "not-an-integer"],
    ],
)
def test_bridge_cli_timeout_rejects_non_positive_or_non_integer_values(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        bridge._build_parser().parse_args(arguments)

    assert exc_info.value.code == 2


@pytest.mark.parametrize("environment", ["0", "not-an-integer"])
def test_bridge_environment_timeout_raises_typed_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", environment)

    with pytest.raises(
        bridge.ConfigurationError,
        match="DIPTRACE_MCP_SESSION_TIMEOUT",
    ):
        bridge._timeout_from_environment()


def test_headless_bridge_applies_valid_control_request(tmp_path: Path) -> None:
    controller, exchange = _controller(tmp_path)
    controller.working_path.write_bytes(_MODIFIED)
    request = controller.store.request_finish("apply", controller.current_sha256())

    assert controller.is_modified() is True
    assert controller.current_sha256() == request["expected_sha256"]
    assert bridge.run_headless(controller, timeout=1) == 0
    assert exchange.read_bytes() == _MODIFIED
    assert controller.store.active_metadata() is None
    assert controller.finish("cancel")["status"] == "applied"


def test_controller_working_sha_uses_stable_store_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _exchange = _controller(tmp_path)
    working_path = controller.working_path
    real_read_bytes = Path.read_bytes

    def reject_unbounded_working_read(path: Path) -> bytes:
        if path == working_path:
            raise AssertionError("working XML must not use Path.read_bytes")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_working_read)

    assert controller.current_sha256() == hashlib.sha256(_SOURCE).hexdigest()
    assert controller.is_modified() is False


def test_controller_working_sha_refuses_oversized_file(tmp_path: Path) -> None:
    controller, _exchange = _controller(tmp_path)
    controller.store.max_document_bytes = len(_SOURCE) - 1

    with pytest.raises(SessionError, match="document-size limit") as caught:
        controller.current_sha256()

    assert caught.value.payload.code == "document_too_large"


def test_controller_working_sha_refuses_redirected_file(tmp_path: Path) -> None:
    controller, _exchange = _controller(tmp_path)
    working_path = controller.working_path
    redirected = tmp_path / "redirected-working.xml"
    redirected.write_bytes(working_path.read_bytes())
    working_path.unlink()
    try:
        working_path.symlink_to(redirected)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(SessionError, match="redirected") as caught:
        controller.is_modified()

    assert caught.value.payload.code == "path_access_denied"


def test_headless_bridge_cancels_without_replacing_exchange(tmp_path: Path) -> None:
    controller, exchange = _controller(tmp_path)
    controller.working_path.write_bytes(_MODIFIED)
    controller.store.request_finish("cancel")

    assert bridge.run_headless(controller, timeout=1) == 0
    assert exchange.read_bytes() == _SOURCE
    assert controller.store.read_metadata(controller.session_id)["status"] == "cancelled"


def test_library_bridge_is_read_only_even_for_direct_control_file(
    tmp_path: Path,
) -> None:
    controller, exchange = _library_controller(tmp_path)
    controller.store.control_path(controller.session_id).write_text(
        json.dumps(
            {
                "action": "apply",
                "expected_sha256": controller.current_sha256(),
            }
        ),
        encoding="utf-8",
    )

    assert controller.can_apply is False
    assert bridge.run_headless(controller, timeout=1) == 2
    assert exchange.read_bytes() == _COMPONENT_LIBRARY_SOURCE
    metadata = controller.store.read_metadata(controller.session_id)
    assert metadata["status"] == "cancelled"
    assert metadata["last_error"] == "Malformed finish request"


def test_headless_bridge_timeout_cancels_and_returns_timeout_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, exchange = _controller(tmp_path)
    moments = iter([10.0, 10.0, 12.0])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)

    assert bridge.run_headless(controller, timeout=1) == 2
    assert exchange.read_bytes() == _SOURCE
    assert controller.store.read_metadata(controller.session_id)["status"] == "cancelled"


def test_headless_bridge_rejects_unknown_control_action_before_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _ = _controller(tmp_path)
    controller.store.request_finish("cancel")
    control = controller.store.control_path(controller.session_id)
    tampered = json.loads(control.read_text(encoding="utf-8"))
    tampered["action"] = "erase"
    control.write_text(json.dumps(tampered), encoding="utf-8")
    moments = iter([20.0, 20.0, 22.0])
    monkeypatch.setattr(bridge.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)

    assert bridge.run_headless(controller, timeout=1) == 2
    metadata = controller.store.read_metadata(controller.session_id)
    assert metadata["status"] == "cancelled"
    assert metadata["last_error"] == "Unknown finish action: erase"
    assert not controller.store.control_path(controller.session_id).exists()


def test_bridge_main_logs_typed_environment_failure_next_to_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes(_SOURCE)
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "unbounded")
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))

    assert bridge.main(["--headless", str(exchange)]) == 1

    output = capsys.readouterr()
    log = json.loads((tmp_path / bridge.BRIDGE_ERROR_LOG_NAME).read_text(encoding="utf-8"))
    assert "DIPTRACE_MCP_SESSION_TIMEOUT" in output.err
    assert log["error"]["code"] == "configuration_error"
    assert log["error"]["recoverable"] is False


def test_bridge_main_logs_typed_document_failure_next_to_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_text("<Source>", encoding="utf-8")
    monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))

    assert bridge.main(["--headless", "--timeout", "1", str(exchange)]) == 1

    capsys.readouterr()
    log = json.loads((tmp_path / bridge.BRIDGE_ERROR_LOG_NAME).read_text(encoding="utf-8"))
    assert log["error"]["code"] == "schema_parse_error"
    assert "Invalid XML" in log["error"]["message"]


def test_bridge_main_rejects_stale_hash_then_cancels_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, exchange = _controller(tmp_path)
    controller.store.request_finish(
        "apply",
        controller.current_sha256(),
    )
    controller.working_path.write_bytes(_MODIFIED)
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(bridge, "BridgeController", lambda _path, _settings: controller)

    assert bridge.main(["--headless", "--timeout", "1", str(exchange)]) == 2

    metadata = controller.store.read_metadata(controller.session_id)
    assert metadata["status"] == "cancelled"
    assert metadata["last_error"] == "Working XML changed after the finish request"
    assert not controller.store.control_path(controller.session_id).exists()
    assert exchange.read_bytes() == _SOURCE


def test_bridge_main_does_not_log_beside_an_unresolved_exchange_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selected_parent = tmp_path / "caller-selected"
    missing = selected_parent / "missing.xml"
    selected_parent.mkdir()
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))

    assert bridge.main(["--headless", "--timeout", "1", str(missing)]) == 1

    capsys.readouterr()
    assert not (selected_parent / bridge.BRIDGE_ERROR_LOG_NAME).exists()


def test_bridge_fatal_payload_types_non_domain_io_errors() -> None:
    payload = bridge._fatal_error_payload(OSError("disk unavailable"))

    assert payload["code"] == "bridge_io_error"
    assert payload["message"] == "disk unavailable"
    assert payload["recoverable"] is False


def test_bridge_fatal_log_failure_never_masks_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_write(_path: Path, _data: bytes) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(bridge, "atomic_write_bytes", refuse_write)

    assert bridge._write_fatal_log(tmp_path / "exchange.xml", SessionError("original")) is None


def test_bridge_fatal_log_is_bounded_and_discloses_truncation(tmp_path: Path) -> None:
    log_path = bridge._write_fatal_log(
        tmp_path / "exchange.xml",
        SessionError("unsafe-control-character\n" * 100_000),
    )

    assert log_path is not None
    data = log_path.read_bytes()
    record = json.loads(data)
    assert len(data) <= bridge.BRIDGE_ERROR_LOG_MAX_BYTES
    assert record["error"]["code"] == "no_active_session"
    assert record["error"]["details"]["bridge_log_truncated"] is True
    assert record["error"]["details"]["original_serialized_bytes"] > len(data)


def test_committed_headless_smoke_script_runs_cross_process(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_bridge_headless.py")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "headless bridge applied controlled XML" in result.stdout
