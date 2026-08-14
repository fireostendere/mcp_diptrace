# Testing

## Current CI model

Repository CI separates ordinary regression coverage, platform-specific behavior, combined supported-environment coverage, generated/contract checks and real/manual DipTrace acceptance.

A green CI run proves tested repository behavior on configured runners. It does not prove universal DipTrace compatibility, a real GUI workflow, manufacturing semantics or field-solver/EMC/PI/thermal sign-off.

## Platform matrix and coverage

CI covers supported Python/platform combinations on Linux, macOS and Windows. Linux includes both exact Shapely/GEOS geometry and pure-Python no-Shapely fallback paths.

Two repository-wide coverage thresholds intentionally coexist:

- **85%** geometry-enabled Linux-only floor;
- **90%** combined supported-environment floor after combining Linux geometry, Linux fallback, macOS and Windows coverage data.

The coverage badge represents the combined 90% gate. `scripts/check_coverage.py` also enforces selected critical-module floors.

## Static / generated contract checks

The static-analysis job includes Ruff, strict Mypy, release metadata, skill sync/generation, privacy/provenance/compliance checks, event-loop audit, coverage badge generation, MCP discovery budget/snapshot, release artifact audit, format inventory and generated probe-pack verification.

`scripts/check_documentation_state.py` is an evergreen documentation/code drift gate. In addition to current tool/module markers, it rejects known stale current-state acceptance/reroute claims and obsolete source commands for the headless GUI worker. Historical dated evidence/release/audit files remain outside current-state freshness assertions.

`.github/workflows/ci.yml` remains the source of truth for the exact required commands.

## Frozen public MCP contract

Current public contract remains:

- 159 registered tools;
- generated `reference/mcp-tools-list.snapshot.json` frozen by CI.

Internal schematic/PCB/DSN-SES/XML/evidence/cinematic/library API modules must not silently expand this surface. Package-level preparation is not public registration.

## Write-path safety

Critical mutation tests continue to cover:

- allowed-root/path handling;
- bounded XML parsing;
- expected SHA-256;
- preview/commit identity consistency;
- policy/write-impact gates;
- backup/atomic replacement/rollback/recovery;
- transaction and live-session leases;
- apply/cancel/wrong-SHA refusal;
- trust invalidation after document mutation.

## Schematic intelligence tests

Focused tests cover:

- functional blocks and provenance-bearing motifs;
- bounded placement candidates and locked-part/grid behavior;
- wire quality/placement feedback;
- conservative pin geometry;
- joint placement/route scoring;
- bounded placement repair;
- builtin motif labelling and deterministic congestion metrics;
- deterministic route/congestion ensemble ranking;
- atomic selective reroute scope;
- preservation of unaffected wire geometry;
- source-document immutability before applying the semantic batch;
- fail-closed locked-part and unresolved-endpoint behavior;
- fail-closed rejection of stale/geometrically inconsistent Wire segment references while valid middle-of-segment joins remain accepted.

Existing-wire support is now available through the dedicated atomic selective-reroute planner. Placement-only planners may still refuse already-wired schematics because they cannot safely move symbols without replacing affected geometry.

The initial 18-case real-DipTrace schematic quality campaign is complete. Repository tests remain the automated regression layer; the detailed manual/native evidence and retained QUALITY FAIL/SEMANTIC FAIL/INVALID ATTEMPT history are in `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md`. Future manual reruns are impact-based rather than a replay of the whole campaign.

## PCB Generations A-D tests

Coverage includes:

- intent classification and unknown-physics preservation;
- bounded placement/legalization;
- stackup/PDN/return-path/via evidence boundaries;
- timing-gated noise triage;
- routing-policy propagation and observed-route checks;
- Generation-D hard-rule dominance and deterministic ranking;
- multiple real bounded Generation-A placement profiles feeding the existing Generation-D selector;
- existing-board baseline and profile deduplication.

Generation B/C SI/PI/thermal/EMI terms remain conservative proxies in tests. Synthetic benchmark success does not become native-DipTrace acceptance.

## DSN/SES analysis tests

`specctra_analysis.py` tests cover:

- bounded one-root S-expression inventory;
- token/scope/depth accounting;
- route net/wire/via/segment statistics;
- deterministic route length/width/layer inventory;
- importability using the existing semantic SES planner without mutation;
- unknown target nets/layers and malformed/wrong-root refusal.

Additional external-router dialect fixtures should be added only from controlled evidence rather than by guessing unsupported syntax.

## XML property/regression tests

`xml_analysis.py` is covered by ordinary fixtures plus Hypothesis properties:

- deterministic semantic fingerprint;
- XML attribute-order invariance;
- detection of unknown-element/attribute mutations;
- known semantic value changes;
- source/root drift reporting.

The XML fingerprint includes unknown XML and preserves child order. It supplements domain-level PCB/schematic semantic comparison; it does not replace connectivity review.

## Evidence-report tests

The evidence report pipeline tests:

- candidate/stage SHA binding;
- deterministic XML fingerprint/delta generation;
- post-capture artifact tamper detection;
- deterministic Markdown output;
- invariant that the report cannot claim PASS/trust automatically.

`capture_diptrace_evidence.py` remains the capture authority. `build_evidence_report.py` is a review/reporting layer only.

## Library mutation API tests

`library_mutation.py` retains raw-preservation/idempotence/mapping regression coverage.

`library_mutation_api.py` additionally tests:

- required expected-SHA binding;
- deterministic in-memory preview/result SHA;
- XML semantic delta output;
- read-only mapping validation;
- cross-action request-shape refusal;
- explicit `public_registration=false` boundary.

## Cinematic tests

Coverage includes timeline/presets, UI profile persistence/calibration, semantic payload generation, dry-run host expansion, recording helpers and now whole-manifest preflight:

- content hash independent of random session identity;
- cue count/index/timing consistency;
- payload-size budgets;
- desktop command/path/text/hotkey bounds.

These tests do not prove that a real DipTrace toolbar/profile macro is correct. Exact UI acceptance remains manual/client-specific evidence.

## Evidence classes

Keep these distinct:

- synthetic fixture;
- sanitised/controlled fixture;
- real DipTrace evidence tied to exact versions/candidate;
- historical release evidence;
- manual/private campaign evidence.

Changing a version string does not convert one evidence class into another.

## Manual acceptance checkpoints

The historical formal manual-production checkpoint remains documented in `MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md` and bound to `main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba` for the eight canonical PASS gates collected there.

At that historical checkpoint:

- 8 of 12 canonical blocking manual gates were PASS;
- Q1 Component Angle was PASS;
- real Codex restart was PASS;
- Claude Desktop restart was not run and was recorded as a project waiver at that stage.

A separate post-release schematic product-quality campaign subsequently completed cases 01–18 and its bounded fixes were merged by PR #90. That later evidence does not rewrite the historical eight-gate identities, and the historical gates do not automatically transfer to newer code.

Later real-host lifecycle evidence completed `windows_clean_install_repair_uninstall`, including an operator-confirmed from-zero run on a separate new Windows machine, and `elevated_plugin_install_profile_preservation` on exact candidate `9af6da2`. Subsequent operator-confirmed evidence from a separate machine completed `custom_state_preservation` and the Claude Desktop restart gate. All 12 blocking gates are therefore PASS across the accepted checkpoints.

## Typical local validation

```bash
python -m pip install -e '.[dev,geometry]'
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/check_release_metadata.py
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/make_probe_pack.py --check
python scripts/check_documentation_state.py
```

For a PR/release decision, GitHub Actions at the exact head SHA is authoritative.

## Historical records

Dated code-review/live-acceptance/release/compliance/manual records intentionally preserve what was true at the time. Do not rewrite their historical counts/statuses merely because current code changed.
