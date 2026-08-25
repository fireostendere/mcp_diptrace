#!/usr/bin/env python3
"""Generate committed test fixtures (no network needed at test time).

Usage: uv pip install fpdf2 && python scripts/make_fixtures.py
Outputs are written into tests/fixtures/ and committed to the repo.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"

DATASHEET_PAGES = [
    # page 1
    [
        ("title", "TPS62130 3-A Step-Down Converter with DCS-Control (TEST FIXTURE)"),
        ("para", "Texas Instruments SLVS973F REV C TestFixture Edition"),
        ("h", "Description"),
        ("para", "The TPS62130 is a high efficiency synchronous step-down DC-DC converter "
                 "with DCS-Control topology. The device operates with input voltages from "
                 "3 V to 17 V and can deliver up to 3 A of continuous output current. "
                 "This document is an authored test fixture, not the real TI datasheet."),
        ("h", "Features"),
        ("para", "D CS-Control topology for fast transient response. Fixed 2.4 MHz switching "
                 "frequency. Power good output. Adjustable output voltage from 0.9 V to 6 V."),
    ],
    # page 2
    [
        ("h", "Pin Functions"),
        ("para", "PIN 1 PG: Power good indicator, open drain output. Connect a 100 kOhm pullup "
                 "resistor to VOUT."),
        ("para", "PIN 2 VIN: Input supply pin. A 22 uF input capacitor must be placed close to "
                 "VIN and GND pins."),
        ("para", "PIN 3 GND: Ground pin."),
        ("para", "PIN 4 EN: Enable pin. Above 1.2 V the device is enabled."),
        ("para", "PIN 5 SS/TR: Soft start and tracking pin."),
        ("para", "PIN 6 VOS: Output voltage sense input. Connect to the regulated point."),
        ("para", "PIN 7 SW: Switch node. Connect the inductor between SW and VOUT."),
        ("para", "PowerPAD: The thermal pad must be soldered to the PCB ground plane."),
    ],
    # page 3
    [
        ("h", "Absolute Maximum Ratings"),
        ("para", "VIN voltage range minus 0.3 V to 20 V. SW pin voltage minus 0.5 V to 20 V. "
                 "EN pin voltage range minus 0.3 V to 20 V. Operating junction temperature "
                 "range minus 40 C to 125 C."),
        ("h", "Electrical Characteristics"),
        ("para", "Minimum input voltage 3 V, maximum input voltage 17 V. Output current 3 A. "
                 "Quiescent current 25 uA typical at light load. Switching frequency 2.4 MHz "
                 "typical. Line regulation 0.5 percent per V. Load regulation 0.3 percent per A. "
                 "RDS on high side 38 mOhm typical."),
    ],
    # page 4
    [
        ("h", "Application Information"),
        ("para", "The TPS62130 requires a 22 uF ceramic input capacitor placed as close as "
                 "possible between VIN and GND. For a 3.3 V output from a 12 V rail use a "
                 "2.2 uH inductor with saturation current above 4.5 A. Output capacitance of "
                 "2 x 22 uF ceramic capacitors gives good transient response."),
        ("para", "The feedback divider connects from VOUT through 100 kOhm to the FB pin and "
                 "18.2 kOhm from FB to AGND. Place the divider close to the FB pin to keep the "
                 "feedback trace short."),
    ],
    # page 5
    [
        ("h", "Layout Guidelines"),
        ("para", "Keep the input capacitor as close as possible to the VIN pin to minimize the "
                 "hot loop area. A small current loop reduces electromagnetic emission. Route "
                 "the switch node SW with short wide traces. Do not route sensitive analog "
                 "signals under the inductor."),
        ("para", "Solder the PowerPAD to a solid ground plane. Use at least nine 0.3 mm vias "
                 "in the thermal pad to connect to the bottom ground plane. This lowers "
                 "junction temperature and improves EMI performance."),
        ("para", "Place the feedback divider away from the switch node. Star ground the AGND "
                 "pin to avoid ground bounce coupling into the control loop."),
    ],
    # page 6
    [
        ("h", "Thermal Information"),
        ("para", "Junction to ambient thermal resistance R theta JA is 36.2 C/W on the standard "
                 "two layer board and 27.4 C/W on a four layer board with solid ground planes. "
                 "Maximum power dissipation depends on ambient temperature."),
        ("h", "Revision History"),
        ("para", "Rev C corrected the layout recommendation figure. Rev B updated electrical "
                 "characteristics table. Rev A initial release."),
    ],
]


def make_pdf(out: Path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    for page in DATASHEET_PAGES:
        pdf.add_page()
        for kind, text in page:
            if kind == "title":
                pdf.set_font("Helvetica", "B", 15)
                pdf.multi_cell(0, 8, text)
                pdf.ln(2)
            elif kind == "h":
                pdf.ln(1)
                pdf.set_font("Helvetica", "B", 12)
                pdf.multi_cell(0, 7, text)
                pdf.ln(1)
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 5, text)
                pdf.ln(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    print(f"wrote {out}")


APPNOTE_MD = """# How to reduce the current loop of a buck converter

Author: kb-rag fixture · Tier example: application note (community-authored)

## Why the hot loop matters

The switching current loop of a step-down converter is formed by the input
capacitor, the high-side switch, the low-side switch and the ground reference.
During every switching cycle the full square-wave current flows inside this
loop, so its area directly defines radiated EMI and input ripple voltage.
To reduce the current loop of an impulse converter, shrink the physical area
enclosed by these components.

## Practical rules

1. Place the input ceramic capacitor (for example 22 uF X7R) as close as the
   package allows between VIN and GND pins. Every millimetre of trace adds
   parasitic inductance that rings at the switching edge.
2. Use a solid, unbroken ground plane on the layer adjacent to the component
   layer. Return current flows directly beneath the forward path.
3. Keep the SW node copper short but wide enough for the RMS current.
4. Put a small RC snubber across the switch node when ringing persists after
   layout optimization; start with 10 Ohm and 1 nF and tune on the bench.
5. Prefer packages with exposed thermal pad and flood several vias to ground;
   this both cools the die and shorts the return path.

## Measuring the result

Compare conducted emissions before and after with a LISN, or probe the switch
node with a short ground spring instead of an alligator clip to see the real
ringing. A smaller hot loop shows up as lower peak ring amplitude and fewer
harmonics above 30 MHz.
"""


def main():
    make_pdf(FIX / "datasheets" / "tps62130_datasheet_fixture.pdf")
    out_md = FIX / "appnotes" / "buck_current_loop_appnote_fixture.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(APPNOTE_MD, encoding="utf-8")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
