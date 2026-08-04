# MCP Tools and Resources

The complete runtime tool list must be requested through MCP `tools/list`.
Actual availability for a particular document, source type, policy profile,
geometry backend, and external-adapter configuration is reported by
`get_capabilities`.

A registered tool is not the same as a universally available operation and is
not a claim of real DipTrace round-trip verification.

## Frozen public contract

The current source tree exposes 159 registered tools. The complete non-null
wire-level `Tool` models are frozen in
[`reference/mcp-tools-list.snapshot.json`](../reference/mcp-tools-list.snapshot.json).
The current canonical snapshot is:

- tool count: `159`;
- canonical descriptor size: `142746` UTF-8 bytes;
- SHA-256: `073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`.

The snapshot is generated through the public in-memory MCP transport rather
than FastMCP internals. CI rejects unregenerated contract drift.

The service layer separately freezes all 157 public `DipTraceService`
signatures and 148 explicit Facade-to-domain-service delegations in
`reference/service-facade-contract.json`.

## Input schemas, units, and errors

All public geometry distances are normalised to millimetres regardless of the
source document's `Units` literal.

Complex object parameters use named schema-backed models. Shared schemas are
available through `diptrace://schemas/tool-inputs`; compact inline parameters
carry their corresponding `x-diptrace-schema` URI.

MCP failures use a bounded structured envelope with:

- stable public error code;
- safe bounded details;
- retryability status.

Internal exception messages and causes are not returned to clients.

Opaque IDs are provenance-bound. Object IDs come from query/model tools;
transaction, plan, report, export, and job IDs come from their respective
create/run tools. Callers must not invent them.

## Write contract

Where exposed, `dry_run=true` is the default and must not modify design bytes.
A real write requires `dry_run=false` and the exact `expected_sha256` returned
by the relevant inspection or preview.

Creation of a new target needs no target SHA. Replacing an existing target
requires:

- `overwrite=true`;
- the current target `expected_sha256`;
- backup capture;
- reparse and write-impact validation;
- atomic replacement.

For seed copies, `expected_seed_sha256` protects the seed input independently
from the target's `expected_sha256`.

`finish_live_session(action="apply")` requires the current working-document
SHA. The server checks it before publishing the finish marker and the bridge
checks it again before replacing the external exchange file. `cancel` requires
no hash and must not replace the exchange XML.

Every semantic transaction, raw XML edit, scaffold/seed write, overwrite, and
live apply passes a conservative impact gate over normalised objects plus exact
XML elements. These views may overlap; refusal is preferred to undercounting.

## Read and query

The read surface includes:

- status, capabilities, document information, and discovery;
- normalised PCB, schematic, Component Library, and Pattern Library models;
- selectors, stable IDs, object reads, and spatial queries;
- connectivity, components, nets, rules, stackup, via styles, and XML fragments;
- BOM, copper pours, unrouted connections, route details, and text objects;
- net lengths, differential pairs, and preliminary impedance analysis;
- component/pattern library lookup and validation.

Unknown XML remains available through bounded fragment reads and is preserved
outside targeted write regions.

## Review and analysis

The analysis surface includes:

- bounded board/schematic/connectivity/DRC/ERC review;
- BOM, assembly, DFM/DFA/DFT, thermal-metadata, and design comparison;
- persistent findings with explicit skipped and partial categories;
- placement scoring and congestion analysis;
- NetClass-aware routing and trace-clearance resolution;
- return-path, differential-pair, length/skew, and preliminary SI helpers;
- typed optional Freerouting, ngspice, and openEMS jobs.

These tools do not provide fabrication, assembly, regulatory, or universal
engineering sign-off. The authoritative coverage matrix is
[`REVIEW_ENGINE.md`](REVIEW_ENGINE.md).

## Semantic writes

Implemented high-level writes include:

- synthetic PCB/schematic creation and seed-based document creation;
- component/part move, rotate, side, lock, value, properties, pattern,
  alignment, distribution, and grouping;
- board-text position, rotation, visibility, and style;
- schematic sheets, parts, pin connectivity, wires, labels, and no-connect;
- additive and guarded exact schematic-to-PCB synchronisation;
- NetClass assignment/rules, trace widths, via styles, and length constraints;
- panelisation parameters;
- standalone test points;
- trace/via primitives, local routes, multi-net routes, and differential-pair
  routes;
- stored placement, silkscreen, route, and external-router plans;
- expert raw XML edits.

High-level writes use preview/transaction, expected SHA, reparse, bounded
checks, backup, commit, and rollback. Raw XML editing remains an expert escape
hatch.

## Transactions and resources

Transactions expose plan, preview, validation, commit, rollback, and recovery
records. Persistent resources include transactions, plans, findings, jobs,
exports, live sessions, capabilities, schemas, and bounded previews.

Resource identifiers and state transitions are validated before use. Persistent
stores apply bounded retention but preserve active or unverifiable state.

## Placement and routing limits

The local implementation supports:

- deterministic silkscreen and local placement plans;
- multi-layer orthogonal/45-degree routing with bounded vias;
- congestion-ordered multi-net routing with batch-local rip-up/retry;
- atomic centreline-based differential-pair routing;
- DSN export and guarded SES inspect/import.

It does not implement push-and-shove, arbitrary free-angle routing, global
optimisation equivalent to a full EDA engine, or native DipTrace autorouter
control.

## Trust and evidence boundary

User-controlled files, sidecars, hashes, and evidence manifests cannot mint
package-owned high trust. User-supplied evidence tools can validate and record
bounded comparison metadata, but remain classified as user supplied and
requiring DipTrace verification.

The capability layer intentionally does not claim complete trust-invalidation
coverage for:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

Q1 Component Angle GUI/re-export evidence remains `NOT_RUN`; rotation results
retain a structured warning.

## Runtime and transport

The server supports:

- MCP stdio;
- loopback Streamable HTTP;
- offline XML workflows on Windows, Linux, macOS, and WSL;
- live DipTrace exchange through the Windows executable bridge.

Streamable HTTP is intended for trusted local loopback use. OAuth, remote
multi-user isolation, and a hosted service boundary are not implemented.

## Version and publication status

The source/package version is `0.2.0`. The latest published GitHub release is
`v0.1.2`. The 0.2.0 installer and portable assets build in CI but are not public
release downloads until `v0.2.0` is tagged and published after the remaining
human acceptance gates.