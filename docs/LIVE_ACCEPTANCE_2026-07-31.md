# Live Acceptance Record — 2026-07-31

## Status

- Result: **PASS**
- Release blocker for the tested matrix: **NO**
- Repository baseline reviewed for release: `main` after the Windows/WSL path fix and
  Windows stdout cleanup fix
- Host: Windows DipTrace 5.2.0.4
- MCP runtime: WSL

## Matrix

| Test | Result | Evidence boundary |
| --- | --- | --- |
| Repository tests | PASS | Local campaign reported 987 passed, 4 skipped; GitHub CI remains authoritative per commit |
| Ruff and strict Mypy | PASS | Zero reported issues |
| Clean Windows bridge build | PASS | Executable built, non-empty, and `--help` smoke-run |
| Four-target bridge install | PASS | PCB, Schematic, Component, and Pattern destinations matched the build hash |
| Offline smoke | PASS | Read, dry-run, commit, and wrong-SHA guard |
| PCB apply | PASS | Real exchange updated, GUI change observed, Save As and independent re-export matched semantically |
| PCB cancel | PASS | Committed working edit did not reach exchange, GUI, or re-export |
| PCB wrong SHA | PASS | Refused without host mutation |
| Schematic apply | PASS | Intended value change observed in GUI |
| Schematic cancel | PASS | Cancelled with original exchange SHA preserved |
| Schematic wrong SHA | PASS | Refused with exchange SHA unchanged |
| Phantom path | PASS | No `C:\mnt\c\...` target |
| Metadata integrity | PASS | Windows-native path and `exchange_path_platform="windows"` throughout |

## Proven PCB apply evidence

One PCB apply run moved `R1` by exactly +2.5 mm in the exchange XML. The committed
working SHA and real exchange SHA matched. The operator confirmed the GUI move, then
saved and independently re-exported the board. The re-export retained the intended
component position with zero component differences in semantic comparison and stable
65-net/77-component connectivity counts.

## Interpretation

This record proves the explicit operations and topology above. It does not prove every
MCP tool, every DipTrace version, every XML structure, native library mutation, or
optional external solver. The project files and complete local artifact directory are
not redistributed, so this record remains operator-supplied acceptance evidence and
does not create a package-owned high-trust registry entry.
