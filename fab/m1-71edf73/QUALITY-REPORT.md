# Production quality report — m1-71edf73

Result: `PASS — MACHINE PACKAGE`; release gate: `MANUAL CAM/DFM PENDING`.

## Source identity

| Item | Value |
| --- | --- |
| Freeze commit | `71edf73` |
| Native PCB SHA-256 | `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf` |
| Native acceptance SHA-256 | `72f865d0ee94734abebcaf81a534c0ca6d440a65eade449e4a22648fe417312d` |
| DipTrace | `5.3.0.3` |
| Board | 2 layers, 25 × 12 mm |

## Automated checks

| Check | Result |
| --- | --- |
| Native refill/save/reopen round-trip | PASS |
| Native DRC | PASS — `No errors found` |
| Gerber layer count and X2 `FileFunction` attributes | PASS — 8/8 |
| Gerber metric units and EOF | PASS |
| Profile size from Gerber coordinates | PASS — 25 × 12 mm |
| Excellon units and EOF | PASS — metric |
| Drill tools/hits | PASS — 0.30 mm ×17; 1.08 mm ×8 |
| Non-plated drill requirement | PASS — design contains no NPTH holes |
| JLC SMT BOM | PASS — 2 grouped rows, all LCSC populated |
| JLC CPL | PASS — 6 Top-side placements, mm coordinates |
| BOM/CPL RefDes equality | PASS — `Q1,Q2,R1,R2,R3,R4` |
| ZIP integrity | PASS |
| Payload hashes | PASS |

The order BOM/CPL intentionally exclude through-hole `J1/J2`; their complete
native rows remain in `evidence/native/` and they must be installed manually.

## Open manual gates

- Independent CAM/fabricator preview has not yet been accepted.
- Placement rotations have not yet been accepted in the JLC 2D/3D preview.
- Board stack-up, thickness, copper weight, finish, mask, assembly side,
  panelization, and order quantity are not yet recorded.
- Live LCSC stock and assembly pricing were not claimed because the order
  quantity and replenishment policy were not supplied. Re-check them in the
  JLC order immediately before submission.
- Fabricator DFM report and warning/waiver ledger are pending.

No unconditional production-release claim is made until these gates close.
