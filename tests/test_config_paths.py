from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.config import Settings, platform_path


def _settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return Settings(
        workspace=workspace,
        allowed_roots=(workspace,),
        state_dir=tmp_path / "state",
    )


def test_caller_path_does_not_expand_environment_or_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    secret_value = "/server/private/ENV_SECRET_8d85f62c"
    monkeypatch.setenv("MCP_PATH_SECRET", secret_value)

    environment_path = settings.resolve_allowed_path(
        "$MCP_PATH_SECRET/board.xml",
        must_exist=False,
    )
    home_path = settings.resolve_allowed_path("~/board.xml", must_exist=False)

    assert environment_path == settings.workspace / "$MCP_PATH_SECRET" / "board.xml"
    assert home_path == settings.workspace / "~" / "board.xml"
    assert secret_value not in str(environment_path)
    assert platform_path("$MCP_PATH_SECRET/board.xml") == Path(
        "$MCP_PATH_SECRET/board.xml"
    )


def test_missing_literal_caller_path_does_not_disclose_environment_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    secret_value = "/server/private/ENV_SECRET_199e150d"
    monkeypatch.setenv("MCP_PATH_SECRET", secret_value)

    with pytest.raises(FileNotFoundError) as caught:
        settings.resolve_allowed_path("$MCP_PATH_SECRET/missing.xml")

    assert secret_value not in str(caught.value)


def test_server_owned_settings_keep_configured_path_expansion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_CONFIG_BASE", str(tmp_path))
    monkeypatch.setenv(
        "DIPTRACE_MCP_WORKSPACE",
        "$MCP_CONFIG_BASE/configured-workspace",
    )
    monkeypatch.setenv(
        "DIPTRACE_MCP_STATE_DIR",
        "$MCP_CONFIG_BASE/configured-state",
    )
    monkeypatch.setenv(
        "DIPTRACE_MCP_ALLOWED_ROOTS",
        "$MCP_CONFIG_BASE/configured-extra",
    )

    settings = Settings.from_env()

    assert settings.workspace == (tmp_path / "configured-workspace").resolve()
    assert settings.state_dir == (tmp_path / "configured-state").resolve()
    assert settings.allowed_roots == (
        (tmp_path / "configured-workspace").resolve(),
        (tmp_path / "configured-extra").resolve(),
    )
