# DipTrace evidence capture

DipTrace MCP has two evidence paths with the same trust boundary:

- **native PCB acceptance rails** for repeatable whole-board evidence from a real DipTrace PCB Layout process;
- **operator-assisted capture** for format questions, unsupported editors/actions, and cases that still require a human GUI observation.

Neither path automatically grants trusted provenance, promotes fixtures, or turns a native GUI action into proof of electrical/manufacturing correctness.

## Native PCB acceptance rails

`python -m diptrace_mcp.pcb_native_acceptance run` drives a bounded real-DipTrace PCB workflow through the isolated Win32 GUI worker. Hidden desktop mode is the default and never falls back to physical mouse or keyboard input.

The `diptrace-5.3-en-v1` profile performs, in order:

1. open the existing `.dip` or `.dipxml` PCB project;
2. invoke native `Objects -> Update All Copper Pours` (with the historical singular `Object` caption accepted as a bounded fallback);
3. invoke native `Verification -> Check Design Rules`;
4. capture DRC dialog text and classify only an explicit known success token as machine PASS;
5. native Save, Close, and require normal process exit;
6. reopen the same project;
7. native `File -> Save As`, select the XML PCB format, and write a distinct `.dipxml` export;
8. hash the project/export and compare the export with an immutable baseline snapshot;
9. persist a machine-readable `*.native-evidence.json` result.

The menu profile is based on the current DipTrace 5.3 workflow. Its first run on a real target host is still a native profile acceptance event: a changed/localized menu or dialog fails closed or returns `HUMAN_REVIEW_REQUIRED` instead of using coordinate automation.

### Example

```powershell
py -m diptrace_mcp.pcb_native_acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\board.dipxml" `
  --output-xml "C:\work\evidence\board.native.dipxml"
```

When the project is binary `.dip`, provide the expected XML separately so a semantic comparison is possible:

```powershell
py -m diptrace_mcp.pcb_native_acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\board.dip" `
  --baseline-xml "C:\work\board.expected.dipxml" `
  --output-xml "C:\work\evidence\board.native.dipxml"
```

Use `--evidence-json PATH` to override the default sidecar path. Native menu paths and DRC success tokens are explicit override arguments for controlled host-profile validation; they are not discovered by coordinate clicking.

### Native result contract

The native result contains the exact UI profile, Win32 desktop/window-station/session identity, worker and DipTrace PIDs, native step evidence, DRC dialog texts, project/export SHA-256 values, structural PCB summaries, structural delta, full XML semantic delta, and any manual-review reasons.

The whole-board structural summary covers at least components, nets, net endpoints, traces, trace points, via-marked points, copper layers, plane layers, via styles, copper pours, ratlines, unrouted multi-pad nets, and duplicate `(tag, Id)` records.

Verdicts are deliberately asymmetric:

- `PASS`: native pipeline completed, DRC matched a known success token, an immutable baseline exists, structural invariants are unchanged, and the full XML semantic fingerprint is equal;
- `FAIL`: the worker/action failed, DRC reports a positive error count, structural invariants changed, or desktop/window-station/session safety evidence changed;
- `HUMAN_REVIEW_REQUIRED`: native transport completed but the DRC locale/dialog is not recognized, no immutable XML baseline exists, or the full semantic fingerprint changed while bounded structural invariants remained stable (for example a native refill/canonicalization delta that still needs classification).

CLI exit codes are `0` for `PASS`, `1` for `FAIL`, and `2` for `HUMAN_REVIEW_REQUIRED`.

A native result is evidence, not trust promotion. A reviewed native result can later be fed into the existing evidence/fixture review process; package-owned trust still requires the separate reviewed promotion path.

## Legacy operator-assisted capture

`scripts/capture_diptrace_evidence.py` remains the controlled path for unsupported native actions and format probes. It records artifacts, hashes, provenance metadata and explicit operator checks; it does not automatically grant trusted provenance or promote files into acceptance fixtures.

### Current Q1 status

The committed Q1 Component Angle recipe/result under `docs/evidence_capture/` is a reproducible public capture template and a historical record. A later manual campaign on the accepted production checkpoint completed Q1 as PASS on DipTrace PCB Layout 5.3.0.3. The immutable `v0.2.1` release record correctly retains its earlier `NOT_RUN` status.

These states are intentionally separate:

- committed historical capture template/result;
- later exact-candidate manual observation;
- package-owned/public trust promotion.

One does not automatically replace the others.

### Capture contract

A legacy session binds one recipe snapshot, operator/application/OS metadata, redistribution statement, explicit checklist answers and three distinct XML roles in order:

1. `source`;
2. `open_save`;
3. `reexport`.

Role paths must be distinct even when bytes are identical. Each role is hashed and structurally inspected. Screenshots, logs, malformed XML or a repeated path cannot substitute for a missing role.

Optional private inputs may be bound by metadata only with repeatable `--input-artifact ROLE=PATH`; their bytes stay outside the capture store and repository. Hash binding proves byte identity at the checked path, not authorship or redistribution permission.

The collector uses an explicit allowed root, refuses path aliasing and records the filesystem-safety mode. Finalized candidates remain review-only until a separate ingest/promotion decision.

### Recipes

Recipes use the strict `diptrace-capture-recipe-v1` structure with stable identity, purpose, optional expected source type, required features and stage-aware operator checks.

Generic template: `docs/evidence_capture/pcb-format-question.recipe.template.json`.

Historical Q1 concrete recipe: `docs/evidence_capture/q1-component-angle.recipe.json`.

Prefer one intentional host/UI variable per probe. Preserve unexpected changes as observations rather than editing evidence to match an expected answer.

### Interactive run

```bash
python scripts/capture_diptrace_evidence.py init \
  --root /mnt/c/capture-work \
  --session probe-001 \
  --recipe question.recipe.json

python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session probe-001 \
  --stage source \
  --file source.xml

python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session probe-001 \
  --stage open_save \
  --file open_save.xml

python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session probe-001 \
  --stage reexport \
  --file reexport.xml

python scripts/capture_diptrace_evidence.py status \
  --root /mnt/c/capture-work \
  --session probe-001

python scripts/capture_diptrace_evidence.py finalize \
  --root /mnt/c/capture-work \
  --session probe-001
```

Use `check` for recipe checklist answers. Silence is not confirmation.

### Automatic review report

After `finalize`, the review-only candidate can be converted into deterministic machine-readable and Markdown reports:

```bash
python scripts/build_evidence_report.py \
  /mnt/c/capture-work/.diptrace-capture/candidates/probe-001.candidate.json \
  --capture-root /mnt/c/capture-work \
  --json-output /mnt/c/capture-work/probe-001.report.json \
  --markdown /mnt/c/capture-work/probe-001.report.md
```

The report builder re-resolves each quarantined stage, recomputes hashes, computes XML semantic inventories, compares the three roles when available, and reports review blockers without granting trust.

The report status may be `complete_review_only`, `incomplete`, or `integrity_failure`. Building a report never grants provenance, fixture trust, release acceptance or registry promotion.

### Non-interactive, resume, abort, and ingest

Non-interactive mode is appropriate only when a controlled caller already has explicit answers/attestations. It must not synthesize operator confirmation. Use `resume` to continue a valid persisted session and `abort --reason ...` to preserve a failed attempt.

Review-only ingest remains separate:

```bash
python scripts/ingest_fixtures.py \
  --dry-run \
  --capture-root /mnt/c/capture-work \
  --candidate .diptrace-capture/candidates/probe-001.candidate.json \
  --destination-root tests/fixtures/acceptance/diptrace_5_3/seeds \
  --fixture-id probe-001 \
  --json
```

A separate reviewed repository change is required for package-owned trust promotion.

See `HEADLESS_GUI.md`, `OPEN_QUESTIONS.md`, generated `PROBE_PACK.md`, `XML_COMPATIBILITY.md`, `EDA_INTELLIGENCE.md` and `MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md` for the current evidence boundaries.
