from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from diptrace_mcp.domain import (
    FieldSolverRequest,
    ImpedanceInput,
    QueryRequest,
    QuerySelector,
)
from diptrace_mcp.operations import (
    AddTestpointOperation,
    MoveComponentsOperation,
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
from diptrace_mcp.silkscreen import SilkscreenPlanConfig
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement

ROOT = Path(__file__).resolve().parents[1]


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
    max_distance = schema["properties"]["max_distance"]
    assert max_distance["anyOf"][0]["minimum"] == 0.0
    assert "both fields are required together" in schema["properties"]["near"]["description"]


@pytest.mark.parametrize(
    "payload",
    [
        {"near": {"x": 0.0, "y": 0.0}},
        {"max_distance": 1.0},
        {"near": {"x": 0.0, "y": 0.0}, "max_distance": math.inf},
        {"near": {"x": 0.0, "y": 0.0}, "max_distance": math.nan},
    ],
)
def test_query_selector_refuses_unbounded_or_nonfinite_near(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        QuerySelector.model_validate(payload)


def test_query_selector_accepts_bounded_near() -> None:
    selector = QuerySelector.model_validate({"near": {"x": 1.0, "y": 2.0}, "max_distance": 0.5})
    assert selector.max_distance == 0.5


def test_query_selector_accepts_zero_radius_for_exact_point_matching() -> None:
    selector = QuerySelector.model_validate(
        {"near": {"x": 1.0, "y": 2.0}, "max_distance": 0.0}
    )
    assert selector.max_distance == 0.0


def test_unbounded_near_is_rejected_by_every_nested_selector_consumer() -> None:
    selector = {"near": {"x": 1.0, "y": 2.0}}
    payloads = [
        (QueryRequest, {"selector": selector}),
        (MoveComponentsOperation, {"selector": selector, "dx": 1.0}),
        (PlacementConfig, {"selector": selector}),
        (SilkscreenPlanConfig, {"selector": selector}),
    ]

    for model, payload in payloads:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_move_components_rejects_removed_noop_anchor_field() -> None:
    with pytest.raises(ValidationError):
        MoveComponentsOperation.model_validate({"dx": 1.0, "anchor": "origin"})


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


def _schema_resource_references(value: object) -> set[str]:
    if isinstance(value, dict):
        references = {
            str(value["x-diptrace-schema"])
            for key in ("x-diptrace-schema",)
            if key in value
        }
        for child in value.values():
            references.update(_schema_resource_references(child))
        return references
    if isinstance(value, list):
        references: set[str] = set()
        for child in value:
            references.update(_schema_resource_references(child))
        return references
    return set()


def test_schema_backed_object_inputs_are_typed_without_inlining_large_models() -> None:
    server = create_server()
    selector_tools = {
        name
        for name, tool in server._tool_manager._tools.items()
        if "selector" in tool.parameters.get("properties", {})
    }
    assert len(selector_tools) == 37
    for name in selector_tools:
        selector = server._tool_manager._tools[name].parameters["properties"]["selector"]
        assert _schema_resource_references(selector) == {
            "diptrace://schemas/tool-inputs#/query_selector"
        }, name

    expected = {
        ("sync_schematic_to_pcb", "component_mappings"): "component_sync_mapping",
        ("sync_schematic_to_pcb", "placement"): "sync_placement",
        ("create_pcb_document", "pcb"): "pcb_scaffold",
        ("set_panelization", "panel"): "panelization",
        ("route_connections", "connections"): "route_connection",
        ("analyze_routing_congestion", "connections"): "route_connection",
    }
    for (tool_name, parameter_name), fragment in expected.items():
        parameter = server._tool_manager._tools[tool_name].parameters["properties"][
            parameter_name
        ]
        assert _schema_resource_references(parameter) == {
            f"diptrace://schemas/tool-inputs#/{fragment}"
        }


def test_public_tool_parameters_do_not_fall_back_to_dict_str_any() -> None:
    tree = ast.parse((ROOT / "src" / "diptrace_mcp" / "server.py").read_text())
    untyped: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_tool = any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
        if not is_tool:
            continue
        arguments = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        for argument in arguments:
            annotation = ast.unparse(argument.annotation) if argument.annotation else ""
            if "dict[str, Any]" in annotation:
                untyped.append(f"{node.name}.{argument.arg}")
    assert untyped == []


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

    assert len(write_tools) == 54
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
