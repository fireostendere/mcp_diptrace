# PCB skill acceptance criteria

The old 57-package set repeated generic prose and schemas; its replacement originally
kept eight inspection/editing workflows. A fixed count also excluded requested lifecycle
work and obscured local native capabilities. The current catalog keeps distinct outcomes
and shared contracts, without imposing an arbitrary maximum number of skills.

A skill belongs in this catalog when:

1. It has a clear user outcome, mode, inputs, artifacts, and completion boundary.
2. It reuses existing workflows/references for shared steps. A lifecycle coordinator
   routes stages; it does not copy each specialist's instructions.
3. Claimed MCP tools are registered, native CLI commands match actual shipped parsers,
   and network/hardware/operator prerequisites are explicit. A missing MCP endpoint
   does not imply that a separately implemented local helper is unavailable.
4. Its advice contains useful task-specific constraints and source/evidence requirements.
   Numbers are included when relevant, not to meet a word or numeral quota.
5. Frontmatter, names, links, runtime guidance, result schema, examples and wheel delivery
   pass the shared checks. Relative package links remain inside the installed skill tree.

Keep one canonical source under root `skills/`; configure the host's search path.
Do not create duplicate per-host copies, schemas, generated examples, or metadata
directories merely to increase the package count. Named existing skills may be retained
as specialized workflows while new requested outcomes are added to
[catalog.json](catalog.json).

The shared suite exercises document contracts and native command parsing without
pretending to prove real GUI acceptance on an untested machine. Real board acceptance
still requires execution evidence for that board, host, editor version and profile.
