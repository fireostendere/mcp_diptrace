from __future__ import annotations

import asyncio
import json
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
            assert "run_openems_stripline_analysis" in tool_names
            board_schema = next(
                tool.inputSchema for tool in tools.tools if tool.name == "get_board_model"
            )
            assert "cutouts" in board_schema["properties"]["section"]["enum"]
            assert board_schema["properties"]["offset"]["minimum"] == 0
            assert board_schema["properties"]["limit"]["maximum"] == 500

            result = await session.call_tool("summarize_design", {"path": "pcb.xml"})
            assert not result.isError
            assert result.structuredContent is not None
            assert result.structuredContent["kind"] == "pcb"
            assert result.structuredContent["component_count"] == 2

            caps = await session.call_tool("get_capabilities", {"path": "pcb.xml"})
            assert not caps.isError
            assert caps.structuredContent["read_capabilities"]["board_model"] is True

            board = await session.call_tool(
                "get_board_model",
                {"path": "pcb.xml", "section": "traces", "limit": 1},
            )
            assert not board.isError
            assert board.structuredContent["ok"] is True
            assert board.structuredContent["result"]["items"][0]["kind"] == "trace"
            assert board.structuredContent["result"]["page"]["returned_count"] == 1

            raw_preview = await session.call_tool(
                "apply_xml_edits",
                {
                    "path": "pcb.xml",
                    "edits": [
                        {
                            "operation": "set_text",
                            "xpath": "./Board/Components/Component[@Id='0']/Value",
                            "value": "47k",
                            "expected_matches": 1,
                        }
                    ],
                },
            )
            assert not raw_preview.isError
            diff_metadata = raw_preview.structuredContent["diff"]
            assert diff_metadata["inline"] is False
            raw_diff = await session.read_resource(diff_metadata["resource_uri"])
            assert "+        <Value>47k</Value>" in raw_diff.contents[0].text
            assert raw_diff.contents[0].mimeType == "text/plain"

            impedance = await session.call_tool(
                "validate_impedance_constraints",
                {
                    "path": "diff_pair_pcb.xml",
                    "constraints": [
                        {
                            "net": "USB_D+",
                            "layer": "0",
                            "target_ohm": 75.0,
                            "tolerance_ohm": 1.0,
                            "width_mm": 0.18,
                        }
                    ],
                },
            )
            assert not impedance.isError
            estimate = impedance.structuredContent["result"]["items"][0]["estimates"][0]
            assert estimate["inputs"]["width_mm"] == 0.18

            resources = await session.list_resources()
            assert {str(item.uri) for item in resources.resources} == {
                "diptrace://status",
                "diptrace://capabilities",
                "diptrace://trusted-provenance-registry",
                "diptrace://schemas/tool-inputs",
            }
            registry_resource = await session.read_resource(
                "diptrace://trusted-provenance-registry"
            )
            registry = json.loads(registry_resource.contents[0].text)
            assert registry["trusted_entry_count"] == 0
            assert registry["high_trust_currently_available"] is False
            assert (
                caps.structuredContent["trust_model"]["trusted_registry"][
                    "trusted_entry_count"
                ]
                == 0
            )
            schema_resource = await session.read_resource("diptrace://schemas/tool-inputs")
            schemas = json.loads(schema_resource.contents[0].text)
            assert "max_distance" in schemas["query_selector"]["properties"]
            assert "kind" in schemas["panelization"]["properties"]
            templates = await session.list_resource_templates()
            template_uris = {item.uriTemplate for item in templates.resourceTemplates}
            assert "diptrace://document/{document_id}/board-model" in template_uris
            assert "diptrace://document/{document_id}/connectivity" in template_uris
            assert "diptrace://transaction/{txid}/preview.json" in template_uris
            assert "diptrace://raw-preview/{preview_id}/diff" in template_uris
            raw_preview_template = next(
                item
                for item in templates.resourceTemplates
                if item.uriTemplate == "diptrace://raw-preview/{preview_id}/diff"
            )
            assert raw_preview_template.mimeType == "text/plain"
            assert "diptrace://plan/{plan_id}/preview.svg" in template_uris
            assert "diptrace://export/{export_id}/{artifact}" in template_uris
            assert "diptrace://job/{jobid}/field_solver_result.json" in template_uris

            prompts = await session.list_prompts()
            prompt_names = {item.name for item in prompts.prompts}
            assert prompt_names == {
                "review_diptrace_design",
                "review_board_before_release",
                "review_schematic_before_layout",
                "place_selected_components_safely",
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
                "synchronize_schematic_to_pcb",
            }
            assert all(item.description for item in prompts.prompts)
            assert {
                item["name"]
                for item in caps.structuredContent["workflow_prompts"]
            } == prompt_names

            prompt = await session.get_prompt(
                "review_board_before_release",
                {"scope": "selected power stage"},
            )
            assert "Review scope: selected power stage" in prompt.messages[0].content.text

    asyncio.run(verify())


def test_http_host_and_port_are_applied_at_server_construction(tmp_path: Path) -> None:
    settings = Settings(
        workspace=FIXTURES,
        allowed_roots=(FIXTURES,),
        state_dir=tmp_path,
    )

    server = create_server(settings, host="0.0.0.0", port=9187)

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 9187
