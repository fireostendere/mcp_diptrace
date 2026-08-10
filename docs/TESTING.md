# Testing

## Current CI model

The repository distinguishes ordinary regression coverage, platform-specific behaviour, aggregate supported-environment coverage, generated-contract checks and real/manual DipTrace acceptance.

A green repository CI run proves the tested source behaviour on the configured runners. It does **not** prove universal DipTrace compatibility, native manufacturing semantics, a successful clean-machine installation outside CI, or a real-client GUI workflow unless that path has separate acceptance evidence.

## Main automated gates

### Python regression matrix

CI runs the test suite across supported Python/platform combinations including Linux, macOS and Windows. Linux also has two explicit geometry modes:

- Shapely/GEOS enabled;
- pure-Python no-Shapely fallback.

The geometry-enabled Linux 3.12 job proves the expected backend first, runs the real headless bridge handshake, then executes the full test suite with coverage.

### Coverage gates

There are two different repository-wide percentages by design:

1. **85% Linux-only floor** — the geometry-enabled Linux 3.12 job runs:

```bash
python -m pytest -q --tb=long \
  --cov=src/diptrace_mcp \
  --cov-report=term \
  --cov-report=json:coverage.json \
  --cov-fail-under=85
python scripts/check_coverage.py coverage.json
```

2. **90% combined supported-environment floor** — coverage artifacts from Linux geometry, Linux fallback, macOS and Windows are combined and gated with:

```bash
coverage combine coverage-data
coverage report --fail-under=90
coverage json -o coverage-combined.json
python scripts/check_coverage.py coverage-combined.json
```

The badge in `docs/badges/coverage.svg` represents the **90% combined gate**, not the Linux-only floor.

`scripts/check_coverage.py` additionally enforces selected per-file coverage floors for critical modules. Do not replace the combined 90% policy with one platform's percentage, and do not raise the Linux-only threshold merely to make the two numbers visually identical.

The old `v0.1.2` measurements around 86% are historical release evidence, not the current gate.

## Static and contract checks

The static-analysis job includes, among other checks:

```bash
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/check_release_metadata.py
python scripts/sync_skill_scripts.py --check
python scripts/generate_pcb_skills.py --check
python scripts/check_public_privacy.py
python scripts/check_provenance_inventory.py
python scripts/generate_compliance_inventory.py --check
python scripts/audit_event_loop.py --json
python scripts/generate_coverage_badge.py --check
python scripts/measure_mcp_surface.py --baseline-bytes 121335 --max-growth-percent 15
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/audit_release_artifacts.py --dist-dir release-dist --check-allowlist
python scripts/report_format_coverage.py --check
```

The exact workflow file `.github/workflows/ci.yml` is the source of truth when a command changes.

## Frozen public MCP contract

The public MCP discovery surface is intentionally frozen and regression-tested. Current expected contract:

- 159 tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations.

`reference/mcp-tools-list.snapshot.json` is generated and checked through the public in-memory MCP transport. Internal schematic/PCB/cinematic modules must not silently change that snapshot.

## Service and async boundaries

Automated tests cover:

- Facade signature/delegation parity;
- shared service ownership and negative decomposition rules;
- server-owned AnyIO worker-thread offload;
- event-loop responsiveness;
- cancellation and timeout behaviour;
- stable public error envelopes;
- record/session/transaction persistence safety.

See `docs/SERVICE_DECOMPOSITION.md`, `docs/ASYNC_EXECUTION.md` and `docs/API_ERRORS.md`.

## Write-path safety regression

Critical write paths are tested for:

- allowed-root/path handling;
- bounded XML parsing;
- expected SHA-256 validation;
- preview/commit identity consistency;
- policy/write-impact gates;
- backup and atomic replacement;
- rollback/recovery;
- live-session leases and apply/cancel finalisation;
- wrong-SHA refusal;
- trust invalidation when a document changes after evidence was created.

A fixture pass establishes project-owned behaviour against that fixture. It is not automatically real-DipTrace evidence.

## Geometry and routing

Tests separately cover exact Shapely/GEOS geometry and the pure-Python fallback. Routing/placement tests cover bounded local algorithms, clearance handling, via validation, differential-pair/length constraints, deterministic candidate ordering and semantic-operation output.

PCB Generations A-D have focused regression coverage for:

- intent classification and unknown-physics preservation;
- placement candidate determinism/legalisation;
- stackup/PDN/return-path/via evidence boundaries;
- timing-gated aggressor/victim triage;
- routing-policy propagation and observed-route checks;
- Generation D hard-rule dominance, candidate bounds and deterministic selection.

The Generation D engineering-trap catalog remains synthetic-regression evidence until its affected primitives complete the documented real-DipTrace acceptance path.

## Schematic intelligence

Focused tests cover:

- deterministic functional blocks and reference motifs;
- bounded multi-candidate placement;
- locked-part preservation and grid adherence;
- non-mutating wire-candidate quality metrics;
- conservative pin-geometry matching and unresolved/ambiguous cases;
- pin-aware joint placement/routing scoring;
- ground/power scoring policy;
- bounded placement repair, candidate budgets and translation bounds;
- source-document immutability.

Existing-wire selective reroute is not yet the default supported placement path, so tests must continue to fail closed rather than pretend that moving symbols while leaving old wire geometry is safe.

## Cinematic subsystem

Unit/CI coverage exists for:

- deterministic timeline/presets;
- capture/compile CLI behaviour;
- dry-run desktop command expansion;
- UI profile persistence/readiness;
- affine design-to-client calibration and residual failures;
- semantic Schematic/PCB payload generation;
- window targeting and recording command generation.

Those tests do not establish that a particular DipTrace toolbar layout, shortcut or profile action macro is correct on a real machine. Real UI profile calibration/action verification remains a manual acceptance boundary.

## Windows artifacts

CI builds and smoke-runs the unsigned bridge executable. Separate Windows workflows/build scripts cover the standalone server, configurator, installer, portable bundle and release artifacts.

Artifact tests/audits verify expected files, checksums, version metadata, packaging boundaries and unsigned status. A CI install/uninstall smoke is useful evidence for the installer implementation but does not replace the currently pending project-level `windows_clean_install_repair_uninstall` gate on the chosen production candidate.

## Fixtures and evidence classes

Keep these categories separate:

- **synthetic fixture** — project-generated XML for deterministic regression;
- **sanitised/controlled fixture** — project-controlled test material with documented provenance;
- **real DipTrace evidence** — controlled native open/save/re-export or client behaviour tied to exact versions and commit/artifact identities;
- **historical release evidence** — immutable observation about a specific released candidate;
- **manual/private campaign evidence** — may justify project decisions but does not automatically become package-owned public trust data.

Changing a version string or format number does not convert one class into another.

## Manual acceptance checkpoint

The latest accepted manual-production checkpoint is documented in `docs/MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md` and remains bound to `main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`.

At that checkpoint:

- 8 of 12 canonical blocking manual gates are PASS;
- Q1 Component Angle is PASS;
- real Codex restart/configuration/`get_capabilities` is PASS;
- Claude Desktop restart is WAIVED for the current campaign, **not PASS**;
- Windows lifecycle acceptance is the next project-required formal gate when acceptance resumes.

Later `main` development does not inherit those PASS results automatically.

## Local developer checks

Typical full local validation:

```bash
python -m pip install -e '.[dev,geometry]'
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/generate_pcb_skills.py --check
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/check_service_facade_contract.py --check
python scripts/validate_service_decomposition.py --check
python scripts/audit_event_loop.py --json
python scripts/generate_coverage_badge.py --check
python scripts/report_format_coverage.py --check
python scripts/audit_acceptance_seeds.py
```

For an exact release/PR decision, use the current GitHub workflow as the authoritative set of required jobs and keep the evidence tied to the exact head SHA.

## Historical records

Dated files such as `CODE_REVIEW_2026-07-31.md`, `LIVE_ACCEPTANCE_2026-07-31.md`, release records/checklists and compliance audits intentionally preserve what was true at that time. Do not rewrite their old counts/statuses to match today's code. Current docs should link to them as historical evidence rather than treating them as current-state dashboards.
