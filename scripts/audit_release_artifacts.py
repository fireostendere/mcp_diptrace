#!/usr/bin/env python3
"""Build-artifact policy for the public wheel and source distribution."""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import stat
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable, Sequence
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).absolute().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "scripts" / "release_artifact_allowlist.txt"
ALLOWLIST_RELATIVE_PATH = ALLOWLIST_PATH.relative_to(REPO_ROOT).as_posix()

MAX_WHEEL_BYTES = 5 * 1024 * 1024
MAX_WHEEL_UNPACKED_BYTES = 10 * 1024 * 1024
MAX_SDIST_BYTES = 10 * 1024 * 1024
MAX_SDIST_UNPACKED_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1_000

_PUBLICATION_PREFIXES = (
    ".github/",
    "benchmarks/",
    "docs/",
    "examples/",
    "plugin/",
    "reference/",
    "scripts/",
    "skills/",
    "src/",
    "tests/",
)
_PUBLICATION_ROOT_NAMES = {
    ".gitattributes",
    ".gitignore",
    "AUTHORS",
    "AUTHORS.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "COPYING",
    "GOVERNANCE.md",
    "LICENSE",
    "LICENSE.md",
    "NOTICE",
    "NOTICE.md",
    "README.md",
    "README_RU.md",
    "SECURITY.md",
    "SUPPORT.md",
    "pyproject.toml",
}
_BLOCKED_PARTS = frozenset({".agents", ".codex", ".git", ".vscode", "etc"})
_BLOCKED_PREFIXES = (
    "docs/private/",
    "tests/fixtures/acceptance/",
    "reference/diptrace-xml/extracted_text/",
    "reference/diptrace-xml/sources/",
)
_BLOCKED_PATHS = frozenset()
_BLOCKED_SUFFIXES = frozenset(
    {".der", ".dll", ".docx", ".eli", ".exe", ".key", ".lib", ".p12", ".pdf", ".pem", ".pfx"}
)
_LICENSE_FILE_PREFIXES = ("LICENCE", "LICENSE", "COPYING", "NOTICE", "AUTHORS")
_REQUIRED_LICENSE_EXPRESSION = "Apache-2.0"
_BOOTSTRAP_RELEASE_FILES = frozenset(
    {
        "scripts/audit_release_artifacts.py",
        "scripts/hatch_build.py",
        "scripts/release_artifact_allowlist.txt",
        "tests/test_release_artifacts.py",
    }
)
_REQUIRED_WHEEL_FILES = frozenset(
    {
        "diptrace_mcp/__init__.py",
        "diptrace_mcp/__main__.py",
        "diptrace_mcp/bridge.py",
        "diptrace_mcp/data/trusted_provenance_registry.json",
        "diptrace_mcp/server.py",
        "diptrace_mcp/skills/catalog.json",
        "diptrace_mcp/skills/shared/result.schema.json",
    }
)
_REQUIRED_ENTRY_POINTS = {
    "diptrace-mcp": "diptrace_mcp.server:main",
    "diptrace-mcp-bridge": "diptrace_mcp.bridge:main",
}
_REQUIRED_PROJECT_URLS = {
    "Documentation": "https://github.com/fireostendere/mcp_diptrace#documentation",
    "Homepage": "https://github.com/fireostendere/mcp_diptrace",
    "Issues": "https://github.com/fireostendere/mcp_diptrace/issues",
    "Repository": "https://github.com/fireostendere/mcp_diptrace",
}


class ReleaseArtifactError(ValueError):
    """Raised when a release artifact violates the publication policy."""


def _normalized_relative_path(raw_path: str) -> str:
    if not raw_path or "\x00" in raw_path or "\\" in raw_path:
        raise ReleaseArtifactError(f"invalid archive or allowlist path: {raw_path!r}")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or raw_path != path.as_posix():
        raise ReleaseArtifactError(f"unsafe archive or allowlist path: {raw_path!r}")
    return path.as_posix()


def is_publication_safe_path(raw_path: str) -> bool:
    try:
        relative = _normalized_relative_path(raw_path)
    except ReleaseArtifactError:
        return False
    path = PurePosixPath(relative)
    folded = relative.casefold()
    if any(part.casefold() in _BLOCKED_PARTS for part in path.parts):
        return False
    if any(folded.startswith(prefix.casefold()) for prefix in _BLOCKED_PREFIXES):
        return False
    if folded in {blocked.casefold() for blocked in _BLOCKED_PATHS}:
        return False
    if path.suffix.lower() in _BLOCKED_SUFFIXES:
        return False
    if len(path.parts) == 1:
        return relative in _PUBLICATION_ROOT_NAMES
    return relative.startswith(_PUBLICATION_PREFIXES)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> tuple[str, ...]:
    if not path.is_file() or path.is_symlink():
        raise ReleaseArtifactError(f"release allowlist is missing or unsafe: {path}")
    entries: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        relative = raw_line.strip()
        if not relative or relative.startswith("#"):
            continue
        relative = _normalized_relative_path(relative)
        if not is_publication_safe_path(relative):
            raise ReleaseArtifactError(
                f"publication-unsafe path at {path}:{line_number}: {relative!r}"
            )
        if relative in seen:
            raise ReleaseArtifactError(f"duplicate path at {path}:{line_number}: {relative!r}")
        source = REPO_ROOT / relative
        if not source.is_file() or source.is_symlink():
            raise ReleaseArtifactError(f"allowlisted path is missing or unsafe: {relative!r}")
        seen.add(relative)
        entries.append(relative)
    if entries != sorted(entries):
        raise ReleaseArtifactError("release allowlist must use deterministic lexical ordering")
    if ALLOWLIST_RELATIVE_PATH not in seen:
        raise ReleaseArtifactError("release allowlist must include itself")
    return tuple(entries)


def tracked_publication_paths() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    tracked = {
        raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw and is_publication_safe_path(raw.decode("utf-8"))
    }
    # These files are untracked only while this change is being reviewed. Once committed,
    # the same comparison is exact with `git ls-files` alone.
    tracked.update(
        relative
        for relative in _BOOTSTRAP_RELEASE_FILES
        if (REPO_ROOT / relative).is_file()
    )
    return tuple(sorted(tracked))


def check_allowlist() -> dict[str, int | str]:
    actual = set(load_allowlist())
    expected = set(tracked_publication_paths())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        lines = ["release allowlist differs from publication-safe tracked files"]
        lines.extend(f"missing: {path}" for path in missing)
        lines.extend(f"extra: {path}" for path in extra)
        raise ReleaseArtifactError("\n".join(lines))
    return {"allowlisted_files": len(actual)}


def write_allowlist() -> None:
    paths = tracked_publication_paths()
    ALLOWLIST_PATH.write_text("".join(f"{path}\n" for path in paths), encoding="utf-8")


def _check_member_names(names: Sequence[str]) -> None:
    if len(names) > MAX_ARCHIVE_MEMBERS:
        raise ReleaseArtifactError(
            f"archive has {len(names)} members; limit is {MAX_ARCHIVE_MEMBERS}"
        )
    if len(names) != len(set(names)):
        raise ReleaseArtifactError("archive contains duplicate member names")
    folded: dict[str, str] = {}
    for name in names:
        normalized = _normalized_relative_path(name.rstrip("/"))
        previous = folded.setdefault(normalized.casefold(), normalized)
        if previous != normalized:
            raise ReleaseArtifactError(
                f"archive has a case-insensitive path collision: {previous!r}, {normalized!r}"
            )


def _expected_wheel_files(allowlist: Iterable[str]) -> set[str]:
    expected: set[str] = set()
    for relative in allowlist:
        if relative.startswith("src/diptrace_mcp/"):
            expected.add(relative.removeprefix("src/"))
        elif relative.startswith("skills/"):
            expected.add(f"diptrace_mcp/{relative}")
    return expected


def _root_license_files(allowlist: Iterable[str]) -> tuple[str, ...]:
    """Root files that Hatch copies into the wheel's ``dist-info/licenses/``."""
    return tuple(
        sorted(
            relative
            for relative in allowlist
            if "/" not in relative and relative.startswith(_LICENSE_FILE_PREFIXES)
        )
    )


def _check_record(archive: zipfile.ZipFile, record_name: str, names: set[str]) -> None:
    rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    recorded_names = {row[0] for row in rows}
    if recorded_names != names:
        raise ReleaseArtifactError("wheel RECORD does not enumerate the exact archive contents")
    for name, digest, size in rows:
        if not digest:
            if name != record_name or size:
                raise ReleaseArtifactError(f"unexpected unhashed RECORD entry: {name!r}")
            continue
        algorithm, expected_digest = digest.split("=", 1)
        payload = archive.read(name)
        actual_digest = (
            base64.urlsafe_b64encode(hashlib.new(algorithm, payload).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        if actual_digest != expected_digest or len(payload) != int(size):
            raise ReleaseArtifactError(f"wheel RECORD mismatch: {name!r}")


def audit_wheel(path: Path, allowlist: Sequence[str] | None = None) -> dict[str, int | str]:
    allowlist = tuple(allowlist or load_allowlist())
    if path.stat().st_size > MAX_WHEEL_BYTES:
        raise ReleaseArtifactError(f"wheel exceeds {MAX_WHEEL_BYTES} bytes: {path.stat().st_size}")

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        _check_member_names(names)
        unpacked_bytes = sum(info.file_size for info in infos if not info.is_dir())
        if unpacked_bytes > MAX_WHEEL_UNPACKED_BYTES:
            raise ReleaseArtifactError(
                f"wheel expands to {unpacked_bytes} bytes; limit is {MAX_WHEEL_UNPACKED_BYTES}"
            )
        for info in infos:
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ReleaseArtifactError(
                    f"wheel contains a non-regular member: {info.filename!r}"
                )

        files = {info.filename for info in infos if not info.is_dir()}
        dist_info_roots = {
            name.split("/", 1)[0] for name in files if ".dist-info/" in name
        }
        if len(dist_info_roots) != 1:
            raise ReleaseArtifactError("wheel must contain exactly one .dist-info directory")
        dist_info = dist_info_roots.pop()
        license_files = _root_license_files(allowlist)
        generated = {
            f"{dist_info}/METADATA",
            f"{dist_info}/RECORD",
            f"{dist_info}/WHEEL",
            f"{dist_info}/entry_points.txt",
        } | {f"{dist_info}/licenses/{name}" for name in license_files}
        expected = _expected_wheel_files(allowlist) | generated
        if files != expected:
            unexpected = sorted(files - expected)
            missing = sorted(expected - files)
            raise ReleaseArtifactError(
                "wheel contents differ from the allowlist; "
                f"unexpected={unexpected}, missing={missing}"
            )
        missing_required = sorted(_REQUIRED_WHEEL_FILES - files)
        if missing_required:
            raise ReleaseArtifactError(f"wheel is missing required files: {missing_required}")

        metadata = BytesParser(policy=default).parsebytes(
            archive.read(f"{dist_info}/METADATA")
        )
        if metadata["Name"] != "diptrace-mcp":
            raise ReleaseArtifactError(f"unexpected wheel project name: {metadata['Name']!r}")
        project_urls = {}
        for value in metadata.get_all("Project-URL", []):
            label, url = value.split(",", 1)
            project_urls[label.strip()] = url.strip()
        if project_urls != _REQUIRED_PROJECT_URLS:
            raise ReleaseArtifactError(f"wheel Project-URL metadata differs: {project_urls}")
        if metadata["License-Expression"] != _REQUIRED_LICENSE_EXPRESSION:
            raise ReleaseArtifactError(
                f"unexpected wheel License-Expression: {metadata['License-Expression']!r}"
            )
        if set(metadata.get_all("License-File", [])) != set(license_files):
            raise ReleaseArtifactError(
                f"wheel License-File metadata differs: {metadata.get_all('License-File', [])}"
            )
        if "LICENSE" in license_files and archive.read(
            f"{dist_info}/licenses/LICENSE"
        ) != (REPO_ROOT / "LICENSE").read_bytes():
            raise ReleaseArtifactError("wheel license file differs from the committed LICENSE")
        empty_legacy_extras = {"preview", "routing", "simulation"} & set(
            metadata.get_all("Provides-Extra", [])
        )
        if empty_legacy_extras:
            raise ReleaseArtifactError(
                f"wheel still publishes empty legacy extras: {sorted(empty_legacy_extras)}"
            )

        parser = configparser.ConfigParser()
        parser.read_string(archive.read(f"{dist_info}/entry_points.txt").decode("utf-8"))
        entry_points = dict(parser["console_scripts"])
        if entry_points != _REQUIRED_ENTRY_POINTS:
            raise ReleaseArtifactError(f"unexpected console entry points: {entry_points}")

        catalog = json.loads(archive.read("diptrace_mcp/skills/catalog.json"))
        expected_skill_files = {
            f"diptrace_mcp/skills/{item['slug']}/SKILL.md" for item in catalog
        }
        if len(expected_skill_files) != 8 or not expected_skill_files <= files:
            raise ReleaseArtifactError(
                "wheel must contain exactly the eight catalogued skill packages"
            )
        _check_record(archive, f"{dist_info}/RECORD", files)

    return {
        "artifact": path.name,
        "files": len(files),
        "packed_bytes": path.stat().st_size,
        "unpacked_bytes": unpacked_bytes,
    }


def audit_sdist(path: Path, allowlist: Sequence[str] | None = None) -> dict[str, int | str]:
    allowlist = tuple(allowlist or load_allowlist())
    if path.stat().st_size > MAX_SDIST_BYTES:
        raise ReleaseArtifactError(f"sdist exceeds {MAX_SDIST_BYTES} bytes: {path.stat().st_size}")

    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        _check_member_names(names)
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ReleaseArtifactError("sdist must contain exactly one top-level directory")
        root = roots.pop()
        unpacked_bytes = 0
        files: set[str] = set()
        for member in members:
            if member.isdir():
                continue
            if not member.isfile():
                raise ReleaseArtifactError(f"sdist contains a non-regular member: {member.name!r}")
            unpacked_bytes += member.size
            files.add(member.name)
        if unpacked_bytes > MAX_SDIST_UNPACKED_BYTES:
            raise ReleaseArtifactError(
                f"sdist expands to {unpacked_bytes} bytes; limit is {MAX_SDIST_UNPACKED_BYTES}"
            )

        expected = {f"{root}/{relative}" for relative in allowlist}
        expected.add(f"{root}/PKG-INFO")
        if files != expected:
            unexpected = sorted(files - expected)
            missing = sorted(expected - files)
            raise ReleaseArtifactError(
                "sdist contents differ from the allowlist; "
                f"unexpected={unexpected}, missing={missing}"
            )
        for member_name in files:
            relative = member_name.removeprefix(f"{root}/")
            if relative != "PKG-INFO" and not is_publication_safe_path(relative):
                raise ReleaseArtifactError(f"sdist contains a blocked path: {relative!r}")

    return {
        "artifact": path.name,
        "files": len(files),
        "packed_bytes": path.stat().st_size,
        "unpacked_bytes": unpacked_bytes,
    }


def _one_artifact(dist_dir: Path, pattern: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        raise ReleaseArtifactError(
            f"expected exactly one {pattern!r} artifact in {dist_dir}, found {len(matches)}"
        )
    return matches[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--check-allowlist", action="store_true")
    parser.add_argument("--write-allowlist", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.write_allowlist:
        write_allowlist()
        print(f"Wrote {ALLOWLIST_PATH.relative_to(REPO_ROOT)}")
        if not (args.dist_dir or args.wheel or args.sdist or args.check_allowlist):
            return 0

    reports: list[dict[str, int | str]] = []
    if args.check_allowlist:
        reports.append(check_allowlist())

    wheel = args.wheel
    sdist = args.sdist
    if args.dist_dir:
        wheel = wheel or _one_artifact(args.dist_dir, "*.whl")
        sdist = sdist or _one_artifact(args.dist_dir, "*.tar.gz")
    if wheel:
        reports.append(audit_wheel(wheel))
    if sdist:
        reports.append(audit_sdist(sdist))
    if not reports:
        raise ReleaseArtifactError("select an artifact or an allowlist operation")

    print(json.dumps({"ok": True, "reports": reports}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ReleaseArtifactError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
