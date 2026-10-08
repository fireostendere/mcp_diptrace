from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import evidence_report, record_ids
from diptrace_mcp.domain import FixtureValidationLevel
from diptrace_mcp.provenance_registry import (
    TrustedProvenanceRegistry,
    TrustedProvenanceRegistryEntry,
    TrustedProvenanceRegistryFile,
    canonical_registry_bytes,
)


def _entry(entry_id: str = "entry") -> TrustedProvenanceRegistryEntry:
    return TrustedProvenanceRegistryEntry(
        entry_id=entry_id,
        document_sha256="a" * 64,
        evidence_manifest_sha256="b" * 64,
        evidence_manifest_source="evidence.json",
        source_type="DipTrace-PCB",
        validation_level=FixtureValidationLevel.diptrace_exported,
    )


def test_record_store_path_failures_are_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    store = state / "store"
    state.mkdir()
    store.symlink_to(state, target_is_directory=True)
    with pytest.raises(record_ids.InvalidRecordPath, match="redirected"):
        record_ids.prepare_safe_store_root(state, store)

    real_store = state / "real"
    real_store.mkdir()
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
    )
    with pytest.raises(record_ids.InvalidRecordPath, match="safely confined"):
        record_ids.require_safe_store_root(state, real_store)


def test_record_link_detection_windows_and_junction_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePath:
        def __init__(self, *, attributes: int = 0, lstat_error: Exception | None = None):
            self.attributes = attributes
            self.lstat_error = lstat_error

        def is_symlink(self) -> bool:
            return False

        def lstat(self) -> object:
            if self.lstat_error:
                raise self.lstat_error
            return SimpleNamespace(st_file_attributes=self.attributes)

        def is_junction(self) -> bool:
            raise OSError("denied")

    monkeypatch.setattr(record_ids, "os", SimpleNamespace(name="nt"))
    assert record_ids.is_link_like(FakePath(attributes=0x400)) is True  # type: ignore[arg-type]
    assert record_ids.is_link_like(FakePath(lstat_error=OSError("bad"))) is True  # type: ignore[arg-type]
    assert record_ids.is_link_like(FakePath(lstat_error=FileNotFoundError())) is True  # type: ignore[arg-type]


def test_confined_paths_reject_unsafe_roots_and_resolution_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    file = root / "file.json"
    file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(record_ids, "is_link_like", lambda path: path == root)
    with pytest.raises(record_ids.InvalidRecordPath, match="safe directory"):
        record_ids.require_confined_file(root, file)

    monkeypatch.setattr(record_ids, "is_link_like", lambda _path: False)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
    )
    with pytest.raises(record_ids.InvalidRecordPath, match="outside"):
        record_ids.require_confined_file(root, file)
    job = root / ("job_" + "a" * 32)
    job.mkdir()
    with pytest.raises(record_ids.InvalidRecordPath, match="outside"):
        record_ids.require_confined_record_directory(root, job.name, kind="job")


def test_provenance_models_and_registry_input_failures(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="high-trust"):
        TrustedProvenanceRegistryEntry.model_validate(
            {**_entry().model_dump(), "validation_level": "synthetic_parser_only"}
        )

    first = _entry("b")
    second = _entry("a").model_copy(update={"document_sha256": "c" * 64})
    with pytest.raises(ValueError, match="sorted"):
        TrustedProvenanceRegistryFile(entries=[first, second])
    with pytest.raises(ValueError, match="entry_id"):
        TrustedProvenanceRegistryFile(entries=[_entry(), _entry()])
    duplicate_binding = _entry("other")
    with pytest.raises(ValueError, match="bindings"):
        TrustedProvenanceRegistryFile(entries=[_entry(), duplicate_binding])

    for raw, message in (
        (b"{", "Invalid trusted"),
        (b"{}", "not canonical"),
    ):
        with pytest.raises(ValueError, match=message):
            TrustedProvenanceRegistry.from_bytes(raw, source_label="test")
    registry = TrustedProvenanceRegistryFile(entries=[_entry()])
    raw = canonical_registry_bytes(registry)
    with pytest.raises(ValueError, match="requires"):
        TrustedProvenanceRegistry.from_bytes(raw, source_label="test")
    with pytest.raises(ValueError, match="Cannot read"):
        TrustedProvenanceRegistry.from_bytes(
            raw,
            source_label="test",
            evidence_source_reader=lambda _path: (_ for _ in ()).throw(OSError("bad")),
        )
    with pytest.raises(ValueError, match="SHA mismatch"):
        TrustedProvenanceRegistry.from_bytes(
            raw,
            source_label="test",
            evidence_source_reader=lambda _path: b"wrong",
        )
    registry_path = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="Cannot read trusted"):
        TrustedProvenanceRegistry.from_path(registry_path)


def test_evidence_candidate_and_path_validation(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.json"
    for value, message in (
        (b"{", "Invalid evidence"),
        (b"[]", "must use schema"),
        (json.dumps({"schema_version": "wrong"}).encode(), "must use schema"),
        (
            json.dumps(
                {
                    "schema_version": "diptrace-capture-candidate-v1",
                    "trust_grant": "trusted",
                    "candidate_only": True,
                }
            ).encode(),
            "review-only",
        ),
    ):
        candidate.write_bytes(value)
        with pytest.raises(ValueError, match=message):
            evidence_report._load_candidate(candidate)

    assert evidence_report._mapping([]) == {}
    for relative in ("../outside", "/absolute"):
        with pytest.raises(ValueError, match="Unsafe"):
            evidence_report._safe_relative(tmp_path, relative)
    outside = tmp_path / "outside"
    outside.write_text("x", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        evidence_report._safe_relative(root, "link")
