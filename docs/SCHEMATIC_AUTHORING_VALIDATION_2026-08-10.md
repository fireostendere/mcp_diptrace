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

### 02 LED + resistor

- Candidate: `daf34fccbd501c979605189e324160076072ec21`, pushed as `origin/codex/schematic-quality-divider`. No new production change for this case yet.
- No native two-pin LED style existed in the local XML corpus; only a four-pin RGB LED was available. Substituting it or synthesizing a symbol was rejected. A clean disposable seed retaining the accepted divider's native power/ground/resistor styles was prepared through public guarded MCP edits: `led_resistor_native_seed_01.dchxml`, initial SHA-256 `b3d1785b4366c9ae0d4c84a4319d9fc202d806b750b116b3f54e14b6c6e60713`.
- Operator setup only: placed one standard DipTrace two-pin `LED` and saved the same seed. Native seed SHA-256: `213ccb7336c936be81a879f4ba4851b80108645bdfb69c185eb5c1ebfc505521`; DipTrace `5.3.0.3`; embedded LED style `CompType0`, pins `0=K`, `1=A`. Exact public-MCP inspection: `operator_led_seed_mcp_evidence.json`, SHA-256 `82a567218285907c35910c3d1247d0a0b233556bc95c9aa38419ee0057d5b23d`.
- Public-MCP authoring removes only the setup LED placement, then creates a vertical functional flow: upward VCC port, R1 `1k`, D1 `RED` with anode toward R1 and cathode toward GND, and downward GND port. Exact topology: `VCC=[VCC port,R1:1]`, `LED_A=[R1:0,D1:A]`, `GND=[D1:K,GND port]`.
- Generated artifact: `.local/validation/schematic-quality-daf34fc/led-resistor-02/led_resistor_mcp_01.dchxml`, SHA-256 `295129386901a01e19aba402b1117d1025578684cc897f99cb2c35fbcc3c04d1`. Exact ten-call evidence: adjacent `led_resistor_mcp_01_evidence.json`, SHA-256 `8988fa6103beedc48a33023b0aef24ed3040cf5c4c2a0e770608799eee2d18d0`.
- Automated precheck: four parts/six pins; three nets with two endpoints each; three orthogonal zero-bend wires; no missing/extra pin membership, accidental shared net, crossing, overlap, diagonal, detour, or stale fragment. VCC remains inside the previously established usable sheet area. MCP ERC/connectivity findings are zero; electrical-type conflict analysis is explicitly skipped because placed pin electrical types are not normalized.
- Operator visual verdict: "Отлично!"; visual gate accepted with no reported cleanup need.
- Native Save/Close/Reopen/Save As was completed for candidate `01`. Saved source stayed byte-identical; native re-export `led_resistor_native_reexport_01.dchxml` SHA-256 `35b488d7c970fa816389e682b80bef30fd0b68cc3fc12f5c77fc638aa5c16b4d`. Re-export ERC/connectivity findings remained zero, but fail-closed semantic comparison correctly rejected changed wire geometry.
- Defect: MCP authored both LED wires at the library pin base and omitted native `Pin Length=0.15 in`; DipTrace moved each endpoint by `3.81 mm` to the actual pin tip on save. Candidate `01` is **SEMANTIC FAIL**: topology and visual appearance were accepted, but serialized pin/wire geometry did not survive the required native round-trip.
- Root fix under test: library pin length/orientation now feeds the internal routed endpoint without changing the public MCP model; verified DipTrace rotation is enabled by default; public `add_wire` snaps declared Pin endpoints to the resolved tip. The wire cleaner also deduplicates sub-micrometre coordinate drift. Regression coverage confirms pin-length/rotation anchoring and public-operation snapping.
- Independent evidence-tool defect fixed: native Part/Net ID reindexing is now compared through canonical part/pin/net identities, while real pin-net changes and symbol geometry changes remain fail-closed. Numeric native symbol precision is normalized under the existing `coordinate_precision` policy; no public contract was expanded.
- Repaired public-MCP artifact: `led_resistor_mcp_02.dchxml`, SHA-256 `95fe11d0622f15427d6c87a710806254fdcc84942e6b5226426338160d7e5bc2`; exact ten-call evidence SHA-256 `fa9f4760d851f4d2c80d1347230f6fb181de34f71a624c2a775484beda5f3757`. The same deliberately stale client coordinates now produce three two-point wires whose LED endpoints match native candidate `01` to coordinate precision. ERC/connectivity remain zero.
- Automated evidence: 158 affected schematic/evidence tests PASS; Ruff and `git diff --check` PASS. In-memory MCP evidence transport remains an `INVALID ATTEMPT` due its pre-existing 10-second startup timeout; real stdio MCP authoring and validation calls pass. Diagnostic comparison of repaired `02` against the already saved native `01` passes all 12 semantic categories, but is not recorded as round-trip evidence because those files were not the same physical save lineage.
- Tested identity: base `daf34fccbd501c979605189e324160076072ec21` plus source/test diff SHA-256 `af2d13bfae488221e9f91f534dce27d08844c644f5009be31d44e65ddb910572`.
- Impact-based retest: only repaired LED candidate `02` requires real-host Open/visual check/Save/Close/Reopen/Save As. Divider and unrelated historical gates are not affected; the resistor endpoint case is covered by automated neighboring smoke and its previous native PASS remains valid.
- Targeted visual retest of repaired candidate `02`: operator verdict "выглядит отлично"; placement/routing/readability PASS with no reported cleanup need.
- Targeted native retest of candidate `02`: Save left the authored source byte-identical, SHA-256 `95fe11d0622f15427d6c87a710806254fdcc84942e6b5226426338160d7e5bc2`; Close/Reopen and Save As succeeded. Native re-export `led_resistor_native_reexport_02.dchxml` SHA-256 `28fa054e89b73020cce4a020a08a011f214b868a7ea2a382742def8a82be7997`.
- Final semantic comparison: PASS and complete across all 12 required schematic categories, with no differences, missing categories, parse warnings, or unsupported categories. Disclosed native normalizations: `coordinate_precision`, `default_attribute_omission`. Re-export ERC/connectivity findings: zero; electrical-type check remains explicitly skipped because placed pin types are unavailable.
- Exact public-MCP round-trip evidence: `led_resistor_native_roundtrip_02_evidence.json`, SHA-256 `81bd007d775f2300b6ac507c105329f7638fc55d14f57a6268fde18e6c62ddaf`; manifest SHA-256 `d3ae5e1bfb1a5e2b732d7f10941249bf536db66dc5e8637a082f0132cb5ca025`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for repaired candidate `02` — electrically correct, visually accepted, and native Save/Close/Reopen/re-export preserved placement, routing geometry, and semantics. Candidate `01` remains the retained regression reproduction and **SEMANTIC FAIL**.
- Campaign impact: divider PASS and unrelated historical gates remain valid. Next meaningful case: `03 RC / divider + capacitor branch`.

### 03 RC / divider + capacitor branch

- Candidate: `24d8a9fe27c1c1d3e5f1d58efbbd24b27c340fe2`.
- Intended topology, clarified by the operator: RC filter `VCC -> R1 -> OUT -> C1 -> GND`. Existing native VCC/GND/OUT/resistor styles and proven public authoring workflow are reused; no prior manual gate is repeated.
- No real two-pin capacitor schematic style exists in the repository/local validation XML corpus. A disposable blank native seed was prepared from divider native rebuild `06` through guarded public MCP edits: `rc_native_seed_01.dchxml`, SHA-256 `b3d1785b4366c9ae0d4c84a4319d9fc202d806b750b116b3f54e14b6c6e60713`; preparation evidence SHA-256 `8540bb26f2d3a4b0a6bb0ed1b720248be32176ed8a4b5ea8242768e1a21319c0`.
- One preparation client timed out after applying its guarded edits but before writing evidence; a repeat against the already-empty file failed the exact-match guard. Classified `INVALID ATTEMPT`. The disposable source was restored byte-for-byte and the successful public sequence was rerun once with complete evidence.
- Operator placed one ordinary non-polarized two-pin capacitor and saved the seed in DipTrace 5.3.0.3. Native seed SHA-256: `7064ff79e692fcd5dfac95eb2ff60c79c94edbe20b6ac7ffbffd38050d9bceb2`; exact public-MCP inspection evidence SHA-256: `97aeb14016c5f11c086d62ba0b65ad15072043c025b31a619a04f2ebd0ca5d54`. The retained native style is `CompType0`, part `C1` / `0402B104K160NT`, with two opposite 0.15-inch pins.
- First public-MCP build `rc_divider_mcp_01.dchxml` incorrectly retained R2 and placed C1 as a parallel OUT-to-GND branch. The operator caught the mismatch at the visual gate. Classification: `INVALID ATTEMPT` caused by client-side test interpretation, not a placement/routing product defect; its artifact/evidence is retained but is not campaign quality evidence.
- Corrected public-MCP build: `.local/validation/schematic-quality-24d8a9f/rc-divider-capacitor-03/rc_filter_mcp_02.dchxml`, SHA-256 `7bec737db9d05cfbe390b35eda59ba0c5c3b7c681de7d3ec53ba959f8162b37a`; exact 16-call evidence `rc_filter_mcp_02_evidence.json`, SHA-256 `d92cb3663e4a1f5a7034107b115e691a17ee6b96c3d5c13176a54849cf8b278d`.
- Corrected automated precheck: five parts/seven pins; exact nets `VCC=[VCC,R1:1]`, `OUT=[R1:0,C1:0,OUT]`, `GND=[C1:1,GND]`; four straight orthogonal wires and one intentional OUT mid-segment Wire junction; no diagonal, bend, detour, unrelated crossing/overlap, or stale R2/branch. MCP ERC/connectivity findings are zero; electrical-type conflict analysis remains explicitly skipped because placed pin types are unavailable.
- Operator visual verdict on corrected candidate `02`: "Все ок"; placement/routing/readability gate accepted. The circuit is the intended passive RC low-pass filter.
- Candidate `02` Save/Close/Reopen/Save As succeeded, but fail-closed comparison reported `parts`/`patterns`: source SHA-256 `7bec737db9d05cfbe390b35eda59ba0c5c3b7c681de7d3ec53ba959f8162b37a`; re-export `02` SHA-256 `0e378666dc85c06bf172b227d608a3162b6c7fde144e0d36ca593d794cb2b6f2`. DipTrace restored stale net-port pattern associations from the native seed and cloned VCC with a different pin-to-pad mapping. Topology/wires/visible geometry survived, but evidence correctly remained fail-closed.
- A proposed `place_part` cleanup was tested as candidate `03`, with identical visible/electrical geometry and source SHA-256 `645a5723f96f493358fdbc3180ccb92a1508593fa03ba7af6b14be2aaafab30b`. Native re-export `03` SHA-256 `ded2f325fc89c9d0c76a0bdd25157d7697eadb395f4eaa817d8a13bb7c422e86` restored the exact same library state; comparison again failed only `parts`/`patterns`. The production/test change was therefore disproven and fully reverted before commit.
- Investigation conclusion: deleting every placed part from divider `06` left orphaned embedded styles; adding C1 to that blank file caused DipTrace to reindex patterns inconsistently. Candidates `02` and `03` share this pathological seed and are `INVALID ATTEMPT`, not product FAIL. The comparator correctly exposed the setup problem; no production code change remains.
- A stable seed was derived instead from native-canonical re-export `03`, then its five placements and three nets were removed through guarded public MCP edits. Blank seed `rc_native_canonical_seed_04.dchxml` SHA-256 `7c33783ce9ce361f5586630f009388cce2fe9ea1ebad3b58503e0adf78ffc0e6`; preparation evidence SHA-256 `5dcd1f4e8e969aa8d9e50125bf06db3f4ccfd7a5b5848168f5e21ede31479331`.
- Candidate `04` was rebuilt through 14 public MCP calls with the same accepted topology, placement, and wire geometry: `rc_filter_mcp_04.dchxml`, SHA-256 `ffb34370e5c883da5ca97b661ffe70d385092c76d3b71e9b2e801d40b9bd90b9`; exact evidence SHA-256 `2dc249b0303b9c713b667869fbb6d464f729335ed660d665cff09f90a010482f`. ERC/connectivity remain zero.
- Targeted native retest of candidate `04`: Save left the authored source byte-identical, SHA-256 `ffb34370e5c883da5ca97b661ffe70d385092c76d3b71e9b2e801d40b9bd90b9`; Close/Reopen and Save As succeeded. Native re-export `rc_filter_native_reexport_04.dchxml` SHA-256 `ded2f325fc89c9d0c76a0bdd25157d7697eadb395f4eaa817d8a13bb7c422e86`.
- Final semantic comparison: PASS and complete across all 12 required schematic categories, with no differences, missing categories, parse warnings, or unsupported categories. Disclosed native normalizations: `coordinate_precision`, `default_attribute_omission`. Re-export ERC/connectivity findings: zero; electrical-type check remains explicitly skipped because placed pin types are unavailable.
- Exact public-MCP round-trip evidence: `rc_filter_native_roundtrip_04_evidence.json`, SHA-256 `c0d88821f3329616e5f0d8422c6ad0f67352cc5c16d6dbc9813fe515ec75bca7`; manifest SHA-256 `c6d9669491655d1b2c99beec029c949e41ada23997403649b7730748cb9c5d5f`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for candidate `04` — correct RC low-pass connectivity, operator-accepted placement/routing/readability, and native Save/Close/Reopen/re-export preserved all compared semantics. Candidates `01`–`03` remain retained `INVALID ATTEMPT` evidence. No production code change was needed; divider, LED, and historical gates remain valid. Next meaningful case: `04 collision-prone placement`.

### 04 collision-prone placement

- Candidate identity: `9ee4e00`; DipTrace format/host remains `5.3.0.3`. Existing canonical resistor/capacitor/net-port seed is reused; no operator setup or prior manual gate is repeated.
- Public capability inspection confirmed that the 159-tool contract exposes schematic `place_part`, `move_components`, connectivity and wire authoring, while the named placement planners are PCB-only and fail closed on schematics. The case therefore uses only the intended public client path: crowded `place_part` -> exact `move_components` transaction -> `add_wire`; no internal schematic Python planner is used.
- Circuit: two-stage RC low-pass `IN -> R1 -> N1 -> R2 -> OUT`, with `C1` from N1 and `C2` from OUT to a shared GND. Seven parts/eleven pins/four nets create body, marking, branch and junction pressure while remaining visually understandable.
- The deliberately crowded authoring state had 21 centre pairs below 2 mm. Seven public `move_components` operations then separated the functional flow before routing; topology was established independently and remained unchanged.
- Candidate `01` automated precheck found a genuine placement-quality defect before native open: pin-tip snapping left only `0.24 mm` between each outer port/resistor pair, and the C2 branch partially followed the R2 lead. Connectivity was correct, but normal cleanup would be expected. Classification: **QUALITY FAIL**; native round-trip was intentionally skipped. Root was client placement based on symbol centres without actual pin-tip clearance, not XML serialization.
- Candidate `02` adjusts only IN/OUT/C2/GND spacing using the observed public-model endpoints, then repeats the same crowded-state repair and routing workflow. Artifact: `.local/validation/schematic-quality-9ee4e00/collision-placement-04/collision_placement_mcp_02.dchxml`, SHA-256 `d7741c008fcac11fde042824887a23386270e27851cdda9598b010a4ffbdfffc`; exact 29-call evidence `collision_placement_mcp_02_evidence.json`, SHA-256 `b2936ba73834fd12de976952aa23b163cc5fdaef1f430c73314f4bc5304c1a13`.
- Candidate `02` automated precheck: exact endpoint counts `IN=2`, `N1=3`, `OUT=3`, `GND=3`; seven orthogonal wires; two total bends; intentional mid-segment junctions only; no diagonal, unrelated crossing/overlap, self-intersection, stale fragment, or wire through an unrelated body. ERC/connectivity findings are zero. Seven schematic-review warnings are expected missing manufacturer/MPN metadata, outside this placement case; electrical-type checking remains skipped because placed pin types are unavailable.
- Operator verdict on candidate `02`: "УЖАСНО, я вообще не понимаю что на схеме". Screenshot `operator_visual_candidate_02.png`, SHA-256 `21a50caf706bf72149784a2435dbabafd564800eefa2c51ddc8fbd43efe4052f`. Classification: **QUALITY FAIL**; native round-trip intentionally skipped.
- Visual diagnosis: although the upper IN-R1-R2-OUT ladder is electrically correct, the shared GND route forms a large asymmetric bracket, the single GND symbol is remote from both capacitors, and inherited `ValueGlobal=Hide` suppresses all `1k`/`100n` markings. This requires ordinary manual interpretation/cleanup and cannot be accepted.
- Candidate `03` keeps the same two-stage RC topology and crowded-placement repair, but uses one short downward native GND port directly below each capacitor and enables the existing global value display through guarded public `apply_xml_edits`. No production code or public contract changed.
- Candidate `03`: `.local/validation/schematic-quality-9ee4e00/collision-placement-04/collision_placement_mcp_03.dchxml`, SHA-256 `7a8372c9408a94eb1190ffecbb12148bde14e99fdae53be6cd9ef34f2d43460d`; exact 31-call public-MCP evidence `collision_placement_mcp_03_evidence.json`, SHA-256 `1cf18196a498d3bb88fc809b7fe57c0f48af2ca33e67fcd5e882eaab6b9697e7`.
- Candidate `03` automated precheck: eight parts/twelve pins; endpoint counts `IN=2`, `N1=3`, `OUT=3`, `GND=4`; seven straight orthogonal wires with zero bends; only two intentional signal-branch junctions; no unrelated crossing/overlap, self-intersection, stale fragment, or body traversal. ERC/connectivity findings are zero; expected BOM metadata warnings remain out of scope.
- Operator visual review confirmed that candidate `03` is much clearer overall, but its left `IN` glyph was actually the native OUT-port style rotated to point left. Rotation does not change port meaning/shape. Classification: **QUALITY FAIL**; native round-trip was intentionally skipped.
- The operator replaced only that glyph in the same document with a real native input port (`NetPort5`, embedded style `CompType12`) and saved it unconnected. Operator-modified source SHA-256: `116fa02413014272e27a1a5d261a97f25ad993dcf1543f9a6376cf59fe3e26f9`; exact public-MCP inspection evidence `operator_input_port_mcp_evidence.json`, SHA-256 `5162e9298004abd189209799697d6ebd085d6651b79f5a4cdbb2d5c08a38c62b`. The expected two unconnected-pin findings were `NetPort5:0` and `R1:1`; all other topology remained intact.
- Candidate `04` is a byte-for-byte disposable copy of that operator source, changed only through public MCP: move the native input port into the signal row, name it `IN`, connect `IN=[NetPort5:0,R1:1]`, and add the single pin-to-pin wire. All other component positions and six existing wires are unchanged.
- Candidate `04`: `.local/validation/schematic-quality-9ee4e00/collision-placement-04/collision_placement_mcp_04.dchxml`, SHA-256 `cbcbc6a2b8b853a4bedb08a2ecc0e97f28c9592865f559adf8c6e855bb855778`; exact 16-call evidence `collision_placement_mcp_04_evidence.json`, SHA-256 `4ee2f96ff36e6d2415436406fb58d84ff9c490287ec888af41ad0fa03485471b`.
- Candidate `04` automated precheck: eight parts/twelve pins/four nets/seven wires; exact endpoint counts `IN=2`, `N1=3`, `OUT=3`, `GND=4`; ERC/connectivity findings zero. All wires are straight orthogonal segments apart from a sub-micrometre native coordinate-normalization stub at the new input endpoint. Eight schematic-review warnings are only missing manufacturer/MPN metadata and are out of scope.
- Operator visual verdict on candidate `04`: "Да, все ок". The corrected native input port and complete two-stage RC layout are accepted as readable without routine cleanup.
- Native Save left candidate `04` byte-identical, SHA-256 `cbcbc6a2b8b853a4bedb08a2ecc0e97f28c9592865f559adf8c6e855bb855778`; Close/Reopen and Save As succeeded. Native re-export `collision_placement_native_reexport_04.dchxml` SHA-256: `eb682e5761f2e776b0affabfc6ab099e3e65705d61372cc76e2bcb3d8a0ee52e`.
- The first fail-closed comparison reported `parts`, `patterns`, and `wire_geometry`. Investigation found only native canonicalization: DipTrace removed duplicate embedded component/pattern aliases while retaining each placed name/value and symbol/pattern geometry, rounded `270.000631°` to `270.000001°`, and removed a redundant approximately `7 nm` input-wire stub. Component positions, visible values, four net memberships, endpoint counts, and all meaningful wire endpoints survived.
- Focused evidence-comparator repair canonicalizes embedded pattern aliases within component aliases, ignores library default Name/Value only while comparing a placed component's style (the placed Name/Value remain compared independently), tolerates native angular precision, and removes only consecutive wire points equal at the existing coordinate precision. No public tool or parameter changed. Production/test diff SHA-256: `27d12245cf0ce4b6a5e7bb2d6507519b9d9145f12b3a19d4a8625ed1e3f269c8`.
- Regression evidence: 64 affected prompt-acceptance/trust tests pass; Ruff and `git diff --check` pass. Explicit mutations of symbol geometry, pattern pad position, meaningful rotation, and wire endpoint remain fail-closed. This evidence-only change does not affect authoring or require another real-host visual retest.
- Final semantic comparison: PASS and complete across all 12 required schematic categories, with no differences, missing categories, parse warnings, or unsupported categories. Disclosed native normalizations: `coordinate_precision`, `equivalent_component_style_alias`. Re-export ERC/connectivity findings are zero.
- Exact public-MCP round-trip evidence `collision_placement_native_roundtrip_04_evidence.json`, SHA-256 `9d7aee8bac01fcbfc484c1c3f34c24be560777f160d1c57f0a1013014e5b9698`; manifest SHA-256 `b2b2809df06a95cf2f9c5c52b34c47aa9fe2c740c8346b2eaef0741642d7fc87`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for candidate `04` — exact intended topology, operator-accepted placement/routing/readability, and native Save/Close/Reopen/re-export preserved all compared semantics. Candidates `01`–`03` remain retained **QUALITY FAIL** evidence. Divider, LED, RC, and unrelated historical gates remain valid. Next meaningful case: `05 RefDes/Value/net-label pressure`.

### 05 RefDes / Value / net-label pressure

- Candidate identity: `d742c4a7ecfefa28012b953f5dcd8d5243768f72`; DipTrace format/host remains `5.3.0.3`. A byte-for-byte copy of the native-canonical collision-case re-export supplies real IN/OUT/VCC/GND/resistor/capacitor styles; all cleanup and design authoring then use guarded public MCP calls.
- Circuit: AC-coupled biased input stage. `IN -> C1(100n) -> AC_BIAS -> R3(1k) -> BIAS_OUT -> OUT`; `R1(100k)` connects VCC to BIAS_OUT and `R2(100k)` connects BIAS_OUT to GND. The two internal wires carry native net labels `AC_BIAS` and `BIAS_OUT`, while all passive RefDes/Value markings are globally visible.
- Candidate `01` was rejected before native open as **QUALITY FAIL**: its VCC port was placed at `y=90 mm`, repeating the already established divider border-risk, and its long labels had only approximately `12–15 mm` of horizontal corridor. No operator round-trip was requested. Artifact SHA-256 `64e3bd9cd09d4c4196267f5a2678e50b892144ccaae9648b37e539cfd8b8709e`; exact 23-call evidence SHA-256 `6563473bfd3580e77c43c8825eaa11d0a609e93bd4dd836798166758f8fd43b2`.
- Candidate `02` changes only placement spacing: VCC moves to `y=85 mm`; the divider compacts safely below it; each internal label receives approximately `19–20 mm` of straight wire corridor. Topology, component values, orientations, label text/font, and public operation sequence are unchanged.
- Candidate `02`: `.local/validation/schematic-quality-d742c4a/refdes-value-label-pressure-05/text_pressure_mcp_02.dchxml`, SHA-256 `b6481aab981fe0b132d6a47a3cbffe0f888bc04d6ce6c37935c49a49d2fae4d6`; exact 23-call public-MCP evidence `text_pressure_mcp_02_evidence.json`, SHA-256 `7cd2dccca85f2e116aecfc9392601e7c7887ccccaeb44aadbb501057d97081a4`.
- Candidate `02` automated precheck: eight parts/twelve pins/five nets/seven wires; exact endpoint counts `IN=2`, `AC_BIAS=2`, `BIAS_OUT=4`, `VCC=2`, `GND=2`; two intentional BIAS_OUT branches meet its horizontal trunk at one junction. All seven wires are straight orthogonal segments with zero bends, no unrelated crossing/overlap, and no stale fragment. Both net-label anchors lie on their own wire. ERC/connectivity findings are zero. Eight review warnings are only missing manufacturer/MPN metadata and are out of scope.
- Operator visual verdict on candidate `02`: "все отлично". RefDes, values and both labels are readable; no text/body/wire collision or routine cleanup need was reported. Screenshot `operator_visual_candidate_02.png`, SHA-256 `189fa13dbe926237db5813b7f0c17abc0e09ea3d703afc6d1a58b3197b13211e`.
- Native Save left candidate `02` byte-identical, SHA-256 `b6481aab981fe0b132d6a47a3cbffe0f888bc04d6ce6c37935c49a49d2fae4d6`; Close/Reopen and Save As succeeded. Native re-export `text_pressure_native_reexport_02.dchxml` SHA-256: `3092d9c3c5427fbf55390c267ea458f78a7e5a5806c9146b875bea7dcd8f9db6`.
- The first fail-closed comparison reported only `parts`/`patterns`. DipTrace had cloned the virtual VCC `PartType="Net Port"` style and changed its stale resistor-pattern `PadId=-1` to `PadId=1`; symbol geometry, electrical type, pin geometry, placed name, placement and VCC membership were unchanged. Net ports never represent PCB components, so their pattern/pad association has no native design meaning.
- Focused comparator repair excludes pattern and PadId only while signing a `PartType="Net Port"` library style, while preserving comparison of its symbol/pin/electrical semantics. Pattern pad geometry and pin-to-pad mapping changes on ordinary components remain fail-closed. Normalization detection now matches reindexed schematic parts/pins/wires by canonical identity, so applied `coordinate_precision` and `equivalent_component_style_alias` policies are disclosed rather than silently omitted. No public MCP tool or parameter changed. Production/test diff SHA-256: `67010abe3d6c1fa02aff80d608e201c49ebdf7276251cda03af088bd80c7c98c`.
- Regression evidence: 64 affected prompt-acceptance/trust tests pass; Ruff and `git diff --check` pass. This evidence-only change does not affect authoring or require another real-host visual retest.
- Final semantic comparison: PASS and complete across all 12 required schematic categories, with no differences, missing categories, parse warnings, or unsupported categories. Disclosed native normalizations: `coordinate_precision`, `equivalent_component_style_alias`. Re-export ERC/connectivity findings are zero.
- Exact public-MCP round-trip evidence `text_pressure_native_roundtrip_02_evidence.json`, SHA-256 `2e54706fa100b608632ce611c468a68ec8ed28be2ded8eebe476de08659fed9d`; manifest SHA-256 `7971110ce3bb995113613196edfcbd681ee79e43bc951f9d1d5eb1f6d25fce95`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for candidate `02` — correct biased-input topology, operator-accepted RefDes/Value/net-label readability, and native Save/Close/Reopen/re-export preserved all meaningful semantics. Candidate `01` remains retained pre-open **QUALITY FAIL** evidence. Cases 01–04 and unrelated historical gates remain valid. Next meaningful case: `06 small multi-net schematic`.

### 06 small multi-net schematic

- Candidate identity: `b9a0d79`; DipTrace format/host remains `5.3.0.3`. The native-canonical case-05 re-export is copied byte-for-byte, then its 8 placements, 5 nets and 2 labels are removed through guarded public MCP edits. All design authoring uses public transactions; no internal schematic planner/API is used.
- Circuit: two side-by-side passive input channels. Each channel is `IN_x -> 1k -> FILTER_x -> OUT_x`, with a `10k` pull-up from VCC and `100n` shunt capacitor to GND. The channels share logical VCC/GND nets while using local native power/ground ports, avoiding a large cross-sheet rail.
- Candidate `01`: `.local/validation/schematic-quality-b9a0d79/small-multi-net-06/small_multi_net_mcp_01.dchxml`, SHA-256 `fa9d768059ac5ad2a86e2ae525ec618befa0701ec01bf5748587fbeac4a13d8a`; exact 23-call public-MCP evidence `small_multi_net_mcp_01_evidence.json`, SHA-256 `46dc11f4fb807220f104306dbecb0ae10a3c5535795a42dcf353cd962f5c27fb`.
- Automated precheck: fourteen parts/twenty pins/six nets/twelve wires; exact endpoint counts `IN_A=2`, `FILTER_A=4`, `IN_B=2`, `FILTER_B=4`, `VCC=4`, `GND=4`. Both FILTER trunks have one pull-up and one capacitor branch at an intentional junction. All wires are straight orthogonal segments with zero bends; there is no unrelated crossing/overlap, diagonal, self-intersection, stale fragment or shared remote power bracket. Labels `FILTER_A`/`FILTER_B` anchor to their own trunks and passive values are visible. ERC/connectivity findings are zero. Fourteen review warnings are only missing manufacturer/MPN metadata and are out of scope.
- Operator verdict on candidate `01`: "Вторая плата сильно за границей". The second functional group visibly crosses the sheet's right working boundary. Screenshot `operator_visual_candidate_01.png`, SHA-256 `1e153b0d729e07e1b2ca4966286e3740ed24c0771c854a213218d04c37abb2df`. Classification: **QUALITY FAIL**; native round-trip was intentionally skipped.
- The normalized public schematic model exposes only sheet id/name/type, not the effective visible working boundary; no MCP-contract expansion is made during this campaign. Candidate `02` therefore applies the smallest conservative repair using the observed native boundary: identical topology/orientations/values, with both groups compacted from `x=8..170 mm` to `x=5..130 mm`. Displayed internal labels shorten to `FILT_A`/`FILT_B`; net names remain `FILTER_A`/`FILTER_B`.
- Candidate `02`: `.local/validation/schematic-quality-b9a0d79/small-multi-net-06/small_multi_net_mcp_02.dchxml`, SHA-256 `60b073c1faf758c71e888198a9d556824121da3d5342bfa8bd143be4b2c4a23e`; exact 23-call public-MCP evidence `small_multi_net_mcp_02_evidence.json`, SHA-256 `09d1c1c17ae9f7913d498909ce3aaf8f5591c0979fb7519707e69c8cb3e46ac1`.
- Candidate `02` retains the exact 14-part/20-pin/6-net/12-wire topology, endpoint counts, straight orthogonal geometry, intentional junctions, zero ERC/connectivity findings, and only the same out-of-scope BOM warnings. No production code changed.
- Operator verdict on candidate `02`: "все равно выходной порт B заходит за границы". OUT_B at `x=130 mm` still visibly crosses the right working boundary, observed near `x=127 mm`. Screenshot `operator_visual_candidate_02.png`, SHA-256 `81ad059320098e842b035be371e2dc128a66022c521fd825613a93a7cd54eab0`. Classification: **QUALITY FAIL**; native round-trip was intentionally skipped.
- Candidate `03` keeps the identical topology, orientations and values, but moves the two groups to `x=3..55 mm` and `x=68..120 mm`; OUT_B now has an observed-boundary margin. Display labels are `A_FILT`/`B_FILT`; logical net names remain `FILTER_A`/`FILTER_B`.
- Candidate `03`: `.local/validation/schematic-quality-b9a0d79/small-multi-net-06/small_multi_net_mcp_03.dchxml`, SHA-256 `5c8be23b9f6e51a8fd8f2dd256a2213df3d94316ae2a1769b7e6af1a2549c98a`; exact 23-call public-MCP evidence `small_multi_net_mcp_03_evidence.json`, SHA-256 `e075fefee4ba5e89f8e15df5eb8356a882b653a52a6053adc4e51cc173768b34`.
- Candidate `03` retains the exact 14-part/20-pin/6-net/12-wire topology and endpoint counts, straight orthogonal geometry with zero bends, intentional junctions, zero ERC/connectivity findings, and only the same 14 out-of-scope BOM warnings. No production code changed.
- Operator visual verdict on candidate `03`: "Да, отлично". Both functional groups fit within the visible sheet boundary and need no routine visual rework.
- Native Save left candidate `03` byte-identical, SHA-256 `5c8be23b9f6e51a8fd8f2dd256a2213df3d94316ae2a1769b7e6af1a2549c98a`; Close/Reopen and Save As succeeded. Native re-export `small_multi_net_native_reexport_03.dchxml` SHA-256: `c4d954832aba75bc8d26086addaf239f9675cc37a9faa350b480b65e7e048354`.
- Re-export retains 14 parts, 20 pins, 6 nets, 12 orthogonal wires and exact endpoint counts. ERC/connectivity findings remain zero. Semantic comparison is complete and passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalization: `coordinate_precision`.
- Exact public-MCP round-trip evidence `small_multi_net_native_roundtrip_03_evidence.json`, SHA-256 `d4e18091232989f3aa9e92c94169673c580ed0b7636c2e1ca26d88c49c607b1e`; manifest SHA-256 `867a08ce8468521105bf2ca307bd197b73e5fa9b0977bf1de1a6e05d6447aae4`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for candidate `03` — correct independent-channel and shared-power topology, operator-accepted composition/readability, and native Save/Close/Reopen/re-export preserved all meaningful semantics. Candidates `01` and `02` remain retained **QUALITY FAIL** evidence. No production code changed, so cases 01–05 and unrelated historical gates remain valid. Next meaningful case: `07 realistic functional block`.

### 07 realistic functional block

- Initial code identity `7971d44`. Intended circuit: an AC-coupled ADC input front-end with 100k/100k VCC bias, input protection/isolation resistor, 1k ADC isolation resistor and 1n shunt anti-alias capacitor. This exercises an actual functional signal chain and bias/filter branches rather than repeating case 06's independent passive channels.
- Product defect found before authoring: valid public `create_document_from_seed` rejected the case-06 native re-export with `write_object_limit_exceeded` (`1227 > 500`). The guard charged every XML descendant as changed even for an exact byte copy to a new absent target, contradicting the tool's intended real-export seed workflow. The case attempt itself is **INVALID ATTEMPT**; no schematic result was produced.
- Root fix commit `1a8eaee`: exact validated seed copies to new targets are exempt from the mutation object limit because they are non-destructive, byte-identical and already bounded by `max_document_bytes`. Seed-copy overwrite and every semantic/raw XML mutation remain fail-closed. No public tool or parameter was added. Production/test commit diff SHA-256: `2d181f958a330c346d1a46f3c1e605dffd7d8793d83ef1b93038f2ffa92dbf44`.
- Regression evidence: 95 affected write-limit, SHA-gate, scaffolding and trust tests pass; Ruff and `git diff --check` pass. Exact oversized/deep new-target copies are covered; oversized overwrite remains rejected without changing its target. Commit pushed to `codex/schematic-quality-divider`.
- One subsequent setup batch combined deletion of all seed parts, nets and labels and correctly hit the unchanged per-mutation guard (`587 > 500`). Classification: **INVALID ATTEMPT**, not a product failure; the exact seed target remained unmodified. The public cleanup was split into two guarded writes without changing production code.
- Candidate `01` code identity `1a8eaee`: `.local/validation/schematic-quality-1a8eaee/realistic-functional-block-07/realistic_adc_frontend_mcp_01.dchxml`, SHA-256 `6295b432e18a2a9acdff2cec0372bbc403260fab1c6b0da07538c316c780c65a`; exact 26-call public-MCP evidence `realistic_adc_frontend_mcp_01_evidence.json`, SHA-256 `1d33075744f78bc5c479dd68527c961a5b7d22a955eeb00749a0ff7ae7a1f646`.
- Candidate topology: `SENSOR_IN -> C1 100n -> R3 1k -> VBIAS -> R4 1k -> ADC_IN`; R1/R2 form the 100k/100k VCC-to-GND bias at VBIAS; C2 1n shunts ADC_IN to GND. Eleven parts, seventeen pins, six nets and ten straight orthogonal wires; endpoint counts are `SENSOR_IN=2`, `AC_COUPLED=2`, `VBIAS=4`, `ADC_IN=3`, `VCC=2`, `GND=4`. No diagonal, bend, unrelated crossing/overlap or stale fragment is present. ERC/connectivity findings are zero. Eleven review warnings are only missing manufacturer/MPN metadata and are out of scope.
- Operator visual verdict on candidate `01`: "Да, ок как какая то абстрактная схема". Composition/readability is accepted; the qualification reflects that this is a reusable passive ADC front-end without the consuming ADC/MCU, not a placement/routing defect. The case is bounded to a realistic functional block rather than a complete device design.
- Native Save left candidate `01` byte-identical, SHA-256 `6295b432e18a2a9acdff2cec0372bbc403260fab1c6b0da07538c316c780c65a`; Close/Reopen and Save As succeeded. Native re-export `realistic_adc_frontend_native_reexport_01.dchxml` SHA-256: `4d150d43654e2d45d51854c06782262c3ea75cdba49707ef30097ca1241124e3`.
- Re-export retains 11 parts, 17 pins, 6 nets, 10 orthogonal wires and exact endpoint counts. ERC/connectivity findings remain zero. Semantic comparison is complete and passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalization: `coordinate_precision`.
- Exact public-MCP round-trip evidence `realistic_adc_frontend_native_roundtrip_01_evidence.json`, SHA-256 `f3cfcd7ec61bb67ea62ef7389deacb7e963b697a7decdb06e13d78745ff85237`; manifest SHA-256 `a0aa17505262d02b47c1792e8fcf776c8a160494df567ddd674cacdf731316ec`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for candidate `01` within its stated passive ADC-front-end scope — correct bias/filter topology, operator-accepted composition/readability and native round-trip preserved all meaningful semantics. The seed-copy defect is fixed and its exact affected real-host retest is included in this successful open/save/re-export; the automated oversized-overwrite check supplies the single adjacent smoke. Cases 01–06 and unrelated historical gates remain valid. Next meaningful case: `08 datasheet/reference-style placement`.

### 08 datasheet/reference-style placement

- Native reference: DipTrace `Astable_Flip_Flop`, eleven-part symmetrical two-transistor astable. Two initial Save As attempts produced binary `.dch` content under the requested export names and are retained as **INVALID ATTEMPT**. Valid operator XML export `.local/validation/astable_seed_08.dchxml` has SHA-256 `4d8e48bf4b5a5df84d1d6a477518f705a7fb60ad6f9ff225402ce7b337d69106` and DipTrace version `5.3.0.3`.
- Public-MCP reference inspection found 11 parts, 24 pins, 8 nets and 16 wires; connectivity findings are zero. Candidate `01` rebuilt the translated reference through guarded move/rename/value/delete-wire/add-wire operations: `astable_reference_rebuild_mcp_01.dchxml`, SHA-256 `4a58fcab580a10172df10ab4b2286916f663d51c1369cb100e9326c76e7a3a32`.
- Candidate `01` is a pre-open **QUALITY FAIL**. Sub-micrometre native pin-coordinate drift was classified as a diagonal and caused a good GND rail to be replanned; the following branch then attached to the replanned rail's stale segment index. Two simple intentional cross-coupled branches were independently replaced by three-bend hooks. Native visual round-trip was intentionally skipped.
- Root repair stays internal and does not expand the MCP contract: orthogonal classification uses the existing pin-anchor tolerance, and a crossing-only cleanup is rejected when it requires more than two added bends. Actual symbol hits, overlaps, self-intersections and diagonals remain eligible for repair; an ordinary two-bend crossing repair remains accepted.
- Automated evidence: 65 affected wire-quality/planner/pin-geometry/atomic-reroute/joint-optimizer/placement/authoring tests pass; Ruff and `git diff --check` pass. Exact regressions cover native sub-micrometre axis noise and the branch-to-wire three-bend hook.
- Candidate `02` was created successfully, but the evidence harness used exact coordinate equality and rejected the intentionally preserved sub-micrometre native drift. It is retained as **INVALID ATTEMPT**; no product result was assigned. The harness check was corrected to the established `1e-6 mm` tolerance.
- Candidate `03` on fixed identity `31cc0fa`: `astable_reference_rebuild_mcp_03.dchxml`, SHA-256 `07927f2d51da06d36d6c0b7a66e5d6c7f625f89392acd762351d0805f0a6fcde`; exact 23-call evidence SHA-256 `7765361c8be003a3e456a611ab98c30ff0076194363137c33aa8de83294598eb`. Automated precheck retained 11 parts, 24 pins, 8 nets, 16 orthogonal wires and exact endpoint counts; ERC/connectivity findings are zero.
- Operator visual verdict on candidate `03`: "Идеально!". The translated native reference composition, intentional cross-coupled crossings and readable rail/branch geometry were accepted without cleanup.
- Native Save left candidate `03` byte-identical. Close/Reopen and Save As succeeded; re-export `astable_reference_native_reexport_03.dchxml` SHA-256 `8964a54b396d229483a518b586d19a212fc1d8ebe02474d1c61a6e014cfd48a7`. Parts, pin/net membership, net endpoint counts and ERC/connectivity all survived, but fail-closed comparison reported `wire_geometry`.
- Candidate `03` is **SEMANTIC FAIL** for native round-trip. Both cross-coupled Wire endpoints were authored with `Bus=-1`; DipTrace requires the containing net id (`Bus=1` / `Bus=4` here). On Save, DipTrace repaired the endpoint metadata and moved each branch from its intended trunk junction to the base pin of Q1/Q2, materially changing routing geometry.
- First root repair set the existing Wire endpoint `BusN` attribute to the containing native net id in the shared `add_wire` serializer. Candidate `04`, SHA-256 `4c4fcc953953843a82dfec1231518aa3cb81de1f18021f2737d197929ede3750`, was geometrically identical to accepted candidate `03`; operator focused verdict: "Все ок". Native re-export SHA-256 `d1b3d718a610171386ec6d925613d8c92c3e718778b1134fee11ef13f9ba739f` still changed the same two branches, so candidate `04` also remains **SEMANTIC FAIL**.
- Second root cause: routing correctly treated sub-micrometre axis drift as orthogonal, but XML `Point Dir` serialization still used exact `dx/dy == 0`, emitting `Dir=-1` for every affected segment. DipTrace then reconstructed Wire-to-Wire branches despite the repaired Bus reference. Direction serialization now uses the same `1e-6 mm` tolerance. No public MCP contract changed.
- Automated evidence after both repairs: 66 affected schematic authoring/routing tests pass; Ruff and `git diff --check` pass. Regressions assert both native Wire `BusN` and horizontal/vertical `Dir` under sub-micrometre noise.
- Impact-based retest: rebuild only case-08 candidate `05`. Its source geometry is already covered by the two accepted focused visual checks, so only native Save/Close/Reopen/re-export and reporting any unexpected visual change are required. Pin-to-Pin serialization is the automated adjacent smoke. Cases 01–07 and unrelated gates remain valid. Case `09 atomic reroute — one net` remains next only after case 08 closes.
- Final candidate `05` on code identity `d6a7b80`: `astable_reference_rebuild_mcp_05.dchxml`, SHA-256 `d10a029b48fd42fdedaf803e54f8885eaff49d79f5b70bea9ba53548f8550844`; exact 23-call build evidence SHA-256 `c9e7cda8f64cbdaed4f1e6c55d52aa4439d8fdd3217e18bf386fb3123eb85bcb`. It is semantically/geometrically identical to accepted candidates `03`/`04`, with every Wire endpoint Bus matching its containing net and every noninitial orthogonal Point carrying native `Dir=0/1`.
- Targeted native retest: operator reported no visual regression. Save left source byte-identical; Close/Reopen and Save As succeeded. Native re-export `astable_reference_native_reexport_05.dchxml` SHA-256 `71d12d039502e8eab071b03ce0c490956458d4c673cd7b9cb9c667423a094436` retains 11 parts, 24 pins, 8 nets, 16 wires, exact endpoint counts and all intended branch geometry. ERC/connectivity findings are zero.
- Final semantic comparison passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalization: `coordinate_precision`. Exact public-MCP round-trip evidence SHA-256 `453d41d4159a6ad7943c3d19c0eff089b9fbad84948b700f97bc4e05d59170a5`; manifest SHA-256 `459b87216da9c62f7e7663b74803c814f775e3c78fbb70fa4be972f96570a113`. Authority remains `user_supplied`, `grants_high_trust=false`; tooling did not assign product PASS.
- Final classification: **PASS** for repaired candidate `05` — reference-style placement/routing was operator-accepted and native Save/Close/Reopen/re-export preserved electrical and visual semantics. Candidate `01` remains **QUALITY FAIL**; candidates `03`/`04` remain **SEMANTIC FAIL** native reproductions; setup/evidence attempts are retained as **INVALID ATTEMPT**. Cases 01–07 remain valid. Next meaningful case: `09 atomic reroute — one net`.

### 09 atomic reroute — one net

- Code identity `5ec8b60`. Runtime introspection confirms the frozen 159-tool public contract has no direct atomic-schematic-reroute entrypoint; the documented planner remains internal. The real client workflow therefore uses the intended public composition without contract expansion: one guarded transaction containing `delete_wire* -> move_components -> add_wire*`, with one stage/validate/commit boundary.
- Scope is only divider net `OUT`: delete its two explicit wires, move the one-pin OUT port horizontally, rebuild its resistor trunk and midpoint branch. GND/VCC geometry must remain byte-for-byte equivalent in the public model; endpoint counts remain `GND=2`, `OUT=3`, `VCC=2`.
- Candidate `01` committed safely but the evidence harness used rounded `x=50.0` instead of the public model's native `50.0000016 mm` junction axis, producing an avoidable hook. Classified **INVALID ATTEMPT** caused by the client request; no production change was made.
- Candidate `02` uses the exact public-model junction coordinate. One atomic transaction deleted two OUT wires, moved only the OUT port, then added exactly two replacement wires; GND/VCC remained unchanged, no stale fragment remained, and ERC/connectivity findings were zero. Artifact SHA-256 `42de1d7c24e041190234cfa9dbd3584e805e504e756ad3292f99ad56914d5d0a`; exact 11-call evidence SHA-256 `de4b3a5f12480b42ea9103d45a3f792190326ddd5c0548a5408715d1fa60fe19`. Operator visual verdict: "Да, все ок".
- Candidate `02` native Save/Close/Reopen/re-export preserved every component position, pin/net membership and wire point, but DipTrace populated/reindexed stale embedded SpiceModel and PadStyle data across all parts, including untouched GND/VCC/R1/R2. This host-wide Design Cache canonicalization is independent of atomic reroute, but simulation metadata is semantic, so the attempt was not promoted to PASS. The canonical native re-export was used as the next seed, matching the established RC-case recovery pattern.
- Final short-name candidate `c09_03.dchxml`, SHA-256 `ba3d263a5bd06284d9157a6dced4cbbff2ee760c778767091def4e3b0bb4aa78`, repeats the same single-net atomic workflow on the native-canonical seed; exact build evidence `c09_03_e.json` SHA-256 `e927b7ca2710332ac4bd5cbdadf9980dd65f891dbc8d39c5e13baa1e3248d2ba`. The OUT port moves to `x=90 mm`; two OUT wires replace two OUT wires, while GND/VCC remain unchanged. ERC/connectivity findings are zero and no visual regression was reported.
- Native Save left the final source byte-identical. Close/Reopen and short-name re-export `c09_rt03.dchxml` succeeded, SHA-256 `3303488ae5727f879d72f16d69c3caf710ad1894928ae6545634f380255d832d`. All four wire geometries and exact endpoint counts survived.
- Final semantic comparison passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalizations: `coordinate_precision`, `whitespace_in_text`. Evidence `c09_ev03.json` SHA-256 `e4a85cfa5e7f690f37ab79da362eee4855f6885fa4ac307cdee1f13f17a4efa2`; manifest SHA-256 `217e8401469770a9b5873c5ba18f20b21695d9e64a30b389c99bdb3528a08b2e`. Authority remains `user_supplied`, `grants_high_trust=false`.
- Final classification: **PASS** — one affected net was replaced atomically with correct readable geometry, unchanged neighboring nets, no stale fragments and stable native round-trip. No production code changed; cases 01–08 remain valid. User requested short artifact names for all later GUI handoffs. Next meaningful case: `10 atomic reroute — multiple nets`.

### 10 atomic reroute — multiple nets

- Code identity `7b2f283`; short artifact naming is used. Native-canonical case-09 re-export is the seed. Moving R1 upward by 5 mm affects exactly `OUT` and `VCC`; `GND` is the explicit unaffected neighbor.
- One public guarded transaction stages `delete_wire x3 -> move_components x1 -> add_wire x3`, validates, and commits once. Both OUT wires and the VCC wire are replaced; GND points remain exactly unchanged. The result retains 5 parts, 7 pins, 3 nets, 4 orthogonal wires and endpoint counts `GND=2`, `OUT=3`, `VCC=2`; no stale fragment remains. ERC/connectivity findings are zero.
- Candidate `c10_01.dchxml` SHA-256 `591757f59a603314978f7c89c6244adaddebad22c701d5cbf80eaf86f4f92556`; exact 11-call build evidence `c10_01_e.json` SHA-256 `e9c6bf761444f8156b21f0ae6031ef288dca004d67423df656edf18f85fc4cac`. Operator visual verdict: "проблем не вижу".
- Native Save left source byte-identical. Close/Reopen and re-export `c10_rt01.dchxml` succeeded, SHA-256 `f78bdd46013cee60b24218f2d65453f15eb7d34eccdd58ec9b2a342985d5b2b2`. Both affected net geometries, unchanged GND and exact endpoint counts survived; ERC/connectivity remain zero.
- Final semantic comparison passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalizations: `coordinate_precision`, `whitespace_in_text`. Evidence `c10_ev01.json` SHA-256 `32a3039122347c389404b6ed32519ea99da06677412112b70141e099e970ee92`; manifest SHA-256 `0a76efdbaeef0fe1cb78c0a5efa3c9073bc3ce5ef86678e19bb0166b6897ce6d`. Authority remains `user_supplied`, `grants_high_trust=false`.
- Final classification: **PASS** — two affected nets were replaced in one atomic public transaction, the neighboring net stayed unchanged, visual quality was accepted and native round-trip preserved all semantics. No production code changed; cases 01–09 remain valid. Next meaningful case: `11 atomic reroute near obstacle`.

### 11 atomic reroute near obstacle

- Code identity `104b50d`; native-canonical case-10 re-export is the seed. Candidate `c11_01.dchxml`, SHA-256 `f011e2046232aeaf6580ba58866f3be7ecbe18eec9afc2ea8cbedcdcd838c3ec`, moved OUT onto R2's row and atomically replaced both OUT wires. Connectivity, ERC, unaffected GND/VCC geometry and endpoint counts remained correct, but the cleaner produced a three-bend U-shaped branch around R2. Exact public-MCP evidence `c11_01_e.json` SHA-256 `1fca3a98a2958a46b6ee03d72801f6aa42e853f8063e27c8a7f7d526a174fefd`; screenshot `c11_01_fail.png` SHA-256 `b71ab0096ecf4e2db60d5eeb4d4df7210330000cff8f16fa105d4e6773c8094d`.
- Operator verdict: "о не, прям косяк, человек бы так не сделал, он бы просто направо повёл линию между резисторами". Candidate `01` is **QUALITY FAIL**; native round-trip was intentionally skipped. Diagnosis confirms the low-level router correctly avoided the symbol obstacle and the internal planner already surfaces readability feedback; the failed choice is the accepted endpoint placement, not wire serialization or connectivity. Existing bounded placement-repair regression covers axis alignment, so no duplicate production code or public MCP contract was added.
- Candidate `c11_02.dchxml`, SHA-256 `ad56b5afef4fc23115a4e6e20658c99820824dead034908441533b0eabcf3ff0`, is the minimal public-path repair: one guarded transaction deletes only the ugly OUT branch, aligns the OUT port with the divider junction and authors one straight replacement segment. GND/VCC are exactly unchanged; the result retains 5 parts, 7 pins, 3 nets, 4 wires and endpoint counts `GND=2`, `OUT=3`, `VCC=2`; ERC/connectivity findings are zero. Exact evidence `c11_02_e.json` SHA-256 `aa51e6212939181cc36d14ae8074de04058c4f5ef62ac16ce74d3088bc2c3ee7`. Focused operator visual verdict: "Все ок". Prior cases and unrelated gates remain valid.
- Native Save left candidate `02` byte-identical. Close/Reopen and re-export `c11_rt02.dchxml` succeeded, SHA-256 `e8cab11467ecae453437a757d0c7845bd79ba6a44ddaf8a92d0b7a1836b44bb6`. All four wire geometries, unchanged GND/VCC and exact endpoint counts survived; ERC/connectivity findings remain zero.
- Final semantic comparison passes all 12 required schematic categories with no differences, missing/unsupported categories or parse warnings; disclosed native normalizations: `coordinate_precision`, `whitespace_in_text`. Evidence `c11_ev02.json` SHA-256 `9efc4eb27fa74ca0ef7533e8645028d7e08e187899aa0ec1b06bc12b224a4128`; manifest SHA-256 `1de66372fbcbc5267b7ca9f256a62ef7b150ffd87b48040828d015a05586ca99`. Authority remains `user_supplied`, `grants_high_trust=false`.
- Final classification: **PASS** for repaired candidate `02` — the near-obstacle bad placement remains retained as candidate `01` **QUALITY FAIL**, while the minimal atomic placement/routing repair is electrically correct, operator-accepted and native-round-trip stable. No production code changed; cases 01–10 and unrelated gates remain valid. Next meaningful case: `12 atomic reroute with pre-existing ugly geometry/readability warning`.
