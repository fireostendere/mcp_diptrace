<!-- quality-gate-event: 0b2ab229714be54e -->
## 2026-08-26T17:12:40.681632+00:00 — BLOCKED

- Project: `/mnt/c/Users/fireo/mcp_diptrace`
- Handoff: `/mnt/c/Users/fireo/mcp_diptrace/PCB_BUILD.md`
- Gates: 0=PASS, 1=PASS, 2=PASS, 3=PASS, 5=PARTIAL, 6=PASS, 7=PARTIAL, 8=PENDING, 9=PENDING, 10=PARTIAL, 11=PENDING, 12=PENDING
- Board: `/mnt/c/Users/fireo/mcp_diptrace/dut-controller-reva-pcb.dipxml`
- Board SHA-256: `b8c6b4473b172a980fdbd2d5259b10cfa47fe9ccff306c13c7cf2e211957f5b4`
- Headless QC: hard errors=3, warnings=2, unrouted=529, score=113231.63830908196

### Blocking evidence

- gate 6 (Stackup) is PASS while earlier gate 5 (Critical placement) is PARTIAL
- cannot verify current board SHA (PCB_BUILD.md has no record)
- schematic SHA stale: dut-controller-reva.dchxml does not match PCB_BUILD.md record
- QC error [unrouted_connections] The PCB still contains unrouted connections.
- QC error [two_layer_ground_pour_missing] Ground pour is missing on: bottom, top.
- QC error [silkscreen_mounting_overlap] Visible silkscreen overlaps another component, pad, hole, or via.

### Pending gates

- gate 5 (Critical placement)
- gate 7 (Routing)
- gate 8 (Pours/stitching)
- gate 9 (Silkscreen)
- gate 10 (Headless QC)
- gate 11 (Native refill/DRC)
- gate 12 (Media)

### QC findings

- `warning` `layout_off_center`: Occupied component geometry is not centered in the board outline.
- `error` `unrouted_connections`: The PCB still contains unrouted connections.
- `error` `two_layer_ground_pour_missing`: Ground pour is missing on: bottom, top.
- `warning` `ground_stitching_sparse_regions`: Some free board regions are farther from GND stitching than the configured coverage radius.
- `error` `silkscreen_mounting_overlap`: Visible silkscreen overlaps another component, pad, hole, or via.

<!-- quality-gate-event: c597cb47e1b7cbb2 -->
## 2026-08-26T17:15:46.870169+00:00 — BLOCKED

- Project: `/mnt/c/Users/fireo/mcp_diptrace`
- Handoff: `/mnt/c/Users/fireo/mcp_diptrace/PCB_BUILD.md`
- Gates: 0=PASS, 1=PASS, 2=PASS, 3=PASS, 5=PARTIAL, 6=PASS, 7=PARTIAL, 8=PENDING, 9=PENDING, 10=PARTIAL, 11=PENDING, 12=PENDING
- Board: `/mnt/c/Users/fireo/mcp_diptrace/dut-controller-reva-pcb.dipxml`
- Board SHA-256: `b8c6b4473b172a980fdbd2d5259b10cfa47fe9ccff306c13c7cf2e211957f5b4`
- Schematic: `/mnt/c/Users/fireo/mcp_diptrace/dut-controller-reva.dchxml`
- Schematic SHA-256: `cd4e470b318464921fb36f038e85ae14132a94ee5ba12dea5c4e9b3b8a0c1241`
- Recorded input SHA-256: `cd4e470b318464921fb36f038e85ae14132a94ee5ba12dea5c4e9b3b8a0c1241`
- Recorded board SHA-256: `b8c6b4473b172a980fdbd2d5259b10cfa47fe9ccff306c13c7cf2e211957f5b4`
- Headless QC: hard errors=3, warnings=2, unrouted=529, score=113231.63830908196

### Blocking evidence

- gate 6 (Stackup) is PASS while earlier gate 5 (Critical placement) is PARTIAL
- QC error [unrouted_connections] The PCB still contains unrouted connections.
- QC error [two_layer_ground_pour_missing] Ground pour is missing on: bottom, top.
- QC error [silkscreen_mounting_overlap] Visible silkscreen overlaps another component, pad, hole, or via.

### Pending gates

- gate 5 (Critical placement)
- gate 7 (Routing)
- gate 8 (Pours/stitching)
- gate 9 (Silkscreen)
- gate 10 (Headless QC)
- gate 11 (Native refill/DRC)
- gate 12 (Media)

### QC findings

- `warning` `layout_off_center`: Occupied component geometry is not centered in the board outline.
- `error` `unrouted_connections`: The PCB still contains unrouted connections.
- `error` `two_layer_ground_pour_missing`: Ground pour is missing on: bottom, top.
- `warning` `ground_stitching_sparse_regions`: Some free board regions are farther from GND stitching than the configured coverage radius.
- `error` `silkscreen_mounting_overlap`: Visible silkscreen overlaps another component, pad, hole, or via.

