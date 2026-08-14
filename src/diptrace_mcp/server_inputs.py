from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, cast

from mcp import types
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .error_boundary import (
    error_result_to_mcp_result,
    exception_to_error_result,
    wrap_tool_callable,
)
from .errors import DipTraceMcpError, InternalStateError
from .scaffolding import (
    FORMAT_VERSION_DESCRIPTION,
    MAX_FORMAT_VERSION_LENGTH,
)

logger = logging.getLogger(__name__)
class XmlEditInput(BaseModel):
    operation: Literal[
        "set_text",
        "set_attribute",
        "remove_attribute",
        "append_xml",
        "replace_xml",
        "delete_element",
    ]
    xpath: str = Field(min_length=1, max_length=512)
    value: str | None = None
    attribute: str | None = None
    expected_matches: int = Field(default=1, ge=1, le=1000)
class ExternalBomRecordInput(BaseModel):
    """Flexible external BOM row with typed identity fields."""

    model_config = ConfigDict(extra="allow")

    refdes: str | list[str]
    value: str = ""
    pattern: str = ""
    manufacturer: str = ""
    mpn: str = ""
class ImpedanceConstraintInput(BaseModel):
    """Explicit controlled-impedance target for one net and layer."""

    net: str = Field(min_length=1, max_length=1_000)
    layer: str = Field(min_length=1, max_length=256)
    target_ohm: float = Field(gt=0.0, allow_inf_nan=False)
    tolerance_ohm: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    width_mm: float | None = Field(
        default=None,
        gt=0.0,
        allow_inf_nan=False,
        description="Distance in millimetres.",
    )
class EvidenceRoleInput(BaseModel):
    """One SHA-bound file role in operator-supplied evidence."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        min_length=1,
        max_length=4_096,
        description="Existing evidence file inside an allowed root.",
    )
    sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Expected lowercase SHA-256 of the exact evidence file bytes.",
    )
class RoundtripEvidenceInput(BaseModel):
    """Distinct source, saved, and optional re-export evidence roles."""

    model_config = ConfigDict(extra="forbid")

    source: EvidenceRoleInput = Field(
        description="File exported before the operator's DipTrace open/save action."
    )
    saved: EvidenceRoleInput = Field(
        description="File saved by DipTrace after opening the source."
    )
    reexport: EvidenceRoleInput | None = Field(
        default=None,
        description=(
            "Optional independent re-export used for structural semantic comparison. "
            "Omit it for an open/save-only observation."
        ),
    )
class FinishLiveSessionResult(BaseModel):
    """Bounded local bridge-finalization outcome; never a DipTrace host ACK."""

    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str
    requested_action: Literal["apply", "cancel"]
    requested_at: str
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["applied", "cancelled", "not_acknowledged"]
    local_bridge_status: Literal["active", "applied", "cancelled", "abandoned"]
    written: bool
    diptrace_host_acknowledged: Literal[False]
    acknowledgement_scope: Literal["local_bridge_exchange_only"]
    message: str
class AbandonLiveSessionResult(BaseModel):
    """Bounded result for a local, non-writing abandonment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str
    outcome: Literal["abandoned"]
    local_bridge_status: Literal["abandoned"]
    written: Literal[False]
    reason: str
    diptrace_host_acknowledged: Literal[False]
    acknowledgement_scope: Literal["local_session_state_only"]
    message: str
DISTANCE_UNITS_DESCRIPTION = (
    "All distances are in millimetres, regardless of the document's own Units attribute."
)
_INPUT_SCHEMA_RESOURCE = "diptrace://schemas/tool-inputs"
FormatVersionInput = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_FORMAT_VERSION_LENGTH,
        description=FORMAT_VERSION_DESCRIPTION,
    ),
]
ExpectedTargetSha256Input = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "Current SHA-256 of the existing target. Required with overwrite=true only "
            "when the target already exists; obtain it by reading that target first."
        ),
    ),
]
ExpectedLiveWorkingSha256Input = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "SHA-256 of the latest working XML inspected by the caller. Required when "
            "action=apply; the service checks it before publishing the bridge control "
            "request and the bridge checks it again immediately before replacement."
        ),
    ),
]
class SchematicRepairMoveInput(BaseModel):
    """One operator-directed part move for schematic placement repair planning."""

    part: str = Field(
        min_length=1,
        max_length=256,
        description="Part reference designator or stable object identifier.",
    )
    x_mm: float = Field(allow_inf_nan=False, description="Target X position in millimetres.")
    y_mm: float = Field(allow_inf_nan=False, description="Target Y position in millimetres.")


SelectorInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/query_selector"
        }
    ),
]
ComponentSyncMappingInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": (
                f"{_INPUT_SCHEMA_RESOURCE}#/component_sync_mapping"
            )
        }
    ),
]
SyncPlacementInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/sync_placement"
        }
    ),
]
PcbScaffoldInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/pcb_scaffold"
        }
    ),
]
PanelizationInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/panelization"
        }
    ),
]
RouteConnectionInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/route_connection"
        }
    ),
]
_GEOMETRIC_FIELD_NAMES = {
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
    "stitching_radius",
    "width",
    "x",
    "y",
}
_GENERIC_SCHEMA_TOOLS = {
    "analyze_routing_congestion",
    "create_pcb_document",
    "route_connections",
    "set_panelization",
    "stage_operations",
    "sync_schematic_to_pcb",
}
_DRY_RUN_DESCRIPTION = (
    "`dry_run=true` previews without writing. Set `dry_run=false` only after "
    "inspecting the preview and pass its `expected_sha256`."
)
_COMPONENT_ANGLE_CAVEAT = (
    "Component angle semantics have not yet been independently validated against "
    "a live DipTrace GUI edit and re-export. Inspect the transaction preview and "
    "verify the result through DipTrace before relying on rotation changes."
)
_NETCLASS_CLEARANCE_DISCLOSURE = (
    "Clearance resolution applies the maximum of explicit requested clearance, "
    "board DRC TraceToTrace defaults, and all affected NetClass LayProperty "
    "Clearance rules. The structured result includes clearance_rule_status and "
    "the effective value; this is not a full DipTrace DRC sign-off."
)
_CLEARANCE_TOOLS = {
    "route_connection",
    "route_net",
    "route_connections",
    "route_diff_pair",
    "plan_diff_pair_route",
    "analyze_routing_congestion",
}
_COMPATIBILITY_ALIAS_DESCRIPTIONS = {
    "analyze_controlled_impedance": "Alias: validate_impedance_constraints.",
    "check_silkscreen": "Alias: run_silkscreen_check.",
    "legalize_component_placement": "Preset: plan_component_placement.",
    "run_assembly_review": "Assembly review profile.",
    "run_board_review": "Complete registered PCB review profile.",
    "run_bom_review": "BOM review profile.",
    "run_component_clearance_check": "Placement-clearance review profile.",
    "run_connectivity_check": "Connectivity review profile.",
    "run_drc": "PCB placement, connectivity and clearance profile.",
    "run_erc": "Schematic connectivity and metadata profile.",
    "run_manufacturing_geometry_check": "Manufacturing-geometry review profile.",
    "run_manufacturing_review": "Manufacturing review profile.",
    "run_schematic_review": "Complete registered schematic review profile.",
    "run_silkscreen_check": "Silkscreen review profile.",
    "run_testability_review": "Testability review profile.",
    "run_thermal_review": "Thermal-metadata review profile.",
    "set_component_fields": "Custom-field-only component update.",
    "set_diff_pair_rules": "Net-class differential-pair preset.",
    "set_length_constraints": "Net-class length preset.",
    "unlock_components": "Unlock selected components.",
}
def _schema_property_names(schema: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for value in schema.values():
            names.update(_schema_property_names(value))
    elif isinstance(schema, list):
        for value in schema:
            names.update(_schema_property_names(value))
    return names
def _finalize_tool_descriptions(mcp: FastMCP) -> None:
    """Add shared schema and unit disclosures to the concrete MCP surface."""

    for tool in mcp._tool_manager._tools.values():
        property_names = _schema_property_names(tool.parameters)
        has_selector = "selector" in tool.parameters.get("properties", {})
        has_geometric_input = (
            has_selector
            or tool.name in _GENERIC_SCHEMA_TOOLS
            or any(
                name in _GEOMETRIC_FIELD_NAMES or name.endswith("_mm")
                for name in property_names
            )
        )
        description = _COMPATIBILITY_ALIAS_DESCRIPTIONS.get(
            tool.name,
            (tool.description or "").strip(),
        )
        if tool.name == "rotate_components" and _COMPONENT_ANGLE_CAVEAT not in description:
            description = f"{description} {_COMPONENT_ANGLE_CAVEAT}".strip()
        if tool.name in _CLEARANCE_TOOLS and _NETCLASS_CLEARANCE_DISCLOSURE not in description:
            description = f"{description} {_NETCLASS_CLEARANCE_DISCLOSURE}".strip()
        if has_geometric_input and DISTANCE_UNITS_DESCRIPTION not in description:
            description = f"{description} {DISTANCE_UNITS_DESCRIPTION}".strip()
        if (has_selector or tool.name in _GENERIC_SCHEMA_TOOLS) and (
            _INPUT_SCHEMA_RESOURCE not in description
        ):
            description = f"{description} Input schema: {_INPUT_SCHEMA_RESOURCE}.".strip()
        if "dry_run" in tool.parameters.get("properties", {}) and (
            _DRY_RUN_DESCRIPTION not in description
        ):
            description = f"{description} {_DRY_RUN_DESCRIPTION}".strip()
        tool.description = description
        tool.fn = wrap_tool_callable(
            tool.fn,
            tool.name,
            mcp_result=True,
            offload_sync=True,
        )
        if getattr(tool.fn, "__diptrace_mcp_thread_offload__", False):
            object.__setattr__(tool, "is_async", True)

        original_validate = tool.fn_metadata.call_fn_with_arg_validation

        async def validate_with_boundary(
            *args: Any,
            _original_validate: Any = original_validate,
            **kwargs: Any,
        ) -> Any:
            try:
                return await _original_validate(*args, **kwargs)
            except Exception as exc:
                if not isinstance(exc, ValidationError):
                    raise
                return error_result_to_mcp_result(exception_to_error_result(exc))

        object.__setattr__(
            tool.fn_metadata,
            "call_fn_with_arg_validation",
            validate_with_boundary,
        )
        cast(Any, validate_with_boundary).__diptrace_mcp_validation_boundary__ = True

        original_run = tool.run

        async def run_with_boundary(
            *args: Any,
            _original_run: Any = original_run,
            _metadata: Any = tool.fn_metadata,
            **kwargs: Any,
        ) -> Any:
            try:
                # FastMCP's output conversion validates typed return models.  An
                # error CallToolResult cannot satisfy a successful tool's output
                # schema, so stop conversion at this boundary and pass transport
                # errors through exactly once. Successful values are converted by
                # the same SDK metadata after this check.
                kwargs["convert_result"] = False
                raw_result = await _original_run(*args, **kwargs)
                if isinstance(raw_result, types.CallToolResult):
                    return raw_result
                return _metadata.convert_result(raw_result)
            except Exception as exc:
                if not isinstance(exc, (DipTraceMcpError, ValidationError)):
                    logger.exception("Unexpected MCP tool boundary failure")
                if isinstance(exc, ValidationError):
                    exc = InternalStateError(
                        "MCP tool output conversion failed",
                        cause=exc,
                    )
                return error_result_to_mcp_result(exception_to_error_result(exc))

        cast(Any, run_with_boundary).__diptrace_mcp_run_boundary__ = True
        object.__setattr__(tool, "run", run_with_boundary)
