# DipTrace 5.3 fixture pack — pending live capture

Status: `HUMAN_ACTION_REQUIRED`. The current environment has no usable DipTrace
PCB Layout GUI, so this directory contains a plan and pending provenance
manifest only. It contains no claimed DipTrace 5.3 export and no fabricated
XML.

The planned pack is intentionally split into small scenarios:

- empty PCB;
- component angle with top and bottom components;
- NetClass clearance precedence;
- via styles and layer spans;
- basic routing;
- basic schematic;
- basic Component Library;
- basic Pattern Library.

For each scenario, a maintainer with DipTrace 5.3 must create a minimal
project-authored design, save the original, perform the independent GUI action
where relevant, re-export, compute SHA-256 values, and complete the acceptance
audit. Exact application version and build, source type, units, scenario,
semantic comparison, and redistribution basis are mandatory. A controlled
export remains `accepted_for_trust=false` until the existing trust-authority
procedure grants a level.

Do not replace a missing live export with a synthetic fixture. Existing
`tests/fixtures/diptrace_5_3/` is retained as a separate synthetic parser and
operation regression area.

After capture, validate without copying or promoting anything:

```bash
python scripts/ingest_fixtures.py \
  --capture-root <private-capture-root> \
  --candidate .diptrace-capture/candidates/<session>.candidate.json \
  --destination-root tests/fixtures/diptrace-5.3 \
  --fixture-id <fixture-id> \
  --dry-run --json
python scripts/audit_acceptance_seeds.py
```

The first command is a trust-neutral ingest dry-run; its `--apply` mode remains
fail-closed. The second command must be run after any proposed acceptance-tree
change and does not itself grant trust.
