# DUT Controller Rev.A schematic memory

## 2026-08-26 — STAGED, Gate 4 PASS

- Authority: `SCHEMATIC_BUILD.md`; this note is retrieval-only and cannot promote a gate.
- Artifact: `dut-controller-reva.dchxml`, SHA256 `5881e11dd0c3d1f4a86111517c881e50dbff83a9a419be82f2705a51ac76fbc9`.
- Deterministic model: 178 parts, 144 named nets, 701 pins checked, 26 explicit no-connect pins.
- Headless `schematic_review`: 0 errors, 0 warnings; completeness 0.8 because `schematic.electrical_conflict` is skipped (`electrical_pin_types_unavailable`).
- Visual baseline: eight A4 sheets, 25 overview shapes, zero symbol-body overlaps, zero wires.
- Gate 5 is PENDING: add local orthogonal wires, native GND/power symbols and named inter-sheet ports. Do not call the schematic complete while `wires == 0`.
- Gate 6 is PENDING: native DipTrace open/save/ERC and semantic round-trip happen only after Gate 5.

### Reusable MCP lessons

1. Never feed the previous visual artifact back into a clean build. Regenerate authoritative connectivity from the frozen design spec, then decorate it.
2. Validate a searched MPN against the returned EasyEDA title before writing evidence. `TSW-108-07-G-D` silently resolved to the wrong 8-pin `TSW-108-07-G-S-LL`; the shared sourcing helper now rejects this.
3. Check library pin geometry before placement. The LCSC converter divided EasyEDA pin coordinates by 0.254 twice, placing terminals hundreds of millimetres from their bodies. The shared converter now scales once and has an ESP32 regression check.
4. Run BOM identity and symbol-body overlap checks before visual wiring. This build moved from 100 incomplete BOM identities and 71 body overlaps to zero before routing any line.
5. The current semantic compiler takes roughly two minutes and emits no progress while applying 144 nets. Treat this as pipeline debt, not a reason to fork another generator.

### Resume

```bash
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva.py
PYTHONPATH=src .venv/bin/python scripts/schematic_quality_gate.py
```

Expected gate output at this checkpoint: `ok=true`, `last_passing_gate=4`, `parts=178`, `nets=144`, `wires=0`, `symbol_body_overlaps=0`.

### PCB isolation evidence

The schematic-only run did not change the captured PCB artifacts: PCB source `b8c6b447...`, native PCB `2a9eaa0f...`, Top SVG `2f1c5acc...`, Bottom SVG `45e40e50...`. Full hashes remain in `SCHEMATIC_BUILD.md`.
