# Physical Validation Plan for the I²C Level-Shifter PCB

Status: `CLOSED FOR DEMO — PASS-M1; M6-LITE + JLC PREVIEW ACCEPTED; FAB/HW NOT RUN BY SCOPE`

Goal: obtain honest physical confirmation for **one exact revision** of the
3.3 V ↔ 5 V demonstration board, not to declare the entire PCB generator
universally validated.

The baseline PASS consists of four independent results:

1. real DipTrace accepted the board after native refill/DRC/save/reopen/re-export;
2. the fabricator accepted the package and the delivered board matches CAM and
   the drawing;
3. the assembled specimen passes unpowered checks and static level shifting;
4. real I²C passes in both directions at 100 kHz without errors.

A separate `PASS-FM` permits a Fast-mode 400 kHz claim only after edge
measurements. SI/PI/EMC, volume manufacturability, and universal compatibility
are not claimed by this plan.

Scope decision of 2026-08-20: the operator accepted the native checks, the
visual materials, the primary JLC PCB preview, and the JLC BOM match as
sufficient for the demonstration result. Board ordering and testing of a real
specimen are explicitly out of scope. Phases C–G are therefore not executed,
and `PASS-FAB`, `PASS-HW`, `PASS-FM`, and the overall physical PASS are not
claimed.

## 1. Candidate identity

Starting point recorded while composing the plan:

| Field | Value |
| --- | --- |
| Git commit | `2506ca1` |
| PCB source | `i2c-level-shifter-pcb.dipxml` |
| PCB SHA-256 before the BOM fix | `0478717d8fe7fa21746c836a6eaed9d9d0f5f17f87b5ab2fbd1288971cde480c` |
| Schematic source | `i2c-level-shifter-module.dchxml` |
| Schematic SHA-256 before the BOM fix | `88b030b7712c0238897b021f3d572a2a93b20303aca8aca83321d335b56ce51a` |
| Board size per XML | 25 × 12 mm |
| Layers | 2, signals and power on Top, GND pours Top/Bottom |
| Contents | Q1/Q2 BSS138; R1–R4 pull-up; J1/J2 1×4, 2.54 mm |
| Hardware candidate | `PV-0 / 4.7 kΩ; freeze m1-71edf73` |
| Candidate PCB SHA-256 | `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118` |
| Candidate schematic SHA-256 | `bb34fca9fb7e6ee9108b77d84be5bd101df9ec32c987e91d8c23a00b5295dd7e` |
| Package freeze label | `m1-71edf73` (pre-DCO freeze SHA `71edf73`) |
| Signed PCB freeze commit | `3c3b6b0` — tree-equivalent rewrite of `71edf73` |
| Signed package commit | `681e9e2` — tree-equivalent rewrite of `3730259` |
| DipTrace build/profile | `5.3.0.3 / diptrace-5.3-en-v1` |
| Fabricator, order, stackup | `JLCPCB preview only; no order placed; stackup not fixed` |
| Specimen serial numbers | `TBD` |

### PV-0 — blocker before ordering

- [x] Select the actual pull-up resistance and resolve the discrepancy across
  all sources/BOM.

Closed 2026-08-20: R1–R4 fixed as **4.7 kΩ ±1 %**, MPN `0402WGF4701TCE`,
LCSC `C25900`; the XML parses and the old `0402WGF1002TCE` and `C25744` are
absent from the physical schematic/PCB artifacts. M1 and the freeze are
complete; manual fabricator CAM/DFM acceptance remains before ordering.

## 2. Criteria sources

- Connector topology and pinout: the current `dchxml`/`dipxml` and the
  generator `scripts/build_i2c_level_shifter_pcb.py`.
- BSS138: [onsemi BSS138/D, Rev. 7, April 2024](https://www.onsemi.com/pdf/datasheet/bss138-d.pdf).
  Pin 1 = Gate, pin 2 = Source, pin 3 = Drain; on the current PCB these are
  3V3, the low-voltage line, and the high-voltage line respectively.
- Bidirectional shifting circuit: [Nexperia AN10441 Rev. 2](https://assets.nexperia.com/documents/application-note/AN10441.pdf).
  Gate to the lower VDD, Source to the low-voltage section, Drain to the
  high-voltage section; normal condition `VDD2 >= VDD1`.
- I²C electrical levels and timings: [NXP UM10204 Rev. 7](https://www.nxp.com/docs/en/user-guide/UM10204.pdf),
  tables 10–11 and section 7.1.
- Pull-up part details: [the selected C25900, 4.7 kΩ](https://www.lcsc.com/product-detail/Chip-Resistor-Surface-Mount-UniOhm_4-7KR-4701-1_C25900.html)
  and [its datasheet](https://www.lcsc.com/datasheet/C25900.pdf).

Below, no unknown value is replaced by a guess: fabricator tolerances, real bus
capacitance, bench leakage current, and connected controller limits are
recorded after selecting the exact parts.

## 3. Connector and channel map

| Pin | J1 — LV | J2 — HV |
| --- | --- | --- |
| 1 | GND | GND |
| 2 | 3V3 | 5V |
| 3 | SCL_3V3, Q2 Source | SCL_5V, Q2 Drain |
| 4 | SDA_3V3, Q1 Source | SDA_5V, Q1 Drain |

R1/R2 pull SDA/SCL LV to 3V3. R3/R4 pull SDA/SCL HV to 5V.
Q1/Q2 Gates connect to 3V3.

## 4. Equipment and bench

| Need | Requirement | Actual |
| --- | --- | --- |
| Inspection | loupe/microscope; camera | `___` |
| Geometry | calipers; 1:1 printout before ordering | `___` |
| Electrical | multimeter with continuity/diode/µA | `___` |
| Power | two channels 3.3 V and 5 V with independent current limits, common GND | `___` |
| Signals | oscilloscope ≥2 channels; 4 preferred, ×10 probes with known capacitance | `___` |
| Protocol | logic analyzer with 5 V tolerant inputs | `___` |
| I²C | 3.3 V controller and 5 V target; swappable roles for the reverse test | `___` |
| Temperature | IR/thermocouple optional; at these power levels any noticeable heating is suspicious | `___` |

Bench rules:

- GPIO open-drain only (`drive LOW / release`), never push-pull HIGH;
- disable all on-board pull-ups of dev boards/analyzers, or record their value
  and recompute the equivalent resistance;
- before connecting the logic analyzer, confirm its 5 V tolerance;
- record the model and input capacitance of scope probes: it is part of the
  measured rise time;
- short wires first, then exactly the cable/load for which the claim is needed.

## 5. Phase A — freeze and native DipTrace acceptance (M1)

- [x] PV-0 closed in the primary schematic, the physical schematic, and the
  PCB; the generator ran successfully. The current reproducible candidate
  contains 17 distributed GND stitching vias.
- [x] PCB, MP4, and GIF regenerated 2026-08-20; first/middle/last frames and
  the 26-stage contact sheet checked.
- [x] Freeze commit `71edf73` and the source PCB candidate SHA-256 recorded.
- [x] `pcb_native_acceptance` ran from this exact source commit/editable
  install, not from the published `v0.4.0` where the post-release module was
  still missing; environment: `.venv-win-tests/Scripts/python.exe`, current
  `src` via `PYTHONPATH`, DipTrace `Pcb.exe` 5.3.0.3.
- [x] Real BSS138, 0402, and 1×4 headers applied to a 1:1 printout; pitch,
  pad geometry, and pin 1 orientation confirmed. The print sheet was prepared:
  `.local/physical-validation/phase-a/review/09-physical-fit-1to1-A4.pdf`;
  print only at 100% / Actual Size and first verify the 100.00 mm control
  marks. Operator observation 2026-08-20: `PASS — everything matches
  physically and in the photos`; no numeric measurements reported.
- [x] The native workflow from `docs/EVIDENCE_CAPTURE.md` ran on the exact
  DipTrace build. Example command from Windows PowerShell:

```powershell
py -m diptrace_mcp.pcb_native_acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\i2c-level-shifter-pcb.dipxml" `
  --output-xml "C:\work\evidence\i2c-level-shifter.native.dipxml" `
  --evidence-json "C:\work\evidence\i2c-level-shifter.native-evidence.json" `
  --desktop native `
  --refill-menu "#3->#14" `
  --drc-menu "#7->#0" `
  --save-as-menu "#0->#4"
```

- [x] Native copper refill completed without error.
- [x] Native DRC: `0` blocking errors; dialog `No errors found`:
  `.local/physical-validation/phase-a/inset-visible-verdict.png`.
- [x] After refill the GND ratline is hidden by DipTrace; J1.1, J2.1, and both
  pours kept one NetId. No unexplained ratlines.
- [x] Bottom GND is continuous; Top GND is useful; no islands or narrow
  accidental necks. Observation: the native `Bottom (2)` view shows a solid
  fill without signal traces; the Top view shows a working fill around traces.
- [x] Stitching is distributed over the whole board including upper/lower free
  areas; a via counter alone is not accepted. Observation: 17 vias are visible
  in the upper, central, and lower free areas of the full Top/Bottom view.
- [x] On J1.1/J2.1 four thermal spokes are visible after the real refill;
  separate large plans are preserved in the visual evidence package.
- [x] All positive-power and signal traces are on Top; Bottom is not cut by
  unnecessary traces.
- [x] The outline is compact and equals the expected 25 × 12 mm; components
  are centered and symmetric without violating clearance.
- [x] Silkscreen is readable, stays at its component, does not touch
  pads/holes/vias, and does not enter a foreign courtyard.
- [x] Save → Close → Reopen → re-export completed; structural delta empty.
  `HUMAN_REVIEW_REQUIRED` is limited to recomputed `CopperPourFills` with
  ±0.000001″ coordinate rounding; this bounded delta is accepted.
- [x] Source/candidate/native/export hashes, Top/Bottom screenshots,
  thermal/stitching close-ups, and a single contact sheet are stored:
  `.local/physical-validation/phase-a/review/`.
- [x] The operator eyeballed the package and issued the verdict 2026-08-20:
  `PASS — everything matches physically and in the photos`; no remarks filed.

### M1 journal — 2026-08-20

- Candidate: 8 physical components + 17 via-components, 7 nets, 14 traces,
  2 pours; source SHA-256
  `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118`.
- Real owner-drawn menu map: refill `#3 -> #14`, DRC `#7 -> #0`,
  Save As `#0 -> #4`. Separators are excluded from pywinauto indices.
- The original pours touched the outline and after the real refill produced
  two `Copper pour - Board outline` errors. Root fix: both pour outlines moved
  inward by the 0.2 mm board clearance, `SnapToBoard=N`.
- After the fix, native refill and DRC completed with `No errors found`.
  Screenshot SHA-256:
  `5d2e2ac49b6d034adc15de3a2b2d71b4346d727848f7aab322da3673c5d7a936`.
- The full open → refill → DRC → save → close → reopen → re-export cycle
  completed without forced termination. The repeated native round-trip has an
  empty structural delta and `drc_status=pass`. Evidence:
  `.local/physical-validation/phase-a/i2c-level-shifter.final10-native-evidence.json`,
  SHA-256 `72f865d0ee94734abebcaf81a534c0ca6d440a65eade449e4a22648fe417312d`.
- Native XML SHA-256:
  `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf`.
  The only semantic delta of the second round-trip is recomputed derivative
  `CopperPourFills` with ±0.000001″ coordinate rounding; connectivity, counts,
  topology, and attributes unchanged. Bounded review accepted.
- MP4/GIF rebuilt from 26 stages: outline first, then 8 components, 14 traces,
  and final pours + 17 vias. MP4 SHA-256
  `30c4765e7e0e47948b35ba8de6686df95ada3397eae8752dd4cb622c0b9bfcc4`,
  GIF `05716de6e42220069287aa6d3c8ebd3ea019ac482ff7497991b432f3394d83ba`.
- A package for human verification was assembled:
  `.local/physical-validation/phase-a/review/README.md`; master sheet
  `00-review-sheet.png`, SHA-256
  `6b4850004e8de5b1aded782cf4b9f23747706508c7e3565a4cfb279e193dc65a`.
  The full registry is in `review/SHA256SUMS`.
- The operator confirmed `PASS` of the physical fit and photo review on
  2026-08-20; no remarks. Numeric dimensions were not reported separately.
- Verdict: M1 checks — `PASS`. The formal M1 freeze completed with commit
  `71edf73`; the source PCB candidate is preserved with SHA-256
  `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118`.

**Stop:** any DRC error, unexplained ratline/island, wrong pin mapping, lost
thermal, or semantic/connectivity delta returns the board to rework; do not
proceed to production.

## 6. Phase B — manufacturing package (M6-lite)

- [ ] Fixed: PCB revision, BOM, footprint list, 2-layer stackup, copper
  weight, finish, solder mask, board thickness, and the selected fabricator's
  rules. Fabricator values: `___`.
- [x] Gerber/NC Drill and BOM/CPL exported by the stock DipTrace/verified
  exporter from the **native-saved** file. The repository is not considered an
  authoritative standalone Gerber generator.
- [x] Gerber ZIP SHA-256:
  `8484362236f943a0e9df33283e0a4fa7754b5f8f27441673f79285052f934b26`;
  full production ZIP:
  `7c5712ddbb6d4a5d26082fbac6a57806d6d8f5da0dd94ceb2ec27920735d1289`.
- [ ] In an independent CAM viewer: outline, both copper layers, mask, silk,
  and drill inspected; no mirrored/missing/duplicate layers.
- [ ] 0.3 mm finished via holes, annular rings, header holes, mask dams, 0402
  paste openings, copper-to-edge, and silkscreen-to-pad checked against the
  fabricator's rule deck. Accepted real tolerances: `___`.
- [ ] Top/Bottom GND, the 17 distributed stitching vias, and four spokes on
  both GND header pads confirmed in CAM.
- [ ] The fabricator closed DFM without blocking warnings; waiver ledger: `___`.
- [ ] CAM screenshots, DRC, DFM report, order ID, and the exact package hash
  stored.

### M6-lite journal — 2026-08-20

- Package: `fab/m1-71edf73/`; exact source — the native-saved PCB SHA-256
  `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf`.
- DipTrace 5.3.0.3 natively exported 8 metric Gerber layers and a metric
  Excellon PTH. X2 `FileFunction`, EOF, the 25 × 12 mm profile, 0.30 mm ×17
  and 1.08 mm ×8 tools verified; no NPTH in the design.
- The JLC SMT BOM contains two grouped rows with populated `C52895` and
  `C25900`; the CPL contains the matching 6 placements `Q1/Q2/R1–R4` in
  millimeters. Lead-frame J1/J2 without LCSC parts are deliberately excluded
  from machine assembly and left for manual mounting; the full native BOM/CPL
  are preserved as evidence.
- ZIP and both SHA-256 manifest checks — PASS. Main visual sheet:
  `fab/m1-71edf73/evidence/review/00-review-sheet.png`.
- Machine part M6-lite verdict: `PASS — READY FOR FABRICATOR PREVIEW`.
  Independent CAM, the JLC placement preview, real order parameters, live
  stock for the chosen quantity, DFM warnings/waivers, and the order ID remain
  manual gates.

### Demo preview closure — 2026-08-20

- JLCPCB recognized the 2-layer 12 × 25 mm board; the shown Top/Bottom views
  the operator accepted without remarks.
- JLC BOM identified and confirmed both grouped SMT rows: `Q1/Q2` — BSS138,
  `C52895`; `R1–R4` — 4.7 kΩ, `C25900`. Packages match the uploaded BOM;
  lead-frame `J1/J2` are expectedly absent from SMT assembly.
- Screenshots and their hashes are stored in `fab/m1-71edf73/evidence/jlc/`.
- The operator closed this preview here: ordering, assembly placement/DFM,
  receiving boards, and electrical tests are not executed. This closes the
  demonstration package check but does not become a production or hardware
  claim.

A minimal physical proof allows hand-assembly of one specimen. A
volume-PCBA-ready claim requires separately accepted BOM/CPL and assembly DFM.

## 7. Phase C — incoming and visual inspection (unpowered)

Assign an ID per specimen: `A___ / B___ / C___`.

- [ ] Photos Top/Bottom before soldering and after soldering.
- [ ] Board dimensions: X `___` mm, Y `___` mm; match the drawing and the
  fabricator tolerance `___`.
- [ ] Headers insert without force/hole widening; actual pitch `___`.
- [ ] No shorts/under-etch/opens, damaged mask, lifted pads, shifted holes,
  or sharp edges.
- [ ] Q1/Q2: correct pin 1 orientation, no SOT-23 bridges or cold joints.
- [ ] R1–R4: all four mounted, no tombstone/bridge; actual MPN and value from
  the assembly record `___`.
- [ ] J1/J2: pin 1 and the LV/HV side are unambiguously distinguishable.
- [ ] With hand soldering using one consistent process, the GND pads J1.1/J2.1
  wet without noticeably more time/temperature than neighboring pads.
  Observation: `___`.

## 8. Phase D — unpowered checks

External boards and sources disconnected.

| Check | Expectation from netlist/datasheet | Measured | PASS |
| --- | --- | --- | --- |
| J1.1 ↔ J2.1 | continuity, GND | `___` | `[ ]` |
| J1.2 ↔ GND | OL/no continuity | `___` | `[ ]` |
| J2.2 ↔ GND | OL/no continuity | `___` | `[ ]` |
| J1.2 ↔ J2.2 | no direct rail connection | `___` | `[ ]` |
| J1.3 ↔ Q2 Source/R2 signal pad | continuity | `___` | `[ ]` |
| J2.3 ↔ Q2 Drain/R4 signal pad | continuity | `___` | `[ ]` |
| J1.4 ↔ Q1 Source/R1 signal pad | continuity | `___` | `[ ]` |
| J2.4 ↔ Q1 Drain/R3 signal pad | continuity | `___` | `[ ]` |
| Q1/Q2 Gate ↔ J1.2 | continuity | `___` | `[ ]` |
| Q1 Source → Drain, diode mode | diode in one direction only; reverse OL | `___` | `[ ]` |
| Q2 Source → Drain, diode mode | diode in one direction only; reverse OL | `___` | `[ ]` |
| R1–R4 | selected value ±1 % plus DMM accuracy | `___` | `[ ]` |

If an in-circuit resistor measurement is distorted by a parallel path, the
value is confirmed on a spare part/assembly reel; the result is not "fitted".

**Stop:** rail-to-GND continuity, swapped body-diode orientation, a wrong
connector circuit, or an unexplained value.

## 9. Phase E — first power-up with current limits

First the board without external I²C devices. The common GND of the sources
connects to J1.1/J2.1. Before this phase the operator separately confirms
readiness.

For the 4.7 kΩ ±1 % variant:

- `Rmin = 4653 Ω`;
- maximum when holding both lines LOW on LV:
  `2 × 3.3 / Rmin = 1.419 mA`;
- maximum when holding both lines LOW on HV:
  `2 × 5 / Rmin = 2.150 mA`.

Working starting limits are therefore: **2.0 mA for 3V3 and 3.0 mA for 5V**.
They are recomputed if PV-0 selects a different value. If the bench supply
cannot hold such a small limit, temporary series resistors of 680 Ω in 3V3
and 1 kΩ in 5V are acceptable for the first idle smoke test: in a direct short
they limit current to roughly 4.9/5 mA; remove them after a successful check
before dynamic tests.

- [ ] 3V3 only, 5V physically disconnected: the limit does not trip,
  voltage/current recorded `___`.
- [ ] 5V only, 3V3 physically disconnected: the limit does not trip,
  voltage/current recorded `___`.
- [ ] Both rails on, `VDD2 >= VDD1`; actual VDD: `___ / ___`.
- [ ] Idle signals: J1.3/J1.4 at the measured 3V3, J2.3/J2.4 at the measured
  5V. Values: `___`.
- [ ] Idle supply current does not trip the limit and matches only board
  leakage plus known bench leakage; actual `___ / ___`.
- [ ] After 60 s no noticeable heating; temperature/observation `___`.

**Stop:** a tripping limit, rail sag, a signal HIGH at the wrong level, smell,
or heating. Remove power and return to localizing the rail/component.

## 10. Phase F — static bidirectional shifting

LOW is created by an open-drain key. For each row, first measure idle HIGH,
then LOW on both sides and each source's current.

| Channel and drive | Expectation | LV/HV LOW | I3V3/I5V | PASS |
| --- | --- | --- | --- | --- |
| J1.4 SDA_LV → LOW | J2.4 also LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J2.4 SDA_HV → LOW | J1.4 also LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J1.3 SCL_LV → LOW | J2.3 also LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J2.3 SCL_HV → LOW | J1.3 also LOW | `___ / ___` | `___ / ___` | `[ ]` |

Criteria:

- each side's HIGH is at least `0.7 ×` its **measured** VDD and is effectively
  pulled to its rail;
- LOW on both sides ≤ 0.4 V;
- with one line LOW the expected pull-up current is about `VDD/R`; with two —
  `2×VDD/R`, accounting for the R tolerance and instrument accuracy;
- after release both sides return HIGH without latching;
- SDA and SCL pass all four directions identically.

## 11. Phase G — real I²C and the oscilloscope

### G1. Preparation

- [ ] Recorded: controller/target, firmware hashes, target address, cable,
  effective pull-ups, and probe models: `___`.
- [ ] LV/HV of one line observed simultaneously; measurement thresholds set to
  30–70 % of the corresponding measured VDD.
- [ ] The logic analyzer decodes START, address, ACK, data, repeated START,
  and STOP.

### G2. Baseline claim — Standard-mode 100 kHz

- [ ] Controller on the 3.3 V side, target on the 5 V side: at least 10,000
  write/read transactions with `00 FF 55 AA`/counter patterns; 0 NACK,
  timeout, and data mismatch. Result: `___`.
- [ ] Roles/sides swapped: controller at 5 V, target at 3.3 V; the same test,
  0 errors. Result: `___`.
- [ ] If the target supports clock stretching, one test explicitly confirms
  LOW SCL transfer from the target side; otherwise this subclaim is marked
  `NOT TESTED`, not PASS.
- [ ] On SDA and SCL of both sides: `tr(30–70 %) <= 1000 ns`,
  `tf <= 300 ns`, `VOL <= 0.4 V`, HIGH >= `0.7×VDD`; no repeated threshold
  crossing due to ringing. The measurement table is filled below.

### G3. Extended claim — Fast-mode 400 kHz

Executed only if the project wants to claim 400 kHz support.

- [ ] Both directions pass the same 10,000 transactions without errors.
- [ ] On all four observed lines `tr(30–70 %) <= 300 ns` and `tf <= 300 ns`;
  the remaining levels stay within G2.
- [ ] Verified on the target cable/load, not only on a short lab wire.

| Mode | Line | Side | tr | tf | VOL | VOH | PASS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 kHz | SDA | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 kHz | SDA | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 kHz | SCL | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 kHz | SCL | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 kHz | SDA | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 kHz | SDA | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 kHz | SCL | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 kHz | SCL | HV | `___` | `___` | `___` | `___` | `[ ]` |

To estimate the cause of a slow edge, the UM10204 formula
`tr = 0.8473 × Rp × Cb` is permitted; it estimates the total capacitance of
the specific bench, not a new datasheet claim. For 4.7 kΩ the theoretical Cb
limit is about 251 pF at 100 kHz and 75 pF at 400 kHz; for 10 kΩ about 118 pF
and 35 pF respectively.

## 12. Phase H — power states and repeatability

- [ ] With 3V3 off and 5V active, no unexplained back-power; measured
  rail/signal/current `___`.
- [ ] With 5V off and 3V3 active, no unexplained back-power; measured
  rail/signal/current `___`.
- [ ] The power-off state is checked against the specific controller/target
  limits; absence of damage is not considered proof of permissible back-power.
- [ ] The full G1–G3 ran on one representative specimen.
- [ ] On every other assembled specimen, at minimum phases C–F and a 100 kHz
  smoke test ran; results `___`.
- [ ] Any repair/rework is recorded with photos and cause; a repaired unit is
  not hidden inside the overall PASS.

## 13. Evidence pack and final verdict

Store outside the sources or in an explicitly chosen capture root; the
repository needs only references, hashes, and a compact report.

- [ ] manifest: commit, all SHAs, DipTrace/OS/profile, rule deck, fab order,
  board/assembly revisions, and specimen IDs;
- [ ] native evidence JSON, native DRC, source/native/export XML;
- [ ] manufacturing ZIP, CAM/DFM reports, and layer screenshots;
- [ ] photos Top/Bottom/microscope/dimensions;
- [ ] continuity, rails, currents, static levels tables;
- [ ] raw scope captures and screenshots for SDA/SCL LV/HV;
- [ ] I²C logs with transaction and error counts;
- [ ] failure/rework/waiver ledger;
- [ ] dated operator verdict and the responsible person's name.

| Verdict | Condition | Result |
| --- | --- | --- |
| `PASS-M1` | native refill/DRC/round-trip and visual review | `PASS` |
| `PASS-DEMO` | M1 + machine package + JLC PCB/BOM preview | `PASS — operator accepted 2026-08-20` |
| `PASS-FAB` | exact package accepted, delivered geometry matched | `NOT RUN — ordering out of scope` |
| `PASS-HW` | C–F and 100 kHz G2 passed | `NOT RUN — hardware out of scope` |
| `PASS-FM` | additionally G3 passed on the target load | `NOT RUN` |

The overall baseline PASS is possible only with
`PASS-M1 + PASS-FAB + PASS-HW` and no unexplained waiver. It is not claimed;
the outcome of the current limited scope is `PASS-DEMO`. `PASS-FM` is not
required for the baseline result.

## 14. Short execution route

1. ~~Close PV-0: 4.7 kΩ / `0402WGF4701TCE` / `C25900`.~~ Done.
2. ~~Run the M1 operator checks and freeze the commit at recorded SHAs.~~ Done.
3. ~~Check the machine package and the JLC PCB/BOM preview.~~ Done for the
   demonstration scope.
4. Ordering, phases C–G, and the baseline physical PASS are not executed per
   the operator decision of 2026-08-20.
