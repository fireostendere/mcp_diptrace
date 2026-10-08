from __future__ import annotations

import asyncio
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolated_default_state_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Keep ``create_server()``/``Settings.from_env()`` off the developer's real state.

    Without this, tests on WSL resolve the Windows ``AppData`` store, pay its
    retention pass, and could prune real records. Tests that exercise default
    resolution delete the variable themselves.
    """

    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path_factory.mktemp("state")))


@pytest.fixture(scope="session")
def listed_tools(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Public tools/list entries exactly as clients receive them, by name."""

    from diptrace_mcp.config import Settings
    from diptrace_mcp.server import create_server

    root = tmp_path_factory.mktemp("listed-tools")
    settings = Settings(workspace=root, allowed_roots=(root,), state_dir=root / "state")
    return {tool.name: tool for tool in asyncio.run(create_server(settings).list_tools())}
