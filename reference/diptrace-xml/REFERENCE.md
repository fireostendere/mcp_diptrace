# DipTrace XML Implementation Reference

This is a coding-agent guide to the extracted public
[specification inventory](spec_inventory.json) and measured
[format coverage](../../docs/FORMAT_COVERAGE.md). Missing or unknown entries remain unknown; this
guide does not supply facts that the cited specifications do not state.

Evidence labels used below:

- **Public specification** — stated by one of the three reproducible sources in
  [`extracted_text/`](extracted_text/);
- **Observed compatibility** — accepted by the current reader or seen in a fixture/run, but not a
  standalone format contract;
- **Open question / safety model** — deliberately conservative behavior pending the named
  experiment in [`OPEN_QUESTIONS.md`](../../docs/OPEN_QUESTIONS.md).

## Reproducible inventory

The PDFs are intentionally not committed. The repository instead contains canonical per-page
text bundles in [`extracted_text/`](extracted_text/), produced with the pinned
`pypdf==6.14.2`. Every bundle records the source PDF URL, SHA-256, byte size, page count, and
extraction engine; `spec_inventory.json` records the bundle SHA-256 as well.

These extracted bundles and the generated inventory are retained as engineering
working inputs, but their redistribution status is not treated as Apache-2.0.
The release build policy excludes them from wheels, source distributions, and
release assets until a human confirms a redistribution basis. An operator with
legitimate source documents can regenerate them locally with the command below.

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

**Public specification:** Pages 3–8 of
[`DipTrace_Plugins.pages.json`](extracted_text/DipTrace_Plugins.pages.json) state that DipTrace
creates `plugin_exchange.xml`, passes its path to the executable, then reads the overwritten file.
They define `ImpMode`/`ExpMode` and object filters. For PCB/Schematic `Selected` import filtering,
incoming `Selected="Y"` is explicitly considered. For the library editors, the same source
documents the named `Library All`, `Library Add`, `Library Insert`, `Component All`, `Part All`,
and `Edit` modes and their high-level overwrite/add behavior.

**Public specification:** PCB/Schematic data roots use hyphenated `DipTrace-PCB` /
`DipTrace-Schematic`; plug-in settings use a separate underscore-based `Type` namespace.

**Open question / safety model:** The public plug-in source says that `ImpMode=All` imports all
regardless of object filters; it does not define generic list replacement, top-level `Id` matching,
the treatment of omitted objects, or wholesale replacement of nested ID-less containers. Current
writers conservatively treat owned `Traces`, net/bus `Wires`, and point containers as replacement
boundaries and require explicit destructive intent. This is an MCP safety rule, not a claim about
DipTrace's complete import algorithm. See
[Q2](../../docs/OPEN_QUESTIONS.md#q2-which-objects-can-an-impmodeall-apply-delete-because-the-exchange-export-omitted-them)
and
[Q4](../../docs/OPEN_QUESTIONS.md#q4-does-diptrace-address-top-level-list-entries-by-id-or-by-position).

**Public specification with operation-specific scope:** Some PCB/Schematic records document
`Enabled="N"` as a removed/non-existing object state. Do not generalize that attribute into a
universal import-delete flag for every element.

## Shared serialization

- **Public specification:** root `Units` values are `mm`, `inch`, `mil`.
- **Writer policy:** numeric XML written by MCP uses a dot decimal separator.
- **Public specification:** `Shape/@Angle` for text and pictures is radians CCW.
- **Open question / safety model:** `Component/@Angle` is assumed to be radians by the current
  code, but unverified; see
  [OPEN_QUESTIONS.md Q1](../../docs/OPEN_QUESTIONS.md#q1-is-componentangle-in-radians-or-degrees).
- **Public specification:** discrete `Orientation` values are `0`, `90`, `180`, `270` where
  documented.
- **Observed compatibility:** the reader exposes literal `Model3D/Rotate` attributes without unit
  conversion; the standalone library format source needed to establish their unit is not in the
  reproducible inventory.
- **Writer policy:** raw-preserving and targeted patch paths preserve unknown XML and existing IDs
  outside the operation-owned region. An operation that owns a container may replace that
  container only at its documented boundary, with the operation-specific disclosure, destructive
  opt-in, or refusal required by its contract.
- **Public specification:** segment attributes belong to the segment end/second point.
- **Public specification and writer policy:** documented external file references can contain
  both `Path` and `Var`; preserve both.

## Pattern / pad rules

**Observed compatibility:** The current reader recognizes `PadStyle Type` values
`Surface|Through`. It recognizes through-drill fields `HoleType=Round|Obround`, `Hole`, and `HoleH`.
These names occur in synthetic fixtures and observed inputs; the committed inventory does not
contain standalone `PadStyle` or `MainStack` element definitions. They must not be used as a
standalone library writer contract.

The reader also recognizes this fiducial form:

```xml
<PadStyle Name="FID" Type="Surface" Hole="1.2">
  <MainStack Shape="Fiducial" Width="0.8"/>
</PadStyle>
```

The interpretations “omit `MainStack/Height`,” “`Width` is copper diameter,” and
“`PadStyle/Hole` is fiducial keepout diameter” remain **open standalone-library semantics**. They
require the controlled Q11 editor experiment before a writer may depend on them.

**Observed compatibility:** The reader recognizes these `MainStack` shape literals: `Ellipse`,
`Obround`, `Rectangle`, `Polygon`, `D-shape`, and `Fiducial`. Contrary to an earlier version of this
guide, the public inventory does not record a `MainStack` element or this enum.

**Public specification:** The embedded PCB pattern/pad section documents mask modes `Common`,
`Open`, `Tented`, `By Paste`; paste modes `Common`, `Solder`, `No Solder`, `Segments`; and
`TopSegments`/`BotSegments` rectangle entries. It does not say that `Common` must be represented by
omission or define a `-1000` sentinel. **Observed compatibility:** the reader preserves explicit
mode attributes, tolerates absent ones, and treats `CustomSwell=-1000` or `CustomShrink=-1000` as
unset. That is compatibility policy, not a standalone writer convention.

**Public specification:** The embedded PCB shape layer enum contains textual literals such as
`Top Silk`, `Bottom Silk`, `Top Assy`, `Bottom Assy`, `Top Mask`, `Bottom Mask`, `Top Paste`,
`Bottom Paste`, `Top Courtyard`, `Bottom Courtyard`, `Top Outline`, and `Bottom Outline`. Do not
invent `Top/Bottom ...` names.

**Observed compatibility:** The standalone-library reader normalizes
`Model3D/Filename/Path` and `Model3D/Filename/Var` and exposes `Rotate` attributes literally;
other raw XML is preserved. Keep this reader behavior separate from filename-shape and angle-unit
writer evidence.

## Component Library aliases and references

**Observed compatibility:** The reader prefers `Pattern/@Style` and accepts `PatternType`; it
prefers `Pin/@PadId` and accepts `PadIndex`; it reads `PadNumber` as the paired footprint pad name.
Those preferences describe current compatibility handling, not proven canonical standalone
library spellings.

**Public specification:** In the embedded PCB component-pattern section,
`InternalConnections/IntCon/PadId/Item` values are pad IDs, and each nested `Ratline/@X` and
`Ratline/@Y` is also a pad ID rather than a coordinate. This corrects the earlier claim that `X`
and `Y` were attributes of `IntCon` itself. Safe mutation must preserve those references. Whether
standalone editors use identical identity and renumbering rules remains part of
[Q11](../../docs/OPEN_QUESTIONS.md#q11-what-are-the-standalone-component-and-pattern-editor-xml-mutation-semantics).

## PCB connectivity

Component pad `NetId` is the authoritative net membership; the net's `<Pads>` list is a mirror.
Trace connectivity is declared with `Connected1/2`, `Object1/2`, `SubObject1/2`, and `Point1/2`.
A trace that merely touches a pad geometrically is not enough. Trace point `Lay` and CopperPour
`Lay` are numeric copper-layer references. `ViaStyle` is a style reference; concrete via geometry
is rebuilt from the style.

## Schematic connectivity

A Part pin carries `NetId`; a Net `<Pins>` list references Part Id plus positional pin index.
Wire endpoints use the documented endpoint tuple. `Dir` on the segment end point is `-1` unset,
`0` horizontal, `1` vertical. Current MCP writers own and replace a targeted net/bus wire
container when explicitly asked to rewrite it. The public format source documents the container
shape and point order, but not a generic plug-in-import replacement rule.

## Trust

These rules prove only that the implementation agrees with the supplied documentation. They do
not prove that a generated file opens, saves, or re-exports correctly in a particular DipTrace
build. Real 5.3 round-trip fixtures remain the writer gate.
