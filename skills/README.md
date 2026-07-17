# PCB Skills for DipTrace MCP

This catalog contains 57 permanent skill packages spanning a PCB project from requirements intake and architecture through engineering reviews, release artifacts, bring-up, and regression control. [catalog.json](catalog.json) is the source of truth for the package inventory and workflow-specific content.

## Package Structure

Each package lives under `skills/<slug>/` and contains:

- `SKILL.md`: the executable workflow contract;
- `agents/openai.yaml`: display metadata and the default prompt;
- `schemas/result.schema.json`: the strict result JSON Schema;
- `examples/result.example.json`: a schema-valid representative result;
- `evals/scenarios.json`: behavioral input scenarios;
- `evals/assertions.json`: expected tool, safety, degradation, and output assertions.

Add this catalog to the agent platform's skill roots. The platform discovers a package through `skills/<slug>/SKILL.md` and reads interface metadata from the adjacent `agents/openai.yaml`. See [pcb-project-intake/SKILL.md](pcb-project-intake/SKILL.md) and [pcb-project-intake/agents/openai.yaml](pcb-project-intake/agents/openai.yaml).

## Capability Discovery

Every skill starts in this strict order: `diptrace_status` -> `get_capabilities`. A document-bound workflow then resolves the exact target through `get_document_info` and captures its SHA-256; a genuine pre-design workflow instead records `pre_design` applicability and hashes its normalized input bundle. Capability names in the catalog are target contracts, not promises that identically named MCP tools exist. [capability-map.json](capability-map.json) records runtime aliases, limitations, missing contracts, and context-specific incompatibilities.

When a required capability is absent, a skill must not imitate it with a heuristic or call an invented tool name. It returns `blocked_by_capability` with a dependency report, or `partial` when independent stages remain valid. An unavailable capability blocks only dependent stages, while `completed` is forbidden if a mandatory check was skipped.

[dependency-contracts.json](dependency-contracts.json) defines exact inputs, outputs, and invariants for unavailable integrations. These are extension contracts for a future MCP tool or adapter, not hidden fallback implementations.

## Execution Modes

- `read_only`: reads and reports only; transactions and design changes are forbidden.
- `preview_write`: permits writes only through status/capabilities -> document SHA -> scope and locks -> typed semantic operation with `dry_run=true` -> preview -> validation -> explicit `commit_transaction(..., expected_sha256=...)` confirmation -> applicable ERC/DRC/connectivity checks -> stop or rollback on regression.
- `artifact_export`: creates bounded external artifacts without mutating the source design; prerequisites, validation, a manifest, and SHA-256 evidence remain mandatory. The mode does not imply that a requested native exporter is installed.

Locked objects, keepouts, user constraints, explicit no-connects, DNP state, and waivers are preserved in every mode.

## Validation

From the repository root:

```bash
.venv/bin/python scripts/generate_pcb_skills.py --check
.venv/bin/python -m pytest -q tests/test_skill_packages.py
```

`--check` verifies that all 57 packages are reproducible from their sources and contain no hand-edited drift. Pytest is the only executable skill test suite; it validates structure, schemas, examples, capability mappings, scenarios, and eval assertions. Files under each package's `evals/` directory are test data consumed by that central suite, not a second test runner.

For an additional frontmatter and naming check, run `quick_validate.py` from an installed `skill-creator` package:

```bash
.venv/bin/python path/to/skill-creator/scripts/quick_validate.py skills/pcb-project-intake
```

This external validator requires PyYAML. Use an environment that includes it; a missing validator dependency is not a skill validation failure.

## Updating Packages

Do not edit generated files under `skills/<slug>/` directly. Change these sources instead:

1. [catalog.json](catalog.json): purpose, inputs, capabilities, workflow, outputs, acceptance criteria, and execution mode;
2. [capability-map.json](capability-map.json): runtime aliases, limitations, and context overrides;
3. [dependency-contracts.json](dependency-contracts.json): exact contracts for unavailable MCP or adapter capabilities.

Regenerate and verify packages after changing a source:

```bash
.venv/bin/python scripts/generate_pcb_skills.py
.venv/bin/python scripts/generate_pcb_skills.py --check
.venv/bin/python -m pytest -q tests/test_skill_packages.py
```

When the catalog gains a new slug whose directory does not exist, run the generator with `--initialize --init-script` and the path to `skill-creator`'s `init_skill.py`. The generator remains authoritative after initialization.
