# Engineering Skills Review — 2026-11-10

## Conclusion

The fifteen `skills/*/SKILL.md` files, the shared runtime and RAG guidance,
`catalog.json`, `capability-map.json`, the generator, the skill tests and the four
legacy `.agents/skills/diptrace-*` recipes were reviewed against `main` at `d27f33e`
(PR #135). Tool names, numeric bounds, CLI options and the native-helper behaviour
described since the [2026-10-09 review](SKILL_REVIEW_2026-10-09.md) still match the
code. The defects were drift against three later changes: the server/service split,
the stop rules of PR #132 and the readability profile of PR #135. All findings in the
table were fixed in this change; the recommendations at the end were not applied.

## Findings and fixes

| Priority | Problem | Fix |
|---|---|---|
| High | The sixteen source links were pinned at `20e4bc1` (2026-07-29). At that commit `server.py` and `service.py` held the cited bounds; on `main` `server.py` is a 22-line shim and the bounds live in `server_runtime.py`, `services/routing.py` and `services/semantic_operations.py`. The pinned `REVIEW_ENGINE.md` and `review.py` also predate the `schematic_readability` profile that schematic-erc-review tells the agent to run while forbidding checks "outside that matrix". | All links re-pinned to `d27f33e`; file names follow the split; `schematic_readability.py` is linked. |
| High | Evidence capture told the agent not to adopt a schematic candidate "until the differences are resolved" for every native re-export delta, renumbered ports included, and never named `no_errors_found` or how to dispose `review_required`. That contradicts the stop rules in `AGENTS.md` and restores the re-verification loop they ended. | The paragraph states the three `erc_status` values, the "No errors found" image rule, comparison on physical pin/pad/net/NC records, the non-defect re-serialization list, and sends real geometry changes to the page-fit inspection. |
| Medium | Schematic ERC review and the capability map said native schematic ERC is not implemented and must be reported missing, without naming the schematic helper's `--erc`; schematic-engineer required native ERC evidence but did not link the evidence skill. This is the "no base helper, so no capability" class of the two earlier reviews. | Review step 4, the `generic_native_schematic_erc` contract and the schematic-engineer authoring note route to the bounded helper. |
| Medium | Batch fixes, one review per milestone, ask-once hardware decisions, no re-verification of unchanged inputs and short handoffs existed only in the checkout's `AGENTS.md`; a wheel-installed catalog carried only the schematic subset. | A compact "Definition of done and stop rules" section in pcb-design-workflow; `AGENTS.md` stays authoritative. |
| Medium | BOM sourcing listed `get_bom` in the catalog but its body named none of the registered BOM checks. Signal-integrity review asked for length and skew measurements without naming the length and pair tools. 72 of the 152 registered tools were absent from the capability map's tool groups. | BOM sourcing names `get_bom`, `group_bom`, `review_bom`, `find_missing_component_fields` and `compare_bom_to_design`; signal-integrity review and critical-net-router name the length and pair analysis; release gate names `get_findings`. Capability map 2.4.0 groups all 152 tools in 16 groups. |
| Medium | Legacy `diptrace-board-build` still instructed practices the house rules forbid: merging a thermal pad array, splitting a merged pad, shrinking EasyEDA copper with `sanitize_pads()`, labels-only wiring, routing USB D+/D- as two nets and accepting native DRC errors as "fab-tolerance"; its description claimed "any new board". `diptrace-pcb-grounding` recommended a via cluster under the exposed pad, and `diptrace-schematic-style` limited RAG to "a material unknown fact". | Fixed in place. The board-build recipe opens with a precedence note and its description no longer competes with pcb-design-workflow. |
| Low | [NATIVE_XML_EXPORT.md](NATIVE_XML_EXPORT.md) said native checks cover 5.3.0.3 only (noted on 2026-10-09). | It states both verified builds. |

## Second pass: executed workflows

The first pass compared text with code. The second ran each written workflow through the MCP
server on scratch copies of the three projects in this repository (`attiny85-arduino-clone`,
`i2c-level-shifter`, `dut-controller-reva`). Read and review steps worked as written, and
every parameter named in the skills exists in the tool schemas. Two write paths and one
acceptance bar did not.

| Priority | Problem | Fix |
|---|---|---|
| Blocker | `add_testpoints` refused one testpoint on both reference boards: 899 and 3018 counted objects against the limit of 500. The tool looked for the footprint cache as a sibling library; native exports nest it, so a second library shadowed every pattern. | Code, PR #137: writers resolve the cache as readers do. testpoint-planner states the required fields. |
| Blocker | `sync_schematic_to_pcb` demanded a pattern for native Net Port parts, which the house rules require on every schematic, and reported "no room" for components already on a compact board. | Code, PR #137. The board recipe states what sync skips and when a `pin_map` is needed. |
| High | "Zero errors, no skipped checks" was unreachable: every schematic in the repository, and anything placed with `place_part`, has markings on automatic alignment, which the readability review reported as missing geometry. | Code, PR #138: automatic markings are counted per sheet for the page-fit inspection. Untyped pins and unsupported symbol primitives still block; schematic-erc-review lists them with their resolution. |
| High | Release gate could only answer BLOCKED: `pcb.silk_to_pad` is never implemented, thermal review needs a power field, and offline errors from estimated geometry had no stated disposition. | Release gate lists the three structural skips and requires an explicit operator waiver backed by native DRC. |
| Medium | Three Russian trigger phrases were identical to the user's EasyEDA skills, and the `AGENTS.md` table routed eight of fifteen skills. | Triggers name DipTrace; the table lists all fifteen. |
| Medium | schematic-engineer told the agent to "take a supported snapshot" (no such tool), repeated the PCB recipe, and kept an import-provenance note. | Rollback wording, a pointer to the board recipe, note removed. |
| Low | Skills use BLOCKED and NOT_RUN, the handoff checker accepts neither. | The handoff template says how to record them. |

Open after the second pass:

- Symbol arcs make readability geometry incomplete (`unsupported_symbol_shape:Arc`), so a
  schematic with such a native symbol stays BLOCKED until arcs are measured. Their native
  semantics need evidence before they are approximated.
- The connectivity review does not flag net pin items that reference a missing part; the
  attiny85 schematic has six.
- Every description still starts with the `RAG-backed.` marker and ends with a fixed English
  sentence. Both are enforced by the generator and spend the most valuable description words.
- No skill has been run by an agent end to end, and the native Windows helpers were not
  launched in either pass.

## Verified without change

- All 152 registered MCP tools resolve. Every backticked tool-like name is a
  registered tool or an explicit CLI word, and every `capabilities` list in
  `catalog.json` is a subset of the registry.
- `run_review` has fourteen profiles. The twelve named in the skills exist;
  `component_clearance` and `manufacturing_geometry` run inside `board_review`.
- Routing bounds (20 connections per local plan, `max_vias` 0, detour 3.0,
  100 000 nodes, four rip-up attempts), write limits (100 operations, 500
  conservatively counted objects), paging (1 through 500, default 100) and testpoint
  defaults (1.0 mm, 0.5 mm, 2.54 mm, 1 through 100 candidates, 5 000 grid points)
  match `src/diptrace_mcp` on `main`.
- The schematic helper matches its description: executable-hash-pinned 5.3.0.3 and
  5.3.5.1 profiles, a repeatable `--startup-dialog-sha256`, the `TFMyMessage` and
  `DipTrace News` handling, and `erc_status` of `not_run`, `no_errors_found` or
  `review_required`.
- `scripts/pcb_quality_gate.py` matches the handoff template: `--stage`, the
  `Gate stage`/`Input schematic`/`Current board` lines, the status vocabulary and
  the CP2102 thermal-via exception.
- The frozen helper still dispatches only `pcb-acceptance` and `cinematic`;
  `SUPPORTED_BUILDS`, `native-fabrication.zip` and `native-placement.csv` in
  `diptrace_mcp.native_cad` are as described.
- Legacy `diptrace-pcb-testpoints` agrees with testpoint-planner and was not changed.

## Recommendations not applied

- Tool-group coverage is not enforced. If the map should stay exhaustive, compare the
  grouped names with `registered_tools()` in `scripts/generate_pcb_skills.py`; every
  new tool would then need a map entry.
- A copy of this catalog under a host configuration directory (for example an
  OpenCode global skills directory) is outside `SOURCES.sha256` and goes stale. Point
  the host at the checkout or at the installed `diptrace_mcp/skills` directory.
- Claude Code registration is still a product decision (see the 2026-10-09 review).
- The source links are pinned again and will drift again; re-pin them when a cited
  bound or file moves.

## Verification

- `python scripts/generate_pcb_skills.py --check`: OK, 15 skills, shared schema,
  links, capabilities, mirrors and hashes.
- `claude plugin validate skills --strict`: validation passed.
- `python -m pytest -q tests/test_skills_integrity.py tests/test_skill_packages.py tests/test_release_artifacts.py tests/test_documentation_links.py`:
  **47 passed** (RAG markers, catalog/tool contracts, real CLI parsers, handoff
  template, readability-rule phrases, wheel build with exact skill bytes, the
  allowlist-versus-tracked-files check and documentation link targets).
- `python scripts/sync_skill_scripts.py --check`,
  `python scripts/audit_release_artifacts.py --check-allowlist` and
  `python scripts/generate_mcp_tools_snapshot.py --check` (152 public tools): OK.
- A one-off comparison of the capability map's tool groups with
  `registered_tools()`: 152 names, no duplicates, none missing.
- `git diff --check`: no whitespace errors.

No DipTrace editor was launched. These results confirm the instructions, CLI
contracts and packaging, not a new native round-trip on an installed GUI.
