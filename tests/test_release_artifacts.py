from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.audit_release_artifacts import (
    REPO_ROOT,
    ReleaseArtifactError,
    _check_member_names,
    audit_sdist,
    check_allowlist,
    is_publication_safe_path,
    load_allowlist,
)


def test_release_allowlist_matches_publication_safe_tracked_files() -> None:
    report = check_allowlist()

    assert report["allowlisted_files"] > 200


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".vscode/settings.json",
        "etc/private-library.eli",
        "docs/private/operator-notes.md",
        "reference/diptrace-xml/extracted_text/DipTraceXML_Pcb_En.pages.json",
        "reference/diptrace-xml/spec_inventory.json",
        "tests/fixtures/acceptance/diptrace_5_3/real-board.xml",
        "plugin/dist/diptrace_mcp_bridge.exe",
        "../outside.txt",
        "/absolute.txt",
    ],
)
def test_publication_policy_rejects_private_or_unsafe_paths(path: str) -> None:
    assert is_publication_safe_path(path) is False


def test_release_allowlist_contains_build_hook_and_auditor() -> None:
    paths = set(load_allowlist())

    assert "scripts/audit_release_artifacts.py" in paths
    assert "scripts/hatch_build.py" in paths
    assert "scripts/release_artifact_allowlist.txt" in paths


def test_project_license_is_apache2_and_allowlisted() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'license = "Apache-2.0"' in pyproject
    assert (REPO_ROOT / "LICENSE").is_file()
    assert "LICENSE" in set(load_allowlist())


def test_archive_name_guard_rejects_traversal_and_case_collisions() -> None:
    with pytest.raises(ReleaseArtifactError, match="unsafe"):
        _check_member_names(["pkg/../private.txt"])
    with pytest.raises(ReleaseArtifactError, match="case-insensitive"):
        _check_member_names(["pkg/README.md", "pkg/readme.md"])


def _write_minimal_sdist(path: Path, *, unsafe_member: tarfile.TarInfo | None = None) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in (
            ("diptrace_mcp-0.1.0/README.md", b"readme"),
            ("diptrace_mcp-0.1.0/PKG-INFO", b"metadata"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if unsafe_member is not None:
            archive.addfile(unsafe_member)


def test_sdist_audit_accepts_exact_regular_file_set(tmp_path: Path) -> None:
    artifact = tmp_path / "diptrace_mcp-0.1.0.tar.gz"
    _write_minimal_sdist(artifact)

    report = audit_sdist(artifact, allowlist=("README.md",))

    assert report["files"] == 2


def test_sdist_audit_rejects_symlinks(tmp_path: Path) -> None:
    artifact = tmp_path / "diptrace_mcp-0.1.0.tar.gz"
    link = tarfile.TarInfo("diptrace_mcp-0.1.0/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "README.md"
    _write_minimal_sdist(artifact, unsafe_member=link)

    with pytest.raises(ReleaseArtifactError, match="non-regular"):
        audit_sdist(artifact, allowlist=("README.md",))


def test_hatch_build_hook_excludes_dirty_untracked_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for relative in load_allowlist():
        source = REPO_ROOT / relative
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    dirty_files = (
        project / ".vscode" / "settings.json",
        project / "etc" / "private-library.eli",
        project / "src" / "diptrace_mcp" / "untracked.py",
        project / "skills" / "untracked" / "SKILL.md",
    )
    for dirty in dirty_files:
        dirty.parent.mkdir(parents=True, exist_ok=True)
        dirty.write_text("must not ship", encoding="utf-8")

    dist = tmp_path / "dist"
    completed = subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-d", str(dist)],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
        # pytest-cov exports a relative source root for child processes. Hatch
        # changes cwd to this temporary project, which would make coverage
        # count the copied package as an unexecuted second source tree.
        env={key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_")},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    sdist = next(dist.glob("*.tar.gz"))
    with tarfile.open(sdist, "r:*") as archive:
        sdist_names = set(archive.getnames())
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())

    for dirty in dirty_files:
        relative = dirty.relative_to(project).as_posix()
        assert not any(name.endswith(relative) for name in sdist_names)
        assert not any(name.endswith(relative) for name in wheel_names)
