# DUT Controller Rev.A component provenance

Lookup date: 2026-08-26. Order: exact installed DipTrace MPN, then exact LCSC/EasyEDA MPN, then official-manufacturer evidence. A search result whose payload title differs from the requested MPN is rejected.

## Exact generic-part identities

| Class/value | Manufacturer | MPN | LCSC | Package evidence |
|---|---|---|---|---|
| R0603 100R | Yageo | RC0603FR-07100RL | C105588 | R0603, 2 pins / 2 pads |
| R0603 390R | Yageo | RC0603FR-07390RL | C114620 | R0603, 2 / 2 |
| R0603 470R | Yageo | RC0603FR-07470RL | C114669 | R0603, 2 / 2 |
| R0603 1k | Yageo | RC0603FR-071KL | C22548 | R0603, 2 / 2 |
| R0603 3.9k | Yageo | RC0603FR-073K9L | C114616 | R0603, 2 / 2 |
| R0603 4.7k | Yageo | RC0603FR-074K7L | C99782 | R0603, 2 / 2 |
| R0603 5.1k | Yageo | RC0603FR-075K1L | C105580 | R0603, 2 / 2 |
| R0603 10k | Yageo | RC0603FR-0710KL | C98220 | R0603, 2 / 2 |
| R0603 15k | Yageo | RC0603FR-0715KL | C114661 | R0603, 2 / 2 |
| R0603 100k | Yageo | RC0603FR-07100KL | C14675 | R0603, 2 / 2 |
| C0603 1nF | Murata | GRM188R71H102KA01D | C71653 | C0603, 2 / 2 |
| C0603 100nF | Murata | GRM188R71H104KA93D | C77055 | C0603, 2 / 2 |
| C0603 1uF | Murata | GRM188R71A105KA61D | C97888 | C0603, 2 / 2 |
| C0805 1uF | Murata | GRM21BR71A105KA01L | C97917 | C0805, 2 / 2 |
| C0805 10uF | Murata | GRM21BR61A106KE19L | C77073 | C0805, 2 / 2 |
| C0805 22uF | Murata | GRM21BR61A226ME44L | C441864 | C0805, 2 / 2 |
| 2x5 2.54 mm | Samtec | TSW-105-07-G-D | C7074471 | Combined EasyEDA symbol/footprint, 10 / 10 |
| 1x4 2.54 mm | Samtec | TSW-104-07-G-S | C3335156 | LCSC has no combined EasyEDA document; official Samtec family geometry + existing 1x4 P2.54 TH footprint |
| 2x8 2.54 mm | Samtec | TSW-108-07-T-D | C3335249 | LCSC has no EasyEDA document; official Samtec family geometry + existing 2x8 P2.54 TH footprint |

Downloaded catalog JSON and datasheet PDFs are kept under `vendor/`. The three generic header footprints remain blocked from any future PCB synchronization until their exact land-pattern dimensions are mechanically compared with the official Samtec drawing; this schematic-only build does not alter the PCB.

## Rejected evidence

- Request `TSW-108-07-G-D` previously resolved to C5994391, whose EasyEDA title is `TSW-108-07-G-S-LL` and whose pin count is 8, not 16. It is rejected and not used.
- The sourcing helper now validates exact payload-title equality before writing a searched MPN. `tests/test_component_sourcing_skill.py` preserves this failure case.
- The LCSC converter had double scaling of symbol-pin coordinates. `scripts/lcsc_library.py` now scales once; the ESP32 regression test checks pin 1 at X = -8.89 mm, length = 2.54 mm, orientation = 0°.

## Sources

- LCSC product pages and their downloaded EasyEDA payloads are identified by the C-codes above.
- Official Samtec family pages: `https://www.samtec.com/products/tsw-104-07-g-s`, `https://www.samtec.com/products/tsw-105-07-g-d`, `https://www.samtec.com/products/tsw-108-07-t-d`.
