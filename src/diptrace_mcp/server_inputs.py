from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Annotated, Any, Literal, cast

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .error_boundary import (
    ToolBodyFailure,
    capture_tool_failures,
    error_result_to_mcp_result,
    exception_to_error_result,
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
# Repeated in ~70 tool descriptions: every character here costs ~70 in tools/list.
DISTANCE_UNITS_DESCRIPTION = "Distances are mm, regardless of the document Units attribute."
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
SchematicEnsembleConfigInput = Annotated[
    dict[str, object],
    Field(
        json_schema_extra={
            "x-diptrace-schema": f"{_INPUT_SCHEMA_RESOURCE}#/schematic_ensemble_config"
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
    "rank_schematic_placement_candidates",
    "route_connections",
    "set_panelization",
    "stage_operations",
    "sync_schematic_to_pcb",
}
_DRY_RUN_DESCRIPTION = (
    "dry_run=true only previews; write with dry_run=false after reviewing it, "
    "passing its expected_sha256."
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
_SCHEMA_VALUE_KEYWORDS = frozenset({"default", "examples", "const", "enum"})


def _compact_schema(schema: Any, *, collapse_nullable: bool) -> Any:
    """Shrink pydantic JSON schema noise that clients pay for on every session.

    Auto ``title`` annotations repeat the property name (~20% of tools/list).
    With ``collapse_nullable``, an optional ``X | None = None`` becomes plain
    ``X``: omitting it already means None, and arguments are validated by the
    pydantic signature, not this schema. Output schemas keep their null
    branches because the SDK validates structured results against them. Value
    keywords are copied verbatim.
    """

    if isinstance(schema, list):
        return [_compact_schema(item, collapse_nullable=collapse_nullable) for item in schema]
    if not isinstance(schema, dict):
        return schema
    compact = {
        key: (
            value
            if key in _SCHEMA_VALUE_KEYWORDS
            else _compact_schema(value, collapse_nullable=collapse_nullable)
        )
        for key, value in schema.items()
        if not (key == "title" and isinstance(value, str))
    }
    branches = compact.get("anyOf")
    if (
        collapse_nullable
        and "default" in compact
        and compact["default"] is None
        and isinstance(branches, list)
        and {"type": "null"} in branches
    ):
        kept = [branch for branch in branches if branch != {"type": "null"}]
        del compact["default"], compact["anyOf"]
        if len(kept) == 1 and isinstance(kept[0], dict):
            # Outer annotations (description) win over the branch's.
            compact = {**kept[0], **compact}
        else:
            compact["anyOf"] = kept
    return compact


def _finalize_listed_tool(tool: types.Tool) -> types.Tool:
    """Compact schemas and add shared disclosures to one tools/list entry."""

    input_schema = _compact_schema(tool.inputSchema, collapse_nullable=True)
    property_names = _schema_property_names(input_schema)
    properties = input_schema.get("properties", {})
    has_selector = "selector" in properties
    has_geometric_input = (
        has_selector
        or tool.name in _GENERIC_SCHEMA_TOOLS
        or any(
            name in _GEOMETRIC_FIELD_NAMES or name.endswith("_mm") for name in property_names
        )
    )
    description = (tool.description or "").strip()
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
    if "dry_run" in properties and _DRY_RUN_DESCRIPTION not in description:
        description = f"{description} {_DRY_RUN_DESCRIPTION}".strip()
    return tool.model_copy(
        update={
            "description": description,
            "inputSchema": input_schema,
            "outputSchema": (
                None
                if tool.outputSchema is None
                else _compact_schema(tool.outputSchema, collapse_nullable=False)
            ),
        }
    )


class DipTraceFastMCP(FastMCP):
    """FastMCP with the project boundary attached only through public overrides.

    Tool bodies are wrapped before registration, tools/list is finalized on
    the listed copies, and ``call_tool`` maps every failure to the stable
    envelope. No SDK-owned tool, metadata or manager object is mutated.
    """

    def __init__(self, *args: Any, version: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # FastMCP v1 has no version argument; without this the initialize
        # handshake reports the MCP SDK's own version as the server version.
        self._mcp_server.version = version
        self.prompt_names: list[str] = []

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
        register = super().tool(*args, **kwargs)

        def decorator(function: Any) -> Any:
            register(capture_tool_failures(function))
            return function

        return decorator

    def prompt(self, name: str | None = None, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
        register = super().prompt(name, *args, **kwargs)

        def decorator(function: Any) -> Any:
            self.prompt_names.append(name or function.__name__)
            return register(function)

        return decorator

    async def list_tools(self) -> list[types.Tool]:
        return [_finalize_listed_tool(tool) for tool in await super().list_tools()]

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[types.ContentBlock] | dict[str, Any]:
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            cause = exc.__cause__
            failure: BaseException
            if isinstance(cause, ToolBodyFailure):
                failure = cause.original
            elif isinstance(cause, ValidationError):
                # Arguments are validated before the body runs; any other model
                # is FastMCP converting a body's successful return value.
                failure = (
                    cause
                    if cause.title == f"{name}Arguments"
                    else InternalStateError("MCP tool output conversion failed", cause=cause)
                )
            elif cause is None:
                raise  # unknown tool: the SDK reports it as a protocol-level error
            else:
                failure = cause
            if not isinstance(failure, (DipTraceMcpError, ValidationError)):
                logger.error("Unexpected failure in MCP tool %s", name, exc_info=failure)
            # The lowlevel server passes a CallToolResult through untouched, so
            # the narrower declared return type of the SDK method is satisfied in
            # practice; mypy needs the cast.
            return cast(
                "Sequence[types.ContentBlock] | dict[str, Any]",
                error_result_to_mcp_result(exception_to_error_result(failure)),
            )
