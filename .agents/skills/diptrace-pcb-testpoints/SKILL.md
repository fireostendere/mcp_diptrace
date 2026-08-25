---
name: diptrace-pcb-testpoints
description: Plan and place physical PCB test points (standalone probe pads) on a DipTrace board through the DipTrace MCP server — coverage audit, free-grid candidate selection, guarded dry-run placement, stub routing, and post-checks. Use when the user asks to add or place testpoints on a PCB, improve probe access or testability, plan fixture/bed-of-nails points, or audit PCB test-point coverage.
---

# DipTrace PCB Test Points

Headless PCB-only workflow over the DipTrace MCP server. For schematic-wired
test points use the separate `diptrace-testpoints` skill. Datasheets, DRC, and
manufacturability override anything here.

## Parse the request

- `nets=` explicit net list. Without it, build a proposal from
  `review_testpoint_coverage` plus design knowledge and confirm before writing.
- `side=Top|Bottom` — default Top.
- `pad=<mm>` probe pad diameter, default 1.0 mm; `hole=<mm>` default 0
  (surface pad). Through-hole only when requested.
- `grid=<mm>` candidate grid, default 2.54 mm.
- `mode=review|plan|apply`. Direct "add testpoints" means apply, but show the
  placement table before committing.

## Hard rules

1. Always call `add_testpoints` with `dry_run=true` first; commit only with
   the preview's `expected_sha256`.
2. Never place a TP on an RF antenna feed, crystal, switching node, reset, or
   high-impedance analog net unless the user explicitly names that net.
3. One TP per net. Skip nets already covered by `list_testpoints`.
4. Candidate generation avoids component/testpoint/keepout bounding boxes but
   NOT traces, vias, or pads. Sanity-check every chosen coordinate against
   routed geometry before committing, and run DRC after.
5. The TP pad joins its net logically; copper still needs a pour (typical for
   GND) or a short stub trace to the nearest same-net pad. Escape beyond the
   pad copper edge plus applicable clearance before any via; via-in-pad stays
   disabled.
6. Keep TPs off the board-edge margin (≥0.5 mm, more for pogo fixtures) and
   out of connector and tall-component shadows; enclosure shadowing is not
   modeled by the tools.
7. Auto RefDes is `TP<n>`; pass `refdes` only to keep a fixture map stable.

## Workflow

1. `diptrace_status`, then `summarize_design` on the PCB path.
2. Baseline: `list_testpoints` and `review_testpoint_coverage`.
3. Choose target nets: functional signals worth probing; power/GND only when
   the user wants supply probing. List intentionally skipped nets with reasons.
4. `find_testpoint_candidates(target_nets, side, probe_diameter, grid)` —
   take rank 1–2 per net; prefer a spot near the driver/receiver pad so the
   stub stays short.
5. Show the table before editing:

   | Net | Side | X, Y | Pad ⌀ | Stub needed | Risk |

6. `add_testpoints(..., dry_run=true)` → inspect preview → commit.
7. Route stubs where the net has no pour: `route_connection` from the new TP
   pad object id to the nearest same-net pad, width per net class.
8. Verify: `run_connectivity_check` with zero opens, `run_drc`,
   `review_testpoint_coverage`, then continue the house gate order
   (`scripts/pcb_quality_gate.py`) if this board uses one.

## Report

Added TPs (refdes, net, X/Y, side), stub routes added, skipped nets with
reasons, coverage percentage before/after, and DRC result.
