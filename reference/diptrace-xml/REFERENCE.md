# DipTrace XML Implementation Reference

This is a coding-agent guide to the extracted public
[specification inventory](spec_inventory.json) and measured
[format coverage](../../docs/FORMAT_COVERAGE.md). Missing or unknown entries remain unknown; this
guide does not supply facts that the cited specifications do not state.

## Reproducible inventory

The PDFs are intentionally not committed. The repository instead contains canonical per-page
text bundles in [`extracted_text/`](extracted_text/), produced with the pinned
`pypdf==6.14.2`. Every bundle records the source PDF URL, SHA-256, byte size, page count, and
extraction engine; `spec_inventory.json` records the bundle SHA-256 as well.

CI performs the offline check:

```bash
python scripts/extract_spec_inventory.py \
  --sources reference/diptrace-xml/extracted_text \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
```

A maintainer who has downloaded the three source PDFs can independently refresh and compare the
committed intermediate:

```bash
python scripts/extract_spec_inventory.py \
  --sources reference/diptrace-xml/sources \
  --write-extracted-text reference/diptrace-xml/extracted_text \
  --out reference/diptrace-xml/spec_inventory.json
```

Only literal XML examples introduce elements. Element text values are stored separately from XML
attributes; a prose mention such as “see `<Groups>` section” cannot re-anchor the extractor.

## Exchange lifecycle

DipTrace exports `plugin_exchange.xml`, launches the standalone executable with the exchange path
as `argv[1]`, waits for it to exit, and imports that same path. PCB/Schematic data roots use
hyphenated `DipTrace-PCB` / `DipTrace-Schematic`; plug-in settings use a separate underscore-based
Type namespace.

`ImpMode=All` replaces lists. `Edit` matches top-level objects by existing `Id`; new objects should
omit `Id`. With PCB/Schematic Selected filtering, only incoming `Selected="Y"` objects are
processed. Nested ID-less lists (`Traces`, net/bus `Wires`, point lists) are replaced wholesale
when present. `Enabled="N"` is an import delete flag on objects that support it.

## Shared serialization

- Root `Units`: `mm`, `inch`, `mil`.
- Canonical decimal separator: dot.
- `Shape/@Angle` for text and pictures: radians CCW.
- `Component/@Angle`: assumed to be radians by the current code, but unverified; see
  [OPEN_QUESTIONS.md Q1](../../docs/OPEN_QUESTIONS.md#q1-is-componentangle-in-radians-or-degrees).
- Discrete `Orientation`: `0`, `90`, `180`, `270` where documented.
- `Model3D/Rotate`: degrees.
- Preserve unknown XML and existing IDs.
- Segment attributes belong to the segment end/second point.
- External file references can contain both `Path` and `Var`; preserve both.

## Pattern / pad rules

`PadStyle Type` is `Surface|Through`. Through drills use `HoleType=Round|Obround`, `Hole`, and
`HoleH` for an obround height.

A fiducial is special:

```xml
<PadStyle Name="FID" Type="Surface" Hole="1.2">
  <MainStack Shape="Fiducial" Width="0.8"/>
</PadStyle>
```

`MainStack/Height` is omitted; `Width` is copper diameter. `PadStyle/Hole` means fiducial keepout
diameter rather than drill geometry.

The public specification inventory records these MainStack shapes: `Ellipse`, `Obround`,
`Rectangle`, `Polygon`, `D-shape`, and `Fiducial`.

Mask modes: `Common`, `Open`, `Tented`, `By Paste`. Paste modes: `Common`, `Solder`, `No Solder`,
`Segments`. Common is represented by omission. `CustomSwell=-1000` and `CustomShrink=-1000` are
unset. Segmented paste uses `TopSegments`/`BotSegments` with rectangle `Item` entries.

Pattern layers are individual textual literals such as `Top Silk`, `Bottom Silk`, `Top Assy`,
`Bottom Assy`, `Top Mask`, `Bottom Mask`, `Top Paste`, `Bottom Paste`, `Top Courtyard`,
`Bottom Courtyard`, `Top Outline`, and `Bottom Outline`. Do not invent `Top/Bottom ...` names.

`Model3D/Filename` is a container with `Path`/`Var`; `Rotate` is in degrees.

## Component Library aliases and references

- Canonical attached footprint attribute: `Pattern/@Style`; reader may accept legacy
  `PatternType`.
- Canonical pin-to-pad numeric reference: `Pin/@PadId`; reader may accept legacy `PadIndex`.
- `PadNumber` is the footprint pad name paired with that numeric reference.
- `InternalConnections/IntCon @X/@Y` are pad Id references, not coordinates. Never delete or
  renumber a referenced pad without updating these references.

## PCB connectivity

Component pad `NetId` is the authoritative net membership; the net's `<Pads>` list is a mirror.
Trace connectivity is declared with `Connected1/2`, `Object1/2`, `SubObject1/2`, and `Point1/2`.
A trace that merely touches a pad geometrically is not enough. Trace point `Lay` and CopperPour
`Lay` are numeric copper-layer references. `ViaStyle` is a style reference; concrete via geometry
is rebuilt from the style.

## Schematic connectivity

A Part pin carries `NetId`; a Net `<Pins>` list references Part Id plus positional pin index.
Wire endpoints use the documented endpoint tuple. `Dir` on the segment end point is `-1` unset,
`0` horizontal, `1` vertical. Net/bus wire containers are replacement lists when supplied.

## Trust

These rules prove only that the implementation agrees with the supplied documentation. They do
not prove that a generated file opens, saves, or re-exports correctly in a particular DipTrace
build. Real 5.3 round-trip fixtures remain the writer gate.
