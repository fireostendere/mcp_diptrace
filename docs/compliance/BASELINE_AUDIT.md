# Baseline compliance and provenance audit

## Binding

- Inspected date: `2026-08-02`.
- Exact baseline commit: `e57422e545c6b94aefe52c044c64d72a74a8c373`.
- Project version: `0.1.2` from `pyproject.toml`.
- Latest repository tag at inspection: `v0.1.2`.
- Baseline tracked-path count: 281.
- Scope: public tracked tree, release policy, public v0.1.2 assets selected
  for inspection, package metadata, fixtures, reference extracts, and
  reachable Git history.

This report contains repository facts and bounded audit observations. It is not
legal advice, an independent audit, a DipTrace permission record, a signing
record, or an OpenAI application decision.

This is a historical baseline report, not a current release manifest. Its
references to tracked extracts, source PDFs, the source-derived inventory, and
the then-installed `pypdf` dependency describe the inspected baseline only.
The current public-tree decision and replacement inventory are recorded in
[REFERENCE_MATERIALS_AUDIT.md](../REFERENCE_MATERIALS_AUDIT.md) and
[DIPTRACE_MATERIALS_STATUS.md](DIPTRACE_MATERIALS_STATUS.md).

## Repository and CI inventory

The repository contains the Python MCP server, packaged skills, Windows bridge
source and installer/settings, documentation, scripts, tests, synthetic
fixtures, evidence templates, and reference-material extracts. The CI workflow
had seven job definitions and eight matrix/run jobs at baseline:

- Linux tests on Python 3.10 and 3.13;
- Linux geometry and coverage on Python 3.12;
- Linux no-Shapely fallback on Python 3.12;
- Ruff, strict Mypy, generated-artifact, release-archive, and evidence checks;
- macOS tests and CLI/headless bridge smoke;
- Windows tests and CLI/headless bridge smoke; and
- native Windows bridge build, executable `--help` smoke, and artifact upload.

All external Actions referenced by the compliance branch are pinned to full
commit SHAs. Branch protection and GitHub rulesets are not claimed here because
they require owner-controlled settings.

## License and dependency facts

The project declares Apache-2.0 in `LICENSE`, `pyproject.toml`, and
`CITATION.cff`. Package metadata in the inspected public wheel reported
`License-Expression: Apache-2.0`. No `NOTICE` file was present at baseline.

The deterministic direct-dependency inventory is in
[dependency-inventory.json](dependency-inventory.json), with the CycloneDX
representation in [sbom.cdx.json](sbom.cdx.json) and the engineering notice
summary in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The declared groups
are:

| Group | Declared direct dependencies |
| --- | --- |
| Runtime | `mcp`, `pydantic`, `typing-extensions` |
| Geometry | `shapely` |
| Bridge | `pyinstaller` |
| Development | `hatchling`, `hypothesis`, `jsonschema`, `mypy`, `pypdf`, `pytest`, `pytest-cov`, `PyYAML`, `ruff` |
| Build | `hatchling` |

The local Python 3.12.3 development environment resolved the main runtime and
geometry packages as `mcp 1.28.1`, `pydantic 2.13.4`,
`typing-extensions 4.16.0`, and `shapely 2.1.2`. It resolved `hatchling 1.31.0`,
`pytest 8.4.2`, `ruff 0.15.21`, `mypy 1.20.2`, `pypdf 6.14.2`, `PyYAML 6.0.3`,
`hypothesis 6.161.2`, and `jsonschema 4.26.0` for development. PyInstaller
was not installed in that environment. These are environment observations,
not lockfile guarantees.

Human review remains required for transitive dependencies, the PyInstaller
bootloader exception, copyleft/special terms, license text provenance, and
every bundled native library.

## Release and packaging inventory

The historical public v0.1.2 release contained these asset types: Python wheel,
Python source distribution, Windows bridge executable, Windows plugin ZIP,
checksum manifest, acceptance record, code-review record, install guide, and
two external-announcement assets. The current repository no longer stores the
announcement drafts and the future release allowlist no longer packages them.
Existing immutable release bytes were not changed.

Selected public assets downloaded into a temporary audit directory were:

- wheel: 396,758 bytes, 79 members;
- source distribution: 878,213 bytes;
- bridge: 17,645,043 bytes, 64-bit Windows PE/PyInstaller executable;
- plugin ZIP: 17,367,697 bytes, 9 members; and
- `SHA256SUMS.txt`: 836 bytes.

The five selected assets matched their corresponding checksum-manifest entries.
The manifest also named five historical assets that were not downloaded in this
run, so a complete ten-file checksum pass is not claimed by this baseline.

The wheel shipped project Python modules, the package-owned registry, and the
eight consolidated skills; it did not vendor runtime dependencies. The plugin
ZIP contained the bridge executable, installer, four settings profiles,
`LICENSE`, exchange-path guidance, and installation guidance. Static strings in
the bridge confirmed a PyInstaller embedded archive and Python modules, but a
full PyInstaller archive listing was not available because
`pyi-archive_viewer`/PyInstaller was absent in the Linux environment.

Exact reproduction commands:

```bash
sha256sum -c SHA256SUMS.txt
unzip -l diptrace_mcp-0.1.2-py3-none-any.whl
tar -tzvf diptrace_mcp-0.1.2.tar.gz
unzip -l diptrace_mcp_windows_plugin-0.1.2.zip
pyi-archive_viewer diptrace_mcp_bridge.exe
```

The final command requires PyInstaller tooling or an equivalent PE/PyInstaller
inspection environment. Its absence is reported rather than replaced with an
invented bundle inventory.

## Documentation, reference, fixture, and evidence inventory

- The repository contains three committed per-page JSON extracts and a
  generated specification inventory. Their source PDFs are local-only ignored
  inputs. Their ownership and redistribution basis are unresolved; they are
  not treated as Apache-2.0 automatically.
- The release build policy excludes those extracts and generated inventory from
  future wheels, source distributions, and release assets. Operators can
  regenerate them locally from legitimately obtained source documents.
- Synthetic XML and JSON fixtures are labelled as MCP-generated or synthetic;
  the DipTrace 5.3 fixture tree states that no redistributable round-trip
  fixture is currently accepted.
- The evidence-capture workflow keeps private input bytes outside the
  repository and cannot grant trusted provenance. Evidence templates and
  operator procedures are project-authored public guidance.
- No tracked PDFs, DOCX files, native libraries, or executable binaries were
  present in the baseline tree. The only tracked image-like fixture was a
  synthetic SVG preview.

The detailed path/pattern assessment is in
[PROVENANCE_INVENTORY.csv](PROVENANCE_INVENTORY.csv) and the neutral reference
status is in [DIPTRACE_MATERIALS_STATUS.md](DIPTRACE_MATERIALS_STATUS.md).

## Privacy and Git history

Two ordinary forum-announcement drafts were tracked at baseline. They were
backed up locally, removed from the current branch, removed from the future
release allowlist, and replaced in public records with a neutral statement that
external announcement materials are maintained privately by the repository
owner.

Reachable history still contains those ordinary non-secret drafts, and the
historical v0.1.2 source distribution/release assets retain their original
bytes. This is **Case A: non-secret drafts only**. No tokens, API keys, signing
secrets, identity documents, private correspondence, or serious personal-data
matches were found by the targeted history searches used here. A full secret
scanner was not available, so this is not a claim of an independent secret
audit. No history rewrite was executed.

Reproduction commands:

```bash
git log --all --name-only -- docs/announcements
git rev-list --objects --all
git log --all --oneline -G '(gho_|ghp_|github_pat_|sk-|BEGIN [A-Z ]+ PRIVATE KEY)' -- .
git ls-files
git status --ignored --short
git grep -n -I -E 'OPENAI.*APPLICATION|PERMISSION_REQUEST|FORUM_ANNOUNCEMENT|HUMAN_ACTIONS_PRIVATE'
```

Unavailable optional tools at inspection: `gitleaks`, `trufflehog`,
`detect-secrets`, `scancode`, `syft`, `cyclonedx-py`, `pip-audit`, `reuse`,
and PyInstaller archive tooling. Install the selected tool in a clean audit
environment and rerun its documented command before making a stronger claim.

## HUMAN ACTION REQUIRED

- Confirm copyright and redistribution authority for every project-authored
  path and dependency notice.
- Decide whether the DipTrace reference extracts should remain in public Git or
  be removed and generated only from user-supplied local documents.
- Inspect the full PyInstaller bridge archive and record bundled native
  libraries/notices.
- Configure and protect future SignPath settings without committing identifiers
  or credentials.
- Select an independent technical/legal-compliance reviewer before claiming an
  independent review.
- Review the historical-draft exposure and decide whether any additional Git
  history action is warranted. Do not rewrite history without explicit approval.
