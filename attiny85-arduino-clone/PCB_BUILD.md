# PCB build handoff

Status: `ROUTED_2LAYER_PENDING_NATIVE`
Updated: 2026-08-23
Input schematic SHA-256: `2f5ee017e42890eaaddc50de831390dcae6cda38531e24c161bc058013ed3ec2`
Starting board SHA-256: `cadc29c4c005ad322276fe3ef8f262795510f9a6de641b6e3544a1e9804c9fd2`
Current board SHA-256: `b4acaf5cece1c1d583b8096528d81fea88d282a33ed71870a5ae30aa7bcbb813`

## Ordered gates

| Gate | Status | Evidence / next action |
|---|---|---|
| 0. Resume and preserve worktree | PASS | User artifacts preserved; `fab/m1-71edf73/image.png` untouched. |
| 1. ERC, connectivity, netlist, BOM | PASS | `build_connectivity.py` asserts full pin coverage (`assigned \| NO_CONNECT == pin_ids`) and rewrote nets without J2; sync asserts in `build_pcb.py` pass. |
| 2. Official datasheet/package/layout evidence | PASS | `rules/ATTINY85-20SU.md`, `rules/CP2102-GM.md`, `rules/TPS63802DLAR.md`; TI DLA0010A layout captured in the TPS rules file. |
| 3. Footprints and pin maps | PASS | `_validate_tps_footprint` asserts DLA0010A 0.250 mm pad styles and segmented pad 8 paste; J1 shield pads renumbered 7..13 and tied to GND; LCSC patterns synced (`PATTERNS`). |
| 4. Mechanics and connector datums | PASS | J1/J3 centerline group checked by `review_pcb_quality(centerline_groups={"y": ["J1","J3"]})`; board edge datum X_SHIFT keeps J1 opening at outline. J2 removed at the schematic source (see deviations). |
| 5. Datasheet-driven critical placement | PASS | `POSITIONS` implements the C1-left / C2-right / L1-above target; manual VBUS tree (J1→C1→VIN, EN branch, VOUT→C2) applied before autorouting. |
| 6. Stackup | PASS | Default `--layers 2`; four layers only via explicit flag after a recorded two-layer failure (none occurred). |
| 7. Routing | PASS | Zero ratlines asserted; 50 traces, 42 vias total, ≤2 vias per connection, no via-in-pad, escapes beyond pad copper. VBUS trunk J1→C1 pre-routed at 0.5 mm (0.25 through the connector zone); TPS_L1/L2 manual hot-loop verticals 0.45 mm with a 0.35 mm taper through the pin-row zone so the U3.8 GND corridor stays routable; router VBUS intent kept at 0.25 mm (only the high-Z R4 sense tap is router-routed). Long hauls (USB pair, +3V3 to U2 VDD, TXD to J3) cross on Bottom where Top is walled. |
| 8. Ground pours and stitching | PASS | GND pours Top+Bottom (`add_copper_pours`, 0.13 clearance, four-spoke connector thermals) plus 21 distributed stitch vias; QC stitching coverage gate green. |
| 9. Silkscreen | PASS | `plan_silkscreen` unresolved set empty (asserted); planner now treats vias as fixed obstacles so labels never overlap stitch vias. |
| 10. Headless QC | PASS | `review_pcb_quality` hard_error_count == 0 gate inside `build()`; pre-QC artifact dumped to `.attiny85-2layer-*-preqc.dipxml` on failure for diagnosis. |
| 11. Native DipTrace refill/DRC | IN PROGRESS | Headless native DRC driver works (`scripts/diptrace_native_gate11.py`, real Pcb.exe 5.3 on a hidden desktop). Native findings reduced 31 -> 3 after the trace-transition fix, pour clearance 0.18, hidden service silk texts, and the 13.9 mm outline. Remaining: C5.1 silk-to-pad (-0.093, cause under investigation), pour-to-TPS_L1/L2 at 0.125 vs 0.13 (native fill ignores the pour clearance attribute - investigating). |
| 12. PNG/MP4/GIF and final frame | PENDING | After gate 11: re-record via `diptrace-mcp-cinematic` capture -> compile -> ffmpeg; boundary-fit framing per house rules; inspect final frame. The existing `attiny85-arduino-clone-pcb.{png,mp4,gif}` are a **stale pre-J2-removal render** — do not ship or resume from them. |

## Build command (exact environment)

```bash
cd /mnt/c/Users/fireo/mcp_diptrace
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python attiny85-arduino-clone/build_pcb.py --layers 2
```

- `.venv/bin/python` is required; the system `python3` has no dependencies.
- `PYTHONPATH=src` is required even inside the venv because the installed
  `site-packages` copy of `diptrace_mcp` is older than `src/`.
- `PYTHONHASHSEED=0` is REQUIRED: PadStyle XML elements serialize in
  hash-set order, so an unpinned seed yields byte-different (same-geometry)
  boards and unstable SHA-256 records.
- Outputs: final board at `attiny85-arduino-clone-pcb.dipxml`;
  `.attiny85-2layer-v14-placed.dipxml` style debug artifacts land next to
  `--output`.

## Intentional deviations

- **GND pour clearance 0.18 mm** (rule 0.13): the native pour fill measures
  up to 5 um inside the requested clearance near polygon corners.
- **Board outline height 13.9 mm** (was 13.7): the router does not model
  outline clearance; its USB_D+ hop copper sat 25 um past the old edge.
- **Service silk texts hidden** (Pattern/Manufacturer/Datasheet besides
  Name/Value): their empty-text bounding boxes tripped native silk checks.
- **Dedupe stale-via cleanup removed (root-cause fix)**: the replacement paths
  deliberately share sibling same-net vias, and `DeleteViaOperation` rewrites
  the FOLLOWING trace point to the incoming layer, silently killing the new
  trace's Top->Bottom transition. DipTrace then re-inserted the missing vias
  on load next to pads (C6.2, U2 pin row) - the source of 28 of the original
  31 native DRC findings.
- **GND pour clearance 0.18 mm** (rule 0.13): the native pour fill measures
  up to 5 um inside the requested clearance near polygon corners.
- **Board outline height 13.9 mm** (was 13.7): the router does not model
  outline clearance; its USB_D+ hop copper sat 25 um past the old edge.
- **Service silk texts hidden** (Pattern/Manufacturer/Datasheet in addition
  to Name/Value): their empty-text bounding boxes tripped native silk checks.
- **VBUS router intent kept at 0.25 mm** (trunk widened separately): the only
  ISP pin set already exposed by J3. Removed from `.dchxml`,
  `build_connectivity.py`, `layout_and_wire.py`, `set_bom_fields.py`,
  provenance and README. `build_pcb.py` asserts no J2 reaches the PCB.
- **Router layer preference repriced**: the old per-step `via_cost` tax on
  non-preferred layers made any necessary Bottom run astronomically expensive
  and starved A* (whole-board floods, zero vias placed). Preference is now
  expressed only through per-transition `via_cost`; the open-fixture test was
  updated accordingly (`test_multilayer_router_does_not_force_layer_preference_vias`).
- **Diagonal trace obstacles chunked**: axis-aligned bbox of a diagonal segment
  walled off legal corridors (it blocked R3.2's Top escapes ~0.95 mm from real
  copper). Diagonals are split into ≤0.25 mm chunks with tight boxes.
- **Via-site checks cached**: pad blockers are resolved once per connection and
  shape→shapely conversion is memoized; `_via_blocked` got an envelope
  pre-filter. Search throughput rose ~24× (4k → ~100k nodes/30 s).
- **Budget ladder continues past exhaustion**: time/node-budget failures get
  `reason: resource_exhausted` and the min-via ladder proceeds to higher
  budgets instead of aborting (budget 2 routes links that budgets 0–1 cannot).
- **Silkscreen planner treats vias as obstacles** (previously ignored).
- **CP2102_TXD routes on Top+Bottom**: the stale Top-only group could not close
  U1↔J3 hop which requires two vias.
- **Router time budgets must never bind before the node cap** (root cause of
  the 2026-08-24 USB_D- flap): A* checked its wall-clock deadline first, so a
  busy WSL host exhausted 30 s before reaching 1M nodes and long hauls failed
  nondeterministically. `route_time_budget_ms=900_000` vs `max_nodes=1_000_000`
  (≈300 s worst case measured) keeps results machine-speed independent; the
  time guard is now a pure runaway safety net. RefDes post-processing was
  proven innocent by an A/B run (disabled block still failed on USB_D-).

## Checkpoints

- `720a478` checkpoint: preserve routed board draft (previous stage)
- Schematic source J2 removal — see git log for the exact hash
- Router/silkscreen core fixes + tests — see git log
- Routed 2-layer board + build script + this handoff — see git log

Native acceptance and media commits follow gates 11–12.
