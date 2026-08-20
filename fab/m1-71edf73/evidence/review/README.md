# Phase A visual evidence — I²C level shifter

Status: `READY FOR OPERATOR REVIEW`; this is native/software evidence, not a
substitute for the pending physical 1:1 component fit.

Review in this order:

1. `00-review-sheet.png` — one-page visual index.
2. `01-native-top-active-ui.png` — exact native-saved XML open in DipTrace
   5.3.0.3, Top side and `Top (1)` active; the Layers and Design Manager panels
   remain visible as provenance context.
3. `02-native-bottom-active-ui.png` — the same exact file with Bottom side and
   `Bottom (2)` active. Confirm the plane is continuous except for intended
   plated holes/pads/vias and that no routed signal trace cuts it.
4. `03-native-top-overview.png` and `04-native-bottom-plane.png` — UI-free
   board-boundary crops with about 10% framing margin.
5. `05-j1-gnd-thermal.png` and `06-j2-gnd-thermal.png` — confirm four-spoke
   relief at J1.1 and J2.1. The native pour settings also record `Spoke="4
   spoke"` and `SpokeWidth="0.011811"` for both copper layers.
6. `07-native-drc-pass.png` — native DRC dialog: `No errors found`.
7. `08-media-stage-contact-sheet.png` — all 26 construction stages, ending in
   the full pours and 17 distributed GND stitching vias.
8. `09-physical-fit-1to1-A4.pdf` — print at 100% / Actual Size, first measure
   the 100.00 mm control ruler, then place the real BSS138, 0402 parts, and 1×4
   headers. `09-physical-fit-1to1-preview.png` is only a screen preview and has
   no physical scale.

Operator verdict remains deliberately blank in
`docs/bringup-i2c-level-shifter.md`. Record any ambiguity or rejection there;
do not grant `PASS-M1` from these files alone.
