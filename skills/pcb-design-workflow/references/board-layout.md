# DipTrace PCB implementation

Use [runtime access](../../shared/runtime.md) and the lifecycle's ordered gates. This
recipe covers the public MCP surface and identifies stages that need a validated
project builder or native operation. It does not claim a general PCB autorouter or
native CAM exporter.

Start from the shared [RAG engineering memory](../../shared/rag.md): combine circuit
and return-current principles, practical board-layout lessons, and DipTrace placement,
pour and routing workflows. Use that context to choose critical placement, evaluate
alternatives, anticipate failure modes and review the finished geometry.

## Establish the board

1. Read the accepted schematic and exact symbol/pin/pad/land-pattern evidence. Use
   `validate_pin_pad_mapping` and `compare_schematic_to_pcb` when both documents exist.
2. Prefer `create_document_from_seed` with a verified real export. Synthetic
   `create_pcb_document` can specify outline, layers, stackup, and rules, but parser
   success is not native acceptance. `pipeline_nativeize_document` prepares a separate
   generated candidate; validate units, geometry, mappings, and native roundtrip.
3. Preview `sync_schematic_to_pcb` with explicit component mappings. Inspect additions,
   reconnections, existing placements, DNP/documentary objects, and locks before commit.
4. Freeze mechanical outline, holes, enclosure/connector datums and keepouts. Derive a
   compact outline from occupied space and manufacturing margins; connectors may fix a
   board dimension. Prefer the simplest, smallest practical footprint for standard
   2.54 mm connectors, subject to exact package and mechanical evidence.
   Existing outline/stackup edits must use an advertised semantic
   operation, supported guarded expert XML, or a validated project builder; do not
   invent an outline-editing tool.

## Place and route

- Follow the exact IC layout figures for decoupling, hot loops, feedback/Kelvin paths,
  clocks, RF/antenna keepouts and thermal paths. Record every intentional deviation.
- Use `analyze_placement`, `generate_placement_candidates`, `score_placement`,
  `plan_component_placement`, `legalize_component_placement`, and
  `apply_component_placement_plan` as applicable. Geometric ranking cannot decide
  which component implements a hot loop; identify that from the circuit first.
- For ordinary two-layer boards, prefer signals/positive supply on Top, continuous
  Bottom GND, and Top GND pour. Source other stackups from actual requirements and fab
  evidence. Configure explicit netclasses/pair rules with
  `update_net_class_rules`, `assign_nets_to_class`, `set_diff_pair_rules`, and
  `set_length_constraints` where supported.
- Route critical nets first through [critical-net-router](../../critical-net-router/SKILL.md),
  then the remaining nets. Coupled pairs stay paired. Check return paths, width,
  clearance, layer transitions, and actual zero-ratline connectivity.
- For a configured external autorouter, use `export_autorouter_dsn`,
  `run_external_autorouter`, `get_job_status`, `get_job_result`,
  `inspect_autorouter_result`, and guarded `import_autorouter_ses`. Keep DSN/SES
  provenance and unsupported-geometry disclosures; do not accept a job merely because
  the external process exited successfully.
- Disable via-in-pad by default. Escape beyond pad copper plus required clearance.
  A filled/capped compatible process must be explicitly requested before exceptions.
  Do not resize verified footprint copper to hide a routing/clearance defect.

## Ground and finish

Choose ground topology from current datasheets and revision histories. Default to a
continuous return plane on ordinary boards; never infer split AGND/PGND planes merely
from pin names. Preserve all manufacturer pad geometry and exposed-pad connections.

Read `list_copper_pours`, `analyze_plane_continuity`, and `analyze_return_path` for
exported geometry. These are not native refill. There is no dedicated semantic
copper-pour creation tool: use a supported guarded operation/native workflow or a validated existing
builder for that stage, then run native refill. The source checkout has
`diptrace_mcp.copper_pours`, but its Python helper is not a public MCP transaction.

Stitch free regions on both layers, starting around a 2 mm grid on small boards and
checking coverage/clearance per region. Hand-soldered connector GND pads use four-spoke
thermal relief. Keep vias outside pads unless the requested process permits them.
Use [testpoint-planner](../../testpoint-planner/SKILL.md) for accessible probes and
route their physical copper connections.

Run `check_silkscreen`, `plan_silkscreen`, `apply_silkscreen_plan`, and post-checks.
Keep labels readable and near their parts, clear of mounting space, pads, holes and
vias. Covered traces do not by themselves forbid silkscreen.

Finish with offline review/QC, then
[native acceptance](../../diptrace-evidence-capture/SKILL.md), media inspection, and
the [production package](../../diptrace-production-pack/SKILL.md) when requested.
Historical builder settings, automatic pad shrinking, permissive native-error tables,
and merging thermal grids are not substitutes for the current source evidence.
