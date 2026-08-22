# ATtiny85 Arduino-like schematic

Review-only DipTrace schematic split into four electrical sheets: `USB_POWER`,
`USB_UART`, `MCU_ISP`, and `IO`, plus the documentary `SYSTEM_OVERVIEW`
cross-sheet map. No PCB layout has been started.

## Design decisions

- System rail: +3.3 V.
- U1: ATTINY85-20SU on its internal 8 MHz oscillator.
- U2: CP2102-GM in regulator-bypassed, self-powered mode. Its UART is routed
  to PB3/PB4 as a software UART.
- J2: standard 2x3 AVR ISP. This is the guaranteed first-flash and recovery
  path because CP2102 is a USB-to-UART bridge, not an AVR ISP programmer.
- C6: 100 nF coupling from CP2102 DTR to RESET; R6 is the 10 kOhm reset pull-up.
- U3: TPS63802DLAR configured for +3.3 V and power-save mode.
- J3: PB0..PB4, RESET, +3V3, and GND on a compact 2x4 2.54 mm header.

USB ESD protection and the PCB layout are deliberately deferred until this
schematic is accepted.

## Files

- `attiny85-arduino-clone.dchxml` — open this in DipTrace Schematics.
- `COMPONENT_PROVENANCE.md` — exact DipTrace/LCSC origin for every component.
- `layout_and_wire.py` — deterministic on-page placement and orthogonal local
  wiring; native Net Port components carry every cross-sheet connection and
  native power symbols carry +3V3, VBUS, and GND. It also builds the
  non-electrical Altium-style overview from native DipTrace shapes.
- `vendor/` — saved LCSC catalog source and deterministic DipTrace conversions
  for parts absent from the installed DipTrace libraries.
- `rules/` — sourced rules used for the fixed ICs.

Validation: offline ERC, schematic review, BOM review, and connectivity review
each report zero findings. The explicit per-sheet wiring check reports zero wire
crossings, component-body hits, unrelated-pin hits, page-boundary escapes,
excessive detours, label/support collisions, and anonymous `Net <number>`
names. Reopen the generated file in DipTrace before visual acceptance so the
editor does not show a stale in-memory copy. Demo screenshots and recordings
were intentionally not generated.
