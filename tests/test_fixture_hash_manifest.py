from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_fixture_hash_manifest import (
    HEADER_LINES,
    FixtureManifestError,
    parse_manifest,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_fixture_hash_manifest.py"
SHA = "a" * 64
HEADER = "\n".join(HEADER_LINES) + "\n"


def test_committed_fixture_hash_manifest_is_current() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_fixture_manifest_rejects_path_traversal() -> None:
    content = HEADER + f"{SHA}  tests/fixtures/../outside.xml\n"
    with pytest.raises(FixtureManifestError, match="escapes"):
        parse_manifest(content)


def test_fixture_manifest_rejects_duplicate_paths() -> None:
    line = f"{SHA}  tests/fixtures/pcb.xml\n"
    with pytest.raises(FixtureManifestError, match="duplicate"):
        parse_manifest(HEADER + line + line)


def test_fixture_hashes_preserve_line_endings(tmp_path: Path) -> None:
    lf = tmp_path / "lf.xml"
    crlf = tmp_path / "crlf.xml"
    lf.write_bytes(b"<Source>\n</Source>\n")
    crlf.write_bytes(b"<Source>\r\n</Source>\r\n")
    assert sha256_file(lf) != sha256_file(crlf)
