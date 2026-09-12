---
name: schematic-engineer
description: RAG-backed. Design, build, modify, and review electronic devices and schematics through DipTrace MCP with source-backed engineering decisions. Use for architecture, schematic capture, and engineering review; coordinate PCB and production work through pcb-design-workflow when requested. Use when the user says “Design or modify this DipTrace schematic.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# Schematic Engineer

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Use the theory/design corpus for circuit decisions and indexed DipTrace courses for
schematic/library workflows; bind both to the actual circuit and its acceptance checks.

Engineer a device from requirements through an editable DipTrace schematic and, only when
scoped, editable PCB. This project adaptation follows the current user instructions and
project `AGENTS.md`, when present, for RAG, build gates, and media.

## Scope and modes

1. Identify the user's current mode: `design`, `schematic`, `PCB`, or `review`.
2. Follow that exact scope. Review and planning are read-only.
3. A schematic request does not authorize PCB changes, synchronization, manufacturing output,
   or release. A PCB request does not imply fab release.
4. State the target document paths, requested deliverable, protected documents, and acceptance
   gates before mutating anything. Ask only about consequential unresolved ambiguity;
   retain authorization already given in the session.
5. Mark gates outside scope as outside scope, not passed. In a machine-checked
   `PCB_BUILD.md`, keep the supported status vocabulary from its handoff template.

## Evidence before engineering decisions

1. Adopt the default hardware-engineering mode: build and maintain RAG context from circuit
   theory, practical design guides, DipTrace courses and project lessons without a role prompt.
   Use it to reason about architecture, alternatives, failure modes and acceptance throughout work.
2. Discover the configured knowledge tools before calling them. Inspect
   the relevant returned documents/sections, not merely a health check. Retrieve part evidence
   or figures when pinouts, packages, or layout topology require them.
3. Use the uploaded courses and guides for methodology and DipTrace practice, and current
   manufacturer datasheets/errata for exact parts and limits. Use the actual specification and
   [diptrace-datasheet-rules](../diptrace-datasheet-rules/SKILL.md) for project rules.
   Retrieve methodology proactively, including familiar topics and relevant prerequisite material.
4. Record source URI/document ID, revision, page/section, applicable constraint, calculation, and
   resulting decision in the engineering journal. Reuse cited, still-applicable evidence.
5. The current user scope overrides stale documentation. Surface technical/safety contradictions
   and resolve them with authoritative current sources before dependent work.
6. If RAG is offline, use verified project evidence or official sources directly. Block only
   decisions whose required evidence remains unavailable; continue independent work.
7. Do not ingest documents into a remote knowledge base unless authorized.

## Start every DipTrace session safely

1. Discover the exact live DipTrace MCP catalog and schemas; aliases may be
   `diptrace_mcp` or `diptrace`. Never invent a tool, parameter, output, or capability.
2. Call `get_capabilities` when present in the discovered catalog, call `diptrace_status`, then
   read document identity. Use explicit target paths unless the active document is confirmed.
3. Separate an implemented capability from permission to use it. For example, the current
   server policy may be read-only with no preview or commit permission.
4. Never reconfigure permissions or bypass a denied bridge operation. Prefer semantic MCP for
   existing documents. For authorized headless builds, maintained repository builders may produce
   isolated outputs after their inputs, targets, and checks are inspected; they must not overwrite
   a live document or bypass a permission refusal.
5. Use the supported local headless helper for native opening/saving, PCB acceptance, and
   requested capture. It is separate from the bridge and public MCP catalog. Check the installed
   Windows/Wine backend before falling back to an operator or reporting a native blocker.
6. Do not claim native ERC, CAM, PNG, or other native capabilities unless they were detected.
7. If an operation has neither an available MCP implementation nor a supported local native
   workflow, mark that dependent stage `BLOCKED` and continue independent work. A missing MCP
   interface is different from a permission denial; never bypass an actual denial.

## Authoring tools

Use `create_document_from_seed` for a native-derived starting point; `create_schematic_document`
alone is synthetic. Query installed libraries with `query_builtin_library_catalog`, place
verified parts with `place_builtin_component` or `place_part`, and add sheets with `add_sheet`.
Use `connect_pins` for logical membership, `add_wire` for visible wiring, `add_net_label` for
labels, and `set_pin_no_connect` only for intentional NCs. Keep fields and names through
`set_component_fields` and `rename_net`. Their schemas and current tool availability win.

For an existing wired layout, inspect `plan_schematic_placement_repair` and its stored preview,
then apply through `apply_schematic_placement_repair_plan` within the authorized scope. For
native readability use headless schematic roundtrip on a copy; base roundtrip is not native ERC.

## Mutation protocol

Apply this protocol only after the user authorized an editable scoped mode and the server policy
permits it.

1. Confirm scope and protected SHA-256 hashes, including PCB and manufacturing files that must
   not change. Take a supported snapshot before the first batch.
2. For new documents, use a native verified seed. Preserve unknown loader data, settings, and
   object IDs; do not regenerate a whole document by hand.
3. Prefer semantic MCP operations. Use the supported dry-run, preview, and validation operations
   with current hashes and their documented limits before commit.
4. Inspect both geometry and net connectivity before a guarded commit. Use bounded batches and
   never lift safety caps.
5. If a conflict occurs, re-read and reconcile; never overwrite. Roll back only a change made in
   this session, only with a hash guard, and never roll back a user change.
6. After each batch, verify semantic diff and every protected SHA. If a protected file changes
   unexpectedly, stop before further edits and report `FAIL` or `BLOCKED`.
7. Use a low-level XML operation only when semantic MCP support is absent, the bridge offers a
   guarded expert operation, and an authoritative schema supports it. Never wholesale regenerate
   XML.

## Architecture stage

1. Convert requirements into a concise interface and power-domain map.
2. Budget power, startup, heat, and operating margins with stated assumptions and calculations.
3. Identify the exact MCU/device variant, boot and strap pins, reserved pins, clocks, reset,
   programming/debug access, and test access.
4. Trace engineering limits, selected component values, and numeric design constraints to an
   authoritative datasheet, application note, or manufacturer process source plus calculations.
   Do not use universal clearance, pull-up, stitching, or other numeric defaults from memory;
   coordinates used only for drawing placement need not be independently sourced.
5. Distinguish house style from manufacturer rules. House style improves readability; it never
   overrides electrical, package, fab, or safety requirements.
6. Do not proceed past an unresolved safety, power, pinmux, or sourcing assumption.

## Parts and library discipline

1. Search for the exact installed DipTrace MPN first, then an approved catalog such as LCSC or
   JLCPCB with a verified imported mapping.
2. For every physical component, validate the reused or custom symbol's exact variant pin numbers,
   electrical pin types, pin-pad map, exact manufacturer package, and land pattern against official
   data before placement. For ICs, also inspect current layout guidelines/examples and revision
   history. For custom parts, document search misses. Missing required evidence blocks physical
   placement; unavailable supported library creation blocks that part, not independent work.
3. Preserve valid existing exact symbols. Rectangular bodies are valid when native and verified;
   never substitute an unverified placeholder rectangle for a component.
4. Do not assign PCB footprints to Net Ports.

## Schematic construction

1. Work one functional sheet at a time. Establish readable left-to-right signal flow, native power
   symbols above, and local native GND symbols below; text labels do not replace these symbols.
2. Keep each support network near its IC and wire visibly and locally with orthogonal direct
   wires and clear pin escape. Keep readable labels and notes wholly inside usable page bounds,
   clear of the frame, components, pins, and wires. Verify extents of ALL objects, including
   power symbols and notes; a viewport does not repair geometry.
3. For cross-sheet/global nets, use a visible native Net Port on every participating sheet, wired to
   its actual pin. Use the intended net name as the component `Name` (not pin text), respect hierarchy
   scope, and verify pin-bound membership.
   Text `NetId` is only a label. Verify names and membership survive a roundtrip.
4. DipTrace Connect Nets by Name is also a valid alternative when explicitly selected and
   verified; do not falsely present ports as the only connectivity mechanism.
5. Verify per-pin connectivity graph, intentional NC pins, and duplicate switch contacts. Never
   hide an error with NC markings or disabled ERC.
6. Make the overview a real diagram, not only a table of contents. Documentary shapes must not
   accidentally create nets or BOM entries.
7. Inspect the native view at normal zoom and page fit, not only a renderer.
8. Before scaling, build a representative sheet and pass structural, electrical, readability, and
   open-save-reexport gates. Where supported, make an isolated safe test copy to verify native
   pin/net membership, names, and a port rename.

## PCB stage: explicit scope only

Begin only after schematic acceptance and PCB work is authorized. Use
[pcb-design-workflow](../pcb-design-workflow/SKILL.md) for the repository gate order and
[PCB implementation](../pcb-design-workflow/references/board-layout.md) for implementation recipes.

1. Verify schematic-to-PCB synchronization, exact pin-pad mapping, package land patterns, and
   vendor layout sources before placement.
2. Establish board outline, mechanics, connector datums, mounting constraints, and keepouts
   before component placement.
3. Select stackup from electrical constraints and authoritative fab/process evidence.
4. Place decoupling and hot-loop critical components locally. Preserve continuous return paths;
   handle differential, RF, USB, thermal, ground-fill, stitching, and connector thermal needs
   from evidence, not habit.
5. Never use via-in-pad without an approved manufacturing process. Zero ratlines alone is not
   acceptance.
6. Validate silkscreen, assembly readability, fab capabilities, DFM, and BOM/CPL correspondence.
7. Netclass rules may not be enforced by MCP. PCB acceptance requires native refill, connectivity,
   and DRC; unavailable native evidence blocks acceptance rather than being skipped.

## Acceptance and reporting

Use separate gates. An offline MCP check is not a native acceptance substitute.

1. Run available offline MCP reviews such as `run_erc` or `run_drc`, but identify when they are
   XML-profile checks rather than native execution.
2. Schematic acceptance requires native open/save/re-export plus native connectivity and ERC.
   If native evidence is unavailable, acceptance is `BLOCKED`, never `PASS` or `N/A`.
3. PCB acceptance requires native refill plus native connectivity and DRC. If native evidence is
   unavailable, acceptance is `BLOCKED`, never `PASS` or `N/A`.
4. Manufacturing-output inspection is separately required only when fab deliverables or release
   are requested. Missing export capability blocks release only; it does not force CAM for
   schematic or PCB editing.
5. Never release fabrication after only XML or geometry audit. A known failure remains `FAIL`.
6. Bind every report to exact path, SHA-256, tool/document version, gate status
   (`PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`), and remaining issues.
7. Maintain a small append-only engineering journal: phase, evidence, decision, mutation batch,
   exact resume point, and last passed gate.
8. Maintain PCB_BUILD.md for PCB work and run the repository quality gate before resuming or
   handing off a built board. Follow current AGENTS.md media requirements after visual PCB
   changes; schematic-only recordings follow explicit user scope. Final responses list actual
   paths, hashes, verified and unverified gates, and remaining issues.

## Project references

Read relevant local skills directly; their contents do not require RAG retrieval.

- [Schematic style](references/schematic-style.md): exact component resolution,
  human-readable placement, local wiring, native ports, page containment, and overview diagrams.
- [schematic-erc-review](../schematic-erc-review/SKILL.md): bounded offline checks;
  these do not replace native ERC or engineering review against component requirements.
- [library-quality-audit](../library-quality-audit/SKILL.md): library pin/pad checks.
- [pcb-design-workflow](../pcb-design-workflow/SKILL.md): specifications, build gates, production,
  bring-up, and revision handoffs.

## Import provenance

Adapted from OpenCode `~/.config/opencode/skills/schematic-engineer/SKILL.md`,
original SHA-256 `7d692c27e82fbbb432c24514df22704734870e75744bc47800baefc73994bdac`.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
