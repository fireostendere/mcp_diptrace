# PCB build handoff — DUT Controller Rev.A

Status: `SCHEMATIC_ERC0 · PCB_PLACED · USB_ROUTED · POURS+SILK_DONE · REST_ROUTING_PENDING`
Updated: 2026-08-26
Input schematic SHA-256: `cf74ced24bb89357d8783de0c7ae151e44eb45278371f3441dec976f6e867769`
Current board SHA-256: see last commit of `dut-controller-reva-pcb.dipxml`
(`git log -1 --format=%H -- dut-controller-reva-pcb.dipxml`)

Build / iterate commands (exact environment):

```bash
cd /mnt/c/Users/fireo/mcp_diptrace
# regenerate library + schematic (deterministic)
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/lcsc_library.py
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva.py
# placement (idempotent, rebuilds board file)
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva_pcb.py
# manual critical routing (USB pairs; idempotent: re-runs placement first)
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva_pcb.py --manual
# batched autorouter (needs larger budgets; see notes)
PYTHONHASHSEED=0 PYTHONPATH=src .venv/bin/python scripts/build_dut_controller_reva_pcb.py --route usb
```

`PYTHONHASHSEED=0` REQUIRED (PadStyle XML serialization order).

## Ordered gates

| Gate | Status | Evidence / next action |
|---|---|---|
| 0. Resume/preserve | PASS | artifacts at repo root (operator decision) |
| 1. ERC/connectivity/BOM | PASS | erc_basic + schematic_review: 0 findings; pin coverage asserted |
| 2. Datasheet evidence | PASS | ESP32-S3-MINI-1U v1.7 (+official footprint), HDG USB section, per-IC PDFs in vendor/ |
| 3. Footprints & pin maps | PASS | positional pin↔pad order enforced in converter; alnum pads renumbered w/ alias JSON; EPAD grid merged |
| 4. Mechanics/datums | PASS* | connectors on edges; *formal centerline check pending |
| 5. Critical placement | PARTIAL | module N-side corridor cleared (C1-C4 relocated); ESD/fuse/shunt clusters set |
| 6. Stackup | PASS | 2-layer default |
| 7. Routing | PARTIAL | CTRL_DP+5 more USB traces applied via --manual; 10 chains fail clearance by ≤0.05–0.3 mm — see "Next actions" |
| 8. Pours/stitching | PENDING | add_copper_pours GND Top+Bottom after routing completes |
| 9. Silkscreen | PENDING | plan_silkscreen after pours |
| 10. Headless QC | PARTIAL | 1 error left: `The PCB still contains unrouted connections` (~100 links; see Routing next actions). Placement/pours/silk clean |
| 11. Native refill/DRC | PENDING | scripts/diptrace_native_gate11.py pattern |
| 12. Media | PENDING | |

## Routing next actions (exact)

Failing chains print `seg=N req=0.2` — obstacles are adjacent connector-row
pads (pitch 0.5 vs required 0.305 incl width) and the F1 polyfuse bbox near
the CTRL lanes. Fixes, in order:

1. Escape stubs must leave connector columns DIAGONALLY: replace first WP of
   every failing chain with two points forming a 45° jog of ≥0.9 mm
   (e.g. `(4.03,87.75)->(4.9,88.6)->lane`).
2. CTRL_DN lane: raise to y=65.35 only AFTER DP moved to 66.0 (done); if still
   colliding with DP trace edge, stagger verticals: DN drops at x=29.6,
   DP at x=30.85.
3. UP pair: route DN horizontals at y=88.35 (between DP 89.15 and J2 pads).
4. USB1_DP stubs to D9 already OK; mirror exact geometry for USB2 (offset
   −22 mm in y), keep stub lane x=110.4 but approach from y=68.68 only AFTER
   clearing U4 body (start stub at x≥59.6).
5. After all 16 chains apply: run `--route power`, then `--route analog`,
   `--route sense`, then a final catch-all autoroute pass with
   `nets=[remaining]`, grid 0.5, budgets max_nodes=1.8M/time=480 s.
6. Pours: `add_copper_pours(net="GND", layers=("Top","Bottom"),
   stitch_pitch_mm=2.0)`; four-spoke thermals on THT connector pads.
7. Silkscreen: hide service markings (`hide_assembly_markings`), label every
   external connector per docs/DUT_CONTROLLER_REVA_DESIGN.md §Connectors.

## Intentional deviations / open issues

docs/DUT_CONTROLLER_REVA_DESIGN.md §7 (W.FL land verify-before-fab; single
simultaneous DUT data link; no reverse-blocking on PWR; ADS7830 8-bit;
ILIM/fuse coordination). Plus: ESD arrays D9 partially routed, D10 pending
(stub lanes collide with RSH_USB2 courtyard — shift shunt 1 mm left OR move
D10 to the receptacle side).

## Checkpoints

- `f1df06b` placement + firmware skeleton + dut-mcp server + bringup/BOM docs
- later commits: manual-routing stage, protocol doc (see git log)


## Session log (2026-08-26 night)

- Autorouter per-net pass routed CTRL/UP/USB1/USB2 pairs (20 segs, 4 vias;
  ratlines on those nets = 0).
- route_rest adaptive chunking landed ~33 more segments; remaining ~100 links
  exceed in-session router capability at grid 0.5 / 120 s budgets.
- Root-caused & fixed CLI dangling-else that wiped routed traces after runs.
- Component relocations to clear corridors: C1-C4, U5/U6, U19/U20, D9/D10,
  RSH_USB2, R70, C16/C17, C20/C21.
