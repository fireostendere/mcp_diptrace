# Real Schematic Authoring / Readability Validation — 2026-08-10

## Why this validation exists

The formal manual acceptance campaign is intentionally paused after
`codex_real_client_restart = PASS` on production candidate
`0bb09b4b3af40a5a3d1a875fab885430a2d251ba`.

The project has explicitly waived `claude_desktop_real_client_restart` for the current campaign. That gate was not run and is not PASS; no direct Claude Desktop validation is claimed. The current priority is deeper product validation: can DipTrace MCP author a normal, electrically correct, human-readable schematic in real DipTrace without routine manual cleanup?

When formal lifecycle acceptance resumes, the next project-required gate is `windows_clean_install_repair_uninstall`.

The canonical repository manual-acceptance validator still treats Claude Desktop as required and does not encode this project-level waiver. Do not rewrite the waiver as PASS merely to satisfy the canonical matrix.

## Relevant implementation history

PR #66 added deterministic bounded readability routing for newly authored schematic wires. Its goals include:

- preserve already-clean orthogonal paths;
- avoid unrelated component regions;
- avoid schematic text/label collisions;
- avoid unnecessary wire crossings;
- strongly avoid collinear overlap;
- avoid self-intersections and diagonal segments;
- prefer deterministic Manhattan routing;
- minimize unnecessary bends and path length within bounded search limits;
- preserve intentional wire-to-wire endpoint connections.

The subsequent Ponytail pass was merged in PR #68. The historical accepted production candidate for the completed manual gates is therefore the post-Ponytail code at `0bb09b4...`.

For this new schematic-quality validation, do not assume that historical identity is still the current code candidate. Before the first experiment, record the actual local production checkout being tested and treat it as a new validation identity if relevant production code has changed since `0bb09b4...`.

The historical `diptrace_ratline_and_wire_roundtrip` gate remains PASS for its original scope. This validation is stronger and product-oriented: it evaluates complete authored schematic quality rather than only wire serialization/connectivity round-trip.

## Test philosophy

Start with small circuits whose correct topology is obvious. Ask MCP to author them from a clean/disposable schematic using normal public workflows. Open the result in real DipTrace Schematic Capture and judge both electrical correctness and presentation quality.

Do not optimize examples around the router. The point is to expose normal user-facing failures.

When a reproducible problem is found:

1. preserve the exact input/request and generated artifact;
2. separate operator/setup error from product behavior;
3. capture the real DipTrace visual result;
4. identify the smallest reproducible case;
5. add a focused regression test before or with the repair;
6. repair the focused behavior without silently changing the public MCP contract;
7. rerun the affected real example.

## Initial circuit set

### 1. Resistor divider

Expected structure:

- VCC -> R1 -> midpoint -> R2 -> GND;
- midpoint net label or output connection;
- clean vertical or horizontal visual flow;
- no wire through symbols or text.

### 2. LED + resistor

Expected structure:

- supply -> current-limiting resistor -> LED -> return/GND;
- obvious signal/power flow;
- readable polarity/orientation;
- no avoidable wire detour.

### 3. Simple RC / divider + capacitor

Expected structure:

- small branch topology;
- clear junction intent;
- capacitor branch should not force unrelated crossings or overlaps.

### 4. Collision-prone placement

Deliberately place components so the direct shortest wire would cross another symbol, label, or existing wire. Validate that the quality router chooses a reasonable alternative rather than producing an unreadable result.

### 5. RefDes / Value / net-label pressure

Use components and labels positioned near likely wire corridors. Validate that wires do not cover user-visible text and that detours remain reasonable.

### 6. Small multi-net schematic

Create a compact circuit with several components and at least three distinct nets. This is the first meaningful test of whether local routing decisions compose into a readable whole.

## Acceptance observations for every example

Record:

- exact production candidate identity;
- DipTrace version/build;
- exact MCP authoring request/operations;
- generated source hash;
- native saved/reopened artifact hash;
- final re-export hash;
- semantic comparison;
- screenshots or equivalent operator observations when permitted.

Check:

### Electrical correctness

- expected components exist;
- RefDes/value/pattern are correct for the test scope;
- pins connect to intended nets;
- no accidental shorts;
- no missing intended connection;
- intentional junctions are represented clearly.

### Placement/readability

- components are sensibly spaced and oriented;
- signal/power flow is understandable;
- no severe unnecessary whitespace or crowding;
- RefDes and Value remain readable.

### Wire quality

- orthogonal/Manhattan geometry where expected;
- no wire through an unrelated component body;
- no wire covering RefDes/Value/net-label text;
- no unnecessary wire-wire crossing;
- no unrelated collinear overlap;
- no self-intersection;
- no diagonal segment unless explicitly intended/supported;
- no absurd detour;
- no needless bend sequence;
- explicit wire-to-wire connection remains distinguishable from a mere crossing.

### Native round-trip

- DipTrace opens the generated file without repair/error;
- native save/reopen succeeds;
- final XML re-export succeeds;
- electrical meaning is preserved;
- DipTrace canonicalization is classified separately from MCP semantic defects.

## Outcome classes

- **PASS** — electrically correct, readable, and native round-trip safe for the tested case.
- **QUALITY FAIL** — electrically correct but clearly unreadable or requires routine manual cleanup because of reproducible MCP placement/routing behavior.
- **SEMANTIC FAIL** — wrong/missing connectivity, component/property corruption, or another functional defect.
- **INVALID ATTEMPT** — operator/setup/seed/path error; does not count as product evidence.

## Stop / resume point

This validation may generate focused repair work. Complete or pause it deliberately before returning to the formal lifecycle matrix.

Project-required formal acceptance resumes at:

`windows_clean_install_repair_uninstall`

`claude_desktop_real_client_restart` remains WAIVED for the current project campaign, not PASS. If direct Claude Desktop evidence becomes important later, run it as a fresh gate.

Do not repeat already accepted PCB, schematic round-trip, library writer, ratline/wire, mask/paste/courtyard/Common, Q1, or Codex restart gates unless a later production-code change plausibly affects their exact tested path.

## Live campaign checkpoint — 2026-08-11

- Candidate: `af00b2afa22fc1228ad953b533bc8bb62fc5be0f` (production tree clean at start).
- MCP server: `0.1.2`; source format and installed DipTrace Schematic: `5.3.0.3`.
- Historical manual gates above remain unchanged and were not repeated.
- `01 resistor divider`: **PASS** after focused repairs and native round-trip.
- One recursive whole-Documents scan was stopped after no bounded response: `INVALID ATTEMPT` (discovery only; no design write).
- Next case after divider completion: `02 LED + resistor`.

### 01 resistor divider

Artifact: `C:\Users\fireo\Documents\Codex\schematic-quality-af00b2a\divider-01\source\divider_source.dchxml`

- SHA-256: `f9a1ae3ddffd0532ca1aee54bd4938ee8ad93a6205222ee523e03346470c01b1` (13,464 bytes).
- Real DipTrace 5.3.0.3 seed SHA-256: `d4287ae42b4a888165bf417ffd05101958495de6409e355a50dbb74dc5919f91`; its embedded `CompType0` resistor style was retained.
- Setup only: copied the seed through `create_document_from_seed`, then guarded `apply_xml_edits` removed its two unwired placed parts while preserving the embedded library.
- Authoring transaction: `tx_3a08618f-6a36-431f-a67c-c296a16699dc`; source SHA `e4bdfcc34111fca55ee1ffc4a37c969a17676bb63cd9a63d42213ad85231afb0`; preview/commit SHA `f9a1ae3ddffd0532ca1aee54bd4938ee8ad93a6205222ee523e03346470c01b1`.
- Exact semantic operations: `place_part(R1, CompType0, 10k, 40,40)`, `place_part(R2, CompType0, 10k, 65,40)`, `connect_pins(VCC=[R1:1])`, `connect_pins(OUT=[R1:0,R2:1])`, `connect_pins(GND=[R2:0])`, three straight two-point `add_wire` calls (`VCC 28..36.19`, `OUT 43.81..61.19`, `GND 68.81..77`, all at y=40 mm), and `add_net_label` for VCC/OUT/GND at `(28,40)`, `(52.5,40)`, `(77,40)`.
- Automated result: R1/R2 and values present; reciprocal pin/net membership matches `VCC -> R1 -> OUT -> R2 -> GND`; 3 nets and 3 wires; no missing intended pin connection or accidental shared net; all wire segments horizontal, non-overlapping, non-crossing, non-self-intersecting, and zero-bend; embedded style resolves; MCP ERC/connectivity findings `0` (electrical pin-type check skipped because the normalized placed pins do not expose types).
- Schematic review has two out-of-scope BOM warnings (manufacturer/MPN absent). Native process opened the artifact as `Schematics - divider_source.dchxml`; visual verdict, save/reopen/re-export, and semantic comparison are pending.

#### Visual defect and focused retest

- Operator verdict on the original real-host view: electrically recognizable, but not a meaningful quality result. Values were absent and VCC/OUT/GND labels were disproportionately large. Classification: `QUALITY FAIL`.
- Screenshot: `.local/validation/schematic-quality-af00b2a/divider-01/operator/visual-before-fix.png`, SHA-256 `f2c2333da7d3ceffc40c1db9eeb5a34c63ae0901c158b11b79edaf7d1c2be666`.
- Root cause: shared `place_part` compilation omitted native `ValueMarking`/marking-size metadata; the public `add_net_label` default was 10 while real DipTrace examples use 4 for comparable labels.
- Focused fix on `af00b2a` working tree (production diff SHA-256 `a95cc27962643f0172d2c0adf9d0026a4533cc575435ed066ae157068d4db96b`): emit common RefDes/Value markings at size 6 and change the existing net-label default to 4. Public tool count remains 159; no tool or parameter was added.
- Regression evidence: 39 affected authoring/schema/wire-quality tests pass; snapshot self-check passes with 159 tools. The broader 40-tool chain is not affected by these fields and timed out at its first `diptrace_status` call on this host; it is not treated as product evidence for this fix.
- Fixed source: `.local/validation/schematic-quality-af00b2a/divider-01/divider_retest_source_02.dchxml`, SHA-256 `fd8e3c8a17c3b47aa7dd8f4751ca242cb8ba4fa60b92989cf5169128e57fafff` (13,969 bytes). Exact public stdio MCP evidence: adjacent `retest_mcp_evidence.json`, SHA-256 `7ce1eb3111a925b81d38d83dcf2cfc8f733bdd306dc1c6bb5db62a915a11ca99`.
- Fixed precheck: 2 parts, 4 pins, 3 nets, 3 straight wires; native value markings exist; all three labels use size 4; ERC/connectivity findings 0. DipTrace opened it as `Schematics - divider_retest_source_02.dchxml` (PID 19060).
- Exact manual retest: inspect only the fixed divider's value visibility and text proportion/readability. No historical manual gate is affected. Native save/reopen/re-export remains pending until this focused visual retest passes.
- Operator focused-retest verdict: "немного лучше", but still `QUALITY FAIL`: VCC/GND are text instead of upward/downward power symbols and OUT is text over the resistor-to-resistor wire instead of a native output port.
- Format diagnosis: DipTrace represents these as library-backed placed parts whose embedded library part has `PartType="Net Port"`; a free text `Shape` cannot substitute for their native semantics. No public tool or parameter was added.
- Operator native reference before save: `.local/validation/schematic-quality-af00b2a/divider-01/divider_retest_source.dchxml`, SHA-256 `fd8e3c8a17c3b47aa7dd8f4751ca242cb8ba4fa60b92989cf5169128e57fafff`. Native-saved reference: `divider_retest_source_02.dchxml`, SHA-256 `3327a7af4c228cffefdc05da64f74ac57262313aea2d7fb59373e96d9094ae77`, DipTrace `5.3.0.3`.
- Reference semantics: five parts/seven pins; native downward GND, upward VCC, right-facing output port, vertical R1/R2, and nets `GND=2`, `OUT=3`, `VCC=2` endpoints. DipTrace encodes the OUT T-junction as a `Wire` endpoint on the interior of the main wire segment (`Connected2="Wire"`, `SubObject2="1"`).
- Focused production repairs: `place_part` now applies native name/refdes/value marking visibility based on the embedded `PartType`; wire cleanup preserves a requested interior segment anchor despite sub-micrometre unit round-off; normalized parts expose `part_type`, and ERC no longer reports intentionally empty values on native net ports. Production diff SHA-256: `550db8bb4bf61ed2c3f91d835715f2ddf01cb974e0eb4dec76da2fff37087f5d`.
- Regression evidence: 42 affected authoring/wire-quality/review tests pass; Ruff and `git diff --check` pass. Exact added checks cover native net-port markings, a midpoint Wire T-junction with XML unit drift, and the net-port missing-value exemption.
- `create_document_from_seed` on the 605-object native reference exceeded its documented 500-object safety cap before writing: `INVALID ATTEMPT`. Setup therefore used an exact byte-for-byte disposable copy; all design edits then used guarded public MCP operations.
- Final public-MCP rebuild: `.local/validation/schematic-quality-af00b2a/divider-01/divider_native_rebuild_04.dchxml`, SHA-256 `185000f9079001cc2b1ec8ccb6d2943dbe8b6786379329e343c50e46e1dd4634`. Exact 16-call evidence: adjacent `native_rebuild_04_mcp_evidence.json`, SHA-256 `5cb04c8c070c43d0fd8119eb0297787c2d6aea8946d1bcf637576b56edd56dbf`.
- Final automated precheck: five correctly typed/marked parts, seven pins, `GND=2`, `OUT=3`, `VCC=2` endpoints; four orthogonal zero-bend wires; OUT is a native horizontal port joined at the midpoint of the vertical OUT segment; no missing/extra net membership, diagonal, detour, crossing, overlap, or stale fragment. MCP ERC and connectivity findings are both zero; electrical-type conflict analysis remains explicitly skipped because placed pin electrical types are unavailable.
- Operator verdict on rebuild 04: `QUALITY FAIL`; the VCC port/label crossed into the sheet border area. The request placed VCC at `y=95 mm`, while this 8.5-inch sheet's upper usable edge is about `92 mm` after its top margin. This is an invalid placement choice in the exact client request, not DipTrace canonicalization or a production routing/port defect; no production change or regression test was warranted.
- Focused rebuild 05 shifts the complete drawing down 25 mm without changing topology or relative geometry: `.local/validation/schematic-quality-af00b2a/divider-01/divider_native_rebuild_05.dchxml`, SHA-256 `55e0a372fd2f52f2a15b928877f87f4622d6a81ec89eb176440160e7712f30b5`; exact 16-call public-MCP evidence `native_rebuild_05_mcp_evidence.json`, SHA-256 `49a535dd9eec83ec8f43f6fdae6a386a5cd33d1468cd3794ba6ea89633011146`. ERC/connectivity findings remain zero.
- Operator verdict on rebuild 05: "прилично"; visual gate accepted.
- Native Save and Close/Reopen succeeded. The saved `_05` bytes retained SHA-256 `55e0a372fd2f52f2a15b928877f87f4622d6a81ec89eb176440160e7712f30b5`. Operator Save As re-export: `divider_native_rebuild_06.dchxml`, SHA-256 `2dcc724d043bd97a95a7ee5f678314e3c3fd17df68b0386952ca46c85199dcd6`, DipTrace `5.3.0.3`.
- The first evidence comparison correctly remained fail-closed but exposed comparator false positives: native DipTrace rounded inch coordinates by tens of nanometres, omitted default `NotConnected="N"`, and replaced duplicate OUT style `CompType6` with geometry/electrically identical `CompType0`. Actual component identities, positions, pin/net membership, 2/3/2 net endpoints, wire topology, and visible symbol geometry survived.
- Evidence comparator repair now normalizes sub-micrometre coordinate serialization, default no-connect omission, and only style aliases whose embedded part structures match after excluding identity-only IDs/refdes/lib paths. Its regression also mutates symbol geometry and requires that real change to remain a failure. No public MCP tool or parameter changed.
- Final production diff SHA-256: `b64bef12a4047788901f2967ad4e6b8abd2bad5b3e8088f6005244811d4e62bb`. Automated evidence: 108 affected source-tree tests pass; Ruff and `git diff --check` pass. Five in-memory MCP transport tests hit their existing 10-second startup timeout on this host; the same public stdio evidence calls completed successfully and are recorded separately.
- Final semantic comparison: PASS and complete across 12 schematic categories, with no differences, parse warnings, unsupported categories, or missing required categories. Disclosed normalizations: `coordinate_precision`, `default_attribute_omission`, `equivalent_component_style_alias`. Re-export ERC/connectivity findings: zero.
- Exact public-MCP evidence: `native_roundtrip_06_mcp_evidence.json`, SHA-256 `cb536b72a6e0162d962d8f9174d51bf2f6454fa5bd2b656252c297c167b7e2ea`; manifest SHA-256 `8fb04a1cca18c5e201af4b1db8107533c10ae03365d75bf658bc7394b3fce836`. Evidence authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** — electrically correct, visually accepted, and native Save/Close/Reopen/re-export preserved semantics. Historical gates are unaffected. Next meaningful case: `02 LED + resistor`.
