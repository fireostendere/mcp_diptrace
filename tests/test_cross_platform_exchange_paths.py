from __future__ import annotations

from pathlib import Path

import pytest

import diptrace_mcp.sessions as sessions_module
from diptrace_mcp.errors import SessionError
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.xml_document import sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def _working_sha256(store: SessionStore, session_id: str) -> str:
    return sha256_bytes(store.working_path(session_id).read_bytes())


def test_windows_exchange_path_maps_to_wsl_without_metadata_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mount_root = tmp_path / "mnt"
    allowed = mount_root / "c" / "Users" / "fireo"
    exchange = allowed / "AppData" / "Local" / "Temp" / "DipTrace" / "plugin_exchange.xml"
    exchange.parent.mkdir(parents=True)
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setenv("DIPTRACE_MCP_WSL_MOUNT_ROOT", str(mount_root))

    store = SessionStore(
        tmp_path / "state",
        10_000_000,
        allowed_roots=(allowed,),
    )
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])
    windows_path = (
        r"C:\Users\fireo\AppData\Local\Temp\DipTrace\plugin_exchange.xml"
    )
    store.update_metadata(
        session_id,
        exchange_path=windows_path,
        exchange_path_platform="windows",
    )

    working_path = store.working_path(session_id)
    working = working_path.read_bytes().replace(
        b"<Value>10k</Value>",
        b"<Value>22k</Value>",
    )
    working_path.write_bytes(working)
    expected_sha256 = _working_sha256(store, session_id)

    request = store.request_finish("apply", expected_sha256)

    pending_metadata = store.read_metadata(session_id)
    assert pending_metadata["exchange_path"] == windows_path
    assert pending_metadata["exchange_path_platform"] == "windows"

    result = store.finalize(
        session_id,
        "apply",
        str(request["expected_sha256"]),
    )

    assert result["status"] == "applied"
    assert exchange.read_bytes() == working
    assert store.read_metadata(session_id)["exchange_path"] == windows_path


def test_windows_runtime_keeps_native_windows_path() -> None:
    raw_path = r"C:\Users\fireo\AppData\Local\Temp\DipTrace\plugin_exchange.xml"

    resolved = sessions_module._exchange_path_for_runtime(
        raw_path,
        "windows",
        runtime_os_name="nt",
        runtime_platform="win32",
    )

    assert str(resolved) == raw_path


def test_windows_runtime_rejects_wsl_path_labeled_as_windows() -> None:
    with pytest.raises(SessionError, match="does not match its recorded platform") as caught:
        sessions_module._exchange_path_for_runtime(
            "/mnt/c/Users/fireo/AppData/Local/Temp/DipTrace/plugin_exchange.xml",
            "windows",
            runtime_os_name="nt",
            runtime_platform="win32",
        )

    assert caught.value.payload.code == "session_state_invalid"


def test_request_finish_rejects_platform_path_mismatch_before_control_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    exchange = allowed / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(
        tmp_path / "state",
        10_000_000,
        allowed_roots=(allowed,),
    )
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setenv("DIPTRACE_MCP_WSL_MOUNT_ROOT", str(tmp_path / "mnt"))
    store.update_metadata(
        session_id,
        exchange_path="/mnt/c/Users/fireo/plugin_exchange.xml",
        exchange_path_platform="windows",
    )

    with pytest.raises(SessionError, match="does not match its recorded platform") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "session_state_invalid"
    assert not store.control_path(session_id).exists()
    assert exchange.read_bytes() == (FIXTURES / "pcb.xml").read_bytes()


def test_new_session_records_exchange_path_platform(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    exchange = allowed / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(
        tmp_path / "state",
        10_000_000,
        allowed_roots=(allowed,),
    )

    metadata = store.create(exchange)

    assert metadata["exchange_path_platform"] == sessions_module._current_exchange_path_platform()
