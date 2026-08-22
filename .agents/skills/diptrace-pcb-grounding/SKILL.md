---
name: diptrace-pcb-grounding
description: Choose and implement the grounding strategy of a DipTrace PCB — continuous polygon vs star tie vs islands — from datasheet evidence, and build it headless with pours, stitching vias and thermal reliefs. Use when starting a PCB layout, placing a switching regulator or QFN part, or reviewing a ground system.
---

# DipTrace PCB Grounding

Decide the ground system from datasheet evidence first, then implement it with
the house 2-layer stackup. Datasheets, electrical safety, DRC, and
manufacturability take precedence over any rule here.

## Decide the strategy from the datasheet

1. Read the Layout section **and the revision history** of every power IC.
   Vendors quietly retire old grounding advice. Example: TI TPS63802
   (SLVSEU9D, rev B→C changes) *deleted* the guideline to separate AGND and
   PGND and the wording "connect AGND and PGND through via at a different
   layer"; the current text asks for a common power-ground node and, if
   control ground is kept separate, a join "close to one of the ground pins of
   the IC". Old split-plane advice found in forum posts or app notes is
   obsolete for that part.
2. Default answer for ordinary 2-layer boards: one continuous GND polygon on
   Bottom, GND pour on Top, stitched together. Do not split planes.
3. "Separate grounds" in a modern datasheet means **nodes/islands that meet at
   a single point near the IC ground pin** (a local star tie), not physically
   split copper regions spanning the board. Implement islands only when the
   current datasheet text still demands them; join them at the IC pad.
4. Reserve true star grounding (separate return wires meeting at one chassis
   or supply node) for mixed high-current/precision-analog systems; it is not
   a PCB-plane technique and must never break the continuous plane under
   signal traces.

## Switching regulator stage

- Input and output capacitors as close as possible to the IC; short, wide,
  direct traces (TPS63802 §12.1 items 1 and 3: separate supply traces for
  power stage and analog stage).
- Keep both switching-node copper areas compact; the inductor sits tight
  between the L pins.
- FB is a signal trace: route it away from L1/L2 and the inductor body.
- Return currents of the hot loop (input cap → IC → output cap) must flow in
  local copper, not through a distant board region.

## QFN exposed pads and thermal grounding

- An exposed pad that the pin table ties to GND is soldered and used as the
  part's primary ground and heat path. Example: CP2102 Table 4 footnote 2 —
  thermal resistance assumes a multi-layer PCB with the exposed pad soldered
  to a PCB pad.
- Put a via cluster under/around the exposed pad into the Bottom plane; each
  via typically 0.3 mm drill for hand assembly friendliness.

## MCU and analog corners

- Bypass capacitors as close to VCC/GND pins as possible (ATtiny85 §17.9).
- Analog tracks short, over the ground plane, away from switching digital
  tracks; do not route digital signals through the analog return area.

## Implement it in the board (house stackup)

- Bottom layer: effectively continuous GND plane; break it only where a
  necessary via or mechanical constraint forces it. Pour GND on Top too.
- Stitch Top and Bottom GND across every free region on about a 2 mm grid on
  small boards; verify coverage in every part of the board, not by via count.
- Connector GND pads that are hand-soldered get four-spoke cross thermal
  reliefs into the pours.
- After pours and stitching, run the return-path review
  (`analyze_return_path` in diptrace MCP) and DRC; the plane under every
  signal trace is the acceptance check.

## Record the evidence

- Every ground decision lands in the project `rules/` file of the responsible
  IC with the datasheet section, page, and revision quoted, so schematic and
  layout reviews can check it. Obsolete advice (split planes, distant star
  points) is recorded as explicitly rejected with the revision that deleted
  it.
