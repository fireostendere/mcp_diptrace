from __future__ import annotations

from typing import get_args

from diptrace_mcp.domain import FieldSolverRequest, ImpedanceInput, QuerySelector
from diptrace_mcp.operations import (
    AddTestpointOperation,
    OperationKind,
    SetPanelizationOperation,
    TracePathPoint,
    WirePathPoint,
    semantic_operation_kinds,
)
from diptrace_mcp.placement import PlacementConfig, PlacementProposal
from diptrace_mcp.routing import DifferentialPairRouteConfig, RouteConnectionConfig
from diptrace_mcp.scaffolding import (
    DEFAULT_FORMAT_VERSION,
    FORMAT_VERSION_DESCRIPTION,
    MAX_FORMAT_VERSION_LENGTH,
    PcbScaffold,
)
from diptrace_mcp.server import (
    _DRY_RUN_DESCRIPTION,
    DISTANCE_UNITS_DESCRIPTION,
    ImpedanceConstraintInput,
    create_server,
)
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement


def test_stage_operation_kind_schema_matches_parser_registry() -> None:
    registry_kinds = set(semantic_operation_kinds())
    assert len(registry_kinds) == 39
    assert set(get_args(OperationKind)) == registry_kinds

    stage_tool = create_server()._tool_manager._tools["stage_operations"]
    staged_definition = stage_tool.parameters["$defs"]["StagedOperationInput"]
    assert set(staged_definition["properties"]["kind"]["enum"]) == registry_kinds


def test_document_creation_schema_exposes_honest_format_version_control() -> None:
    server = create_server()

    for name in ("create_schematic_document", "create_pcb_document"):
        schema = server._tool_manager._tools[name].parameters["properties"]["format_version"]
        assert schema["default"] == DEFAULT_FORMAT_VERSION
        assert schema["minLength"] == 1
        assert schema["maxLength"] == MAX_FORMAT_VERSION_LENGTH
        assert schema["description"] == FORMAT_VERSION_DESCRIPTION

    seed_properties = server._tool_manager._tools["create_document_from_seed"].parameters[
        "properties"
    ]
    assert "format_version" not in seed_properties


def test_impedance_constraint_preserves_explicit_width() -> None:
    constraint = ImpedanceConstraintInput(
        net="USB_D+",
        layer="Top",
        target_ohm=50.0,
        width_mm=0.18,
    )

    assert constraint.model_dump()["width_mm"] == 0.18
    assert (
        constraint.model_json_schema()["properties"]["width_mm"]["description"]
        == "Distance in millimetres."
    )


def test_query_selector_schema_publishes_exact_spatial_shapes() -> None:
    schema = QuerySelector.model_json_schema()

    bbox = schema["$defs"]["SelectorBBox"]
    near = schema["$defs"]["SelectorNear"]
    assert set(bbox["properties"]) == {"min_x", "min_y", "max_x", "max_y"}
    assert set(bbox["required"]) == set(bbox["properties"])
    assert set(near["properties"]) == {"x", "y"}
    assert set(near["required"]) == set(near["properties"])


def _property_names(value: object) -> set[str]:
    if isinstance(value, dict):
        names = set(value.get("properties", {}))
        for child in value.values():
            names.update(_property_names(child))
        return names
    if isinstance(value, list):
        names: set[str] = set()
        for child in value:
            names.update(_property_names(child))
        return names
    return set()


def test_geometric_tool_descriptions_disclose_millimetre_normalization() -> None:
    geometric_names = {
        "absolute_x",
        "absolute_y",
        "board_edge_clearance",
        "clearance",
        "differential_gap",
        "dx",
        "dy",
        "fixed_length",
        "font_width",
        "gap",
        "grid",
        "grid_snap",
        "hole_diameter",
        "length_delta",
        "max_distance",
        "max_uncoupled_length",
        "max_width",
        "min_width",
        "neck_width",
        "pad_diameter",
        "probe_diameter",
        "spacing",
        "width",
        "x",
        "y",
    }
    generic_geometric_tools = {
        "analyze_routing_congestion",
        "create_pcb_document",
        "route_connections",
        "set_panelization",
        "stage_operations",
        "sync_schematic_to_pcb",
    }
    server = create_server()
    checked: set[str] = set()
    for name, tool in server._tool_manager._tools.items():
        top_level = set(tool.parameters.get("properties", {}))
        properties = _property_names(tool.parameters)
        if (
            "selector" in top_level
            or name in generic_geometric_tools
            or any(field in geometric_names or field.endswith("_mm") for field in properties)
        ):
            checked.add(name)
            assert DISTANCE_UNITS_DESCRIPTION in (tool.description or ""), name
    assert {
        "query_objects",
        "stage_operations",
        "add_wire",
        "route_diff_pair",
        "calculate_impedance",
    } <= checked


def test_every_write_tool_description_discloses_dry_run_contract() -> None:
    server = create_server()
    write_tools = {
        name
        for name, tool in server._tool_manager._tools.items()
        if "dry_run" in tool.parameters.get("properties", {})
    }

    assert len(write_tools) == 53
    for name in write_tools:
        tool = server._tool_manager._tools[name]
        assert _DRY_RUN_DESCRIPTION in (tool.description or ""), name
        assert "expected_sha256" in tool.parameters["properties"], name


def test_geometric_input_models_describe_distance_fields() -> None:
    expected_fields = {
        AddTestpointOperation: {"x", "y", "pad_diameter", "hole_diameter"},
        ComponentSyncMapping: {"x", "y"},
        DifferentialPairRouteConfig: {
            "width",
            "gap",
            "clearance",
            "grid",
            "endpoint_tolerance",
        },
        FieldSolverRequest: {
            "width_mm",
            "copper_thickness_mm",
            "lower_dielectric_height_mm",
            "upper_dielectric_height_mm",
            "trace_length_mm",
        },
        ImpedanceInput: {
            "width_mm",
            "copper_thickness_mm",
            "dielectric_height_mm",
            "gap_mm",
        },
        PcbScaffold: {"width_mm", "height_mm", "trace_width_mm", "clearance_mm"},
        PlacementConfig: {"grid", "spacing", "board_edge_clearance"},
        PlacementProposal: {"x", "y"},
        RouteConnectionConfig: {"width", "clearance", "grid"},
        SetPanelizationOperation: {"column_spacing", "row_spacing", "tab_width"},
        SyncPlacement: {"origin_x", "origin_y", "pitch_x", "pitch_y"},
        TracePathPoint: {"x", "y", "width"},
        WirePathPoint: {"x", "y"},
    }
    for model, field_names in expected_fields.items():
        properties = model.model_json_schema()["properties"]
        for field_name in field_names:
            assert "millimetres" in properties[field_name]["description"], (
                model.__name__,
                field_name,
            )
