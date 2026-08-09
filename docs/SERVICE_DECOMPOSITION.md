# Service decomposition

`DipTraceService` is an internal composition/orchestration layer for the MCP server. The supported product contract is the MCP `tools/list` surface, which is frozen by `reference/mcp-tools-list.snapshot.json` and exercised through the normal test suite.

Domain implementations live under `src/diptrace_mcp/services/`. Internal forwarding topology, exact facade method ownership, and private helper placement are intentionally not versioned contracts; they may change when doing so preserves the MCP behavior and safety invariants.

The durable architecture overview is in [`ARCHITECTURE.md`](ARCHITECTURE.md).
