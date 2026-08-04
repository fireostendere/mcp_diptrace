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


def audit_event_loop_boundary() -> dict[str, Any]:
    """Audit the public tool registry's synchronous worker-thread boundary."""

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
    sync_tools = sorted(
        name for name, tool in tools.items() if not inspect.iscoroutinefunction(tool.fn)
    )
    async_tools = sorted(
        name for name, tool in tools.items() if inspect.iscoroutinefunction(tool.fn)
    )
    missing_heavy_tools = sorted(HEAVY_TOOL_NAMES.difference(tools))
    async_heavy_tools = sorted(HEAVY_TOOL_NAMES.intersection(async_tools))

    status = "pass"
    reasons: list[str] = []
    if async_tools:
        status = "fail"
        reasons.append(
            "Public async tool callables bypass the project-wide synchronous FastMCP "
            "worker-thread contract and require an explicit non-blocking review."
        )
    if missing_heavy_tools:
        status = "fail"
        reasons.append("Expected routing tools are missing from the public registry.")
    if async_heavy_tools:
        status = "fail"
        reasons.append("One or more CPU-heavy routing tools are registered as async callables.")

    return {
        "status": status,
        "tool_count": len(tools),
        "sync_tool_count": len(sync_tools),
        "async_tool_count": len(async_tools),
        "async_tools": async_tools,
        "heavy_tools": sorted(HEAVY_TOOL_NAMES),
        "missing_heavy_tools": missing_heavy_tools,
        "async_heavy_tools": async_heavy_tools,
        "execution_contract": (
            "All public tools remain synchronous callables at registration time; FastMCP "
            "executes synchronous callables through its AnyIO worker-thread boundary."
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
            f"{result['status']} — {result['sync_tool_count']} sync tools, "
            f"{result['async_tool_count']} async tools"
        )
        for reason in result["reasons"]:
            print(f"- {reason}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
