from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.backups import BackupStore
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import DocumentProvenance, FixtureValidationLevel
from diptrace_mcp.errors import (
    EditError,
    ObjectNotFoundError,
    SessionError,
    TransactionConflictError,
)
from diptrace_mcp.exports import ExportStore
from diptrace_mcp.findings import FindingStore
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.plans import PlanStore
from diptrace_mcp.retention import RetentionPolicy
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.transactions import TransactionStore
from diptrace_mcp.xml_document import (
    DipTraceDocument,
    XmlEdit,
    atomic_write_bytes,
    sha256_bytes,
    write_with_backup,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 1, 31, tzinfo=timezone.utc)
FUTURE = datetime(2030, 1, 1, tzinfo=timezone.utc)
OLD = "2020-01-01T00:00:00+00:00"
COUNT_OLD = "2026-01-29T00:00:00+00:00"
NEWEST = "2026-01-30T00:00:00+00:00"
SHA = "a" * 64


def _clock(value: datetime = NOW) -> Callable[[], datetime]:
    return lambda: value


def _patch_json(path: Path, **updates: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload.update(updates)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _snapshot() -> Any:
    return build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))


def _create_plan(store: PlanStore, *, suffix: str = "") -> Any:
    snapshot = _snapshot()
    return store.create(
        plan_type=f"retention{suffix}",
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


@dataclass
class StoreCase:
    record_id: str
    record_path: Path
    directory: Path
    read: Callable[[], object]
    reopen: Callable[[RetentionPolicy, Callable[[], datetime]], object]
    create_peer: Callable[[], tuple[str, Path, Path]]
    expected_error: type[Exception]
    update_requested: Callable[[], object] | None = None


def _store_case(kind: str, tmp_path: Path) -> StoreCase:
    state = tmp_path / "state"
    snapshot = _snapshot()
    if kind == "transaction":
        store = TransactionStore(state)

        def create() -> tuple[str, Path, Path]:
            record = store.create(
                snapshot.info,
                FIXTURES / "pcb.xml",
                source_sha256=snapshot.info.sha256,
            )
            store.store_snapshot(record.txid, b"snapshot")
            store.store_backup(record.txid, b"backup")
            store.mark_rolled_back(record.txid, rolled_back_sha256=None)
            return record.txid, store.record_path(record.txid), store.tx_dir(record.txid)

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read(record_id),
            lambda policy, clock: TransactionStore(
                state,
                retention=policy,
                clock=clock,
            ),
            create,
            TransactionConflictError,
            lambda: store.update(record_id, notes=["must-not-cross-write"]),
        )
    if kind == "job":
        store = JobStore(state)

        def create() -> tuple[str, Path, Path]:
            record = store.create(job_type="retention")
            store.store_artifact(record.jobid, "log.txt", b"log")
            store.update(
                record.jobid,
                status="completed",
                completed_at=NEWEST,
                phase="completed",
                progress=1.0,
            )
            return record.jobid, store.record_path(record.jobid), store.job_dir(record.jobid)

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read(record_id),
            lambda policy, clock: JobStore(state, retention=policy, clock=clock),
            create,
            ObjectNotFoundError,
            lambda: store.update(record_id, phase="must-not-cross-write"),
        )
    if kind == "plan":
        store = PlanStore(state)

        def create() -> tuple[str, Path, Path]:
            record = _create_plan(store, suffix=NEWEST)
            store.update(record.plan_id, status="committed", transaction_id=None)
            return (
                record.plan_id,
                store.record_path(record.plan_id),
                store.plan_dir(record.plan_id),
            )

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read(record_id),
            lambda policy, clock: PlanStore(state, retention=policy, clock=clock),
            create,
            ObjectNotFoundError,
            lambda: store.update(
                record_id,
                status="obsolete",
                transaction_id=None,
            ),
        )
    if kind == "export":
        store = ExportStore(state, max_artifact_bytes=10_000_000)

        def create() -> tuple[str, Path, Path]:
            record = store.create(snapshot, "bom", {}, {}, [])
            return (
                record.export_id,
                store._record_path(record.export_id),
                store._directory(record.export_id),
            )

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read(record_id),
            lambda policy, clock: ExportStore(
                state,
                max_artifact_bytes=10_000_000,
                retention=policy,
                clock=clock,
            ),
            create,
            ObjectNotFoundError,
        )
    if kind == "finding":
        store = FindingStore(state)
        counter = 0

        def create() -> tuple[str, Path, Path]:
            nonlocal counter
            counter += 1
            report = store.create_report(
                document_id=snapshot.info.document_id,
                source_sha256=snapshot.info.sha256,
                profile=f"retention-{counter}",
                findings=[],
                metrics={},
                assumptions=[],
                skipped_checks=[],
                registered_check_count=0,
            )
            path = store.report_path(report.report_id)
            return report.report_id, path, path

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read(record_id),
            lambda policy, clock: FindingStore(
                state,
                retention=policy,
                clock=clock,
            ),
            create,
            ObjectNotFoundError,
        )
    if kind == "session":
        store = SessionStore(state, 10_000_000)

        def create() -> tuple[str, Path, Path]:
            metadata = store.create(FIXTURES / "pcb.xml")
            session_id = str(metadata["session_id"])
            atomic_write_bytes(
                store.backups_dir(session_id) / "working.bak",
                b"recover",
            )
            store.finalize(session_id, "cancel")
            return (
                session_id,
                store.metadata_path(session_id),
                store.session_dir(session_id),
            )

        record_id, record_path, directory = create()
        return StoreCase(
            record_id,
            record_path,
            directory,
            lambda: store.read_metadata(record_id),
            lambda policy, clock: SessionStore(
                state,
                10_000_000,
                retention=policy,
                clock=clock,
            ),
            create,
            SessionError,
            lambda: store.update_metadata(record_id, note="must-not-cross-write"),
        )
    raise AssertionError(f"Unknown store kind: {kind}")


@pytest.mark.parametrize(
    ("kind", "timestamp_field"),
    [
        ("transaction", "updated_at"),
        ("job", "completed_at"),
        ("plan", "updated_at"),
        ("export", "created_at"),
        ("finding", "created_at"),
        ("session", "finished_at"),
    ],
)
def test_each_store_prunes_by_age_and_count(
    tmp_path: Path,
    kind: str,
    timestamp_field: str,
) -> None:
    case = _store_case(kind, tmp_path)
    count_old_id, count_old_path, count_old_dir = case.create_peer()
    newest_id, newest_path, newest_dir = case.create_peer()
    assert len({case.record_id, count_old_id, newest_id}) == 3
    _patch_json(case.record_path, **{timestamp_field: OLD})
    _patch_json(count_old_path, **{timestamp_field: COUNT_OLD})
    _patch_json(newest_path, **{timestamp_field: NEWEST})

    case.reopen(RetentionPolicy(max_records=1, max_age_days=30), _clock())

    assert not case.directory.exists()
    assert not count_old_dir.exists()
    assert newest_dir.exists()


@pytest.mark.parametrize(
    "kind",
    ["transaction", "job", "plan", "export", "finding", "session"],
)
def test_each_store_retention_skips_corrupt_records(
    tmp_path: Path,
    kind: str,
) -> None:
    case = _store_case(kind, tmp_path)
    case.record_path.write_text("{", encoding="utf-8")

    case.reopen(
        RetentionPolicy(max_records=1, max_age_days=1),
        _clock(FUTURE),
    )

    assert case.record_path.exists()
    with pytest.raises(case.expected_error):
        case.read()


@pytest.mark.parametrize(
    ("kind", "link_level"),
    [
        ("transaction", "record"),
        ("transaction", "directory"),
        ("job", "record"),
        ("job", "directory"),
        ("plan", "record"),
        ("plan", "directory"),
        ("export", "record"),
        ("export", "directory"),
        ("finding", "record"),
        ("session", "record"),
        ("session", "directory"),
    ],
)
def test_each_store_rejects_and_retains_redirected_state(
    tmp_path: Path,
    kind: str,
    link_level: str,
) -> None:
    case = _store_case(kind, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    if link_level == "record":
        target = outside / f"{kind}.json"
        case.record_path.replace(target)
        try:
            case.record_path.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"Symlinks are unavailable on this platform: {exc}")
        redirected = case.record_path
    else:
        target = outside / kind
        case.directory.replace(target)
        try:
            case.directory.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"Symlinks are unavailable on this platform: {exc}")
        redirected = case.directory

    case.reopen(
        RetentionPolicy(max_records=1, max_age_days=1),
        _clock(FUTURE),
    )

    assert redirected.is_symlink()
    with pytest.raises(case.expected_error):
        case.read()


@pytest.mark.parametrize(
    "kind",
    ["transaction", "job", "plan", "export", "finding", "session"],
)
def test_each_store_rejects_embedded_id_mismatch_without_cross_write(
    tmp_path: Path,
    kind: str,
) -> None:
    case = _store_case(kind, tmp_path)
    peer_id, peer_path, _peer_dir = case.create_peer()
    assert peer_id != case.record_id
    peer_bytes = peer_path.read_bytes()
    case.record_path.write_bytes(peer_bytes)

    with pytest.raises(case.expected_error):
        case.read()
    if case.update_requested is not None:
        with pytest.raises(case.expected_error):
            case.update_requested()
    assert peer_path.read_bytes() == peer_bytes

    case.reopen(
        RetentionPolicy(max_records=1, max_age_days=1),
        _clock(FUTURE),
    )
    assert case.record_path.exists()


def test_junction_like_record_directory_is_rejected_and_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _store_case("transaction", tmp_path)
    original = getattr(Path, "is_junction", lambda _path: False)

    def fake_is_junction(path: Path) -> bool:
        return path == case.directory or original(path)

    monkeypatch.setattr(Path, "is_junction", fake_is_junction, raising=False)
    case.reopen(
        RetentionPolicy(max_records=1, max_age_days=1),
        _clock(FUTURE),
    )

    assert case.directory.exists()
    with pytest.raises(TransactionConflictError):
        case.read()


def test_nonterminal_records_and_their_backups_survive_retention(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    policy = RetentionPolicy(max_records=1, max_age_days=1)
    state = tmp_path / "state"

    transactions = TransactionStore(state)
    transaction = transactions.create(
        snapshot.info,
        FIXTURES / "pcb.xml",
        source_sha256=snapshot.info.sha256,
    )
    transaction_backup = transactions.store_backup(transaction.txid, b"recover")

    jobs = JobStore(state)
    job = jobs.create(job_type="still-running")
    job_artifact = jobs.store_artifact(job.jobid, "log.txt", b"running")

    plans = PlanStore(state)
    plan = _create_plan(plans, suffix="-planned")

    sessions = SessionStore(state, 10_000_000)
    active = sessions.create(FIXTURES / "pcb.xml")
    active_id = str(active["session_id"])
    live_backup = sessions.backups_dir(active_id) / "working.bak"
    atomic_write_bytes(live_backup, b"recover")

    TransactionStore(state, retention=policy, clock=_clock(FUTURE))
    JobStore(state, retention=policy, clock=_clock(FUTURE))
    PlanStore(state, retention=policy, clock=_clock(FUTURE))
    SessionStore(state, 10_000_000, retention=policy, clock=_clock(FUTURE))

    assert transactions.tx_dir(transaction.txid).exists()
    assert transaction_backup.read_bytes() == b"recover"
    assert jobs.job_dir(job.jobid).exists()
    assert job_artifact.read_bytes() == b"running"
    assert plans.plan_dir(plan.plan_id).exists()
    assert sessions.session_dir(active_id).exists()
    assert live_backup.read_bytes() == b"recover"


def test_active_json_protects_referenced_terminal_session(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = SessionStore(state, 10_000_000)
    terminal = store.create(FIXTURES / "pcb.xml")
    terminal_id = str(terminal["session_id"])
    store.finalize(terminal_id, "cancel")
    _patch_json(store.metadata_path(terminal_id), finished_at=OLD)
    terminal_backup = store.backups_dir(terminal_id) / "last.bak"
    atomic_write_bytes(terminal_backup, b"recover")
    active = store.create(FIXTURES / "pcb.xml")
    active_id = str(active["session_id"])
    _patch_json(store.active_file, session_id=terminal_id)

    SessionStore(
        state,
        10_000_000,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )

    assert store.session_dir(terminal_id).exists()
    assert terminal_backup.read_bytes() == b"recover"
    assert store.session_dir(active_id).exists()


def test_corrupt_active_json_fails_closed_for_all_sessions(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = SessionStore(state, 10_000_000)
    terminal = store.create(FIXTURES / "pcb.xml")
    terminal_id = str(terminal["session_id"])
    store.finalize(terminal_id, "cancel")
    _patch_json(store.metadata_path(terminal_id), finished_at=OLD)
    store.active_file.write_text("{", encoding="utf-8")

    reopened = SessionStore(
        state,
        10_000_000,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )

    assert reopened.session_dir(terminal_id).exists()
    assert reopened.last_retention_report.removed == ()


def test_redirected_active_json_fails_closed_for_all_sessions(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = SessionStore(state, 10_000_000)
    terminal = store.create(FIXTURES / "pcb.xml")
    terminal_id = str(terminal["session_id"])
    store.finalize(terminal_id, "cancel")
    _patch_json(store.metadata_path(terminal_id), finished_at=OLD)
    active = store.create(FIXTURES / "pcb.xml")
    active_id = str(active["session_id"])
    outside = tmp_path / "active.json"
    store.active_file.replace(outside)
    try:
        store.active_file.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    reopened = SessionStore(
        state,
        10_000_000,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )

    assert reopened.session_dir(terminal_id).exists()
    assert reopened.session_dir(active_id).exists()
    assert reopened.last_retention_report.removed == ()
    with pytest.raises(SessionError, match="unsafe"):
        reopened.active_metadata()


def test_active_json_metadata_id_mismatch_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = SessionStore(state, 10_000_000)
    first = store.create(FIXTURES / "pcb.xml")
    first_id = str(first["session_id"])
    store.finalize(first_id, "cancel")
    second = store.create(FIXTURES / "pcb.xml")
    second_id = str(second["session_id"])
    second_bytes = store.metadata_path(second_id).read_bytes()
    store.metadata_path(first_id).write_bytes(second_bytes)
    _patch_json(store.active_file, session_id=first_id)

    reopened = SessionStore(
        state,
        10_000_000,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )
    assert reopened.session_dir(first_id).exists()
    assert reopened.session_dir(second_id).exists()
    assert reopened.last_retention_report.removed == ()
    with pytest.raises(SessionError, match="does not match"):
        reopened.active_metadata()
    assert store.metadata_path(second_id).read_bytes() == second_bytes


def test_backup_store_is_outside_design_and_restores_original_bytes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "board.dip"
    original = (FIXTURES / "pcb.xml").read_bytes()
    target.write_bytes(original)
    replacement = original.replace(b"<Value>10k</Value>", b"<Value>47k</Value>")
    store = BackupStore(tmp_path / "state", clock=_clock())

    backup = write_with_backup(target, replacement, store)

    assert target.read_bytes() == replacement
    assert backup.read_bytes() == original
    backup.resolve().relative_to(store.root.resolve())
    assert not (project / ".diptrace-mcp-backups").exists()
    atomic_write_bytes(target, backup.read_bytes())
    restored = DipTraceDocument.load(target, 10_000_000)
    assert restored.sha256 == sha256_bytes(original)


def test_job_artifact_symlink_is_rejected_for_read_and_write(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state")
    job = store.create(job_type="artifact-confinement")
    artifact = store.store_artifact(job.jobid, "input.dsn", b"safe")
    outside = tmp_path / "outside.dsn"
    artifact.replace(outside)
    try:
        artifact.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    with pytest.raises(ObjectNotFoundError, match="redirected"):
        store.artifact_path(job.jobid, "input.dsn")
    with pytest.raises(ObjectNotFoundError, match="redirected"):
        store.store_artifact(job.jobid, "input.dsn", b"poison")
    assert outside.read_bytes() == b"safe"


def test_export_artifact_symlink_is_rejected_and_retention_skips_record(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = ExportStore(state, max_artifact_bytes=10_000_000)
    export = store.create(
        _snapshot(),
        "bom",
        {"bom.csv": b"safe"},
        {},
        [],
    )
    artifact = store._directory(export.export_id) / "bom.csv"
    outside = tmp_path / "outside.csv"
    artifact.replace(outside)
    try:
        artifact.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    reopened = ExportStore(
        state,
        max_artifact_bytes=10_000_000,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )

    assert reopened._directory(export.export_id).exists()
    with pytest.raises(ObjectNotFoundError, match="not found"):
        reopened.artifact(export.export_id, "bom.csv")
    assert outside.read_bytes() == b"safe"


def test_backup_pruning_is_counted_per_target_without_sleeps(
    tmp_path: Path,
) -> None:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def clock() -> datetime:
        return current

    state = tmp_path / "state"
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    first.write_bytes(b"first-0")
    second.write_bytes(b"second-0")
    store = BackupStore(
        state,
        retention=RetentionPolicy(max_records=2, max_age_days=10),
        clock=clock,
    )
    second_backup = store.write_with_backup(second, b"second-1")
    second_before = store.backups_for(second)
    assert second_before == (second_backup,)

    first_backup_1 = store.write_with_backup(first, b"first-1")
    first_backup_2 = store.write_with_backup(first, b"first-2")
    first_backup_3 = store.write_with_backup(first, b"first-3")

    assert first_backup_3.exists()
    assert len(store.backups_for(first)) == 2
    assert not first_backup_1.exists()
    assert first_backup_2.exists()
    assert store.backups_for(second) == second_before
    assert second_backup.read_bytes() == b"second-0"

    current = datetime(2026, 2, 1, tzinfo=timezone.utc)
    newest = store.write_with_backup(first, b"first-4")
    assert store.backups_for(first) == (newest,)
    # A write/prune for the first target never mutates the second history.
    assert store.backups_for(second) == second_before


def test_service_routes_offline_backup_to_state_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    state = tmp_path / "state"
    project.mkdir()
    target = project / "board.dip"
    target.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    settings = Settings(
        workspace=project,
        allowed_roots=(project,),
        state_dir=state,
        max_document_bytes=10_000_000,
        max_scan_files=100,
    )
    service = DipTraceService(settings)
    edits = [
        XmlEdit(
            operation="set_text",
            xpath="./Board/Components/Component[RefDes='R1']/Value",
            value="47k",
        )
    ]
    preview = service.apply_edits(edits, path="board.dip")
    committed = service.apply_edits(
        edits,
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["before_sha256"],
    )

    backup = Path(str(committed["backup"]))
    backup.resolve().relative_to((state / "offline_backups").resolve())
    assert backup.is_file()
    assert not (project / ".diptrace-mcp-backups").exists()


def test_transaction_snapshot_path_is_derived_and_hash_checked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    state = tmp_path / "state"
    project.mkdir()
    target = project / "board.dip"
    target.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=project,
            allowed_roots=(project,),
            state_dir=state,
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )
    begun = service.begin_transaction("board.dip")
    txid = str(begun["transaction"]["txid"])
    outside = tmp_path / "outside.xml"
    outside.write_bytes(b"not XML and must never be read")
    _patch_json(service.transactions.record_path(txid), snapshot_path=str(outside))

    record = service.transactions.read(txid)
    loaded = service._load_snapshot_record(record)

    assert loaded.sha256 == begun["transaction"]["source_sha256"]
    assert outside.read_bytes() == b"not XML and must never be read"
    internal = service.transactions.require_snapshot(txid)
    tampered = internal.read_bytes().replace(
        b"<Value>10k</Value>",
        b"<Value>47k</Value>",
    )
    internal.write_bytes(tampered)
    with pytest.raises(TransactionConflictError, match="source SHA"):
        service._load_snapshot_record(service.transactions.read(txid))


def test_transaction_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "board.dip"
    target.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=project,
            allowed_roots=(project,),
            state_dir=tmp_path / "state",
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )
    txid = str(service.begin_transaction("board.dip")["transaction"]["txid"])
    snapshot = service.transactions.snapshot_path(txid)
    outside = tmp_path / "outside.xml"
    outside.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    snapshot.unlink()
    try:
        snapshot.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    with pytest.raises(TransactionConflictError, match="missing or unsafe"):
        service._load_snapshot_record(service.transactions.read(txid))


def test_rollback_ignores_persisted_backup_and_provenance_paths(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "board.dip"
    original = (FIXTURES / "pcb.xml").read_bytes()
    target.write_bytes(original)
    service = DipTraceService(
        Settings(
            workspace=project,
            allowed_roots=(project,),
            state_dir=tmp_path / "state",
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )
    preview = service.move_components(
        selector={"refdes": ["R1"]},
        dx=1.0,
        dy=0.0,
        path="board.dip",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    committed = service.move_components(
        selector={"refdes": ["R1"]},
        dx=1.0,
        dy=0.0,
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["transaction"]["expected_sha256"],
        txid=txid,
    )
    outside_xml = tmp_path / "outside.xml"
    outside_xml.write_bytes(original.replace(b"<Value>10k</Value>", b"<Value>POISON</Value>"))
    outside_provenance = tmp_path / "outside.provenance.json"
    poisoned_sidecar = DocumentProvenance(
        provenance="outside-poison",
        validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        current_document_sha256=sha256_bytes(original),
    ).model_dump_json().encode("utf-8")
    outside_provenance.write_bytes(poisoned_sidecar)
    _patch_json(
        service.transactions.record_path(txid),
        backup_path=str(outside_xml),
        provenance_backup_path=str(outside_provenance),
        provenance_backup_sha256=sha256_bytes(poisoned_sidecar),
    )

    service.rollback_transaction(
        txid,
        expected_sha256=committed["transaction"]["committed_sha256"],
    )

    assert target.read_bytes() == original
    assert b"POISON" in outside_xml.read_bytes()
    assert outside_provenance.read_bytes() == poisoned_sidecar
    restored_sidecar = DocumentProvenance.model_validate_json(
        target.with_suffix(target.suffix + ".provenance.json").read_bytes()
    )
    assert restored_sidecar.provenance == "mcp_rollback_no_backup"


def test_rollback_rejects_internal_backup_hash_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "board.dip"
    target.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=project,
            allowed_roots=(project,),
            state_dir=tmp_path / "state",
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )
    preview = service.move_components(
        selector={"refdes": ["R1"]},
        dx=1.0,
        dy=0.0,
        path="board.dip",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    committed = service.move_components(
        selector={"refdes": ["R1"]},
        dx=1.0,
        dy=0.0,
        path="board.dip",
        dry_run=False,
        expected_sha256=preview["transaction"]["expected_sha256"],
        txid=txid,
    )
    committed_bytes = target.read_bytes()
    service.transactions.require_backup(txid).write_bytes(
        (FIXTURES / "schematic.xml").read_bytes()
    )

    with pytest.raises(TransactionConflictError, match="source SHA"):
        service.rollback_transaction(
            txid,
            expected_sha256=committed["transaction"]["committed_sha256"],
        )
    assert target.read_bytes() == committed_bytes


def test_backup_store_excludes_content_with_a_forged_hash(tmp_path: Path) -> None:
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    store = BackupStore(tmp_path / "state", clock=_clock())
    backup = store.write_with_backup(target, b"changed")
    backup.write_bytes(b"forged")

    assert store.backups_for(target) == ()
    assert backup.exists()


def test_backup_store_does_not_overwrite_corrupt_target_binding(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    store = BackupStore(state, clock=_clock())
    backup = store.write_with_backup(target, b"changed")
    metadata = backup.parent / "target.json"
    metadata.write_text("{", encoding="utf-8")

    reopened = BackupStore(
        state,
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=_clock(FUTURE),
    )

    assert backup.exists()
    with pytest.raises(EditError, match="metadata is corrupt"):
        reopened.write_with_backup(target, b"must-not-write")
    assert target.read_bytes() == b"changed"


def test_backup_store_rejects_redirected_target_history(tmp_path: Path) -> None:
    state = tmp_path / "state"
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    store = BackupStore(state, clock=_clock())
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    outside = tmp_path / "outside-history"
    history.replace(outside)
    try:
        history.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    with pytest.raises(EditError, match="redirected"):
        store.write_with_backup(target, b"must-not-write")
    assert target.read_bytes() == b"changed"
    assert (outside / backup.name).read_bytes() == b"original"


def test_retention_settings_are_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DIPTRACE_MCP_RETENTION_MAX_RECORDS", "17")
    monkeypatch.setenv("DIPTRACE_MCP_RETENTION_MAX_AGE_DAYS", "23")
    settings = Settings.from_env()

    assert settings.retention_policy == RetentionPolicy(
        max_records=17,
        max_age_days=23,
    )
    assert settings.as_dict()["retention_max_records"] == 17
    assert settings.as_dict()["retention_max_age_days"] == 23
    limits = DipTraceService(settings).get_capabilities()["limits"]
    assert limits["retention_max_records"] == 17
    assert limits["retention_max_age_days"] == 23
