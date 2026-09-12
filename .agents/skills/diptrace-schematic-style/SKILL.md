---
name: diptrace-schematic-style
description: Create or edit readable DipTrace schematics and multi-sheet overview diagrams while preserving verified library parts, page containment, and clear human-oriented wiring. Use for schematic authoring or visual cleanup, not read-only electrical review.
---

# DipTrace Schematic Style

Apply these house rules while creating, generating, or visually cleaning a
DipTrace schematic. Datasheets, electrical safety, ERC/DRC, mechanical limits,
and manufacturability take precedence.

## Run gated learning builds one sheet at a time

When the user is using a board as a training run for repeatable one-prompt
generation:

1. Apply the repository Knowledge/RAG policy before searching. Query the
   configured engineering RAG only when a material unknown fact is required to
   decide the design. Pure visual rearrangement, alignment, spacing, or cleanup
   must use the user's instruction and current DipTrace state without
   `knowledge_search`. When retrieval is required, record returned document
   IDs/sections and distinguish retrieved requirements from model inference.
2. Freeze the purpose, interfaces, component evidence and acceptance checks of
   one sheet only. Do not create the next sheet until the current sheet passes
   its declared structural, electrical, readability and native-roundtrip gates.
3. On an explicit clean restart, delete only the resolved schematic targets;
   preserve PCB artifacts unless the user separately includes them. Never use
   rejected schematic coordinates, wires or generated netlist XML as inputs to
   the replacement.
4. Keep an append-only engineering journal with the query, retrieved sources,
   mutations, tool results, failures, exact resume point and artifact hashes.
   RAG is retrieval memory, not gate authority.
5. After a gate passes, ingest the journal update and add only reusable,
   observed workflow rules to this skill. Keep project-specific MPNs, nets and
   coordinates in project evidence rather than universal skill instructions.
6. When native acceptance is required, start from `create_document_from_seed`
   with a known DipTrace export so native `Settings`, `Simulator`, and unknown
   loader fields survive. A synthetic scaffold that parses in MCP is not proof
   that DipTrace will open it as a normal project.
7. Opening schematic XML can show DipTrace's `Shift Origin` import dialog even
   for an unchanged control seed. Automation may confirm it only by exact title
   plus one enabled `OK` button through a Win32 message; otherwise fail closed.
   Keep page geometry centered at `(0, 0)` and do not infer a coordinate defect
   from this dialog alone.
8. Respect the MCP per-write object limit. If cleaning a native seed exceeds
   it, split the cleanup into guarded dry-run/commit operations by container or
   component. Never raise or bypass the limit for convenience.

## Resolve components before placement

For every component, record the result of this exact lookup order before
placing or creating it:

1. Search installed DipTrace libraries by exact MPN. Reuse the native symbol,
   pin mapping, and attached pattern.
2. If no exact DipTrace match exists, search LCSC/JLCPCB by exact MPN and reuse
   its catalog/library data.
3. Draw a custom component only after both searches have documented zero exact
   matches; validate its pinout and footprint against the manufacturer
   datasheet.

Never replace an available exact component with a hand-drawn generic symbol.
Apply the same order to connectors and catalog passives.

## Place for human reading

- Organize functional flow left-to-right. Put external connectors and other
  signal or power sources on the left and receiving blocks on the right.
- Put positive rails above the signal path. Use exact installed native power
  Net Port symbols for them (for example `+3V3`, or a VCC-style symbol whose
  instance name is `VBUS`) and native GND symbols below the components they
  return. Hide a GND name marking when the symbol is already unambiguous and
  the marking would add rotated clutter. Do not draw long ground wires or use
  text labels in place of power symbols.
- Place each support component beside the IC pin it serves. Move or rotate
  parts before accepting a long detour, crossing, or ambiguous connection.
- Keep reference designators, values, net names, sheet names, and port labels
  horizontal, upright, unobstructed, and close to their object. Rotate the part
  or counter-rotate its markings where necessary.
- Orient or mirror connectors so their wire-facing pins point into the sheet or
  block while their pin order remains easy to scan from top to bottom.

## Wire visibly and locally

- Prefer short orthogonal wires within a sheet. For every cross-sheet/global
  signal, place a native DipTrace Net Port component with the exact intended
  net name on every participating sheet. A root `Shape Type=Text` net label is
  only an annotation; it does not create cross-sheet electrical connectivity.
- Give every IC pin a clear straight escape segment before the first bend.
  Never run along adjacent pin stubs.
- Never route through a component body, an unrelated pin, or a pin stub.
- Avoid crossings and gratuitous U/staple detours. Rearrange or rotate parts
  first; use a compact multi-bend route only when endpoint orientations require
  it.
- Use one straight segment when the endpoints can be connected directly. Add a
  bend only to avoid a real obstacle or to enter the intended side of a block.
- Align peer blocks to a shared edge or centerline and keep their sizes and gaps
  visually consistent. Do not stagger equivalent tiles without a functional
  reason.
- Every documentary line must terminate on a visible block, endpoint, port, or
  intentional junction. Never leave a line ending in empty page space.
- Route intersections are a visual-gate failure unless they are intentional
  connected junctions. Prefer moving blocks over adding detours.
- A documentary DipTrace `Shape Type="Line"` is exactly one two-point segment.
  Encode every bend as another line shape with a shared endpoint; never accept
  a preview renderer that silently treats one multi-point shape as a polyline.
- Extend a net label away from its pin or wire end and keep its text corridor
  clear of support parts and wires.
- Reject any generated name matching `Net <number>`. Repair the native Net Port
  connection, then confirm the intended name survives a native DipTrace
  open/save/re-export.

## Keep content on the DipTrace page

DipTrace schematic pages are centered at `(0, 0)`. Treat `XPos` and `YPos` as
viewport state only. Compute the usable page bounds as:

```text
min_x = -SheetWidth / 2 + LeftMargin
max_x =  SheetWidth / 2 - RightMargin
min_y = -SheetHeight / 2 + BottomMargin
max_y =  SheetHeight / 2 - TopMargin
```

Center each sheet's content in this box and verify the extents of components,
wires, power symbols, labels, and annotations all remain inside it.

## Add a multi-sheet overview

For a multi-sheet design, add one top-level overview sheet similar to an Altium
hierarchy diagram:

- use one named block per functional sheet;
- keep the primary functional flow left-to-right, but place secondary blocks as
  a fan, star, or compact pipeline when that makes their relationships clearer;
  never force every block into decorative rows, but align blocks that are peers
  in the chosen composition;
- put input ports on each block's left edge and output ports on its right edge;
- connect blocks with visible orthogonal lines labelled with the key cross-sheet
  nets;
- use native hierarchy/sheet ports when supported; otherwise use documentary
  shapes and text that cannot create unintended electrical connectivity or BOM
  entries.

Do not duplicate the detailed circuitry on the overview sheet.
Do not draw sheet-wide power-distribution rails on an architecture overview
unless power distribution is the point of that view; prefer only the logical
or control relationships the overview is meant to explain.

## Finish checks

Before handing off, verify page containment, readable horizontal text, visible
pin escapes, absence of component/pin crossings, local ground symbols, and a
coherent overview. Demo media is opt-in: do not record video, GIF, MP4, or a
staged screenshot sequence unless the user explicitly requests a demo, capture,
or evidence package.
