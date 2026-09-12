# Engineering Skills Review — 2026-09-10

## Conclusion

The original set of eight `skills/*/SKILL.md` files did not sufficiently explain
native DipTrace access. It focused on the public MCP tools and could push the model
toward a false conclusion: "no tool or live session — the editor cannot be opened".
That is an instruction defect, not evidence that headless access is absent.

All eight skills, the catalog, the capability map, the generator/tests, the release
packaging, and the corresponding code were reviewed. All eight were updated; seven
new skills were moved from `.opencode/skills` into the canonical root `skills/`.
Standalone copies of the new skills under `.opencode/skills` were removed; their
content is preserved in the root set. Existing `.agents/skills` recipes were not
modified.

## Findings and fixes

| Priority | Problem | Fix |
|---|---|---|
| High | The MCP catalog was perceived as the entire available interface; the explicit XML path was conflated with a live session | A shared [runtime access](../skills/shared/runtime.md) document is linked from all 15 skills; MCP, bridge, and local native CLI are described separately |
| High | Ordinary opening of all four editors was hidden behind the PCB/operator-evidence scenario | Roundtrip commands added for Schematic/PCB/Component/Pattern plus Windows, WSL, and Linux/macOS Wine backend discovery |
| High | `bridge --headless`, XML nativeization, SVG, and the real GUI could be conflated | Each now states its real result, side effects, and evidence limit |
| High | Native roundtrip preserves the input file; a read-only review could modify it | Reviews must use an isolated copy bound to the source SHA; an unknown dialog never authorizes mouse/keyboard interception |
| High | New skills lived outside the shipped set; the generator and release auditor capped it at eight | A single catalog of 15, updated allowlist, exact wheel-content verification without a numeric quota, internal portable links |
| Medium | Native library write is absent, but that could imply refusing to read the installed `.eli` | `query_builtin_library_catalog` is documented, exporting via the hidden CompEdit into the XML cache; this is not arbitrary library editing |
| Medium | Testpoint net assignment could look like a finished physical connection | Added a check for copper, short stub traces, or polygon attachment after native refill |
| Medium | Repeated common confirmations and rollback not limited to own changes | An already granted permission is preserved; the plan never authorizes commits; rollback is limited to own changes and the current SHA |
| Medium | The generator demanded arbitrary numeric counts instead of useful coverage | It now verifies real MCP names, native modules/CLI examples, links, the handoff template, package composition and hashes |

## Changes to the original skills

| Skill | Substantive clarification |
|---|---|
| `pcb-project-intake` | XML versus binary before parsing, explicit path without a live session, native checks on copies |
| `library-quality-audit` | Reading the installed catalog via the XML cache and native roundtrip of both library editors |
| `schematic-erc-review` | The hidden Schematic editor is available separately from MCP; a base roundtrip does not run native ERC |
| `testpoint-planner` | Physical testpoint connection, allowed-change area, protected rollback |
| `critical-net-router` | Plan/commit, hash guard, local router boundaries, native PCB verification |
| `signal-integrity-review` | Native refill as a geometry source, but not a replacement for a field solver or engineering validation |
| `release-gate` | Native acceptance and real CAM artifacts cannot be excluded merely because an MCP command is missing |
| `diptrace-evidence-capture` | Opening all four editors, native PCB acceptance and recording; the formal operator-candidate pipeline only for the matching task |

## Added full-cycle stages

The [catalog](../skills/README.md) now includes `pcb-design-workflow`,
`schematic-engineer`, `diptrace-datasheet-rules`, `diptrace-bom-sourcing`,
`diptrace-production-pack`, `diptrace-board-bringup`, and `diptrace-revision-review`.
This covers specifications, component evidence, schematic, PCB, sourcing, production,
first power-on, production test, and ECO. Having an instruction does not mean physical
measurement, native CAM, or order placement is automated.

`schematic-engineer` is adapted from the original OpenCode skill with the source SHA
preserved. Real MCP authoring commands and native/headless paths were added; the
schematic, PCB, and release boundaries are kept. The initial policy of consulting RAG
only when facts are missing was replaced by a later user clarification: RAG is the
default working engineering memory, not a conditional reference.

All 15 skills are marked `RAG-backed` in their descriptions, bodies, and `rag: true`
in the catalog. The [shared process](../skills/shared/rag.md) automatically builds and
carries context across stages from MIT/theory courses, schematic/PCB guides, DipTrace
courses, and project lessons. The model uses it to understand the task, compare
alternatives, find risks, implement, and verify without re-stating the experienced
engineer role. This is contextual application of knowledge, not training of model
weights. Real sources must be fetched through the connected Knowledge MCP; the corpus
content was not inspected or imported during this skill change.

Shared rules require official package/land-pattern/layout/revision evidence, the
13 `PCB_BUILD.md` gates, the two-layer strategy, and the default via-in-pad ban. The
verifiable template contains no pre-issued PASS results. It is stated that the
repository `pcb_quality_gate.py` is not part of the wheel and its exit 0 does not
close pending manual checks.

## What is actually implemented

| Interface | Confirmation in sources | Limit |
|---|---|---|
| MCP over the XML path | [server_runtime.py](../src/diptrace_mcp/server_runtime.py) | Parser/model/guarded edit, not GUI launching |
| `headless_gui roundtrip` | [headless_gui.py](../src/diptrace_mcp/headless_gui.py) | The real four editors, open/save/close; not generic XML export, ERC, or CAM |
| `pcb_native_acceptance run` | [pcb_native_acceptance.py](../src/diptrace_mcp/pcb_native_acceptance.py) | Refill/DRC/save/reopen/XML, profile version/locale and the exact verdict; not Gerber |
| Native MP4/GIF | [cinematic_recording.py](../src/diptrace_mcp/cinematic_recording.py), [helper dispatch](../scripts/headless_gui_entry.py) | Requires ffmpeg, a valid manifest, and a profile; replay can modify the copy and output files |
| Wine wrappers | [install_linux.sh](../scripts/install_linux.sh), [install_macos.sh](../scripts/install_macos.sh) | Linux automatically provides root/desktop and translates paths for roundtrip only; macOS translates only a separate `--project PATH` |
| Fabrication/assembly MCP | [exports.py](../src/diptrace_mcp/services/exports.py) | Generic CSV/placement/manifest; native Gerber/NC Drill requires a separate export |

Native `PASS`, `FAIL`, and `HUMAN_REVIEW_REQUIRED` are not interchangeable. A
successful roundtrip confirms only the executed scenario; SVG, smoke tests, and XML
adaptation are not native DRC. Missing automatic ERC/CAM blocks that specific
acceptance but does not cancel the available open/save or other independent stages.

## Verification

- Format check via `skill-creator/scripts/quick_validate.py`: all 15 skills are
  valid. The shared runtime and topic references are separated by purpose.
- `python scripts/generate_pcb_skills.py --check`: catalog, real MCP names, internal
  links, script mirrors, and the SHA manifest are consistent.
- `python -m pytest -q tests/test_skill_packages.py tests/test_release_artifacts.py`:
  **35 passed**. Verified real CLI parsers, the 13-line handoff template, OpenCode
  path registration, wheel build, exact bytes of all skill files, links after
  unpacking, and the release audit; native CLI modules are present in the wheel.
- `python -m pytest -q tests/test_headless_gui.py tests/test_pcb_native_acceptance.py tests/test_pcb_quality_gate.py`:
  **60 passed, 2 skipped**. The skips require real Win32 desktop objects.
- Ruff for the changed Python files and `git diff --check`: no errors.

The strict allowlist check compares it against the Git index. To verify new files not
yet added by the user, a temporary index and a separate Git object directory under
`/tmp` were used, with HEAD and the exact addition set. The working index and project
history were not modified. A normal `--check-allowlist` in the working tree would
require adding the new files to Git; the publication constraint was not weakened.

No real user CAD files were opened or saved during this review. These results confirm
the instructions, CLI contracts, and packaging — not a new native roundtrip on the
installed GUI and not the quality of a specific physical board.

### Re-verification after the RAG mode change

`python -m pytest -q tests/test_skill_packages.py`: **19 passed**, including RAG
marking consistency, rejection of invalid catalog values, and the wheel build with the
shared `shared/rag.md`. All 15 skills passed `quick_validate.py` again; the SHA
manifest and links were verified. These checks do not access the corpus: the Knowledge
MCP tools were not published in the current session, so a real course search was not
exercised. This is not a restriction on RAG usage built into the skills.
