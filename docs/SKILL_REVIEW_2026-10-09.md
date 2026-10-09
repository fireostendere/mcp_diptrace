# Engineering Skills Review — 2026-10-09

## Conclusion

The fifteen `skills/*/SKILL.md` files, the shared runtime and RAG guidance,
`catalog.json`, `capability-map.json`, the generator and the skill tests were
reviewed against `main` at `4437d8d` (PR #129). Tool names, numeric bounds, review
profiles, CLI parsers, links and wheel packaging were consistent with the code.
The defects were in native-capability coverage: three shipped native paths (the
native XML exporter, the per-build schematic acceptance profiles, and the
Windows-only native manufacturing export) were missing or described as
unavailable. That is the same "no MCP tool, so no capability" error class that the
[2026-09-10 review](SKILL_REVIEW_2026-09-10.md) corrected. All findings below were
fixed in this change; the recommendations at the end were not applied.

## Findings and fixes

| Priority | Problem | Fix |
|---|---|---|
| High | The skills and the capability map said that base roundtrip does not export XML and told the agent not to invent an export command, but never named the shipped `diptrace_mcp.native_xml_export` CLI (native `.dch`/`.dip` to XML from a private copy, documented in [NATIVE_XML_EXPORT.md](NATIVE_XML_EXPORT.md) and run in CI on 5.3.5.1). A binary project would have been treated as unreadable or handed to an operator. | Exporter named in [runtime access](../skills/shared/runtime.md), evidence capture, project intake, revision review and library audit; `local_cli.native_xml_export` entry and a precise `generic_native_xml_export` contract in capability map 2.3.0. |
| High | Production packaging routed Gerber, NC Drill and pick-and-place to "a supported native export workflow or operator export" without naming the Windows-only `native_cad` round-trip that CI exercises through `scripts/validate_native_platform.py` (`native-fabrication.zip`, `native-placement.csv`); `native_fabrication_export` read as a blanket unavailability. | Production pack and runtime access describe `diptrace_mcp.native_cad.run_native_cad` with `export_manufacturing=True`: verified build, isolated copy, metric/design-origin/no-mirror settings, outputs, and its limits (Python API only; the output is not inspected CAM). Contract text refined. |
| Medium | The schematic acceptance helper was described as a single "Schematic 5.3.0.3 profile" and was absent from `local_cli`; PR #129 added a reviewed 5.3.5.1 profile and CI coverage. No skill stated which DipTrace builds are verified. | Per-build profiles (5.3.0.3, 5.3.5.1) stated in evidence capture, runtime access and `host_backends.windows`; `local_cli.schematic_native_acceptance` entry with example arguments; PCB acceptance refill-by-menu-group and hidden-desktop startup-message handling described. |
| Medium | Nine of fifteen descriptions carried no Russian trigger phrases, unlike the six lifecycle skills and the user's other skills; Russian requests matched only through the English trigger sentence. | "Use for ...; «...»" phrases added to all nine. The English catalog trigger sentences are unchanged, so `catalog.json` and the tests still bind. |
| Low | Host registration text omitted `.agents/skills.json` and did not say that Claude Code (Skill tool, `/skill-doctor`) never loads a repository-root `skills/` directory. | Stated in the catalog README together with the `claude plugin validate` command. |
| Low | The `--startup-dialog-sha256` wording bound the schematic helper to one image; a pending change makes the option repeatable. | Neutral wording: an explicitly reviewed exact image. |

## Verified without change

- All 152 registered MCP tools resolve. Every backticked tool-like name in the
  catalog is a registered tool or an explicit CLI word, and every `capabilities`
  list in `catalog.json` is a subset of the registry.
- Routing bounds (20 connections per local plan, `max_vias` 0, detour 3.0,
  100 000 nodes, four rip-up attempts), write limits (100 operations, 500
  conservatively counted objects), paging (1 through 500, default 100), testpoint
  defaults (1.0 mm, 0.5 mm, 2.54 mm, 1 through 100 candidates, 5 000 grid points),
  impedance validity ranges and the thirteen `run_review` profiles match
  `src/diptrace_mcp` on `main`.
- Capture-script bounds (128 MiB, 32 private inputs, DTD/entity refusal), headless
  timeouts (30 s default, 300 s maximum), the Linux/macOS wrapper behaviour and the
  frozen-helper dispatch (`pcb-acceptance`, `cinematic`) match the scripts.
- The six pinned GitHub source links point at commit `20e4bc1` (2026-07-29); the
  commit exists and every number cited from it still matches `main`.
- `docs/REVIEW_ENGINE.md`, `scripts/pcb_quality_gate.py` (CP2102 thermal-via
  exception) and `scripts/build_generic_board.py` (DUT Rev.A scripts) are as described.

## Recommendations not applied

- Claude Code registration is a product decision: `.claude/skills/<name>` copies
  would break the single-source rule, symlinks are fragile on drvfs/Windows
  checkouts, and a `.claude-plugin/plugin.json` would turn the checkout into a
  plugin whose `skills/` directory loads through `claude --plugin-dir`. Choose one
  and add the files to the release allowlist.
- [NATIVE_XML_EXPORT.md](NATIVE_XML_EXPORT.md) still says that native checks cover
  5.3.0.3; CI now also covers 5.3.5.1.
- The legacy `.agents/skills/*` recipes were not modified; `AGENTS.md` already
  prefers the catalog.
- Re-pin the six source links when a cited bound changes.

## Verification

- `python scripts/generate_pcb_skills.py --check`: OK, 15 skills, shared schema,
  links, capabilities, mirrors and hashes.
- `claude plugin validate skills --strict`: validation passed.
- `python -m pytest -q tests/test_skills_integrity.py tests/test_skill_packages.py`:
  **21 passed** (RAG markers, catalog/tool contracts, real CLI parsers, handoff
  template, wheel build with exact skill bytes and installed links).
- `python -m pytest -q tests/test_skills_integrity.py tests/test_skill_packages.py tests/test_release_artifacts.py tests/test_documentation_links.py`:
  **46 passed** (adds the allowlist-versus-tracked-files check, sdist/wheel audits
  and documentation link targets).
- `python scripts/sync_skill_scripts.py --check` and
  `python scripts/audit_release_artifacts.py --check-allowlist`: OK.
- `git diff --check`: no whitespace errors.

No DipTrace editor was launched. These results confirm the instructions, CLI
contracts and packaging, not a new native round-trip on an installed GUI.
