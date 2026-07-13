from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server


async def exercise(session: ClientSession, document: str) -> None:
    tools = await session.list_tools()
    result = await session.call_tool("summarize_design", {"path": document})
    if result.isError:
        raise RuntimeError(f"summarize_design failed: {result.content}")
    print(
        json.dumps(
            {
                "tool_count": len(tools.tools),
                "tools": [tool.name for tool in tools.tools],
                "summary": result.structuredContent,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def run_memory(workspace: Path, document: str) -> None:
    with tempfile.TemporaryDirectory(prefix="diptrace-mcp-smoke-") as state_dir:
        settings = Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=Path(state_dir),
        )
        server = create_server(settings)
        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=15),
        ) as session:
            await exercise(session, document)


async def run_stdio(workspace: Path, document: str) -> None:
    with tempfile.TemporaryDirectory(prefix="diptrace-mcp-smoke-") as state_dir:
        environment = os.environ.copy()
        environment["DIPTRACE_MCP_WORKSPACE"] = str(workspace)
        environment["DIPTRACE_MCP_STATE_DIR"] = state_dir
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "diptrace_mcp.server"],
            cwd=str(Path(__file__).parents[1]),
            env=environment,
        )
        async with stdio_client(server) as (read_stream, write_stream), ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=15),
        ) as session:
            await session.initialize()
            await exercise(session, document)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an MCP protocol smoke test")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(__file__).parents[1] / "tests" / "fixtures",
    )
    parser.add_argument("--document", default="pcb.xml")
    parser.add_argument(
        "--transport",
        choices=("memory", "stdio"),
        default="memory",
        help="Use memory for deterministic CI or stdio for a subprocess check",
    )
    args = parser.parse_args()
    run = run_memory if args.transport == "memory" else run_stdio
    asyncio.run(run(args.workspace.resolve(), args.document))


if __name__ == "__main__":
    main()
