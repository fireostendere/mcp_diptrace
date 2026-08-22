# TPS63802DLAR rules

Source: Texas Instruments, *TPS63802 2-A High-Efficiency Low-IQ Buck-Boost
Converter*, SLVSEU9D, revised January 2021:
https://www.ti.com/lit/ds/symlink/tps63802.pdf

- Pin mapping, Table 7-1 on PDF page 4: EN=1, MODE=2, AGND=3, FB=4, PG=5,
  VOUT=6, L2=7, GND=8, L1=9, VIN=10.
- EN and MODE must not float. MODE low selects power-save operation; this
  design ties MODE to GND and EN to USB VBUS.
- 3.3 V typical application, Figure 10-1 on PDF page 17: L1=0.47 µH,
  C1=10 µF, C2=22 µF, R1=511 kΩ, R2=91 kΩ, R3=100 kΩ.
- PG is open-drain (Table 7-1); R3 is its +3.3 V pull-up.
- PCB-stage constraint: place the input/output capacitors and inductor tightly
  around U3 and keep both switching nodes compact.

## PCB layout and grounding

Source: section 12.1 "Layout Guidelines", PDF page 28:

1. Place input and output capacitors as close as possible to the IC; keep the
   traces short, wide, and direct for low trace resistance and low parasitic
   inductance.
2. Use a common ground node for power ground and a different one for control
   ground to minimize the effects of ground noise; connect these ground nodes
   at any place close to one of the ground pins of the IC.
3. Use separate traces for the power-stage supply and the analog-stage supply.
4. The FB sense trace is a signal trace; keep it away from the L1 and L2
   switching nodes.

Grounding interpretation (revision history, PDF page 4, "Changes from Revision
B to Revision C"): TI **deleted** the old guideline to separate AGND and PGND
and the old wording "connect AGND and PGND through via at a different layer".
The current guidance is therefore not split ground planes: keep one continuous
ground, and if power and control grounds are islanded, join them at a single
point next to an IC ground pin (local star tie), not through a distant layer.

