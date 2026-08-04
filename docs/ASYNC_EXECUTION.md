# Async Execution and Event-Loop Safety

DipTrace MCP keeps the engineering service layer synchronous. MCP Python SDK/FastMCP v1 invokes synchronous tool functions directly from its async execution path, so an unwrapped blocking call can monopolize the server event loop. DipTrace MCP therefore installs a project-owned async boundary around every registered synchronous tool and runs the original callable through `anyio.to_thread.run_sync`.

This keeps filesystem access, XML parsing, hashing, subprocess waits, bridge access, geometry work, and bounded routing computations away from the MCP event loop without converting the service surface into a second async API.

## Enforced contract

The repository enforces three related properties:

1. Every maintained public tool carries the project thread-offload marker after server registration.
2. The known routing-heavy tools use the same boundary:
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

The tests use an in-memory MCP client/server session. A slow service call is started through `session.call_tool`, then the event loop must schedule a heartbeat before the slow call completes. The I/O probe blocks its worker for two seconds and the CPU probe runs for more than one second; both tests fail when the callable executes directly on the event loop.

## CPU work

Thread offload protects event-loop responsiveness but does not make pure-Python A* routing run in parallel with other Python code under the GIL. The current routing workloads remain in a bounded worker thread because they share service models and transaction contracts that are not process-serializable yet.

A future process-worker migration requires separate evidence for:

- immutable and serializable routing inputs;
- bounded worker count and memory use;
- timeout and process-tree cleanup;
- cancellation behavior;
- deterministic route-plan output;
- guarded application through the existing expected-SHA transaction boundary.

## Cancellation and mutation boundary

Worker-thread execution protects event-loop responsiveness; it does not make synchronous work safely interruptible. A cancelled MCP request must not be treated as proof that the underlying synchronous operation stopped immediately.

For that reason:

- write operations retain transaction, expected-SHA, policy, backup, and atomic-write gates;
- routing computes a plan before a separate guarded apply step;
- live bridge finalization retains its own SHA and session barriers;
- thread offload uses `abandon_on_cancel=False` for public service calls;
- process workers are not introduced until their serialization, cancellation,
  cleanup, and state-isolation contracts are independently tested.

A responsiveness pass is not a claim that every long-running operation is fast. It proves only that maintained public MCP calls do not monopolize the event loop under the tested MCP SDK contract.

## Adding an async tool

A native `async def` MCP tool is rejected by the registry audit until its implementation receives an explicit non-blocking review. Such a tool must not call synchronous filesystem, XML, subprocess, routing, or bridge code directly. Any approved native async tool must carry a separate review marker and add a protocol-level responsiveness test for its blocking boundaries.
