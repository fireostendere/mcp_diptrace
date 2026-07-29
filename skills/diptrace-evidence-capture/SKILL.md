---
name: diptrace-evidence-capture
description: Guide a human operator through quarantined DipTrace source, open-save, and re-export capture, dry-run ingest, MCP validation, explicit confirmation, and metadata recording. Use when the user says “Guide an operator through a reviewable DipTrace round-trip capture.”
---

# DipTrace evidence capture

Collect a reviewable candidate without promoting operator claims to trusted provenance. Read
[`references/operator-workflow.md`](references/operator-workflow.md) before running commands.
Use public `tools/list` for exact callable names and `get_capabilities` for session, document, and
feature availability.

## Mandatory stage order

1. **Candidate capture:** choose a committed question recipe and initialize an operator-owned
   allowed root. Record three distinct roles in order: `source`, `open_save`, `reexport`. Each role
   gets its own path, SHA-256, XML inventory, and stage-specific attestations.
2. **Candidate finalization:** answer every required recipe check from actual GUI observation, then
   finalize. The result is `operator_supplied_unverified`, `candidate_only=true`, and grants no
   validation level.
3. **Dry-run ingest:** run the shipped `ingest_fixtures.py --dry-run`. It re-reads every role,
   validates candidate and detached hashes, reports conflicts, and has no apply implementation.
4. **MCP validation:** bind `source` and `saved`, plus `reexport` when available, to the selected
   document and call `validate_roundtrip_evidence`. Require exact role paths and hashes. This call
   is read-only and still grants no trusted authority.
5. **Explicit confirmation:** show the operator the candidate ID, document SHA, role hashes,
   semantic comparison summary, conflicts, and metadata files that would be written. Silence,
   script success, or prior capture consent is not confirmation.
6. **Metadata record:** only after that confirmation call `record_roundtrip_evidence`. It may write
   `<document>.roundtrip-evidence.json` and `<document>.provenance.json`; it never changes design
   bytes and never grants high trust.

Do not make fixture-tree changes. A separate reviewed source change is required to add trusted
registry entries.

## Quantitative and provenance boundaries

- Required capture roles: exactly three named stages; paths must be distinct even when bytes are
  identical.
- Supported XML source types: PCB, Schematic, Component Library, and Pattern Library.
- Supported document units recorded literally: `mm`, `inch`, and `mil`.
- Each XML input is bounded at 128 MiB; DTD and entity declarations are refused.
- A SHA-256 is exactly 64 lowercase hexadecimal characters and is rechecked at every handoff.

The packaged scripts are byte-identical mirrors of
[`../../scripts/capture_diptrace_evidence.py`](scripts/capture_diptrace_evidence.py) and
[`../../scripts/ingest_fixtures.py`](scripts/ingest_fixtures.py); their hashes are pinned in
[`../SOURCES.sha256`](../SOURCES.sha256).

## Result

Return [`../shared/result.schema.json`](../shared/result.schema.json). Label GUI attestations
`operator`, parsed identities and hashes `document`, semantic comparison `analytical` only when it
is deterministic code output, and planning advice `heuristic`. Any missing role, hash mismatch,
unresolved checklist item, path alias, failed comparison, or absent explicit confirmation prevents
`completed`.
