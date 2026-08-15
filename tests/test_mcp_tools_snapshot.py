from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.types import Icon, ListToolsResult, Tool, ToolAnnotations, ToolExecution

from scripts.generate_mcp_tools_snapshot import (
    DEFAULT_OUTPUT,
    ToolsSnapshotError,
    build_snapshot,
    canonical_descriptors,
    collect_tool_pages,
    main,
    parse_snapshot,
    render_snapshot,
    serialize_tool,
    validate_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def _descriptor(name: str, description: str = "description") -> dict[str, object]:
    return {
        "description": description,
        "inputSchema": {"properties": {}, "type": "object"},
        "name": name,
        "outputSchema": {"type": "object"},
    }


class _PagedSession:
    def __init__(self, pages: dict[str | None, ListToolsResult]) -> None:
        self.pages = pages
        self.cursors: list[str | None] = []

    async def list_tools(self, cursor: str | None = None) -> ListToolsResult:
        self.cursors.append(cursor)
        return self.pages[cursor]


def test_committed_public_tools_snapshot_is_current() -> None:
    assert main(["--check"]) == 0


def test_snapshot_is_self_consistent_and_exactly_pretty_printed() -> None:
    content = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    snapshot = parse_snapshot(content)
    tools = snapshot["tools"]

    assert snapshot["tool_count"] == len(tools) == 167
    canonical = canonical_descriptors(tools)
    assert snapshot["canonical_descriptor_bytes"] == len(canonical)
    assert render_snapshot(snapshot) == content


def test_snapshot_generation_is_stable_under_transport_order() -> None:
    forward = build_snapshot([_descriptor("b"), _descriptor("a")])
    reverse = build_snapshot([_descriptor("a"), _descriptor("b")])

    assert forward == reverse
    assert [tool["name"] for tool in forward["tools"]] == ["a", "b"]
    assert render_snapshot(forward) == render_snapshot(reverse)


def test_public_collector_exhausts_all_tool_pages() -> None:
    first = Tool(name="b", inputSchema={"type": "object"})
    second = Tool(name="a", inputSchema={"type": "object"})
    session = _PagedSession(
        {
            None: ListToolsResult(tools=[first], nextCursor="page-2"),
            "page-2": ListToolsResult(tools=[second]),
        }
    )

    tools = asyncio.run(collect_tool_pages(session))

    assert [tool.name for tool in tools] == ["b", "a"]
    assert session.cursors == [None, "page-2"]


def test_public_collector_rejects_repeated_cursor() -> None:
    session = _PagedSession(
        {
            None: ListToolsResult(tools=[], nextCursor="repeat"),
            "repeat": ListToolsResult(tools=[], nextCursor="repeat"),
        }
    )

    with pytest.raises(ToolsSnapshotError, match="repeated cursor"):
        asyncio.run(collect_tool_pages(session))
    assert session.cursors == [None, "repeat"]


def test_snapshot_self_check_rejects_descriptor_mutation() -> None:
    snapshot = build_snapshot([_descriptor("a")])
    snapshot["tools"][0]["description"] = "changed after digest"

    with pytest.raises(ToolsSnapshotError, match="inconsistent"):
        validate_snapshot(snapshot)


def test_serializer_captures_every_non_null_public_tool_field() -> None:
    tool = Tool(
        name="complete",
        title="Complete tool",
        description="All fields populated",
        inputSchema={"type": "object"},
        outputSchema={"type": "object"},
        icons=[Icon(src="data:image/svg+xml;base64,PHN2Zy8+")],
        annotations=ToolAnnotations(readOnlyHint=True),
        _meta={"diptrace": {"contract": 1}},
        execution=ToolExecution(taskSupport="optional"),
    )

    descriptor = serialize_tool(tool)

    assert set(descriptor) == {
        "_meta",
        "annotations",
        "description",
        "execution",
        "icons",
        "inputSchema",
        "name",
        "outputSchema",
        "title",
    }
    assert "meta" not in descriptor
    assert descriptor == tool.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def test_check_detects_mutation_without_rewriting(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"
    original = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    output.write_text(original, encoding="utf-8")
    decoded = json.loads(original)
    decoded["tools"][0]["description"] = "mutated"
    mutated = json.dumps(decoded, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.write_text(mutated, encoding="utf-8")
    before = output.read_bytes()

    assert main(["--out", str(output), "--check"]) == 1
    assert output.read_bytes() == before


def test_check_does_not_create_a_missing_output(tmp_path: Path) -> None:
    output = tmp_path / "missing.json"

    assert main(["--out", str(output), "--check"]) == 1
    assert not output.exists()
