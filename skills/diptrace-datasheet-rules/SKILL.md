---
name: diptrace-datasheet-rules
description: RAG-backed. Extract auditable schematic, package, footprint, and PCB layout requirements from official component documents into project rules. Use before choosing or placing physical parts, checking a pin map, or resolving component-specific requirements; «требования из даташита». Use when the user says “Extract official component rules for this DipTrace design.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# Datasheet to DipTrace rules

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Retrieve indexed component evidence plus relevant theory/layout guidance; use DipTrace
library courses for mapping interpretation and verify exact limits against current official sources.

Write project-local `rules/<MPN>.md` using the
[rules template](references/rules-template.md). Replace its placeholders with actual
sources and checks; filling in a template does not establish evidence.
This task creates evidence documents; it does not authorize CAD edits.

## Identify and retrieve

1. Resolve exact manufacturer, orderable MPN suffix, package code, and device revision
   from the current BOM/specification. A family name or generic package label is insufficient.
2. Build on the project's RAG engineering context: retrieve indexed component evidence,
   supporting theory, practical layout guidance and DipTrace mapping lessons. Reuse verified
   sources and connect their principles to the rule extraction; obtain current official
   vendor documents for exact requirements and as a disclosed fallback when RAG is unavailable.
3. Check the vendor's current datasheet revision and revision history, errata, relevant
   application notes, recommended land pattern, and layout example. Save URLs, download
   date, revision, page/section, local artifact path, and SHA-256. Catalog geometry
   and a distributor mirror alone do not establish current manufacturer requirements.
4. Inspect the pinout, package dimensions, and layout figures themselves where required;
   text extraction can lose pin numbering, bottom-view orientation, and dimensions.

## Extract only applicable rules

- Recommended supply/logic ranges, sequencing, startup/inrush, absolute maxima as
  limits rather than operating targets, and power dissipation assumptions.
- Required decoupling/bias/filter/protection networks, values/tolerances, placement,
  capacitor bias effects and regulator stability conditions where specified.
- Pin types and mapping, exposed pad function, NC/DNC/reserved pins, boot straps,
  clocks/reset, programming/debug, interface and external connector constraints.
- Manufacturer package dimensions and tolerances; land pattern pad sizes/spacing,
  holes, pin 1 orientation, solder mask/paste and thermal treatment where specified.
- Critical placement topology, hot loops, feedback/Kelvin paths, ground connections,
  keepouts, differential/RF/clock routes, and thermal recommendations.
- Relevant revision-history changes and superseded advice. Do not apply one IC's
  grounding example to another part without evidence.

For each requirement record its ID, applicability, source section/page, value/unit or
topology, affected pins/nets/components, verification method, and status. Distinguish
manufacturer requirements, recommendations, calculated values, and house preferences.
If a dimension is derived rather than specified, show the formula and assumptions.

## Validate and hand off

Compare the actual library symbol/pattern with the source: pin numbers, pad numbers,
pin-to-pad correspondence, pitch, body/land dimensions, holes, orientation, exposed
pad, and duplicated physical contacts. Use
[library-quality-audit](../library-quality-audit/SKILL.md) for the
supported structural checks, then inspect unmodeled properties separately.

Never shrink pads, merge thermal arrays, or renumber pins merely to satisfy a parser
or DRC. A required conversion preserves physical geometry and all electrical contacts
with an explicit checked alias map. Missing package/land-pattern evidence blocks
physical placement; unavailable IC layout/revision evidence blocks the PCB build.

Record deviations with the cited requirement, reason, consequence, and disposition.
Leave unavailable checks unresolved. Report the rule file and the stage it enables;
do not fill in native-roundtrip or footprint-validation success before those checks run.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
