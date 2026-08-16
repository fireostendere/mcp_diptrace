from pathlib import Path
import re

root = Path('.')


def read(path: str) -> str:
    return (root / path).read_text(encoding='utf-8')


def write(path: str, text: str) -> None:
    (root / path).write_text(text, encoding='utf-8')


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f'{path}: expected replacement anchor not found')
    write(path, text.replace(old, new, 1))


readme = read('README.md')
start = readme.index('## Current status\n')
end = readme.index('\n## Public Release Status\n', start)
current_status = '''## Current status

Version `0.4.0` is the current published unsigned development release. The
immutable GitHub release is `v0.4.0`, and the matching Python package is
`diptrace-mcp==0.4.0` on PyPI.

The published release keeps the public MCP contract frozen at 167 tools and
contains the A1-A8 roadmap closure plus tested cross-platform host paths:

- Windows split per-user/admin installers and portable bundle;
- Ubuntu 24.04 x86-64 one-command deployment with Wine and private-Xvfb GUI
  isolation;
- macOS 15 one-command deployment on Apple Silicon and Intel using the official
  DipTrace.app bundled Wine runtime and hidden-Win32-desktop automation.

Published `v0.4.0` GitHub assets are:

- `DipTrace-MCP-Setup-0.4.0.exe`;
- `DipTrace-MCP-Plugin-Setup-0.4.0.exe`;
- `DipTrace-MCP-Portable-0.4.0.zip`;
- `SHA256SUMS.txt`.

The v0.4.0 MCPB/registry preparation gate passed before release, but no v0.4.0
MCPB was attached to the public GitHub release. Do not infer an unpublished
bundle from preparation-only CI evidence; the older published MCPB identity
remains a separate historical distribution line.

The Windows executables are unsigned. CI, SHA-256, PyPI Trusted Publishing and
package attestations establish tested behaviour, byte identity and publication
provenance. They do not create a trusted Authenticode signature, universal
compatibility, independent review or production readiness.

`main` may contain post-release hardening that is not part of immutable
`v0.4.0`; use the tag when reproducibility matters.
'''
readme = readme[:start] + current_status + readme[end:]
readme = readme.replace(
    'https://raw.githubusercontent.com/fireostendere/mcp_diptrace/main/scripts/install_linux.sh',
    'https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_linux.sh',
)
readme = readme.replace(
    'https://raw.githubusercontent.com/fireostendere/mcp_diptrace/main/scripts/install_macos.sh',
    'https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_macos.sh',
)
readme = readme.replace('After v0.4.0 publication:\n', '')
write('README.md', readme)

roadmap = read('docs/ROADMAP.md')
rstart = roadmap.index('## Current checkpoint — 2026-08-16\n')
rend = roadmap.index('\nThe schematic-quality production fixes were merged by PR #90.', rstart)
checkpoint = '''## Current checkpoint — 2026-08-17

The current source/package version is `0.4.0`. Version `v0.4.0` is the current published
unsigned development release. Its annotated tag targets
`b4c0132283ff16a0bca81567df6704d1f6a73c7f`; the GitHub release and
`diptrace-mcp==0.4.0` PyPI package are public immutable identities.

The exact pre-release cross-platform candidate
`72750d195e204cf0c11c04d71364055ca7634c6b` passed the Windows, Linux, macOS,
PyPI-validation, MCPB/registry-preparation and repository-CI gates before the
release/tag sequence. Preparation-only MCPB evidence did not publish a v0.4.0
MCPB asset.

Current `main` may contain post-release documentation/release-pipeline hardening
that is intentionally not part of the immutable `v0.4.0` bytes. Historical
release and acceptance evidence stays bound to the identity actually tested.
'''
roadmap = roadmap[:rstart] + checkpoint + roadmap[rend:]
write('docs/ROADMAP.md', roadmap)

replace_once(
    'CHANGELOG.md',
    'Version `0.4.0` is the current unsigned development release candidate.',
    'Version `0.4.0` is the current published unsigned development release.',
)
changelog = read('CHANGELOG.md')
marker = '### Added\n'
insertion = '''### Publication

- Published as annotated tag `v0.4.0` with GitHub release ID `371451484`.
- Published `diptrace-mcp==0.4.0` to PyPI through OIDC Trusted Publishing; both
  wheel and source distribution returned `200 OK` and received attestations.
- Published Windows per-user installer, administrator plug-in installer,
  portable bundle and `SHA256SUMS.txt`; a v0.4.0 MCPB was not attached.
- Linux/macOS release installation is bootstrapped from the immutable v0.4.0
  installer scripts rather than from moving `main`.

'''
pos = changelog.index(marker, changelog.index('## 0.4.0 - 2026-08-16'))
changelog = changelog[:pos] + insertion + changelog[pos:]
write('CHANGELOG.md', changelog)

next_text = read('CHANGELOG_NEXT.md')
next_text = next_text.replace(
    '# 0.4.0 release candidate\n',
    '# Post-v0.4.0 development\n\nThe immutable `v0.4.0` GitHub release and PyPI package were published on 2026-08-16.\nChanges in this section are later development and are not silently part of those released bytes.\n',
    1,
)
write('CHANGELOG_NEXT.md', next_text)

process = read('docs/RELEASE_PROCESS.md')
pstart = process.index('## Current release status\n')
pend = process.index('\n## Historical release evidence versus current manual evidence\n', pstart)
status = '''## Current release status

`v0.4.0` is the current published unsigned development release.

Immutable/current published identities:

- annotated tag: `v0.4.0`;
- tag object: `3794c32c7d94456aec2ed358326e953e21e3fa21`;
- exact tag target: `b4c0132283ff16a0bca81567df6704d1f6a73c7f`;
- exact pre-release candidate: `72750d195e204cf0c11c04d71364055ca7634c6b`;
- GitHub release ID: `371451484`;
- PyPI package: `diptrace-mcp==0.4.0`;
- PyPI publish workflow run: `31976705280`;
- Windows installer: `DipTrace-MCP-Setup-0.4.0.exe`;
- administrator plug-in installer: `DipTrace-MCP-Plugin-Setup-0.4.0.exe`;
- portable bundle: `DipTrace-MCP-Portable-0.4.0.zip`;
- Linux/macOS bootstrap scripts: immutable `v0.4.0` tag paths.

A v0.4.0 MCPB was not attached to the GitHub release. The MCPB/registry workflow
for the candidate was a preparation/validation gate only and must not be
represented as published v0.4.0 bytes.

The completed release checklist and publication evidence are recorded in
[RELEASE_0_4_0_CHECKLIST.md](RELEASE_0_4_0_CHECKLIST.md) and
[releases/v0.4.0.md](releases/v0.4.0.md). Older release records remain immutable
historical identities.

Future releases use two reusable boundaries instead of version-specific one-shot
workflows:

- `.github/workflows/pypi.yml` accepts an annotated `v*` tag only when it exactly
  matches the version in `pyproject.toml`, builds/audits wheel+sdist separately,
  then publishes through the protected `pypi` environment and OIDC;
- `.github/workflows/release.yml` is an explicit dispatch that requires the exact
  annotated tag plus a successful `Windows one-click installer` run whose
  `head_sha` equals the tag target. It refuses to replace an existing release.

Windows executables remain unsigned. CI, SHA-256, PyPI Trusted Publishing and
package attestations establish tested behaviour, byte identity and publication
provenance; they do not establish Authenticode trust, universal compatibility,
independent review or production readiness.
'''
process = process[:pstart] + status + process[pend:]
write('docs/RELEASE_PROCESS.md', process)

distribution = read('docs/MCP_DISTRIBUTION.md')
dstart = distribution.index('## Current published state\n')
dend = distribution.index('\n## Distribution roles\n', dstart)
current = '''## Current published state

Version `v0.4.0` is the current published unsigned development release.

Published immutable identities:

- GitHub release: `v0.4.0` (ID `371451484`);
- PyPI package: `diptrace-mcp==0.4.0`;
- Windows installer: `DipTrace-MCP-Setup-0.4.0.exe`;
- administrator plug-in installer: `DipTrace-MCP-Plugin-Setup-0.4.0.exe`;
- portable bundle: `DipTrace-MCP-Portable-0.4.0.zip`;
- checksum manifest: `SHA256SUMS.txt`;
- Linux/macOS host bootstrap: the `v0.4.0` installer scripts.

No `DipTrace-MCP-0.4.0-windows.mcpb` asset was published. The candidate MCPB and
registry workflow passed as preparation evidence only; the latest published MCPB
line remains historical and must not be mixed with v0.4.0 runtime/bridge claims.

Published tags/files are immutable. A corrected build requires a new version.
Development on `main` after `v0.4.0` may contain changes not present in the
published package/bundles; track them in `CHANGELOG_NEXT.md` until the next
version is selected.
'''
distribution = distribution[:dstart] + current + distribution[dend:]
distribution = distribution.replace(
    '`0.3.0` was published through the guarded GitHub OIDC workflow after an exact\nannotated-tag checkout and target verification.',
    '`0.4.0` was published through the guarded GitHub OIDC workflow after an exact\nannotated-tag checkout and target verification.',
)
distribution = distribution.replace('diptrace-mcp==0.3.0', 'diptrace-mcp==0.4.0')
distribution = distribution.replace(
    'The `v0.3.0` publication is complete; these are future-release rules, not\npending `0.3.0` publication steps.',
    'The `v0.4.0` publication is complete; these are future-release rules, not\npending `0.4.0` publication steps.',
)
distribution = distribution.replace(
    '--version 0.3.0 \\\n  --commit fbbbda176043c555b04a908bb63f6fc4ac5909cb',
    '--version 0.4.0 \\\n  --commit b4c0132283ff16a0bca81567df6704d1f6a73c7f',
)
distribution = re.sub(
    r'## Published release versus current `main`\n.*?\n## Immutability rule',
    '''## Published release versus current `main`

Do not conflate these states:

- `v0.4.0` / PyPI `0.4.0` are immutable published bytes with the A1-A8 roadmap
  closure and bounded Windows/Linux/macOS host paths described by its release
  record;
- later `main` may advance independently;
- a future release must explicitly package/re-verify later changes before
  distribution docs claim they are in published artifacts.

## Immutability rule''',
    distribution,
    count=1,
    flags=re.S,
)
distribution = distribution.replace('## v0.4.0 host installers', '## v0.4.0 published host installers')
distribution = distribution.replace('The v0.4.0 release candidate adds two host bootstrap paths', 'The published v0.4.0 release adds two host bootstrap paths')
write('docs/MCP_DISTRIBUTION.md', distribution)

install = '''# Install from Published Release Assets

## Current published release

Version `v0.4.0` is the current published GitHub/PyPI distribution line. Keep
every downloaded artifact on the same immutable version and verify checksums
before execution.

Published GitHub assets:

```text
DipTrace-MCP-Setup-0.4.0.exe
DipTrace-MCP-Plugin-Setup-0.4.0.exe
DipTrace-MCP-Portable-0.4.0.zip
SHA256SUMS.txt
```

Published PyPI artifacts:

```text
diptrace_mcp-0.4.0-py3-none-any.whl
diptrace_mcp-0.4.0.tar.gz
```

A v0.4.0 MCPB was not attached to this release. Do not invent or mix an older
MCPB with the v0.4.0 bridge/runtime identity.

## Linux one-command installation

Validated release path: Ubuntu/Debian-style x86-64, with Ubuntu 24.04 used by the
permanent clean-install gate.

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_linux.sh \\
  | bash -s -- --accept-diptrace-license
```

The installer verifies the v0.4.0 portable bundle/checksum manifest, installs the
pinned DipTrace/Wine path after explicit license acceptance, installs bridge and
wrappers, and provides visible plus private-Xvfb headless GUI modes. See
[LINUX.md](LINUX.md).

## macOS one-command installation

The tested macOS 15 path covers Apple Silicon and Intel and uses the Wine runtime
bundled in the official DipTrace.app:

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_macos.sh \\
  | bash -s -- --accept-diptrace-license
```

On Apple Silicon without Rosetta, after reviewing Apple's terms, add
`--accept-rosetta-license`. See [MACOS.md](MACOS.md).

## PyPI

Python 3.10 or newer:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.4.0
diptrace-mcp --help
```

The Python package contains the MCP server and packaged skills. It does not
silently install the native DipTrace bridge plug-in.

`0.4.0` was published through GitHub OIDC Trusted Publishing. That establishes
publication provenance, not Authenticode trust, universal compatibility or
production readiness.

## Verify GitHub release hashes

Download `SHA256SUMS.txt` from the same `v0.4.0` GitHub release.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

PowerShell for an individual file:

```powershell
Get-FileHash .\\DipTrace-MCP-Setup-0.4.0.exe -Algorithm SHA256
```

The digest must match the release manifest. A matching SHA-256 proves byte
identity, not publisher signing.

## Recommended Windows installation

1. Close affected DipTrace modules and the MCP client being configured.
2. Verify the installer hash from the same v0.4.0 release.
3. Run `DipTrace-MCP-Setup-0.4.0.exe` normally for the per-user MCP
   server/configurator.
4. Run `DipTrace-MCP-Plugin-Setup-0.4.0.exe` separately with administrator
   privileges when machine-wide DipTrace integration is required.
5. Restart DipTrace and the configured MCP client.
6. Call `get_capabilities` before relying on document-specific paths.

Windows binaries remain unsigned, so SmartScreen may warn. Workspaces and user
state are preserved by default on uninstall; owned-state removal is explicit.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.4.0.zip` against `SHA256SUMS.txt`.
2. Extract it to a stable local directory.
3. Read `README_FIRST.txt` and verify the internal checksums.
4. Run the included helper/configuration path as appropriate.
5. Restart the MCP client and call `get_capabilities`.

A separate Python installation is not required for the frozen Windows runtime.

## Exact released source

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
git checkout v0.4.0
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

A checkout of current `main` may contain post-release changes not present in
published v0.4.0 bytes. Use the tag when reproducibility matters.

## Evidence and limitations

The v0.4.0 release is backed by exact-candidate Windows, Ubuntu 24.04, macOS
Apple Silicon/Intel and package validation gates plus the recorded historical
manual DipTrace evidence. Those are bounded claims, not universal compatibility.

The project still does not claim trusted Authenticode signing, native
manufacturing sign-off, Novarm/DipTrace endorsement, independent review,
field-solver/PI/EMC/thermal sign-off or production readiness.

Runtime `get_capabilities` remains authoritative for an installed build and
active document.
'''
write('docs/INSTALL_FROM_RELEASE.md', install)

windows = read('docs/WINDOWS_INSTALLER.md')
wstart = windows.index('## Status\n')
wend = windows.index('\n## Design goals\n', wstart)
wstatus = '''## Status

The immutable `v0.4.0` unsigned development release is the current published
Windows distribution. It preserves the hardened split-privilege architecture:

- `DipTrace-MCP-Setup-0.4.0.exe` — per-user server/configurator installer;
- `DipTrace-MCP-Plugin-Setup-0.4.0.exe` — administrator-only DipTrace plug-in
  installer with a self-contained bridge/settings payload;
- `DipTrace-MCP-Portable-0.4.0.zip`;
- `SHA256SUMS.txt`.

The Windows binaries remain unsigned. Older published assets retain their own
immutable identities/checksums and are never replaced by later versions.
'''
windows = windows[:wstart] + wstatus + windows[wend:]
windows = windows.replace(
    'The current workflow and installer-script default are aligned to `0.4.0` for\nthis release candidate. Future releases must select their own new version.',
    'The published v0.4.0 workflow/build identity remains immutable. Future releases\nmust select a new version and produce a new exact-tag artifact run.',
)
write('docs/WINDOWS_INSTALLER.md', windows)

release_record = '''# Release Record: v0.4.0

## Published identity

- Version: `0.4.0`.
- Status: **PUBLISHED — unsigned development release**.
- Published: `2026-08-16T22:34:44Z`.
- Annotated tag: `v0.4.0`.
- Annotated-tag object SHA: `3794c32c7d94456aec2ed358326e953e21e3fa21`.
- Tag target: `b4c0132283ff16a0bca81567df6704d1f6a73c7f`.
- Exact cross-platform pre-release candidate:
  `72750d195e204cf0c11c04d71364055ca7634c6b`.
- GitHub release ID: `371451484`.
- GitHub release workflow run: `31976705266`.
- PyPI project/version: `diptrace-mcp==0.4.0`.
- PyPI Trusted Publishing workflow run: `31976705280`.
- Release manager: repository owner `fireostendere` under the documented
  solo-maintainer exception.
- Independent reviewer: none recorded.

The published tag and release/PyPI bytes are immutable. Post-release repository
changes do not move the tag or replace published bytes.

## Scope

Version `0.4.0` packages the A1-A8 roadmap closure and tested cross-platform
installation/GUI paths while keeping the public MCP contract at 167 tools.

Included changes include guarded whole-board PCB plan/apply, source-bound rule
and physics evidence, topology-preserving schematic reroute, confidence-gated
rotation candidates, evidence campaigns, Linux one-command installation with
private-Xvfb headless GUI, and macOS one-command installation using the official
DipTrace.app bundled Wine runtime on Apple Silicon and Intel.

## Final pre-release gates

Exact candidate `72750d195e204cf0c11c04d71364055ca7634c6b` completed:

- PyPI validation: run `31974338002` — PASS;
- MCPB/registry preparation: run `31974338015` — PASS (preparation only);
- macOS one-command install: run `31974338039` — PASS;
- Windows one-click installer: run `31974338063` — PASS;
- Linux one-command install: run `31974338096` — PASS;
- repository CI: run `31974338117` — PASS.

The accepted project-level manual matrix remains 12/12 PASS across its recorded
historical checkpoints. Those results remain exact-checkpoint evidence rather
than being silently transferred to unrelated future changes.

## Published GitHub assets

| Asset | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `DipTrace-MCP-Setup-0.4.0.exe` | 56,482,464 | `c4b9ae77028c85131c0c9ffb145d21b6eb55e86e9fdc0c7e43ec8025b7a96a37` |
| `DipTrace-MCP-Plugin-Setup-0.4.0.exe` | 19,045,882 | `b5862f45dc9b188e64a9f7b4ee56dc204fef5a3d06d89f14a77af4281a6ca0a2` |
| `DipTrace-MCP-Portable-0.4.0.zip` | 95,678,071 | `5eda04ab86e6b99a3ca4edad17f8e868142d8b1176c9d7d01842f8c887db0e79` |
| `SHA256SUMS.txt` | 298 | `ab5b4066ffa7e0f95a15e43ccecbb7d84841e679f12af3051517c281eb3a741d` |

No `DipTrace-MCP-0.4.0-windows.mcpb` was published. MCPB/registry preparation
passed as a validation gate but did not create a public v0.4.0 MCPB asset.

## Published PyPI artifacts

The OIDC publish job returned `200 OK` for both distributions and generated
Sigstore/PyPI attestations:

- `diptrace_mcp-0.4.0-py3-none-any.whl` —
  `5e0aa2c4a15252ee299093c9e169e813c9bc07f54e6358c742760caa6fafcabc`;
- `diptrace_mcp-0.4.0.tar.gz` —
  `2704fbf47d43dccad7726a9effd4ae954e38e007430895c21e615e48f38e5b8d`.

## Platform evidence

- **Windows:** split per-user/admin installer, portable bundle, frozen server,
  bridge, lifecycle, stdio and headless helper checks.
- **Linux:** Ubuntu 24.04 x86-64 clean installation; Wine; DipTrace 5.3.0.3;
  frozen MCP stdio; shared-prefix bridge; real Schematic GUI liveness under
  private Xvfb; headless worker and idempotent reinstall.
- **macOS Apple Silicon / Intel:** macOS 15 clean installation using the official
  DipTrace 5.3.0.3 app, bundled Wine, Rosetta where needed, MCP/bridge liveness,
  real Schematic GUI, hidden Win32 desktop worker, doctor and idempotent install.

The macOS hosted gate proves GUI liveness/isolation/readiness, not a universal
native `.dch`/`.dip` Save/Close/Reopen claim.

## Post-publication verification

The GitHub API release object confirms the four uploaded assets and their
server-reported SHA-256 digests. The PyPI publication workflow confirms successful
HTTP `200 OK` uploads for the wheel and source distribution and records their
hashes/attestations.

An additional independent redownload-and-install smoke from a separate network
path is not recorded in this release record yet. It remains useful verification
debt but does not change the immutable identities above.

## Known limitations

- Windows executables remain unsigned development artifacts.
- Linux/macOS gates establish the exact tested host/runtime paths, not universal
  compatibility with every distribution/macOS/DipTrace version.
- Headless GUI isolation is not a process/filesystem/network/token/privilege
  sandbox.
- Native manufacturing generation, production readiness, Novarm/DipTrace
  endorsement, field-solver accuracy, PI/EMC/thermal sign-off and universal
  compatibility are not claimed.
'''
write('docs/releases/v0.4.0.md', release_record)

checklist = '''# v0.4.0 Release Checklist

Version: `0.4.0`  
Tag: `v0.4.0`  
Release class: published unsigned development release  
Release manager: `fireostendere` (solo-maintainer exception)

## Source and contract

- [x] Version `0.4.0` selected without reusing an existing tag/version.
- [x] Public MCP surface remained frozen at 167 tools.
- [x] A1-A8 implementation stayed behind existing guarded semantic boundaries.
- [x] Exact cross-platform candidate frozen at `72750d195e204cf0c11c04d71364055ca7634c6b`.
- [x] Release tag target frozen at `b4c0132283ff16a0bca81567df6704d1f6a73c7f`.

## Documentation and repository quality

- [x] README, roadmap, platform, testing, release and distribution docs synchronized.
- [x] Linux and macOS one-command/visible/headless guides exist.
- [x] Changelog and v0.4.0 release record exist.
- [x] `check_documentation_state.py` and release metadata checks passed on the candidate.
- [x] Linux 3.10/3.13, Linux geometry/fallback, macOS and Windows test jobs passed.
- [x] Combined supported-environment coverage, Ruff, Mypy and DCO passed.
- [x] Release/privacy/provenance/compliance/event-loop/artifact audits passed.
- [x] Frozen 167-tool public contract check passed.
- [x] PyPI wheel/sdist build, audit and clean-install smoke passed.
- [x] MCPB/registry preparation passed as validation-only evidence.

## Platform gates

- [x] Windows split installer/portable build and lifecycle smoke passed (run `31974338063`).
- [x] Ubuntu 24.04 x86-64 one-command install, Wine/DipTrace GUI, bridge, private-Xvfb
  headless worker and idempotent reinstall passed (run `31974338096`).
- [x] macOS 15 Apple Silicon and Intel clean install, official DMG verification,
  bundled Wine, bridge, real GUI, hidden desktop/doctor and idempotent reinstall
  passed (run `31974338039`).
- [x] Repository CI passed on the exact candidate (run `31974338117`).

## Publication

- [x] Created immutable annotated `v0.4.0` tag object
  `3794c32c7d94456aec2ed358326e953e21e3fa21`.
- [x] Tag points to exact release target `b4c0132283ff16a0bca81567df6704d1f6a73c7f`.
- [x] GitHub release `v0.4.0` published (release ID `371451484`, workflow
  `31976705266`).
- [x] Published per-user installer, administrator plug-in installer, portable ZIP
  and one `SHA256SUMS.txt`; recorded final sizes/hashes.
- [x] Published `diptrace-mcp==0.4.0` through PyPI OIDC Trusted Publishing
  (workflow `31976705280`).
- [x] PyPI returned HTTP `200 OK` for wheel and sdist and generated attestations.
- [x] GitHub API release metadata confirms uploaded asset digests.
- [ ] Independent public-byte redownload plus reinstall/smoke from a separate
  network path is not yet recorded.
- [x] Immutable publication fields are filled in `docs/releases/v0.4.0.md`.

## Publication boundary

No v0.4.0 MCPB was attached to the public release. Preparation-only MCPB evidence
must not be promoted to a published-asset claim. Existing `v0.4.0` GitHub/PyPI
bytes are immutable; corrections require a new version.
'''
write('docs/RELEASE_0_4_0_CHECKLIST.md', checklist)

allowlist = read('scripts/release_artifact_allowlist.txt')
allowlist = allowlist.replace('.github/workflows/release-v0.4.0.yml\n', '')
allowlist = allowlist.replace('.github/workflows/tag-v0.4.0-on-main.yml\n', '')
if '.github/workflows/release.yml\n' not in allowlist:
    allowlist = allowlist.replace('.github/workflows/pypi.yml\n', '.github/workflows/pypi.yml\n.github/workflows/release.yml\n')
write('scripts/release_artifact_allowlist.txt', allowlist)

checker = read('scripts/check_documentation_state.py')
checker = checker.replace(
    '"docs/RELEASE_PROCESS.md": ("v0.4.0", "RELEASE_0_4_0_CHECKLIST.md"),',
    '"docs/RELEASE_PROCESS.md": ("v0.4.0", "published", ".github/workflows/release.yml"),',
)
anchor = 'STALE_PHRASES: dict[str, tuple[str, ...]] = {'
insert = '''PUBLISHED_RELEASE_DOCS = (
    "README.md",
    "CHANGELOG.md",
    "docs/ROADMAP.md",
    "docs/RELEASE_PROCESS.md",
    "docs/MCP_DISTRIBUTION.md",
    "docs/INSTALL_FROM_RELEASE.md",
    "docs/WINDOWS_INSTALLER.md",
)

PUBLISHED_RELEASE_STALE_PHRASES = (
    "version `v0.3.0` is the current published",
    "version `0.4.0` is the current unsigned development release candidate",
    "`v0.4.0` is the current release candidate",
    "release candidate — not yet published",
)

'''
if 'PUBLISHED_RELEASE_DOCS = (' not in checker:
    checker = checker.replace(anchor, insert + anchor, 1)
block_anchor = '    headless_doc = _read_text(root, "docs/HEADLESS_GUI.md", errors)\n'
published_block = '''    try:
        release_state = json.loads((root / "release.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"release.json: cannot parse published state: {exc}")
        release_state = {}
    if str(release_state.get("release_status", "")).startswith("published-"):
        version = str(release_state.get("version", ""))
        for relative in PUBLISHED_RELEASE_DOCS:
            text = _read_text(root, relative, errors)
            normalized = _normalized(text)
            if version and version not in text:
                errors.append(f"{relative}: published release version {version} is missing")
            if "published" not in normalized:
                errors.append(f"{relative}: published release state is not documented")
            for phrase in PUBLISHED_RELEASE_STALE_PHRASES:
                if _normalized(phrase) in normalized:
                    errors.append(f"{relative}: contains stale published-release claim: {phrase}")

'''
if 'release_state = json.loads' not in checker:
    checker = checker.replace(block_anchor, published_block + block_anchor, 1)
write('scripts/check_documentation_state.py', checker)

tests = read('tests/test_ci_workflow.py')
pattern = re.compile(r'def test_pypi_workflow_builds_before_a_minimal_oidc_publish_job\(\) -> None:\n.*\Z', re.S)
replacement = '''def test_pypi_workflow_builds_before_a_minimal_oidc_publish_job() -> None:
    workflow_path = ROOT / ".github/workflows/pypi.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    assert '      - "v*"' in workflow_text
    assert "workflow_run:" not in workflow_text
    assert 'RELEASE_VERSION: "0.4.0"' not in workflow_text
    assert 'RELEASE_TAG: "v0.4.0"' not in workflow_text

    build = jobs["build"]
    build_commands = _job_commands(build)
    checkout_ref = build["steps"][0]["with"]["ref"]
    assert "github.ref_name" in checkout_ref
    assert "inputs.tag" in checkout_ref
    assert "tomllib" in build_commands
    assert "RELEASE_VERSION" in build_commands
    assert "RELEASE_TAG" in build_commands
    assert "git cat-file -t" in build_commands
    assert "git rev-parse HEAD" in build_commands
    assert "python -m hatchling build -d dist" in build_commands
    assert "audit_release_artifacts.py --dist-dir dist --check-allowlist" in build_commands
    assert "python -m twine check --strict dist/*" in build_commands
    assert "diptrace_mcp.__version__" in build_commands

    publish = jobs["publish"]
    assert "workflow_run" not in publish["if"]
    assert "github.event_name == 'push'" in publish["if"]
    assert "inputs.publish == true" in publish["if"]
    assert publish["needs"] == "build"
    assert publish["environment"] == {
        "name": "pypi",
        "url": "https://pypi.org/p/diptrace-mcp",
    }
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert len(publish["steps"]) == 2
    assert publish["steps"][1]["uses"] == (
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
    )
    assert "password:" not in workflow_text
    assert "username:" not in workflow_text


def test_generic_github_release_workflow_is_exact_tag_and_immutable_safe() -> None:
    workflow_path = ROOT / ".github/workflows/release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert "workflow_dispatch:" in workflow_text
    assert "windows_run_id:" in workflow_text
    assert "v0.4.0" not in workflow_text
    assert not (ROOT / ".github/workflows/release-v0.4.0.yml").exists()
    assert not (ROOT / ".github/workflows/tag-v0.4.0-on-main.yml").exists()

    publish = jobs["publish"]
    assert publish["permissions"] == {"contents": "write", "actions": "read"}
    commands = _job_commands(publish)
    assert "git cat-file -t" in commands
    assert "pyproject.toml" in commands
    assert "head_sha" in commands
    assert "Windows one-click installer" in commands
    assert "gh release create" in commands
    assert "already exists; refusing to replace published bytes" in commands
    assert "--clobber" not in commands

    download_step = next(
        step for step in publish["steps"]
        if isinstance(step, dict) and step.get("uses", "").startswith("actions/download-artifact@")
    )
    assert download_step["with"]["run-id"] == "${{ inputs.windows_run_id }}"
'''
if not pattern.search(tests):
    raise SystemExit('tests/test_ci_workflow.py: PyPI test block anchor not found')
tests = pattern.sub(replacement, tests)
write('tests/test_ci_workflow.py', tests)
