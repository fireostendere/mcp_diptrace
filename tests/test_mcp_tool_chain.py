from __future__ import annotations

import asyncio
import hashlib
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"


def _copy_synthetic_fixture_workspace(workspace: Path) -> None:
    workspace.mkdir()
    for name in (
        "component_library.xml",
        "diff_pair_pcb.xml",
        "pattern_library.xml",
        "pcb.xml",
        "pcb_4layer.xml",
        "schematic.xml",
    ):
        shutil.copy2(FIXTURES / name, workspace / name)


def test_fixture_workflow_invokes_at_least_forty_public_mcp_tools(
    tmp_path: Path,
) -> None:
    """Exercise a realistic bounded workflow through the public MCP transport."""

    async def verify() -> None:
        workspace = tmp_path / "workspace"
        _copy_synthetic_fixture_workspace(workspace)
        settings = Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=tmp_path / "state",
        )
        server = create_server(settings)
        invoked: set[str] = set()

        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=15),
        ) as session:

            async def invoke(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                assert name not in invoked, (
                    f"tool called twice instead of widening coverage: {name}"
                )
                result = await session.call_tool(name, arguments)
                assert not result.isError, (name, result.content)
                assert isinstance(result.structuredContent, dict), name
                invoked.add(name)
                return result.structuredContent

            status = await invoke("diptrace_status", {})
            assert status["active_session"] is None

            capabilities = await invoke("get_capabilities", {"path": "pcb.xml"})
            assert capabilities["read_capabilities"]["board_model"] is True

            document_info = await invoke("get_document_info", {"path": "pcb.xml"})
            source_sha256 = document_info["result"]["sha256"]
            assert len(source_sha256) == 64

            board_model = await invoke(
                "get_board_model",
                {"path": "pcb.xml", "section": "components", "offset": 0, "limit": 1},
            )
            assert board_model["result"]["page"]["returned_count"] == 1
            assert board_model["result"]["page"]["has_more"] is True

            schematic_model = await invoke(
                "get_schematic_model", {"path": "schematic.xml"}
            )
            assert schematic_model["result"]["sheets"]

            component_libraries = await invoke(
                "scan_component_libraries", {"root": ".", "recursive": True}
            )
            assert component_libraries["result"]["matched_count"] == 1

            pattern_libraries = await invoke(
                "scan_pattern_libraries", {"root": ".", "recursive": True}
            )
            assert pattern_libraries["result"]["matched_count"] == 1

            library_query = await invoke(
                "query_library_items",
                {
                    "path": "component_library.xml",
                    "query": "RES",
                    "offset": 0,
                    "limit": 1,
                },
            )
            assert library_query["result"]["matched_count"] == 1

            library_component = await invoke(
                "get_library_component",
                {"path": "component_library.xml", "name": "RES_0603"},
            )
            assert library_component["result"]["name"] == "RES_0603"

            library_pattern = await invoke(
                "get_library_pattern",
                {"path": "pattern_library.xml", "name": "HDR_1X02"},
            )
            assert library_pattern["result"]["name"] == "HDR_1X02"

            component_validation = await invoke(
                "validate_library_component",
                {"path": "component_library.xml", "name": "RES_0603"},
            )
            assert component_validation["result"]["valid"] is True

            pattern_validation = await invoke(
                "validate_library_pattern",
                {"path": "pattern_library.xml", "name": "HDR_1X02"},
            )
            assert pattern_validation["result"]["valid"] is True

            mapping_validation = await invoke(
                "validate_pin_pad_mapping",
                {"path": "component_library.xml", "name": "RES_0603"},
            )
            assert mapping_validation["result"]["valid"] is True

            bom = await invoke(
                "get_bom",
                {"path": "pcb.xml", "grouped": False, "include_dnp": True},
            )
            assert bom["result"]["record_count"] == 2
            external_bom = [
                {
                    "refdes": item["refdes"],
                    "value": item["value"],
                    "pattern": item["pattern"],
                    "manufacturer": item["manufacturer"],
                    "mpn": item["mpn"],
                }
                for item in bom["result"]["items"]
            ]

            bom_review = await invoke("review_bom", {"path": "pcb.xml"})
            assert bom_review["result"]["items"]

            bom_comparison = await invoke(
                "compare_bom_to_design",
                {"path": "pcb.xml", "external_records": external_bom},
            )
            assert bom_comparison["result"]["missing_external"] == []
            assert bom_comparison["result"]["extra_external"] == []

            missing_fields = await invoke(
                "find_missing_component_fields",
                {"path": "pcb.xml", "required_fields": ["mpn"]},
            )
            assert missing_fields["result"]["record_count"] == 2

            grouped_bom = await invoke(
                "group_bom", {"path": "pcb.xml", "include_dnp": True}
            )
            assert grouped_bom["result"]["grouped"] is True

            duplicate_bom = await invoke(
                "detect_duplicate_bom_items", {"path": "pcb.xml"}
            )
            assert "duplicate_group_count" in duplicate_bom["result"]

            mpn_consistency = await invoke(
                "validate_mpn_consistency", {"path": "pcb.xml"}
            )
            assert isinstance(mpn_consistency["result"]["valid"], bool)

            value_pattern_consistency = await invoke(
                "validate_value_pattern_consistency", {"path": "pcb.xml"}
            )
            assert isinstance(value_pattern_consistency["result"]["valid"], bool)

            design_comparison = await invoke(
                "compare_schematic_to_pcb",
                {"schematic_path": "schematic.xml", "pcb_path": "pcb.xml"},
            )
            assert design_comparison["result"]["pcb_document"]["kind"] == "pcb"

            bom_export = await invoke(
                "export_bom", {"path": "pcb.xml", "include_dnp": True}
            )
            fabrication_export = await invoke(
                "export_fabrication_outputs",
                {
                    "path": "pcb.xml",
                    "include_dnp": True,
                    "request_native_outputs": False,
                },
            )
            assembly_export = await invoke(
                "export_assembly_outputs",
                {
                    "path": "pcb.xml",
                    "include_dnp": False,
                    "request_native_outputs": False,
                },
            )
            export_ids = {
                response["result"]["export"]["export_id"]
                for response in (bom_export, fabrication_export, assembly_export)
            }
            assert len(export_ids) == 3
            assert all(response["resources"] for response in (bom_export, fabrication_export))

            listed_exports = await invoke("list_exports", {})
            assert {
                item["export_id"] for item in listed_exports["result"]["exports"]
            } == export_ids

            objects = await invoke(
                "query_objects",
                {
                    "path": "pcb.xml",
                    "selector": {"kinds": ["component"]},
                    "offset": 0,
                    "limit": 1,
                    "sort_by": "stable_id",
                },
            )
            assert objects["result"]["items"]
            stable_id = objects["result"]["items"][0]["stable_id"]

            selected_object = await invoke(
                "get_object", {"path": "pcb.xml", "stable_id": stable_id}
            )
            assert selected_object["result"]["stable_id"] == stable_id

            connectivity = await invoke(
                "get_connectivity_graph", {"path": "pcb.xml"}
            )
            assert connectivity["result"]["nets"]

            scanned = await invoke(
                "scan_diptrace_documents", {"root": ".", "recursive": True}
            )
            assert len(scanned["documents"]) >= 4

            summary = await invoke("summarize_design", {"path": "pcb.xml"})
            assert summary["kind"] == "pcb"

            components = await invoke(
                "list_components",
                {"path": "pcb.xml", "offset": 0, "limit": 1},
            )
            assert components["items"][0]["refdes"] == "R1"

            component = await invoke(
                "get_component", {"path": "pcb.xml", "refdes": "R1"}
            )
            assert component["component"]["refdes"] == "R1"

            nets = await invoke(
                "list_nets",
                {
                    "path": "pcb.xml",
                    "include_endpoints": True,
                    "offset": 0,
                    "limit": 10,
                },
            )
            assert {item["name"] for item in nets["items"]} == {"VCC", "SIGNAL"}

            design_rules = await invoke("get_design_rules", {"path": "pcb.xml"})
            assert design_rules["type"] == "DipTrace-PCB"

            xml_fragment = await invoke(
                "read_xml_fragment",
                {
                    "path": "pcb.xml",
                    "xpath": "./Board/Components/Component[@Id='0']",
                    "max_matches": 1,
                    "max_characters": 2_000,
                },
            )
            assert xml_fragment["match_count"] == 1
            assert xml_fragment["truncated"] is False

            board_path = workspace / "pcb.xml"
            before_preview = board_path.read_bytes()
            raw_preview = await invoke(
                "apply_xml_edits",
                {
                    "path": "pcb.xml",
                    "dry_run": True,
                    "expected_sha256": source_sha256,
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
            assert raw_preview["written"] is False
            assert (
                raw_preview["serialized_response_bytes"]
                <= raw_preview["response_byte_limit"]
            )
            assert board_path.read_bytes() == before_preview
            raw_diff = await session.read_resource(raw_preview["diff"]["resource_uri"])
            assert "+        <Value>47k</Value>" in raw_diff.contents[0].text

            begun = await invoke(
                "begin_transaction",
                {
                    "path": "pcb.xml",
                    "expected_sha256": source_sha256,
                    "notes": ["public MCP fixture workflow"],
                },
            )
            txid = begun["transaction"]["txid"]
            staged = await invoke(
                "stage_operations",
                {
                    "txid": txid,
                    "operations": [
                        {
                            "kind": "set_component_value",
                            "selector": {"refdes": ["R1"]},
                            "value": "47k",
                        }
                    ],
                },
            )
            assert staged["result"]["staged_count"] == 1

            preview = await invoke("preview_transaction", {"txid": txid})
            assert preview["written"] is False
            assert preview["preview"]["inline"] is False
            assert "operations" not in preview["transaction"]
            assert set(preview["preview"]["artifacts"]) == {"svg", "json", "diff"}
            transaction_diff = await session.read_resource(
                preview["preview"]["artifacts"]["diff"]["resource_uri"]
            )
            assert "<Value>47k</Value>" in transaction_diff.contents[0].text
            assert board_path.read_bytes() == before_preview

            validated = await invoke("validate_transaction", {"txid": txid})
            assert validated["transaction"]["status"] == "validated"
            assert board_path.read_bytes() == before_preview

            transactions = await invoke("list_transactions", {})
            assert txid in {item["txid"] for item in transactions["transactions"]}

            created_schematic = await invoke(
                "create_schematic_document",
                {
                    "path": "generated_schematic.xml",
                    "sheets": ["Main"],
                    "units": "mm",
                    "overwrite": False,
                },
            )
            assert created_schematic["result"]["created"] is True
            assert (workspace / "generated_schematic.xml").is_file()

            created_pcb = await invoke(
                "create_pcb_document",
                {
                    "path": "generated_pcb.xml",
                    "units": "mm",
                    "overwrite": False,
                },
            )
            assert created_pcb["result"]["created"] is True
            assert (workspace / "generated_pcb.xml").is_file()

            seed_sha256 = hashlib.sha256((workspace / "pcb.xml").read_bytes()).hexdigest()
            copied_seed = await invoke(
                "create_document_from_seed",
                {
                    "seed_path": "pcb.xml",
                    "target_path": "seed_copy.xml",
                    "expected_seed_sha256": seed_sha256,
                    "overwrite": False,
                },
            )
            assert copied_seed["result"]["created"] is True
            assert (workspace / "seed_copy.xml").read_bytes() == before_preview

            board_texts = await invoke("list_board_texts", {"path": "pcb.xml"})
            assert board_texts["result"]["matched_count"] >= 0

            testpoints = await invoke(
                "list_testpoints", {"path": "pcb.xml", "selector": {}}
            )
            assert testpoints["result"]["matched_count"] == 0

            candidates = await invoke(
                "find_testpoint_candidates",
                {
                    "path": "pcb.xml",
                    "target_nets": ["VCC"],
                    "side": "Top",
                    "candidates_per_net": 2,
                },
            )
            assert candidates["result"]["matched_net_count"] == 1
            assert candidates["result"]["candidate_count"] <= 2

            testpoint_coverage = await invoke(
                "review_testpoint_coverage",
                {"path": "pcb.xml", "target_nets": ["VCC"]},
            )
            assert testpoint_coverage["result"]["target_net_count"] == 1

            unrouted = await invoke(
                "list_unrouted_connections", {"path": "pcb.xml", "nets": ["VCC"]}
            )
            assert unrouted["result"]["matched_count"] == 1

            route_details = await invoke(
                "get_route_details", {"path": "pcb.xml", "net": "SIGNAL"}
            )
            assert route_details["result"]["trace_count"] == 1

            stackup = await invoke("get_stackup", {"path": "diff_pair_pcb.xml"})
            assert stackup["result"]["completeness"] == "complete"

            lengths = await invoke(
                "measure_net_lengths",
                {"path": "diff_pair_pcb.xml", "nets": ["USB_D+", "USB_D-"]},
            )
            assert lengths["result"]["matched_count"] == 2

            differential_pairs = await invoke(
                "list_differential_pairs",
                {"path": "diff_pair_pcb.xml", "offset": 0, "limit": 1},
            )
            pair_id = differential_pairs["result"]["items"][0]["stable_id"]

            pair = await invoke(
                "get_differential_pair",
                {"path": "diff_pair_pcb.xml", "pair": pair_id},
            )
            assert pair["result"]["stable_id"] == pair_id

            analyzed_pair = await invoke(
                "analyze_differential_pair",
                {"path": "diff_pair_pcb.xml", "pair": pair_id},
            )
            assert analyzed_pair["result"]["pair_id"] == pair_id

            all_pairs = await invoke(
                "analyze_differential_pairs", {"path": "diff_pair_pcb.xml"}
            )
            assert all_pairs["result"]["matched_count"] == 1

            validated_pair = await invoke(
                "validate_differential_pair",
                {"path": "diff_pair_pcb.xml", "pair": pair_id},
            )
            assert validated_pair["result"]["status"] == "incomplete"

            stackup_impedance = await invoke(
                "analyze_stackup_for_impedance", {"path": "diff_pair_pcb.xml"}
            )
            assert stackup_impedance["result"]["microstrip_candidates"]

            pours = await invoke(
                "list_copper_pours",
                {"path": "diff_pair_pcb.xml", "offset": 0, "limit": 1},
            )
            assert pours["result"]["matched_count"] == 1

            plane = await invoke(
                "analyze_plane_continuity", {"path": "diff_pair_pcb.xml"}
            )
            assert plane["result"]["pour_count"] == 1

            board_review = await invoke("run_board_review", {"path": "pcb.xml"})
            report_id = board_review["result"]["summary"]["report_id"]
            assert report_id.startswith("report_")

            findings = await invoke("get_findings", {"report_id": report_id})
            assert findings["report"]["report_id"] == report_id

            assert len(invoked) >= 40
            assert board_path.read_bytes() == before_preview
            board_page = board_model["result"]["page"]
            assert (
                board_page["serialized_response_bytes"]
                <= board_page["response_byte_limit"]
            )

    asyncio.run(verify())
