---
name: diptrace-production-pack
description: RAG-backed. Prepare and inspect a versioned DipTrace fabrication and assembly package with real native CAM files, reconciled BOM/CPL, production instructions, and release evidence. Use for Gerber/NC Drill, assembly files, JLCPCB handoff, or a fabrication release; «файлы на производство». Use when the user says “Prepare this DipTrace board for fabrication and assembly.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# DipTrace production package

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Use DFM/DFA guides and indexed DipTrace CAM/assembly-export courses to establish the
release checklist and export procedure; verify current supplier and installed-editor requirements.

Prepare a local package for the chosen fabricator and assembler. A fabrication
manifest is not Gerber; preparing files does not authorize upload, purchase,
payment, or sending supplier messages.

## Freeze the release

1. Resolve project revision, board and schematic paths/hashes, fitted variant, quantity,
   supplier, stackup/material/finish, and assembly process. Reuse project decisions;
   ask only about unresolved choices that materially affect the output.
2. Run [release-gate](../release-gate/SKILL.md) and the `PCB_BUILD.md`
   quality gate from [pcb-design-workflow](../pcb-design-workflow/SKILL.md).
   Inspect pending gates even when the script exits zero.
3. Require evidence for the exact final PCB: footprint/pin map, schematic comparison,
   zero ratlines, headless QC, and native refill/connectivity/DRC. Use
   [native evidence capture](../diptrace-evidence-capture/SKILL.md).
   File edits after verification invalidate affected evidence and exports.
4. Verify the selected supplier's current manufacturing and BOM/CPL requirements from
   official sources. Record constraints and check date; do not borrow another fab's
   clearance, stackup, panel, coordinate, or rotation conventions.

## Generate the actual outputs

Discover live capabilities and inspect `diptrace_mcp.services.exports` when needed.
Currently:

| MCP call | Actual result |
|---|---|
| `export_bom` | Generic BOM CSV and provenance |
| `export_fabrication_outputs(request_native_outputs=false)` | Review manifest, no Gerber/NC Drill |
| `export_assembly_outputs(request_native_outputs=false)` | Generic BOM/placement, not vendor-certified CPL or assembly drawings |
| Either export with `request_native_outputs=true` | Capability unavailable |

Use these exports as inputs, preserve their limitations, and fetch all artifact resources.
Obtain real Gerber, NC Drill, required drawings, and native placement exports through a
supported native DipTrace export workflow or operator export from the frozen revision.
The native acceptance helper does not implement CAM export. If a required exporter or
artifact is unavailable, prepare the remaining package and mark release BLOCKED with
an exact export checklist. Do not fabricate CAM from SVG, JSON manifests, or filenames.

## Inspect and reconcile

- Inspect all copper, mask, silk, outline/cutout, and applicable paste layers together
  in a CAM viewer, with plated/non-plated drills and slots. Check units, scale,
  origin, outline closure, drill alignment, edge clearances, and layer completeness.
- Bind native export provenance to the board hash. Check assembler rotation and
  Bottom-side mirroring conventions against native placement and the actual assembly
  view, including pin 1 and polarities. Never blindly rotate or mirror every part.
- Reconcile fitted RefDes, quantities, MPN/package, side, and placement across CAD,
  BOM, and CPL. Distinguish DNP, SMT, through-hole, and hand-installed parts; list
  intentional exclusions. Use [BOM sourcing](../diptrace-bom-sourcing/SKILL.md).
- For panelization, verify agreed rails, fiducials, tooling, tabs/V-cuts, copper
  clearance, and component overhang from fab rules. Do not add a panel by default.
  When panelization changes the output, validate the resolved panel separately.
- Include fabrication notes, stackup, assembly/polarity drawings, stencil/process
  requirements, programming image/hash and settings when relevant, testpoint map,
  first-article and production acceptance instructions. Reuse
  [board bring-up](../diptrace-board-bringup/SKILL.md) for the test plan.

## Package and hand off

Create a new `release/<revision>-<variant>/` with the actual fabrication, assembly,
and evidence artifacts plus `RELEASE.md` and `SHA256SUMS`. Record source CAD hashes,
tool versions, manufacturing parameters, BOM stock timestamp, waivers, missing checks,
and disposition. Preserve earlier releases; do not silently overwrite them.

Create the ZIP only from an explicit reviewed file list. Verify archive contents,
hashes, nonempty outputs, revision consistency, and CAM/assembly inspection evidence.
Report PASS only when required gates and files are verified; a prepared draft with
missing exports remains BLOCKED. Actual supplier submission or ordering needs existing
authorization for that separate action.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
