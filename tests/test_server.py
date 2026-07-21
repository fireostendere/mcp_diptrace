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
            assert "get_capabilities" in tool_names
            assert "get_connectivity_graph" in tool_names
            assert "begin_transaction" in tool_names
            assert "move_components" in tool_names
            assert "plan_silkscreen" in tool_names
            assert "apply_silkscreen_plan" in tool_names
            assert "analyze_placement" in tool_names
            assert "generate_placement_candidates" in tool_names
            assert "plan_component_placement" in tool_names
            assert "score_placement" in tool_names
            assert "apply_component_placement_plan" in tool_names
            assert "sync_schematic_to_pcb" in tool_names
            assert "analyze_routing_congestion" in tool_names
            assert "add_trace" in tool_names
            assert "replace_trace" in tool_names
            assert "delete_trace" in tool_names
            assert "set_trace_width" in tool_names
            assert "add_via" in tool_names
            assert "move_via" in tool_names
            assert "delete_via" in tool_names
            assert "set_via_style" in tool_names
            assert "list_unrouted_connections" in tool_names
            assert "get_route_details" in tool_names
            assert "route_connection" in tool_names
            assert "route_net" in tool_names
            assert "route_diff_pair" in tool_names
            assert "plan_diff_pair_route" in tool_names
            assert "plan_route_nets" in tool_names
            assert "apply_route_plan" in tool_names
            assert "export_bom" in tool_names
            assert "export_fabrication_outputs" in tool_names
            assert "export_assembly_outputs" in tool_names
            assert "list_exports" in tool_names

            result = await session.call_tool("summarize_design", {"path": "pcb.xml"})
            assert not result.isError
            assert result.structuredContent is not None
            assert result.structuredContent["kind"] == "pcb"
            assert result.structuredContent["component_count"] == 2

            caps = await session.call_tool("get_capabilities", {"path": "pcb.xml"})
            assert not caps.isError
            assert caps.structuredContent["read_capabilities"]["board_model"] is True

            board = await session.call_tool("get_board_model", {"path": "pcb.xml"})
            assert not board.isError
            assert board.structuredContent["ok"] is True
            assert board.structuredContent["result"]["traces"][0]["kind"] == "trace"

            resources = await session.list_resources()
            assert {str(item.uri) for item in resources.resources} == {
                "diptrace://status",
                "diptrace://capabilities",
            }
            templates = await session.list_resource_templates()
            template_uris = {item.uriTemplate for item in templates.resourceTemplates}
            assert "diptrace://document/{document_id}/board-model" in template_uris
            assert "diptrace://document/{document_id}/connectivity" in template_uris
            assert "diptrace://transaction/{txid}/preview.json" in template_uris
            assert "diptrace://plan/{plan_id}/preview.svg" in template_uris
            assert "diptrace://export/{export_id}/{artifact}" in template_uris

            prompts = await session.list_prompts()
            prompt_names = {item.name for item in prompts.prompts}
            assert {
                "review_board_before_release",
                "place_decoupling_network",
                "route_critical_net",
                "route_diff_pair_with_constraints",
                "clean_silkscreen_for_manufacturing",
                "add_testpoints_for_fixture",
                "review_return_paths",
                "prepare_fabrication_export",
                "prepare_assembly_export",
                "review_bom",
                "compare_schematic_and_pcb",
            } <= prompt_names

    asyncio.run(verify())
