# Operator workflow

Use a dedicated allowed root such as `C:\diptrace-capture\q1` or its WSL path. Never work inside
`tests/fixtures/acceptance/`. The recipe may exist at initialization; `open_save.xml` and
`reexport.xml` must be created later by the operator and are not initialization prerequisites.

## Locate the installed scripts

From a wheel installation:

```bash
DIPTRACE_SKILL_DIR="$(python -c 'from importlib.resources import files; print(files("diptrace_mcp").joinpath("skills/diptrace-evidence-capture"))')"
DIPTRACE_CAPTURE_SCRIPT="$DIPTRACE_SKILL_DIR/scripts/capture_diptrace_evidence.py"
DIPTRACE_INGEST_SCRIPT="$DIPTRACE_SKILL_DIR/scripts/ingest_fixtures.py"
```

From a source checkout, use `scripts/capture_diptrace_evidence.py` and
`scripts/ingest_fixtures.py` directly.

## Capture candidate

Copy one recipe into the capture root, then initialize:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" init \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001 \
  --recipe q1-component-angle.recipe.json
```

The interactive prompts require an operator label, literal DipTrace version/build, operating
system, redistribution decision/basis, and notes. Defaults do not attest success.

Record the initial DipTrace export:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" record \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001 \
  --stage source \
  --file source.xml
```

Now have the operator open `source.xml` in DipTrace and save the document to a new
`open_save.xml`. Only after that action:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" record \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001 \
  --stage open_save \
  --file open_save.xml
```

Have the operator export that saved design independently to `reexport.xml`. Only after that action:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" record \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001 \
  --stage reexport \
  --file reexport.xml
```

`status` lists pending checklist IDs but does not print commands or prompts. Read each prompt from
the recipe and answer the observed result with a literal command; do not encode an expected answer
in the recipe:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" check \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001 \
  --item <pending-id-from-status> \
  --answer yes \
  --note "What the operator actually observed"
```

Use `no` or `not_applicable` only when that is the observation allowed by the recipe. Then
finalize:

```bash
python "$DIPTRACE_CAPTURE_SCRIPT" status \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001

python "$DIPTRACE_CAPTURE_SCRIPT" finalize \
  --root /mnt/c/diptrace-capture/q1 \
  --session q1-angle-001
```

Finalization creates a candidate manifest and detached digest in quarantine. It grants no trust.

## Dry-run ingest

Validate the finalized candidate without modifying a fixture tree:

```bash
python "$DIPTRACE_INGEST_SCRIPT" \
  --dry-run \
  --capture-root /mnt/c/diptrace-capture/q1 \
  --candidate .diptrace-capture/candidates/q1-angle-001.candidate.json \
  --destination-root /mnt/c/diptrace-review-destination \
  --fixture-id q1-angle-001 \
  --json
```

The destination may be an empty review directory. `--apply` is deliberately unavailable. The plan
must report all role destinations, conflicts, registry state, `trust_promoted: false`, and
`validation_level_granted: null`.

For a shape-only CI/installation test outside every fixture tree:

```bash
python "$DIPTRACE_INGEST_SCRIPT" --dry-run --synthetic --json
```

This synthetic mode exercises validation plumbing only and is not operator or DipTrace evidence.

## MCP validation and record handoff

Select `q1/reexport.xml` itself with `get_document_info` and keep its returned SHA in the operator
summary. If a separate working document is used instead, it must be an exact byte copy whose SHA
matches the `reexport` role; a merely related `board.dip` is refused by the binding gate.
Map capture roles as follows:

- candidate `source` -> MCP `evidence.source`;
- candidate `open_save` -> MCP `evidence.saved`;
- candidate `reexport` -> MCP `evidence.reexport`.

Call `validate_roundtrip_evidence` with the exact existing role paths and freshly computed lowercase
SHA-256 values:

```json
{
  "path": "q1/reexport.xml",
  "evidence": {
    "source": {
      "path": "q1/source.xml",
      "sha256": "64-lowercase-hex-characters"
    },
    "saved": {
      "path": "q1/open_save.xml",
      "sha256": "64-lowercase-hex-characters"
    },
    "reexport": {
      "path": "q1/reexport.xml",
      "sha256": "64-lowercase-hex-characters"
    }
  }
}
```

Before recording, show the operator:

- selected `q1/reexport.xml` path, kind, and SHA-256 from `get_document_info`;
- candidate manifest path and SHA-256;
- all three role paths and SHA-256 values;
- source type and structural comparison status;
- dry-run ingest conflicts and the two metadata sidecars that may be written beside that exact
  selected path.

Ask for explicit confirmation of that exact summary. Only then send the unchanged payload to
`record_roundtrip_evidence`. If any path, file, hash, document SHA, or comparison changed since
validation, validate again. Recording remains user-supplied metadata; independent source review is
required before any trusted-registry change.
