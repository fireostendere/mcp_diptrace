from __future__ import annotations

import argparse
import json
import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .config import Settings
from .service import DipTraceService
from .xml_document import XmlEdit


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


def create_server(settings: Settings | None = None) -> FastMCP:
    service = DipTraceService(settings or Settings.from_env())
    mcp = FastMCP(
        name="DipTrace MCP",
        instructions=(
            "Inspect and safely edit DipTrace XML. Without a path, tools use the active live "
            "DipTrace bridge session. Always preview changes with dry_run=true, then repeat with "
            "dry_run=false and the returned before_sha256. Finish live sessions explicitly with "
            "apply or cancel."
        ),
        json_response=True,
    )

    @mcp.tool()
    def diptrace_status() -> dict[str, Any]:
        """Show server paths and the active DipTrace bridge session, if any."""
        return service.status()

    @mcp.tool()
    def scan_diptrace_documents(
        root: str | None = None,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Find DipTrace XML/native-XML documents inside an allowed directory."""
        return service.scan_documents(root, recursive)

    @mcp.tool()
    def summarize_design(path: str | None = None) -> dict[str, Any]:
        """Summarize a PCB or schematic: components, nets, layers, sheets and connectivity."""
        return service.summarize(path)

    @mcp.tool()
    def list_components(
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List and search PCB components or grouped schematic component parts."""
        return service.components(path, query, offset, limit)

    @mcp.tool()
    def get_component(refdes: str, path: str | None = None) -> dict[str, Any]:
        """Get one component, its parts/pads and all connected nets by reference designator."""
        return service.component(refdes, path)

    @mcp.tool()
    def list_nets(
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List PCB or schematic nets with component endpoints."""
        return service.nets(path, query, include_endpoints, offset, limit)

    @mcp.tool()
    def get_design_rules(path: str | None = None) -> dict[str, Any]:
        """Read PCB DRC/routing rules or schematic ERC settings from DipTrace XML."""
        return service.rules(path)

    @mcp.tool()
    def read_xml_fragment(
        xpath: str = ".",
        path: str | None = None,
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        """Read bounded XML fragments using ElementTree-compatible XPath."""
        return service.read_xml(path, xpath, max_matches, max_characters)

    @mcp.tool()
    def apply_xml_edits(
        edits: list[XmlEditInput],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Preview edits, or write them with the preview SHA-256, match guards and backups."""
        operations = [XmlEdit(**edit.model_dump()) for edit in edits]
        return service.apply_edits(operations, path, dry_run, expected_sha256)

    @mcp.tool()
    def finish_live_session(action: Literal["apply", "cancel"]) -> dict[str, Any]:
        """Tell the DipTrace bridge to import working XML or discard the live session."""
        return service.finish_live_session(action)

    @mcp.resource("diptrace://status")
    def status_resource() -> str:
        """Current DipTrace MCP configuration and live-session state."""
        return json.dumps(service.status(), ensure_ascii=False, indent=2)

    @mcp.prompt()
    def review_diptrace_design(scope: str = "full") -> str:
        """Create a safe workflow prompt for reviewing the active DipTrace design."""
        return (
            "Review the active DipTrace design. First call diptrace_status and summarize_design. "
            f"Review scope: {scope}. Inspect components, nets and design rules as needed. Report "
            "findings with exact RefDes/net names. Do not edit unless explicitly requested. "
            "If edits are requested, preview with dry_run=true, explain the diff, then commit "
            "with the returned "
            "before_sha256 and finish the live session only after confirmation."
        )

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for DipTrace XML and live projects")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("DIPTRACE_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("DIPTRACE_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DIPTRACE_MCP_PORT", "8765")),
    )
    args = parser.parse_args(argv)
    server = create_server()
    server.settings.host = args.host
    server.settings.port = args.port
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
