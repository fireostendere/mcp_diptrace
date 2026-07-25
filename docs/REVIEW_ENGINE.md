# Review Engine

Checks are registered in `CheckRegistry`. Each check returns deterministic `Finding`
objects and metrics, or an exact reason why it was skipped. `FindingStore` persists a
report keyed by document SHA.

## PCB Checks v1

- component overlap and edge clearance, with conservative bounding-box placement checks;
- trace-to-trace clearance, trace-to-edge clearance, and minimum width;
- spatially filtered trace-to-pad, trace-to-via, and trace-to-copper-pour
  clearance. Pour checks use the exported boundary polygon and the applicable
  DRC `TraceToCopper` value; same-net and other-layer pours are excluded, and a
  missing layer rule is disclosed rather than inferred;
- via drill size and annular ring;
- nets with multiple exported endpoints but no trace records, and trace records with fewer
  than two points or zero path length; these narrow structural checks do not prove full
  connectivity or detect electrically dangling trace endpoints;
- silkscreen overlap; silkscreen-to-pad clearance is not implemented and is reported as
  a structured `not_implemented` skip;
- stackup completeness and differential-pair rules;
- test-point coverage;
- BOM identity, assembly pattern geometry, and explicit thermal metadata.

## Schematic Checks v1

- unconnected pins, including intentional no-connect markers;
- missing values, duplicate unit/RefDes metadata, and BOM identity;
- electrical conflicts only when electrical pin types are available.

Tools aggregate registry checks by category: `run_drc`, `run_erc`, `run_board_review`,
`run_schematic_review`, and manufacturing, assembly, testability, BOM, and thermal reviews.

## Finding Contract

A finding contains ID, check, category, severity, confidence, explanation, object and net
references, layer, location, bounding box, measured and required values, delta, rule
source, suggested actions, and suppression state. A report contains metrics, assumptions,
skipped checks, completeness information, and a resource URI.

## Heuristic Analyses

- Return-path analysis uses adjacent stackup layers, pour boundaries, and return-via proximity.
- Plane continuity does not treat a pour boundary as authoritative refilled copper.
- BOM and design comparison documents assumptions about pin indices and pad identity.
- Thermal checks are skipped when explicit power metadata is unavailable.

Without the `geometry` extra, complex rotated-pad pairs are explicitly skipped rather
than reported with a false exact result. Pour boundaries use exact GEOS polygon distance
when the extra is installed and a conservative AABB fallback otherwise. Pour findings
always carry `pour_geometry: "boundary_only"` and identify exact versus approximate
geometry; they do not claim that the boundary equals refilled copper. Exact shorts,
isolated refill, mask dams, paste, tombstoning, complete thermal analysis, and complete
SI analysis are not implemented.
Offline review does not replace DipTrace DRC/ERC or fabrication-house checks.
