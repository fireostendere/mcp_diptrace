from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import diptrace_mcp.retention as retention


def test_retention_policy_and_timestamp_validation() -> None:
    with pytest.raises(ValueError, match="max_records"):
        retention.RetentionPolicy(max_records=0)
    with pytest.raises(ValueError, match="max_age_days"):
        retention.RetentionPolicy(max_age_days=0)

    assert retention.parse_retention_timestamp(None) is None
    assert retention.parse_retention_timestamp(123) is None
    assert retention.parse_retention_timestamp("") is None
    assert retention.parse_retention_timestamp("not-a-date") is None
    assert retention.parse_retention_timestamp("2026-01-01T00:00:00") is None
    parsed = retention.parse_retention_timestamp("2026-01-01T01:00:00+01:00")
    assert parsed == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retention.system_clock().tzinfo is not None


def test_prune_handles_age_count_protection_files_and_directories(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = state / "records"
    store.mkdir(parents=True)
    old_file = store / "old.json"
    count_file = store / "count.json"
    protected = store / "protected.json"
    directory = store / "directory"
    old_file.write_text("old", encoding="utf-8")
    count_file.write_text("count", encoding="utf-8")
    protected.write_text("protected", encoding="utf-8")
    directory.mkdir()
    (directory / "nested.txt").write_text("nested", encoding="utf-8")

    candidates = [
        retention.RetentionCandidate(
            "old",
            old_file,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
        retention.RetentionCandidate(
            "count",
            count_file,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        retention.RetentionCandidate(
            "protected",
            protected,
            datetime(2020, 1, 2, tzinfo=timezone.utc),
        ),
        retention.RetentionCandidate(
            "dir",
            directory,
            datetime(2020, 1, 3, tzinfo=timezone.utc),
        ),
    ]
    report = retention.prune_terminal_records(
        state_root=state,
        store_root=store,
        candidates=candidates,
        policy=retention.RetentionPolicy(max_records=1, max_age_days=30),
        clock=lambda: datetime(2026, 2, 1),
        protected_paths=[protected],
    )

    assert old_file in report.removed
    assert directory in report.removed
    assert not old_file.exists()
    assert not directory.exists()
    assert protected.exists()
    assert count_file.exists() or count_file in report.removed


def test_prune_refuses_unsafe_roots_and_candidates(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    candidate = outside / "record.json"
    candidate.write_text("x", encoding="utf-8")

    assert retention.prune_terminal_records(
        state_root=state,
        store_root=outside,
        candidates=[
            retention.RetentionCandidate(
                "outside",
                candidate,
                datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        ],
        policy=retention.RetentionPolicy(max_records=1, max_age_days=1),
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    ).removed == ()
    assert candidate.exists()

    store = state / "records"
    store.mkdir()
    nested = store / "nested" / "record.json"
    nested.parent.mkdir()
    nested.write_text("x", encoding="utf-8")
    assert retention._safe_candidate_path(state, store, nested) is False
    assert retention._safe_candidate_path(state, store, store / "missing.json") is False


def test_tree_link_detection_and_resolve_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert retention._tree_contains_link_like(file_path) is False

    directory = tmp_path / "tree"
    directory.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("x", encoding="utf-8")
    link = directory / "link.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    assert retention._tree_contains_link_like(directory) is True

    original = Path.resolve

    def fail_resolve(path: Path, *, strict: bool = False) -> Path:
        if path == file_path and strict:
            raise OSError("no resolve")
        return original(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    assert retention._resolved_if_possible(file_path) == file_path


def test_prune_ignores_delete_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "state"
    store = state / "records"
    store.mkdir(parents=True)
    record = store / "old.json"
    record.write_text("x", encoding="utf-8")

    def refuse_unlink(_path: Path) -> None:
        raise OSError("busy")

    monkeypatch.setattr(Path, "unlink", refuse_unlink)
    report = retention.prune_terminal_records(
        state_root=state,
        store_root=store,
        candidates=[
            retention.RetentionCandidate(
                "old",
                record,
                datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        ],
        policy=retention.RetentionPolicy(max_records=1, max_age_days=1),
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert report.removed == ()
    assert record.exists()
