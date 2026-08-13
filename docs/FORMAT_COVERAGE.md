# DipTrace XML Format Coverage

## Summary

| Metric | Value |
| --- | --- |
| Total observed elements | 107 |
| Observed XML attributes | 300 |
| Element text-content observations | 0 |
| Project-authored omission clauses | 0 |
| Documented parent/child relationships | 143 across 61 parents |
| Normalized (reader produces typed field) | 72 |
| Written only (writer can create/modify) | 19 |
| Mentioned only (literal, not an XML call) | 6 |
| Passthrough (unknown XML, kept byte-for-byte) | 10 |
| **Coverage** | **85.0%** |

## Inventory Provenance

The inventory is a clean-room factual summary generated from the project-owned
XML fixtures listed in `spec_inventory.json`. It records observed element and
attribute names and bounded observed values only. It contains no PDF material,
extracted documentation text, normative descriptions, or copied examples.
Each source is SHA-256 bound, marked `synthetic_fixture`, and explicitly excluded
from accepted DipTrace trust evidence until an independent acceptance audit
confirms its provenance and any required redistribution basis.

Coverage below is coverage of the project-authored factual vocabulary against
the current reader/writer call sites; it is not a normative DipTrace format specification.

## Normalized Elements

- `AddField`
- `AddFields`
- `BoardOutline`
- `Buses`
- `CenterPoint`
- `CenterPoints`
- `Component`
- `Components`
- `ConnectivityCheck`
- `CopperLayers`
- `CopperPour`
- `CopperPours`
- `DRC`
- `DefPad`
- `DifferentialPair`
- `DifferentialPairs`
- `ERC`
- `Hole`
- `Holes`
- `Item`
- `Lay`
- `LayClearance`
- `LayClearances`
- `LayProperties`
- `LayProperty`
- `LaySize`
- `LaySizes`
- `LayerStackItem`
- `LayerStackItems`
- `Library`
- `Lines`
- `MainStack`
- `MaskPaste`
- `Material`
- `Model3D`
- `Net`
- `NetClass`
- `NetClasses`
- `Nets`
- `Number`
- `Offset`
- `Pad`
- `PadPoint`
- `PadPoints`
- `PadStyle`
- `PadStyles`
- `Pads`
- `Part`
- `Pattern`
- `Patterns`
- `Pin`
- `Pins`
- `Point`
- `Points`
- `Ratline`
- `Ratlines`
- `Rotate`
- `Routing`
- `Segment`
- `Segments`
- `Settings`
- `Shape`
- `Shapes`
- `Sheet`
- `SheetSettings`
- `Sheets`
- `Trace`
- `Traces`
- `ViaStyle`
- `ViaStyles`
- `Wires`
- `Zoom`

## Written-Only Elements

- `ActiveSheet`
- `Board`
- `GNDTemplate`
- `Id`
- `LayerName`
- `LayerStackName`
- `Name`
- `Name_Unique`
- `Origin`
- `PartName`
- `PartRefDes`
- `RefDes`
- `RefDesMarking`
- `Schematic`
- `Source`
- `Text`
- `Type`
- `VCCTemplate`
- `Value`

## Mentioned-Only Elements

- `Assy`
- `NegPoint`
- `NegPoints`
- `PosPoint`
- `PosPoints`
- `Silk`

## Passthrough Elements

- `Data`
- `Datasheet`
- `Filename`
- `FutureComponentData`
- `FutureExtension`
- `FuturePatternData`
- `FutureStackupExtension`
- `Manufacturer`
- `Note`
- `PadNumber`

## What Passthrough Means

Passthrough elements survive byte-for-byte **only** while no operation removes or
regenerates their parent subtree. The list below is derived from writer call sites
that iterate existing children and remove them. A value of `none` means no child
currently classified as passthrough was named by the inventory or removal path; it
does not make undocumented children safe.

- `routing_compiler.py::_prune_satisfied_ratlines` may remove `<Ratline>` from `<Ratlines>`; known passthrough children: none.
- `routing_compiler.py::_write_points` clears all children of `<Points>` (inventory children: `<Item>`, `<Point>`); known passthrough children: none.
- `semantic_compiler.py::_apply_remove_testpoints` may remove `<PadStyle>` from `<PadStyles>`; known passthrough children: none.
- `semantic_compiler.py::_apply_remove_testpoints` may remove `<Item>` from `<Pads>`; known passthrough children: none.
- `semantic_compiler.py::_apply_remove_testpoints` may remove `<Pattern>` from `<Patterns>`; known passthrough children: none.
- `semantic_compiler.py::_apply_sync_schematic_to_pcb` may remove `<Item>` from `<Pads>`; known passthrough children: none.
- `semantic_compiler.py::_apply_ungroup_components` may remove `<Group>` from `<Groups>`; known passthrough children: none.

Any operation listed above can discard matching passthrough children rather than
preserve their original bytes. Unlisted dynamic removal sites remain unavailable
to this static detector and must not be assumed safe.

