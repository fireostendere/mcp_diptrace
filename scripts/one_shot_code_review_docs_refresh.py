#!/usr/bin/env python3
"""One-shot repository review/documentation refresh for 2026-07-31.

This helper is executed once by a branch-scoped GitHub Actions workflow. It
updates maintained documentation, adds review/acceptance records, strengthens
cross-platform path regression tests, removes itself and the temporary workflow,
and regenerates the release allowlist before the final commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).relative_to(ROOT)
WORKFLOW = Path(".github/workflows/one-shot-code-review-docs-refresh.yml")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement anchor, found {count}")
    write(path, content.replace(old, new, 1))


def append_once(path: str, marker: str, addition: str) -> None:
    content = read(path)
    if marker in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    write(path, content + addition)


# README: clarify current readiness and record both real-DipTrace campaigns.
replace_once(
    "README.md",
    "It is not yet a full replacement for DipTrace's interactive EDA engine. The main remaining gap is no longer MCP tool count; it is broad, automated, redistributable evidence that all important write paths survive real DipTrace 5.3 open/save/re-export cycles with the intended semantics.\n",
    "It is not yet a full replacement for DipTrace's interactive EDA engine. PCB and schematic live finalization now have controlled Windows/WSL apply, cancel, wrong-SHA, GUI, save, and re-export evidence for the tested paths. The main remaining gap is broader, redistributable evidence for the many other writers, source variants, native libraries, and optional external-tool paths.\n",
)

old_validation = """Synthetic 4.3 fixtures cover PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES, and server contracts. A separate live DipTrace 5.3.0.2 schematic acceptance test verified:\n\n- source-SHA conflict protection, backup equality, and atomic write;\n- 41 scoped `RefDesMarking` edits on the Power sheet;\n- bridge apply followed by an independent DipTrace re-export;\n- persistence of all 41 coordinates and unchanged normalized sheet/part/pin/net/bus/differential-pair counts;\n- no new offline ERC errors after the round trip.\n\nThis is strong evidence for the tested paths, not a claim of complete compatibility with every DipTrace version or XML object.\n"""
new_validation = """Synthetic 4.3 fixtures cover PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES, and server contracts. Two controlled live acceptance campaigns provide separate host evidence:\n\n- DipTrace 5.3.0.2 schematic: source-SHA conflict protection, backup equality, atomic write, 41 scoped `RefDesMarking` edits, bridge apply, independent re-export, stable normalized counts, and no new offline ERC errors;\n- DipTrace 5.2.0.4 on Windows with the MCP server in WSL: PCB apply/cancel/wrong-SHA and Schematic apply/cancel/wrong-SHA, Windows-native exchange-path metadata, no phantom `C:\\mnt\\c\\...` target, GUI confirmation where applicable, Save As/re-export, semantic comparison, and unchanged connectivity/counts.\n\nThe 2026-07-31 campaign reported `ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for that tested matrix. This is strong evidence for the tested paths, not a claim of complete compatibility with every DipTrace version, XML object, MCP tool, or optional adapter. See [the acceptance record](docs/LIVE_ACCEPTANCE_2026-07-31.md) and [code review](docs/CODE_REVIEW_2026-07-31.md).\n"""
replace_once("README.md", old_validation, new_validation)

replace_once(
    "README.md",
    "DipTrace starts the plug-in as a separate executable and passes a temporary XML path. The bridge stores a working copy under `%LOCALAPPDATA%\\DipTraceMCP`, waits for an MCP `apply` or `cancel` request, verifies the caller-observed working SHA-256, revalidates that the original exchange file is unchanged and still inside an allowed root, and exits only after the session is finalized. DipTrace then imports the exchange XML on `apply`.\n",
    "DipTrace starts the plug-in as a separate executable and passes a temporary XML path. The bridge stores a working copy under `%LOCALAPPDATA%\\DipTraceMCP`, waits for an MCP `apply` or `cancel` request, verifies the caller-observed working SHA-256, revalidates that the original exchange file is unchanged and still inside an allowed root, and exits only after the session is finalized. DipTrace then imports the exchange XML on `apply`. The metadata keeps the exchange path in the bridge's native syntax; a WSL server derives `/mnt/<drive>/...` only in memory and never persists it back.\n",
)

replace_once(
    "README.md",
    "- [Development](docs/DEVELOPMENT.md)\n- [Russian README](README_RU.md)",
    "- [Development](docs/DEVELOPMENT.md)\n- [Windows/WSL live exchange paths](docs/LIVE_EXCHANGE_PATHS.md)\n- [2026-07-31 live acceptance](docs/LIVE_ACCEPTANCE_2026-07-31.md)\n- [2026-07-31 code review](docs/CODE_REVIEW_2026-07-31.md)\n- [Russian README](README_RU.md)",
)

# Russian README: keep claims aligned with the English source.
replace_once(
    "README_RU.md",
    "Это пока не полная замена интерактивному EDA-движку DipTrace. Наиболее важный незакрытый слой — не количество MCP tools, а доказанная совместимость write-paths с реальным DipTrace 5.3 через контролируемые open/save/re-export fixtures. Создание/изменение native Component/Pattern Libraries и native manufacturing outputs пока намеренно не заявлены как готовые возможности.\n",
    "Это пока не полная замена интерактивному EDA-движку DipTrace. Для проверенных PCB/schematic live-путей уже есть контролируемые Windows/WSL apply, cancel, wrong-SHA, GUI, save и re-export доказательства. Главный незакрытый слой теперь — более широкие redistributable evidence для остальных writers, вариантов исходных файлов, native libraries и optional external-tool путей. Создание/изменение native Component/Pattern Libraries и native manufacturing outputs по-прежнему намеренно не заявлены как готовые возможности.\n",
)

old_ru_validation = """Synthetic 4.3 fixtures покрывают PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES и MCP contracts. Отдельный live acceptance test с DipTrace 5.3.0.2 подтвердил:\n\n- защиту от source-SHA conflict, равенство backup и atomic write;\n- 41 scoped `RefDesMarking`-правку на листе Power;\n- bridge apply и независимый повторный export из DipTrace;\n- сохранение всех 41 координат и неизменность нормализованных количеств sheet/part/pin/net/bus/differential-pair;\n- отсутствие новых offline ERC errors после round trip.\n\nЭто сильное доказательство для проверенных путей, но не обещание полной совместимости со всеми версиями DipTrace и всеми XML objects.\n"""
new_ru_validation = """Synthetic 4.3 fixtures покрывают PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES и MCP contracts. Отдельно проведены две контролируемые live acceptance-кампании:\n\n- DipTrace 5.3.0.2, schematic: source-SHA conflict protection, backup equality, atomic write, 41 scoped `RefDesMarking`-правка, bridge apply, независимый re-export, стабильные normalized counts и отсутствие новых offline ERC errors;\n- DipTrace 5.2.0.4 на Windows с MCP-сервером в WSL: PCB apply/cancel/wrong-SHA и Schematic apply/cancel/wrong-SHA, Windows-native exchange-path metadata, отсутствие фантомного `C:\\mnt\\c\\...`, GUI-подтверждение для применяемых изменений, Save As/re-export, semantic comparison и неизменная connectivity/counts.\n\nКампания 2026-07-31 завершилась как `ACCEPTANCE: PASS`, `RELEASE BLOCKER: NO` для этой матрицы. Это сильное доказательство для проверенных путей, но не обещание полной совместимости со всеми версиями DipTrace, всеми XML objects, всеми MCP tools и optional adapters. См. [отчёт acceptance](docs/LIVE_ACCEPTANCE_2026-07-31.md) и [code review](docs/CODE_REVIEW_2026-07-31.md).\n"""
replace_once("README_RU.md", old_ru_validation, new_ru_validation)

replace_once(
    "README_RU.md",
    "DipTrace запускает плагин отдельным `.exe` и передаёт путь к временному XML. Bridge хранит рабочую копию в `%LOCALAPPDATA%\\DipTraceMCP`, ждёт MCP `apply` или `cancel`, проверяет SHA-256 рабочей копии, который видел caller, заново убеждается, что исходный exchange-файл не изменился и всё ещё находится внутри allowed root, и завершает процесс только после финализации сессии. После `apply` DipTrace импортирует exchange XML обратно.\n",
    "DipTrace запускает плагин отдельным `.exe` и передаёт путь к временному XML. Bridge хранит рабочую копию в `%LOCALAPPDATA%\\DipTraceMCP`, ждёт MCP `apply` или `cancel`, проверяет SHA-256 рабочей копии, который видел caller, заново убеждается, что исходный exchange-файл не изменился и всё ещё находится внутри allowed root, и завершает процесс только после финализации сессии. После `apply` DipTrace импортирует exchange XML обратно. В metadata путь хранится в native-синтаксисе процесса bridge; WSL-сервер вычисляет `/mnt/<drive>/...` только в памяти и никогда не записывает этот derived path обратно.\n",
)

# Add review/acceptance links before the final English link if present.
ru_content = read("README_RU.md")
ru_marker = "- [English README](README.md)"
if ru_marker in ru_content and "LIVE_ACCEPTANCE_2026-07-31.md" not in ru_content.split("## Документация")[-1]:
    ru_content = ru_content.replace(
        ru_marker,
        "- [Windows/WSL live exchange paths](docs/LIVE_EXCHANGE_PATHS.md)\n- [Live acceptance 2026-07-31](docs/LIVE_ACCEPTANCE_2026-07-31.md)\n- [Code review 2026-07-31](docs/CODE_REVIEW_2026-07-31.md)\n" + ru_marker,
        1,
    )
    write("README_RU.md", ru_content)

# Changelog: record post-0.1.0 fixes and validation without prematurely assigning 0.1.1.
replace_once(
    "CHANGELOG.md",
    "## Unreleased\n\n## 0.1.0 - 2026-07-30",
    """## Unreleased\n\n### Fixed\n\n- Preserve Windows-native live exchange paths in session metadata and derive WSL\n  drive-mount paths only in memory, preventing false `applied` results against a\n  phantom `C:\\mnt\\c\\...` target.\n- Ignore the intentional stdout-close race used to unblock a Windows output-reader\n  thread after the root process exits while a descendant inherited the pipe.\n\n### Validation\n\n- Completed Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance for PCB and\n  Schematic apply/cancel/wrong-SHA paths, including GUI checks, independent\n  save/re-export comparisons, path invariants, and connectivity/count preservation.\n- Added focused unit coverage for non-WSL Windows-path refusal, relative WSL mount\n  roots, POSIX-path refusal on Windows, and invalid path-platform metadata.\n\n### Documentation\n\n- Reconciled English and Russian readiness, testing, architecture, compatibility,\n  usage, roadmap, and release-policy documentation with the 2026-07-31 evidence.\n- Added a dated code-review record and live-acceptance record.\n\n## 0.1.0 - 2026-07-30""",
)

# Roadmap: update the dated readiness checkpoint and keep evidence boundaries explicit.
replace_once("docs/ROADMAP.md", "## Current Readiness — 2026-07-25", "## Current Readiness — 2026-07-31")
replace_once(
    "docs/ROADMAP.md",
    "The main remaining risk is no longer missing MCP surface area. It is the gap between synthetic/fixture-tested writer behavior and broad, redistributable, automated evidence from real DipTrace 5.3 open/save/re-export cycles.\n\n### WO-11 input and write-safety checkpoint — 2026-07-25",
    """The main remaining risk is no longer missing MCP surface area or the tested PCB/Schematic live-finalization path. It is the gap between synthetic/fixture-tested behavior and broad, redistributable, automated evidence for the remaining writers, source variants, native libraries, and optional external adapters.\n\n### Windows/WSL live bridge acceptance checkpoint — 2026-07-31\n\nThe cross-platform exchange-path defect `DT-LIVE-001` is closed for the tested topology.\nThe Windows bridge now persists a Windows-native exchange path plus\n`exchange_path_platform=\"windows\"`; a WSL MCP process derives its `/mnt/<drive>/...`\nview in memory only. Path-style mismatches fail before `control.json` publication.\n\nControlled DipTrace 5.2.0.4 acceptance verified PCB apply, cancel, and wrong-SHA\nbehavior and Schematic apply, cancel, and wrong-SHA behavior. Applied changes were\nconfirmed in the GUI and through independent Save As/re-export semantic comparison;\ncancelled and wrong-SHA changes did not reach the host document. No phantom\n`C:\\mnt\\c\\...` target appeared, Windows-native metadata remained unchanged, and\nconnectivity/count checks remained stable. The local campaign result was\n`ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for that matrix.\n\nThis closes the specific live path/finalization defect, not the separate all-write-path\ntrust-invalidation gap, the need for redistributable DipTrace fixtures, native library\nwriter evidence, or real external-solver evidence.\n\n### WO-11 input and write-safety checkpoint — 2026-07-25""",
)

# Testing: distinguish CI, two host campaigns, and the remaining non-automated boundary.
replace_once(
    "docs/TESTING.md",
    "The test strategy intentionally separates implementation correctness from real-DipTrace compatibility evidence. A green unit/CI matrix proves the maintained contracts and fixtures; it does not automatically promote every writer to DipTrace 5.3 round-trip verified status.\n",
    "The test strategy intentionally separates implementation correctness from real-DipTrace compatibility evidence. A green unit/CI matrix proves the maintained contracts and fixtures; it does not automatically promote every writer to real-DipTrace round-trip verified status.\n",
)
old_acceptance = """## Real DipTrace Acceptance Already Completed\n\nA live acceptance test with DipTrace 5.3.0.2 separately verified:\n\n- source-SHA conflict protection;\n- backup equality;\n- atomic write behavior;\n- 41 bounded schematic `RefDesMarking` edits on the Power sheet;\n- bridge apply followed by an independent DipTrace re-export;\n- persistence of all 41 coordinates;\n- unchanged normalized sheet/part/pin/net/bus/differential-pair counts;\n- no new offline ERC errors after the round trip.\n\nThe rebuilt Windows bridge also passes isolated cross-process finish-request tests covering metadata/control publication, cleanup, and exchange-file integrity.\n\nThis acceptance evidence is valuable but intentionally scoped. The user project used for the live test is not redistributed, so the same path is not yet automated in public CI.\n"""
new_acceptance = """## Real DipTrace Acceptance Already Completed\n\n### DipTrace 5.3.0.2 schematic campaign\n\nA live schematic acceptance test separately verified source-SHA conflict protection,\nbackup equality, atomic write behavior, 41 bounded `RefDesMarking` edits on the Power\nsheet, bridge apply followed by an independent DipTrace re-export, persistence of all\n41 coordinates, unchanged normalized sheet/part/pin/net/bus/differential-pair counts,\nand no new offline ERC errors after the round trip.\n\n### DipTrace 5.2.0.4 Windows bridge with WSL MCP — 2026-07-31\n\nA second campaign verified:\n\n- PCB apply with GUI confirmation, Save As, independent XML re-export, semantic\n  comparison, and unchanged 65-net/77-component connectivity counts in the tested board;\n- PCB cancel after a committed working-copy edit, with the exchange XML, GUI, and\n  re-export remaining at baseline;\n- PCB wrong-SHA refusal without exchange or GUI mutation;\n- Schematic apply with the intended value change confirmed in the GUI;\n- Schematic cancel and wrong-SHA refusal with the original exchange SHA preserved;\n- Windows-native `exchange_path` plus `exchange_path_platform=\"windows\"` in every\n  session, with WSL translation performed only in memory;\n- no phantom `C:\\mnt\\c\\...` target; and\n- clean bridge build/install hash checks across PCB, Schematic, Component, and Pattern\n  plug-in destinations.\n\nThe campaign's final result was `ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for the\ntested matrix. The detailed evidence boundary is recorded in\n[LIVE_ACCEPTANCE_2026-07-31.md](LIVE_ACCEPTANCE_2026-07-31.md).\n\nThe rebuilt Windows bridge also passes isolated cross-process finish-request tests\ncovering metadata/control publication, cleanup, and exchange-file integrity. The real\nprojects and full operator artifact directory are not redistributed, so these host\nchecks remain local acceptance evidence rather than public-CI fixtures or package-owned\nhigh-trust registry entries.\n"""
replace_once("docs/TESTING.md", old_acceptance, new_acceptance)

# Compatibility: add the 5.2 live matrix without weakening 5.3 evidence gaps.
replace_once(
    "docs/XML_COMPATIBILITY.md",
    "A live import/re-export acceptance run with DipTrace 5.3 has confirmed real Schematic XML using `Version=\"5.3.0.2\"`. Component and Pattern Library exports have also been observed from DipTrace 5.3, while some public specification examples remain 4.3-era. Application version and XML `Version` are therefore treated as related but non-equivalent evidence.\n",
    "A live import/re-export acceptance run with DipTrace 5.3 has confirmed real Schematic XML using `Version=\"5.3.0.2\"`. A separate DipTrace 5.2.0.4 Windows/WSL campaign confirmed the tested PCB and Schematic live apply/cancel/wrong-SHA paths, including independent re-export for applied changes and no host mutation for cancelled/refused changes. Component and Pattern Library exports have also been observed from DipTrace 5.3, while some public specification examples remain 4.3-era. Application version and XML `Version` are therefore treated as related but non-equivalent evidence.\n",
)
replace_once(
    "docs/XML_COMPATIBILITY.md",
    "| PCB XML 5.3.0.2 installed examples | yes | not broadly mutation-verified | complex multilayer examples parsed locally; redistributable round-trip fixtures still needed |\n",
    "| PCB XML 5.2.0.4 live project | yes | scoped component move + guarded live finalization | real apply/GUI/save/re-export verified; cancel and wrong-SHA preserved baseline; not broad writer coverage |\n| PCB XML 5.3.0.2 installed examples | yes | not broadly mutation-verified | complex multilayer examples parsed locally; redistributable round-trip fixtures still needed |\n",
)
replace_once(
    "docs/XML_COMPATIBILITY.md",
    "| Schematic XML 5.3.0.2 live project | yes | bounded raw/semantic writes | real bridge apply + independent DipTrace re-export verified for scoped marking edits |\n",
    "| Schematic XML 5.2.0.4 live project | yes | scoped value edit + guarded live finalization | real apply/GUI verified; cancel and wrong-SHA preserved baseline |\n| Schematic XML 5.3.0.2 live project | yes | bounded raw/semantic writes | real bridge apply + independent DipTrace re-export verified for scoped marking edits |\n",
)
replace_once(
    "docs/XML_COMPATIBILITY.md",
    "- representative PCB semantic writes on DipTrace 5.3;\n",
    "- broader representative PCB semantic writes, especially on DipTrace 5.3; one scoped 5.2.0.4 component move is verified;\n",
)
append_once(
    "docs/XML_COMPATIBILITY.md",
    "## Additional 5.2 live baseline",
    """\n## Additional 5.2 live baseline\n\nThe 2026-07-31 Windows/WSL campaign used DipTrace 5.2.0.4 and verified the\nbridge-native path invariant, PCB and Schematic finalization outcomes, GUI behavior,\nand independent save/re-export semantics for the tested changes. It supplements, but\ndoes not replace, the 5.3 fixture and writer-verification priorities above.\n""",
)

# Usage: document the immutable native-path rule and the operator evidence boundary.
replace_once(
    "docs/USAGE.md",
    "This guide and the live acceptance path were reviewed against an installed DipTrace 5.3\nbuild exporting XML `Version=\"5.3.0.2\"`. The integration remains feature- and\nfixture-gated because the public XML specification PDFs used by the project still\ncontain 4.3-era examples.\n",
    "This guide and the live acceptance path were reviewed against an installed DipTrace 5.3 build exporting XML `Version=\"5.3.0.2\"`. A second acceptance campaign used DipTrace 5.2.0.4 with the Windows bridge and a WSL MCP server to verify the tested PCB/Schematic apply, cancel, and wrong-SHA paths. The integration remains feature- and fixture-gated because the public XML specification PDFs used by the project still contain 4.3-era examples and the real operator projects are not redistributed.\n",
)
replace_once(
    "docs/USAGE.md",
    "When the workspace is under `/mnt/<drive>/Users/<user>/...`, the server can usually\nderive the Windows state directory automatically. Setting it explicitly removes\nambiguity.\n\nCreate the WSL virtual environment with Linux Python. Do not reuse a Windows virtual\nenvironment from WSL.\n",
    "When the workspace is under `/mnt/<drive>/Users/<user>/...`, the server can usually derive the Windows state directory automatically. Setting it explicitly removes ambiguity.\n\nThe bridge records its exchange file in Windows-native form, for example `C:\\Users\\...\\plugin_exchange.xml`, together with `exchange_path_platform=\"windows\"`. The WSL server derives `/mnt/<drive>/...` only for its local read/validation operations and must never rewrite metadata to the WSL path. A path/platform mismatch is a fail-closed session error; do not repair it manually. Close the old session, update both server and bridge, and start a fresh session. See [LIVE_EXCHANGE_PATHS.md](LIVE_EXCHANGE_PATHS.md).\n\nCreate the WSL virtual environment with Linux Python. Do not reuse a Windows virtual environment from WSL.\n",
)

# Architecture: make the native-path invariant part of the protocol and safety list.
replace_once(
    "docs/ARCHITECTURE.md",
    "A separate state directory is necessary because `plugin_exchange.xml` is temporary and\nowned by DipTrace.\n",
    "A separate state directory is necessary because `plugin_exchange.xml` is temporary and owned by DipTrace. Session metadata stores that exchange path in the native syntax of the bridge process plus an immutable platform field. A WSL server derives its drive-mount view in memory only; persisting `/mnt/c/...` into Windows-origin metadata is invalid and is rejected before a finish control marker can be published.\n",
)
replace_once(
    "docs/ARCHITECTURE.md",
    "12. A finish request publishes `control.json` only after `metadata.json` is complete.\n",
    "12. A finish request publishes `control.json` only after `metadata.json` is complete.\n13. The exchange path remains in bridge-native syntax. Cross-platform runtime translation is in-memory only, and path/platform disagreement fails closed.\n",
)
replace_once(
    "docs/ARCHITECTURE.md",
    "Apply remains separately bound to the original\nexchange path/hash, current working hash, and two independent write-impact checks.\n",
    "Apply remains separately bound to the original exchange path/hash, current working hash, and two independent write-impact checks. The 2026-07-31 DipTrace 5.2.0.4 Windows/WSL campaign verified this path for PCB and Schematic apply/cancel/wrong-SHA outcomes, with no phantom `C:\\mnt\\c\\...` target.\n",
)

# Live-path document: append the actual acceptance record and operator rule.
append_once(
    "docs/LIVE_EXCHANGE_PATHS.md",
    "## Acceptance evidence — 2026-07-31",
    """\n## Acceptance evidence — 2026-07-31\n\nA controlled DipTrace 5.2.0.4 Windows bridge ↔ WSL MCP campaign verified:\n\n- PCB apply reached the real Windows exchange file, appeared in the GUI, survived\n  Save As and independent XML re-export, and preserved connectivity/counts;\n- PCB cancel and wrong-SHA left the exchange file and host document unchanged;\n- Schematic apply reached the GUI, while cancel and wrong-SHA preserved baseline;\n- all sessions kept `exchange_path_platform=\"windows\"` and a `C:\\...` path; and\n- no `C:\\mnt\\c\\...` target was created.\n\nThe campaign result was `ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for that\nexplicit matrix. This local host evidence does not convert every writer or every\nDipTrace version into round-trip-verified support.\n\nNever repair a legacy or malformed active session by editing `metadata.json`. Close\nthe bridge, update the server and executable, and start a fresh session.\n""",
)

# Release policy: reconcile the existing development release with the documented blockers.
replace_once(
    "docs/RELEASE_PROCESS.md",
    "Publishing is prohibited while any blocking item in\n[PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) remains open. The\nGitHub repository owner is the only currently documented administrative\nauthority.\n",
    "A release presented as independently reviewed, signed, or production-ready is prohibited while the corresponding blocking items in [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) remain open. A development-stage unsigned release may proceed only through an explicit solo-maintainer exception recorded with its limitations, artifact hashes, test evidence, and rollback decision. The GitHub repository owner is the only currently documented administrative authority.\n",
)
replace_once(
    "docs/RELEASE_PROCESS.md",
    "All required GitHub Actions jobs must pass on the same commit. A missing\nplatform result cannot be replaced by a local claim.\n",
    "All required GitHub Actions jobs must pass on the same commit. A missing platform result cannot be replaced by a local claim. When release notes claim live PCB or Schematic integration, attach a dated acceptance record for the exact server/bridge baseline and clearly separate local host evidence from public CI.\n",
)
replace_once(
    "docs/RELEASE_PROCESS.md",
    "Install the staged wheel and bridge rather than the source tree. Run CLI,\npublic MCP `tools/list`, skill-delivery, and headless bridge smoke tests on\nsupported platforms. Download the staged artifacts and verify their hashes.\n",
    "Install the staged wheel and bridge rather than the source tree. Run CLI, public MCP `tools/list`, skill-delivery, and headless bridge smoke tests on supported platforms. For a release that claims Windows live integration, run fresh-session PCB and Schematic apply/cancel/wrong-SHA acceptance, verify GUI/save/re-export behavior for applied changes, and prove cancelled/refused changes do not reach the host document. Download the staged artifacts and verify their hashes.\n",
)

replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "Audited repository state: 2026-07-30.\n\n**Status: blocked.** The repository has an OSI-approved project-wide license\n(Apache-2.0, committed as `LICENSE`), private vulnerability reporting\npublished as `SECURITY.md`, and a published 0.1.0 development-stage release\nwith an unsigned-binary disclosure, but no verified conduct channel, approved\ncontribution terms, signed release artifact, or independent release reviewer.\n",
    "Audited repository state: 2026-07-31.\n\n**Status: development release only under explicit exception.** The repository has an OSI-approved project-wide license (Apache-2.0, committed as `LICENSE`), private vulnerability reporting published as `SECURITY.md`, a published 0.1.0 development-stage release with an unsigned-binary disclosure, and a completed 2026-07-31 live acceptance matrix. It still has no verified conduct channel, approved contribution terms, signed release artifact, or independent release reviewer, so it must not be represented as independently reviewed, signed, or production-ready.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "Until these items are complete, do not call the repository open source and do\nnot publish a package or binary release.\n",
    "Until the remaining redistribution and review items are complete, do not claim every bundled asset has independent clearance and do not publish a release as independently reviewed, signed, or production-ready. Development-stage publication requires the explicit exception and disclosures described in [RELEASE_PROCESS.md](RELEASE_PROCESS.md).\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] The changelog does not present development version `0.1.0` as released.\n",
    "- [x] The changelog and release provenance consistently record `0.1.0` as the first tagged development-stage release.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [ ] Windows plug-in settings, installer, and bridge-binary delivery are\n      documented and tested separately from the Python wheel.\n",
    "- [x] Windows plug-in settings, installer, and bridge-binary delivery are documented separately from the Python wheel; clean build, four-target install hash checks, and live PCB/Schematic acceptance were completed on 2026-07-31.\n",
)
replace_once(
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "- [x] Acceptance seed audit fails closed and reports zero accepted seeds.\n",
    "- [x] Acceptance seed audit fails closed and reports zero accepted seeds.\n- [x] Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance covers the tested PCB/Schematic apply, cancel, and wrong-SHA matrix, with GUI/save/re-export checks and no phantom path.\n",
)

# Add a concise, source-grounded code-review record.
code_review = """# Code Review — 2026-07-31\n\n## Scope\n\nReview baseline: `main` at `29f9721d8f3efbc32e6c33f891bf1c27365b3ca0`.\n\nThe review focused on the release-critical paths changed after 0.1.0:\n\n- `src/diptrace_mcp/sessions.py`: session identity, Windows/WSL path translation,\n  allowed-root binding, stable-file reads, finish-request publication, and finalization;\n- `src/diptrace_mcp/external_process.py`: bounded output draining, Windows Job\n  Object cleanup, reader shutdown, and slot release;\n- bridge build/install PowerShell scripts and their CI smoke path;\n- cross-platform path, live lifecycle, external-process, public MCP contract,\n  release-artifact, and documentation tests; and\n- README, roadmap, testing, compatibility, usage, architecture, changelog, and\n  release-policy consistency.\n\n## Findings\n\n### Release-blocking findings\n\nNone found in the reviewed baseline. The full repository CI and the controlled host\nacceptance matrix remain the release gates; this review is not a substitute for them.\n\n### Closed defect: Windows/WSL exchange path binding\n\nThe previous false-positive apply path was caused by persisting `/mnt/c/...` into\nmetadata later consumed by the Windows bridge as `C:\\mnt\\c\\...`. The current code\nstores the creator-native path and immutable platform, derives WSL drive mounts only\nin memory, requires an absolute drive-letter path for Windows origin, rejects path-style\nmismatches before control publication, re-reads the original and exchange files through\nallowed-root/stable-file checks, and verifies the replacement SHA. Unit tests and the\nreal DipTrace campaign cover the failure mode.\n\n### Closed defect: inherited stdout on Windows\n\nThe external-process runner correctly places a suspended root into a kill-on-close Job\nObject before resuming it. When a descendant inherits stdout after the root exits, the\nrunner force-closes its local pipe only as a last-resort reader unblock. The reviewed\nchange avoids turning that intentional close into a false output-read failure while\nretaining real read errors when the stream is not closed. The native Windows regression\ntest covers root exit, inherited output, descendant termination, log contents, and slot\nrecovery.\n\n### Documentation drift\n\nThe code and host evidence were newer than the public documentation. Several pages\nstill described only the DipTrace 5.3.0.2 schematic campaign, did not record the\nWindows/WSL native-path invariant, and contained conflicting wording about the already\npublished Apache-2.0 development release. This change reconciles those claims without\nconverting local evidence into public-CI or high-trust registry evidence.\n\n### Regression coverage added\n\nFocused tests now explicitly cover:\n\n- refusal of a Windows-origin path on ordinary non-WSL Linux;\n- refusal of a relative `DIPTRACE_MCP_WSL_MOUNT_ROOT`;\n- refusal of POSIX-origin session metadata on Windows; and\n- refusal of an unknown exchange-path platform.\n\n## Residual risks and non-claims\n\n- Real DipTrace GUI acceptance is operator-assisted and not run in public CI.\n- The package-owned trusted provenance registry still contains zero reviewed entries.\n- The public transport workflow exercises 63 distinct tools, not every registered tool.\n- Total measured coverage is above the enforced 85% floor but below the stated 88%\n  project target.\n- Native Component/Pattern Library mutation, broad 5.3 PCB writer coverage, real\n  DSN/SES pairs, and real openEMS/Freerouting matrices remain evidence-gated.\n- All-write-path trust invalidation is still explicitly incomplete for the paths listed\n  by `get_capabilities` and `docs/TESTING.md`.\n\n## Verdict\n\nNo release blocker was identified for the tested 0.1.1 candidate scope. Release notes\nmust remain scoped to the implemented contracts and the exact acceptance matrix.\n\n## Краткое резюме на русском\n\nКритических, высоких или средних release-blocking дефектов в проверенном baseline не\nобнаружено. Подтверждены корректность native Windows exchange path, in-memory WSL\ntranslation, fail-closed wrong-SHA/path mismatch, безопасное завершение Windows process\ntree и соответствующие regression tests. Обновлена документация, но ограничения по\nredistributable fixtures, native library writers, external solvers, trust invalidation\nи неполному охвату всех 159 tools остаются явными.\n"""
write("docs/CODE_REVIEW_2026-07-31.md", code_review)

acceptance = """# Live Acceptance Record — 2026-07-31\n\n## Status\n\n- Result: **PASS**\n- Release blocker for the tested matrix: **NO**\n- Repository baseline reviewed for release: `main` after the Windows/WSL path fix and\n  Windows stdout cleanup fix\n- Host: Windows DipTrace 5.2.0.4\n- MCP runtime: WSL\n\n## Matrix\n\n| Test | Result | Evidence boundary |\n| --- | --- | --- |\n| Repository tests | PASS | Local campaign reported 987 passed, 4 skipped; GitHub CI remains authoritative per commit |\n| Ruff and strict Mypy | PASS | Zero reported issues |\n| Clean Windows bridge build | PASS | Executable built, non-empty, and `--help` smoke-run |\n| Four-target bridge install | PASS | PCB, Schematic, Component, and Pattern destinations matched the build hash |\n| Offline smoke | PASS | Read, dry-run, commit, and wrong-SHA guard |\n| PCB apply | PASS | Real exchange updated, GUI change observed, Save As and independent re-export matched semantically |\n| PCB cancel | PASS | Committed working edit did not reach exchange, GUI, or re-export |\n| PCB wrong SHA | PASS | Refused without host mutation |\n| Schematic apply | PASS | Intended value change observed in GUI |\n| Schematic cancel | PASS | Cancelled with original exchange SHA preserved |\n| Schematic wrong SHA | PASS | Refused with exchange SHA unchanged |\n| Phantom path | PASS | No `C:\\mnt\\c\\...` target |\n| Metadata integrity | PASS | Windows-native path and `exchange_path_platform=\"windows\"` throughout |\n\n## Proven PCB apply evidence\n\nOne PCB apply run moved `R1` by exactly +2.5 mm in the exchange XML. The committed\nworking SHA and real exchange SHA matched. The operator confirmed the GUI move, then\nsaved and independently re-exported the board. The re-export retained the intended\ncomponent position with zero component differences in semantic comparison and stable\n65-net/77-component connectivity counts.\n\n## Interpretation\n\nThis record proves the explicit operations and topology above. It does not prove every\nMCP tool, every DipTrace version, every XML structure, native library mutation, or\noptional external solver. The project files and complete local artifact directory are\nnot redistributed, so this record remains operator-supplied acceptance evidence and\ndoes not create a package-owned high-trust registry entry.\n\n## Резюме на русском\n\nПроверены PCB apply/cancel/wrong-SHA и Schematic apply/cancel/wrong-SHA на DipTrace\n5.2.0.4 с MCP-сервером в WSL. Native Windows path сохранялся в metadata, WSL path\nвычислялся только в памяти, фантомный `C:\\mnt\\c\\...` не создавался. Применённые\nизменения подтверждены в GUI и, для PCB, независимым save/re-export; отменённые и\nотклонённые изменения не попали в документ. Итог: `ACCEPTANCE: PASS`,\n`RELEASE BLOCKER: NO` для этой матрицы.\n"""
write("docs/LIVE_ACCEPTANCE_2026-07-31.md", acceptance)

# Strengthen focused unit coverage discovered during review.
test_path = "tests/test_cross_platform_exchange_paths.py"
test_content = read(test_path)
new_tests_marker = "def test_windows_origin_is_rejected_outside_windows_or_wsl"
if new_tests_marker not in test_content:
    test_content += """\n\n\ndef test_windows_origin_is_rejected_outside_windows_or_wsl(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    monkeypatch.setattr(sessions_module, \"_is_wsl_runtime\", lambda _platform: False)\n\n    with pytest.raises(SessionError, match=\"accessible only from Windows or WSL\") as caught:\n        sessions_module._exchange_path_for_runtime(\n            r\"C:\\Users\\fireo\\plugin_exchange.xml\",\n            \"windows\",\n            runtime_os_name=\"posix\",\n            runtime_platform=\"linux\",\n        )\n\n    assert caught.value.payload.code == \"path_access_denied\"\n\n\ndef test_relative_wsl_mount_root_is_rejected(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    monkeypatch.setattr(sessions_module, \"_is_wsl_runtime\", lambda _platform: True)\n    monkeypatch.setenv(\"DIPTRACE_MCP_WSL_MOUNT_ROOT\", \"relative-mount\")\n\n    with pytest.raises(SessionError, match=\"must be absolute\") as caught:\n        sessions_module._exchange_path_for_runtime(\n            r\"C:\\Users\\fireo\\plugin_exchange.xml\",\n            \"windows\",\n            runtime_os_name=\"posix\",\n            runtime_platform=\"linux\",\n        )\n\n    assert caught.value.payload.code == \"path_access_denied\"\n\n\ndef test_windows_runtime_rejects_posix_origin() -> None:\n    with pytest.raises(SessionError, match=\"refuses a POSIX\") as caught:\n        sessions_module._exchange_path_for_runtime(\n            \"/tmp/plugin_exchange.xml\",\n            \"posix\",\n            runtime_os_name=\"nt\",\n            runtime_platform=\"win32\",\n        )\n\n    assert caught.value.payload.code == \"session_state_invalid\"\n\n\ndef test_unknown_exchange_path_platform_is_rejected() -> None:\n    with pytest.raises(SessionError, match=\"no valid exchange-path platform\") as caught:\n        sessions_module._exchange_path_for_runtime(\n            \"/tmp/plugin_exchange.xml\",\n            \"unknown\",\n            runtime_os_name=\"posix\",\n            runtime_platform=\"linux\",\n        )\n\n    assert caught.value.payload.code == \"session_state_invalid\"\n"""
    write(test_path, test_content)

# Stage new documentation so git-ls-files sees it, remove temporary automation from
# the index, then regenerate the exact publication allowlist.
subprocess.run(
    ["git", "add", "docs/CODE_REVIEW_2026-07-31.md", "docs/LIVE_ACCEPTANCE_2026-07-31.md"],
    cwd=ROOT,
    check=True,
)
subprocess.run(["git", "rm", "--", str(SELF), str(WORKFLOW)], cwd=ROOT, check=True)
subprocess.run(
    ["python", "scripts/audit_release_artifacts.py", "--write-allowlist"],
    cwd=ROOT,
    check=True,
)
