from __future__ import annotations

from pathlib import Path

import pytest

import diptrace_mcp.record_ids as record_ids
from diptrace_mcp.record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    iter_valid_record_files,
    prepare_safe_store_root,
    require_confined_file,
    require_confined_record_artifact,
    require_confined_record_directory,
    require_confined_record_file,
    require_record_id,
    require_safe_store_root,
)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("transaction", "tx_00000000-0000-4000-8000-000000000000"),
        ("preview", "preview_" + "0" * 32),
        ("job", "job_" + "0" * 32),
        ("plan", "plan_" + "0" * 32),
        ("export", "export_" + "0" * 32),
        ("session", "00000000-0000-4000-8000-000000000000"),
        ("report", "report_" + "0" * 16),
        ("finding", "finding_" + "0" * 16),
    ],
)
def test_record_id_patterns_accept_exact_generated_shapes(kind: str, value: str) -> None:
    assert require_record_id(value, kind) == value  # type: ignore[arg-type]
    with pytest.raises(InvalidRecordId):
        require_record_id(value + "x", kind)  # type: ignore[arg-type]


def test_store_root_preparation_and_validation_fail_closed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = state / "jobs"

    assert prepare_safe_store_root(state, store) == store
    assert require_safe_store_root(state, store) == store

    with pytest.raises(InvalidRecordPath, match="direct child"):
        prepare_safe_store_root(state, state / "nested" / "jobs")

    file_state = tmp_path / "state-file"
    file_state.write_text("not-a-directory", encoding="utf-8")
    with pytest.raises(InvalidRecordPath, match="cannot be prepared safely"):
        prepare_safe_store_root(file_state, file_state / "jobs")

    with pytest.raises(InvalidRecordPath, match="not a safe directory"):
        require_safe_store_root(state, state / "missing")


def test_confined_file_and_record_helpers_cover_success_and_rejection(tmp_path: Path) -> None:
    root = tmp_path / "records"
    root.mkdir()
    report_id = "report_" + "a" * 16
    report = root / f"{report_id}.json"
    report.write_text("{}", encoding="utf-8")

    assert require_confined_file(root, report) == report
    assert require_confined_record_file(root, report_id, kind="report") == report

    with pytest.raises(FileNotFoundError):
        require_confined_file(root, root / "missing.json")
    with pytest.raises(InvalidRecordPath, match="not a regular file"):
        require_confined_file(root, root)

    job_id = "job_" + "b" * 32
    job_dir = root / job_id
    job_dir.mkdir()
    manifest = job_dir / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    assert require_confined_record_directory(root, job_id, kind="job") == job_dir
    assert (
        require_confined_record_file(
            root,
            job_id,
            kind="job",
            record_filename="manifest.json",
        )
        == manifest
    )
    assert require_confined_record_artifact(root, job_id, "manifest.json", kind="job") == manifest

    for artifact_name in ("", "../manifest.json", "nested/manifest.json"):
        with pytest.raises(InvalidRecordPath, match="artifact name is invalid"):
            require_confined_record_artifact(root, job_id, artifact_name, kind="job")

    with pytest.raises(InvalidRecordPath, match="directory is unsafe"):
        require_confined_record_directory(root, "job_" + "c" * 32, kind="job")


def test_confined_helpers_reject_redirect_signals_without_real_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "records"
    root.mkdir()
    file = root / ("report_" + "d" * 16 + ".json")
    file.write_text("{}", encoding="utf-8")

    original = record_ids.is_link_like
    monkeypatch.setattr(
        record_ids,
        "is_link_like",
        lambda path: path == file or original(path),
    )
    with pytest.raises(InvalidRecordPath, match="redirected"):
        require_confined_file(root, file)


def test_iter_valid_record_files_filters_malformed_and_misplaced_paths(tmp_path: Path) -> None:
    root = tmp_path / "records"
    root.mkdir()
    valid_id = "report_" + "e" * 16
    valid = root / f"{valid_id}.json"
    valid.write_text("{}", encoding="utf-8")
    malformed = root / "report_bad.json"
    malformed.write_text("{}", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    misplaced = nested / f"{valid_id}.json"
    misplaced.write_text("{}", encoding="utf-8")

    assert list(iter_valid_record_files(root, [valid, malformed, misplaced], kind="report")) == [
        (valid_id, valid)
    ]

    job_id = "job_" + "f" * 32
    job_dir = root / job_id
    job_dir.mkdir()
    manifest = job_dir / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    other = job_dir / "other.json"
    other.write_text("{}", encoding="utf-8")

    assert list(
        iter_valid_record_files(
            root,
            [manifest, other],
            kind="job",
            record_filename="manifest.json",
        )
    ) == [(job_id, manifest)]

    missing_root = tmp_path / "missing"
    assert list(iter_valid_record_files(missing_root, [valid], kind="report")) == []
