# Security and Policy

## Invariants

- caller-supplied paths are interpreted literally and resolve only within the workspace or
  explicitly allowed roots; environment and home expansion is reserved for server-owned
  configuration;
- document, artifact, and log sizes are bounded;
- `DOCTYPE` and `ENTITY` declarations are rejected;
- supported source encodings and BOMs are detected and preserved; raw and semantic XML
  output is reparsed and checked against the requested semantic tree before it can be
  written;
- non-finite numeric values are rejected in typed inputs, normalized XML data, and
  Specctra sessions rather than entering geometry or rule comparisons;
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

Paths supplied in MCP calls are not passed through environment-variable or home-directory
expansion: `$NAME`, `%NAME%`, and `~` remain literal path components. Operator-controlled
configuration such as `DIPTRACE_MCP_WORKSPACE`, `DIPTRACE_MCP_ALLOWED_ROOTS`, and executable
paths may be expanded when settings are loaded. This distinction prevents a caller from
using path errors as an environment-variable disclosure channel.

## XML and Numeric Input Boundary

The XML loader records the detected codec, byte order, and BOM. Guarded writes preserve
UTF-8 (with or without BOM), UTF-16LE/BE, US-ASCII, and ISO-8859-1 source representation,
encode only the replacement spans, and preserve untouched bytes. Clean UTF-32 input is
currently unsupported and fails closed. Every raw edit and raw-preserving
semantic compilation is reparsed and compared with the intended in-memory element tree;
passing XML syntax alone is not sufficient.

The DTD/entity guard combines a whole-document byte scan, allowlisted decoded scans, and
Expat declaration callbacks. XML and SES numeric parsers report typed errors for `NaN` and
infinities with available element/attribute or character-offset context, and typed request
models disallow non-finite floats.

The DSN serializer intentionally supports only quoted tokens that need no unverified
escaping or character encoding: printable ASCII without quotes or backslashes. It refuses
control characters, quotes, backslashes, and non-ASCII quoted values. The SES reader
requires UTF-8 and refuses backslash escapes and literal control characters in quoted
tokens. These refusals remain in place until the real DipTrace DSN/SES conventions in
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md#q17-what-dsnses-conventions-does-diptrace-use-on-a-real-routed-design)
are established.

## Local State and Retention

Offline backups are held under `DIPTRACE_MCP_STATE_DIR/offline_backups`, keyed by the
SHA-256 of the canonical target path. They are not placed in the user's design
directory. Backup metadata binds the opaque directory key to one target and the
backup filename binds it to the original content hash. Direct offline replacements use
this per-target history; semantic transaction commits keep their authenticated recovery
bytes inside the central transaction record, and live writes keep them inside the
session record. In each case an existing target is captured before replacement.
Creating a new target produces no pre-existing-content backup; overwrite operations do.

Count-and-age retention runs when a store is constructed. It deletes only fully
parsed, validated terminal records confined to that store. Active or nonterminal
records and the state needed to recover them are protected. The newest valid offline
backup per target is also retained. A corrupt record, unknown status, ID mismatch,
symbolic link, junction, or path outside the state tree fails closed: it is neither
followed nor deleted. The configured count and age values are cleanup targets, not
storage quotas: protected or unverifiable records can keep the on-disk count above a
threshold, and cleanup failure does not make startup destructive.

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
- POSIX process-group termination and Windows Job Objects configured with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, followed by root-process reaping;
- structured status/result parsing;
- terminal cancellation semantics;
- explicit `external_tool_unavailable`, timeout, malformed-output, or non-convergence failures instead of fabricated fallback output.

A configured external adapter may still be unavailable for the active document if required geometry, stackup data, or source artifacts are missing.

## Manufacturing Boundary

The `manufacturing` policy profile is not evidence that native manufacturing generation exists. The current core can prepare/review bounded generic manifests and artifacts, but native Gerber/NC Drill/ODB++/IPC-2581 generation is outside the verified capability set.

The project must continue to fail explicitly rather than produce a file that merely looks like a manufacturing artifact without a verified writer/API.
