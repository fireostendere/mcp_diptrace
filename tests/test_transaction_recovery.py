from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import diptrace_mcp.service as service_module
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import TransactionConflictError
from diptrace_mcp.scaffolding import SchematicScaffold, build_schematic_document
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import sha256_bytes

MAX_BYTES = 20_000_000


def _service(workspace: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=workspace / ".state",
            max_document_bytes=MAX_BYTES,
        )
    )


def _validated_transaction(
    workspace: Path,
) -> tuple[DipTraceService, Path, str, str, bytes, bytes]:
    service = _service(workspace)
    created = service.create_document("schematic", "board.dch")
    target = workspace / "board.dch"
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    source_bytes = target.read_bytes()
    source_sidecar_bytes = sidecar.read_bytes()
    preview = service.add_sheet("MCP sheet", path="board.dch")
    return (
        service,
        target,
        str(preview["transaction"]["txid"]),
        str(created["result"]["sha256"]),
        source_bytes,
        source_sidecar_bytes,
    )


def _committed_transaction(
    workspace: Path,
) -> tuple[DipTraceService, Path, str, str, bytes, bytes]:
    service, target, txid, source_sha256, _, _ = _validated_transaction(workspace)
    committed = service.commit_transaction(txid, source_sha256)
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    return (
        service,
        target,
        txid,
        str(committed["transaction"]["committed_sha256"]),
        target.read_bytes(),
        sidecar.read_bytes(),
    )


def test_rollback_sidecar_write_failure_restores_exact_pre_call_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, committed_sha256, committed_bytes, committed_sidecar = (
        _committed_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    real_atomic_write = service_module.atomic_write_bytes

    def fail_sidecar_write(path: Path, data: bytes) -> None:
        if path == sidecar:
            raise OSError("injected sidecar write failure")
        real_atomic_write(path, data)

    monkeypatch.setattr(service_module, "atomic_write_bytes", fail_sidecar_write)

    with pytest.raises(TransactionConflictError) as failed:
        service.rollback_transaction(txid, committed_sha256)

    assert failed.value.payload.details["phase"] == "rollback_apply"
    assert failed.value.payload.details["compensated"] is True
    assert target.read_bytes() == committed_bytes
    assert sidecar.read_bytes() == committed_sidecar
    assert service.transactions.read(txid).status == "committed"


def test_rollback_preserves_external_sidecar_bytes_during_compensation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, committed_sha256, committed_bytes, _ = (
        _committed_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    external_sidecar = b'{"authority":"external-writer"}\n'
    real_atomic_write = service_module.atomic_write_bytes

    def replace_sidecar_then_fail(path: Path, data: bytes) -> None:
        if path == sidecar:
            real_atomic_write(path, external_sidecar)
            raise OSError("external sidecar appeared")
        real_atomic_write(path, data)

    monkeypatch.setattr(service_module, "atomic_write_bytes", replace_sidecar_then_fail)

    with pytest.raises(TransactionConflictError) as failed:
        service.rollback_transaction(txid, committed_sha256)

    details = failed.value.payload.details
    assert details["phase"] == "rollback_apply"
    assert details["compensated"] is False
    assert details["current_sidecar_sha256"] == sha256_bytes(external_sidecar)
    assert target.read_bytes() == committed_bytes
    assert sidecar.read_bytes() == external_sidecar
    assert service.transactions.read(txid).status == "committed"


def test_rollback_state_write_failure_compensates_document_and_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, committed_sha256, committed_bytes, committed_sidecar = (
        _committed_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    transaction_store_type = type(service.transactions)

    def fail_mark_rolled_back(
        store: object,
        transaction_id: str,
        *,
        rolled_back_sha256: str | None,
        reason: str = "",
    ) -> Any:
        raise OSError("injected transaction state failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_rolled_back",
        fail_mark_rolled_back,
    )

    with pytest.raises(TransactionConflictError) as failed:
        service.rollback_transaction(txid, committed_sha256)

    assert failed.value.payload.details["phase"] == "rollback_state_write"
    assert failed.value.payload.details["compensated"] is True
    assert target.read_bytes() == committed_bytes
    assert sidecar.read_bytes() == committed_sidecar
    assert service.transactions.read(txid).status == "committed"


def test_failed_commit_write_restores_authenticated_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, source_sha256, source_bytes, source_sidecar = (
        _validated_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    real_atomic_write = service_module.atomic_write_bytes
    failed_once = False

    def fail_after_target_replace(path: Path, data: bytes) -> None:
        nonlocal failed_once
        if path == target and not failed_once:
            failed_once = True
            real_atomic_write(path, data)
            raise OSError("injected post-replace failure")
        real_atomic_write(path, data)

    monkeypatch.setattr(service_module, "atomic_write_bytes", fail_after_target_replace)

    with pytest.raises(TransactionConflictError) as failed:
        service.commit_transaction(txid, source_sha256)

    assert failed.value.payload.details["phase"] == "commit_write"
    assert failed.value.payload.details["source_restored"] is True
    assert target.read_bytes() == source_bytes
    assert sidecar.read_bytes() == source_sidecar
    assert service.transactions.require_backup(txid).read_bytes() == source_bytes
    assert service.transactions.read(txid).status == "failed"


def test_commit_state_write_failure_restores_source_and_stays_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, source_sha256, source_bytes, source_sidecar = (
        _validated_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    transaction_store_type = type(service.transactions)

    def fail_mark_committed(store: object, transaction_id: str, **changes: Any) -> Any:
        raise OSError("injected commit state failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_committed",
        fail_mark_committed,
    )

    with pytest.raises(TransactionConflictError) as failed:
        service.commit_transaction(txid, source_sha256)

    assert failed.value.payload.details["phase"] == "commit_state_write"
    assert failed.value.payload.details["source_restored"] is True
    assert target.read_bytes() == source_bytes
    assert sidecar.read_bytes() == source_sidecar
    assert service.transactions.read(txid).status == "validated"


def test_commit_accepts_state_write_that_persisted_before_reporting_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, source_sha256, source_bytes, _ = _validated_transaction(
        tmp_path
    )
    transaction_store_type = type(service.transactions)
    real_mark_committed = transaction_store_type.mark_committed

    def mark_committed_then_fail(
        store: Any,
        transaction_id: str,
        **changes: Any,
    ) -> Any:
        real_mark_committed(store, transaction_id, **changes)
        raise OSError("injected post-state-write failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_committed",
        mark_committed_then_fail,
    )

    committed = service.commit_transaction(txid, source_sha256)

    assert committed["transaction"]["status"] == "committed"
    assert target.read_bytes() != source_bytes
    assert service.transactions.read(txid).status == "committed"


def test_commit_failure_state_error_leaves_coherent_retryable_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, source_sha256, source_bytes, source_sidecar = (
        _validated_transaction(tmp_path)
    )
    sidecar = target.with_suffix(target.suffix + ".provenance.json")
    transaction_store_type = type(service.transactions)
    real_atomic_write = service_module.atomic_write_bytes
    failed_once = False

    def fail_after_target_replace(path: Path, data: bytes) -> None:
        nonlocal failed_once
        if path == target and not failed_once:
            failed_once = True
            real_atomic_write(path, data)
            raise OSError("injected post-replace failure")
        real_atomic_write(path, data)

    def fail_mark_failed(store: object, transaction_id: str, error: dict[str, Any]) -> Any:
        raise OSError("injected failure-state write error")

    monkeypatch.setattr(service_module, "atomic_write_bytes", fail_after_target_replace)
    monkeypatch.setattr(transaction_store_type, "mark_failed", fail_mark_failed)

    with pytest.raises(TransactionConflictError) as failed:
        service.commit_transaction(txid, source_sha256)

    assert failed.value.payload.details["phase"] == "commit_failure_state"
    assert failed.value.payload.details["source_restored"] is True
    assert target.read_bytes() == source_bytes
    assert sidecar.read_bytes() == source_sidecar
    assert service.transactions.read(txid).status == "validated"


def test_commit_compensation_never_overwrites_external_document_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, source_sha256, _, _ = _validated_transaction(tmp_path)
    external_bytes = build_schematic_document(
        SchematicScaffold(sheet_names=["External writer"])
    )
    real_atomic_write = service_module.atomic_write_bytes
    failed_once = False

    def install_external_bytes_then_fail(path: Path, data: bytes) -> None:
        nonlocal failed_once
        if path == target and not failed_once:
            failed_once = True
            real_atomic_write(path, data)
            real_atomic_write(path, external_bytes)
            raise OSError("external document won the race")
        real_atomic_write(path, data)

    monkeypatch.setattr(
        service_module,
        "atomic_write_bytes",
        install_external_bytes_then_fail,
    )

    with pytest.raises(TransactionConflictError) as failed:
        service.commit_transaction(txid, source_sha256)

    details = failed.value.payload.details
    assert details["phase"] == "commit_compensation"
    assert details["current_sha256"] == sha256_bytes(external_bytes)
    assert target.read_bytes() == external_bytes
    assert service.transactions.read(txid).status == "failed"


def test_rollback_accepts_state_write_that_persisted_before_reporting_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, target, txid, committed_sha256, committed_bytes, _ = (
        _committed_transaction(tmp_path)
    )
    transaction_store_type = type(service.transactions)
    real_mark_rolled_back = transaction_store_type.mark_rolled_back

    def mark_rolled_back_then_fail(
        store: Any,
        transaction_id: str,
        *,
        rolled_back_sha256: str | None,
        reason: str = "",
    ) -> Any:
        real_mark_rolled_back(
            store,
            transaction_id,
            rolled_back_sha256=rolled_back_sha256,
            reason=reason,
        )
        raise OSError("injected post-state-write failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_rolled_back",
        mark_rolled_back_then_fail,
    )

    rolled_back = service.rollback_transaction(txid, committed_sha256)

    assert rolled_back["transaction"]["status"] == "rolled_back"
    assert target.read_bytes() != committed_bytes
    assert service.transactions.read(txid).status == "rolled_back"
