# DUT Controller Rev.A — Bring-up procedure

Prereqs: bench PSU (current-limited), USB-C cable, multimeter, ST-Link not
needed (native USB DFU/CDC).

1. **Visual / shorts** (no power): VBUS-GND resistance on J1 >100 kΩ;
   PWR1_IN/PWR2_IN to GND >100 kΩ; no solder bridges on U1 module pads.
2. **Control power**: plug PC into J1 only.
   Expect: LED1 lit; TP_+5V = 5.0±0.25 V; TP_+3V3 = 3.3±0.15 V.
   AMS1117 thermal: OK at idle (<40 °C).
3. **Module alive**: `lsusb` shows Espressif USB JTAG/serial (303A:1001).
   `idf.py monitor` prints boot log over CDC. If not: check EN RC (R1/C5),
   measure EN = 3.3 V, TXD0 toggling at reset.
4. **Wi-Fi smoke** (after flash): station connect, TCP server 4242 reachable.
5. **I²C bus scan**: PCA9539@0x77, ADS7830@0x48, INA226@0x40..43 all ACK.
   Missing ACK → check 4.7 k pull-ups, address straps R44/R45 (PCA A0/A1=high).
6. **PhotoMOS dry-run**: `switch.close(1)` → K1 LED sinks ~7 mA; measure
   SW1_A↔SW1_B < 5 Ω closed, >10 MΩ open, both polarities (true dry contact).
7. **VBUS channels**: usb.set_power(1,true) → TP_VBUS1 = 5 V; short test load
   33 Ω → I≈150 mA on INA226@0x40; SY6280 trip test at 2 A load → FLTB path
   (Rev.A: fault visible via INA current spike; no FLTB pin on SOT23-5).
8. **PWR channels**: 12 V into J11, pwr.on(main) → J12 = 12 V; verify soft
   start ramp <5 ms, gate zener clamps VGS ≥ −13 V.
9. **UART matrix**: loopback plug on J5: route normal → TX echo returns;
   swapped → no echo until route=swapped; rx_only → TX line stays Hi-Z
   (scope); off → full isolation, DUT side free to drive.
10. **USB data path**: PC ↔ J2 cable; usb.set_data(1,true) → attached DUT
    enumerates natively; confirm interlock blocks port 2 while port 1 active.
11. **ADC rails**: ADC4 reads +5V_FUSED ≈ 2000 mV (÷2.5), ADC5 ≈ 1320 mV
    (+3V3 ×0.4). Ext inputs with divider: 6 V → ≈2400 mV.

## Test points (TP pads, 1 mm)

| TP | Net | Purpose |
|---|---|---|
| TP1 | GND | reference |
| TP2 | +5V | control rail |
| TP3 | +3V3 | logic rail |
| TP4 | +5V_FUSED | switched DUT feed |
| TP5 | VBUS1_OUT | port 1 power |
| TP6 | VBUS2_OUT | port 2 |
| TP7 | PWR1_OUT | channel 1 |
| TP8 | PWR2_OUT | channel 2 |
| TP9 | I2C_SDA | bus |
| TP10 | I2C_SCL | bus |
| TP11 | U1_TXGATED | UART1 to DUT |
| TP12 | U1_RXGATED | UART1 from DUT |
| TP13 | EN_RC | module reset |
| TP14 | BOOT_IO0 | strap |

(TP footprints are placed during silkscreen gate; nets above are final.)
