# Operator-assisted DipTrace evidence capture

## Outcome

`scripts/capture_diptrace_evidence.py` is a standard-library CLI for collecting an
operator-produced source/open-save/re-export XML triple. It writes only to a quarantine rooted at
an explicitly allowed directory and emits a review-only candidate manifest.

It deliberately does **not**:

- write to `tests/fixtures/acceptance/`;
- call a result “golden”, “verified”, or “DipTrace-authenticated”;
- grant `diptrace_exported`, `diptrace_open_save_verified`, or
  `diptrace_roundtrip_verified`;
- infer that an operator claim, a valid XML parse, or matching hashes proves provenance;
- invent an expected numeric value or DipTrace serialization convention.

Those properties make it suitable as the collection half of the evidence harness. Promotion into
a trusted registry remains a separate, reviewable repository action.

## Why the engine should be a script, with an optional thin skill

The durable component should be a Python script. Path containment, XML hardening, hashing, atomic
state-file replacement, recoverable multi-file finalization, stage ordering, and canonical manifest
generation require deterministic code and direct tests. Encoding those rules only as
natural-language skill instructions would make the evidence chain depend on agent compliance.

A small `capture-diptrace-evidence` skill is still useful as the operator-facing layer. It should:

1. turn an item from `docs/OPEN_QUESTIONS.md` or the
   [generated probe pack](PROBE_PACK.md) into a concrete recipe;
2. explain one action at a time to the Windows/DipTrace operator;
3. run this CLI for `init`, `record`, `check`, `status`, and `finalize`;
4. surface discrepancies and stop instead of answering for the operator;
5. hand the candidate manifest to the independent review/ingest workflow.

The skill must never duplicate hashing or trust decisions. Its bundled `scripts/` resource should
be this tested engine (or a stable wrapper around a repository-installed command). The skill body
can remain short because recipe shape and trust rules belong in repository documentation.

## Capture model

Each session binds these inputs:

- one immutable recipe snapshot and SHA-256 computed from the same single byte read;
- an operator label, reported DipTrace version/build, OS, and redistribution claim;
- a required checklist designed for one experiment;
- optionally, metadata for private binary inputs used to produce the source export;
- three distinct file roles captured in order:
  - `source`: XML exported directly from the prepared design;
  - `open_save`: a separate XML file saved by DipTrace after opening the source;
  - `reexport`: a fresh XML export from the saved design.

The files may be byte-identical. Equality is evidence, not a failure. They must nevertheless have
different role paths so the manifest cannot silently reuse one file for every step.

For each role the script records:

- a byte-identical quarantine copy;
- SHA-256 and byte size;
- `Source/@Type`, `Source/@Version`, and `Source/@Units`;
- counts for every descendant element name below `<Source>` and every direct child of `<Source>`;
- stage-specific operator attestations and notes;
- directly observed discrepancies such as a units change between stages.

Element counts are intentionally syntactic. They make object loss reviewable without pretending
that every tag is a normalized engineering object.

The operator-reported DipTrace application version/build and literal `Source/@Version` are stored
as separate facts. The collector does not assume they use the same versioning convention.

### Private input-artifact binding

The source-stage `record` command accepts repeatable `--input-artifact ROLE=PATH` arguments. This is
for an operator-owned legacy library, project, or other private input whose byte identity matters
to the experiment but whose bytes must not enter quarantine or Git. Each candidate entry has
exactly:

```json
{
  "role": "component_library",
  "name": "original.eli",
  "path": "private/original.eli",
  "sha256": "64-lowercase-hex-characters",
  "size_bytes": 12345
}
```

Roles are lowercase slugs. Names are single safe basenames. Paths are canonical forward-slash
paths below the allowed root and outside `.diptrace-capture`. Roles, names, paths, and filesystem
identities must be unique; symlinks, junctions, and hard-link aliases are refused. At most 32
inputs of at most 128 MiB each may be bound. Entries are sorted by role, name, and path before
canonical manifest serialization.

Capture-store exclusion is checked from real filesystem ancestry and identity, not from the
spelling or letter case of `.diptrace-capture`. This matters on Windows and WSL-mounted NTFS, where
differently cased path components may name the same directory. The ingest validator also refuses
an input that reuses the recipe, an original XML-stage path, a quarantined stage, the candidate
manifest, or its detached digest.

The collector hashes each original file while the source stage is recorded and re-hashes it on
finalization, including repeated finalization. The ingest validator re-opens and re-hashes the same
private path. Missing, redirected, aliased, resized, or changed files fail closed. Only the five
metadata fields above enter session state, the candidate, or the dry-run receipt; input bytes are
never copied into quarantine, a prospective destination, or the repository. The original private
file must therefore remain available and unchanged through ingest.

This binds candidate metadata to exact local bytes as reported by the operator. It does not prove
who authored the input, that DipTrace used it to produce the XML, or that it may be redistributed.
Authority remains `operator_supplied_unverified`, trust remains `none`, and candidates that omit
`input_artifacts` remain valid for backward compatibility.

For a library experiment, the source record may bind more than one controlled input:

```bash
python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session library-probe-001 \
  --stage source \
  --file source.xml \
  --input-artifact component_library=private/original.eli \
  --input-artifact control_library=private/control.eli
```

## Recipe contract

Recipes use `diptrace-capture-recipe-v1` and contain:

- `recipe_id`, `title`, and `purpose`;
- an optional exact `expected_source_type`;
- `required_features`, written by the experiment author;
- a non-empty `operator_checklist`, with stable ids, prompts, required flags, and optional stages.

A checklist item bound to a stage cannot be answered until that stage has been recorded. The stage
annotation is therefore an enforced observation boundary, not presentation-only metadata.

The collector does not claim it can recognize the requested features in arbitrary DipTrace XML.
The operator confirms their presence, while an independent reviewer compares the quarantined
artifacts and UI evidence if required. A later recipe-specific validator may add a **refusal** for
an absent, structurally documented element; it must not manufacture expected DipTrace behavior.

The generic [recipe template](evidence_capture/pcb-format-question.recipe.template.json) must have
its feature placeholders replaced before a real capture.
The [Q1 Component angle recipe](evidence_capture/q1-component-angle.recipe.json) is a concrete
experiment derived from `docs/OPEN_QUESTIONS.md`; it records the literal result and does not assume
whether the value is radians or degrees.

## Designing a controlled recipe

For a before/after format experiment, make one intentional GUI change per probe. If two settings
must change together, document why they cannot be isolated; otherwise split them into separate
recipes. A broad “representative library” capture is useful for vocabulary discovery but cannot
answer which setting caused a byte or semantic difference.

Include unchanged controls in the same prepared design:

- use two otherwise equivalent objects when one is the probe and one is the control;
- record the source role before the intentional change;
- leave the control object's relevant settings untouched through open/save/re-export;
- state the single intended difference in the recipe and record every additional observed
  difference as a discrepancy, not as part of the expected result.

Screenshots may support the operator's report of the selected object, dialog, field value, warning,
or application build. They are never the authoritative format artifact: XML role copies, hashes,
the recipe snapshot, and explicit attestations remain the machine-reviewable candidate evidence.
A screenshot must not be used to fill a missing XML role, infer an undocumented unit, or upgrade
the candidate's trust level.

If the GUI cannot reproduce the prepared state or isolate the intended change, stop the session
with a review blocker. Do not repair the exported bytes by hand.

## Storage and trust boundary

Given `--root C:\capture-work` (or the corresponding WSL path), the script creates:

```text
C:\capture-work\.diptrace-capture\
├── sessions\<session>\state.json
├── quarantine\<session>\source\source.xml
├── quarantine\<session>\open_save\open_save.xml
├── quarantine\<session>\reexport\reexport.xml
└── candidates\
    ├── <session>.candidate.json
    └── <session>.candidate.json.sha256
```

All supplied files must resolve inside `--root`; inputs from the capture store itself are refused.
On POSIX, including the documented WSL workflow, the collector pins an open descriptor for the
allowed root, opens every descendant component relative to that descriptor with `O_NOFOLLOW`, and
publishes temporary files relative to the already-open destination directory. A concurrent rename
or symlink swap therefore cannot redirect a capture-store read or write outside the pinned root.

Native Windows lacks the complete descriptor-relative API in Python's standard library. There the
collector uses the explicitly named `cooperative_static_checks` mode: capture-store symlinks and
junctions, plus input redirects that visibly escape the root, are refused, but the operator must use
a private capture root and must not let another process rename or replace its paths during a
command. Use WSL when containment must remain race-resistant under concurrent filesystem mutation.
Every candidate records `filesystem_safety.mode` and `filesystem_safety.race_resistant`, so a
reviewer can enforce the required mode.

Mutations use an advisory lock that the OS releases after a crash. State replacement is atomic;
candidate manifest/digest publication is recoverable and refuses conflicting existing artifacts.

Quarantine is not an authenticated store: the operator controls the allowed root. Hash validation
detects a changed quarantined artifact before finalization, and the detached candidate digest makes
later change visible, but neither fact identifies who operated DipTrace.

Every emitted candidate contains:

```json
{
  "authority": "operator_supplied_unverified",
  "trust_grant": "none",
  "candidate_only": true,
  "review_status": "pending_independent_review",
  "requires_independent_review": true,
  "must_not_copy_to_acceptance_without_review": true,
  "filesystem_safety": {
    "mode": "descriptor_relative_posix",
    "race_resistant": true
  }
}
```

The shown filesystem mode is the POSIX/WSL value; native Windows records
`cooperative_static_checks` and `false`. There is deliberately no high-trust `validation_level`
field.

## Interactive run

Keep the recipe and all three exports inside the allowed root. For Q1, copy
`docs/evidence_capture/q1-component-angle.recipe.json` into that root first:

```bash
python scripts/capture_diptrace_evidence.py init \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --recipe q1-component-angle.recipe.json

python scripts/capture_diptrace_evidence.py status \
  --root /mnt/c/capture-work \
  --session pcb-angle-001

python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --stage source \
  --file source.xml

python scripts/capture_diptrace_evidence.py check \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --item same_component_definition \
  --answer yes \
  --note "U_CTRL and U_PROBE use the same component and pattern"
```

Repeat `record` for `open_save` and `reexport`, and answer every required Q1 checklist item from the
recipe. Then:

```bash
python scripts/capture_diptrace_evidence.py finalize \
  --root /mnt/c/capture-work \
  --session pcb-angle-001
```

Interactive prompts default to “no”; silence cannot become an attestation.

## Non-interactive run

Non-interactive mode is for a controlled operator UI or automation that already collected explicit
answers. It never synthesizes a human confirmation:

```bash
python scripts/capture_diptrace_evidence.py init \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --recipe q1-component-angle.recipe.json \
  --answers operator-answers.json \
  --non-interactive --json

python scripts/capture_diptrace_evidence.py record \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --stage source \
  --file source.xml \
  --attestations source.attestations.json \
  --non-interactive --json
```

`--answers` and `--attestations` are required in non-interactive mode and forbidden in interactive
mode. The JSON schemas are strict; unknown fields and non-boolean confirmations are rejected.
Committed attestation templates for
[source](evidence_capture/source.attestations.template.json),
[open/save](evidence_capture/open-save.attestations.template.json), and
[re-export](evidence_capture/reexport.attestations.template.json) deliberately contain only
`false`. Copy the appropriate template into the allowed root, and change each value to `true` only
after the named action has actually occurred. An unchanged template is refused.

## Resume, interruption, and abort

State is persisted after each action. To continue after closing the terminal:

```bash
python scripts/capture_diptrace_evidence.py resume \
  --root /mnt/c/capture-work \
  --session pcb-angle-001
```

`resume` validates the complete persisted state structure, verifies its session/root binding, and
reports the next stage and unresolved checklist items. Corrupt or shape-invalid state fails with a
typed `invalid_session_state` error rather than continuing from partial data. A crash after the
quarantine copy but before the state update can reuse the byte-identical orphan. A crash after
candidate-manifest creation but before the state update recovers only when the existing manifest is
exactly bound to the session state.

To abandon a bad run without destroying evidence:

```bash
python scripts/capture_diptrace_evidence.py abort \
  --root /mnt/c/capture-work \
  --session pcb-angle-001 \
  --reason "Wrong design revision selected" \
  --non-interactive
```

Abort preserves state and quarantine artifacts. Start a new session id for the corrected run.

## Review-only ingest checkpoint

Repository integration should use two deliberately separate commands:

1. **Capture (this script):** produces an untrusted candidate under an operator-owned allowed root.
2. **Ingest validation (`scripts/ingest_fixtures.py`):** strictly validates the candidate
   manifest and detached hash, re-reads every quarantined role, checks its path/SHA/size/fresh XML
   inventory, re-reads every optional private input to check its path/SHA/size without planning a
   copy, checks redistribution permission, and reports prospective destinations and conflicts. It
   is currently a dry-run checkpoint only.

For a real capture:

```bash
python scripts/ingest_fixtures.py \
  --dry-run \
  --capture-root /mnt/c/capture-work \
  --candidate .diptrace-capture/candidates/pcb-angle-001.candidate.json \
  --destination-root tests/fixtures/acceptance/diptrace_5_3/seeds \
  --fixture-id pcb-angle-001 \
  --json
```

Candidate and artifact paths are relative to the explicit capture root; traversal, symlinks,
hard-linked role reuse, changed files, source-type disagreement, unresolved review blockers, and
unknown manifest fields fail closed. Existing destination files are never replaced: the plan marks
an identical hash as `identical`, a different hash or unplanned entry as a conflict, and returns a
non-zero status when conflicts exist.

Optional input artifacts are reported under `candidate.input_artifacts` and covered by the
deterministic receipt hash, while `validation.input_artifacts_metadata_only` remains `true`.
`destination.files` contains only the three XML roles, candidate manifest, and detached digest;
private input bytes never become planned fixture files.

The dry-run plan reports `validation.filesystem_safety`. POSIX systems with descriptor-relative
`open` and `O_NOFOLLOW` report `descriptor_relative_posix` and `race_resistant: true`; paths are
walked relative to a pinned root descriptor and no checked descendant is reopened by full pathname.
Platforms without that API, including native Windows, report `cooperative_identity_checks` and
`race_resistant: false`; every component and the open file identity are compared before and after
the read, but an uncooperative process with concurrent filesystem mutation remains outside that
fallback's guarantee.

The repository now has a package-owned committed registry, and the validator
loads it fail-closed. The production registry currently has zero independently
reviewed entries. Every plan therefore reports
`trusted_registry_exists: true`, `trusted_registry_checked: true`,
`trusted_registry_entry_count: 0`, `trust_promoted: false`, and
`validation_level_granted: null`.

Registry existence does not imply fixture-ingest authorization. This command
has no mutation implementation, so every plan also reports
`apply_available: false` and
`apply_unavailable_reason: fixture_apply_not_implemented`. Passing `--apply`
is a typed refusal performed before any candidate or destination path is
opened. The command does not write to `tests/fixtures/acceptance/`, create a
provenance sidecar, or turn operator claims into trust.

CI exercises the same validator with:

```bash
python scripts/ingest_fixtures.py --dry-run --synthetic --json
```

That mode constructs a schema-complete stand-in only inside a process-owned temporary directory,
uses deterministic bytes, prints no temporary absolute paths, destroys the stand-in on return, and
grants no trust. Its shape-only attestation fields are synthetic test inputs, not human or DipTrace
claims.

The committed registry binds reviewed evidence and document hashes; its first
entry remains human-gated. A future ingest implementation would additionally
need an independently reviewed mapping from a candidate manifest SHA-256 to
approved fixture roles. Neither the capture script nor this dry-run validator
may create that authorization. CI can inspect the empty registry and validate
candidate hashes without DipTrace, but it cannot manufacture provenance.

Promotion should also reject:

- candidates with `review_blockers`;
- missing or changed quarantine files;
- recipes with placeholder text;
- source-type disagreements;
- incomplete checklist items;
- reuse of one filesystem object for multiple roles;
- any candidate whose authority/trust-boundary constants changed;
- any requested fixture without explicit redistribution permission.

## Repository layout

```text
scripts/capture_diptrace_evidence.py
scripts/ingest_fixtures.py
scripts/make_probe_pack.py
tests/test_capture_diptrace_evidence.py
tests/test_ingest_fixtures.py
tests/test_probe_pack.py
docs/EVIDENCE_CAPTURE.md
docs/PROBE_PACK.md
docs/evidence_capture/
```

The example directory contains recipe and input templates, never captured output. Do not place
example output in `tests/fixtures/acceptance/`. Tests continue generating synthetic stand-ins only
under temporary directories. The packaged `diptrace-evidence-capture` skill invokes byte-identical
mirrors of these repository commands rather than implementing a separate trust path.

## Validation

The test suite covers:

- UTF-8 and UTF-16 DTD/entity refusal;
- root/type/units validation and literal object counts;
- root containment and symlink escape;
- POSIX root/path replacement races through descriptor-relative regression tests;
- redirected per-session and quarantine descendant refusal;
- single-read recipe snapshot/SHA binding and strict corrupt-state refusal;
- strict recipes, answers, and attestations;
- ordered stage recording and source-type parity;
- refusal to answer a stage-bound checklist item before its artifact is recorded;
- byte-identical quarantine and SHA binding;
- optional private-input metadata binding, canonical order, and backward compatibility;
- private-input tamper, traversal, symlink, hard-link, duplicate-role, and wrong-stage refusals;
- finalize- and ingest-time private-input hash/size revalidation without copy planning;
- incomplete captures and quarantine tampering;
- idempotent finalization and interrupted-finalize recovery;
- stale/live locks, resume, and evidence-preserving abort;
- interactive answers and non-interactive required inputs;
- a complete subprocess-driven `init` → three `record` stages → checklist → `finalize` example;
- a no-redistribution candidate that remains untrusted and blocked.
- deterministic temporary synthetic-ingest planning with no acceptance-tree mutation;
- strict candidate/digest/artifact/inventory validation and path/hardlink/symlink refusals;
- inspection of the existing empty embedded registry without trust promotion;
- typed `--apply` refusal because fixture apply is not implemented;
- prospective destination creation/identity/conflict reporting without writes.

Run:

```bash
./.venv/bin/python -m pytest -q tests/test_capture_diptrace_evidence.py
./.venv/bin/python -m pytest -q tests/test_ingest_fixtures.py
./.venv/bin/python -m ruff check --no-cache \
  scripts/capture_diptrace_evidence.py scripts/ingest_fixtures.py \
  tests/test_capture_diptrace_evidence.py tests/test_ingest_fixtures.py
./.venv/bin/python -m mypy --strict --no-incremental \
  scripts/capture_diptrace_evidence.py scripts/ingest_fixtures.py
./.venv/bin/python scripts/make_probe_pack.py --check
```
