---
name: diptrace-xml-reference
description: "Reference skill for implementing, reviewing, or debugging DipTrace XML parsers, writers, plug-in exchange, and bridge behavior. Use it to resolve exact XML enums/defaults/import semantics before changing MCP code. It is reference-only and never grants DipTrace compatibility or round-trip trust."
---

# DipTrace XML Reference

## Purpose

Use this skill when changing the MCP's DipTrace XML parser/compiler, library adapters, bridge,
fixture generator, semantic transactions, or any code that emits XML. The canonical machine rules
are in `../../src/diptrace_mcp/data/serializer_reference.json`; read `REFERENCE.md` for a compact
human-oriented map.

## Trust boundary

The supplied documents state that they were generated/verified against a DipTrace serializer
repository revision 7276. This repository does not independently authenticate that claim. Treat
them as `user_supplied_reference` with `trust_effect=none`.

They may constrain parser/writer behavior and regression tests. They may not promote a document to
`diptrace_exported`, `diptrace_open_save_verified`, or `diptrace_roundtrip_verified`, and they may
not unblock native Pattern/Component Library writers without independent DipTrace 5.3 fixtures.

## Mandatory workflow

1. Identify the exact XML dialect and element/attribute being changed.
2. Look up the stable machine rule ID before implementing an enum/default/write condition.
3. Check cross-cutting behaviors before touching import, deletion, IDs, or nested lists.
4. Preserve unknown attributes/elements and existing IDs unless the semantic operation explicitly
   requires a change.
5. Add a regression test for every behavior taken from the reference.
6. Keep capability discovery unchanged for writer paths until real DipTrace round-trip evidence
   exists.
7. Run pytest, Ruff, Mypy, generated-skill verification, and the native Windows CI matrix.

## High-risk rules

- Ordinary `Angle` values are radians counter-clockwise. Pin and Pattern `Orientation` are discrete
  `0/90/180/270`; `Model3D/Rotate` is degrees.
- `Enabled="N"` is an edit-import delete flag, not visibility.
- Under `Edit`, keep an existing top-level object's `Id`; omit `Id` for a new object.
- With a PCB/Schematic `Selected` import filter, unselected incoming objects are skipped entirely.
- Nested ID-less containers such as `Traces`, net/bus `Wires`, and point lists are replacement
  containers when present.
- `MainStack Shape="Fiducial"` omits `Height`; `Width` is copper diameter. `PadStyle/Hole` is then
  fiducial keepout diameter, not a drill.
- `MaskPaste` Common modes are represented by omitted attributes. `CustomSwell=-1000` and
  `CustomShrink=-1000` are unset sentinels.
- Pattern `Layer` is a textual literal (`Top Silk`, `Bottom Courtyard`, etc.); trace-point `Lay` and
  CopperPour `Lay` are numeric copper-layer references.
- Geometry point lists canonically use `<Point>`; mask/paste segment rectangles are a documented
  `<Item X1 Y1 X2 Y2>` exception.
- PCB pad `NetId` is authoritative net membership. Visual trace contact does not create logical
  connectivity; trace endpoints must be declared.

## Stop conditions

Stop and require independent evidence when a requested writer behavior is absent from the
reference, when supplied sources conflict, or when the change would expand a currently unavailable
capability. Do not infer missing semantics from field names alone.
