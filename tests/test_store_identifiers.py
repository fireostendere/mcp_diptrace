from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import (
    ObjectNotFoundError,
    SessionError,
    TransactionNotFoundError,
)
from diptrace_mcp.exports import ExportStore
from diptrace_mcp.findings import FindingStore, ReviewReport, make_finding
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.plans import PlanStore
from diptrace_mcp.previews import RawPreviewStore
from diptrace_mcp.record_ids import (
    RecordIdKind,
    iter_valid_record_files,
    require_record_id,
)
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.transactions import TransactionStore
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
UUID4 = "123e4567-e89b-42d3-a456-426614174000"
VALID_IDS = {
    "transaction": f"tx_{UUID4}",
    "preview": f"preview_{'0' * 32}",
    "job": f"job_{'1' * 32}",
    "plan": f"plan_{'2' * 32}",
    "export": f"export_{'3' * 32}",
    "session": UUID4,
    "report": f"report_{'4' * 16}",
    "finding": f"finding_{'5' * 16}",
}


def test_each_store_generated_identifier_passes_shared_validator(tmp_path: Path) -> None:
    state = tmp_path / "state"
    findings = FindingStore(state)
    jobs = JobStore(state)
    plans = PlanStore(state)
    exports = ExportStore(state, max_artifact_bytes=1024)
    sessions = SessionStore(state)
    transactions = TransactionStore(state)
    previews = RawPreviewStore(state)

    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)
    job = jobs.create(job_type="identifier-test")
    plan = plans.create(
        plan_type="identifier-test",
        document_id=snapshot.info.document_id,
        source_sha256=snapshot.info.sha256,
        target_path=tmp_path / "target.xml",
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
    export = exports.create(snapshot, "bom", {}, {}, [])
    session = sessions.create(FIXTURES / "pcb.xml")
    transaction = transactions.create(
        snapshot.info,
        tmp_path / "target.xml",
        source_sha256=snapshot.info.sha256,
    )
    preview_id, _preview_uri = previews.store("", {})
    finding = make_finding(
        "identifier.test",
        "test",
        "info",
        "Identifier test",
        "Synthetic identifier-shape test.",
    )
    report = findings.create_report(
        document_id=snapshot.info.document_id,
        source_sha256=snapshot.info.sha256,
        profile="identifier-test",
        findings=[finding],
        metrics={},
        assumptions=[],
        skipped_checks=[],
        registered_check_count=1,
    )

    generated_ids: dict[RecordIdKind, str] = {
        "transaction": transaction.txid,
        "preview": preview_id,
        "job": job.jobid,
        "plan": plan.plan_id,
        "export": export.export_id,
        "session": str(session["session_id"]),
        "report": report.report_id,
        "finding": finding.finding_id,
    }
    for kind, value in generated_ids.items():
        assert require_record_id(value, kind) == value

    assert findings.report_path(report.report_id).parent == findings.reports_dir
    assert jobs.job_dir(job.jobid).parent == jobs.jobs_dir
    assert plans.plan_dir(plan.plan_id).parent == plans.plans_dir
    assert exports._directory(export.export_id).parent == exports.root
    assert sessions.session_dir(str(session["session_id"])).parent == sessions.sessions_dir
    assert transactions.tx_dir(transaction.txid).parent == transactions.transactions_dir
    assert previews.preview_dir(preview_id).parent == previews.previews_dir


def test_store_lists_skip_invalid_paths_and_embedded_id_mismatches(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    transactions = TransactionStore(state)
    transaction = transactions.create(
        snapshot.info,
        tmp_path / "target.xml",
        source_sha256=snapshot.info.sha256,
    )
    invalid_tx_dir = transactions.transactions_dir / "tx_invalid"
    invalid_tx_dir.mkdir()
    (invalid_tx_dir / "transaction.json").write_text(
        transaction.model_dump_json(),
        encoding="utf-8",
    )
    mismatched_tx_dir = transactions.transactions_dir / f"tx_{UUID4}"
    mismatched_tx_dir.mkdir()
    (mismatched_tx_dir / "transaction.json").write_text(
        transaction.model_dump_json(),
        encoding="utf-8",
    )

    jobs = JobStore(state)
    job = jobs.create(job_type="identifier-test")
    invalid_job_dir = jobs.jobs_dir / "job_invalid"
    invalid_job_dir.mkdir()
    (invalid_job_dir / "job.json").write_text(job.model_dump_json(), encoding="utf-8")
    mismatched_job_dir = jobs.jobs_dir / VALID_IDS["job"]
    mismatched_job_dir.mkdir()
    (mismatched_job_dir / "job.json").write_text(job.model_dump_json(), encoding="utf-8")

    exports = ExportStore(state, max_artifact_bytes=1024)
    export = exports.create(snapshot, "bom", {}, {}, [])
    invalid_export_dir = exports.root / "export_invalid"
    invalid_export_dir.mkdir()
    (invalid_export_dir / "record.json").write_text(
        export.model_dump_json(),
        encoding="utf-8",
    )
    mismatched_export_dir = exports.root / VALID_IDS["export"]
    mismatched_export_dir.mkdir()
    (mismatched_export_dir / "record.json").write_text(
        export.model_dump_json(),
        encoding="utf-8",
    )

    findings = FindingStore(state)
    report = findings.create_report(
        document_id=snapshot.info.document_id,
        source_sha256=snapshot.info.sha256,
        profile="identifier-test",
        findings=[],
        metrics={},
        assumptions=[],
        skipped_checks=[],
        registered_check_count=0,
    )
    (findings.reports_dir / "report_invalid.json").write_text(
        report.model_dump_json(),
        encoding="utf-8",
    )
    (findings.reports_dir / f"{VALID_IDS['report']}.json").write_text(
        report.model_dump_json(),
        encoding="utf-8",
    )

    assert [item.txid for item in transactions.list()] == [transaction.txid]
    assert [item.jobid for item in jobs.list()] == [job.jobid]
    assert [item.export_id for item in exports.list()] == [export.export_id]
    assert [item.report_id for item in findings.list_reports()] == [report.report_id]


def test_valid_record_iterator_rejects_symlinked_state_file(tmp_path: Path) -> None:
    root = tmp_path / "reviews"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    target = outside / "report.json"
    target.write_text("{}", encoding="utf-8")
    link = root / f"{VALID_IDS['report']}.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")

    assert (
        list(
            iter_valid_record_files(
                root,
                root.glob("report_*.json"),
                kind="report",
            )
        )
        == []
    )


def test_all_stores_reject_invalid_ids_without_echoing_them(tmp_path: Path) -> None:
    state = tmp_path / "state"
    findings = FindingStore(state)
    jobs = JobStore(state)
    plans = PlanStore(state)
    exports = ExportStore(state, max_artifact_bytes=1024)
    sessions = SessionStore(state)
    transactions = TransactionStore(state)
    invalid_marker = "../SENSITIVE_INVALID_ID"
    cases: list[tuple[Callable[[], object], type[Exception]]] = [
        (lambda: findings.read(invalid_marker), ObjectNotFoundError),
        (lambda: findings.get_finding(invalid_marker), ObjectNotFoundError),
        (lambda: jobs.job_dir(invalid_marker), ObjectNotFoundError),
        (lambda: plans.plan_dir(invalid_marker), ObjectNotFoundError),
        (lambda: exports.read(invalid_marker), ObjectNotFoundError),
        (lambda: sessions.session_dir(invalid_marker), SessionError),
        (lambda: transactions.tx_dir(invalid_marker), TransactionNotFoundError),
    ]

    for call, error_type in cases:
        with pytest.raises(error_type) as caught:
            call()
        assert invalid_marker not in str(caught.value)

    with pytest.raises(ObjectNotFoundError) as job_error:
        jobs.job_dir(invalid_marker)
    assert job_error.value.payload.jobid == invalid_marker
    assert job_error.value.payload.code == "object_not_found"

    with pytest.raises(TransactionNotFoundError) as transaction_error:
        transactions.tx_dir(invalid_marker)
    assert transaction_error.value.payload.txid == invalid_marker
    assert transaction_error.value.payload.code == "transaction_not_found"


def test_finding_store_rejects_report_path_traversal_before_read(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = FindingStore(state)
    outside = state / "secrets"
    outside.mkdir()
    report = ReviewReport(
        report_id=VALID_IDS["report"],
        document_id=f"doc_{'6' * 16}",
        source_sha256="7" * 64,
        profile="board_review",
        created_at="2026-01-01T00:00:00Z",
        completeness=1.0,
    )
    (outside / "report.json").write_text(report.model_dump_json(), encoding="utf-8")

    with pytest.raises(ObjectNotFoundError, match=r"^Invalid report id$"):
        store.read("../secrets/report")


def test_export_store_rejects_prefix_and_length_path_escape(tmp_path: Path) -> None:
    store = ExportStore(tmp_path / "state", max_artifact_bytes=1024)
    exploit = "export_" + "../" * 10 + ".."
    assert len(exploit) == 39
    escaped = (store.root / exploit).resolve()
    with pytest.raises(ValueError):
        escaped.relative_to(store.root.resolve())

    with pytest.raises(ObjectNotFoundError, match=r"^Invalid export id$"):
        store.read(exploit)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("transaction", "tx_123e4567-e89b-12d3-a456-426614174000"),
        ("preview", "preview_" + "../" * 10 + ".."),
        ("job", f"job_{'A' * 32}"),
        ("plan", f"plan_{'0' * 31}"),
        ("export", "export_" + "../" * 10 + ".."),
        ("session", "deadbeef"),
        ("report", "../secrets/report"),
        ("finding", "../secrets/finding"),
    ],
)
def test_record_id_validator_rejects_near_misses(
    kind: RecordIdKind, value: str
) -> None:
    with pytest.raises(ValueError):
        require_record_id(value, kind)
