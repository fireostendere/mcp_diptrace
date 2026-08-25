# DUT Controller Rev.A — Design Document

Universal physical-DUT controller for AI/MCP agents. Main controller:
**ESP32-S3-MINI-1U-N8** (LCSC C2980299).

Sources of truth: ESP32-S3-MINI-1/-1U datasheet **v1.7**
(documentation.espressif.com), Espressif official KiCad footprint
(`ESP32-S3-MINI-1U.kicad_mod`), ESP32-S3 Hardware Design Guidelines
(docs.espressif.com, "PCB Layout Design"), per-IC datasheets in `vendor/`.

## 1. Architecture

```
LLM → MCP server (PC) → USB-CDC or TCP → ESP32-S3 → HAL → DUT
```

Connectors:

| Ref | Connector | Role |
|---|---|---|
| J1 | USB-C 16p (TYPE-C-31-M-12) | CONTROL: powers board, ESP32 native USB (CDC/JTAG/flash) |
| J2 | USB-C 16p | UPLINK: PC host USB 2.0 pair for DUT enumeration |
| J3/J4 | USB-A receptacle (UK-USB AF 90-19.6) | USB1/USB2 DUT ports |
| J5/J6 | HDR-1x4 | UART1/UART2: GND,VREF,TX,RX |
| J7/J8 | HDR-2x8 | SW1..SW8 dry contacts (row A / row B) |
| J9/J10 | HDR-2x5 | AUX1/AUX2 |
| J11..J14 | TB 1x2 5.08 | PWR1_IN, PWR1_OUT, PWR2_IN, PWR2_OUT |
| J15 | HDR-2x5 | DEBUG: console UART0, EN/RST, BOOT, spare IOs |
| ANT1 | W.FL-R-SMT-1 | module antenna (MHF III/W.FL compatible per datasheet §10.2) |

### USB data path decision (documented deviation)

The UPLINK pair is switched by two TS3USB221 2:1 muxes to USB1/USB2. The PC
sees the DUT **natively** (no hub, no proxy). Rev.A limitation: only ONE port
may be data-connected at a time; firmware interlock auto-disconnects the other
(`usb.data()` on port B returns error while A is CONNECTED). Simultaneous dual
enumeration = Rev.B (add SL2.1A-class hub). VBUS is fully independent per port.

Fail-safe: TS3USB221 OĒ has 100 k pull-ups → reset/crash/flashing ⇒ both muxes
disabled ⇒ DUT data lines float (DUT keeps working standalone).

## 2. Power architecture

- CONTROL VBUS 5 V → polyfuse 1.5 A (F1) → `+5V` rail → AMS1117-3.3 (U?) →
  `+3V3`. Bulk 22 µF + 100 nF per datasheet typical application.
- `+3V3` feeds ESP32 module (peak 355 mA WiFi TX, supply must deliver ≥0.5 A
  per datasheet Table 6-2), logic, PhotoMOS LEDs, ESD clamps.
- DUT VBUS n: `+5V` → polyfuse F2/F3 1.5 A hold → shunt 20 mΩ → INA226 →
  SY6280AAC current-limited switch (ILIM ≈ 1.8 A) → USB-A VBUS pin +
  SMAJ5.0A TVS + 10 k bleed.
- PWR n: terminal IN (3.3–24 V) → SMBJ26A TVS → AO3401A P-FET high side
  (gate: 100 k to source = OFF default; NPN MMBT3904 + 470 Ω from GPIO turns
  ON; 12 V zener clamp on VGS; RC soft start) → shunt 20 mΩ → INA226 → OUT.
- Reverse current DUT→PSU is NOT blocked by the P-FET body diode topology;
  INA226 reports negative current (agent-detectable). True blocking = Rev.B.
- Current sense: 4× INA226 (addresses 0x40 USB1 / 0x41 USB2 / 0x42 PWR1 /
  0x43 PWR2 via A0/A1 straps), ±81.92 mV FS over 20 mΩ = ±4.096 A,
  LSB 0.125 mA; bus-voltage pin measures DUT-side voltage (36 V max).
- ADC: ADS7830IPWR (pin-compatible ADS7828, 8-bit — enough to distinguish
  0/1.8/3.3/5 V; documented trade-off, drop-in 12-bit upgrade possible) at
  0x48. CH0..3 = external ADC1..4 inputs: divider 30k/20k (Zin 50 k,
  ×0.4 → 6 V→2.4 V vs internal 2.5 V ref) + BAT54S clamp to +3V3 + 1 nF.
  CH4..7 internal rails: +5V, +3V3, VBUS1_OUT, VBUS2_OUT (30k/20k dividers).

## 3. GPIO map (verified against datasheet Table 3-1)

Strapping pins per datasheet §4: GPIO0 (weak PU), GPIO3 (floating),
GPIO45 (weak PD), GPIO46 (weak PD). N8 variant ⇒ IO35/36/37 free (no PSRAM).

| GPIO | Pad | Function | Reset state | Notes |
|---|---|---|---|---|
| IO0 | 4 | BOOT button → GND | PU | strap: boot mode |
| IO1 | 5 | DEBUG hdr spare | Hi-Z | ADC1_CH0 capable |
| IO2 | 6 | I2C_SDA | Hi-Z | ext 4.7 k PU |
| IO3 | 7 | — NC | — | strap (JTAG source), leave free |
| IO4 | 8 | I2C_SCL | Hi-Z | ext 4.7 k PU |
| IO5 | 9 | UART1_POL | PD 100k → NORMAL | matrix select |
| IO6 | 10 | UART1_TXG | PD 100k → gated OFF | TX gate (0=sink) |
| IO7 | 11 | UART1_RXG | PD 100k → gated OFF | RX gate |
| IO8 | 12 | DEBUG hdr spare | Hi-Z | |
| IO9 | 13 | USB1_OĒ | PU 100k → disabled | TS3USB221 #1 |
| IO10 | 14 | USB1_S | PD | select |
| IO11 | 15 | USB2_OĒ | PU 100k → disabled | TS3USB221 #2 |
| IO12 | 16 | USB2_S | PD | |
| IO13 | 17 | UART2_POL | PD → NORMAL | |
| IO14 | 18 | UART2_TXG | PD → OFF | |
| IO15 | 19? no — pad 20 | see below | | |

Corrected pads (Table 3-1): IO13=pad17, IO14=pad18, IO15=pad19, IO16=pad20,
IO17=pad21, IO18=pad22, IO21=pad25, IO26=pad26, IO33=pad28, IO34=pad29,
IO35=pad31, IO36=pad32, IO37=pad33, IO38=pad34, IO47=pad27, IO48=pad30.

| GPIO | Function | Reset state |
|---|---|---|
| IO16 | VBUS1_EN (SY6280 EN, PD 100k=off) | off |
| IO17 | VBUS2_EN | off |
| IO18 | PWR1_EN (NPN gate driver, PD=off) | off |
| IO21 | PWR2_EN | off |
| IO26 | LED_STATUS | Hi-Z (LED off) |
| IO33..36 | AUX1.IO1..IO4 (series 100R + ESD array) | Hi-Z |
| IO37,38,47,48 | AUX2.IO1..IO4 | Hi-Z |
| IO39..42 | DEBUG header (MTCK/MTDO/MTDI/MTMS JTAG) | Hi-Z |
| IO43/44 (pads 39/40) | U0TXD/U0RXD console → DEBUG hdr | UART0 |
| IO45/46 | — NC | straps |
| IO19/20 (pads 23/24) | USB_D-/D+ → J1 via USBLC6-2SC6 | native USB |

No DUT-affecting output is on a strapping pin; every actuator line has a
hardware pull that forces the safe state at reset (see §4).

## 4. Fail-safe table

| Subsystem | Reset/crash state | Mechanism |
|---|---|---|
| SW1..8 | OPEN | PCA9539 registers reset to input; LED path open |
| PWR1/2 | OFF | 100 k gate-source pulldown on P-FET |
| VBUS1/2 | OFF | SY6280 EN pulldown; quick discharge via 10 k bleed |
| USB data | DISCONNECTED | OĒ pull-up disables muxes |
| UART routes | DISCONNECTED | TS5A23157 IN pulldowns route TX/RX into sinks |
| AUX IOs | Hi-Z | ESP32 reset = high impedance |
| Module EN | runs after RC | 10 k PU + 1 µF RC per HDG |

## 5. UART port circuit (per port)

```
ESP TX ──LVC2T45 ch1 (DIR=H)──U?TX_V──[SPDT g1]──┬─(NO)─[SPDT m1 COM]
                                                 └─(NC)─10k GND sink
ESP RX ←─LVC2T45 ch2 (DIR=L)──U?RX_V←─[SPDT g2]──┬─(NO)─[SPDT m2 COM]
                                                 └─(NC)─10k sink
m1: NO=lineA(drv) NC=lineB(drv)   m2: NO=lineB(sense) NC=lineA(sense)
```
- Shifters SN74LVC2T45DCUR: VCCA=+3V3, VCCB=VREF_n (DUT-supplied, 100 k PD,
  series 1 k + zener clamp ≤6 V documented); OĒ grounded.
- Matrix/gates TS5A23157 ×2, V+ = +3V3 (control VIH 2.0 V < 3.3 V; analog
  ports pass VREF-domain levels ≤5.5 V within abs-max).
- States: POL=0,gates ON=NORMAL; POL=1,gates ON=SWAPPED; TXG off=RX_ONLY;
  both gates off=DISCONNECTED. All controls have 100 k pulldowns ⇒ reset =
  DISCONNECTED.
- Connector pinout: 1=GND, 2=VREF, 3=DUT_TX(=lineA), 4=DUT_RX(=lineB).

## 6. I²C map

PCA9539PW 0x77: bits O0_0..O0_7 = SW1..SW8 LED sinks (reset=input ⇒ OPEN);
I1_0/I1_1 = VBUS_FLT1/2 (SY6280 FLTB, board PU), I1_2/I1_3 reserved.
INA226 ×4: 0x40..0x43. ADS7830: 0x48. Pull-ups 4.7 k ×2.

## 7. Known limitations / OPEN ISSUES

1. **W.FL land pattern** drawn from Hirose catalog fig B numbers (GND centers
   ±1.3 mm, 0.65 wide; SIG centered) — verify against the physical drawing
   before fabrication (no machine-readable drawing available offline).
2. Single simultaneous DUT data connection (interlocked) — hub in Rev.B.
3. No reverse-current blocking on PWR outputs (INA-visible only).
4. 8-bit ADC (ADS7830) — adequate for rail checks, not metrology.
5. ILIM/fuse coordination: SY6280 trip ~1.8 A vs fuse 1.5 A hold — fuse is
   backstop, switch trips first; verify thermals on real loads.
