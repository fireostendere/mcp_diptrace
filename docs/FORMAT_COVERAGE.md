# DipTrace XML Format Coverage

## Summary

| Metric | Value |
| --- | --- |
| Total elements in spec | 270 |
| XML attributes in spec | 727 |
| Element text-content definitions | 232 |
| Explicit attribute omission clauses | 4 |
| Documented parent/child relationships | 90 across 80 parents |
| Normalized (reader produces typed field) | 58 |
| Written only (writer can create/modify) | 19 |
| Mentioned only (literal, not an XML call) | 22 |
| Passthrough (unknown XML, kept byte-for-byte) | 171 |
| **Coverage** | **28.5%** |

## Inventory Provenance

The inventory is generated from the three official PDFs named in
[`spec_inventory.json`](../reference/diptrace-xml/spec_inventory.json). The PDFs
are not redistributed. Canonical per-page text extracted with the pinned
`pypdf==6.14.2` is committed under
[`reference/diptrace-xml/extracted_text/`](../reference/diptrace-xml/extracted_text/),
with both PDF and intermediate SHA-256 values recorded in the inventory.
CI regenerates the inventory from that offline intermediate before computing this
report. A maintainer with the original PDFs can independently re-extract the same
intermediate and compare it byte-for-byte.

Only literal XML examples introduce element names. Scalar element content is
recorded separately from attributes, and prose that merely mentions `<Element>`
does not change parser ownership. The public PDFs contain four explicit
attribute-level absence clauses; no additional `omitted_when` conditions are
inferred.

## Normalized Elements

- `AddField`
- `AddFields`
- `BoardOutline`
- `Bus`
- `Buses`
- `CenterPoint`
- `CenterPoints`
- `ClearanceDetails`
- `Component`
- `Components`
- `ConnectivityCheck`
- `CopperLayers`
- `CopperPour`
- `CopperPours`
- `DRC`
- `DifferentialPair`
- `DifferentialPairs`
- `ERC`
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
- `MaskPaste`
- `Material`
- `Net`
- `NetClass`
- `NetClasses`
- `Nets`
- `Pad`
- `PadPoint`
- `PadPoints`
- `Pads`
- `Part`
- `Pin`
- `Pins`
- `Point`
- `Points`
- `Ratline`
- `Ratlines`
- `Segment`
- `Segments`
- `Shape`
- `Shapes`
- `Sheet`
- `Sheets`
- `Trace`
- `Traces`
- `ViaStyle`
- `ViaStyles`
- `Wire`
- `Wires`

## Written-Only Elements

- `ActiveSheet`
- `GNDTemplate`
- `Group`
- `Groups`
- `Id`
- `LayerName`
- `LayerStackName`
- `Name`
- `Panel`
- `PartName`
- `PartRefDes`
- `RefDes`
- `Source`
- `Text`
- `TextLine`
- `TextLines`
- `Type`
- `VCCTemplate`
- `Value`

## Mentioned-Only Elements

- `Assy`
- `BotSegments`
- `Columns`
- `Courtyard`
- `DatasheetMarking`
- `HorzTabsX`
- `ManufacturerMarking`
- `NameMarking`
- `NegPoint`
- `NegPoints`
- `Polygon`
- `PosPoint`
- `PosPoints`
- `RefDesMarking`
- `Signal`
- `Silk`
- `TopSegments`
- `TraceClearance`
- `ValueMarking`
- `VertTabsY`
- `ViaHole`
- `ViaSize`

## Passthrough Elements

- `AddFieldsGlobal`
- `AllowedVias`
- `Assembly`
- `AssemblyExclude`
- `AssemblyName`
- `AssemblyVariant`
- `AssemblyVariants`
- `AutoUpdate`
- `Autorouting`
- `AxisColor`
- `BlindLay`
- `BlockId`
- `BoardClearance`
- `Border`
- `BottomComponentLock`
- `BottomMargin`
- `BottomRightBlock`
- `BusConnector`
- `BusConnectors`
- `CTC_Cells`
- `Category`
- `CategoryType`
- `CategoryTypes`
- `Cell`
- `Cells`
- `ClassToClass`
- `ColWidths`
- `Column`
- `ColumnWidths`
- `CompBorders`
- `CompOutline`
- `CompRotate`
- `ConnectedTeardrops`
- `CustomSpoke`
- `CustomSpokes`
- `DRCDone`
- `DatasheetGlobal`
- `DesignCache`
- `DesignError`
- `DesignErrors`
- `Dimension`
- `Dimensions`
- `DisplayName`
- `DisplaySheet`
- `DisplayTitles`
- `EditInactiveLayer`
- `FanoutLength`
- `Field`
- `Fields`
- `FlipTextAuto`
- `Folder`
- `Folders`
- `FontColor`
- `FontLineWidth`
- `FontName`
- `FontScale`
- `FontSize`
- `FontVector`
- `FontWidth`
- `GndNetName`
- `HSheet`
- `HidePower`
- `HideRingLay`
- `HierarchyPath`
- `HierarchySheets`
- `HorzBorderSize`
- `HorzZones`
- `IntCon`
- `InternalConnections`
- `JumperLayer`
- `LayerClearances`
- `LayerDisplayMode`
- `LayerPanel`
- `Lays`
- `LeftMargin`
- `LengthRule`
- `LengthRules`
- `Lib`
- `Libs`
- `LockNetStructure`
- `MainLengthRule`
- `ManufacturerGlobal`
- `NameGlobal`
- `NegSeparateTraces`
- `NegTrace`
- `NodeSize`
- `NonSignal`
- `NonSignals`
- `NumberOfPoints`
- `OutputNet`
- `PadId`
- `PasteMaskShrink`
- `Path`
- `PatternGlobal`
- `PictureFile`
- `PictureVector`
- `PinNumbers`
- `PointerText`
- `PointsPerSummary`
- `Polygons`
- `PosSeparateTraces`
- `PosTrace`
- `Position`
- `ProjectDir`
- `ProjectLibs`
- `RealTimeMode`
- `RefDesGlobal`
- `ReferenceNet`
- `RemovedDifferentialPair`
- `RemovedDifferentialPairs`
- `RightMargin`
- `RouteLayers`
- `Router`
- `RowHeights`
- `Rule`
- `Rules`
- `Scale`
- `SecondSource`
- `SecondSourceRefDes`
- `SecondSourceType`
- `SecondStartValue`
- `SecondStep`
- `SecondStopValue`
- `Separator`
- `SheetHeight`
- `SheetWidth`
- `Show`
- `ShowCompFiducials`
- `ShowList`
- `SignalDelayLength`
- `Signals`
- `Simulator`
- `Size`
- `Snap`
- `SolderMaskSwell`
- `SourceRefDes`
- `SourceType`
- `StackLength`
- `Standard`
- `StartFrequency`
- `StartTime`
- `StartValue`
- `Step`
- `StopFrequency`
- `StopTime`
- `StopValue`
- `SubType`
- `Table`
- `Tables`
- `Teardrop`
- `TeardropParams`
- `Teardrops`
- `Titles`
- `TopComponentLock`
- `TopMargin`
- `TraceWidth`
- `UId`
- `UpdateIds`
- `UsePartFontColor`
- `ValueGlobal`
- `Var`
- `Variation`
- `VertBorderSize`
- `VertZones`
- `Visible`
- `X`
- `XPos`
- `Y`
- `YIdentical`
- `YPos`
- `YSize`

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
- `semantic_compiler.py::_apply_sync_schematic_to_pcb` may remove `<Ratline>` from `<Ratlines>`; known passthrough children: none.
- `semantic_compiler.py::_apply_ungroup_components` may remove `<Group>` from `<Groups>`; known passthrough children: none.

Any operation listed above can discard matching passthrough children rather than
preserve their original bytes. Unlisted dynamic removal sites remain unavailable
to this static detector and must not be assumed safe.

