# PCB skill survival criteria

The former 57-package catalog repeated transport rules, schemas, and generic PCB prose. A package
survives only when all four checks below are true:

1. Its trigger selects a distinct user outcome that is not already a stage of another survivor.
2. Its workflow maps to registered MCP tools or a shipped deterministic CLI, with unavailable work
   stated as a refusal.
3. It contains quantitative, source-linked operating limits or evidence rules beyond generic
   “inspect, report, validate” prose.
4. It is discoverable from the wheel and is covered by the shared schema, capability, link, and
   forward-path tests.

The rule was applied mechanically: group the 57 old slugs by outcome, keep one package only when it
passes all four checks, and merge the useful bounded stages into that survivor. The result is eight
packages:

| Survivor | Distinct outcome | Consolidated families |
| --- | --- | --- |
| `pcb-project-intake` | bounded project inventory | requirements, architecture, constraints, documentation |
| `library-quality-audit` | component/pattern library validation | library creation review and quality review; mutation remains refused |
| `schematic-erc-review` | schematic/ERC disposition | schematic, power-tree, interface, boot, BOM, and consistency reviews |
| `testpoint-planner` | guarded testpoint coverage | DFT, fixture planning, and testability |
| `critical-net-router` | bounded critical-net routing | route priority, single/differential routing, cleanup, and autorouter handoff |
| `signal-integrity-review` | analytical SI evidence | stackup, impedance, return path, EMC, and external solver adapters |
| `release-gate` | explicit `PASS`/`BLOCKED` decision | DRC, DFM, DFA, thermal, manufacturing, and release review |
| `diptrace-evidence-capture` | operator-assisted round-trip evidence candidate | probe execution, quarantine, dry-run ingest, and MCP metadata intake |

Removed package names are not aliases and are not advertised as installed features. Generic
orchestration, evaluation, and multi-agent wrappers failed the distinct-outcome check; duplicated
placement, routing, review, manufacturing, and documentation packages became stages of the eight
survivors. Reintroducing a package requires a new outcome and an executable forward-path test.
