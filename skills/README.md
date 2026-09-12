# DipTrace engineering skills

The canonical catalog is this root `skills/` directory. Its fifteen workflows cover
requirements, schematic and PCB work, native verification, production preparation,
bring-up, and revisions. The same files ship as `diptrace_mcp/skills/` in the wheel;
do not maintain separate edited copies under agent-host directories.

Start with [runtime access](shared/runtime.md) when deciding what the agent can do.
It distinguishes explicit-path MCP, a live XML bridge, native/headless opening,
PCB acceptance, real-window recording, and unavailable export operations.
The [capability map](capability-map.json) lists tool groups, local CLI entry points,
backend requirements, and executable example arguments.

All fifteen skills are **RAG-backed**: the agent works in hardware-engineering mode
by default, without a repeated expert-role prompt. [RAG engineering memory](shared/rag.md)
explains how to assemble, apply and carry forward context from the user's MIT/theory,
schematic/PCB, DipTrace courses and project lessons. Use it to understand the problem,
compare alternatives, anticipate failures and verify results throughout the work,
not only to look up an unknown fact. The marker appears in each skill's discovery
description and body, and as `rag: true` in `catalog.json`.

## Catalog

| Skill | RAG | CAD mode | Outcome |
|---|---|---|---|
| [pcb-design-workflow](pcb-design-workflow/SKILL.md) | [RAG](shared/rag.md) | scoped workflow | specification, stage selection, ordered gates and checkpoint |
| [pcb-project-intake](pcb-project-intake/SKILL.md) | [RAG](shared/rag.md) | read-only | existing project identity, scope, rules and inventory |
| [diptrace-datasheet-rules](diptrace-datasheet-rules/SKILL.md) | [RAG](shared/rag.md) | read-only | official requirements, package and layout evidence |
| [diptrace-bom-sourcing](diptrace-bom-sourcing/SKILL.md) | [RAG](shared/rag.md) | read-only | procurement BOM, stock, variants and substitutions |
| [library-quality-audit](library-quality-audit/SKILL.md) | [RAG](shared/rag.md) | read-only | component/pattern/pin-map validation and installed-library inspection |
| [schematic-engineer](schematic-engineer/SKILL.md) | [RAG](shared/rag.md) | guarded write or review | architecture and editable, visibly wired schematic |
| [schematic-erc-review](schematic-erc-review/SKILL.md) | [RAG](shared/rag.md) | read-only | offline ERC/connectivity/BOM and native-check disposition |
| [critical-net-router](critical-net-router/SKILL.md) | [RAG](shared/rag.md) | guarded write | constrained single-net/pair routes and autorouter handoff |
| [signal-integrity-review](signal-integrity-review/SKILL.md) | [RAG](shared/rag.md) | read-only | analytical impedance, return paths and configured solvers |
| [testpoint-planner](testpoint-planner/SKILL.md) | [RAG](shared/rag.md) | guarded write | standalone probe pads and physical copper connection checks |
| [release-gate](release-gate/SKILL.md) | [RAG](shared/rag.md) | read-only | explicit release decision from required evidence |
| [diptrace-evidence-capture](diptrace-evidence-capture/SKILL.md) | [RAG](shared/rag.md) | native/copy or operator | headless opening/saving, PCB native acceptance, recording and formal evidence |
| [diptrace-production-pack](diptrace-production-pack/SKILL.md) | [RAG](shared/rag.md) | native/copy or operator | actual CAM/assembly artifacts, reconciliation and release package |
| [diptrace-board-bringup](diptrace-board-bringup/SKILL.md) | [RAG](shared/rag.md) | plan or guided hardware | first article, programming, measurements and production tests |
| [diptrace-revision-review](diptrace-revision-review/SKILL.md) | [RAG](shared/rag.md) | read-only; scoped ECO when requested | revision differences, affected gates and revalidation |

CAD read-only modes may create reports/exports or run native verification on isolated
copies; they do not modify the source design. A plan never authorizes applying the plan.
Use the task's existing authorization for edits and local verification. Ordering,
payment, supplier messages, and publication remain separate actions.

## Discovery and handoff

For MCP, use public `tools/list` for exact callable names and `get_capabilities` for
feature/policy/document support. No active editor is needed for explicit-path XML work.
For native operations, discover the local helper and backend separately. Lack of a
native MCP tool does not make supported headless CLI unavailable.

All workflows use [one result schema](shared/result.schema.json). Evidence is labeled
`caller`, `document`, `analytical`, `heuristic`, `external_solver`, or `operator`.
Specifications without CAD can use `document: null`. A successful scoped report, a
native-accepted design, verified CAM, and tested hardware are different outcomes.

Writes require preview, validation, current `expected_sha256`, and applicable
post-checks. Default limits are 100 staged operations and 500 conservatively counted
affected objects/elements; runtime values win. Native roundtrip saves its input, so
protect originals with copies. Formal operator evidence has its own attestation and
metadata-record boundary; ordinary native opening does not require that pipeline.

## Host registration and verification

In this checkout, root `AGENTS.md` routes engineering requests here and root
`opencode.json` registers `./skills` through `skills.paths`, supported by the
[OpenCode configuration schema](https://opencode.ai/config.json).
Wheel installation includes the catalog but does not itself register an agent-host
search path; point that host to the installed `diptrace_mcp/skills` directory.

From a source checkout:

```bash
python scripts/generate_pcb_skills.py --check
python -m pytest -q tests/test_skill_packages.py
```

The tests check RAG marker consistency, catalog/tool contracts, actual native CLI parsers, host registration,
handoff-template parsing, evidence handling, and wheel contents/relative links.
`SOURCES.sha256` covers delivered artifacts and the maintained capture/ingest mirrors.
[Survival criteria](SURVIVAL_CRITERIA.md) prevent duplication without a fixed skill quota.
