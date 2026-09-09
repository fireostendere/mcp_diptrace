# DipTrace MCP platform review — 2026-09-09

## Scope and provenance

Baseline: `main` at `24d4106ca7436cc2f1a052885b289bb48bffe734`.
Work is isolated on `astra`; no main-branch merge or native release is implied.
This is an AI-assisted engineering review and implementation, not independent
human approval. New test cases are synthetic and do not promote fixture trust.
No files under `tests/fixtures/acceptance/` or trusted provenance entries were changed.

The review covered the platform architecture and public contract, selected
high-risk implementations, the complete automated regression suite, packaging
and static gates. It is not a claim that every line has been independently
certified or that native DipTrace/Windows/macOS acceptance was executed here.

## Architectural assessment

The existing repository is a substantial guarded EDA backend, not an empty MCP
wrapper. Keep its secure XML/raw-tree writer, source-SHA transactions, rollback,
policy/allowed-root enforcement, provenance boundary, bounded process jobs,
read-only installed-library bridge and deterministic PCB/schematic engines.
Replacing these with a second framework would increase risk without improving
PCB correctness.

| Area | Evidence inspected | Assessment / decision |
| --- | --- | --- |
| MCP and application layer | `server_runtime.py`, `service.py`, `services/`, tools snapshot and event-loop tests | Keep the stable facade and 167-tool default contract. Do not publish a tool per heuristic. |
| XML and writes | `xml_document.py`, semantic compiler, transactions, sessions, source-SHA tests | Retain preview/apply boundaries, raw unknown XML preservation and stale-input rejection. |
| Engineering evidence | provenance registry, rule packs, trust/evidence tests | A caller-supplied fact is not native acceptance. Preserve missing facts as unknown. |
| Libraries and electrical identity | `library_mutation.py`, `library_mutation_api.py`, `synchronization.py`, `design_compare.py` | Correct explicit pin/pad validation; remove positional mapping guesses and false match paths. |
| PCB generation | A-D intent/placement/routing layers, `pcb_whole_board.py`, quality tests | Retain bounded candidate planning; fix outline compaction before adding more optimizers. |
| Assembly handoff | BOM, readiness, export services and resource store | Unify population semantics; add source-bound preflight and artifact integrity. |
| External tools/runtime | process runner, jobs, cache, headless/bridge and installer tests | Keep bounded output/cancellation and per-platform tests. Native execution remains separate evidence. |
| Presentation | optional cinematic subsystem and repository house rules | Keep optional; recordings are not engineering or manufacturing acceptance. |
| Distribution/docs | pyproject, allowlist/build audit, development guide, CI | Remove stale commands/version text; preserve package, privacy, provenance and discovery gates. |

## Reproduced defects and corrective changes

Severity is engineering impact, not a CVSS score.

### P1 — Pin/pad validation accepted inconsistent pairs

`validate_explicit_pin_pad_mapping` separately checked whether PadId and
PadNumber existed anywhere in the footprint. A pin could therefore reference
one pad ID and another pad's number and still pass validation. Duplicate pattern
styles were silently reduced to the last definition.

The shared `pin_mapping.py` now checks the ID/number pair on the same pad,
rejects ambiguous definitions, accepts the documented PadIndex alias, and
rejects conflicting PadId/PadIndex values. A malformed section is not partially
certified. The library mutation preview uses this same validator.

### P1 — Single-part synchronization guessed electrical mapping

`build_sync_plan` assigned the Nth schematic pin to the Nth footprint pad. A
single-part component can have any pin-to-pad permutation; having the same pin
count does not make that mapping correct. It also invented pad numbers when
neither footprint data nor explicit numbers were available.

Connected pins now require exact embedded-cache bindings or caller-supplied
`pin_map` entries. The cache resolver uses ComponentStyle/ComponentPart, validates
pin counts and actual PadId/PadNumber pairs, and supports section-local indices
for multi-unit components. Literal cache-key lookup rejects malformed, Unicode
and oversized index strings without integer coercion. Missing or ambiguous
evidence does not fall back to pin order. Existing explicit mappings and guarded transactions remain available.

**Compatibility change:** older callers relying on implicit positional mapping
must provide a reviewed `pin_map`. See `DEVELOPMENT.md` for a synthetic example.
Unconnected component placement is still possible when footprint data is present.

### P1 — Comparison could report false electrical matches

The previous comparator overwrote duplicate/empty net names, collapsed unknown
endpoint owners to `?`, and compared symbol pin indices directly with PCB pad
IDs. Two equally malformed inputs could therefore appear to match.

Comparison now uses verified physical pad numbers, preserves all duplicate-name
endpoint data while marking it ambiguous, rejects unresolved owners/mappings,
checks explicitly declared NetId/no-connect contradictions, and reports both
source hashes. `matches=true` requires a complete comparison. Ambiguity output
is bounded to 200 entries with an exact total and truncation flag.

This remains comparison of exported logical membership, not a proof of routed
copper continuity, hierarchy alias equivalence, ERC, or correct datasheet intent.

### P1 — Board-outline compaction could cut away occupied geometry

Compaction omitted via annuli, existing pours and text bounds. A synthetic
freestanding via was left outside the resulting board. The rectangle detector
also accepted a self-crossing bowtie with the same four extrema.

The occupied-bound calculation now includes vias, pours and markings; incomplete
bounds or cutouts cause a conservative skip. Rectangle edges must be nonzero and
axis-aligned. Compaction never expands the mechanical boundary. Existing corner
order, winding and point-container metadata are preserved instead of clearing
and rebuilding the point list. Returned bounds describe the serialized result.
Non-finite dimensions are rejected at the package-function boundary as well.

Bounding boxes can still be approximate when source geometry is incomplete;
these candidate edits do not replace mechanical review or native DipTrace DRC.

### P2 — Assembly population disagreed across outputs

`include_dnp=false` filtered the BOM but not placement CSV. Readiness used a
second DNP parser that ignored `DNP=dnp` and `Populate=no`, and did not recognize
the BOM's manufacturer aliases.

BOM extraction is now the population/procurement source for readiness and
placement. Both outputs honor the same include-DNP flag. Missing assembly
reference designators are explicit blockers rather than silently usable rows.
The manifest records included component count and excluded reference designators.

### P2 — CSV escaping corrupted negative numeric coordinates

A leading minus sign was escaped even on actual floats/integers, producing
non-numeric placement cells. Conversely, whitespace-prefixed spreadsheet
expressions could bypass the text guard.

Finite numeric cells retain numeric syntax. Untrusted text receives the formula
prefix guard, including leading whitespace/control-character cases. NaN and
infinity are rejected. Spreadsheet re-saving is not claimed to preserve this
protection, and the generic placement format still needs assembler convention
review.

### P2 — Export integrity and read bounds were incomplete

Release data had no byte-identity inventory and artifact size was checked only
after reading the whole file. Version-2 review manifests now carry per-artifact
SHA-256 and byte sizes; resource reads detect changed content and use bounded
reads. The manifest is checked against the saved export record, not self-hashed.
Legacy records remain readable. This protects against accidental artifact edits,
not an attacker able to replace both the record and its checksums.

### P3 — Stale development instructions

The development guide still named 0.3.0 and two scripts that no longer exist.
It now names 0.4.0, identifies the server shim/runtime correctly, removes dead
commands, and documents the changed electrical and handoff contracts.

## Added functionality, without additional MCP tools

Existing assembly/fabrication export calls now return a coherent review bundle:
BOM, placement, stackup, board geometry, `preflight.json`, and a versioned manifest.
The preflight joins existing readiness checks with explicit ratlines and source
identity. Known blockers produce `blocked`; otherwise it returns
`manual_review_required`, never a fabrication approval. Offline geometric DRC
and native acceptance are explicitly marked not run by this export operation.

Electrical comparison and synchronization share the same explicit cache resolver,
including multi-unit section indices and non-positional pin permutations. This
adds useful automatic operation where evidence exists while refusing guesses.

No embeddings, RAG search, web scraping, model inference or agent loop was added.
OpenCode/mcp-rag owns retrieval, interpretation and orchestration. DipTrace MCP
owns typed operations, deterministic checks, guarded state changes and evidence
about what the tools actually did.

## What still separates this from an ultimate PCB platform

| Priority | Next capability | Required acceptance, not just more code |
| --- | --- | --- |
| P0 | Claim-specific native regression for changed electrical and outline paths | Open/save/reopen/re-export real two-layer and multi-unit samples; preserve nets, pin maps, vias, cutouts and winding; retain exact source/result hashes. |
| P1 | Native manufacturing export adapter | Real DipTrace Gerber/NC drill/assembly export on a version-pinned host, file inventory, origin/layer mapping and independent CAM review. Existing generic manifests must never masquerade as these files. |
| P1 | Public library-authoring decision | Reuse the existing internal raw-preserving writer, define permissions and preview/apply semantics, then deliberately update public schemas and native-host evidence. Do not build another library editor from scratch. |
| P1 | Resumable project-level PCB build workflow | Compose the existing gate order, source-bound rules, whole-board plan/apply and native acceptance into one state/evidence report. Reuse transactions instead of maintaining a second mutable project state. |
| P1 | Real-board end-to-end benchmark set | Measure schematic-to-PCB fidelity, mechanical constraints, routing completion, return paths, DRC deltas and engineering readability across representative circuits. Synthetic optimizer scores alone are insufficient. |
| P2 | Fabricator/assembler profiles and richer assembly variants | Versioned caller-approved process limits, side/origin/rotation conversions and explicit population rules; test actual vendor outputs rather than invent universal thresholds. |
| P2 | Broader electrical/geometry semantics | Add verified hierarchy aliases, internally shorted/multi-pad pins, arbitrary outlines and complex stackups only with fixtures and native round trips for each supported claim. |
| P2 | Optional narrower discovery/presentation profile | Preserve the existing default contract; measure client token/runtime cost before introducing profiles or removing historical user-requested tools. |

No broad deletion of tested routing, cinematic, installer or evidence subsystems
was justified merely by size. This change removes demonstrably incorrect or
redundant logic and stale instructions instead of replacing it with abstractions.

## Validation record

Executed locally on Linux with CPython 3.13.5 and the declared dev/geometry
dependencies (including the Shapely/GEOS backend):

- Complete regression: **1619 passed, 6 skipped** in 67.83 seconds. This adds
  **49 passing regression cases** against the original baseline. The six skips
  require native Windows Job Objects, desktop objects, PID/path semantics or
  PowerShell; none is counted as a pass.
- Global Ruff check passed across `src`, `tests`, `benchmarks`, `scripts` and
  `plugin`; strict Mypy passed for **136 source files**.
- **19/19 additional gate commands passed**: release metadata, skill-script and
  PCB-skill consistency, public privacy, provenance inventory, compliance
  inventory, event-loop audit, coverage-badge consistency, discovery-size budget,
  complete tools/list snapshot, XML-spec inventory, format coverage, probe-pack
  consistency, synthetic-only fixture-ingest dry run, acceptance-seed audit,
  actual GEOS-backend selection, process-level bridge handshake, wheel/sdist
  build, and release-artifact/allowlist audit.
- The public discovery snapshot remains **167 tools**; this change adds no new
  model-facing tool schemas. Package audit verifies allowlisted files and RECORD
  hashes, not native CAD compatibility.

Native DipTrace open/save/reopen/re-export, native DRC/refill and manufacturing
export acceptance were **not run** in this local environment. The process-level
bridge handshake does not substitute for them. Local Windows/macOS execution was
not performed. A successful coverage-badge consistency check is not a new code
coverage measurement. The PR's final-head CI checks provide the separate
cross-platform and coverage results; they must not be inferred from these local
results or from an earlier commit's green status.

## Primary format/security references

- DipTrace Component Editor XML specification, serializer revision 7276:
  https://diptrace.com/support/tutorials/xml_specs_CompEdit_html/
- DipTrace Schematic XML specification, serializer revision 7276:
  https://diptrace.com/support/tutorials/xml_specs_Schematic_html/
- OWASP CSV Injection guidance:
  https://owasp.org/www-community/attacks/CSV_Injection

These references inform bounded parsing/validation. Reading a newer specification
does not establish compatibility with every DipTrace version.
