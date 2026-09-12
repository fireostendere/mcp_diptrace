# DUT Controller Rev.A — sheet 1 specification

Sheet name: `SYSTEM_OVERVIEW`

Scope: one documentary overview sheet only. This file is the Gate-1 contract; it does not authorize any detailed electrical sheet.

## RAG evidence

- Design architecture: document `44f8a5a9-58c7-5473-86b9-59664d3a2af8`, sections `DUT Controller Rev.A — Design Document`, `1. Architecture`, and `USB data path decision`.
- Multi-sheet presentation and gated workflow: document `069b425d-f1a0-5416-ad76-713b72659f8d`, sections `Run gated learning builds one sheet at a time`, `Keep content on the DipTrace page`, and `Add a multi-sheet overview`.
- Exact component evidence for later sheets: document `aac79210-b7a2-55c7-aa23-9a96a9e1f3bd`. It is not used to place parts on this sheet.

## Required content

Seven named documentary blocks, one for each future detailed sheet:

1. `ESP32_CONTROL` — MCP/firmware control and debug.
2. `POWER` — control power and two external power channels.
3. `USB_DUT` — CONTROL/UPLINK and two DUT USB ports.
4. `UART` — two configurable DUT UART channels.
5. `SWITCHES` — eight dry-contact channels.
6. `AUX_ADC` — AUX GPIO and rail measurements.
7. `CURRENT_SENSE` — four monitored power paths.

Show PC/MCP as a bounded endpoint block on the left and DUT as a bounded endpoint block on the right so no connection terminates in empty space. Keep the primary control/USB flow left-to-right. Align the five peer service blocks to one shared top and bottom edge. Use visible orthogonal documentary lines labelled with interface groups; do not create electrical connectivity on this sheet.

Show logic and control groups only: `CONTROL USB`, `UPLINK USB`, `I2C_SDA / I2C_SCL`, GPIO enables, UART control, and `DUT interfaces`. Do not draw global power rails or `+3V3 / +5V / GND` distribution on this overview. Any more detailed net name requires a later source-bound sheet specification.

## Acceptance checks

- The artifact contains exactly one sheet named `SYSTEM_OVERVIEW`.
- It contains zero placed parts, zero electrical nets and zero electrical wires.
- It contains exactly seven named functional block rectangles plus two bounded external endpoint rectangles for PC/MCP and DUT.
- All lines are documentary `Shape` objects, orthogonal, and do not cross a block interior except at the intended edge.
- Peer blocks are aligned, direct connections use one segment, every bend has an obstacle/entry-side reason, lines do not cross, and no line ends in empty page space.
- All text is horizontal and all content is inside the centered A4 usable page bounds.
- Native DipTrace open/save/re-export preserves the sheet name, shapes, text and zero-part/zero-net state.
- PCB artifacts remain byte-for-byte unchanged.
