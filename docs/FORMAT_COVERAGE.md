# DipTrace XML Format Coverage

## Summary

| Metric | Value |
| --- | --- |
| Total elements in spec | 294 |
| Normalized (reader produces typed field) | 61 |
| Written only (writer can create/modify) | 22 |
| Mentioned only (literal, not an XML call) | 20 |
| Passthrough (unknown XML, kept byte-for-byte) | 191 |
| **Coverage** | **28.2%** |

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
- `Wire`
- `Wires`

## Written-Only Elements

- `ActiveSheet`
- `Board`
- `GNDTemplate`
- `Group`
- `Groups`
- `Id`
- `LayerName`
- `LayerStackName`
- `Name`
- `Origin`
- `Panel`
- `PartName`
- `PartRefDes`
- `RefDes`
- `Schematic`
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
- `PatternMarking`
- `Polygon`
- `PosPoint`
- `PosPoints`
- `RefDesMarking`
- `Signal`
- `Silk`
- `TopSegments`
- `ValueMarking`
- `VertTabsY`

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
- `BorderZones`
- `BottomComponentLock`
- `BottomLeftBlock`
- `BottomMargin`
- `BottomRightBlock`
- `BusConnections`
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
- `DCTransferFunc`
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
- `ExtBottomLeftBlock`
- `ExtTopLeftBlock`
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
- `Grid`
- `HSheet`
- `HidePower`
- `HideRingLay`
- `HierarchyPath`
- `HierarchySheets`
- `HorzBorderSize`
- `HorzZones`
- `Index`
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
- `LibPath`
- `Libs`
- `LineWidth`
- `LockNetStructure`
- `MainLengthRule`
- `ManufacturerGlobal`
- `Markings`
- `NameGlobal`
- `NegSeparateTraces`
- `NegTrace`
- `NodeSize`
- `Noise`
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
- `RelatedSchem`
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
- `SmallSignalAC`
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
- `Title`
- `Titles`
- `TopComponentLock`
- `TopLeftBlock`
- `TopMargin`
- `TopRightBlock`
- `TraceClearance`
- `TraceWidth`
- `Transient`
- `UId`
- `UpdateIds`
- `UsePartFontColor`
- `ValueGlobal`
- `Var`
- `Variation`
- `VertBorderSize`
- `VertZones`
- `ViaHole`
- `ViaSize`
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

