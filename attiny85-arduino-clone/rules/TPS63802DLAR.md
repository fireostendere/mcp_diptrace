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

