# <MPN> — design rules for placement/routing

> Copy this template to `rules/<MPN>.md` and fill it from the official
> datasheet BEFORE placing the part. The PCB build gates require it.

## Identity

| Field | Value |
|---|---|
| MPN | `CHANGEME` |
| LCSC | `Cxxxxxx` |
| Package | `CHANGEME (e.g. VSON-10 3×2, pitch 0.5)` |
| Datasheet | vendor URL + revision checked |
| Revision history checked | Yes — list any retired layout advice |

## Power & decoupling (section + page)

- Required decoupling: ...
- Input/output cap placement: ...

## Layout constraints

- Critical placement: ...
- Keepout / courtyard: ...
- Routing notes: ...

## Pin-specific rules

- Boot/strap pins: ...
- RF/analog keepout: ...

## Retired advice (explicitly rejected)

| Old advice | Why rejected | Superseded by |
|---|---|---|
| e.g. "split AGND/PGND planes" | TI SLVSEU9D rev B→C deleted it | "single power-ground node, join close to GND pin" |

## Evidence

- LCSC JSON: `vendor/Cxxxxxx.json` (sha256: `...`)
- Footprint validated: `scripts/build_*.py::_validate_*` assert passed
- Native roundtrip: `ok: true`

## Intentional deviations (if any)

| Deviation | Consequence | Accepted |
|---|---|---|
| e.g. "pour clearance 0.22 vs rule 0.13" | native raster needs margin | Yes |

