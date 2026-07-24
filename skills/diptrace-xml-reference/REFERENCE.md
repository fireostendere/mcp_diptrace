# DipTrace XML Implementation Reference

This is a compact coding-agent reference distilled from the two user-supplied documentation
archives. The machine-readable source of implementation rules is
`../../src/diptrace_mcp/data/serializer_reference.json`.

## Plug-in exchange lifecycle

A DipTrace plug-in is an external executable. DipTrace exports a temporary XML exchange file,
launches the executable with that path, waits for it to exit, and imports the same file back.
There is no required in-process DLL API. Each editor has a separate plug-in `Type` namespace in
`settings.xml`; those underscore names must not be confused with the hyphenated data XML root
`Type` values.

Typical data roots are:

- `Source Type="DipTrace-PCB"` → editable `Board` plus embedded design-cache libraries;
- `Source Type="DipTrace-Schematic"` → editable `Schematic` plus design cache;
- `Library Type="DipTrace-ComponentLibrary"`;
- `Library Type="DipTrace-PatternLibrary"`.

## Shared serialization rules

- Root `Units` is `mm`, `inch`, or `mil`; Real geometry uses that unit.
- Defaults are commonly omitted. Missing does not mean numeric zero.
- Ordinary geometry/placement angles are radians counter-clockwise.
- Discrete `Orientation` values are `0`, `90`, `180`, `270` where documented.
- `Model3D/Rotate` values are degrees.
- Keep unknown XML when editing in place. Never normalize away fields merely because the MCP
  does not currently interpret them.

## IDs and import behavior

`ImpMode=All` replaces the incoming object list. `Edit` matches existing top-level objects by
`Id`. Preserve IDs on edited objects; omit IDs on newly added objects so DipTrace can assign
them. A guessed ID in a partial export can collide with an object that was not exported.

When a Selected filter is active, only incoming objects with `Selected="Y"` are processed.
Unselected objects are skipped silently.

Nested containers whose children have no independent ID are replacement lists when included.
The critical examples are PCB traces, schematic/bus wires, and point lists. To append one
member safely, re-list the complete nested list; to preserve it, omit that container.

For edit-import deletion, keep the object node and set `Enabled="N"`. A normal full save may
prune disabled objects afterwards.

Whole-file generation has an additional constraint: arrays used positionally by the reader
must stay dense and in their required order. This is separate from the ID-keyed plug-in Edit
workflow.

## Pattern/Pad rules

`PadStyle Type` is `Surface` or `Through`. Through holes use `HoleType=Round|Obround`, `Hole`
for diameter/width, and `HoleH` for obround height.

A fiducial is special:

```xml
<PadStyle Name="FID" Type="Surface" Hole="1.2">
  <MainStack Shape="Fiducial" Width="0.8"/>
</PadStyle>
```

For `Shape="Fiducial"`, `MainStack/Height` is omitted and `Width` alone is copper diameter.
`PadStyle/Hole` is fiducial keepout diameter; it is not a drill. `HoleH` has no fiducial
meaning.

Main copper shapes documented by the supplied serializer reference are `Ellipse`, `Obround`,
`Rectangle`, `Polygon`, `D-shape`, and `Fiducial`.

## Mask and paste

Mask modes: `Common`, `Open`, `Tented`, `By Paste`.
Paste modes: `Common`, `Solder`, `No Solder`, `Segments`.

`Common` is represented by omission of the corresponding attribute. Custom numeric overrides
use `CustomSwell` and `CustomShrink`; the serializer reference identifies `-1000` as the unset
sentinel. Segmented paste uses `Segment_Percent`, `Segment_EdgeGap`, `Segment_Gap`,
`Segment_Side` and `TopSegments`/`BotSegments` containing rectangle `Item` entries.

## Pattern layer literals

Documented pattern shape layers include:

`Top Silk`, `Top Assy`, `Top Mask`, `Top Paste`, `Bottom Paste`, `Bottom Mask`, `Bottom Assy`,
`Bottom Silk`, `Top`, `Top Keepout`, `Bottom Keepout`, `Bottom`, `Board Cutout`,
`Top Dimension`, `Bottom Dimension`, `Non-Signal`, `Top Courtyard`, `Bottom Courtyard`,
`Top Outline`, `Bottom Outline`, `Top Terminals`, `Bottom Terminals`.

Do not invent combined names such as `Top/Bottom Courtyard`. Do not replace numeric trace-point
`Lay` references with textual layer names.

## Geometry containers

Most geometry vertex containers use `<Point X="..." Y="..."/>`. Do not globally rewrite
`Point` ↔ `Item`. Mask/paste segment rectangles are a documented exception and use
`<Item X1="..." Y1="..." X2="..." Y2="..."/>`.

## Trust and verification

These rules can prove that MCP code agrees with the supplied serializer documentation. They do
not prove that a generated file opens/saves/re-exports correctly in a particular DipTrace
build. Native writer capabilities remain gated on real DipTrace 5.3 fixtures and semantic
round-trip evidence.

## Source fingerprints

Serializer-derived archive Markdown:

- Pattern Editor: `b000a248bdbf7a2f17d24a12b9453928c8a4c1a2b96388800b085aa52838bdf3`
- Component Editor: `cf76b6698cab8fa5300e48003a0516e4a53d0e2b58259d40439c600f8ac6fc48`
- PCB Layout: `ec70cb9ecc5766c500cad4ed7c99e1d712d6e02b9e4075a59bd02ede965916b9`
- Schematic: `d6ed68ae448b453841ba7b83aff51dccf9966450b55f7cc4d58e0265d31f080a`

The second archive was used as an agent-oriented navigation/cookbook source; its statements are
also treated as reference-only.
