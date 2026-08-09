# Manual Acceptance Checkpoint — 2026-08-09

This file is a recovery checkpoint for the current real-DipTrace acceptance campaign.
Its purpose is to prevent already completed manual gates from being repeated after a
failed experiment, interrupted Work session, branch repair, or later documentation
change.

The evidence archives themselves remain the authority for individual observations.
This document records the campaign disposition and the exact point from which work
should resume.

## Code identities at this checkpoint

- Current accepted `main` baseline before the Courtyard parser repair:
  `4ddea7937661afedf9c195af558680c4705bb368`.
- Courtyard repair PR: #65, `agent/fix-courtyard-project-settings`.
- Code-only PR #65 head that completed green PR workflows before these documentation
  checkpoint commits: `936fdf3d5c8378f5f42214813620eab95f3755ca`.
- Green workflows for that code-only head:
  - CI run `31320690490` / run number 547 — success;
  - Windows one-click installer run `31320690465` / run number 200 — success;
  - PyPI release workflow run `31320690467` / run number 59 — success.

Documentation commits added after that head must pass their own PR checks before merge.
They do not replace the real-DipTrace evidence listed below.

## Completed real-DipTrace gates

| Gate | Result | Accepted identity / evidence note |
| --- | --- | --- |
| `diptrace_current_pcb_roundtrip` | **PASS** | Real DipTrace 5.3 round-trip completed after the PCB serialization repairs merged through PR #62. Connectivity, native save/reopen and final XML re-export were accepted. |
| `diptrace_current_schematic_roundtrip` | **PASS** | Authoritative attempt used a real DipTrace-authored seed on commit `b9966f63e8ba3f3cc227dcff18f2de826043ecb7`; authored `WIRE_TEST` connectivity survived save/reopen/re-export. |
| `diptrace_component_library_writer_roundtrip` | **PASS** | Commit `b9966f63e8ba3f3cc227dcff18f2de826043ecb7`; real Component Editor seed; native `.eli` save/reopen; components, pins, fields, pattern attachment and pin-to-pad mapping preserved; second writer pass idempotent. Writer XML `b7c584d895fc520c34a269a7f593887ae57a780e1824c15e219167e72c81ccef`; native `.eli` `88d3ffcc354b8968676e16b5c791ac29e49226e9d7af5043ee0ce6849e263d0e`; final XML `3dba8713c0925a5931f0a7b28bcdc99e140dfaab363ab79c1754101152f4d8f6`. |
| `diptrace_pattern_library_writer_roundtrip` | **PASS** | Commit `4ddea7937661afedf9c195af558680c4705bb368`; DipTrace Pattern Editor 5.3.0.3; native `.lib` save/reopen, final XML re-export, semantic preservation and second writer pass all passed. Writer XML `4bf0df32f57e0bc8c2c782ad31c20012fca7ba4a76a3a32e7b5de83dbfead733`; native `.lib` `60f4ac03ae268b631682a4c8b35f8e6728b38cbebdccf09d9fcd50f93549db27`; final XML `4c71e90e0c8ebeffaa7c544faa407feab709f43e56e73f4a6ee8e3139ad8f7de`. DipTrace canonicalization of `UID32`, derived width and coordinate frame was classified as non-semantic. |
| `diptrace_ratline_and_wire_roundtrip` | **PASS** | Full gate PASS on `main@4ddea7937661afedf9c195af558680c4705bb368`. PCB Part A passed after PR #64 removed the avoidable non-endpoint-pad ratline collision. Schematic Part B passed in Schematic Capture 5.3.0.3. Part B generated `.dchxml` `a135709bd818143ef07caf5a05bae4317776d29092506c09357eb8fb9e50f04e`; native `.dch` `7a27285124a8b53b22be7a55a1a2696a4089b5e7ef8c7a69644e1abbec50cdad`; final `.dchxml` `d540c2babdfee0b822757a26f313ff79fff7ff1d4bd8c43b57ab2e111b9e997e`. |
| `diptrace_mask_paste_courtyard_common_semantics / MASK` | **PASS** | Recorded PASS in the current campaign. Do not repeat merely because COURTYARD required a parser repair. |
| `diptrace_mask_paste_courtyard_common_semantics / PASTE` | **PASS** | Recorded PASS in the current campaign. Do not repeat merely because COURTYARD required a parser repair. |

## Historical failures that are already resolved

These failures are evidence and must remain preserved. They are not reasons to restart
older PASS gates.

1. PCB current-roundtrip failures found serialization/canonicalization issues and were
   repaired through PRs #61 and #62 before the PCB gate was accepted.
2. Ratline acceptance on PR #63 / main
   `f4f2b6217aa70ec43ba56249f1626915ffe43258` correctly failed because a valid VCC
   ratline crossed an unrelated pad region. PR #64 fixed the layout-quality heuristic;
   PCB ratline Part A then passed on `main@4ddea7937661afedf9c195af558680c4705bb368`.
3. COURTYARD on `main@4ddea7937661afedf9c195af558680c4705bb368`
   found a parser-coverage defect, not a DipTrace save/open defect. DipTrace 5.3.0.3
   correctly preserved `Source/Board/Settings/LineWidth/Courtyard`, but MCP read
   surfaces could not distinguish `<Courtyard>0.05</Courtyard>` from
   `<Courtyard>0.1</Courtyard>`. The historical baseline export hash is
   `4db8e41429e04d18fdca048c368933c1ec257ac02d8e7ce35765cc64c48c2df9` and the
   changed export hash is
   `2fbd1ca4e374d0296022a425c7c41b23d154e7639174db4cd34dee5787ec0a1d`.
   PR #65 is the targeted parser repair.

## Current blocking point

`diptrace_mask_paste_courtyard_common_semantics / COURTYARD` is the first unfinished
item.

After PR #65 is merged, create a **fresh COURTYARD retest attempt only**. Confirm that
the same real-DipTrace one-setting-at-a-time delta is visible through the MCP read
surface as a typed millimetre project setting. Preserve the historical FAIL attempt;
do not overwrite it.

If COURTYARD passes, the next gate is **COMMON**. `COMMON` has not been run and must
not be marked PASS by inference.

## Remaining gates after COMMON

The remaining manual/external work is:

1. Q1 Component Angle GUI/re-export validation.
2. Real Codex configuration/restart/`get_capabilities`.
3. Real Claude Desktop configuration/restart/`get_capabilities`.
4. Clean Windows install/repair/uninstall acceptance for the applicable release bytes.
5. Elevated plug-in installation with original user-profile preservation.
6. Pre-existing custom-state preservation across install/repair/uninstall.
7. Claim-specific optional work only when needed: public-redownload smoke for changed
   release bytes, external legal/Novarm review for a planned claim/activity, and real
   openEMS execution if external-solver validation is to be claimed.

The earlier Windows/profile preflight found no active/blocking live session but did
find Component Editor and Pattern Editor plug-ins not installed. That preflight is
context for the later Windows/profile gates, not a failure of the already completed
native library round-trips.

## Resume rules

When resuming this campaign:

- start from the first unfinished item in this file, not from the beginning;
- never rerun a PASS gate solely because a later unrelated gate failed;
- rerun an earlier PASS gate only when a subsequent code change can plausibly affect
  that exact semantic/write path;
- keep every historical FAIL attempt immutable and create a new retest attempt after a
  repair;
- distinguish operator/path/seed mistakes from product defects;
- stop the campaign on a genuine blocking product FAIL, repair it on a focused branch,
  and resume only the affected gate after merge;
- do not silently expand the public MCP contract while performing acceptance repairs.

For PR #65 specifically, the code change is limited to reading project-level PCB
settings on existing MCP read surfaces. Therefore the completed PCB/schematic/library/
ratline gates and the already accepted MASK/PASTE portions are not invalidated by this
repair.

## Native library writer disposition

The real Component Editor and Pattern Editor host-evidence condition is now satisfied
for the internal raw-preserving Component/Pattern mutation core. This does **not**
automatically register new public MCP write tools. Public registration remains a
separate product/API decision; the current public contract remains intentionally
unchanged during this acceptance campaign.
