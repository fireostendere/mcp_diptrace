# DipTrace MCP 0.3.0 Release Checklist

## Candidate identity

- [x] Version `0.3.0` selected.
- [x] Release class remains unsigned alpha/development prerelease.
- [x] Release manager is the repository owner under the solo-maintainer
      exception.
- [x] No independent reviewer is claimed.
- [x] Candidate commit `2646b12bca9534cdbceec8c1808bcacc09aa26bd`
      frozen and merged without tree changes at
      `fbbbda176043c555b04a908bb63f6fc4ac5909cb`.
- [x] Annotated tag `v0.3.0` created with tag object
      `82b8beac697ae25a008f4b215e2baf33959367b5`.

## Documentation and acceptance

- [x] Post-`v0.2.1` user-visible changes moved into current changelog material.
- [x] PCB authoring defaults, copper-pour/stitching boundary and silkscreen
      behavior documented.
- [x] PCB GIF/MP4 added alongside the Schematic demo.
- [x] Operator confirmed the repository PCB/Schematic examples and GIF/MP4
      outputs in the current DipTrace configuration on 2026-08-16.
- [x] Remaining native refill, manufacturing, signing, independent-review and
      universal-compatibility boundaries remain explicit.

## Automated gates

- [x] Full exact-candidate CI passes on supported GitHub runners.
- [x] 90% combined and 85% geometry-enabled coverage gates pass.
- [x] Ruff, strict Mypy, documentation, service/facade and generated snapshot
      checks pass.
- [x] Wheel and source distribution build, audit and clean-install smoke pass.
- [x] Windows installer, administrator plug-in installer, portable bundle and
      MCPB workflows pass.
- [x] Smithery lock regenerated after `0.3.0` became available from PyPI.

Local sandbox note: ordinary lint/document checks are usable, but this isolated
environment does not wake `asyncio.to_thread`/AnyIO worker futures. Thread-offload
and full-suite acceptance must therefore come from the authoritative GitHub
runners rather than a weakened code path or a falsely reported local PASS.

## Publication

- [x] Release preparation merged through protected PR #108.
- [x] Annotated tag points to the exact approved merge commit.
- [x] GitHub development prerelease and immutable assets published.
- [x] Public assets redownloaded and SHA-256 verified.
- [x] PyPI Trusted Publishing completed from an exact verified `v0.3.0`
      checkout in workflow run `31915399966`.
- [x] Public PyPI wheel/sdist redownloaded byte-for-byte; wheel installed and
      smoke-tested in a clean environment.
- [x] Public PyPI metadata contains both GIF references; both tagged GIF assets
      were redownloaded and decoded successfully.
- [x] Release record updated with exact commit, workflow runs, asset sizes and
      hashes.
