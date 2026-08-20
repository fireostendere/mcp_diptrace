# Changes in m1-71edf73

Compared with base commit `2506ca1`:

- fixed R1–R4 at 4.7 kΩ ±1 %, MPN `0402WGF4701TCE`, LCSC `C25900`;
- inset both copper-pour boundaries by the 0.2 mm board clearance and disabled
  outline snapping, eliminating native DipTrace copper-to-outline DRC errors;
- retained the compact 25 × 12 mm two-layer layout, continuous Bottom GND,
  Top GND, four-spoke connector-GND thermals, and 17 distributed stitching vias;
- regenerated PCB demonstration media and completed physical/photo review;
- froze the validated sources at commit `71edf73` and exported this package
  from the accepted native-saved DipTrace file.
