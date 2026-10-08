# DUT Controller Rev.A schematic build

State: `SHEET_1_PASS`

Artifact: `dut-controller-reva.dchxml`

Artifact SHA-256: `26f5a68666a93102b517d913ea04420049eedc697cee709ca4d02ea8d62c65eb`

Last passing gate: 6 (`SYSTEM_OVERVIEW` memory writeback and retrieval)

| Gate | Status | Evidence |
|---:|:---:|---|
| 0 | PASS | Live RAG retrieval returned the sheet-1 contract and reset journal; `docs/DUT_CONTROLLER_REVA_DESIGN.md` supplied the source-bound control relationships used by the revised view. Exact queries are recorded in the reset journal. |
| 1 | PASS | `docs/DUT_CONTROLLER_REVA_SHEET1_SPEC.md` freezes the user-directed logic-only `SYSTEM_OVERVIEW`: bounded HOST/DUT endpoints, one aligned service row, no global power rails. |
| 2 | PASS | N/A for this documentary sheet; the gate asserts zero placed parts, library components, nets and wires. |
| 3 | PASS | MCP bounded SHA-guarded edits created one A4 `SYSTEM_OVERVIEW` with 40 documentary shapes, seven functional rectangles, two endpoint rectangles, and one two-point native segment per line. |
| 4 | PASS | The checker reports 1 sheet, 7 blocks, 40 shapes, 0 parts/nets/wires and now rejects dangling endpoints, line crossings, overlapping segments, zero-length segments, and misaligned service tiles. The inspected render has a straight main axis, five equal-level service blocks, no empty-space endpoints, and only the obstacle-required UPLINK bends. |
| 5 | PASS | Hidden Windows DipTrace open/save/close returned `ok=true`, `forced_termination=false`, unchanged SHA `26f5a686…`; input desktop remained `Default`. |
| 6 | PASS | No `knowledge_search` was made for this visual-only correction. The direct project state and explicit user markup were sufficient; `AGENTS.md`, the local journal, sheet contract, and schematic skill record the resulting policy and reusable gates. |

No later sheet may be created while an earlier sheet has a non-PASS gate.

## Reset evidence

On 2026-08-27 the rejected DUT schematic artifacts were deleted: `dut-controller-reva.dchxml`, `dut-controller-reva-native.dchxml`, `dut-controller-reva-native-wired.dchxml`, `dut-controller-reva-normalized.dchxml`, `dut-controller-reva-fresh.dchxml`, and its provenance sidecar. The rejected generator and its quality-gate script were also removed so they cannot become accidental inputs.

Do not reuse component coordinates, visual wiring, generated symbol geometry or netlist XML from the rejected iteration. Design requirements and official source evidence may be retrieved independently through RAG and revalidated.

## PCB isolation

PCB is outside this build. Baseline hashes that must remain unchanged:

- `dut-controller-reva-pcb.dipxml`: `b8c6b4473b172a980fdbd2d5259b10cfa47fe9ccff306c13c7cf2e211957f5b4`
- `dut-controller-reva-native.dipxml`: `2a9eaa0fad1f668ec8b4a404d29ac45e6bdd62fc12b75c0d8c2c4e583c0a8a3b`
- `dut-controller-reva-pcb-top.svg`: `2f1c5accf166656ffdb6d08c770fb72a953fb93acb247a0ed9dbce4660ead5cf`
- `dut-controller-reva-pcb-bottom.svg`: `45e40e50a8c8b5d81ad39ed568c2da5d128f431a3c0439cf726f48eab60b07b3`

## Exact resume point

Begin the next one-sheet cycle by querying live RAG for `ESP32_CONTROL` requirements, official source evidence and component-resolution rules. Freeze a dedicated sheet specification before any placement; do not add any other later sheet.

Current sheet check:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_sheet1.py --check
```

Checkpoint commit: none; the worktree contains unrelated user changes.
