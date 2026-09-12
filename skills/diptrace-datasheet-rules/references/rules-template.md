# Component rules template

Copy into the design project's `rules/<MPN>.md`. Replace placeholders with actual
evidence; leave unavailable results unresolved. This template makes no PASS claims.

## Identity and sources

Manufacturer / exact orderable MPN / variant: <identity>
Package code and revision: <identity>
Official datasheet / package drawing / layout guide / errata: <URLs and local paths>
Revision history checked: <date, revisions and relevant changes>
Source artifact SHA-256: <64 lowercase hexadecimal characters per file>

## Applicable constraints

| ID | Requirement or recommendation | Value/unit or topology | Pins/nets/parts | Source revision/page | Verification | Status |
|---|---|---|---|---|---|---|
| <ID> | <power, sequencing, decoupling, protection, clocks, straps or layout> | <evidenced constraint> | <scope> | <citation> | <method> | UNRESOLVED |

## Package and mapping

Record body/pad/hole dimensions and tolerances, pitch, pin-1/view orientation,
exposed pads, repeated physical contacts, mask/paste recommendations, and every
pin-to-pad mapping. Bind comparisons to the actual library file/hash and validator
result. Show derivations separately from manufacturer-specified dimensions.

## Retired advice and intentional deviations

| Source requirement | Superseding source or intentional deviation | Consequence | Disposition |
|---|---|---|---|
| <citation> | <change> | <electrical/manufacturing effect> | <actual decision or unresolved> |

## Verification evidence

Footprint/pin-map check: <result, tool, path/hash or NOT_RUN>
Layout comparison: <result and source figure or NOT_RUN>
Native roundtrip: <actual result and evidence or NOT_RUN>
Remaining blockers and dependent stages: <list or none>
