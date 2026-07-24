---
name: diptrace-xml-reference
description: "Reference skill for implementing, reviewing, or debugging DipTrace XML parsers, writers, plug-in exchange, and bridge behavior. Use it to resolve exact XML enums/defaults/import semantics before changing MCP code. It is reference-only and never grants DipTrace compatibility or round-trip trust."
---

# DipTrace XML Reference

## Purpose

Use this skill when changing the MCP's DipTrace XML parser/compiler, library adapters, bridge,
fixture generator, or semantic transaction code. It distills the supplied serializer-derived
specifications and AI context pack into implementation constraints.

The canonical machine-readable rules live at
`../../src/diptrace_mcp/data/serializer_reference.json`. Read `REFERENCE.md` for the compact
human reference.

## Trust boundary

The supplied documents state that they were generated/verified against a DipTrace serializer
repository revision 7276. This repository does not independently authenticate that claim.
Treat them as `user_supplied_reference` with `trust_effect=none`.

They may:

- constrain parser and writer behavior;
- define enums, defaults, omission rules, and import semantics;
- motivate regression tests and identify likely implementation bugs.

They may **not**:

- promote any document to `diptrace_exported`, `diptrace_open_save_verified`, or
  `diptrace_roundtrip_verified`;
- unblock native Pattern/Component Library writers without independent DipTrace 5.3
  open/save/re-export fixtures;
- replace the semantic comparison and trusted-evidence gates.

## Mandatory workflow

1. Identify the exact XML dialect and element/attribute being changed.
2. Look up the machine rule by ID before implementing an enum/default/write condition.
3. Check the cross-cutting behaviors before touching import or list mutation logic.
4. Preserve unknown attributes/elements and existing IDs unless the semantic operation
   explicitly requires a change.
5. Add a regression test for every behavior taken from the reference.
6. For a writer change, keep capability discovery unchanged until real DipTrace round-trip
   evidence exists.
7. Run pytest, Ruff, Mypy, generated-skill verification, and the native Windows CI matrix.

## High-risk rules

- Ordinary `Angle` values are radians counter-clockwise. Pin `Orientation` and pattern
  template `Orientation` are discrete `0/90/180/270` enums. `Model3D/Rotate` is degrees.
- `Enabled="N"` is an edit-import delete flag. Do not model it as visibility.
- Under `Edit`, keep an existing object's `Id`; omit `Id` for a new object. Do not invent a
  free ID from a partial export.
- Under a `Selected` import filter, an unselected incoming object is skipped, not added.
- Nested lists without member IDs, notably PCB `Traces`, schematic/bus `Wires`, and point
  lists, are replacement containers when present.
- `MainStack Shape="Fiducial"` omits `Height`; `Width` is the copper diameter. `PadStyle/Hole`
  then means fiducial keepout diameter, not a drill.
- `MaskPaste` Common modes are represented by omitted attributes. `CustomSwell=-1000` and
  `CustomShrink=-1000` are unset sentinels and must not become geometry.
- Pattern `Layer` is a textual literal (`Top Silk`, `Bottom Courtyard`, etc.); trace-point
  `Lay` is a numeric copper-layer reference.
- Geometry point lists use `<Point>` except documented containers such as mask/paste
  `TopSegments`/`BotSegments`, whose rectangles are `<Item X1 Y1 X2 Y2>`.

## Stop conditions

Stop and require independent evidence when a requested writer behavior is not represented by
a serializer rule, when two supplied references conflict, or when a change would expand a
currently unavailable capability. Do not infer missing semantics from field names alone.
