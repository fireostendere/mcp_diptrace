# Security and Policy

## Invariants

- paths resolve only within the workspace or explicitly allowed roots;
- document, artifact, and log sizes are bounded;
- `DOCTYPE` and `ENTITY` declarations are rejected;
- supported source encodings and BOMs are detected and preserved, writes are atomic, backups are created, and modified XML is reparsed;
- commits and rollbacks use SHA-256 optimistic concurrency;
- persisted record and job/export artifact reads require confined non-redirected paths, and embedded record identifiers must match the requested identifiers;
- transaction snapshots and rollback backups are derived from the transaction identifier and hash-checked instead of trusting persisted path strings;
- locked objects are preserved by default unless an operation explicitly allows otherwise;
- only one live DipTrace bridge session may be active;
- external processes use fixed typed argument vectors, `shell=false`, isolated job directories, bounded streaming logs/results, a global concurrency cap, process-tree timeouts, terminal cancellation, and explicit reaping;
- the core does not expose arbitrary shell execution supplied by an LLM;
- high-level write tools default to preview/dry-run behavior and must not silently convert unavailable capabilities into success.

## Policy Profiles

Set the active profile with `DIPTRACE_MCP_POLICY`:

| Profile | Preview/plan | Commit | External execution | Native manufacturing |
| --- | --- | --- | --- | --- |
| `read_only` | no | no | no | no |
| `review` | yes | no | no | no |
| `interactive_edit` | yes | yes | explicit typed tools | no |
| `automation` | yes | yes | yes | no |
| `manufacturing` | yes | yes | yes | policy permits requests, but unsupported native outputs still fail |

A policy profile grants permission; it does not create an implementation. Generic BOM/fabrication/assembly manifests are analysis artifacts, not native Gerber/NC Drill/ODB++/IPC-2581 outputs. Unsupported native requests return explicit capability errors.

A policy violation returns `policy_denied` with profile, operation, and dry-run context. Rollback is not blocked by ordinary write policy because it restores a previously captured state.

## Local Security Boundary

The server is designed as a trusted local single-user engineering tool.

Streamable HTTP listens on loopback by default. There is no built-in OAuth, multi-user isolation, or remote authentication. Exposing the HTTP endpoint outside the local machine requires a separate authenticated reverse proxy and is outside the core security model.

Filesystem restrictions reduce accidental reach but do not make an LLM an engineering authority. A model can still request a structurally valid but electrically incorrect change. Visual review, ERC/DRC, and engineering judgment remain mandatory for consequential edits.

## Local State and Retention

Offline backups are held under `DIPTRACE_MCP_STATE_DIR/offline_backups`, keyed by the
SHA-256 of the canonical target path. They are not placed in the user's design
directory. Backup metadata binds the opaque directory key to one target and the
backup filename binds it to the original content hash.

Count-and-age retention runs when a store is constructed. It deletes only fully
parsed terminal records confined to that store. Nonterminal transactions, plans and
jobs, active sessions, sessions referenced by `active.json`, and their internal
backups are never retention candidates. The newest valid offline backup per target is
also retained. A corrupt record, unknown status, ID mismatch, symbolic link, junction,
or path outside the state tree fails closed: it is neither followed nor deleted.

## Trust Boundary

The trust model separates provenance from authority.

Clients are not trust authorities. Runtime sidecars, user-supplied evidence, fixture manifests, matching hashes, and workspace-controlled JSON cannot self-mint `diptrace_roundtrip_verified` or `external_tool_roundtrip_verified`.

Evidence is bound to exact file roles/paths, source type, before/after SHA-256 values, and required semantic-comparison categories. Rollback reparses and revalidates restored provenance/evidence rather than trusting stale metadata.

High-trust promotion remains unavailable until the project has an authenticated server-owned registry, signature verifier, or committed allowlist.

## Write-Path Trust Invalidation

Documentation must not claim that every possible write path has already proven identical trust-invalidation behavior.

At the current baseline, `get_capabilities` explicitly reports that complete all-write-path invalidation coverage is not yet established. The remaining named paths are:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

The security requirement for each path is fail-closed behavior: a mutation must not allow stale higher-trust evidence to remain effective, and rollback must not restore authority unless the restored document/evidence pair is revalidated successfully.

Closing these paths is a compatibility/security priority in [ROADMAP.md](ROADMAP.md).

## External Process Boundary

Freerouting, ngspice, and openEMS integrations are explicit typed adapters rather than generic command execution.

Required properties include:

- executable/configuration selected by server settings rather than model-supplied shell fragments;
- `shell=false`;
- isolated job workspace;
- sanitized/bounded environment and arguments;
- explicit timeout, result-size, and log-size limits;
- a configured cross-adapter concurrency limit;
- process-group/tree termination followed by root-process reaping;
- structured status/result parsing;
- terminal cancellation semantics;
- explicit `external_tool_unavailable`, timeout, malformed-output, or non-convergence failures instead of fabricated fallback output.

A configured external adapter may still be unavailable for the active document if required geometry, stackup data, or source artifacts are missing.

## Manufacturing Boundary

The `manufacturing` policy profile is not evidence that native manufacturing generation exists. The current core can prepare/review bounded generic manifests and artifacts, but native Gerber/NC Drill/ODB++/IPC-2581 generation is outside the verified capability set.

The project must continue to fail explicitly rather than produce a file that merely looks like a manufacturing artifact without a verified writer/API.
