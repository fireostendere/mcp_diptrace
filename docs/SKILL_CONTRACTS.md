# Skill Contracts

The MCP server performs parsing, geometry, deterministic checks, planning, exact edits,
and safety enforcement. The model selects critical nets, functional groups, trade-offs,
and remediation strategy. Every write workflow must read capabilities and the source
SHA, show a preview, and run post-write checks.

## Delivered Catalog

The canonical `skills/` catalog ships fifteen source-authored workflows: the original
eight inspection, editing and evidence skills plus schematic engineering, lifecycle
coordination, datasheet rules, BOM sourcing, production packaging, bring-up, and revision
review. The [catalog](../skills/README.md) links each distinct outcome. Shared
[runtime access](../skills/shared/runtime.md) explains explicit-path MCP, the live bridge,
and native/headless CLI; [one result schema](../skills/shared/result.schema.json) records
evidence. Package references stay within the shipped skill tree. The old fixed eight-skill
quota has been removed; [survival criteria](../skills/SURVIVAL_CRITERIA.md) still prohibit
duplicate workflows and invented capabilities.

The evidence skill first uses supported headless opening/saving, PCB acceptance, or
native recording. These are local CLI interfaces and do not have to appear in MCP
`tools/list`. Read-only review uses isolated copies because native roundtrip saves its
input. The base helper opens all four editors but does not implement generic native
ERC or CAM export. Linux and macOS wrappers have different path-conversion behavior.

For formal operator-supplied evidence, the skill also ships byte-identical capture and
dry-run ingest scripts. Their candidate -> ingest dry-run -> MCP validation -> operator
confirmation -> metadata-record sequence cannot promote trust or modify acceptance
fixtures. Ordinary headless opening does not require this legacy candidate pipeline.

## RAG-backed Hardware Engineering

All catalog skills carry `rag: true`, a discovery-description marker and a link to
[shared engineering memory](../skills/shared/rag.md). Hardware-engineering mode is
the default; the user does not need to restate an expert persona or request retrieval.
Build a focused working context from the user's MIT/theory courses, schematic/PCB
guides, DipTrace courses and project lessons. Use it throughout problem framing,
tradeoffs, implementation, failure analysis and review; carry it between stages.
Model confidence is not a gate on retrieval. Source-based learning supplements
current CAD facts, exact official part/process constraints and actual verification.

Knowledge search/read is a separate configured MCP capability, not a DipTrace tool
or a bundled corpus. Disclose unavailable retrieval and any fallback; do not fabricate
course references or count a retrieved recommendation as a passed native check.

## Release Review

`review_board_before_release`: information/capabilities -> board/connectivity/stackup ->
DRC, board, manufacturing, assembly, testability, BOM, and return-path review -> model
synthesis. Compare the result with the
[implemented/partial/missing coverage matrix](REVIEW_ENGINE.md). Stop on blocking
findings, skipped mandatory checks, an uncovered mandatory category, or an incomplete
stackup.

`review_schematic_before_layout`: schematic/connectivity -> ERC/schematic review -> BOM
and PCB comparison when available. Stop on ambiguous hierarchy or mapping, or missing patterns.

## Placement

`place_selected_components_safely`: explicit selector/region -> query -> placement
analysis/candidates/plan -> SVG/JSON -> dry-run transaction -> DRC -> commit. The model
selects the plan.

`place_decoupling_network`: the model first identifies the IC, power pins, and capacitors;
the MCP server only evaluates connectivity and local placement. Stop when pin roles or
body geometry are unknown.

## Routing and SI

`route_critical_net`: rules/stackup/unrouted/details -> bounded route plan -> preview ->
DRC/connectivity -> commit. Stop when required via geometry/policy is unsupported,
push-and-shove is needed, or applicable rules are unknown.

`route_diff_pair_with_constraints`: stackup/pair/length/analytical impedance ->
`plan_diff_pair_route` -> SVG/JSON plus skew/via metrics -> `apply_route_plan` -> pair
validation and DRC. Stop on an incomplete stackup, incompatible pad spacing or
orientation, unresolved DRC, or SHA conflict. A coupled plan must not be replaced with
two independent `route_net` calls. Analytical impedance remains preliminary-only.

`review_return_paths`: stackup/pours/plane continuity/return path. Results are heuristic;
the caller must supply the return-via search radius and the model determines criticality.
Reference-net stable/XML identity takes precedence over a display name. Equal-rank
reference-layer candidates, missing explicit via spans, three-point coverage sampling,
or unknown refill are disclosed and keep confidence low. Stop when the reference plane
or refill is unknown.

## Manufacturing UX

`clean_silkscreen_for_manufacturing`: check -> plan -> unresolved items/preview ->
dry-run -> commit -> recheck. Locked labels are neither moved nor hidden.

`add_testpoints_for_fixture`: connectivity/current coverage/candidates -> model target
selection -> dry-run -> testability/DRC -> commit. Accessibility remains an estimate and
is labeled accordingly.

`prepare_fabrication_export`: applicable registered release checks -> explicit review of
skips and missing categories -> generic manifest only. The MCP server does not generate
Gerber or NC Drill. Obtain them through a supported native export or operator workflow;
until actual CAM is inspected, do not describe the bundle as fabrication-ready.

`prepare_assembly_export`: assembly/BOM/silkscreen -> generic BOM/placement. The model
selects the assembly variant. Stop on DNP ambiguity or an unknown assembler coordinate convention.

`review_bom`: normalized BOM -> missing fields and MPN/value-pattern consistency.
`pipeline_source_component` can fetch catalog JSON/PDF, not reserve stock or certify
assembly availability. Verify current supplier stock separately; substitution requires
an engineering decision and authorization to change CAD.

`compare_schematic_and_pcb`: exact document pair -> compare RefDes, values, nets, and
endpoints. Stop before edits on ambiguous pin-to-pad mapping or a changed SHA.

The server also exposes concise MCP prompts for several lower-level contracts. Prompt
count is independent of the delivered skill catalog; a prompt or registered tool
does not by itself qualify a distinct wheel-shipped skill.
