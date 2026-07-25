# Routing Engine

## Local Routing v2

The semantic compiler uses the verified
`Net/Traces/Trace/Points/Point` structure. Segment parameters are stored on the second
point. A routed via is represented by a trace point with `ViaStyle` whose incoming
`Lay` differs from the following segment's `Lay`. `ViaStyle` alone is insufficient:
real DipTrace exports may retain it on same-layer routing points, which must not be
counted as physical vias. Standalone/static vias use
`Components/Component[@Type='Via']`. Trace add, replace, delete, and width operations,
and via add, move, delete, and style operations, pass through one validation path.

The router uses bounded deterministic eight-neighbor A*:

- orthogonal and 45-degree segments;
- layer-aware state `(x, y, layer, direction, via_count)`;
- bend, via, and detour costs;
- swept-segment obstacle expansion;
- different-net copper-pour boundary obstacles on the active layer, with same-net
  exemption;
- explicit preferred, start, and end layers, via style, and maximum-via budget;
- via clearance checks on every layer within the physical `Lay1`/`Lay2` span;
- node, time, and detour budgets;
- deterministic simplification;
- sequential planning for small nets against an updated snapshot.

Route `clearance` is an explicit override. When omitted, the router reads
`DRC/LayClearances/LayClearance/@TraceToTrace` for every requested routing layer and
uses the maximum applicable value. If any requested layer lacks that rule, routing
fails with `capability_unavailable`; it does not fall back to the former hardcoded
`0.2 mm` value or silently use zero.

Legacy `layer="Top", max_vias=0` preserves single-layer behavior. Multi-layer routing is
enabled only with explicit `preferred_layers`, `via_style`, and `max_vias>0`; an unknown
via span is not guessed. When `Lay1`/`Lay2` are absent, fallback is permitted only on a
two-layer board, where the only possible span includes both copper layers. On a
multilayer board the tool returns `capability_unavailable`.

The adapter accepts documented `Size`/`HoleSize` attributes and observed
`Diameter`/`Hole` aliases while preserving the original attributes. A* permits layer
transitions only within the normalized span. The compiler repeats this check
independently for route plans, `add_via`, and `set_via_style`.

When Shapely is installed, A* measures candidate segments against the exported pour
polygon. Without it, the router uses the expanded pour AABB as a conservative obstacle
and reports `pour_geometry_backend: "aabb_approximate"`. Route results affected by a
pour report `pour_geometry: "boundary_only"`. An explicit `CopperPour/@Clearance`
can only enlarge the obstacle when `UseNetClearance="N"`; otherwise the requested
route clearance applies. Neither path reconstructs thermals, cutouts, islands, or
DipTrace 5.3 refill data.

Limitations: no push-and-shove, curves, free-angle routing, dynamic neck-down, or
authoritative copper-refill geometry.

## Multi-Net Routing with Rip-Up/Retry

`analyze_routing_congestion` scores each direct corridor from obstacle count, occupied
bounding-box area, detour allowance, layer options, via constraints, and direct length.
The payload labels this value `score_kind: "uncalibrated_heuristic"` and reports every
arithmetic contribution in `score_terms`. It is an ordering aid, not a physical
congestion measurement or a value that can be compared across boards. In particular,
the existing obstacle-count term contributes 10 points per object and can dominate all
other terms.
`route_connections` uses that deterministic most-constrained-first order by default (or
caller order with `ordering="input"`) for a bounded list of connections (up to 64) against
an evolving document: every routed connection immediately becomes an obstacle for the
next one. When a connection fails, a bounded rip-up/retry pass (default 4 candidate
attempts, hard limit 8) temporarily removes one earlier routed connection of a different
net, routes the failed connection, and re-routes the ripped one. The result is an ordered
list of semantic operations (add/delete traces) that replays through the standard
transactional preview/commit path with the review regression gate. Rip-up candidates are
limited to connections routed inside the same call; pre-existing routing is never ripped.

Limitations: the congestion score is a corridor/bounding-box heuristic rather than a global
router. Rip-up/retry is batch-local and bounded, and push-and-shove is not implemented.

## Coupled Differential Pair

`plan_diff_pair_route` and `route_diff_pair` create one centerline and then generate two
parallel offset polylines with a constant edge-to-edge gap. The compiler atomically adds
both traces and one `DifferentialPairs/Segments/Segment`. Independent `route_net` calls
are not used for the pair.

Each layer transition creates two vias of the same style at symmetric offset positions.
The planner returns positive, negative, and center lengths, skew, layer sequence, and
via balance. Pad pairs must have equal center spacing and compatible orientation.
Uncoupled escape routing, phase tuning, and miters beyond the safety bound are rejected
with machine-readable errors.

## DSN/SES and Freerouting

The bounded DSN serializer first checks geometry compatibility and rejects cutouts,
unsupported pad shapes, pours, or keepouts that cannot be preserved correctly. Until
Q17 is resolved with real DipTrace evidence, quoted tokens are limited to printable
ASCII excluding quote and backslash; spaces are supported by the declared
`space_in_quoted_tokens on` parser mode. Incoming SES quoted tokens containing
backslashes or literal control characters are refused instead of being decoded with an
assumed escape convention. A job stores the DSN, manifest, bounded log, SES, versioned
options, and source SHA in an isolated directory.

Freerouting is started with a fixed argument vector (`shell=false`) and supports timeout
and cancellation. The SES parser creates typed route operations. Import is available
only after inspection, preview, internal connectivity/DRC delta analysis, and a SHA
check. The external router is never treated as authoritative.

Electra, Specctra, and arbitrary CLI execution are not implemented.
