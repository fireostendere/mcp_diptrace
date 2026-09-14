"""Fail-safe branches of the offline backup store: unreadable, corrupt and
redirected state must never be deleted and never crash retention."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from diptrace_mcp.backups import BackupStore, backup_target_key, canonical_target_path
from diptrace_mcp.errors import EditError
from diptrace_mcp.retention import RetentionCandidate, RetentionPolicy

_BAK = "backup.20260101T120000.000000Z.{}.{}.bak".format("a" * 64, "b" * 32)
_BAD_STAMP = "backup.20261345T121530.000000Z.{}.{}.bak".format("a" * 64, "b" * 32)


def _clock() -> datetime:
    return datetime(2026, 1, 31, tzinfo=timezone.utc)


def _store(state: Path, **kwargs: object) -> BackupStore:
    return BackupStore(state, clock=_clock, **kwargs)  # type: ignore[arg-type]


def _craft_history(root: Path, target: Path) -> tuple[Path, str, str]:
    """Create a metadata-only history directory bound to ``target``."""

    canonical = canonical_target_path(target)
    key = backup_target_key(canonical)
    history = root / key
    history.mkdir(parents=True, exist_ok=True)
    (history / "target.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_key": key,
                "canonical_target_path": canonical,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return history, key, canonical


def test_write_with_backup_reports_unreadable_target(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    directory = tmp_path / "dir-target"
    directory.mkdir()

    with pytest.raises(EditError, match="Cannot read target before backup"):
        store.write_with_backup(directory, b"data")


def test_backups_for_unknown_target_without_history_is_empty(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")

    assert store.backups_for(tmp_path / "missing.xml") == ()


def test_binding_scan_skips_histories_with_invalid_metadata(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")

    root = state / "offline_backups"
    junk = root / ("c" * 64)
    junk.mkdir()
    (junk / "target.json").write_text("{", encoding="utf-8")

    try:
        linked = tmp_path / "board-link.xml"
        os.link(target, linked)
    except OSError:
        pytest.skip("hard links are unavailable")

    # The junk history is skipped during the samefile scan; the real history
    # is still found through the alternative path identity.
    assert store.backups_for(linked) == (backup,)


def test_binding_scan_survives_samefile_errors(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    root = state / "offline_backups"
    ghost = tmp_path / "ghost.xml"
    _craft_history(root, ghost)

    real = tmp_path / "real.xml"
    real.write_bytes(b"<Source/>")

    # samefile() against the ghost's recorded path raises; the scan must
    # continue and fall back to the default binding.
    assert store.backups_for(real) == ()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_write_refuses_redirected_history_directory(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    outside = tmp_path / "outside-history"
    shutil.move(str(history), str(outside))
    history.symlink_to(outside, target_is_directory=True)

    with pytest.raises(EditError, match="redirected"):
        store.write_with_backup(target, b"again")


def test_file_in_place_of_backup_root_keeps_startup_read_only(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "offline_backups").write_text("not a directory", encoding="utf-8")

    store = _store(state)

    assert store.last_retention_reports == {}
    assert store._safe_root() is False


def test_unreadable_backup_root_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    store.write_with_backup(target, b"changed")
    root = state / "offline_backups"
    root.chmod(0o000)
    try:
        reopened = _store(state)
        assert reopened.last_retention_reports == {}
        # The binding scan cannot list the root either and must fail closed.
        assert reopened.backups_for(target) == ()
    finally:
        root.chmod(0o755)


def test_history_can_expire_treats_unreadable_history_as_expirable(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    history.chmod(0o000)
    try:
        assert store._history_can_expire(history) is True
    finally:
        history.chmod(0o755)


def test_history_can_expire_falls_back_on_unparsable_stamp(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    (history / _BAD_STAMP).write_bytes(b"x")

    assert store._history_can_expire(history) is True


def test_remove_empty_history_keeps_corrupt_binding(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    key = history.name
    canonical = canonical_target_path(target)
    (history / "target.json").write_text("{", encoding="utf-8")

    store._remove_empty_history(history, key, canonical)

    assert history.exists()


def test_remove_empty_history_restores_binding_when_rmdir_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    key = history.name
    canonical = canonical_target_path(target)
    backup.unlink()
    metadata = history / "target.json"
    before = metadata.read_bytes()

    original_rmdir = pathlib.Path.rmdir

    def failing_rmdir(self: Path) -> None:
        if self == history:
            raise OSError("device busy")
        original_rmdir(self)

    monkeypatch.setattr(pathlib.Path, "rmdir", failing_rmdir)
    store._remove_empty_history(history, key, canonical)

    assert history.is_dir()
    assert metadata.read_bytes() == before


def test_candidates_glob_failure_yields_no_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    store.write_with_backup(target, b"changed")

    original_glob = pathlib.Path.glob

    def failing_glob(self: Path, pattern: str):
        if pattern == "backup.*.bak":
            raise OSError("device not ready")
        return original_glob(self, pattern)

    monkeypatch.setattr(pathlib.Path, "glob", failing_glob)

    assert store.backups_for(target) == ()


def test_malformed_backup_names_are_not_candidates(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    (history / "backup.junk.bak").write_bytes(b"x")
    (history / _BAD_STAMP).write_bytes(b"x")

    assert store.backups_for(target) == (backup,)


def test_unreadable_backup_content_is_not_a_recovery_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")

    original_read_bytes = pathlib.Path.read_bytes

    def failing_read_bytes(self: Path) -> bytes:
        if self.name == backup.name:
            raise OSError("input/output error")
        return original_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", failing_read_bytes)

    assert store.backups_for(target) == ()


def test_record_is_intact_rejects_non_record_names(tmp_path: Path) -> None:
    store = _store(tmp_path / "state")
    candidate = RetentionCandidate(
        identifier="backup.junk.bak",
        path=tmp_path / "backup.junk.bak",
        timestamp=_clock(),
    )

    assert store._record_is_intact(candidate) is False


def test_metadata_validation_rejects_bad_key_json_and_schema(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")
    backup = store.write_with_backup(target, b"changed")
    history = backup.parent
    metadata = history / "target.json"

    # Key is not a 64-hex digest.
    assert store._validated_target_metadata(history, "zz") is None

    # Corrupt JSON.
    metadata.write_text("{", encoding="utf-8")
    assert store._validated_target_metadata(history, history.name) is None

    # Valid JSON, wrong schema version.
    metadata.write_text("[]", encoding="utf-8")
    assert store._validated_target_metadata(history, history.name) is None


def test_safe_root_rejects_missing_state_directory(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = _store(state)
    assert store._safe_root() is True

    shutil.rmtree(state)

    assert store._safe_root() is False


def test_naive_clock_is_normalized_to_utc(tmp_path: Path) -> None:
    state = tmp_path / "state"
    naive = datetime(2026, 1, 1)
    store = BackupStore(
        state,
        retention=RetentionPolicy(max_records=10, max_age_days=30),
        clock=lambda: naive,
    )
    target = tmp_path / "board.xml"
    target.write_bytes(b"original")

    backup = store.write_with_backup(target, b"changed")

    assert store.backups_for(target) == (backup,)
    assert backup.name.startswith("backup.20260101T000000.000000Z.")
