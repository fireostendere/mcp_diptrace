# Trusted provenance registry

## Current status

The repository-owned registry mechanism is implemented and fail-closed. The
committed registry currently contains **0 trusted entries**, so no existing
fixture or user document receives high-trust status from it.

The machine-readable count and entry summaries are available in:

- `get_capabilities().trust_model.trusted_registry`;
- the `diptrace://trusted-provenance-registry` MCP resource.

The production registry is
`src/diptrace_mcp/data/trusted_provenance_registry.json`. It is package data
shipped in the wheel. Workspace files, the MCP state directory, environment
variables, and client arguments cannot select a replacement registry.

## What one entry proves

An entry is a repository-level assertion made through code review. It binds:

- one exact document SHA-256;
- one exact trusted-evidence-manifest SHA-256;
- the repository-relative package-data path from which those reviewed evidence
  bytes are loaded;
- the document source type;
- the validation level.

At startup the loader requires canonical deterministic JSON, sorted unique
entry ids, a safe relative evidence path, an exact hash match for the packaged
evidence source, a strict trusted-evidence schema, and matching document hash,
source type, authority, and validation level. At use time the service again
checks the current document, sidecar, allowed-root evidence path, evidence
bytes, source type, validation level, and registry entry. Any missing,
unregistered, relocated, stale, or tampered binding downgrades effective trust
to `synthetic_parser_only` with a warning.

SHA-256 establishes exact byte identity, not DipTrace provenance. The trust
authority comes from independent human review of the evidence before the
registry change is accepted.

## Adding the first entry

The first production entry requires a human with the relevant DipTrace version
and a separate repository review. Do not add an entry merely because XML
parses, an operator says it was exported, user-supplied hashes match, or a
synthetic round trip passes.

The reviewer must:

1. inspect provenance-bearing source/open-save/re-export artifacts collected
   by the [operator-assisted evidence workflow](EVIDENCE_CAPTURE.md);
2. verify that file roles are distinct, the claimed DipTrace build and source
   type are supported by retained evidence, and semantic comparison is
   complete for the claimed validation level;
3. place the reviewed trusted evidence manifest under package-owned
   `src/diptrace_mcp/data/` without changing any acceptance fixture;
4. add its exact binding to the registry in sorted canonical form;
5. run the registry tests and all project gates, then have the source and
   registry changes reviewed together.

Copying an authorized document to a new path does not transfer high trust,
because evidence is path-role bound. The copy remains synthetic until a
separate reviewed entry binds evidence for the new target.
