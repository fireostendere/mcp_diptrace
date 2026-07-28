from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp import bridge
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS


def test_bridge_timeout_default_is_shared_by_cli_capabilities_and_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)

    args = bridge._build_parser().parse_args(["exchange.xml"])
    limits = get_capabilities().limits
    usage = (Path(__file__).parents[1] / "docs" / "USAGE.md").read_text(
        encoding="utf-8"
    )

    assert args.timeout == DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    assert (
        limits["default_live_session_timeout_seconds"]
        == DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    )
    assert (
        f"| `DIPTRACE_MCP_SESSION_TIMEOUT` | "
        f"`{DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS}` |"
    ) in usage


def test_bridge_timeout_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "2400")

    args = bridge._build_parser().parse_args(["exchange.xml"])

    assert args.timeout == 2400


def test_bridge_timeout_cli_override_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", "2400")

    args = bridge._build_parser().parse_args(
        ["exchange.xml", "--timeout", "45"]
    )

    assert args.timeout == 45


@pytest.mark.parametrize(
    ("environment", "arguments"),
    [
        ("0", ["exchange.xml"]),
        ("not-an-integer", ["exchange.xml"]),
        (None, ["exchange.xml", "--timeout", "-1"]),
        (None, ["exchange.xml", "--timeout", "not-an-integer"]),
    ],
)
def test_bridge_timeout_rejects_non_positive_or_non_integer_values(
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
    arguments: list[str],
) -> None:
    if environment is None:
        monkeypatch.delenv("DIPTRACE_MCP_SESSION_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("DIPTRACE_MCP_SESSION_TIMEOUT", environment)

    with pytest.raises(SystemExit) as exc_info:
        bridge._build_parser().parse_args(arguments)

    assert exc_info.value.code == 2
