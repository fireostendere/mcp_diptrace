# Acceptance Seed Audit

`scripts/audit_acceptance_seeds.py` is a bounded, read-only consumer for a
candidate DipTrace fixture pack. It validates the existing
[v2 fixture manifest schema](../tests/fixtures/diptrace_5_3/manifest.schema.json),
the corresponding `FixtureManifest` invariants, canonical in-root paths, exact
SHA-256 values, and each file's actual XML or Specctra source type.

Passing the audit does not prove that a human actually used DipTrace, does not
authenticate the manifest author, and does not promote trust. Every result,
including a structurally valid real export, therefore contains:

```json
{
  "registry_consulted": true,
  "registry_entry_count": 0,
  "registry_match": false,
  "sidecar_authority_used": false,
  "trust_promoted": false,
  "written": false
}
```

The separately reviewed repository registry is the authority boundary. This
consumer reads its actual entry count, but deliberately does not write to it or
infer a match from an unregistered seed manifest. A
`.provenance.json` sidecar next to a seed is not treated as authority.

## Current CI result

The protected
[acceptance seed directory](../tests/fixtures/acceptance/diptrace_5_3/seeds/README.md)
currently contains instructions and no seed data. The default command is:

```bash
python scripts/audit_acceptance_seeds.py
```

It exits successfully with JSON containing `status: "no_seeds"` and
`seed_count: 0`. If data appears without `manifest.json`, if a path escapes the
root, if bytes or source type disagree with the manifest, or if provenance
invariants fail, it exits nonzero with `status: "invalid"`.

The README inside the protected seed directory predates the current v2
manifest authority boundary and still describes a per-file sidecar procedure.
That procedure is stale: the audit warning points here, while the protected
file itself remains byte-untouched under the repository's acceptance-fixture
rule.

## Literal synthetic stand-in check

This procedure exercises the CLI mechanics outside the protected tree. Its
values explicitly describe a synthetic test stand-in, not a DipTrace export.
It cannot become acceptance evidence and the audit still grants no trust.

Run this Python block from the repository root. By default it creates a new OS
temporary directory and prints its path. Tests run this exact block with
`SEED_AUDIT_STANDIN_ROOT` set to a fresh pytest temporary directory.

<!-- SYNTHETIC_STANDIN_PY_BEGIN -->
```python
import hashlib
import json
import os
import tempfile
from pathlib import Path

configured_root = os.environ.get("SEED_AUDIT_STANDIN_ROOT")
stand_in_root = (
    Path(configured_root)
    if configured_root
    else Path(tempfile.mkdtemp(prefix="diptrace-seed-audit-"))
)
stand_in_root.mkdir(parents=True, exist_ok=True)
xml = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Source Type="DipTrace-PCB" Version="5.3.0.0" Units="mm"><Board/></Source>\n'
)
(stand_in_root / "board.xml").write_bytes(xml)
manifest = {
    "schema_version": "diptrace-fixture-manifest-v2",
    "diptrace": {
        "version": "5.3.0.0",
        "build": "synthetic-stand-in-not-a-real-build",
        "operating_system": "synthetic-test-environment",
    },
    "redistribution": {
        "permitted": True,
        "basis": "Temporary synthetic stand-in generated outside the acceptance tree.",
    },
    "fixtures": [
        {
            "path": "board.xml",
            "source_type": "DipTrace-PCB",
            "sha256": hashlib.sha256(xml).hexdigest(),
            "validation_level": "synthetic_parser_only",
            "provenance": "synthetic_test_stand_in_not_diptrace_evidence",
            "units": "mm",
            "workflow": "Temporary auditor contract test; DipTrace was not involved.",
            "purpose": "Exercise manifest/path/hash/source-type validation only.",
            "format_version": "5.3.0.0",
        }
    ],
}
(stand_in_root / "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n",
    encoding="utf-8",
)
print(stand_in_root)
```
<!-- SYNTHETIC_STANDIN_PY_END -->

Audit the printed directory:

```bash
python scripts/audit_acceptance_seeds.py --root /the/printed/temporary/directory
```

The expected result is `status: "valid"`, one
`synthetic_parser_only` entry, `registry_consulted: true`, and no registry
match, trust promotion, sidecar authority, or write. Deleting or changing one
byte of `board.xml` after creating the manifest must make the audit fail with a
SHA-256 mismatch.

## Real operator handoff

For a real candidate pack, an operator should work in a staging directory
outside `tests/fixtures/acceptance/`:

1. Preserve the exact exported bytes; do not normalize encoding, whitespace,
   identifiers, or XML structure.
2. Create `manifest.json` conforming to the committed v2 schema. Record the
   actual DipTrace version/build/OS, source role, SHA-256, workflow,
   redistribution grant, and only the validation level supported by the
   captured evidence.
3. Run the auditor with `--root` and preserve its JSON report.
4. Submit the candidate bytes, manifest, legal basis, and operator evidence for
   independent review. A green audit is necessary but not sufficient.
5. Let a separate reviewed registry change establish authority. This script
   never copies a candidate into the protected tree and never edits that
   registry.

Do not repair a failing candidate to fit an expected convention. Preserve the
failure and either correct only demonstrably wrong metadata or record the
unknown in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
