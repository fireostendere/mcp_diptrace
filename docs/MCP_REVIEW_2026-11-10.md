# MCP server review — 2026-11-10

Dated record. Scope: the server itself — the 152-tool public surface, the guarded
write path and the offline analysis engines — reviewed on `main@3041f00`. The skill
catalog was reviewed separately in [SKILL_REVIEW_2026-11-10.md](SKILL_REVIEW_2026-11-10.md).

Method: three independent read-through reviews, each finding reproduced in-process on
copies of `tests/fixtures/*` or the repository boards unless marked *read only*.
Nothing here is native DipTrace evidence. Open items are tracked in
[TECH_DEBT.md](TECH_DEBT.md) and scheduled in
[the project roadmap](../documents/ROADMAP.md) under the `B` numbers given below.

## Fixed in this pass

| Area | Defect | Fix |
| --- | --- | --- |
| Safety | `pipeline_nativeize_document`, `pipeline_render_board_preview` and `pipeline_source_component` wrote outside the allowed roots and under the `read_only` policy; nativeize replaced an existing file with no SHA or backup | The tools resolve every path through the allowed roots, require write (and external-execution) policy, and nativeize refuses an existing output. The catalog query is URL-quoted and `curl` globbing is off |
| Write path | A semantic commit in a live session failed with `Path is outside allowed roots` whenever the state directory was outside the workspace, which is the installed layout | Commit and rollback accept the confined session working copy |
| Write path | `delete_wire` left branch wires pointing at the deleted wire; `connect_pins(allow_reconnect=true)` and `disconnect_pins` left a wire of the old net on the moved pin | A batch that adds such a dangling wire end is refused with `connectivity_conflict`; deleting trunk and branch in one batch still works |
| Review | `run_review` with a board profile on a schematic (or the reverse, or a library) returned a clean, complete report | The profile must match the document kind |
| Review | Net Port symbols were BOM rows (62 rows for 18 parts on the ATtiny board), raised `schematic.bom_identity` warnings, and were reported as components missing on the PCB | Net Ports are excluded from the schematic BOM, the BOM identity check and `compare_schematic_to_pcb` |
| Review | `analyze_release_readiness` ignored exported unrouted connections | Exported ratlines are a `release.unrouted_connections` error |
| Gate | `pcb_quality_gate.py` dropped gate rows whose status cell was annotated (`PASS*`, `FAIL (10 chains)`), so they could not block | The whole status cell is read; an unknown status blocks |
| Surface | `scan_diptrace_documents` did not list `.dipxml` / `.dchxml` | Both suffixes are scanned |
| Surface | `path_exists` and `write_object_limit_exceeded` surfaced as `INTERNAL_ERROR`; inverted width bounds in `suggest_trace_geometry_for_impedance` raised a bare `ValueError` | Mapped to `CONFLICT` / `VALIDATION_ERROR`; the bounds error is `INVALID_ARGUMENT` |
| Docs | Nine evergreen documents still stated 167 or 170 tools, and the drift checker only required the right number to appear somewhere | Counts corrected; `check_documentation_state.py` now rejects any other tool count in an evergreen document |

## Closed after this record

- **B1**: `connectivity.copper_connectivity` groups each net's pads by exported trace
  copper. The board gate enables it (`verify_copper_connectivity`): an open net is the
  hard error `open_copper_nets`; pads joined only through a pour are disclosed as
  `pour_connectivity_unverified` (native refill decides). It stays off for candidate
  ranking, where parts are moved away from their traces hypothetically. Layers are
  ignored, so same-net copper overlapping on two layers without a via counts as joined.
  The gate still does not run `run_checks`: its overlap findings on the accepted
  ATtiny board need triage first.
- **B2**: the odd/even impedances use the air-line impedance in the coupling term and
  each mode's own effective permittivity — the structure of the Kirschning-Jansen
  static form on the page the module already cites. Reference geometries now give
  123.0 / 94.3 / 122.4 Ω and a wide gap converges to twice the single line. Stripline
  plane separation includes the signal copper thickness. Not validated against a field
  solver.
- **B3**: pads/vias without geometry and components with a stand-in box are reported
  as partial skips (`pad_geometry_unavailable`,
  `component_pattern_geometry_unavailable`). Stand-in boxes stay in the overlap check
  because placement planning relies on it.
- **B4**: an unrouted net has no routed length (`net_unrouted`), the pair length
  tolerance is skipped, and `within_tolerance` is `null` without a tolerance or copper.
- **B5**: without an MPN, supplier order codes are part of the BOM grouping key.
- **B6**: stitching coverage samples a coarser grid on large boards instead of
  returning nothing; a trace outside the outline fails the edge check. Silkscreen box
  rotation/mirroring stays open (no fixture to verify against).

## Open findings

### Engineering correctness (false PASS first)

- **B1 — copper connectivity.** Headless QC counts only exported `<Ratlines>` and the
  connectivity check flags a net only when it has no trace at all. A board with every
  trace removed has `hard_error_count == 0`; a net missing one of four traces has no
  finding. The board-stage gate does not run `run_checks`, so it also misses the
  overlap/edge errors that check reports.
- **B2 — differential microstrip impedance.** The coupled-microstrip odd/even
  impedance uses the dielectric-loaded line impedance where the model needs the air
  impedance. Reproduced overestimates: +23 % for 0.35/0.2 mm on a 1.5 mm dielectric,
  +4…5 % on thin dielectrics, with no warning. The comparison values came from an
  independent implementation written for this review, not from a field solver, so the
  fix must be validated against a cited source or the openEMS adapter first. Stripline
  plane separation also omits the copper thickness (*read only*).
- **B3 — skipped geometry reported as checked.** Pads without geometry are filtered
  out before the trace-to-pad clearance check can count them as skipped (54 of 701
  pads on the DUT controller board). Components without an embedded pattern are
  checked for overlap on a 1×1 mm placeholder box.
- **B4 — length checks on unrouted nets.** `measure_net_lengths` returns 0.0 with
  status `available`, and a differential pair with no traces passes its length
  tolerance. `analyze_length_group` reports `within_tolerance=true` when no tolerance
  was given.
- **B5 — BOM grouping without MPN.** Two capacitors with the same value and pattern
  but different supplier part numbers merge into one line carrying the first one's
  fields.
- **B6 — smaller geometry gaps** (*read only*): the stitching-coverage check
  silently returns nothing above 4096 sample points; silkscreen text boxes ignore
  rotation and bottom-side mirroring; the trace-to-edge check accepts a trace wholly
  outside the outline.
- The ATtiny schematic has nets whose pin items name part ids that no part carries
  (for example net 13 → part 66). `compare_schematic_to_pcb` reports them as
  `unresolved_endpoint_owner`; the cause was not investigated.

### Write path

- **B7 — transaction staging semantics.** Calling a write tool with `txid` and
  `dry_run=false` appends the new operations to the previewed ones and commits both
  in one call; re-sending an identical single operation is silently dropped instead
  of staged twice. Gates still run on the combined batch, but the caller never saw
  that preview.
- **B8 — `sync_schematic_to_pcb` does not pin the schematic.** `expected_sha256`
  guards the PCB only, so a schematic edited between dry run and commit is synced
  without a matching preview (*read only*). Needs an `expected_schematic_sha256`
  input, which is a public-schema change.
- **B9 — net lookup by name or XML id.** `connect_pins(net="1")` attaches to the net
  whose id is 1 instead of creating a net named `1`.
- **B10 — `move_via` / `add_via` validation.** Only via-to-pad clearance is checked;
  `move_via(dy=500)` on a 50×30 mm board commits. `_replace_trace` already has the
  full path validation to reuse.
- **B11 — `place_part` without a library definition.** A style that is in neither
  the document library nor `library_component_xml` is committed with any
  `pin_count`.
- **B12 — abandoned previews are never pruned.** Each dry run without a `txid`
  leaves a full document snapshot in a `validated` transaction. Retention
  deliberately keeps every non-terminal record (it may hold a recovery backup), so
  this needs a design decision: an age limit for records that never reached commit.

### Tool surface

- **B13 — no MCP tool annotations.** None of the 152 tools carries `readOnlyHint`,
  `destructiveHint` or `openWorldHint`, so clients must treat every read as a
  possible write. Changes the frozen snapshot.
- **B14 — capability report vs behaviour.** `get_capabilities` says
  `net_class_rules=false` on a schematic while `assign_nets_to_class` accepts it;
  `list_testpoints` and `review_testpoint_coverage` answer on a schematic instead of
  refusing. There is no tool → capability-key map, and the pipeline tools have no key.
- **B15 — shared state directory.** A second server on the same per-user state
  directory marks the first server's running jobs `failed/interrupted`; `cancel_job`
  racing with completion can leave `status=completed, phase=cancelling`. Reproduced
  by forced interleaving in one process.
- **B16 — envelope and argument strictness.** Nine read tools return no `ok` key on
  success; `pipeline_render_board_preview` on a schematic returns `ok=false` with a
  string error as a normal result; unknown arguments are silently dropped
  (`reconciliation_mod="exact"` runs additive); write tools publish `selector` as
  optional but always require it; more domain codes are unmapped (`invalid_request`,
  `document_too_large`, `session_lock_*`, `backup_state_invalid`, …).
- **Q1 component angle status disagrees.** Documents record the Q1 campaign as PASS;
  `evidence_status.Q1_COMPONENT_ANGLE_LIVE_VALIDATED` is still `False`, so
  `rotate_components` and `get_capabilities` keep warning. One side is stale; the
  flag was not changed because it is a source-controlled evidence gate.

## Missing tools

What a full schematic → PCB → release run cannot do through MCP today. No skill
names a tool that does not exist; each gap is worked around by a CLI, a Python API
or raw XML edits.

| # | Gap | Current workaround | Size |
| --- | --- | --- | --- |
| G1 | Native refill + DRC, native ERC, native open/save/re-export as tools or jobs | Local CLIs (`pcb_native_acceptance`, `schematic_native_acceptance`, `native_xml_export`) | M |
| G2 | Native Gerber X2 / NC Drill / pick-and-place export | `native_cad` Python API; `export_fabrication_outputs(request_native_outputs=true)` always fails | M |
| G3 | Copper pour create/edit/delete (`list_copper_pours` only) | Internal `copper_pours.add_copper_pours`, build scripts | S–M |
| G4 | Free GND stitching vias (`add_via` needs an existing trace segment) | Internal stitching in the whole-board pipeline | M |
| G5 | Board outline, mounting holes, cutouts, keepouts after creation | `create_pcb_document` scaffold only | M |
| G6 | Schematic deletes: part, sheet, net label, net; PCB component removal | `apply_xml_edits` | S each |
| G7 | Board text add/delete/set content | none | S |
| G8 | Create/delete net class, differential pair, via style; write DRC rules/stackup | Seed document | M |
| G9 | Stage quality gate and headless QC as a tool | `scripts/pcb_quality_gate.py`, checkout only | M |
| G10 | Paginated schematic readers (sheets, wires, labels, ports) | Unbounded `get_schematic_model` | S |
| G11 | Public wire planner for `add_wire` | Caller supplies every point | M |
| G12 | `place_builtin_component` inside a transaction (`txid`) | Separate commit per Net Port | S |

Every one of these adds or changes public tools, so each goes through the M12
product/API decision and an intentional snapshot update.

## Not checked

`_apply_sync_schematic_to_pcb` internals; live-session finish and exchange binding
with a real bridge; the differential-pair router; bottom-side pad mirroring (no
repository board has bottom-side parts); outline arcs and cutouts; external adapters
with real Freerouting/ngspice/openEMS binaries; `pipeline_source_component` against
the network; whether DipTrace itself tolerates the XML that the now-refused wire
edits used to produce.
