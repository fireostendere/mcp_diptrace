from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from diptrace_mcp.errors import (
    ObjectNotFoundError,
    SessionError,
    TransactionNotFoundError,
)
from diptrace_mcp.exports import ExportStore
from diptrace_mcp.findings import FindingStore, ReviewReport
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.plans import PlanStore
from diptrace_mcp.record_ids import RecordIdKind, require_record_id
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.transactions import TransactionStore

UUID4 = "123e4567-e89b-42d3-a456-426614174000"
VALID_IDS = {
    "transaction": f"tx_{UUID4}",
    "job": f"job_{'1' * 32}",
    "plan": f"plan_{'2' * 32}",
    "export": f"export_{'3' * 32}",
    "session": UUID4,
    "report": f"report_{'4' * 16}",
    "finding": f"finding_{'5' * 16}",
}


@pytest.mark.parametrize(("kind", "value"), VALID_IDS.items())
def test_record_id_validator_accepts_only_generated_formats(
    kind: RecordIdKind, value: str
) -> None:
    assert require_record_id(value, kind) == value


def test_each_store_accepts_its_generated_identifier_shape(tmp_path: Path) -> None:
    state = tmp_path / "state"
    findings = FindingStore(state)
    jobs = JobStore(state)
    plans = PlanStore(state)
    exports = ExportStore(state, max_artifact_bytes=1024)
    sessions = SessionStore(state)
    transactions = TransactionStore(state)

    assert findings.report_path(VALID_IDS["report"]).parent == findings.reports_dir
    assert jobs.job_dir(VALID_IDS["job"]).parent == jobs.jobs_dir
    assert plans.plan_dir(VALID_IDS["plan"]).parent == plans.plans_dir
    assert exports._directory(VALID_IDS["export"]).parent == exports.root
    assert sessions.session_dir(VALID_IDS["session"]).parent == sessions.sessions_dir
    assert (
        transactions.tx_dir(VALID_IDS["transaction"]).parent
        == transactions.transactions_dir
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
    assert (store.root / exploit).resolve() == Path((store.root / exploit).anchor)

    with pytest.raises(ObjectNotFoundError, match=r"^Invalid export id$"):
        store.read(exploit)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("transaction", "tx_123e4567-e89b-12d3-a456-426614174000"),
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
