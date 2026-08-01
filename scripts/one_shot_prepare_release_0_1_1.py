#!/usr/bin/env python3
"""Prepare the 0.1.1 release tree, then remove this one-shot automation."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).relative_to(ROOT)
WORKFLOW = Path(".github/workflows/one-shot-release-0.1.1.yml")
VERSION = "0.1.1"
DATE = "2026-08-01"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one anchor, found {count}: {old!r}")
    write(path, content.replace(old, new, 1))


replace_once("pyproject.toml", 'version = "0.1.0"', f'version = "{VERSION}"')
replace_once(
    "src/diptrace_mcp/__init__.py",
    '__version__ = "0.1.0"',
    f'__version__ = "{VERSION}"',
)
replace_once("CITATION.cff", "version: 0.1.0", f"version: {VERSION}")
replace_once("CITATION.cff", "date-released: 2026-07-30", f"date-released: {DATE}")

changelog = read("CHANGELOG.md")
unreleased_body = """## Unreleased

### Fixed

- Preserve Windows-native live exchange paths in session metadata and derive WSL
  drive-mount paths only in memory, preventing false `applied` results against a
  phantom `C:\\mnt\\c\\...` target.
- Ignore the intentional stdout-close race used to unblock a Windows output-reader
  thread after the root process exits while a descendant inherited the pipe.

### Validation

- Completed Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance for PCB and
  Schematic apply/cancel/wrong-SHA paths, including GUI checks, independent
  save/re-export comparisons, path invariants, and connectivity/count preservation.
- Added focused unit coverage for non-WSL Windows-path refusal, relative WSL mount
  roots, POSIX-path refusal on Windows, and invalid path-platform metadata.

### Documentation

- Reconciled English and Russian readiness, testing, architecture, compatibility,
  usage, roadmap, and release-policy documentation with the 2026-07-31 evidence.
- Added a dated code-review record and live-acceptance record.
"""
release_body = unreleased_body.replace(
    "## Unreleased\n\n",
    f"## Unreleased\n\n## {VERSION} - {DATE}\n\n",
    1,
)
if changelog.count(unreleased_body) != 1:
    raise RuntimeError("CHANGELOG.md: unexpected Unreleased contents")
changelog = changelog.replace(unreleased_body, release_body, 1)
link = f"[{VERSION}]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v{VERSION}\n"
if link not in changelog:
    changelog = changelog.replace(
        "[0.1.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.0",
        link + "[0.1.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.0",
        1,
    )
write("CHANGELOG.md", changelog)

replace_once(
    "README.md",
    "Version 0.1.0 is the current release. The tag `v0.1.0`, unsigned artifacts,\n"
    "`SHA256SUMS.txt`, and the provenance record in\n"
    "[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) identify the same commit.\n",
    "Version 0.1.1 is the current development-stage release. The tag `v0.1.1`,\n"
    "unsigned artifacts, `SHA256SUMS.txt`, and the provenance record in\n"
    "[docs/releases/v0.1.1.md](docs/releases/v0.1.1.md) identify the same commit.\n",
)
replace_once(
    "README_RU.md",
    "Текущий релиз — версия 0.1.0. Tag `v0.1.0`, unsigned-артефакты,\n"
    "`SHA256SUMS.txt` и provenance-запись в\n"
    "[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) указывают на один и тот же\n"
    "commit.\n",
    "Текущий development-stage релиз — версия 0.1.1. Tag `v0.1.1`,\n"
    "unsigned-артефакты, `SHA256SUMS.txt` и provenance-запись в\n"
    "[docs/releases/v0.1.1.md](docs/releases/v0.1.1.md) указывают на один и тот же\n"
    "commit.\n",
)

replace_once(
    "docs/RELEASE_PROCESS.md",
    "Version 0.1.0 is the current release, tagged `v0.1.0` with unsigned artifacts;\n"
    "its provenance record is [releases/v0.1.0.md](releases/v0.1.0.md). CI has no\n",
    "Version 0.1.1 is the current development-stage release, tagged `v0.1.1` with\n"
    "unsigned artifacts; its provenance record is\n"
    "[releases/v0.1.1.md](releases/v0.1.1.md). CI has no\n",
)

replace_once("docs/PUBLIC_RELEASE_CHECKLIST.md", "Audited repository state: 2026-07-31.", "Audited repository state: 2026-08-01.")
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "a published 0.1.0 development-stage release with an unsigned-binary disclosure, and a completed 2026-07-31 live acceptance matrix.",
    "a published 0.1.1 development-stage release with an unsigned-binary disclosure, and a completed 2026-07-31 live acceptance matrix.",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] Citation metadata records the Apache-2.0 license and the 0.1.0 release\n      date.\n",
    "- [x] Citation metadata records the Apache-2.0 license and the 0.1.1 release\n      date.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] The changelog and release provenance consistently record `0.1.0` as the first tagged development-stage release.\n",
    "- [x] The changelog and release provenance consistently record `0.1.0` as the first tagged development-stage release and `0.1.1` as the current release.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [ ] Release commit passes every required CI job.\n",
    "- [x] Release commit passes every required CI job.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [ ] Known limitations are copied into release notes without overclaiming.\n",
    "- [x] Known limitations are copied into release notes without overclaiming.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "      see [releases/v0.1.0.md](releases/v0.1.0.md)).\n",
    "      see [releases/v0.1.1.md](releases/v0.1.1.md)).\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] A reviewed unsigned policy is disclosed for the unsigned 0.1.0\n      artifacts; no signing identity is configured yet.\n",
    "- [x] A reviewed unsigned policy is disclosed for the unsigned 0.1.1\n      artifacts; no signing identity is configured yet.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [ ] Tag, archive, wheel, binary, checksums, and release notes resolve to the\n      same commit and version.\n",
    "- [x] Tag, archive, wheel, binary, checksums, and release notes resolve to the\n      same commit and version.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] Version and frozen commit are approved (recorded in\n      [releases/v0.1.0.md](releases/v0.1.0.md)).\n",
    "- [x] Version and frozen commit are approved (recorded in\n      [releases/v0.1.1.md](releases/v0.1.1.md)).\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [ ] Tag and artifacts are published through\n      [RELEASE_PROCESS.md](RELEASE_PROCESS.md).\n",
    "- [x] Tag and artifacts are published through\n      [RELEASE_PROCESS.md](RELEASE_PROCESS.md).\n",
)

release_record = f"""# Release Record: v{VERSION}

## Identity and frozen commit

- Version: `{VERSION}`, tag: `v{VERSION}`.
- Frozen commit: the tip of `main` produced by the 0.1.1 release pull request and
  recorded in the annotated tag object `v{VERSION}`. Verify with
  `git rev-parse v{VERSION}^{{}}`.
- Artifact hashes are published as the immutable release asset
  `SHA256SUMS.txt`; verify them with `sha256sum -c SHA256SUMS.txt`.

## Scope

This patch release contains the Windows/WSL live-exchange-path fix, the Windows
inherited-stdout cleanup fix, focused cross-platform path regressions, and the
English/Russian documentation reconciliation for the completed live acceptance
campaign. It does not expand the advertised native DipTrace writer surface.

## Approvals and exception

- Release manager: [@fireostendere](https://github.com/fireostendere)
  (repository owner), {DATE}.
- Independent reviewer: none exists. The owner approves this unsigned alpha
  release under the documented solo-maintainer development-release exception.
- Private vulnerability reporting remains the security channel published in
  [SECURITY.md](../../SECURITY.md).
- No verified confidential conduct channel, signing identity, or independent
  release approver exists. The release must not be described as signed,
  independently reviewed, or production-ready.

## Verification

- The complete GitHub Actions matrix passes on the release pull-request tree:
  Linux 3.10/3.13, Linux geometry plus coverage, Linux no-Shapely fallback,
  macOS, Windows, native Windows bridge build/smoke, and static/release audit.
- Ruff, strict Mypy, generated skill contracts, the exact 159-tool snapshot,
  release allowlist, specification inventory, format coverage, probe pack,
  trust-neutral ingest, and acceptance-seed audit pass.
- The direct wheel and the wheel rebuilt from the source distribution have the
  same member set and per-member SHA-256 values.
- The frozen wheel installs into a clean environment, starts the CLI, completes
  a real MCP stdio handshake, exposes 159 tools, and answers a real tool call.
- The unsigned Windows bridge is taken from the same successful CI run that
  built and smoke-ran it with `--help`.

## Real DipTrace acceptance evidence

The 2026-07-31 DipTrace 5.2.0.4 Windows bridge ↔ WSL MCP campaign completed with
`ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for its explicit matrix:

- PCB apply, cancel, and wrong-SHA;
- Schematic apply, cancel, and wrong-SHA;
- GUI confirmation for applied changes;
- PCB Save As plus independent XML re-export and semantic comparison;
- stable connectivity/counts;
- Windows-native exchange-path metadata; and
- no phantom `C:\\mnt\\c\\...` target.

See [LIVE_ACCEPTANCE_2026-07-31.md](../LIVE_ACCEPTANCE_2026-07-31.md). This is
operator-assisted evidence for the tested topology, not proof for every MCP tool,
DipTrace version, XML object, native library writer, or optional external solver.

## Release assets

- `diptrace_mcp-{VERSION}.tar.gz` — audited Python source distribution.
- `diptrace_mcp-{VERSION}-py3-none-any.whl` — MCP server and eight packaged skills.
- `diptrace_mcp_bridge.exe` — unsigned Windows bridge built and smoke-run by CI.
- `diptrace_mcp_windows_plugin-{VERSION}.zip` — bridge, installer, four settings
  profiles, license, and live-path documentation.
- `LIVE_ACCEPTANCE_2026-07-31.md` and `CODE_REVIEW_2026-07-31.md` — scoped
  evidence records.
- `SHA256SUMS.txt` — SHA-256 manifest for every attached asset above.

## Supported environments

- Python 3.10–3.13 on Linux, macOS, and Windows for the MCP server.
- Offline XML analysis under WSL.
- Live integration on Windows 10/11 with a DipTrace build that supports
  executable XML plug-ins; the accepted host matrix includes DipTrace 5.2.0.4,
  while separate schematic evidence exists for DipTrace 5.3.0.2.

## Known limitations

- Not a replacement for the DipTrace GUI or native EDA engine.
- `get_capabilities` remains authoritative for each document and installation.
- Component and Pattern Editor bridge profiles remain read-only.
- Native Component/Pattern Library mutation and native manufacturing output are
  not claimed.
- Broad redistributable DipTrace 5.3 writer fixtures, native library writer
  acceptance, complete trust invalidation across every write path, and real
  external-solver matrices remain incomplete.
- Artifacts are unsigned and no package-index publication is performed.

## Retention and rollback

Release assets are immutable and are never replaced under the same version. A
defect requires a new version or withdrawal under
[RELEASE_PROCESS.md](../RELEASE_PROCESS.md). Security-sensitive incidents use
the private channel in [SECURITY.md](../../SECURITY.md).
"""
write(f"docs/releases/v{VERSION}.md", release_record)

# Stage the intended release tree, remove the one-shot files, and regenerate the
# exact tracked-file allowlist only after the temporary automation is absent.
subprocess.run(
    [
        "git",
        "add",
        "pyproject.toml",
        "src/diptrace_mcp/__init__.py",
        "CITATION.cff",
        "CHANGELOG.md",
        "README.md",
        "README_RU.md",
        "docs/RELEASE_PROCESS.md",
        "docs/PUBLIC_RELEASE_CHECKLIST.md",
        f"docs/releases/v{VERSION}.md",
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(["git", "rm", "--", str(SELF), str(WORKFLOW)], cwd=ROOT, check=True)
subprocess.run(
    ["python", "scripts/audit_release_artifacts.py", "--write-allowlist"],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    ["git", "add", "scripts/release_artifact_allowlist.txt"],
    cwd=ROOT,
    check=True,
)

# Fail before publication if the release identity is internally inconsistent.
assert 'version = "0.1.1"' in read("pyproject.toml")
assert '__version__ = "0.1.1"' in read("src/diptrace_mcp/__init__.py")
assert "version: 0.1.1" in read("CITATION.cff")
assert "date-released: 2026-08-01" in read("CITATION.cff")
assert "## 0.1.1 - 2026-08-01" in read("CHANGELOG.md")
assert (ROOT / "docs/releases/v0.1.1.md").is_file()
