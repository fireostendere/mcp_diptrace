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
