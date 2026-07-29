#!/usr/bin/env python3
"""Capture the exact public MCP ``tools/list`` contract over an in-memory transport."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ListToolsResult, Tool

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "reference" / "mcp-tools-list.snapshot.json"
SNAPSHOT_FORMAT_VERSION = 1
TRANSPORT_DESCRIPTION = "MCP ClientSession.list_tools over the public in-memory transport"
TOP_LEVEL_KEYS = frozenset(
    {
        "canonical_descriptor_bytes",
        "canonical_descriptor_sha256",
        "format_version",
        "tool_count",
        "tools",
        "transport",
    }
)


class ToolsSnapshotError(ValueError):
    """The generated or committed public-tool snapshot is malformed."""


class ToolsListSession(Protocol):
    """The public client operation used by the snapshot collector."""

    async def list_tools(self, cursor: str | None = None) -> ListToolsResult: ...


def serialize_tool(tool: Tool) -> dict[str, Any]:
    """Return every non-null field as it appears on the MCP wire."""
    payload = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
    if not isinstance(payload, dict):
        raise ToolsSnapshotError("MCP Tool serialization did not produce an object")
    return payload


def canonical_descriptors(tools: list[dict[str, Any]]) -> bytes:
    """Return the byte-exact canonical descriptor representation used for the digest."""
    return json.dumps(
        tools,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_snapshot(tools: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(tools, key=lambda item: str(item.get("name", "")))
    names = [tool.get("name") for tool in ordered]
    if not ordered:
        raise ToolsSnapshotError("tools/list returned no tools")
    if any(not isinstance(name, str) or not name for name in names):
        raise ToolsSnapshotError("every tool must have a non-empty string name")
    if len(set(names)) != len(names):
        raise ToolsSnapshotError("tools/list contains duplicate tool names")
    if any(value is None for tool in ordered for value in tool.values()):
        raise ToolsSnapshotError("tool descriptors must omit null Tool fields")

    canonical = canonical_descriptors(ordered)
    return {
        "canonical_descriptor_bytes": len(canonical),
        "canonical_descriptor_sha256": hashlib.sha256(canonical).hexdigest(),
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "tool_count": len(ordered),
        "tools": ordered,
        "transport": TRANSPORT_DESCRIPTION,
    }


def validate_snapshot(snapshot: object) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ToolsSnapshotError("snapshot root must be a JSON object")
    if set(snapshot) != TOP_LEVEL_KEYS:
        raise ToolsSnapshotError("snapshot top-level fields do not match format version 1")
    if snapshot["format_version"] != SNAPSHOT_FORMAT_VERSION:
        raise ToolsSnapshotError("unsupported snapshot format version")
    if snapshot["transport"] != TRANSPORT_DESCRIPTION:
        raise ToolsSnapshotError("snapshot transport description is not canonical")
    tools = snapshot["tools"]
    if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
        raise ToolsSnapshotError("snapshot tools must be a list of objects")

    rebuilt = build_snapshot(tools)
    if rebuilt != snapshot:
        raise ToolsSnapshotError(
            "snapshot order, count, canonical byte count, or SHA-256 is inconsistent"
        )
    return snapshot


def render_snapshot(snapshot: dict[str, Any]) -> str:
    validate_snapshot(snapshot)
    return (
        json.dumps(
            snapshot,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


async def collect_public_tools(repository_root: Path) -> list[dict[str, Any]]:
    """Call public ``tools/list`` without reading FastMCP's private registry."""
    workspace = (repository_root / "tests" / "fixtures").resolve()
    with tempfile.TemporaryDirectory(prefix="diptrace-tools-snapshot-") as state_dir:
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
            tools = await collect_tool_pages(session)
    return [serialize_tool(tool) for tool in tools]


async def collect_tool_pages(session: ToolsListSession) -> list[Tool]:
    """Exhaust public pagination and fail closed if a server repeats a cursor."""
    tools: list[Tool] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        response = await session.list_tools(cursor=cursor)
        tools.extend(response.tools)
        next_cursor = response.nextCursor
        if next_cursor is None:
            return tools
        if not next_cursor:
            raise ToolsSnapshotError("tools/list returned an empty next cursor")
        if next_cursor in seen_cursors:
            raise ToolsSnapshotError(f"tools/list repeated cursor {next_cursor!r}")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


async def generate_snapshot(repository_root: Path) -> str:
    tools = await collect_public_tools(repository_root)
    return render_snapshot(build_snapshot(tools))


def parse_snapshot(content: str) -> dict[str, Any]:
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ToolsSnapshotError(f"snapshot is not valid JSON: {exc}") from exc
    snapshot = validate_snapshot(decoded)
    if render_snapshot(snapshot) != content:
        raise ToolsSnapshotError("snapshot is not in the exact generated pretty format")
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="snapshot path (default: reference/mcp-tools-list.snapshot.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail without rewriting when the committed snapshot is stale",
    )
    args = parser.parse_args(argv)
    output = args.out.resolve()

    try:
        generated = asyncio.run(generate_snapshot(REPOSITORY_ROOT))
        if args.check:
            actual = output.read_text(encoding="utf-8")
            parse_snapshot(actual)
            if actual != generated:
                print(f"FAIL: {output} differs from public MCP tools/list")
                return 1
            snapshot = json.loads(actual)
            print(
                f"OK: {output} matches {snapshot['tool_count']} public tools "
                f"({snapshot['canonical_descriptor_bytes']} canonical bytes)"
            )
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generated, encoding="utf-8", newline="\n")
        snapshot = json.loads(generated)
        print(
            f"Wrote {output} with {snapshot['tool_count']} public tools "
            f"({snapshot['canonical_descriptor_bytes']} canonical bytes)"
        )
        return 0
    except (OSError, ToolsSnapshotError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
