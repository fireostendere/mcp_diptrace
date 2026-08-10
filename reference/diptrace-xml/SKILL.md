---
name: diptrace-xml-reference
description: "Project-authored guidance for DipTrace XML parser, writer, review and evidence work; preserve unknowns and separate synthetic observations from live evidence."
---

# DipTrace XML reference

Use this guide when changing the XML parser, compiler, bridge, fixture or review code. Read [`REFERENCE.md`](REFERENCE.md), the clean-room [`spec_inventory.json`](spec_inventory.json), and the measured [`FORMAT_COVERAGE.md`](../../docs/FORMAT_COVERAGE.md). The inventory is derived from project-owned observations; it is not a redistributed vendor manual.

## Required workflow

1. Identify the XML dialect and exact element/attribute being changed.
2. Distinguish synthetic observation, controlled export, private/manual evidence and still-open behavior; never promote one class into another by assertion.
3. Preserve unknown attributes/elements and stable IDs outside the operation boundary.
4. Add regression coverage and update evidence/trust disclosure for writer/review behavior.
5. Run relevant parser, geometry, packaging, provenance and MCP-contract checks.
6. For native compatibility claims, bind the result to an exact DipTrace/editor version and exact candidate/artifact.

## Current evidence boundaries

- `Component/@Angle` has later manual DipTrace PCB Layout 5.3.0.3 evidence consistent with the radians reader/writer convention and is PASS at the project-manual checkpoint. Broader/public package-owned evidence remains scoped rather than inferred.
- Internal raw-preserving Component/Pattern Library mutation exists and has controlled real Component Editor / Pattern Editor evidence; public native-library mutation is still unregistered and broader identity/canonicalization semantics remain evidence-gated.
- Synthetic fixtures do not prove DipTrace 5.3 compatibility.
- NetClass-aware routing/review behavior remains feature-specific and is not equivalent to complete native DRC.
- Copper refill, manufacturing, full DSN/SES and other native-host semantics remain exact-scope evidence questions where documented.

Do not claim vendor permission, endorsement, universal DipTrace compatibility or production readiness from this reference or from the inventory.
