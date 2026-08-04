from __future__ import annotations

import argparse
import inspect
import json
import tempfile
from pathlib import Path
from typing import Any

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server

HEAVY_TOOL_NAMES = {
    "analyze_routing_congestion",
    "plan_diff_pair_route",
    "route_connection",
    "route_connections",
    "route_diff_pair",
    "route_net",
}
_OFFLOAD_MARKER = "__diptrace_mcp_thread_offload__"


def audit_event_loop_boundary() -> dict[str, Any]:
    """Audit the project-owned worker-thread boundary around FastMCP v1 tools."""

    with tempfile.TemporaryDirectory(prefix="diptrace-mcp-event-loop-audit-") as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        state_dir = root / "state"
        workspace.mkdir()
        settings = Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state_dir,
        )
        server = create_server(settings)

    tools = server._tool_manager._tools
    offloaded_tools = sorted(
        name for name, tool in tools.items() if getattr(tool.fn, _OFFLOAD_MARKER, False)
    )
    unprotected_sync_tools = sorted(
        name
        for name, tool in tools.items()
        if not inspect.iscoroutinefunction(tool.fn)
        and not getattr(tool.fn, _OFFLOAD_MARKER, False)
    )
    unreviewed_async_tools = sorted(
        name
        for name, tool in tools.items()
        if inspect.iscoroutinefunction(tool.fn)
        and not getattr(tool.fn, _OFFLOAD_MARKER, False)
    )
    missing_heavy_tools = sorted(HEAVY_TOOL_NAMES.difference(tools))
    heavy_tools_without_offload = sorted(
        name
        for name in HEAVY_TOOL_NAMES.intersection(tools)
        if not getattr(tools[name].fn, _OFFLOAD_MARKER, False)
    )

    reasons: list[str] = []
    if unprotected_sync_tools:
        reasons.append("One or more synchronous public tools execute without thread offload.")
    if unreviewed_async_tools:
        reasons.append(
            "One or more native async public tools lack an explicit non-blocking review marker."
        )
    if missing_heavy_tools:
        reasons.append("Expected routing tools are missing from the public registry.")
    if heavy_tools_without_offload:
        reasons.append("One or more CPU-heavy routing tools lack thread offload.")

    return {
        "status": "pass" if not reasons else "fail",
        "tool_count": len(tools),
        "offloaded_tool_count": len(offloaded_tools),
        "offloaded_tools": offloaded_tools,
        "unprotected_sync_tools": unprotected_sync_tools,
        "unreviewed_async_tools": unreviewed_async_tools,
        "heavy_tools": sorted(HEAVY_TOOL_NAMES),
        "missing_heavy_tools": missing_heavy_tools,
        "heavy_tools_without_offload": heavy_tools_without_offload,
        "execution_contract": (
            "FastMCP v1 invokes synchronous tools on the event loop. DipTrace MCP replaces "
            "each registered synchronous callable with an async wrapper that executes the "
            "original callable through anyio.to_thread.run_sync."
        ),
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the public MCP event-loop blocking boundary."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    result = audit_event_loop_boundary()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "event-loop audit: "
            f"{result['status']} — {result['offloaded_tool_count']}/"
            f"{result['tool_count']} tools offloaded"
        )
        for reason in result["reasons"]:
            print(f"- {reason}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
