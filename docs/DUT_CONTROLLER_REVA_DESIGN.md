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
| J7 | HDR-2x8 | SW1..SW8 dry contacts (row A / row B) |
| J9/J10 | HDR-2x5 | AUX1/AUX2 |
| J11..J14 | TB 1x2 5.08 | PWR1_IN, PWR1_OUT, PWR2_IN, PWR2_OUT |
| J15 | HDR-2x5 | DEBUG: console UART0, EN/RST, BOOT, JTAG |
| ANT | on-module W.FL/MHF III | module carries its own connector; baseboard needs keepout only |

### USB data path decision (documented deviation)

The UPLINK pair is switched by two TS3USB221 2:1 muxes to USB1/USB2. The PC
sees the DUT **natively** (no hub, no proxy). Rev.A limitation: only ONE port
may be data-connected at a time; firmware interlock auto-disconnects the other.
Simultaneous dual enumeration = Rev.B (add SL2.1A-class hub). VBUS is fully
independent per port.

Fail-safe: TS3USB221 OĒ has 100 k pull-ups → reset/crash/flashing ⇒ both muxes
disabled ⇒ DUT data lines float (DUT keeps working standalone).

## 2. Power architecture

- CONTROL VBUS 5 V → polyfuse F1 1.5 A → `+5V` → AMS1117-3.3 → `+3V3`
  (22 µF + 100 nF per side; AMS supply ≥0.5 A per module datasheet Table 6-2).
- `+3V3` feeds module (WiFi TX peak 355 mA), logic, PhotoMOS LEDs, ESD clamps.
- DUT VBUS n: `+5V_FUSED` (F4/F5 1.5 A) → shunt 20 mΩ → INA226 → SY6280AAC
  (ILIM≈1.8 A via RSET 3.9 k) → USB-A VBUS + SMAJ5.0A TVS. Internal discharge
  resistor of SY6280 pulls output to GND at OFF.
- PWR n (3.3–24 V): terminal IN → SMBJ26A TVS → BSMD2920-200-24V fuse →
  AO3401A P-FET high-side (100 k GS pulldown = OFF default; MMBT3904 driven
  from GPIO turns ON; BZT52C12S clamps VGS) → shunt 20 mΩ → INA226 → OUT.
- Reverse current DUT→PSU is NOT blocked (P-FET body diode); INA226 reports
  negative current (agent-detectable). True blocking = Rev.B.
- Current sense: INA226 ×4 addresses 0x40..0x43 (USB1/USB2/PWR1/PWR2),
  ±81.92 mV FS / 20 mΩ = ±4.096 A, LSB 0.125 mA; VBUS pin measures DUT side.
- ADC: ADS7830IPWR @0x48 (pin-compatible ADS7828, **8-bit** — enough for
  0/1.8/3.3/5 V discrimination; documented trade-off). CH0..CH3 external:
  divider 15k/10k (Zin 25 k, ×0.4 → 6 V→2.4 V vs internal 2.5 V ref) +
  BAT54S clamp + 1 nF. CH4=+5V_FUSED, CH5=+3V3 monitors; CH6/CH7 tied GND.

## 3. GPIO map (final; pads per datasheet Table 3-1)

Reserved straps: IO0(BOOT btn), IO3 NC, IO45 NC, IO46 NC. Native USB: IO19/20.
N8 variant ⇒ IO35/36/37 free.

| GPIO | Pad | Function | Reset-safe mechanism |
|---|---|---|---|
| IO1 | 5 | UART1_TX data | shifter DIR fixed; gate default OFF |
| IO8 | 12 | UART1_RX data | Hi-Z input |
| IO2 | 6 | I2C_SDA | ext 4.7 k PU |
| IO4 | 8 | I2C_SCL | ext 4.7 k PU |
| IO5/6/7 | 9/10/11 | UART1 POL/TXG/RXG | 100 k PD ⇒ DISCONNECTED |
| IO13/14/15 | 17/18/19 | UART2 POL/TXG/RXG | 100 k PD ⇒ DISCONNECTED |
| IO9/10 | 13/14 | USB1 OĒ/S | OĒ PU100k=off; S PD |
| IO11/12 | 15/16 | USB2 OĒ/S | same |
| IO16 | 20 | VBUS1_EN | SY6280 EN PD100k=off |
| IO17 | 21 | VBUS2_EN | « |
| IO18 | 22 | PWR1_EN | gate PD100k=off |
| IO21 | 25 | PWR2_EN | « |
| IO26 | 26 | UART2_TX data | gate OFF by default |
| IO35 | 31 | UART2_RX data | Hi-Z input |
| IO33/34/36/37 | 28/29/32/33 | AUX1.IO1..4 | 100 Ω series + BAT54S clamp |
| IO38/47/48/42 | 34/27/30/38 | AUX2.IO1..4 (IO42 shares JTAG hdr) | « |
| IO39..41 | 35/36/37 | DEBUG header (MTCK/MTDO/MTDI) | Hi-Z |
| IO43/44 | 39/40 | U0TXD/U0RXD console → J15 | UART0 |

PCA9539 (0x77, A0=A1=high): O0.0..O0.7 → SW1..SW8 PhotoMOS LEDs (reset=input
⇒ OPEN); I1.7 → LED_ACT via 390 Ω. INT# NC.

DEBUG header J15: 1:+3V3 2:U0TX 3:U0RX 4:EN 5:GND 6:BOOT(IO0) 7:IO39 8:IO40
9:IO41 10:GND.

## 4. Fail-safe summary

| Subsystem | Reset state | Mechanism |
|---|---|---|
| SW1..8 | OPEN | expander registers reset to input |
| PWR1/2 | OFF | 100 k GS pulldown on P-FET |
| VBUS1/2 | OFF | SY6280 EN PD + internal discharge |
| USB data | DISCONNECTED | OĒ pull-up |
| UART routes | DISCONNECTED | TS5A23157 IN PDs route into 10 k sinks |
| AUX | Hi-Z | ESP32 reset Hi-Z + series 100 R |
| Module EN | RC power-on | 10 k PU + 1 µF |

## 5. UART port circuit (per port)

```
ESP TX ─LVC1T45(DIR=L→fixed A>B, VCCB=VREF)─TX_V─[gate SPDT]─┬NO→[POL COM]
                                                             └NC→10k sink
ESP RX ←LVC1T45(DIR=GND)──────────────RX_V←[gate SPDT]───────┬NO→[POL COM]
                                                             └NC→10k sink
POL ch1: NO=lineA drv / NC=lineB drv ; ch2: NO=lineB sns / NC=lineA sns
```
States: POL=0,gates on=NORMAL; POL=1,on=SWAPPED; TXG off=RX_ONLY; both off=
DISCONNECTED. All control nets have 100 k pulldowns. Matrix/gates TS5A23157,
V+=+3V3 (analog ports carry VREF-domain ≤5.5 V within abs-max; control VIH
2.0 V < 3.3 V). VREF pin: series 1 k + BZT52C5V6S clamp + 100 k PD ⇒ undervolt
shifters Hi-Z when DUT absent.

Connector: 1=GND, 2=VREF, 3=DUT_TX(lineA), 4=DUT_RX(lineB).

## 6. I²C map

0x77 PCA9539 · 0x48 ADS7830 · 0x40/41/42/43 INA226. Pull-ups 4.7 k ×2.

## 7. Known limitations / OPEN ISSUES

1. **W.FL land pattern** on module side is vendor-defined; baseboard has no RF
   path — issue closed for Rev.A (was: custom receptacle removed).
2. Single simultaneous DUT data connection (interlocked) — hub in Rev.B.
3. No reverse-current blocking on PWR outputs (INA-visible only).
4. 8-bit ADC — adequate for rail checks, not metrology.
5. ILIM/fuse coordination: switch trips ≈1.8 A before 1.5 A-hold fuse heats.
6. USB2 pair not length-matched with USB1 corridor (asymmetric lanes);
   acceptable for FS/LS-heavy DUT bring-up, revisit for HS compliance.
