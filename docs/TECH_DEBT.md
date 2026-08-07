# Technical Debt Register

This register separates maintainability debt from compatibility/evidence debt so release decisions do not conflate them.

## Architecture debt

- Keep `diptrace_mcp.server` as a compatibility facade while implementation is split into input/boundary and runtime modules.
- Keep adapter parsing helpers and record/query builders in explicit modules rather than rebuilding `adapters.py` as a monolith.
- Keep `DipTraceService` focused on orchestration; stateful store construction belongs to `services.container`.
- Coverage floors for high-risk modules are ratchets and must not be lowered to make CI pass without a documented reason.
- Packaged skill scripts are generated copies of canonical scripts and must pass the synchronization gate.
- Release/version-bearing metadata must agree with `release.json`.

## Evidence debt

The following remain evidence/acceptance work rather than architecture blockers:

- real DipTrace acceptance for all trust-invalidation paths;
- broader redistributable current-version fixtures;
- real authored-wire/ratline round trips;
- native Component/Pattern writer semantics;
- optional openEMS/Freerouting external validation.

Evidence debt must stay visible, but it must not be represented as missing code structure when the implementation boundary already exists.
