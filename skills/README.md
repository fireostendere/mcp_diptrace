# DipTrace MCP skills

This wheel ships eight compact workflows selected by
[the mechanical survival rule](SURVIVAL_CRITERIA.md). They are agent instructions over the
registered MCP/CLI surface, not additional EDA engines and not proof of DipTrace compatibility.

## Installed catalog

| Skill | Mode | Use it for |
| --- | --- | --- |
| [`pcb-project-intake`](pcb-project-intake/SKILL.md) | read-only | project identity, scope, rules, and model inventory |
| [`library-quality-audit`](library-quality-audit/SKILL.md) | read-only | component/pattern validation without mutation |
| [`schematic-erc-review`](schematic-erc-review/SKILL.md) | read-only | ERC, connectivity, BOM, and engineering triage |
| [`testpoint-planner`](testpoint-planner/SKILL.md) | guarded write | explicit standalone-pad testpoint coverage |
| [`critical-net-router`](critical-net-router/SKILL.md) | guarded write | bounded single-net or coupled-pair routing |
| [`signal-integrity-review`](signal-integrity-review/SKILL.md) | read-only | analytical impedance, return path, and configured solvers |
| [`release-gate`](release-gate/SKILL.md) | read-only | explicit evidence-based release decision |
| [`diptrace-evidence-capture`](diptrace-evidence-capture/SKILL.md) | operator-assisted | quarantined round-trip evidence candidates |

All results use [one shared schema](shared/result.schema.json). Every finding and measurement labels
its evidence as `caller`, `document`, `analytical`, `heuristic`, `external_solver`, or `operator`;
one class must never be silently promoted to another.

## Safety and discovery

Start with `diptrace_status`, then `get_capabilities`; document-bound runs also freeze the SHA-256
returned by `get_document_info`. Exact callable names come from public `tools/list`; capability
reports supply session, document, policy, feature, and configured-adapter availability rather than
an exact tool-name inventory.
[The capability map](capability-map.json) records repository-revision scope and limitations but
does not override discovery.

Writes require dry-run staging, bounded preview, validation, explicit confirmation, an
`expected_sha256` commit, and applicable post-checks. The shared implementation limits are
100 staged operations and 500 conservatively counted affected objects/elements per write; the
counter includes normalized, changed-XML, and compiler-only identities, so it may refuse fewer
unique physical objects. Runtime capabilities remain authoritative.

## Delivery and verification

`skills/` is force-included in the wheel as `diptrace_mcp/skills/`; no separate install step is
required. The evidence package contains byte-identical mirrors of the capture and dry-run ingest
CLIs so an installed wheel keeps the operator workflow.

From a source checkout:

```bash
python scripts/generate_pcb_skills.py --check
python -m pytest -q tests/test_skill_packages.py
python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/diptrace-wheel .
```

`SOURCES.sha256` is generated from every delivered skill artifact and verifies that the packaged
CLI mirrors match their maintained root scripts.
