# PCB build handoff — DUT Controller Rev.A

Status: `SCHEMATIC_PASS_ERC0`
Updated: 2026-08-25
Input schematic SHA-256: `f889dd1e1dd35fd9e641438b7e7bb7616adf0071e08b57547cb3dcbe6585a222`
Starting board SHA-256: `-`
Current board SHA-256: `-`
Build command:
`PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva.py`

## Ordered gates

| Gate | Status | Evidence / next action |
|---|---|---|
| 0. Resume and preserve worktree | PASS | Artifacts at repo root per operator decision |
| 1. ERC / connectivity / netlist / BOM | PASS | erc_basic + schematic_review: 0 findings; full pin coverage asserted in builder |
| 2. Official datasheet evidence | PASS | rules/ pending consolidation; see docs/DUT_CONTROLLER_REVA_DESIGN.md sources (ESP32-S3-MINI-1U v1.7, Espressif kicad-libraries footprint, HDG USB 90Ω section, per-IC PDFs in vendor/) |
| 3. Footprints and pin maps | PASS | pin→pad mapping asserted for all 178 parts; merged USB-C pads remapped; ESP32 EPAD grid uniquified |
| 4. Mechanics and connector datums | PENDING | board outline from connector courtyards |
| 5. Datasheet-driven critical placement | PENDING | module antenna keepout, AMS1117 caps flank, INA shunt Kelvin |
| 6. Stackup | PENDING | 2-layer house default |
| 7. Routing | PENDING | USB DP/DN 90Ω diff priority |
| 8. Ground pours and stitching | PENDING | |
| 9. Silkscreen | PENDING | |
| 10. Headless QC | PENDING | review_pcb_quality hard_error_count==0 |
| 11. Native DipTrace refill/DRC | PENDING | manual |
| 12. Media and final frame | PENDING | manual |

## Intentional deviations / open issues

See docs/DUT_CONTROLLER_REVA_DESIGN.md §7 (W.FL land verification before fab,
single simultaneous DUT data link interlock, no reverse-blocking on PWR,
8-bit ADC trade-off, ILIM/fuse coordination).

## Checkpoints

- `5e7705f` schematic build checkpoint
