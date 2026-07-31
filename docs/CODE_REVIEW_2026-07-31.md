# Code Review — 2026-07-31

## Scope

Review baseline: `main` at `29f9721d8f3efbc32e6c33f891bf1c27365b3ca0`.

The review focused on the release-critical paths changed after 0.1.0:

- `src/diptrace_mcp/sessions.py`: session identity, Windows/WSL path translation,
  allowed-root binding, stable-file reads, finish-request publication, and finalization;
- `src/diptrace_mcp/external_process.py`: bounded output draining, Windows Job
  Object cleanup, reader shutdown, and slot release;
- bridge build/install PowerShell scripts and their CI smoke path;
- cross-platform path, live lifecycle, external-process, public MCP contract,
  release-artifact, and documentation tests; and
- README, roadmap, testing, compatibility, usage, architecture, changelog, and
  release-policy consistency.

## Findings

### Release-blocking findings

None found in the reviewed baseline. The full repository CI and the controlled host
acceptance matrix remain the release gates; this review is not a substitute for them.

### Closed defect: Windows/WSL exchange path binding

The previous false-positive apply path was caused by persisting `/mnt/c/...` into
metadata later consumed by the Windows bridge as `C:\mnt\c\...`. The current code
stores the creator-native path and immutable platform, derives WSL drive mounts only
in memory, requires an absolute drive-letter path for Windows origin, rejects path-style
mismatches before control publication, re-reads the original and exchange files through
allowed-root/stable-file checks, and verifies the replacement SHA. Unit tests and the
real DipTrace campaign cover the failure mode.

### Closed defect: inherited stdout on Windows

The external-process runner correctly places a suspended root into a kill-on-close Job
Object before resuming it. When a descendant inherits stdout after the root exits, the
runner force-closes its local pipe only as a last-resort reader unblock. The reviewed
change avoids turning that intentional close into a false output-read failure while
retaining real read errors when the stream is not closed. The native Windows regression
test covers root exit, inherited output, descendant termination, log contents, and slot
recovery.

### Documentation drift

The code and host evidence were newer than the public documentation. Several pages
still described only the DipTrace 5.3.0.2 schematic campaign, did not record the
Windows/WSL native-path invariant, and contained conflicting wording about the already
published Apache-2.0 development release. This change reconciles those claims without
converting local evidence into public-CI or high-trust registry evidence.

### Regression coverage added

Focused tests now explicitly cover:

- refusal of a Windows-origin path on ordinary non-WSL Linux;
- refusal of a relative `DIPTRACE_MCP_WSL_MOUNT_ROOT`;
- refusal of POSIX-origin session metadata on Windows; and
- refusal of an unknown exchange-path platform.

## Residual risks and non-claims

- Real DipTrace GUI acceptance is operator-assisted and not run in public CI.
- The package-owned trusted provenance registry still contains zero reviewed entries.
- The public transport workflow exercises 63 distinct tools, not every registered tool.
- Total measured coverage is above the enforced 85% floor but below the stated 88%
  project target.
- Native Component/Pattern Library mutation, broad 5.3 PCB writer coverage, real
  DSN/SES pairs, and real openEMS/Freerouting matrices remain evidence-gated.
- All-write-path trust invalidation is still explicitly incomplete for the paths listed
  by `get_capabilities` and `docs/TESTING.md`.

## Verdict

No release blocker was identified for the tested 0.1.1 candidate scope. Release notes
must remain scoped to the implemented contracts and the exact acceptance matrix.

## Краткое резюме на русском

Критических, высоких или средних release-blocking дефектов в проверенном baseline не
обнаружено. Подтверждены корректность native Windows exchange path, in-memory WSL
translation, fail-closed wrong-SHA/path mismatch, безопасное завершение Windows process
tree и соответствующие regression tests. Обновлена документация, но ограничения по
redistributable fixtures, native library writers, external solvers, trust invalidation
и неполному охвату всех 159 tools остаются явными.
