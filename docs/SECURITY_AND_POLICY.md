# Security and Policy

## Invariants

- paths resolve only within the workspace or explicitly allowed roots;
- document, artifact, and log sizes are bounded;
- `DOCTYPE` and `ENTITY` declarations are rejected;
- UTF-8 handling is explicit, writes are atomic, backups are created, and results are reparsed;
- commits and rollbacks use SHA-256 optimistic concurrency;
- locked objects are preserved by default;
- only one live session may be active;
- external processes use a fixed typed argument vector, `shell=false`, an isolated job
  directory, bounded logs, a timeout, and cancellation;
- the core does not use the network or execute arbitrary shell commands supplied by an LLM.

## Policy Profiles

Set the profile with `DIPTRACE_MCP_POLICY`:

| Profile | Preview/plan | Commit | External execution | Native manufacturing |
| --- | --- | --- | --- | --- |
| `read_only` | no | no | no | no |
| `review` | yes | no | no | no |
| `interactive_edit` | yes | yes | explicit typed tools | no |
| `automation` | yes | yes | yes | no |
| `manufacturing` | yes | yes | yes | yes |

Generic BOM and release manifests are analysis artifacts, not native manufacturing
outputs. A policy violation returns `policy_denied` with profile, operation, and dry-run
details. Rollback is not blocked by policy because it restores a previously safe state.

## Trust Boundary

The server is a local single-user tool. Streamable HTTP listens on loopback by default;
there is no built-in remote authentication. Exposing the port externally requires a
separate reverse proxy and authentication layer and is outside the core security model.
