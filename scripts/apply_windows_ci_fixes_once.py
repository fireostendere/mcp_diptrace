#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if old not in content:
        raise SystemExit(f"expected text not found in {path}: {old[:80]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> None:
    validate_old = (
        "def validate_candidate(capture_root: Path, manifest_relative: Path) -> ValidatedCandidate:\n"
        "    expected_candidates = Path(STORE_NAME) / \"candidates\"\n"
    )
    validate_new = (
        "def validate_candidate(capture_root: Path, manifest_relative: Path) -> ValidatedCandidate:\n"
        "    capture_root = _existing_root(capture_root, role=\"capture root\")\n"
        "    expected_candidates = Path(STORE_NAME) / \"candidates\"\n"
    )
    for path in (
        "scripts/ingest_fixtures.py",
        "skills/diptrace-evidence-capture/scripts/ingest_fixtures.py",
    ):
        replace(path, validate_old, validate_new)

    digest_old = '''    manifest_path.with_name(manifest_path.name + ".sha256").write_text(\n        f"{manifest_sha}  {manifest_path.name}\\n",\n        encoding="ascii",\n    )\n'''
    digest_new = '''    manifest_path.with_name(manifest_path.name + ".sha256").write_bytes(\n        f"{manifest_sha}  {manifest_path.name}\\n".encode("ascii")\n    )\n'''
    replace("tests/test_ingest_fixtures.py", digest_old, digest_new)

    ps_anchor = '''function Assert-CopiedFile {\n'''
    ps_helper = '''function Get-Sha256Hex {\n    param(\n        [Parameter(Mandatory = $true)]\n        [string]$Path\n    )\n\n    $Stream = [IO.File]::OpenRead($Path)\n    try {\n        $Hasher = [Security.Cryptography.SHA256]::Create()\n        try {\n            $Digest = $Hasher.ComputeHash($Stream)\n        }\n        finally {\n            $Hasher.Dispose()\n        }\n    }\n    finally {\n        $Stream.Dispose()\n    }\n    return ([BitConverter]::ToString($Digest)).Replace("-", "")\n}\n\nfunction Assert-CopiedFile {\n'''
    replace("plugin/install_plugin.ps1", ps_anchor, ps_helper)
    replace(
        "plugin/install_plugin.ps1",
        '''    $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash\n    $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash\n''',
        '''    $SourceHash = Get-Sha256Hex -Path $Source\n    $DestinationHash = Get-Sha256Hex -Path $Destination\n''',
    )
    replace(
        "tests/test_plugin_settings.py",
        '''    assert "Get-FileHash -LiteralPath" in script\n''',
        '''    assert "Get-Sha256Hex" in script\n    assert "[Security.Cryptography.SHA256]::Create()" in script\n''',
    )

    replace(
        "tests/test_probe_pack.py",
        '''    output.write_text("stale\\n", encoding="utf-8")\n''',
        '''    output.write_bytes(b"stale\\n")\n''',
    )

    replace(
        ".gitattributes",
        "* text=auto\n",
        "* text=auto eol=lf\n",
    )

    subprocess.run(
        ["python", "scripts/generate_pcb_skills.py"],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
