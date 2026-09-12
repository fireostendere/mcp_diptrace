# PCB build handoff template

Copy the section below into the board project's `PCB_BUILD.md`. Replace all angle
brackets with actual values; use `none` where no evidence or commit exists yet.
The hash labels and numbered table rows are parsed by
`scripts/pcb_quality_gate.py`
in a source checkout. The wheel does not ship that project-specific script.

---

# <Project> — PCB build

Revision: <revision and assembly variant>
Requested endpoint: <schematic / PCB / production package / tested board>

Input schematic: <path>
Input schematic SHA-256: `<64 lowercase hexadecimal characters>`
Input board before edits: <path and SHA-256, or none for a new build>
Current board: <path>
Current board SHA-256: `<64 lowercase hexadecimal characters>`

| Gate | Status | Evidence |
|---|---|---|
| 1. Electrical checks | PENDING | <report> |
| 2. Official source evidence | PENDING | <rules and source revisions> |
| 3. Footprint and pin-map validation | PENDING | <pin/pad and geometry checks> |
| 4. Mechanics and connector datums | PENDING | <outline, mounting, enclosure> |
| 5. Critical placement | PENDING | <vendor layout comparison> |
| 6. Two-layer-first stackup | PENDING | <stackup and fab evidence> |
| 7. Critical then remaining routing | PENDING | <route/constraint checks> |
| 8. Zero ratlines | PENDING | <connectivity evidence> |
| 9. GND pours and stitching | PENDING | <both sides and coverage> |
| 10. Silkscreen | PENDING | <clearance and readability> |
| 11. Headless QC | PENDING | <hard_error_count == 0> |
| 12. Native refill/connectivity/DRC | PENDING | <native evidence and hashes> |
| 13. Media and release inspection | PENDING | <PCB, MP4, GIF; CAM if in scope> |

Use PASS, FAIL, PENDING, TODO, MANUAL, or PARTIAL in the status column. Describe
out-of-scope work in the evidence column; the checker does not accept N/A statuses.
Do not mark checks passed by filling in this template.

Last passing gate: <number or none>
Current failure evidence: <finding, artifact, and owning stage, or none>
Intentional datasheet deviations: <source requirement, deviation, consequence, disposition>
Other input/output SHA-256 hashes: <libraries, rule sources, native outputs, media, releases>
Last checkpoint commit: <actual commit hash or none>
If Git writes are unavailable: <exact paths and intended git add / git commit commands>
Resume from repository root: `<exact runnable command with concrete paths and flags>`
