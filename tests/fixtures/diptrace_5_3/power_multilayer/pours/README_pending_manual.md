# Copper-pour evidence — pending manual DipTrace 5.3.0.2 work

No `before_refill.xml` or `after_refill.xml` is present yet. Do not rename this file or
the fixture directory to imply that the evidence pair is complete.

1. Open `../source_board.xml` in DipTrace PCB Layout 5.3.0.2.
2. Confirm the 70 × 50 mm outline, four copper layers, component sides, nine traces and
   two through vias. Recalculate the ratsnest, but do not change placement or routing.
3. Add a GND copper pour on Top (or Bottom if Top is unavailable for a controlled case),
   keeping enough clearance around the existing routes.
4. Configure thermal relief for at least one through-hole GND pad, preferably `J1:2`,
   `J2:2`, `J3:2` or `J4:2`.
5. Add one clearly distinguishable cutout, island-control case or equivalent feature if
   the GUI supports it.
6. Do **not** run refill. Export official DipTrace XML to `before_refill.xml`.
7. Run **Update All Copper Pours / Refill** exactly once.
8. Change nothing else. Export official DipTrace XML to `after_refill.xml`.
9. Record exact DipTrace version/build, Windows version and SHA-256 for both files in
   `../manifest.pending.json`, then promote it to a schema-conforming `manifest.json`.
10. Re-import both XML files through MCP and verify that their only intended semantic
    difference is refill-derived copper geometry/status.

The MCP did not perform these steps because capability discovery confirms copper-pour
boundaries are readable but authoritative refill geometry is not writable. Fabricating
that XML would defeat the purpose of the fixture.
