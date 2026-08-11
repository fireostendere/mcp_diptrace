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
