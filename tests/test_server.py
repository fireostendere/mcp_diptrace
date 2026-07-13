from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"


def test_mcp_protocol_lists_and_calls_tools(tmp_path: Path) -> None:
    async def verify() -> None:
        settings = Settings(
            workspace=FIXTURES,
            allowed_roots=(FIXTURES,),
            state_dir=tmp_path,
        )
        server = create_server(settings)
        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=5),
        ) as session:
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "summarize_design" in tool_names
            assert "apply_xml_edits" in tool_names

            result = await session.call_tool("summarize_design", {"path": "pcb.xml"})
            assert not result.isError
            assert result.structuredContent is not None
            assert result.structuredContent["kind"] == "pcb"
            assert result.structuredContent["component_count"] == 2

    asyncio.run(verify())
