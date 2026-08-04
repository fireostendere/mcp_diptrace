from __future__ import annotations

import json
from pathlib import Path

import pytest

from diptrace_mcp.windows_configurator import (
    ConfiguratorError,
    build_codex_add_command,
    configure_claude,
    configure_clients,
    configure_codex,
    detect_diptrace_installations,
    validate_diptrace_directory,
    validate_state_dir,
    validate_workspace,
)


def _server(tmp_path: Path) -> Path:
    path = tmp_path / "path with spaces" / "diptrace_mcp_server.exe"
    path.parent.mkdir()
    path.write_bytes(b"server")
    return path


def _workspace(tmp_path: Path) -> Path:
    path = tmp_path / "Проекты DipTrace"
    path.mkdir()
    return path


def test_diptrace_detection_requires_executable_or_module_layout(tmp_path: Path) -> None:
    root = tmp_path / "DipTrace5"
    root.mkdir()
    assert detect_diptrace_installations(env={"ProgramFiles": str(tmp_path)}) == ()

    (root / "Pcb.exe").write_bytes(b"synthetic")
    found = detect_diptrace_installations(env={"ProgramFiles": str(tmp_path)})
    assert len(found) == 1
    assert found[0].evidence == ("executable:Pcb.exe",)


def test_multiple_diptrace_installations_are_returned_sorted(tmp_path: Path) -> None:
    for name in ("DipTrace", "DipTrace5"):
        root = tmp_path / name
        root.mkdir()
        (root / "Schematic.exe").write_bytes(b"synthetic")
    found = detect_diptrace_installations(env={"ProgramFiles": str(tmp_path)})
    assert [item.root.name for item in found] == ["DipTrace", "DipTrace5"]


def test_invalid_diptrace_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfiguratorError, match="recognized DipTrace"):
        validate_diptrace_directory(tmp_path)


def test_workspace_validation_handles_unicode_and_rejects_file(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert validate_workspace(workspace) == workspace.resolve()
    file_path = tmp_path / "workspace.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ConfiguratorError, match="not a directory"):
        validate_workspace(file_path)


def test_state_directory_rejects_program_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_files = tmp_path / "Program Files"
    monkeypatch.setenv("ProgramFiles", str(program_files))
    with pytest.raises(ConfiguratorError, match="Program Files"):
        validate_state_dir(program_files / "DipTraceMCP")


def test_codex_command_is_argument_vector_and_quotes_unicode_paths(tmp_path: Path) -> None:
    command = build_codex_add_command(
        _server(tmp_path), _workspace(tmp_path), tmp_path / "state dir"
    )
    assert command[:4] == ("codex", "mcp", "add", "diptrace")
    assert "--" in command
    assert "Проекты DipTrace" in command[command.index("--env") + 1]
    assert all("&" not in part and "|" not in part for part in command)


def test_claude_json_preserves_unknown_fields_and_other_servers(tmp_path: Path) -> None:
    config = tmp_path / "AppData" / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"custom": {"keep": True}, "mcpServers": {"other": {"command": "other"}}}),
        encoding="utf-8",
    )
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    change = configure_claude(
        server=server,
        workspace=workspace,
        state_dir=tmp_path / "state",
        env={"APPDATA": str(tmp_path / "AppData")},
    )
    payload = json.loads(config.read_text(encoding="utf-8"))
    assert payload["custom"] == {"keep": True}
    assert payload["mcpServers"]["other"] == {"command": "other"}
    assert payload["mcpServers"]["diptrace"]["command"] == str(server.resolve())
    assert change.backup_path is not None and change.backup_path.is_file()


def test_claude_malformed_json_is_fail_closed(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    original = "{not-json"
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ConfiguratorError, match="invalid"):
        configure_claude(
            server=_server(tmp_path),
            workspace=_workspace(tmp_path),
            state_dir=tmp_path / "state",
            env={"APPDATA": str(tmp_path)},
        )
    assert config.read_text(encoding="utf-8") == original
    assert list(config.parent.glob("*.backup.json")) == []


def test_claude_duplicate_entry_is_idempotent_without_new_backup(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"
    entry = {
        "command": str(server.resolve()),
        "args": [],
        "env": {
            "DIPTRACE_MCP_WORKSPACE": str(workspace.resolve()),
            "DIPTRACE_MCP_STATE_DIR": str(state.resolve()),
        },
    }
    config.write_text(json.dumps({"mcpServers": {"diptrace": entry}}), encoding="utf-8")
    change = configure_claude(
        server=server, workspace=workspace, state_dir=state, env={"APPDATA": str(tmp_path)}
    )
    assert change.status == "unchanged"
    assert list(config.parent.glob("*.backup.json")) == []


def test_claude_dry_run_does_not_write_or_backup(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"mcpServers": {"other": {}}}), encoding="utf-8")
    change = configure_claude(
        server=_server(tmp_path),
        workspace=_workspace(tmp_path),
        state_dir=tmp_path / "state",
        env={"APPDATA": str(tmp_path)},
        dry_run=True,
    )
    assert change.status == "dry-run"
    assert "diptrace" not in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert list(config.parent.glob("*.backup.json")) == []


def test_claude_unconfigure_and_restore_backup(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"mcpServers": {"diptrace": {"command": "old"}, "other": {}}}), encoding="utf-8"
    )
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"
    removed = configure_claude(
        server=server,
        workspace=workspace,
        state_dir=state,
        env={"APPDATA": str(tmp_path)},
        unconfigure=True,
    )
    assert removed.status == "unconfigured"
    assert "diptrace" not in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    restored = configure_claude(
        server=server,
        workspace=workspace,
        state_dir=state,
        env={"APPDATA": str(tmp_path)},
        restore_backup=True,
    )
    assert restored.status == "restored"
    assert (
        json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["diptrace"]["command"] == "old"
    )


def test_both_client_selection_configures_claude_and_reports_codex_without_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.shutil.which", lambda name, path=None: None
    )
    changes = configure_clients(
        client="both",
        server=_server(tmp_path),
        workspace=_workspace(tmp_path),
        state_dir=tmp_path / "state",
        env={"APPDATA": str(tmp_path), "PATH": ""},
    )
    assert [change.client for change in changes] == ["codex", "claude"]
    assert changes[0].status == "manual-required"
    assert (tmp_path / "state" / "codex_setup.txt").is_file()
    assert "diptrace" in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]


def test_both_client_preflight_preserves_codex_when_claude_is_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    codex_config = codex_home / "config.toml"
    original = '[mcp_servers.other]\ncommand = "other.exe"\n'
    codex_config.write_text(original, encoding="utf-8")
    claude_config = tmp_path / "Claude" / "claude_desktop_config.json"
    claude_config.parent.mkdir()
    claude_config.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.shutil.which", lambda name, path=None: "codex.exe"
    )
    with pytest.raises(ConfiguratorError, match="invalid"):
        configure_clients(
            client="both",
            server=_server(tmp_path),
            workspace=_workspace(tmp_path),
            state_dir=tmp_path / "state",
            env={"CODEX_HOME": str(codex_home), "APPDATA": str(tmp_path), "PATH": ""},
        )
    assert codex_config.read_text(encoding="utf-8") == original


def test_codex_existing_entry_is_replaced_without_touching_other_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config = codex_home / "config.toml"
    config.write_text(
        '[mcp_servers.other]\ncommand = "other.exe"\n'
        '[mcp_servers.diptrace]\ncommand = "old.exe"\n'
        '[mcp_servers.diptrace.env]\nDIPTRACE_MCP_WORKSPACE = "old"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.shutil.which", lambda name, path=None: "codex.exe"
    )
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.subprocess.run",
        lambda command, **kwargs: calls.append(command) or Completed(),
    )
    change = configure_codex(
        server=_server(tmp_path),
        workspace=_workspace(tmp_path),
        state_dir=tmp_path / "state",
        env={"CODEX_HOME": str(codex_home), "PATH": ""},
    )
    assert change.status == "configured"
    assert calls[0][:4] == ["codex", "mcp", "remove", "diptrace"]
    assert calls[1][:4] == ["codex", "mcp", "add", "diptrace"]
    assert change.backup_path is not None and change.backup_path.is_file()
    assert "mcp_servers.other" in config.read_text(encoding="utf-8")


def test_codex_add_failure_restores_config_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config = codex_home / "config.toml"
    original = '[mcp_servers.diptrace]\ncommand = "old.exe"\n'
    config.write_text(original, encoding="utf-8")

    class Completed:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    results = iter((Completed(0), Completed(1)))
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.shutil.which", lambda name, path=None: "codex.exe"
    )
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.subprocess.run",
        lambda command, **kwargs: next(results),
    )
    with pytest.raises(ConfiguratorError, match="failed"):
        configure_codex(
            server=_server(tmp_path),
            workspace=_workspace(tmp_path),
            state_dir=tmp_path / "state",
            env={"CODEX_HOME": str(codex_home), "PATH": ""},
        )
    assert config.read_text(encoding="utf-8") == original


def test_missing_workspace_is_rejected_for_direct_configuration(tmp_path: Path) -> None:
    missing = tmp_path / "missing workspace"
    with pytest.raises(ConfiguratorError, match="does not exist"):
        validate_workspace(missing)


def test_codex_unconfigure_without_cli_fails_instead_of_reporting_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        '[mcp_servers.diptrace]\ncommand = "server.exe"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        "diptrace_mcp.windows_configurator.shutil.which", lambda name, path=None: None
    )
    with pytest.raises(ConfiguratorError, match="was not removed"):
        configure_codex(
            server=_server(tmp_path),
            workspace=_workspace(tmp_path),
            state_dir=tmp_path / "state",
            env={"CODEX_HOME": str(codex_home), "PATH": ""},
            unconfigure=True,
        )
