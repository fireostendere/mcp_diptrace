# Skill Contracts

The MCP server performs parsing, geometry, deterministic checks, planning, exact edits,
and safety enforcement. The model selects critical nets, functional groups, trade-offs,
and remediation strategy. Every write workflow must read capabilities and the source
SHA, show a preview, and run post-write checks.

## Release Review

`review_board_before_release`: information/capabilities -> board/connectivity/stackup ->
DRC, board, manufacturing, assembly, testability, BOM, and return-path review -> model
synthesis. Stop on blocking findings, skipped mandatory checks, or an incomplete stackup.

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
DRC/connectivity -> commit. Stop when vias, push-and-shove behavior, or unknown rules are required.

`route_diff_pair_with_constraints`: stackup/pair/length/analytical impedance ->
`plan_diff_pair_route` -> SVG/JSON plus skew/via metrics -> `apply_route_plan` -> pair
validation and DRC. Stop on an incomplete stackup, incompatible pad spacing or
orientation, unresolved DRC, or SHA conflict. A coupled plan must not be replaced with
two independent `route_net` calls. Analytical impedance remains preliminary-only.

`review_return_paths`: stackup/pours/plane continuity/return path. Results are heuristic;
the model determines criticality. Stop when the reference plane or refill is unknown.

## Manufacturing UX

`clean_silkscreen_for_manufacturing`: check -> plan -> unresolved items/preview ->
dry-run -> commit -> recheck. Locked labels are neither moved nor hidden.

`add_testpoints_for_fixture`: connectivity/current coverage/candidates -> model target
selection -> dry-run -> testability/DRC -> commit. Accessibility remains an estimate and
is labeled accordingly.

`prepare_fabrication_export`: all release checks -> generic manifest only. Stop because
the MCP server does not generate Gerber or NC Drill; the bundle must not be described as
fabrication-ready.

`prepare_assembly_export`: assembly/BOM/silkscreen -> generic BOM/placement. The model
selects the assembly variant. Stop on DNP ambiguity or an unknown assembler coordinate convention.

`review_bom`: normalized BOM -> missing fields and MPN/value-pattern consistency. Online
sourcing is unavailable; substitution remains a model decision.

`compare_schematic_and_pcb`: exact document pair -> compare RefDes, values, nets, and
endpoints. Stop before edits on ambiguous pin-to-pad mapping or a changed SHA.

All listed contracts are also exposed as concise MCP prompts. This document is the
expanded contract for external skills.
