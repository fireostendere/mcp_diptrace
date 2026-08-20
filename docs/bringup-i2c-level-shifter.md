# Physical validation plan for the I²C level-shifter PCB

Status: `CLOSED FOR DEMO — PASS-M1; M6-LITE + JLC PREVIEW ACCEPTED; FAB/HW NOT RUN BY SCOPE`

The purpose of this document is to record defensible physical evidence for one exact revision of the 3.3 V ↔ 5 V demonstration board. It does not claim that every board produced by the PCB generator is universally validated.

A full physical PASS would require four independent results:

1. real DipTrace accepts the board after native refill/DRC/save/reopen/re-export;
2. the fabricator accepts the package and the manufactured board matches CAM and the drawing;
3. an assembled specimen passes unpowered checks and static bidirectional level translation;
4. real I²C traffic passes in both directions at 100 kHz without errors.

`PASS-FM` additionally requires measured Fast-mode 400 kHz edges. SI/PI/EMC, production manufacturability, and universal compatibility are outside this claim.

Scope decision, 2026-08-20: the operator accepted the native checks, visual material, initial JLCPCB preview, and JLC BOM match as sufficient for the demonstration result. Board ordering and tests on physical specimens were explicitly excluded. Therefore phases C–H below were not run, and `PASS-FAB`, `PASS-HW`, `PASS-FM`, and a full physical PASS are not claimed.

## 1. Candidate identity

| Field | Value |
| --- | --- |
| Git base commit | `2506ca1` |
| PCB source | `i2c-level-shifter-pcb.dipxml` |
| PCB SHA-256 before BOM correction | `0478717d8fe7fa21746c836a6eaed9d9d0f5f17f87b5ab2fbd1288971cde480c` |
| Schematic source | `i2c-level-shifter-module.dchxml` |
| Schematic SHA-256 before BOM correction | `88b030b7712c0238897b021f3d572a2a93b20303aca8aca83321d335b56ce51a` |
| Board size from XML | 25 × 12 mm |
| Layers | 2; signals and power on Top; GND pours on Top/Bottom |
| Components | Q1/Q2 BSS138; R1–R4 pull-ups; J1/J2 1×4, 2.54 mm |
| Hardware candidate | `PV-0 / 4.7 kΩ; freeze m1-71edf73` |
| Candidate PCB SHA-256 | `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118` |
| Candidate schematic SHA-256 | `bb34fca9fb7e6ee9108b77d84be5bd101df9ec32c987e91d8c23a00b5295dd7e` |
| Package freeze label | `m1-71edf73` (pre-DCO freeze SHA `71edf73`) |
| Signed PCB freeze commit | `3c3b6b0` — tree-equivalent rewrite of `71edf73` |
| Signed package commit | `681e9e2` — tree-equivalent rewrite of `3730259` |
| DipTrace build/profile | `5.3.0.3 / diptrace-5.3-en-v1` |
| Fabricator/order/stackup | `JLCPCB preview only; no order placed; stackup not frozen` |
| Physical specimen IDs | `TBD` |

### PV-0 — blocker before ordering

- [x] Freeze the actual pull-up resistance and remove the BOM/source mismatch.

Closed 2026-08-20: R1–R4 are **4.7 kΩ ±1 %**, MPN `0402WGF4701TCE`, LCSC `C25900`. XML parses successfully; the previous `0402WGF1002TCE` and `C25744` are absent from the physical schematic/PCB artifacts. M1 and the package freeze are complete. A real fabricator CAM/DFM acceptance would still be required before ordering.

## 2. Acceptance references

- Connector topology and pinout: the current `dchxml`/`dipxml` sources and `scripts/build_i2c_level_shifter_pcb.py`.
- BSS138 pinout: [onsemi BSS138/D, Rev. 7, April 2024](https://www.onsemi.com/pdf/datasheet/bss138-d.pdf). Pin 1 = Gate, pin 2 = Source, pin 3 = Drain. On this PCB those map to 3V3, the low-voltage signal, and the high-voltage signal respectively.
- Bidirectional level-shifter topology: [Nexperia AN10441 Rev. 2](https://assets.nexperia.com/documents/application-note/AN10441.pdf). Gate goes to the lower VDD, Source to the low-voltage side, Drain to the high-voltage side; normal operation requires `VDD2 >= VDD1`.
- I²C electrical levels/timing: [NXP UM10204 Rev. 7](https://www.nxp.com/docs/en/user-guide/UM10204.pdf), tables 10–11 and section 7.1.
- Pull-ups: [LCSC C25900, 4.7 kΩ](https://www.lcsc.com/product-detail/Chip-Resistor-Surface-Mount-UniOhm_4-7KR-4701-1_C25900.html) and [datasheet](https://www.lcsc.com/datasheet/C25900.pdf).

Unknown fabricator tolerances, actual bus capacitance, fixture leakage, and attached-controller limits must be measured or taken from the selected parts. They must not be replaced with guessed values.

## 3. Connector/channel map

| Pin | J1 — LV | J2 — HV |
| --- | --- | --- |
| 1 | GND | GND |
| 2 | 3V3 | 5V |
| 3 | SCL_3V3, Q2 Source | SCL_5V, Q2 Drain |
| 4 | SDA_3V3, Q1 Source | SDA_5V, Q1 Drain |

R1/R2 pull SDA/SCL LV to 3V3. R3/R4 pull SDA/SCL HV to 5V. Q1/Q2 gates are connected to 3V3.

## 4. Phase A — freeze and native DipTrace acceptance (M1)

- [x] PV-0 is closed in the primary schematic, physical schematic, and PCB. The generator passes. The reproducible candidate contains 17 distributed GND stitching vias.
- [x] PCB, MP4, and GIF were regenerated on 2026-08-20. First/middle/last frames and the 26-stage contact sheet were reviewed.
- [x] Freeze commit `71edf73` and the source PCB SHA-256 were recorded.
- [x] `pcb_native_acceptance` was run from the same source commit/editable install, not from published `v0.4.0`, where this post-release module did not yet exist. Environment: `.venv-win-tests/Scripts/python.exe`, current `src` via `PYTHONPATH`, DipTrace `Pcb.exe` 5.3.0.3.
- [x] Real BSS138, 0402 parts, and 1×4 headers were placed on the 1:1 print. Pitch, pad geometry, and pin-1 orientation were accepted. Print file: `.local/physical-validation/phase-a/review/09-physical-fit-1to1-A4.pdf`; print only at 100% / Actual Size and verify the 100.00 mm reference first. Operator verdict on 2026-08-20: `PASS — physical fit and photos match`; no separate numerical measurements were supplied.
- [x] The native workflow from `docs/EVIDENCE_CAPTURE.md` was executed on the exact DipTrace build. Example Windows PowerShell command:

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
- [x] Native DRC reported `0` blocking errors and `No errors found`. Evidence screenshot: `.local/physical-validation/phase-a/inset-visible-verdict.png`.
- [x] After refill the GND ratline disappeared; J1.1, J2.1, and both pours retained one NetId. No unexplained ratline remains.
- [x] Bottom GND is continuous; Top GND remains useful; no unintended islands or narrow accidental bridges were observed. Native `Bottom (2)` shows a solid plane without signal traces; Top shows a working pour around traces.
- [x] All 17 stitching vias are distributed across the board, including upper/lower free areas; acceptance is not based on the via count alone.
- [x] Four thermal spokes are visible at both J1.1 and J2.1 after native refill; close-ups are included in the visual evidence package.
- [x] Positive-power and signal traces are on Top; Bottom is not cut by unnecessary traces.
- [x] Outline is the expected 25 × 12 mm; placement is compact and symmetric without clearance violations.
- [x] Silkscreen is readable, belongs to the correct component, and does not touch pads/holes/vias or enter another component's courtyard.
- [x] Save → Close → Reopen → re-export completed. Structural delta is empty. `HUMAN_REVIEW_REQUIRED` is limited to regenerated `CopperPourFills` with coordinate rounding of ±0.000001 in; this bounded delta was accepted.
- [x] Source/candidate/native/export hashes, Top/Bottom screenshots, thermal/stitching close-ups, and a unified contact sheet were preserved under `.local/physical-validation/phase-a/review/`.
- [x] Operator visual review on 2026-08-20: `PASS — physical fit and photos match`; no issues were reported.

### M1 journal — 2026-08-20

- Candidate: 8 physical components + 17 via-components, 7 nets, 14 traces, 2 pours. Source SHA-256: `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118`.
- Actual owner-drawn menu map: refill `#3 -> #14`, DRC `#7 -> #0`, Save As `#0 -> #4`. Separators are not counted by pywinauto.
- Original pours touched the outline and produced two `Copper pour - Board outline` errors after real refill. Root fix: both pour boundaries were inset by the 0.2 mm board clearance and `SnapToBoard=N`.
- After the fix, native refill and DRC completed with `No errors found`. Screenshot SHA-256: `5d2e2ac49b6d034adc15de3a2b2d71b4346d727848f7aab322da3673c5d7a936`.
- Full open → refill → DRC → save → close → reopen → re-export completed without forced termination. The repeated native round-trip has an empty structural delta and `drc_status=pass`. Evidence: `.local/physical-validation/phase-a/i2c-level-shifter.final10-native-evidence.json`, SHA-256 `72f865d0ee94734abebcaf81a534c0ca6d440a65eade449e4a22648fe417312d`.
- Native XML SHA-256: `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf`. The only semantic delta in the second round-trip is regenerated derived `CopperPourFills` with ±0.000001 in coordinate rounding; connectivity, counts, topology, and attributes are unchanged. The bounded review was accepted.
- MP4/GIF were rebuilt from 26 stages: outline, then 8 components, 14 traces, and final pours + 17 vias. MP4 SHA-256 `30c4765e7e0e47948b35ba8de6686df95ada3397eae8752dd4cb622c0b9bfcc4`; GIF SHA-256 `05716de6e42220069287aa6d3c8ebd3ea019ac482ff7497991b432f3394d83ba`.
- Human-verification package: `.local/physical-validation/phase-a/review/README.md`; combined sheet `00-review-sheet.png`, SHA-256 `6b4850004e8de5b1aded782cf4b9f23747706508c7e3565a4cfb279e193dc65a`. Full registry: `review/SHA256SUMS`.
- Operator accepted the physical fit and photo review on 2026-08-20. No separate numerical dimensions were supplied.
- Verdict: M1 checks are `PASS`. Formal M1 freeze ended at commit `71edf73`; source PCB candidate SHA-256 remains `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118`.

**Stop condition:** any DRC error, unexplained ratline/island, incorrect pin mapping, lost thermal, or semantic/connectivity delta returns the board to correction; do not proceed to fabrication.

## 5. Phase B — manufacturing package (M6-lite)

- [ ] Freeze the actual fabricator stackup, copper weight, finish, solder-mask, board thickness, and rule deck before a real order.
- [x] Gerber/NC Drill and BOM/CPL were exported from the **native-saved** board using DipTrace/the verified exporter. The repository is not treated as an independent authoritative Gerber generator.
- [x] Gerber ZIP SHA-256: `8484362236f943a0e9df33283e0a4fa7754b5f8f27441673f79285052f934b26`.
- [x] Full production ZIP SHA-256: `7c5712ddbb6d4a5d26082fbac6a57806d6d8f5da0dd94ceb2ec27920735d1289`.
- [ ] A real order would still require independent CAM inspection, actual fabricator tolerance checks, DFM warning/waiver review, and an order ID.

### M6-lite journal — 2026-08-20

- Package: `fab/m1-71edf73/`; exact source is native-saved PCB SHA-256 `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf`.
- DipTrace 5.3.0.3 natively exported 8 metric Gerber layers and metric Excellon PTH. X2 `FileFunction`, EOF, 25 × 12 mm profile, 0.30 mm ×17 tools, and 1.08 mm ×8 tools were checked; the design contains no NPTH.
- JLC SMT BOM contains two grouped rows with populated `C52895` and `C25900`; CPL contains the matching 6 positions `Q1/Q2/R1–R4` in millimetres. Through-hole J1/J2 have no LCSC part and are intentionally excluded from machine assembly for manual installation. Full native BOM/CPL are preserved as evidence.
- ZIP and both SHA-256 manifests passed verification. Main review sheet: `fab/m1-71edf73/evidence/review/00-review-sheet.png`.
- Machine-side M6-lite verdict: `PASS — READY FOR FABRICATOR PREVIEW`.

### Demonstration preview closure — 2026-08-20

- JLCPCB recognized a 2-layer 12 × 25 mm board; the displayed Top/Bottom previews were accepted by the operator without reported issues.
- JLC BOM recognized both grouped SMT rows: `Q1/Q2` — BSS138, `C52895`; `R1–R4` — 4.7 kΩ, `C25900`. Packages matched the uploaded BOM. Through-hole `J1/J2` were expectedly absent from SMT assembly.
- Screenshots and hashes are stored in `fab/m1-71edf73/evidence/jlc/`.
- The operator ended the work at preview: order placement, assembly placement/DFM, board receipt, and electrical testing were not performed. This closes the demonstration package review but does not become a manufacturing or hardware claim.

## 6. Deferred physical phases C–H

These phases remain the acceptance plan if a physical batch is ordered later. They are `NOT RUN` for the current demonstration scope.

### Phase C — incoming/visual inspection

Assign an ID to every specimen. Record Top/Bottom photos before and after soldering, board dimensions, header fit/pitch, pad/mask/hole quality, Q1/Q2 pin-1 orientation, R1–R4 population, J1/J2 side/pin-1 markings, and any rework.

### Phase D — unpowered checks

With all external boards and supplies disconnected, verify continuity for GND and every connector-to-transistor/pull-up path, absence of rail-to-GND and rail-to-rail shorts, BSS138 body-diode orientation, and R1–R4 value. An in-circuit resistor reading distorted by a parallel path must be confirmed from a spare part or assembly reel rather than adjusted to fit the expectation.

### Phase E — first current-limited power-up

For 4.7 kΩ ±1 %, `Rmin = 4653 Ω`. The maximum pull-up current with both lines LOW is approximately `1.419 mA` on the 3.3 V side and `2.150 mA` on the 5 V side. Initial working limits are therefore **2.0 mA for 3V3 and 3.0 mA for 5V**, adjusted only if the test fixture requires a documented alternative. Verify each rail separately, then both rails with `VDD2 >= VDD1`, idle signal HIGH levels, idle supply current, and absence of heating.

### Phase F — static bidirectional translation

Drive LOW only with open-drain behavior (`drive LOW / release`), never push-pull HIGH. Exercise SDA and SCL from both LV and HV sides. Acceptance requires HIGH at or above `0.7 ×` measured VDD on each side, LOW ≤ 0.4 V on both sides, plausible pull-up current, and clean return to HIGH after release.

### Phase G — real I²C and oscilloscope

For Standard-mode 100 kHz, run at least 10,000 write/read transactions in each direction with 0 NACK, timeout, or data mismatch. If the target supports clock stretching, explicitly verify SCL LOW propagation from the target side; otherwise record `NOT TESTED`. On SDA/SCL for both LV/HV sides require `tr(30–70 %) <= 1000 ns`, `tf <= 300 ns`, `VOL <= 0.4 V`, and HIGH ≥ `0.7 × VDD` without repeated threshold crossings from ringing.

A Fast-mode 400 kHz claim requires the same bidirectional transaction test plus `tr(30–70 %) <= 300 ns` and `tf <= 300 ns` on all observed lines under the target cable/load. UM10204 `tr = 0.8473 × Rp × Cb` may be used to estimate the capacitance of the specific fixture; it is not a new datasheet claim. With 4.7 kΩ, the theoretical Cb limit is about 251 pF at 100 kHz and 75 pF at 400 kHz.

### Phase H — power-state and repeatability

Check both one-rail-off states for unexplained back-power against the actual attached-controller limits. Run the complete G1–G3 sequence on one representative specimen and at least phases C–F plus a 100 kHz smoke on every additional specimen. Record every repair/rework with its cause and photos.

## 7. Evidence pack and final verdict

For a future physical campaign, preserve the commit and all source/native/export hashes, exact DipTrace/OS/profile, fabricator rule deck/order/revisions, specimen IDs, native evidence JSON and DRC, manufacturing package and CAM/DFM material, photos/measurements, continuity/rail/current/static-level tables, raw scope captures, I²C logs, and failure/rework/waiver ledger.

| Verdict | Condition | Result |
| --- | --- | --- |
| `PASS-M1` | native refill/DRC/round-trip + visual review | `PASS` |
| `PASS-DEMO` | M1 + machine package + JLC PCB/BOM preview | `PASS — operator accepted 2026-08-20` |
| `PASS-FAB` | exact package accepted and received geometry matches | `NOT RUN — order excluded from scope` |
| `PASS-HW` | physical phases C–F + 100 kHz G2 pass | `NOT RUN — hardware excluded from scope` |
| `PASS-FM` | G3 also passes on the target load | `NOT RUN` |

A full base physical PASS requires `PASS-M1 + PASS-FAB + PASS-HW` with no unexplained waiver. That claim is not made here. The result of the current bounded scope is `PASS-DEMO`; `PASS-FM` is not required for the base result.

## 8. Closed execution route

1. ~~Close PV-0 at 4.7 kΩ / `0402WGF4701TCE` / `C25900`.~~ Done.
2. ~~Complete M1 operator checks and freeze the candidate with recorded hashes.~~ Done.
3. ~~Verify the machine package and JLC PCB/BOM preview.~~ Done for the demonstration scope.
4. Ordering, physical phases C–H, and a full physical PASS are intentionally not performed under the 2026-08-20 scope decision.
