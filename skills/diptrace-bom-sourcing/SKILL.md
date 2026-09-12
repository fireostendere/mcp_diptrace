---
name: diptrace-bom-sourcing
description: RAG-backed. Build and check a purchasable DipTrace BOM for a specified assembly variant and quantity, verify live stock, and assess substitutions. Use for BOM completeness, component sourcing, JLCPCB/LCSC selection, shortages, or procurement preparation; «подбери компоненты», «проверь BOM». Use when the user says “Prepare a purchasable BOM for this DipTrace revision.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# DipTrace BOM and sourcing

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Bring component/nonideality, sourcing and design-course knowledge into BOM review,
substitutions, margins and lifecycle tradeoffs; verify live stock and prices separately.

Prepare an auditable procurement BOM. Catalog searches and local documents are in
scope; purchasing or changing the circuit requires authorization for those actions.

## Baseline

1. Resolve schematic/PCB revision, assembly variant, fitted/DNP state, board count,
   assembler, and allowed substitutions from the request and project.
2. Discover live MCP tools, then use `get_document_info`, `run_bom_review`, and
   `export_bom`. When both CAD documents exist, use `compare_schematic_to_pcb`.
   Keep source hashes and original exports.
3. Normalize one row per exact manufacturer/MPN/package/variant combination, preserving
   RefDes membership. Record value, tolerance/rating, footprint, quantity per board,
   supplier code, stock/date, unit price/currency/price break, lead time, and evidence.
   Exclude Net Ports and documentary objects. Preserve DNP and hand-assembly lists.
4. Multiply fitted quantity by board count; account explicitly for approved spares,
   attrition, MOQ, and order multiples. If the board count is unknown, complete the
   per-board BOM and leave order totals pending.

## Source and compare

- Search exact installed parts with `query_builtin_library_catalog` first. On a supported
  Windows host, this can export installed component libraries to an XML cache through
  hidden Component Editor without modifying the installed library.
- For missing catalog data, `pipeline_source_component` resolves an MPN/LCSC code and
  writes combined EasyEDA JSON plus an available PDF into an explicit project vendor
  directory. It does not import a native library or reserve stock. Verify the exact
  MPN/package, JSON symbol and footprint records, and actual PDF content; preserve
  returned paths/hashes. Convert geometry only through a supported import or a validated
  project converter, checking units, orientation, pad geometry and pin-to-pad aliases.
  Check official package evidence with [diptrace-datasheet-rules](../diptrace-datasheet-rules/SKILL.md).
- Verify stock, category, current orderability, price breaks, and assembly availability
  on the supplier/assembler's current service. Timestamp results. LCSC warehouse
  stock does not prove JLCPCB assembly stock; cached stock is not a reservation.
- For JLCPCB, prefer Basic, then Preferred Extended, then Extended among technically
  valid choices. Minimize unique types only when ratings, behavior, and packaging
  remain suitable. Use the chosen assembler's rules for other suppliers.
- Evaluate substitutes against function, pinout, package/land pattern, electrical
  limits, tolerances, temperature, dynamic behavior, and relevant firmware effects.
  Include capacitor effective capacitance, inductor saturation/current, and ferrite
  impedance/DC resistance when those characteristics matter to the circuit.
- A shared value or package name is not equivalence. Separate drop-in candidates from
  changes needing a new footprint, schematic, layout, firmware, or qualification.
  Propose an ECO through [diptrace-revision-review](../diptrace-revision-review/SKILL.md)
  when applicable; sourcing by itself does not apply substitutions.

## Deliver

Write `BOM_SOURCING.csv` and a short `BOM_SOURCING.md` (or update the project's
existing equivalents) with shortages, unresolved identities, proposed substitutions,
quantity arithmetic, cost assumptions, and timestamped sources. Use a CSV library,
not string concatenation, and preserve identifiers and units.

Reconcile all fitted RefDes with CAD and disclose stock/price uncertainty. Mark order
readiness BLOCKED for unresolved required parts or variant ambiguity. Recheck time
sensitive facts at order time and pass the resolved BOM to
[diptrace-production-pack](../diptrace-production-pack/SKILL.md).

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
