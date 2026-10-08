from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp.domain import ExportRecord
from diptrace_mcp.errors import ObjectNotFoundError
from diptrace_mcp.exports import ExportStore, placement_csv


def _snapshot():
    return SimpleNamespace(
        info=SimpleNamespace(document_id="doc", sha256="a" * 64),
        board=SimpleNamespace(components=[]),
    )


def test_export_store_create_validation_and_read_failures(tmp_path: Path) -> None:
    store = ExportStore(tmp_path / "state", 3)
    for artifacts, message in (
        ({"../bad": b"x"}, "Invalid export artifact"),
        ({"large": b"1234"}, "size limit"),
    ):
        with pytest.raises(ValueError, match=message):
            store.create(_snapshot(), "bom", artifacts, {}, [])
    with pytest.raises(ObjectNotFoundError, match="Invalid export id"):
        store.read("bad")
    missing_id = "export_" + "a" * 32
    with pytest.raises(ObjectNotFoundError, match="not found"):
        store.read(missing_id)

    corrupt_id = "export_" + "b" * 32
    directory = store.root / corrupt_id
    directory.mkdir()
    (directory / "record.json").write_text("{", encoding="utf-8")
    with pytest.raises(ObjectNotFoundError, match="corrupt"):
        store.read(corrupt_id)


def test_export_artifact_bounds_and_listing_filter_corrupt_records(tmp_path: Path) -> None:
    store = ExportStore(tmp_path / "state", 10)
    record = store.create(_snapshot(), "bom", {"bom.csv": b"ok"}, {}, [])
    with pytest.raises(ObjectNotFoundError, match="artifact was not found"):
        store.artifact(record.export_id, "missing")
    artifact = store.root / record.export_id / "bom.csv"
    artifact.write_bytes(b"x" * 11)
    with pytest.raises(ValueError, match="read limit"):
        store.artifact(record.export_id, "bom.csv")

    record_path = store.root / record.export_id / "record.json"
    wrong = ExportRecord.model_validate_json(record_path.read_bytes()).model_copy(
        update={"export_id": "export_" + "c" * 32}
    )
    record_path.write_text(wrong.model_dump_json(), encoding="utf-8")
    assert store.list() == []


def test_export_manifest_integrity_and_non_pcb_placement(tmp_path: Path) -> None:
    store = ExportStore(tmp_path / "state", 1_000)
    manifest = {"schema_version": 2, "artifact_integrity": {}}
    record = store.create(
        _snapshot(),
        "bom",
        {"manifest.json": json.dumps(manifest).encode(), "data.txt": b"x"},
        manifest,
        [],
    )
    (store.root / record.export_id / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest integrity"):
        store.artifact(record.export_id, "manifest.json")
    with pytest.raises(ValueError, match="artifact integrity"):
        store.artifact(record.export_id, "data.txt")
    assert placement_csv(SimpleNamespace(board=None)) == b""
