# Review Engine

Checks are registered in `CheckRegistry`. Each check returns deterministic `Finding`
objects and metrics. A wholly unavailable check returns a structured skip reason; a
partially supported check can instead disclose skipped geometry in its metrics.
`FindingStore` persists a report keyed by document SHA.

## NetClass clearance disclosure

Current status: `implemented for routing and trace-to-trace review; partial for
trace-to-object and placement clearance`.

The shared resolver reads per-layer `DRC/LayClearances/LayClearance.TraceToTrace`
board defaults and the `Clearance` value under each affected
`NetClasses/NetClass/LayProperties/LayProperty`. For every route, it applies the
monotonic precedence:

```text
required = max(board default, every affected NetClass rule)
effective = max(required, explicit requested clearance)
```

An explicit value can increase the effective clearance but cannot lower a
mandatory rule. A missing NetClass assignment falls back to the board default.
An unknown class reference fails closed for routing with `unknown_net_class`; the
offline review skips that pair and reports the unresolved class in structured
metrics. A missing rule with no explicit value also fails closed rather than
guessing. No object-specific clearance is currently passed into this shared
resolver; trace-object and placement rules remain the separate partial paths
described below.

This resolver is used by `route_connection`, `route_net`, `route_connections`,
differential-pair routing, congestion ordering, route plans, and the
`pcb.trace_clearance` offline check. `pcb.trace_object_clearance` and placement
clearance still use their DRC/geometry-specific rules and do not apply NetClass
clearance; their results expose `netclass_rules_ignored: true`. Board-edge
clearance is a separate geometry rule.

### Trace-to-trace completeness

`pcb.trace_clearance` does not treat a trace with an absent or unresolved
owning net as compliant. Each candidate pair is counted in
`candidate_pairs_checked` and then in exactly one of `evaluated_pairs`,
`skipped_unresolved_net_pairs`, or `skipped_clearance_resolution_pairs`.
Unresolved pairs produce no violation finding because no safe effective rule was
calculated, but they set `clearance_review_complete: false`, add a stable
`warning_codes` value, and appear in report-level `skipped_reasons` with safe
unresolved-net/class details. Detailed pair reasons are bounded by
`MAX_SKIPPED_PAIR_REASONS`; `skipped_pair_reasons_total` and
`skipped_pair_reasons_truncated` disclose omitted detail records. A missing rule
set returns a whole-check partial result without enumerating quadratic same-layer
pairs; `candidate_pairs_not_enumerated: true` makes that boundary explicit. A
skipped pair is never counted as evaluated or compliant.

`netclass_rules_ignored` is reserved for paths that actually ignore or cannot
resolve NetClass rules. An absent owning net still makes the clearance review
partial, but it does not by itself claim that a NetClass rule was ignored.

Trace-clearance findings publish the compact `rule_source` label plus the
project-authored `rule_sources` records from the shared resolver. The records
contain only source kind, layer/net/class identifiers, normalized millimetres,
and a stable project rule path. `clearance_rule_status.effective_rule_source`
and the resolution's requested/required/effective values explain whether the
effective result came from board defaults, NetClass rules, or an explicit
request. The router and review use the same resolution object and expose the
same effective source label; this remains an offline structural review, not a
DipTrace DRC sign-off.

Affected routing, planning, congestion, and review results contain
`requested_clearance_mm`, `required_clearance_mm`, `effective_clearance_mm`,
`clearance_sources`, `netclass_rules_applied`, `netclass_rules_ignored`, and
`clearance_rule_status`. Capability metadata also lists the partial paths. These
results are not a full DipTrace DRC or fabrication sign-off.

## Coverage Status

The table below is a representative release-review matrix, not a fabrication-house
capability table. It deliberately separates the checks implemented by this repository
from common categories that still require DipTrace, output-package inspection, a
fabricator's rule deck, or engineering review.

- **Implemented** means the named registered check covers the stated, narrow scope using
  exported XML and, where applicable, the document's own DRC rule. It does not mean that
  a fabrication process has accepted the result.
- **Partial** means the code uses a narrower structural check, an approximation, or only
  the geometry present in the export. The limitation in the last column is part of the
  result contract.
- **Missing** means there is no registered check. A report with no finding must not be
  interpreted as a pass for that category.

| Release-review category | Status | Registered check / behavior | Exact boundary and disclosure |
| --- | --- | --- | --- |
| Minimum trace width | Implemented | `pcb.min_trace_width` | Compares exported segment widths with `DRC/LaySizes/LaySize.MinTrace`; skips layers without that rule and does not substitute a fabrication-house limit. |
| Trace-to-trace clearance | Partial | `pcb.trace_clearance` | Measures straight exported centerline segments and their widths on the same layer against `TraceToTrace`; curved/arc copper is not reconstructed. |
| Trace-to-pad and trace-to-via clearance | Partial | `pcb.trace_object_clearance` | Uses exact Shapely shape distance when geometry is available. Without the geometry extra, unsupported non-circular shapes are counted as skipped geometry. |
| Pad-to-pad, pad-to-via, and via-to-via clearance | Missing | none | These copper-pair classes are not covered by `pcb.trace_object_clearance`. |
| Trace-to-board clearance | Partial | `pcb.trace_board_edge` | Checks straight trace segments against the exported polygon outline and the document rule; pads, vias, pours, slots, and cutouts are outside this check. |
| Component crossing the board outline | Partial | `pcb.component_edge` | Tests conservative component/test-point bounding-box containment. It is not a component-to-edge clearance check. |
| Same-side component overlap | Partial | `pcb.component_overlap` | Intersects conservative bounding boxes, not authoritative body, courtyard, height, or keepout geometry. |
| Via drill and annular ring | Implemented | `pcb.via_drill_annular_ring` | Compares exported via hole/diameter data with document `MinDrill`/`MinRing`; it does not add process-specific rules. |
| Non-via holes, slots, and NPTH clearances | Missing | none | No registered manufacturing check covers these features. |
| Copper-pour interaction | Partial | `pcb.trace_object_clearance` and local routing | Uses only the exported boundary polygon, with same-net and layer filtering. Review uses the applicable DRC `TraceToCopper` value and discloses a missing layer rule instead of inferring one. Findings and route results disclose `pour_geometry: "boundary_only"`; the boundary is not authoritative refilled copper. |
| Pour refill, cutouts, islands, and thermal reliefs | Missing | none | Stored fill, refill results, isolated islands, and thermal-spoke geometry are not validated. |
| Routed connectivity, opens, shorts, and dangling endpoints | Partial | `pcb.net_without_traces`, `pcb.degenerate_trace_path` | Detects only a multi-endpoint net with zero trace records and a trace record with fewer than two points or zero path length. It does not prove graph continuity, find shorts, or identify electrically dangling trace endpoints. |
| Silkscreen text overlap | Partial | `pcb.silk_overlap` | Intersects same-side text bounding boxes only; other silkscreen primitives and authoritative rendered glyph geometry are not checked. |
| Silkscreen-to-pad clearance | Missing | structured `pcb.silk_to_pad` skip | Explicitly reported as `not_implemented`; no clean report can imply a pass. |
| Solder-mask expansion, dams, and slivers | Missing | none | Mask manufacturing geometry is not evaluated. |
| Paste apertures, coverage, and stencil webs | Missing | none | Paste and stencil manufacturability are not evaluated. |
| Acute copper, neck-down, and minimum copper features | Missing | none | No acid-trap, neck-down, or minimum-copper-feature check is registered. |
| Differential-pair geometry | Partial | `pcb.differential_pair_rules` | Reviews exported lengths, vias, and parallel same-layer linear projections. Arcs are excluded from coupling/gap estimation, and the result is not a field solution. |
| Physical stackup completeness | Partial | `pcb.stackup_completeness` | Reports missing exported physical fields; it does not validate a fabricator stackup or certify controlled impedance. |
| Test-point presence | Partial | `pcb.testpoint_coverage` | Counts explicit standalone test points on eligible nets. Probe access, fixture mechanics, sensitive-net policy, and electrical suitability still require review. |
| BOM identity | Partial | `pcb.bom_identity` | Checks presence of manufacturer/MPN metadata, honoring explicit DNP metadata. It does not check sourcing, alternates, lifecycle, or assembly-house acceptance. |
| Embedded footprint availability | Partial | `pcb.assembly_geometry` | Checks that a referenced pattern is present in the embedded design cache. It does not validate pin 1, polarity, centroid convention, courtyard, or body height. |
| Assembly collision, polarity, and tombstoning | Missing | none | Conservative component bounding boxes do not implement these assembly checks. |
| Thermal implementation | Partial | `pcb.thermal_metadata` | Reviews explicit power/thermal-strategy metadata only and skips when power metadata is absent; no temperature or heat-flow calculation is performed. |
| Panel and output-package manufacturability | Missing | none | Panel parameters can be edited, but no registered check validates the resolved panel, Gerber, NC Drill, stencil, or vendor package. |

The package-level `copper_pours.py` and `silkscreen.py` authoring helpers do not
change these review classifications. They can request four-spoke thermals,
place distributed stitching vias and avoid known silkscreen obstacles, but the
review engine still cannot promote requested attributes into proof of native
refill/spoke geometry or independently pass `pcb.silk_to_pad`.

## Schematic Coverage

The schematic registry checks unconnected pins while respecting explicit no-connect
markers, empty part values, duplicate unit/RefDes metadata, and BOM identity. Electrical
conflict detection is partial: it reports multiple output-type pins on a net only when
the export carries electrical pin types. It is not a complete DipTrace ERC
implementation, and missing electrical types produce a structured skip.

Tools aggregate registry checks by category: `run_drc`, `run_erc`, `run_board_review`,
`run_schematic_review`, and manufacturing, assembly, testability, BOM, and thermal reviews.

## Finding Contract

A finding contains ID, check, category, severity, confidence, explanation, object and net
references, layer, location, bounding box, measured and required values, delta, rule
source, structured rule sources, requested/required/effective clearance values where
applicable, suggested actions, and suppression state. A report contains metrics,
assumptions, skipped checks, report-level `skipped_reasons`, registry completeness, and
a resource URI. `completeness` is only the fraction of selected registered checks that
did not return a whole-check skip; it does not include unresolved pairs or missing rows
from the matrix and is not manufacturing completeness. Consumers must inspect the
trace-clearance counters and `clearance_review_complete` before treating the report as
complete.

## Heuristic Analyses

- Return-path analysis uses adjacent stackup layers, pour boundaries, and return-via proximity.
- Plane continuity does not treat a pour boundary as authoritative refilled copper.
- BOM and design comparison documents assumptions about pin indices and pad identity.
- Thermal checks are skipped when explicit power metadata is unavailable.

Without the `geometry` extra, unsupported complex pad shapes are explicitly skipped
rather than reported with a false exact result. Pour boundaries use exact GEOS polygon
distance when the extra is installed and a conservative AABB fallback otherwise. Pour
findings identify exact versus approximate geometry and never claim that the boundary
equals refilled copper. Every consumer must inspect both `skipped_checks`, per-check
metrics, and the missing rows above; finding count alone is not a completeness signal.
Offline review does not replace DipTrace DRC/ERC, manufacturing-output review, or
fabrication/assembly-house checks.
