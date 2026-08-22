# Component provenance

Lookup order was DipTrace exact match, then LCSC exact MPN, then custom only if
both were absent. No component in this schematic was drawn from memory.

| RefDes | Exact part | Source | Attached pattern |
|---|---|---|---|
| U1 | ATTINY85-20SU | DipTrace `builtin-component:1905240492:1486` | `SOIC8P127_524X798X216L68X41N` |
| U2 | CP2102-GM | DipTrace `builtin-component:1681702205:8` | `PQFN29P50_500X500X100L45X24T315N` |
| J1 | 10118194-0001LF | DipTrace `builtin-component:457793591:83` | `AMPHENOL_10118194-0001LF` |
| J2 | HDR-2x3 | DipTrace `builtin-component:1525896499:92` | `HDR-2x3` |
| J3 | HDR-2x4 | DipTrace `builtin-component:1525896499:93` | `HDR-2x4` |
| U3 | TPS63802DLAR | LCSC C2845237; no exact DipTrace match | `VSON-10_L3.0-W2.0-P0.50-TL` |
| L1 | XFL4015-471MEC | LCSC C18221164; no exact DipTrace match | LCSC catalog footprint |
| R1 | RC0402FR-07511KL, 511 kOhm | LCSC C163461; no exact DipTrace match | `R0402` |
| R2 | 0402WGF9102TCE, 91 kOhm | LCSC C4147; no exact DipTrace match | `R0402` |
| R3 | 0402WGF1003TCE, 100 kOhm | DipTrace JLCPCB Basic library | `RESC100X50X40L25N` |
| R4 | 0402WGF4702TCE, 47 kOhm | DipTrace JLCPCB Basic library | `RESC100X50X40L25N` |
| R5 | 0402WGF2402TCE, 24 kOhm | DipTrace JLCPCB Basic library | `RESC100X50X40L25N` |
| R6 | 0402WGF1002TCE, 10 kOhm | DipTrace chip-resistor library | `RESC100X50X40L25N_AD1` |
| C1 | CL10A106KP8NNNC, 10 uF | DipTrace ceramic-capacitor library | `CAPC160X80X90L30N` |
| C2 | CL21A226MAQNNNE, 22 uF | DipTrace ceramic-capacitor library | `CAPC200X125X140L50N` |
| C3 | CL05A105KA5NQNC, 1 uF | DipTrace ceramic-capacitor library | `CAPC100X50X55L25N_AD4` |
| C4, C5, C6 | 0402B104K160NT, 100 nF | DipTrace ceramic-capacitor library | `CAPC100X50X55L25N_AD3` |
| PSG* | GND net port | DipTrace `builtin-component:1244111437:19` | none; schematic symbol only |
| PWR* | +3V3 / VBUS power net port | DipTrace installed Net Ports library, indices 4 / 14 | none; schematic symbol only |
| NPI*, NPO* | named signal net ports | DipTrace installed Net Ports library, `Port_In*` / `Port_Out*` | none; schematic symbol only |

The four LCSC JSON files in `vendor/` are the saved catalog inputs. Their
`.elixml` derivatives passed the local component-library and pin-to-pad
validators and a native hidden DipTrace Component Editor open/save check.
