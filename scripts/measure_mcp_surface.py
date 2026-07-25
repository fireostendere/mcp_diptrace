from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server


async def _measure(
    *,
    baseline_bytes: int | None,
    max_growth_percent: float,
) -> None:
    workspace = (Path(__file__).parents[1] / "tests" / "fixtures").resolve()
    with tempfile.TemporaryDirectory() as state_dir:
        server = create_server(
            Settings(
                workspace=workspace,
                allowed_roots=(workspace,),
                state_dir=Path(state_dir),
            )
        )
        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=30),
        ) as session:
            tools = await session.list_tools()
            payload = json.dumps(
                [
                    {
                        "n": tool.name,
                        "d": tool.description,
                        "s": tool.inputSchema,
                    }
                    for tool in tools.tools
                ]
            )
            print(
                f"tools={len(tools.tools)} bytes={len(payload)} "
                f"approx_tokens={len(payload) // 4}"
            )
            if baseline_bytes is not None:
                growth_percent = (len(payload) - baseline_bytes) / baseline_bytes * 100.0
                print(
                    f"baseline_bytes={baseline_bytes} "
                    f"growth_percent={growth_percent:.4f}"
                )
                if growth_percent > max_growth_percent:
                    raise SystemExit(
                        f"FAIL: tools/list grew by {growth_percent:.4f}% "
                        f"(limit {max_growth_percent:.4f}%)"
                    )
            for arguments in ({}, {"path": str(workspace / "pcb.xml")}):
                result = await session.call_tool("get_capabilities", arguments)
                structured = result.structuredContent or {}
                trust_model = structured.get("trust_model") or {}
                print(
                    f"get_capabilities({','.join(arguments) or 'no_path'}) "
                    f"trust_model_keys={len(trust_model)}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the concrete MCP discovery surface")
    parser.add_argument("--baseline-bytes", type=int)
    parser.add_argument("--max-growth-percent", type=float, default=15.0)
    args = parser.parse_args()
    if args.baseline_bytes is not None and args.baseline_bytes <= 0:
        parser.error("--baseline-bytes must be positive")
    if args.max_growth_percent < 0:
        parser.error("--max-growth-percent must be non-negative")
    asyncio.run(
        _measure(
            baseline_bytes=args.baseline_bytes,
            max_growth_percent=args.max_growth_percent,
        )
    )


if __name__ == "__main__":
    main()
