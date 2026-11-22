# 2.0.0 detailed changes (post-v0.4.0 development)

The immutable `v0.4.0` GitHub release and PyPI package were published on 2026-08-16.
Version `2.0.0` collects everything in this section; none of it is part of those released bytes.

## Added

- `apply_plan`: one tool stages or commits any stored plan (component placement,
  schematic placement repair, silkscreen, route or SES import). The plan record
  carries its own type; package-level plan types keep their own guarded apply path
  and are refused;
- nine tools: `add_copper_pours` and `delete_copper_pours` (pour
  boundaries with optional free stitching vias), `set_board_outline`, `delete_parts`,
  `delete_net_labels`, `run_quality_gate` (the handoff gate, now shipped in the package
  as `diptrace_mcp.quality_gate`) and `run_native_check` (the native acceptance, ERC
  and XML-export helpers as background jobs), `plan_add_wire` (read-only bounded
  wire preview and placement feedback), and `run_native_export` (SHA-bound raw CAM
  evidence jobs on private PCB XML copies); `place_builtin_component` accepts `txid`;
- qualified public tool-to-capability mappings, real pipeline capability keys and
  registration coverage validation (B14); capability flags are feature metadata,
  not policy permissions or native acceptance;
- a schematic stage for `scripts/pcb_quality_gate.py`: the handoff's `Gate stage`,
  `Input schematic` and `Current board` lines (or `--stage/--schematic/--board`) name
  what is gated; the schematic stage needs no board and requires a clean, complete
  offline schematic review; AGENTS.md gains reachable per-stage done criteria;
- the reviewed focused-OK "No errors found" image as a second native ERC token for
  Schematic 5.3.0.3;

- one-command Linux and macOS host installation, with real visible DipTrace GUI,
  Linux private-Xvfb headless automation, macOS hidden-Win32-desktop automation,
  and permanent fresh-host CI gates for the bounded release claim;

- candidate-specific PCB quality review covering compactness, centering,
  symmetry, return planes, GND pours/stitching, thermal-relief intent,
  silkscreen mounting-space clearance, hot-loop span and decoupling span;
- a bounded whole-board PCB pipeline that reuses placement, routing, rectangular
  outline compaction, two-layer GND pours/stitching and silkscreen operations;
- source-linked qualitative PCB physics principles and explicit unknown-fact
  reporting instead of guessed current, impedance, thermal or EMC limits;
- SHA-bound structured engineering-rule packs for project, datasheet and
  reference-design facts, with per-rule provenance and redistribution metadata;
- iterative schematic placement repair with objective history, a global
  interconnect strategy (wire/label/bus/power symbol), and conservative reuse of
  intentional existing junctions;
- evidence-report domain summaries/connectivity fingerprints and deterministic
  design-frame quality assessment for PCB/Schematic recording crops.

## Fixed

- the Linux and macOS one-command installers pin the DipTrace build the vendor serves
  today (5.3.5.1). The 5.3.0.3 pin had failed since the vendor replaced the download
  in place in October 2026. Linux now accepts the `DIPTRACE_VERSION`,
  `DIPTRACE_INSTALLER_URL` and `DIPTRACE_INSTALLER_SHA256` overrides macOS already had;
- native PCB DRC no longer passes merely because the dialog class is `TFMyMessage`;
  positive error counts take precedence, and unknown text requires a verified bitmap
  or explicit visual review with the retained PNG/hash;
- XML duplicate-ID diagnostics are scoped to the owning collection, avoiding false
  collisions between pads on different components and points on different traces;
- `plan_add_wire` discovery text is stable across Python 3.12/3.13;
- Windows builds pin patched MCP 1.30.0 and Pillow 13.0.0;
  compliance inventories now include the declared headless-GUI dependencies.

- the three `pipeline_*` tools obey the allowed roots and the active policy (they
  previously wrote anywhere, including under `read_only`), and
  `pipeline_nativeize_document` no longer replaces an existing file;
- semantic commits and rollbacks in a live session work when the state directory is
  outside the workspace, which is the installed layout;
- `delete_wire`, `disconnect_pins` and `connect_pins(allow_reconnect=true)` refuse a
  batch that leaves a wire attached to a deleted wire or to a pin that left its net;
- `run_review` refuses a profile that does not match the document kind instead of
  returning a clean report;
- Net Port symbols no longer appear in the schematic BOM, the BOM identity check or
  `compare_schematic_to_pcb`;
- `analyze_release_readiness` blocks on exported unrouted connections;
- `pcb_quality_gate.py` reads annotated gate statuses (`PASS*`, `FAIL (…)`) and
  blocks on them instead of dropping the row;
- `scan_diptrace_documents` lists `.dipxml` and `.dchxml`; `path_exists` and
  `write_object_limit_exceeded` map to public error codes; inverted width bounds are
  `INVALID_ARGUMENT`;
- the board gate computes copper connectivity: a net whose pads are not joined by
  trace copper is a hard error, and pads joined only through a pour are disclosed as
  needing a native refill;
- differential microstrip impedance no longer overestimates (up to +23 % on thick
  dielectrics); stripline plane separation includes the copper thickness;
- missing pad/pattern geometry is reported as a partial skip; unrouted nets have no
  length and cannot pass length matching; BOM grouping keeps different supplier codes
  apart; large boards keep stitching coverage; traces outside the outline fail;
- a write call with `txid` and `dry_run=false` commits only the previewed operations;
  `move_via` re-validates the dragged trace; `place_part` requires the style and pin
  count of the embedded library; numeric schematic net strings resolve only as
  names, with explicit `xml-id:<Id>` and escaped `name:<literal>` syntax and safe
  duplicate/invalid-reference refusal (B9); abandoned dry-run
  transactions expire by age; servers sharing a state directory no longer fail each
  other's jobs;
- evergreen documents state the current tool count and the drift checker
   rejects any other count ([review](docs/MCP_REVIEW_2026-11-10.md)).
- MCP stdio writes UTF-8 bytes independently of Windows' ANSI text encoding;
  regressions cover CP1252 stdout with Unicode punctuation and Cyrillic text;
- clean Windows headless builds explicitly install and pin Pillow for native
  screenshot capture instead of relying on an incidental environment dependency;
- geometry-enabled frozen servers initialize Shapely/NumPy before tool workers,
  avoiding the observed Windows first-import hang on PCB document reads;
- malformed native CAM ZIP DEFLATE/EOF failures are bounded validation errors,
  not uncaught exceptions.

## Changed

- **breaking (2.0):** Python 3.11 is the minimum. Python 3.10 reached end of life in
  October 2026; the `tomli` fallback dependency and its import branches are gone;
- **breaking (2.0):** the public surface is 151 tools. `apply_plan` replaces
  `apply_component_placement_plan`, `apply_schematic_placement_repair_plan`,
  `apply_silkscreen_plan`, `apply_route_plan` and `import_autorouter_ses`, which all
  ran the same stored-plan path. Removed as pure aliases or filtered views:
  `validate_transaction` (`preview_transaction`), `group_bom` and
  `detect_duplicate_bom_items` (`get_bom(grouped=true)`), `validate_mpn_consistency`
  and `validate_value_pattern_consistency` (`review_bom` finding codes) and
  `validate_pin_pad_mapping` (`validate_library_component`). The mapping is in
  [MCP_TOOLS.md](docs/MCP_TOOLS.md); `get_capabilities` keys are unchanged;
- the packaged skill catalog (capability map 2.6.0) and the workflow prompts name
  `apply_plan` and the surviving BOM and library tools;
- tool, resource and prompt registration moved from one 3000-line function into
  `diptrace_mcp/tools/`, one module per domain. Apart from the removed and added
  tools the published descriptors are byte-identical;
- unreferenced internals are removed: `apply_low_level_edits`, `SemComparisonResult`,
  `Unit`, the `RoundtripEvidenceRecord` alias, `invoke_with_error_boundary`,
  `sha_from_bytes`, an unused clearance resolver and the two legacy single-junction
  reroute helpers. String enums are `StrEnum`, so `str()` returns the value on every
  supported Python;
- the CI discovery budget is measured against the 2.0 surface (91,751 bytes, about
  23k tokens) instead of the `v0.4.0` one;
- the board quality gate runs `run_checks` and blocks on review errors, rather
  than omitting overlap/edge review; skipped board checks remain explicit pending work;
- `run_native_check` uses SHA-checked job-owned copies, supports native binary
  `.dch`/`.dip` XML export, and dispatches source or packaged GUI helpers. Optional
  `startup_dialog_sha256` approvals bind exact operator-reviewed client PNG hashes
  (schematic: up to eight; XML export: one; PCB acceptance: unsupported);
- Q1 code/output distinguishes manual checkpoint PASS from reusable package-public
  evidence, which remains false and grants no high trust;
- native DipTrace 5.3.0.3 jobs now executed all four check variants. Schematic
  acceptance/ERC and binary XML export returned zero; the ERC client image was
   viewed and reads "No errors found". Label deletion preserved the compared
   semantics; R1 deletion after removing all wires lost 22 net memberships on
   native re-export, so its smoke is not connectivity acceptance. The base
   schematic preserved physical pin-to-pad/net/NC records but still has library
   and wire geometry deltas. Pour add/delete and outline copies completed
  refill, DRC (`pass`), save/re-export, but their strict comparison verdict remains
   `FAIL` (22 to 20 endpoint records: GND `J1`/`J2` pad `1` disappeared, plus
   scoped-ID differences); this is not waived.
  The observed asynchronous DRC-progress race is fixed with a narrow bounded wait.
  G2 produced real Gerber/NC Drill/placement files with a complete bounded manifest,
  not CAM acceptance. G11 is implemented;
  B6 and G5/G7/G8/G6 remain BLOCKED pending native-authored references/profiles.
   No version, published release or release authorization is changed;
- a clean frozen Windows build completed all four native checks and CAM export
  through MCP stdio with source SHAs unchanged. Schematic/ERC/XML export and CAM
  helpers returned zero; native-authored PCB acceptance returned
  `HUMAN_REVIEW_REQUIRED` (DRC pass, structural equality, remaining XML semantic
  delta). This does not waive the mutation-copy failures or named-client gates;
- the schematic readability review counts visible markings on automatic alignment per
  sheet (`automatic_markings`) for the native page-fit inspection instead of reporting
  them as missing geometry; the native editor and `place_part` use that alignment by
  default, so the previous classification blocked the schematic-stage gate for every
  such schematic. Genuinely missing or ambiguous exported geometry still blocks;
- the native PCB round-trip (`native_cad`) supports DipTrace 5.3.5.1 next to
  5.3.0.3: it waits until the main form has its menu, and resolves Objects >
  Update All Copper Pours by its menu group because 5.3.5.1 reveals an extra
  Objects item only when the menu opens (a fixed position would have run
  Clear All Copper Pours before DRC);
- schematic native acceptance, native XML export and the schematic Zoom
  Extents step of cinematic recording also accept DipTrace 5.3.5.1. Its menus
  have the same items at the pinned positions, but command IDs shift, so each
  build has its own reviewed profile. The native-windows CI job now runs these
  tools and hidden-desktop PCB acceptance on 5.3.5.1 as a standard user;
- `pcb_native_acceptance --desktop hidden` works again: it records and
  acknowledges the Direct3D startup message that a private desktop shows, and
  waits until the main form has its menu and is enabled before posting commands;
- the packaged skill catalog (capability map 2.3.0) names the native XML exporter
  and the schematic acceptance helper as local CLIs, states the verified 5.3.0.3
  and 5.3.5.1 builds, routes native Gerber/NC Drill/pick-and-place export to the
  Windows-only `native_cad` round-trip instead of an operator-only step, and adds
  Russian trigger phrases to every skill description
  ([review](docs/SKILL_REVIEW_2026-10-09.md));
- the packaged skill catalog (capability map 2.4.0) judges native re-exports by the
  stop rules, routes native schematic ERC to the schematic helper's `--erc`, carries
  the definition of done in `pcb-design-workflow`, names the BOM, length and
  differential-pair tools, groups all 152 tools, and re-pins its source links to
  current `main`; the legacy `.agents/skills` recipes no longer contradict the house
  rules ([review](docs/SKILL_REVIEW_2026-11-10.md));
- after running the skill workflows on the repository's boards: Russian triggers name
  DipTrace, `AGENTS.md` routes all fifteen skills, the reviews list the known skipped
  checks and what clears them, the board recipe states what sync skips, and
  schematic-engineer drops a step with no tool, a duplicated PCB recipe and a provenance
  note ([second pass](docs/SKILL_REVIEW_2026-11-10.md#second-pass-executed-workflows));
- PCB ensemble candidates are now reviewed after their hypothetical operations
  are applied in memory, so hard physical/layout findings affect selection;
- PCB placement scoring now includes board compactness, centering, simple
  repeated-pair symmetry and topology-backed high-di/dt-loop span;
- silkscreen labels prefer closer association, normalize unreadable quarter-turn
  text, may cross solder-masked traces, and still avoid foreign mounting areas,
  pads, holes and vias;
- the two public candidate-ranking tools accept optional validated engineering
  rule packs without adding another MCP tool;
- **breaking:** one contract revision of the 152 tools: every tool carries
  `readOnlyHint`/`destructiveHint`/`openWorldHint`; unknown arguments are refused
  instead of ignored; every successful result has `ok: true`; write tools publish
  `selector` as required; committing `sync_schematic_to_pcb` requires
  `expected_schematic_sha256`; `list_testpoints` and `review_testpoint_coverage`
  refuse a non-PCB document;
- **breaking:** the public surface is 152 tools. Fourteen review-profile tools
  (`run_drc`, `run_erc`, `run_connectivity_check`, `run_board_review`,
  `run_schematic_review`, `run_manufacturing_review`,
  `run_manufacturing_geometry_check`, `run_assembly_review`, `run_testability_review`,
  `run_bom_review`, `run_thermal_review`, `run_silkscreen_check`, `check_silkscreen`,
  `run_component_clearance_check`) become `run_review(profile=...)`; the duplicate
  `analyze_controlled_impedance`, `legalize_component_placement` and
  `set_component_fields` are removed in favour of `validate_impedance_constraints`,
  `plan_component_placement` and `set_component_properties`; `set_diff_pair_rules` and
  `set_length_constraints` fold into `update_net_class_rules`; `unlock_components` is
  `lock_components(locked=false)`;
- FastMCP is used only through its public API: the boundary overrides `tool`,
  `prompt`, `list_tools` and `call_tool` instead of mutating SDK tool objects, and
  stdio and Streamable HTTP are served by a project-owned lowlevel `Server`
  (`protocol_server`) wired to FastMCP's public handlers, so `initialize` reports
  the DipTrace MCP version rather than the SDK's;
- coverage-wave test files are renamed after the modules they cover
  (`test_<module>_edge_coverage.py`); 28 tests that added no unique line coverage
  were removed, keeping total coverage at 93.9%;
- `tools/list` is ~40% smaller: auto-generated schema titles are dropped, optional
  `X | None = None` inputs are published as plain `X`, the units and dry-run
  disclosures are shorter, and `rank_schematic_placement_candidates.config` is
  published through `diptrace://schemas/tool-inputs#/schematic_ensemble_config`;
- `get_board_model` pages are capped at 64 KiB (was 256 KiB) so a page fits common
  client output limits, and `diptrace_status` no longer embeds the full
  `get_capabilities` report;
- the first retention pass runs in a background thread and proves path confinement
  only for deletable records, so the server answers `initialize` without waiting
  for state I/O; repeated document reads reuse the cached model snapshot;
- unexpected internal failures report `details.exception_type` (class name only);
- the stdin transport blocks on its queue instead of polling at 100 Hz, timed
  screen capture and Codex configuration commands have timeouts, and the `mcp`
  SDK is bounded to the tested `<1.31` range because the runtime wraps FastMCP
  internals.

# 0.3.0 detailed release changes

This record preserves the detailed changes included in the immutable `v0.3.0`
unsigned development prerelease. New post-release work belongs in a new section
above this release record.

## Added

### Read-only built-in library bridge

- public `query_builtin_library_catalog` browsing/search over DipTrace's immutable installed catalog;
- public `place_builtin_component` for guarded copy-only placement from a returned catalog ID into a schematic Design Cache;
- isolated Component Editor `.eli` to `.elixml` export with source-SHA preservation, cache reuse, unit conversion and real-DipTrace BSS138 open/save validation;
- no public mutation path for native `.eli` or `.lib` files.

### Schematic intelligence

- deterministic schematic design-intent model with functional blocks and provenance-bearing reference motifs;
- hierarchical schematic placement foundation and bounded multi-candidate placement optimizer;
- non-mutating schematic wire planner with disclosed readability metrics and explicit placement feedback;
- conservative Component Library pin-geometry resolution from the embedded Design Cache;
- pin-aware joint placement/routing scoring for hypothetical candidates;
- bounded non-mutating placement repair driven by route feedback and re-scored by the joint optimizer;
- **atomic selective schematic reroute planner** that identifies only explicit sheet-local nets touched by moved parts, fails closed on unresolved endpoints/routes, and emits one dependency-safe `delete_wire -> move_components -> add_wire` semantic batch for the existing guarded transaction path;
- deterministic schematic ensemble ranking that combines builtin-but-explicitly-labelled readability motifs, pin-aware route quality and bounded placement-grid congestion pressure;
- fail-closed validation for stale/geometrically inconsistent Wire segment references while preserving valid middle-of-segment joins;
- real-DipTrace schematic authoring/readability campaign coverage for cases 01–18, including incremental editing, failed-operation safety, single- and multi-net atomic reroute, obstacle/readability repair and a repaired 22-part stress schematic;
- public MCP tools `rank_schematic_placement_candidates`, `plan_schematic_placement_repair` and `apply_schematic_placement_repair_plan` productizing ensemble ranking and the repair-plus-atomic-reroute pipeline through the stored-plan preview/expected-SHA/transaction path.

### PCB Generations A-D

- **Generation A:** engineering intent, component roles, functional blocks, multi-role net classification, explicit electrical constraints, conservative power/ground topology intent and intent-aware placement v2;
- **Generation B:** exported stackup/reference context, conservative PDN/source/load/decoupling analysis, regulator hot-loop candidates, return-path integration, timing-gated aggressor/victim triage and semantic via roles;
- **Generation C:** deterministic routing-policy compiler, engineering route ordering, observed-route SI checks, copper/topology strategy and bounded placement feedback;
- **Generation D:** bounded whole-board candidate selector with lexicographically dominant hard constraints, decomposed soft metrics and a synthetic engineering-trap benchmark catalog;
- bounded A-D candidate ensemble generation using multiple real Generation-A placement profiles (`balanced`, `critical_nets`, `noise_aware`, `support_compact`) plus the existing-board baseline, with B/C conservative evidence proxies and the existing hard-first Generation-D selector;
- public MCP tool `compare_pcb_placement_candidates` exposing that ensemble as a read-only comparison.
- deterministic smallest-area preference between otherwise equally compatible
  patterns, making compact standard 2.54 mm connectors the default;
- package-level `copper_pours.py` helper for explicit-net Top/Bottom pour
  boundaries, four-spoke thermal intent and bounded distributed GND stitching;
- silkscreen body avoidance enabled by default, hidden-marking filtering and
  assembly-only label suppression;
- compact symmetric 25×12 mm I²C level-shifter PCB example with 14 traces, two
  GND pours and 14 stitching vias.

### DSN/SES and XML analysis

- bounded Specctra structure inventory for DSN/SES-style S-expressions with scope histogram, token/depth limits and exact root validation;
- non-mutating SES compatibility analysis with route length/width/layer statistics, duplicate-net detection, unknown target nets/layers and the existing semantic import planner's importable/skipped classification;
- deterministic XML semantic inventory/fingerprint and structural delta analysis that ignores XML attribute order while preserving element order and unknown XML;
- Hypothesis/property regression coverage for fingerprint invariants and unknown-XML mutation detection.

### Evidence and acceptance automation

- deterministic evidence-report builder and CLI for finalized operator capture candidates;
- evidence reports re-check quarantined artifact SHA-256 bindings, compute XML semantic fingerprints/deltas, render JSON/Markdown, reproduce operator claims/checklists as such, and **never** grant provenance trust, fixture trust, release acceptance or PASS automatically.

### Component/Pattern Library API preparation

- stable package-level `LibraryMutationRequest` / preview contract over the existing raw-preserving mutation core;
- required expected-SHA binding, deterministic semantic delta/inventory output and explicit pin/pad mapping validation;
- the contract is intentionally **not** registered as a public MCP tool yet; public registration remains a separate API/product and contract-snapshot decision.

### Cinematic presentation mode

- deterministic cinematic timelines with `cinematic`, `timelapse`, `tutorial` and `gif` pacing presets;
- Windows desktop replay host with bounded cursor/click/hotkey/text/path actions and dry-run support;
- version/editor-specific `DipTraceUIProfile` persistence and readiness validation;
- affine DipTrace design-coordinate to normalized client-coordinate calibration with residual checks;
- normalized live cursor probing for one-shot UI calibration;
- semantic Schematic part/wire replay and PCB Generation A placement replay;
- same-layer PCB trace replay with fail-closed refusal of unsupported via/layer transitions;
- HWND-targeted ffmpeg capture plus MP4/GIF post-processing helpers;
- cinematic manifest preflight with deterministic content fingerprint, timing consistency checks and explicit cue/payload/desktop-command/path/text/hotkey safety budgets.
- isolated hidden-desktop capture of the real DipTrace project window through `PrintWindow`/bounded `WM_PRINT` BGRA frames piped to ffmpeg, with black/title-bar-only rejection;
- repository I²C level-shifter source plus MP4/GIF demonstration with one-at-a-time symbol and net reveal.
- PCB/Schematic design-boundary fitting, purple board-outline detection,
  control-free crop selection, output padding and one-point-at-a-time route
  timing;
- matching PCB source plus board-framed MP4/GIF demonstration.

Cinematic replay is deliberately a presentation path. The XML bridge and normal preview/SHA/transaction/review path remain authoritative for engineering edits and acceptance.

### Headless Windows GUI worker

- isolated Win32-desktop worker for bounded native DipTrace open/save/close work without switching the user's input desktop or synthesizing physical mouse/keyboard input;
- selectable launch mode: `hidden` (separate randomly named `WinSta0` desktop, invisible) is the default, and `native` explicitly targets the verified current `WinSta0` input desktop so the round trip stays visible; native mode rejects elevated callers and validates desktop/window-station/session identity before DipTrace work;
- Windows hidden/native smoke/readiness checks and a frozen packaged helper under `app/tools/diptrace_mcp_headless_gui/`;
- fail-closed automation with no coordinate-input fallback when a native control action cannot be completed safely;
- split Windows packaging boundary: the per-user MCP installer is permanently non-elevated, while a separate self-contained administrator plug-in installer owns only the bridge/settings payload and bounded DipTrace `Plugins\\<module>\\DipTraceMCP` writes.

The headless worker is a host-automation boundary, not a second semantic authoring authority or a process/filesystem/network/token/privilege sandbox. Real DipTrace actions remain claim-specific acceptance evidence.

### Product and engineering support

- raw-preserving internal Component/Pattern Library mutation core with controlled real-editor evidence;
- deterministic pattern recommendation and privacy-bounded feedback/evaluation baseline;
- deterministic synthetic acceptance fixture-pack generator;
- write-path trust invalidation regression coverage;
- deterministic DFM/DFA/DFT release-readiness supplement;
- manual-only acceptance evidence generator and validator;
- aggregate supported-environment coverage gate raised to 90% while preserving the 85% geometry-enabled Linux-only floor;
- public MCP tools `recommend_patterns` (deterministic pattern-library recommendation without model calls) and `analyze_release_readiness` (bounded DFM/DFA/DFT findings from exported XML).

## Changed

- The public MCP contract was intentionally expanded from the frozen 159 to 165 tools for bounded intelligence engines, then to 167 for the read-only built-in-library bridge; package-level native-library mutation remains intentionally unregistered.
- Existing-wired schematics no longer represent a fundamental placement dead-end: affected explicit wire geometry can now be selectively replanned as one atomic semantic transaction batch. The older conservative placement planners may still refuse existing wires when used directly.
- The initial real-DipTrace schematic quality campaign is complete: cases 01–18 closed with retained failed/invalid attempts, targeted fixes, operator visual review and native Save/Close/Reopen/re-export evidence. PR #90 merged the bounded fixes into `main`.
- PCB Generation D can now compare multiple internally generated bounded placement candidates rather than only caller-supplied synthetic examples.
- DSN/SES results can be structurally and semantically screened before import without mutating the PCB.
- Real-DipTrace capture candidates can be converted into reproducible machine-readable and Markdown evidence reports without rewriting historical evidence or manufacturing trust.
- The private/manual Q1 Component Angle campaign is PASS on its accepted production checkpoint; immutable historical release records keep the status that was true when each release was cut.
- The accepted manual matrix is complete at 12 of 12 blocking gates PASS across its recorded checkpoints. Claude Desktop restart and custom-state preservation are operator-confirmed PASS from a separate machine; their earlier WAIVED/pending states remain historical only.
- Documentation distinguishes current implementation state from immutable release/audit/acceptance snapshots.
- Installation/release documentation identifies the immutable `v0.3.0`
  GitHub/PyPI assets and split Windows packaging without rewriting older releases.
- Testing documentation reflects the combined 90% coverage gate and the separate 85% Linux-only floor.
- The operator accepted the current repository PCB/Schematic designs and both
  GIF/MP4 examples in the current DipTrace configuration on 2026-08-16.

## Fixed

- `add_testpoints` and `remove_testpoints` resolve the PCB footprint cache the way readers do. Native exports nest it inside the embedded component library; the tools looked only for a sibling library, created a second one that shadowed every existing pattern, and the per-write limit then refused a single testpoint on any native board (899 and 3018 counted objects on the two reference boards).
- `sync_schematic_to_pcb` skips native Net Port parts instead of demanding a pattern for them, refuses a mapping that names one, and no longer runs auto-placement for components that already exist on the PCB, which reported "PCB outline has no room" on a compact populated board.
- Wired-schematic repair scoring now models the same world the atomic reroute applies: the joint route scorer removes exactly the affected wire geometry the reroute would replace for a candidate's moved parts (through the same shared affected-group logic) and keeps unaffected nets as obstacles instead of re-scoring their preserved wires as phantom replacement candidates; a clean wired schematic no longer receives spurious repair motion, and unaffected nets' geometry is provably never deleted.
- `plan_schematic_placement_repair` builds its baseline from the document's current placement, so repair-plus-reroute works on already-wired schematics as documented (the previous optimizer candidate generation refused wired documents before the reroute stage ran).
- Operator `moves` are true immutable repair constraints: the engine carries `fixed_part_ids`, proposal generation never moves a fixed part or a group containing one, scoring happens on the constrained geometry, and the service verifies the final coordinates fail-closed instead of silently re-applying them; reported `improved`/score now refer to the actually applied geometry.
- RefDes resolution for `moves` is fail-closed: a RefDes shared by multiple schematic parts (multi-part components) is refused with the bounded list of matching stable IDs, duplicate moves for one part are refused (conflicting or identical), unique RefDes remain case-insensitive and stable object IDs remain the exact selector.
- No-op plan/apply contract is consistent across the stored-plan tools: empty placement/silkscreen/repair plans are stored with `status="noop"` plus `no_changes=true`, and applying one is an idempotent success (`ok=true`, `changed=false`, no transaction, SHA unchanged) instead of raising after looking applicable.
- Schematic placement-repair planning fails closed when the generated operation batch exceeds the 100-operation transaction limit, instead of storing a plan that the paired apply tool could never execute.
- Capability reporting matches runtime availability: `release_readiness` requires a board document, and `schematic_placement_candidate_ranking` is reported unavailable for wired schematics where the underlying scorer refuses to run.
- `recommend_patterns` exposes the typed `PatternRequirement` schema in `tools/list` (pad count, mounting, geometry bounds, pitch, holes, required pad numbers) instead of an opaque object.
- Headless Save targets the project window rather than IME/proxy windows, dispatches the native menu command without physical input, orders `WM_CLOSE` behind Save on the same queue, and fails when normal process exit cannot be observed.
- Hidden recording selects the real project `TForm1`, dismisses the XML-open information dialog through a button message, pads odd H.264 frames, bounds GIF post-processing, and removes stale MP4/GIF outputs before each validated run.

## Remaining boundaries

- atomic selective schematic reroute currently rebuilds affected sheet-local explicit nets from resolved pin endpoints; it does not preserve arbitrary pre-existing manual junction topology as a visual constraint;
- stronger sheet-level/global schematic congestion scheduling and external/reference motif ingestion remain future work;
- the completed 18-case schematic campaign supports its tested scope only; new schematic claims such as hierarchy, topology-preserving reroute or automatic rotation/pin-facing behavior still require claim-specific evidence;
- PCB candidate/whole-board quality remains subject to claim-specific real-DipTrace
  native refill/plane/via acceptance where stronger claims are desired;
- cinematic UI macros and calibration for additional DipTrace
  version/editor configurations require their own real-client verification;
- staged cinematic playback of vias/layer transitions remains unsupported;
- the 12-gate manual matrix is complete for its recorded checkpoints; future Windows/client reruns are impact- or release-claim-based rather than automatically replaying the full matrix;
- the library mutation request/preview contract remains package-level and unregistered in the public MCP tool snapshot;
- native manufacturing generation, field-solver/PI/EMC/thermal sign-off, universal compatibility, signed-binary trust, independent review and production readiness are not claimed.

The concise release summary is in `CHANGELOG.md`; do not rewrite this detailed
published-release record when later development begins.
