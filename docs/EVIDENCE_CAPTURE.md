# Operator-assisted DipTrace evidence capture

`scripts/capture_diptrace_evidence.py` collects controlled source -> open/save -> re-export evidence. It records artifacts, hashes, provenance metadata and explicit operator checks; it does not automatically grant trusted provenance or promote files into acceptance fixtures.

## Current Q1 status

The committed Q1 Component Angle recipe/result under `docs/evidence_capture/` is a reproducible public capture template and a historical record. A later manual campaign on the accepted production checkpoint completed Q1 as PASS on DipTrace PCB Layout 5.3.0.3. The immutable `v0.2.1` release record correctly retains its earlier `NOT_RUN` status.

These states are intentionally separate:

- committed historical capture template/result;
- later exact-candidate manual observation;
- package-owned/public trust promotion.

One does not automatically replace the others.

## Capture contract

A session binds one recipe snapshot, operator/application/OS metadata, redistribution statement, explicit checklist answers and three distinct XML roles in order:

1. `source`;
2. `open_save`;
3. `reexport`.

Role paths must be distinct even when bytes are identical. Each role is hashed and structurally inspected. Screenshots, logs, malformed XML or a repeated path cannot substitute for a missing role.

Optional private inputs may be bound by metadata only with repeatable `--input-artifact ROLE=PATH`; their bytes stay outside the capture store and repository. Hash binding proves byte identity at the checked path, not authorship or redistribution permission.

The collector uses an explicit allowed root, refuses path aliasing and records the filesystem-safety mode. Finalized candidates remain review-only until a separate ingest/promotion decision.

## Recipes

Recipes use the strict `diptrace-capture-recipe-v1` structure with stable identity, purpose, optional expected source type, required features and stage-aware operator checks.

Generic template:

`docs/evidence_capture/pcb-format-question.recipe.template.json`

Historical Q1 concrete recipe:

`docs/evidence_capture/q1-component-angle.recipe.json`

Prefer one intentional host/UI variable per probe. Preserve unexpected changes as observations rather than editing evidence to match an expected answer.

## Interactive run

Typical sequence:

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

## Non-interactive run

Non-interactive mode is appropriate only when a controlled caller already has explicit answers/attestations. It must not synthesize operator confirmation. Committed attestation templates intentionally default to false; malformed or incomplete answers fail closed.

## Resume and abort

Use `resume` to continue a valid persisted session. Corrupt state or changed bound artifacts fail closed. Use `abort --reason ...` to preserve a failed attempt for review and start a corrected run under a new session ID.

## Review-only ingest

Capture and trusted fixture promotion are separate steps. `scripts/ingest_fixtures.py --dry-run` revalidates candidate/artifact/hash bindings, redistribution claims, destination conflicts and optional private inputs without silently copying data into acceptance fixtures.

Example:

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

See `OPEN_QUESTIONS.md`, generated `PROBE_PACK.md`, `XML_COMPATIBILITY.md` and `MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md` for the current evidence boundaries.
