# How to reduce the current loop of a buck converter

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
