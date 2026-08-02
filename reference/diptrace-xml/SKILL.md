---
name: diptrace-xml-reference
description: "Project-authored guidance for DipTrace XML parser, writer, review and evidence work; preserve unknowns and separate synthetic observations from live evidence."
---

# DipTrace XML reference

Use this guide when changing the XML parser, compiler, bridge, fixture or
review code. Read [`REFERENCE.md`](REFERENCE.md), the clean-room
[`spec_inventory.json`](spec_inventory.json), and the measured
[`FORMAT_COVERAGE.md`](../../docs/FORMAT_COVERAGE.md). The inventory is derived
from project-owned XML observations; it is not a redistributed vendor manual.

## Required workflow

1. Identify the XML dialect and the exact element/attribute being changed.
2. Confirm that the inventory observation is synthetic, controlled-export, or
   still open; do not promote a synthetic observation to live compatibility.
3. Preserve unknown attributes/elements and existing IDs outside the operation
   boundary.
4. Add a regression test and update the evidence/trust disclosure for any
   writer or review behavior.
5. Run the relevant parser, geometry, packaging, provenance and MCP contract
   checks.

## Open gates

- `Component/@Angle` direction, units, normalization, and side/mirror behavior
  require a live DipTrace GUI edit and independent re-export (Q1).
- Standalone Component/Pattern Library mutation remains evidence-gated.
- Synthetic fixtures do not prove DipTrace 5.3 compatibility.
- NetClass-aware clearance is implemented for routing and trace-to-trace review;
  trace-to-object review remains explicitly partial.

Do not claim vendor permission, endorsement, universal DipTrace compatibility,
or production readiness from this skill or from the inventory.
