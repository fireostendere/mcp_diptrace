# Manual Acceptance Checkpoint — 2026-08-09, updated 2026-08-10

This file is the durable recovery checkpoint for the current real-system acceptance campaign.
Its purpose is to prevent already completed manual gates from being repeated after an interrupted
Work session, a focused repair, or later documentation-only commits.

The evidence archives themselves remain authoritative for individual observations. This document
records the accepted production candidate, completed gates, the intentional pause point, and the
next validation priority.

## Accepted production candidate

The production-code candidate accepted through the latest completed gates is:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

This is the merge of PR #68 (`Ponytail: aggressive repository cleanup`). The acceptance campaign
confirmed no relevant production-code drift through the COMMON, Q1 Component Angle, and Codex
restart gates.

Documentation-only commits made after this checkpoint do **not** invalidate that accepted
production-code identity. When resuming acceptance, distinguish documentation drift from changes to
`src/`, packaging/runtime code, plug-in code, or other files that can affect the tested behavior.

## Formal acceptance progress

Eight of the twelve blocking manual gates are now complete.

| Gate | Result | Accepted identity / evidence note |
| --- | --- | --- |
| `diptrace_current_pcb_roundtrip` | **PASS** | Real DipTrace 5.3 PCB open/save/re-export accepted after the PCB serialization repairs. |
| `diptrace_current_schematic_roundtrip` | **PASS** | Real DipTrace Schematic open/save/re-export accepted; authored connectivity survived native round-trip. |
| `diptrace_component_library_writer_roundtrip` | **PASS** | Real Component Editor `.eli` save/reopen/re-export, semantic preservation and second-pass idempotence accepted. |
| `diptrace_pattern_library_writer_roundtrip` | **PASS** | Real Pattern Editor `.lib` save/reopen/re-export, semantic preservation and second-pass idempotence accepted. |
| `diptrace_ratline_and_wire_roundtrip` | **PASS** | Generated PCB ratlines and authored schematic wires passed the historical real-host gate. |
| `diptrace_mask_paste_courtyard_common_semantics` | **PASS** | MASK, PASTE, COURTYARD and COMMON all accepted. |
| `diptrace_q1_component_angle` | **PASS** | Real DipTrace PCB Layout 5.3.0.3 angle/side semantics accepted on `0bb09b4...`. |
| `codex_real_client_restart` | **PASS** | Real Codex Desktop restart/configuration/`get_capabilities` accepted on `0bb09b4...`. |

The remaining blocking formal gates are:

1. `claude_desktop_real_client_restart` — **PENDING**.
2. `windows_clean_install_repair_uninstall` — **PENDING**.
3. `elevated_plugin_install_profile_preservation` — **PENDING**.
4. `custom_state_preservation` — **PENDING**.

Claim-specific optional work remains separate: public-redownload smoke for future changed release
bytes, external legal/Novarm review when required for a planned claim/activity, and a real openEMS
run only if external-solver validation is to be claimed.

## Mask / paste / courtyard / Common disposition

The composite gate is complete:

- MASK — **PASS**;
- PASTE — **PASS**;
- COURTYARD — **PASS**;
- COMMON — **PASS**.

The historical COURTYARD failure on
`4ddea7937661afedf9c195af558680c4705bb368` remains immutable evidence. It proved that DipTrace
correctly preserved `Source/Board/Settings/LineWidth/Courtyard` while the old MCP read surface did
not expose the semantic delta. PR #65 repaired the parser/read surface; the fresh retest on
`0bb09b4...` then passed.

COURTYARD fresh PASS hashes:

- baseline XML: `4db8e41429e04d18fdca048c368933c1ec257ac02d8e7ce35765cc64c48c2df9`;
- native `.dip`: `fd4f16cf447ba0f76bc67dc5f694dbe7453062653c594628978b2eb0aa23d1e2`;
- final XML: `7020f948dee94f2af7878c84d27cf0340f9aeca26c3b520089c93d2302cd6fce`;
- evidence ZIP: `8cf749f261e08739b8f536d1f845f96fe741bff7bf4dad3d960c59349f19a09f`.

COMMON fresh PASS hashes:

- baseline XML: `4db8e41429e04d18fdca048c368933c1ec257ac02d8e7ce35765cc64c48c2df9`;
- native `.dip`: `eaeed1d5ae09a12703b605a86f0e7da56ad4102d3316f2e40a818f0f21fb77e1`;
- final XML: `4bb2345b530a263b3c43665cca7827f2dc0dcd6617dfd79175be143b0ad619fa`;
- evidence ZIP: `7f6fa9288d2d13da2d0d2e3b86307bcd937b9412b819241ae7c51208926ee8ae`.

The accepted COMMON distinction is native omission for Common versus explicit override:
`mask_paste = {}` versus `mask_paste.TopMask = Tented`; no numeric default is invented.

## Q1 Component Angle disposition

`diptrace_q1_component_angle = PASS` on `main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`
with DipTrace PCB Layout 5.3.0.3.

Observed real-host semantics:

- `90° = Angle="1.5708"`;
- `180° = Angle="3.1416"`;
- `270° = Angle="4.7124"`;
- entering `360°` normalizes the GUI to `0°`, and the canonical zero export may omit `Angle`;
- an existing `6.2832` literal can survive while the GUI displays 0°, so 0/360 representations are semantically equivalent within the observed scope;
- `Change Side` from Top 90° produced Bottom `Angle="4.7124"`, `Flip="Y"`; the reader correctly reports `mirrored=true`;
- coordinates, pattern, connectivity and other non-orientation component properties were preserved;
- native open/save/re-export completed without warning, repair or error.

Q1 evidence ZIP SHA256:

`6b7d561e2fda4118cf6b4d94c137b04882f608d42dfc1f5148a093ac6b4a20bc`

The private/manual campaign PASS does not by itself redistribute the private source artifacts. If a
repository-owned public evidence flag/result is promoted later, that is a separate source-controlled
change and must retain the provenance/redistribution boundary.

## Codex real-client disposition

`codex_real_client_restart = PASS` on
`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`.

Observed environment and result:

- Codex Desktop: `26.803.5235.0`;
- DipTrace MCP: `0.2.1`;
- 159 tools available after both client restarts;
- both `get_capabilities` responses were identical, SHA256
  `b2d9a5f5...87bc861` as recorded in the private PASS evidence;
- new process IDs confirmed that Codex and the MCP server actually restarted;
- Git remained clean and production code did not change during the gate.

Codex evidence ZIP SHA256:

`931001886200eb928fd3a376f76bd14856b2f5dcffd9d023208285623887fbe8`

## Intentional pause before the remaining formal gates

The formal acceptance campaign is intentionally **PAUSED** here. The formal resume point remains:

`claude_desktop_real_client_restart`

Do not infer that Claude Desktop or any Windows lifecycle gate passed. They remain pending.

Before resuming those infrastructure/lifecycle gates, the project will prioritize a separate
real-world schematic authoring/readability validation. The reason is product confidence: the next
question is not merely whether the server installs and restarts, but whether it can produce a
normal, readable, useful schematic in real DipTrace.

This validation is not a replacement for the formal matrix and must not silently mark any pending
formal gate PASS.

## Immediate validation priority — real schematic authoring/readability

PR #66 added deterministic bounded readability routing for newly authored schematic wires, and the
subsequent Ponytail pass may have changed adjacent code. The historical
`diptrace_ratline_and_wire_roundtrip` PASS proves its exact historical scope, but it does not prove
that current higher-level schematic authoring produces good human-readable designs.

The next project validation should exercise current post-Ponytail code on small real circuits, for
example:

- resistor divider;
- LED + resistor;
- divider + capacitor / simple RC network;
- a deliberately collision-prone placement;
- cases with RefDes, Value and net labels near wires;
- at least one small multi-net schematic built from a clean starting point.

Inspect both electrical correctness and presentation quality:

- correct parts, pins and net connectivity;
- sensible component placement and orientation;
- orthogonal/Manhattan wire geometry where appropriate;
- no wire through unrelated symbols;
- no unnecessary wire crossings or collinear overlaps;
- no wire covering RefDes, Value or net labels;
- clear intentional junctions and no accidental junction implication;
- no absurd detours or needless bends;
- native DipTrace open/save/reopen/re-export preserves the result;
- the resulting schematic is understandable to a human without manual cleanup being the default.

Any reproducible visual/authoring problem should become a focused regression case and, if needed, a
separate code repair. Do not erase or rerun historical PASS evidence merely because this stronger
product-quality validation finds a new issue.

## Resume rules

When resuming work from this checkpoint:

- do not restart completed gates;
- treat `0bb09b4...` as the accepted production-code identity for the completed gates;
- ignore later documentation-only commits when evaluating production candidate continuity;
- if relevant production code changes, record the new candidate explicitly and rerun only the gates
  plausibly affected by that code change;
- keep historical FAIL attempts immutable;
- distinguish operator/path/seed mistakes from product defects;
- Work may prepare files, hashes, XML comparisons and evidence automatically; ask the operator only
  for meaningful real-GUI checkpoints;
- stop on a genuine blocking product FAIL and repair it separately;
- do not silently expand the public MCP contract while performing acceptance or validation repairs.

## Native library writer disposition

Real Component Editor and Pattern Editor host evidence exists for the internal raw-preserving
Component/Pattern mutation core. This does **not** automatically register new public MCP write tools.
Public registration remains a separate product/API decision.
