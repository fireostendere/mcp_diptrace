# DipTrace MCP 0.3.0 Release Checklist

## Candidate identity

- [x] Version `0.3.0` selected.
- [x] Release class remains unsigned alpha/development prerelease.
- [x] Release manager is the repository owner under the solo-maintainer
      exception.
- [x] No independent reviewer is claimed.
- [ ] Exact candidate commit frozen.
- [ ] Annotated tag `v0.3.0` created.

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

- [ ] Full exact-candidate CI passes on supported GitHub runners.
- [ ] 90% combined and 85% geometry-enabled coverage gates pass.
- [ ] Ruff, strict Mypy, documentation, service/facade and generated snapshot
      checks pass.
- [ ] Wheel and source distribution build, audit and clean-install smoke pass.
- [ ] Windows installer, administrator plug-in installer, portable bundle and
      MCPB workflows pass.
- [ ] Smithery lock regenerated only after `0.3.0` is available from PyPI.

Local sandbox note: ordinary lint/document checks are usable, but this isolated
environment does not wake `asyncio.to_thread`/AnyIO worker futures. Thread-offload
and full-suite acceptance must therefore come from the authoritative GitHub
runners rather than a weakened code path or a falsely reported local PASS.

## Publication

- [ ] Release preparation merged through the protected branch workflow.
- [ ] Annotated tag points to the exact approved commit.
- [ ] GitHub development prerelease and immutable assets published.
- [ ] Public assets redownloaded and SHA-256 verified.
- [ ] Tag-bound PyPI Trusted Publishing completed.
- [ ] Public PyPI wheel/sdist installed and smoke-tested.
- [ ] README and both GIF previews verified on GitHub and PyPI.
- [ ] Release record updated with exact commit, workflow runs, asset sizes and
      hashes.
