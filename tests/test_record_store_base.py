from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.exports import ExportStore
from diptrace_mcp.findings import FindingStore
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.plans import PlanStore
from diptrace_mcp.record_ids import InvalidRecordPath
from diptrace_mcp.record_store import RecordStore
from diptrace_mcp.retention import RetentionPolicy, RetentionReport
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.transactions import TransactionStore
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
STORE_TYPES = (
    TransactionStore,
    SessionStore,
    PlanStore,
    FindingStore,
    JobStore,
    ExportStore,
)


def _clock() -> datetime:
    return datetime(2026, 7, 29, tzinfo=timezone.utc)


def _create_plan(store: PlanStore) -> Any:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    return store.create(
        plan_type="record-store-parity",
        document_id=snapshot.info.document_id,
        source_sha256=snapshot.info.sha256,
        target_path=FIXTURES / "pcb.xml",
        config={},
        operations=[],
        changed_ids=[],
        unresolved=[],
        candidates=[],
        score={},
        metrics={},
        assumptions=[],
        warnings=[],
        limitations=[],
    )


def test_six_persistent_stores_share_only_the_common_lifecycle_seam(
    tmp_path: Path,
) -> None:
    policy = RetentionPolicy(max_records=7, max_age_days=11)
    stores = (
        TransactionStore(tmp_path / "transactions", retention=policy, clock=_clock),
        SessionStore(tmp_path / "sessions", retention=policy, clock=_clock),
        PlanStore(tmp_path / "plans", retention=policy, clock=_clock),
        FindingStore(tmp_path / "findings", retention=policy, clock=_clock),
        JobStore(tmp_path / "jobs", retention=policy, clock=_clock),
        ExportStore(
            tmp_path / "exports",
            max_artifact_bytes=1024,
            retention=policy,
            clock=_clock,
        ),
    )

    assert all(isinstance(store, RecordStore) for store in stores)
    assert all(store.retention is policy for store in stores)
    assert all(store.clock is _clock for store in stores)
    assert all(isinstance(store.last_retention_report, RetentionReport) for store in stores)
    assert all("_prune_retention" in store_type.__dict__ for store_type in STORE_TYPES)
    for store in stores:
        store._require_safe_root()


def test_all_six_primary_records_use_the_common_atomic_json_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: set[type[RecordStore]] = set()
    original = RecordStore._write_store_json

    def recording_writer(
        self: RecordStore,
        path: Path,
        value: dict[str, Any],
        **options: Any,
    ) -> None:
        seen.add(type(self))
        original(self, path, value, **options)

    monkeypatch.setattr(RecordStore, "_write_store_json", recording_writer)
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    transaction_store = TransactionStore(tmp_path / "transactions")
    transaction_store.create(
        snapshot.info,
        FIXTURES / "pcb.xml",
        source_sha256=snapshot.info.sha256,
    )
    SessionStore(tmp_path / "sessions").create(FIXTURES / "pcb.xml")
    _create_plan(PlanStore(tmp_path / "plans"))
    FindingStore(tmp_path / "findings").create_report(
        document_id=snapshot.info.document_id,
        source_sha256=snapshot.info.sha256,
        profile="record-store-parity",
        findings=[],
        metrics={},
        assumptions=[],
        skipped_checks=[],
        registered_check_count=0,
    )
    JobStore(tmp_path / "jobs").create(job_type="record-store-parity")
    ExportStore(tmp_path / "exports", max_artifact_bytes=1024).create(
        snapshot,
        "bom",
        {},
        {},
        [],
    )

    assert seen == set(STORE_TYPES)


def test_common_json_writer_refuses_a_redirected_record_directory(
    tmp_path: Path,
) -> None:
    store = PlanStore(tmp_path / "state")
    record = _create_plan(store)
    directory = store.plan_dir(record.plan_id)
    outside = tmp_path / "outside"
    directory.replace(outside)
    try:
        directory.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")
    before = store.record_path(record.plan_id).read_bytes()

    with pytest.raises(InvalidRecordPath, match="redirected|outside"):
        store.write(record)

    assert store.record_path(record.plan_id).read_bytes() == before
