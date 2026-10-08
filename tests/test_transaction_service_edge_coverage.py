from __future__ import annotations

from pathlib import Path

from diptrace_mcp.services import transactions


def test_transaction_summary_bounds_error_and_optional_file_guards(tmp_path: Path) -> None:
    digest = "a" * 64
    record = transactions.TransactionRecord(
        txid="tx_12345678-1234-4123-8123-123456789abc",
        document_id="doc",
        status="failed",
        source_sha256=digest,
        target_path="x" * 5000,
        created_at="now",
        updated_at="now",
        changed_ids=[str(index) for index in range(100)],
        error={"code": "bad", "message": "m" * 5000},
    )
    summary = transactions.transaction_response_summary(record)
    assert summary["target_path_truncated"] and summary["error"]["message_truncated"]
