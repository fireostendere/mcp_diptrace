# Architecture cleanup execution

This branch executes the maintainability work identified after the 0.2.1 release without changing the public MCP contract.

1. Split the MCP server facade from input/boundary definitions and runtime registration.
2. Split adapter helpers and dependency-closed record/query builders out of the adapters monolith.
3. Extend coverage ratchets and add architecture regression checks.
4. Move stateful store/gateway construction into a typed service container.
5. Treat packaged evidence scripts as generated copies with an explicit synchronization gate.
6. Align release documentation and version-bearing metadata with one committed release manifest.

Acceptance criteria: the branch remains based on `main`, preserves the 159-tool MCP snapshot and 157/148 service Facade contracts, and all required GitHub Actions checks pass.
