# Serializer Reference

`src/diptrace_mcp/data/serializer_reference.json` is the machine-readable implementation
reference distilled from the two user-supplied DipTrace documentation archives reviewed in
July 2026.

It is deliberately **reference-only evidence**. The source documents describe themselves as
serializer-derived and identify repository revision 7276, but this project does not independently
authenticate that provenance. Consequently the reference may constrain parser/writer behavior and
regression tests, but it cannot grant `diptrace_exported`, `diptrace_open_save_verified`,
`diptrace_roundtrip_verified`, or any other high-trust validation level.

## What is encoded

The current v1 reference contains:

- source SHA-256 fingerprints for the four serializer-derived specifications and the nine-file AI
  context pack;
- cross-cutting import rules for units, angles, object IDs, `Selected`, `Enabled`, nested-list
  replacement, point semantics, unknown-field preservation, file references, and the executable
  plug-in exchange contract;
- field-level rules for PCB, Schematic, Component Library, and Pattern Library XML;
- enum sets, omission/default behavior, legacy aliases, and writer/reader notes for high-risk
  fields such as Pattern `MaskPaste`, fiducials, `Model3D`, PCB connectivity, and Schematic wires.

The JSON Schema is stored beside the reference as
`src/diptrace_mcp/data/serializer_reference.schema.json`. Runtime helpers are in
`diptrace_mcp.serializer_reference`:

- `load_serializer_reference()`;
- `serializer_rule(rule_id)`;
- `serializer_behavior(behavior_id)`;
- `serializer_enum(rule_id)`;
- `serializer_accepts(rule_id, value)`.

## Parser corrections derived from the reference

The first integration uses the reference to close concrete parser gaps rather than merely adding
more documentation:

- `MainStack Shape="Fiducial"` normalizes to circular copper geometry even though the serializer
  omits `Height`; normalized height is derived from `Width`;
- `PadStyle/Hole` on a fiducial is treated as keepout semantics and is excluded from annular-ring
  drill validation;
- `CustomSwell="-1000"` and `CustomShrink="-1000"` normalize to unset rather than producing
  nonsensical mask/paste geometry;
- `D-shape` pad stacks are retained as a conservative rectangle approximation instead of losing
  geometry entirely;
- Pattern `Mounting` no longer invents a non-existent `None` value when the attribute is absent;
- `Model3D/Filename` reads its nested `Path` and `Var` children instead of treating `Filename` as
  direct text;
- Component Editor legacy `PadIndex` and `PatternType` aliases are accepted while canonical names
  remain `PadId` and `Style`.

These fixes do not enable native Component/Pattern Library mutation. Writer capability remains
blocked on independent DipTrace 5.3 controlled open/save/re-export fixtures.

## Maintenance rule

When code depends on an exact serializer enum, default, omission condition, or import behavior:

1. add or update a stable rule in the machine reference;
2. add a regression test that exercises the behavior;
3. preserve unknown XML outside the targeted semantic change;
4. do not raise capability/trust merely because the documentation states that a behavior exists;
5. require real DipTrace evidence for any newly exposed writer path.
