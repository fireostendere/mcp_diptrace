from __future__ import annotations

import os
from pathlib import Path

import pytest

import diptrace_mcp.sessions as sessions_module
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import SessionError
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.xml_document import sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def _store_and_exchange(tmp_path: Path) -> tuple[SessionStore, Path, str]:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    exchange = allowed / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())
    store = SessionStore(
        tmp_path / "state",
        10_000_000,
        allowed_roots=(allowed,),
    )
    metadata = store.create(exchange)
    return store, exchange, str(metadata["session_id"])


def _working_sha256(store: SessionStore, session_id: str) -> str:
    return sha256_bytes(store.working_path(session_id).read_bytes())


def test_session_create_refuses_exchange_above_bounded_read_limit(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    exchange = allowed / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())
    store = SessionStore(
        tmp_path / "state",
        max_document_bytes=16,
        allowed_roots=(allowed,),
    )

    with pytest.raises(SessionError, match="document-size limit") as caught:
        store.create(exchange)

    assert caught.value.payload.code == "document_too_large"
    assert store.active_metadata() is None


def test_apply_refuses_store_without_allowed_root_policy(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])

    with pytest.raises(SessionError, match="configured allowed roots") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "path_access_denied"
    assert not store.control_path(session_id).exists()


@pytest.mark.parametrize("expected_sha256", [None, "0" * 64])
def test_apply_request_requires_current_caller_sha_before_control_publish(
    tmp_path: Path,
    expected_sha256: str | None,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()

    with pytest.raises(SessionError) as caught:
        store.request_finish("apply", expected_sha256)

    assert caught.value.payload.code in {"confirmation_required", "sha256_mismatch"}
    assert exchange.read_bytes() == original
    assert not store.control_path(session_id).exists()
    metadata = store.read_metadata(session_id)
    assert metadata["status"] == "active"
    assert "finish_requested" not in metadata


def test_service_rejects_stale_apply_sha_without_publishing_control(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    exchange = allowed / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    settings = Settings(
        workspace=allowed,
        allowed_roots=(allowed,),
        state_dir=tmp_path / "state",
    )
    service = DipTraceService(settings)
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])

    with pytest.raises(SessionError, match="changed after it was inspected") as caught:
        service.finish_live_session("apply", "0" * 64)

    assert caught.value.payload.code == "sha256_mismatch"
    assert not service.sessions.control_path(session_id).exists()


def test_apply_request_refuses_metadata_path_outside_allowed_roots(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()
    outside = tmp_path / "outside.xml"
    outside.write_bytes(original)
    store.update_metadata(session_id, exchange_path=str(outside))

    with pytest.raises(SessionError, match="outside allowed roots") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "path_access_denied"
    assert exchange.read_bytes() == original
    assert outside.read_bytes() == original
    assert not store.control_path(session_id).exists()


def test_apply_request_refuses_redirected_exchange_path(tmp_path: Path) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()
    alternate = exchange.with_name("alternate.xml")
    alternate.write_bytes(original)
    exchange.unlink()
    try:
        exchange.symlink_to(alternate)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(SessionError, match="redirected") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "path_access_denied"
    assert alternate.read_bytes() == original
    assert not store.control_path(session_id).exists()


def test_apply_request_refuses_multiply_linked_exchange_file(tmp_path: Path) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    linked = exchange.with_name("second-name.xml")
    try:
        os.link(exchange, linked)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable: {exc}")

    with pytest.raises(SessionError, match="non-linked regular file") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "path_access_denied"
    assert not store.control_path(session_id).exists()


def test_apply_request_refuses_externally_changed_exchange_file(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    external = exchange.read_bytes().replace(b"<Value>10k</Value>", b"<Value>47k</Value>")
    exchange.write_bytes(external)

    with pytest.raises(SessionError, match="changed after the live session started") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "sha256_mismatch"
    assert exchange.read_bytes() == external
    assert not store.control_path(session_id).exists()


def test_apply_request_refuses_tampered_original_hash_metadata(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()
    store.update_metadata(session_id, original_sha256="0" * 64)

    with pytest.raises(SessionError, match="captured original XML") as caught:
        store.request_finish("apply", _working_sha256(store, session_id))

    assert caught.value.payload.code == "session_state_invalid"
    assert exchange.read_bytes() == original
    assert not store.control_path(session_id).exists()


def test_finalize_requires_expected_working_sha_before_direct_apply(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()

    with pytest.raises(SessionError, match="finish request is required") as caught:
        store.finalize(session_id, "apply")

    assert caught.value.payload.code == "confirmation_required"
    assert exchange.read_bytes() == original
    assert store.read_metadata(session_id)["status"] == "active"


def test_finalize_rechecks_exchange_binding_after_control_publish(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    working = store.working_path(session_id)
    working.write_bytes(
        working.read_bytes().replace(b"<Value>10k</Value>", b"<Value>22k</Value>")
    )
    expected_sha256 = _working_sha256(store, session_id)
    request = store.request_finish("apply", expected_sha256)
    external = exchange.read_bytes() + b"\n"
    exchange.write_bytes(external)

    with pytest.raises(SessionError, match="changed after the live session started"):
        store.finalize(session_id, "apply", str(request["expected_sha256"]))

    assert exchange.read_bytes() == external
    assert store.read_metadata(session_id)["status"] == "active"
    assert store.control_path(session_id).exists()


def test_finalize_rechecks_metadata_path_inside_allowed_roots(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    original = exchange.read_bytes()
    expected_sha256 = _working_sha256(store, session_id)
    request = store.request_finish("apply", expected_sha256)
    outside = tmp_path / "outside.xml"
    outside.write_bytes(original)
    store.update_metadata(session_id, exchange_path=str(outside))

    with pytest.raises(SessionError, match="outside allowed roots") as caught:
        store.finalize(session_id, "apply", str(request["expected_sha256"]))

    assert caught.value.payload.code == "path_access_denied"
    assert exchange.read_bytes() == original
    assert outside.read_bytes() == original
    assert store.read_metadata(session_id)["status"] == "active"


def test_valid_bound_apply_replaces_exchange_with_exact_working_bytes(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    working_path = store.working_path(session_id)
    working = working_path.read_bytes().replace(
        b"<Value>10k</Value>",
        b"<Value>22k</Value>",
    )
    working_path.write_bytes(working)
    expected_sha256 = sha256_bytes(working)

    request = store.request_finish("apply", expected_sha256)
    result = store.finalize(session_id, "apply", str(request["expected_sha256"]))

    assert result["status"] == "applied"
    assert exchange.read_bytes() == working
    assert sha256_bytes(exchange.read_bytes()) == expected_sha256


def test_finalize_detects_non_exact_atomic_exchange_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, exchange, session_id = _store_and_exchange(tmp_path)
    expected_sha256 = _working_sha256(store, session_id)
    request = store.request_finish("apply", expected_sha256)
    real_atomic_write = sessions_module.atomic_write_bytes

    def corrupt_exchange_write(path: Path, data: bytes) -> None:
        if path == exchange:
            real_atomic_write(path, data + b"\n")
            return
        real_atomic_write(path, data)

    monkeypatch.setattr(sessions_module, "atomic_write_bytes", corrupt_exchange_write)

    with pytest.raises(SessionError, match="does not match") as caught:
        store.finalize(session_id, "apply", str(request["expected_sha256"]))

    assert caught.value.payload.code == "sha256_mismatch"
    assert store.read_metadata(session_id)["status"] == "active"


def test_finish_live_session_schema_binds_apply_to_latest_working_sha() -> None:
    tool = create_server()._tool_manager._tools["finish_live_session"]
    expected = tool.parameters["properties"]["expected_sha256"]["anyOf"][0]

    assert expected["pattern"] == "^[0-9a-f]{64}$"
    assert "latest working XML" in expected["description"]
    assert "Required when action=apply" in expected["description"]
    assert "SHA-256" in (tool.description or "")
