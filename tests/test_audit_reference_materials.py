import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_reference_materials.py"


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _run(root: Path, *, sample_count: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(root),
            "--sample-per-kind",
            str(sample_count),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_inventory_hashes_documents_and_samples_binary_libraries(tmp_path: Path) -> None:
    secret = b"do-not-copy-this-source-body"
    component_small = b"\x06DTELIB" + b"a"
    component_large = b"\x06DTELIB" + b"b" * 10
    pattern = b"\x06DTCLIB" + b"c"
    _write(tmp_path / "notes" / "source.md", secret)
    _write(tmp_path / "comps" / "small.eli", component_small)
    _write(tmp_path / "comps" / "large.eli", component_large)
    _write(tmp_path / "patterns" / "one.lib", pattern)

    result = _run(tmp_path, sample_count=1)

    library_bytes = len(component_small) + len(component_large) + len(pattern)
    assert result["scope"] == {
        "bytes": len(secret) + library_bytes,
        "documentation_bytes": len(secret),
        "documentation_file_count": 1,
        "file_count": 4,
        "legacy_library_bytes": library_bytes,
        "legacy_library_file_count": 3,
        "other_bytes": 0,
        "other_file_count": 0,
        "root_name": tmp_path.name,
        "skipped_symlinks": [],
    }
    documents = result["documentation"]
    assert isinstance(documents, list)
    assert documents == [
        {
            "path": "notes/source.md",
            "sha256": hashlib.sha256(secret).hexdigest(),
            "size_bytes": len(secret),
        }
    ]
    samples = result["legacy_library_samples"]
    assert isinstance(samples, dict)
    assert samples[".eli"]["population_count"] == 2
    assert samples[".eli"]["population_magic_counts"] == {
        "legacy_component_library_binary": 2
    }
    assert len(samples[".eli"]["sample"]) == 1
    assert samples[".lib"]["population_magic_counts"] == {
        "legacy_pattern_library_binary": 1
    }
    assert secret.decode() not in json.dumps(result)
    assert result["disclosure"]["source_bytes_embedded"] is False
    assert result["disclosure"]["all_legacy_libraries_hashed"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation requires privileges")
def test_inventory_skips_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "redirect.md").symlink_to(outside)

    result = _run(tmp_path, sample_count=0)

    assert result["scope"]["skipped_symlinks"] == ["redirect.md"]
    assert result["scope"]["file_count"] == 0
    assert result["scope"]["documentation_file_count"] == 0
    assert result["scope"]["legacy_library_file_count"] == 0
    assert result["documentation"] == []
