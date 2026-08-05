# MCP distribution and package publication

## Current state

GitHub prerelease `v0.2.0` remains the latest published release. It contains no
MCPB asset and is not published to PyPI, the official MCP Registry, or Smithery.
Existing tags and release assets are immutable and must never be replaced.

Version `0.2.1` is the active distribution candidate on branch
`release/v0.2.1-pypi`. It prepares:

- PyPI package `diptrace-mcp==0.2.1`;
- Windows MCPB `DipTrace-MCP-0.2.1-windows.mcpb`;
- official MCP Registry identity `io.github.fireostendere/diptrace-mcp`;
- Smithery publication from the same immutable MCPB.

Nothing in the candidate branch creates a tag, GitHub Release, PyPI project,
Registry entry, or Smithery listing automatically.

## Distribution roles

The release channels serve different purposes:

- PyPI distributes the cross-platform Python MCP server, packaged skills, and
  command-line entry points;
- GitHub Release distributes the complete immutable release set, including
  Windows installer, portable bundle, MCPB, checksums, SBOM, notices,
  provenance, and release record;
- MCPB packages the self-contained Windows stdio server for MCP clients that
  support local bundles;
- the official MCP Registry publishes versioned metadata and the immutable MCPB
  URL plus SHA-256;
- Smithery indexes and distributes the same verified MCPB.

The Python package and MCPB do not silently install the DipTrace bridge plug-in.
Live exchange requires the matching Windows bridge and settings from the same
GitHub release.

## Build the 0.2.1 Python candidate

From a clean checkout of the release branch:

```bash
python -m pip install -e '.[dev]'
rm -rf dist
python -m hatchling build -d dist
python scripts/audit_release_artifacts.py --dist-dir dist --check-allowlist
python -m twine check --strict dist/*
```

Expected files:

```text
dist/diptrace_mcp-0.2.1-py3-none-any.whl
dist/diptrace_mcp-0.2.1.tar.gz
```

The dedicated `.github/workflows/pypi.yml` workflow repeats the build, allowlist
audit, strict metadata check, wheel installation, source-distribution
installation, version assertion, and CLI smoke.

## PyPI Trusted Publishing

The first PyPI publication uses a pending Trusted Publisher rather than a
long-lived API token.

Configure these exact values on PyPI:

```text
PyPI project:       diptrace-mcp
GitHub owner:       fireostendere
GitHub repository:  mcp_diptrace
Workflow filename:  pypi.yml
Environment:        pypi
```

Create a protected GitHub environment named `pypi`. The workflow gives
`id-token: write` only to the minimal publish job. The build job has no OIDC
permission and uploads the exact validated wheel and source distribution as a
workflow artifact.

Publication is manual and fail-closed:

1. merge the reviewed release-finalisation pull request;
2. create annotated tag `v0.2.1` at the exact approved merge commit;
3. publish and publicly verify the GitHub prerelease assets;
4. confirm the PyPI pending publisher and GitHub environment settings;
5. dispatch `.github/workflows/pypi.yml` from tag `v0.2.1` with
   `publish=true`.

The workflow rejects branch, `main`, lightweight-tag, wrong-tag, and mismatched
commit publication requests.

After publication, verify from a clean environment:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.2.1
diptrace-mcp --help
```

Also verify the PyPI project links, README rendering, file hashes, Trusted
Publisher identity, and uploaded attestations. A pending publisher does not
reserve the package name until the first successful upload, so confirm name
availability immediately before publishing.

## Build the Windows MCPB candidate

On Windows:

```powershell
.\scripts\build_windows_server.ps1 `
  -PythonCommand python `
  -OutputDir dist\windows-server `
  -Clean

python scripts/build_mcpb.py `
  --server-dir dist\windows-server\diptrace_mcp_server `
  --output-dir dist\mcpb
```

Expected files:

```text
dist/mcpb/DipTrace-MCP-0.2.1-windows.mcpb
dist/mcpb/DipTrace-MCP-0.2.1-windows.mcpb.sha256
```

The MCPB workflow builds the real frozen Windows server, creates the bundle,
checks ZIP integrity, verifies the sibling SHA-256, and uploads a CI candidate.
A CI artifact is not a public release asset and must not be used in Registry or
Smithery metadata.

## Official MCP Registry publication

Only after the public `v0.2.1` MCPB has been downloaded again and its SHA-256
verified:

```bash
python scripts/generate_registry_server_json.py \
  --version 0.2.1 \
  --mcpb-url https://github.com/fireostendere/mcp_diptrace/releases/download/v0.2.1/DipTrace-MCP-0.2.1-windows.mcpb \
  --mcpb-file DipTrace-MCP-0.2.1-windows.mcpb \
  --output server.json
```

Then:

1. validate `server.json` with the current official schema and current
   `mcp-publisher` version;
2. authenticate with `mcp-publisher login github`;
3. run `mcp-publisher publish`;
4. query the Registry API and record the immutable version metadata;
5. confirm that the public URL and SHA-256 exactly match the redownloaded MCPB.

The official Registry is in preview. Re-check its schema and package
requirements at publication time rather than relying only on this repository's
template.

## Smithery publication

After the same public MCPB has been verified:

```bash
smithery auth login
smithery mcp publish ./DipTrace-MCP-0.2.1-windows.mcpb \
  -n fireostendere/diptrace-mcp
```

Record the Smithery release identifier and confirm the installation prompts for
workspace and state directories. Do not describe the MCPB as installing the
DipTrace bridge automatically.

## Directory listing

The repository is suitable for MCP directories and awesome lists independently
of PyPI or MCPB publication. The canonical concise entry is:

```markdown
- [fireostendere/mcp_diptrace](https://github.com/fireostendere/mcp_diptrace) 🐍 🏠 🪟 - Local MCP server and Windows bridge for reading, reviewing and guarded editing of DipTrace PCB and schematic projects; also supports cross-platform offline XML analysis.
```

## Evidence and immutability

For every public channel, record:

- exact tag and commit;
- workflow run;
- filename, size, and SHA-256;
- public URL;
- public redownload verification;
- install or introspection smoke;
- signing status and limitations.

Do not replace bytes under an existing GitHub tag, PyPI version, Registry
version, or Smithery release. Publish a corrected new version instead.
