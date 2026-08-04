# Async Execution and Event-Loop Safety

DipTrace MCP keeps the engineering service layer synchronous. Public MCP tools are registered as synchronous callables, and FastMCP executes those callables through its AnyIO worker-thread boundary rather than directly on the event loop.

This design keeps filesystem access, XML parsing, hashing, subprocess waits, bridge access, geometry work, and bounded routing computations away from the MCP event loop without converting the 7,000-line service surface into a second async API.

## Enforced contract

The repository enforces three related properties:

1. Every public tool callable remains synchronous at registration time.
2. The known routing-heavy tools use the same synchronous boundary:
   `route_connection`, `route_net`, `route_connections`, `route_diff_pair`,
   `plan_diff_pair_route`, and `analyze_routing_congestion`.
3. Protocol-level responsiveness probes run a deliberately blocking I/O call
   and a deliberately CPU-heavy call while measuring an event-loop heartbeat.

Run the static registry audit with:

```bash
python scripts/audit_event_loop.py --json
```

Run the connected MCP responsiveness probes with:

```bash
python -m pytest -q tests/test_event_loop_responsiveness.py
```

The tests use an in-memory MCP client/server session. A slow synchronous tool is started through `session.call_tool`, then the event loop must schedule a heartbeat before the slow call completes. The I/O probe would block for two seconds and the CPU probe runs for more than one second if a callable were executed directly on the event loop.

## Cancellation and mutation boundary

Worker-thread execution protects event-loop responsiveness; it does not make synchronous work safely interruptible. A cancelled MCP request must not be treated as proof that the underlying synchronous operation stopped immediately.

For that reason:

- write operations retain transaction, expected-SHA, policy, backup, and atomic-write gates;
- routing computes a plan before a separate guarded apply step;
- live bridge finalization retains its own SHA and session barriers;
- the project does not use `abandon_on_cancel=True` around mutating service calls;
- process workers are not introduced until their serialization, cancellation,
  cleanup, and state-isolation contracts are independently tested.

A responsiveness pass is not a claim that every long-running operation is fast. It only proves that maintained synchronous MCP calls do not monopolize the event loop under the tested FastMCP/MCP SDK contract.

## Adding an async tool

An `async def` MCP tool is rejected by the registry audit until its implementation receives an explicit non-blocking review. Such a tool must not call synchronous filesystem, XML, subprocess, routing, or bridge code directly. Any approved async tool must add a protocol-level responsiveness test for its blocking boundaries.
