# MCP Distribution and Package Publication

## Current published state

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

## Distribution roles

- **PyPI** distributes the cross-platform Python MCP server and packaged skills.
- **GitHub Release** is the immutable release set for installer, portable bundle, MCPB, Python packages, checksums and provenance.
- **MCPB** packages the self-contained Windows stdio server for clients supporting local MCP bundles.
- **Registries/directories** index an immutable release identity; they do not strengthen compatibility/evidence claims.

The PyPI package and MCPB do not silently install the DipTrace bridge plug-in. Live exchange requires the matching bridge/settings and the relevant real-host acceptance.

## PyPI Trusted Publishing

`0.4.0` was published through the guarded GitHub OIDC workflow after an exact
annotated-tag checkout and target verification.

Authorized identity:

```text
PyPI project:       diptrace-mcp
GitHub owner:       fireostendere
GitHub repository:  mcp_diptrace
Workflow filename:  pypi.yml
Environment:        pypi
```

No long-lived PyPI API token is required. Future versions should preserve the separation between build/validation and the minimal publish job.

Clean package smoke:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.4.0
diptrace-mcp --help
```

Trusted Publishing establishes publication provenance, not Authenticode signing, real DipTrace compatibility or production readiness.

## Windows / MCPB build path

The repository contains deterministic build/audit infrastructure for:

- Windows standalone server;
- live XML bridge;
- client configurator;
- Inno Setup installer;
- portable bundle;
- MCPB;
- checksums/provenance inventories.

Those builders/tests are implementation evidence. They do not automatically prove that an arbitrary clean real Windows machine, DipTrace configuration or MCP client accepted the resulting release.

For each future version:

1. build from the exact frozen candidate/tag;
2. validate Python/Windows artifacts;
3. freeze filenames, sizes and SHA-256 values;
4. publish immutable bytes;
5. redownload the public bytes and repeat checksum/install/stdio smoke;
6. record exact public identities in the release record.

The `v0.4.0` publication is complete; these are future-release rules, not
pending `0.4.0` publication steps.

## Registry / Smithery metadata

Registry/directory metadata must reference public immutable artifacts and verified hashes, never transient CI files.

For a future MCPB:

1. publish the exact versioned MCPB;
2. redownload and verify SHA-256;
3. generate concrete metadata from the public URL/hash;
4. validate against the registry's then-current schema/tooling;
5. publish and record the immutable returned identity.

Directory publication is distribution metadata, not real-host acceptance evidence.

## Manual acceptance boundary

Manual acceptance is tracked in [ROADMAP.md](ROADMAP.md) and the generated acceptance tooling.

The accepted manual-production checkpoints now have all 12 blocking gates PASS. Q1 Component Angle, real Codex and Claude Desktop restarts, clean Windows lifecycle, elevated plug-in/profile preservation and custom-state preservation are PASS. The latter Claude/custom-state evidence is operator-confirmed from a separate machine.

Evidence remains bound to its recorded checkpoint and must not be copied to changed release bytes without an impact-based retest.

Example acceptance pack preparation:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.4.0 \
  --commit b4c0132283ff16a0bca81567df6704d1f6a73c7f
```

Manual evidence must remain tied to the exact candidate/artifacts tested.

## Published release versus current `main`

Do not conflate these states:

- `v0.4.0` / PyPI `0.4.0` are immutable published bytes with the A1-A8 roadmap
  closure and bounded Windows/Linux/macOS host paths described by its release
  record;
- later `main` may advance independently;
- a future release must explicitly package/re-verify later changes before
  distribution docs claim they are in published artifacts.

## Immutability rule

Do not replace bytes under an existing GitHub tag, PyPI version, Registry version or directory release. If a material issue is found, document affected identities, preserve original bytes, withdraw/yank only where appropriate and publish a corrected new version.


## v0.4.0 published host installers

The published v0.4.0 release adds two host bootstrap paths alongside the existing
Windows installer/portable/MCPB route:

- `install_linux.sh`: Ubuntu/Debian x86-64 bootstrap for pinned Wine/DipTrace,
  release-checksummed portable MCP runtime, bridge and private-Xvfb GUI worker;
- `install_macos.sh`: macOS bootstrap for the official DipTrace.app, its bundled
  Wine prefix, release-checksummed portable MCP runtime, bridge and hidden-Win32-
  desktop GUI worker. The release gate covers macOS 15 Apple Silicon and Intel.

These scripts install or integrate third-party DipTrace only after explicit license
acceptance. They do not redistribute the DipTrace installer/application as a
DipTrace MCP release asset.
