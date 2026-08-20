# I²C level shifter — production package M1

Revision: `m1-71edf73`  
Freeze commit: `71edf73`  
Native export application: DipTrace PCB Layout `5.3.0.3`  
Export date: `2026-08-20`

## Order files

- `i2c-level-shifter-m1-71edf73-gerbers.zip` — upload to the PCB fabricator.
- `i2c-level-shifter-m1-71edf73-bom.csv` — JLCPCB SMT assembly BOM.
- `i2c-level-shifter-m1-71edf73-cpl.csv` — JLCPCB SMT placement file.
- `i2c-level-shifter-m1-71edf73-production.zip` — complete archival package.
- `QUALITY-REPORT.md` — passed machine checks and remaining manual gates.

The SMT BOM/CPL contain `Q1`, `Q2`, and `R1`–`R4`. Through-hole connectors
`J1` and `J2` have no assigned LCSC part and are intentionally excluded from
machine assembly; fit and solder them manually. The full native BOM and CPL,
including the connectors, are retained under `evidence/native/`.

## Native export settings

- Gerber units: metric; one selected layer per native export.
- Layers: Top/Bottom copper, Top/Bottom solder mask, Top/Bottom legend,
  board profile, and Top paste.
- Drill: metric Excellon, automatic tool assignment, plated holes only.
- Drill tools: 0.30 mm (17 hits) and 1.08 mm (8 hits).
- No non-plated holes exist in this design, so no NPTH file is emitted.
- Native export offset: X = 10.0 mm, Y = 10.0 mm; the 25 × 12 mm profile is
  therefore located at X 10…35 mm and Y 10…22 mm in CAM coordinates.

## Validation state

Completed automatically:

- freeze commit recorded;
- native DipTrace refill/save/reopen round-trip accepted;
- native DRC passed with `No errors found`;
- Gerber/Excellon syntax, layer functions, non-empty files, profile size,
  drill tools/hit counts, BOM/CPL headers, LCSC completeness for SMT rows,
  and BOM↔CPL designator equality checked;
- payload hashes recorded.

Still requires a human before ordering:

- upload the Gerber ZIP and inspect every layer in the fabricator CAM viewer;
- confirm outline 25 × 12 mm, two copper layers, masks, legend, paste, and
  drill alignment; reject any mirrored or duplicate layer;
- inspect SMT orientation/rotation in the JLC placement preview, especially
  Q1/Q2 pin 1;
- choose and record stack-up, board thickness, copper weight, finish, mask,
  order quantity, assembly side, and any panelization;
- accept or resolve every fabricator DFM warning and re-check live LCSC stock
  for the chosen quantity.

Until those manual CAM/DFM checks are recorded, this package is
`READY FOR FABRICATOR PREVIEW`, not an unconditional production release.

## Evidence

`evidence/review/00-review-sheet.png` is the quickest visual entry point.
The review directory also includes native Top/Bottom views, GND thermal
close-ups, the native DRC result, the staged-media contact sheet, and a 1:1
fit sheet. `evidence/native/` preserves the exact native-saved PCB, acceptance
JSON, and unfiltered native BOM/CPL used to build the order files.
