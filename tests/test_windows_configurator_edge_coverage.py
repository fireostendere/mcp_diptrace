from __future__ import annotations

import json
from pathlib import Path

import pytest

import diptrace_mcp.windows_configurator as configurator


def _server(tmp_path: Path) -> Path:
    path = tmp_path / "diptrace_mcp_server.exe"
    path.write_bytes(b"server")
    return path


def _workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir(exist_ok=True)
    return path


def test_small_configurator_helpers_and_path_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = configurator.ConfigChange(
        "codex",
        "configured",
        tmp_path / "config.toml",
        tmp_path / "backup.toml",
        ("codex", "mcp"),
        "done",
    )
    assert change.as_dict()["command"] == ["codex", "mcp"]
    assert change.as_dict()["backup_path"] == str(tmp_path / "backup.toml")

    monkeypatch.setenv("MiXeD_CaSe_Value", "present")
    assert configurator._windows_environment_value("mixed_case_value") == "present"
    assert configurator._is_within(tmp_path / "child", tmp_path)
    assert not configurator._is_within(tmp_path.parent, tmp_path)

    with pytest.raises(configurator.ConfiguratorError, match="non-empty"):
        configurator._canonical_path("", must_exist=False)
    with pytest.raises(configurator.ConfiguratorError, match="NUL"):
        configurator._canonical_path("bad\x00path", must_exist=False)

    created = tmp_path / "created-workspace"
    assert configurator.validate_workspace(created, create=True) == created.resolve()

    state_file = tmp_path / "state-file"
    state_file.write_text("x", encoding="utf-8")
    with pytest.raises(configurator.ConfiguratorError, match="not a directory"):
        configurator.validate_state_dir(state_file)

    missing_state = tmp_path / "missing-state"
    with pytest.raises(configurator.ConfiguratorError, match="does not exist"):
        configurator.validate_state_dir(missing_state, create=False)

    wrong_server = tmp_path / "wrong.exe"
    wrong_server.write_bytes(b"x")
    with pytest.raises(configurator.ConfiguratorError, match="diptrace_mcp_server.exe"):
        configurator.validate_server_path(wrong_server)
    server_dir = tmp_path / "diptrace_mcp_server.exe"
    server_dir.mkdir()
    with pytest.raises(configurator.ConfiguratorError, match="regular file"):
        configurator.validate_server_path(server_dir)


def test_config_file_loaders_fail_closed_and_defaults_are_explicit(tmp_path: Path) -> None:
    override = tmp_path / "claude.json"
    assert configurator._default_claude_config(
        {"CLAUDE_DESKTOP_CONFIG": str(override)}
    ) == override
    with pytest.raises(configurator.ConfiguratorError, match="APPDATA"):
        configurator._default_claude_config({})

    config_dir = tmp_path / "config-dir"
    config_dir.mkdir()
    with pytest.raises(configurator.ConfiguratorError, match="regular file"):
        configurator._claude_config_path({"CLAUDE_DESKTOP_CONFIG": str(config_dir)})

    json_root = tmp_path / "root.json"
    json_root.write_text("[]", encoding="utf-8")
    with pytest.raises(configurator.ConfiguratorError, match="root must be an object"):
        configurator._load_json_object(json_root)

    bad_servers = tmp_path / "servers.json"
    bad_servers.write_text(json.dumps({"mcpServers": []}), encoding="utf-8")
    with pytest.raises(configurator.ConfiguratorError, match="mcpServers"):
        configurator._load_json_object(bad_servers)

    bad_toml = tmp_path / "config.toml"
    bad_toml.write_text("[broken", encoding="utf-8")
    with pytest.raises(configurator.ConfiguratorError, match="Codex config is invalid"):
        configurator._load_toml(bad_toml)


def test_backup_and_atomic_write_failure_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(configurator, "_timestamp", lambda: "20260101T000000Z")
    first = tmp_path / "config.json.diptrace-20260101T000000Z.backup.json"
    first.write_text("old", encoding="utf-8")
    candidate = configurator._backup_path(config)
    assert candidate.name.endswith("backup-1.json")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(configurator.os, "replace", fail_replace)
    with pytest.raises(configurator.ConfiguratorError, match="Atomic write failed"):
        configurator._atomic_write(tmp_path / "out.json", b"{}")

    monkeypatch.undo()

    def fail_copy(_source: Path, _target: Path) -> None:
        raise OSError("copy failed")

    monkeypatch.setattr(configurator.shutil, "copy2", fail_copy)
    with pytest.raises(configurator.ConfiguratorError, match="Unable to create config backup"):
        configurator._backup_existing(config)


def test_claude_restore_dry_run_and_missing_backup(tmp_path: Path) -> None:
    config = tmp_path / "Claude" / "claude_desktop_config.json"
    config.parent.mkdir()
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"
    env = {"CLAUDE_DESKTOP_CONFIG": str(config)}

    with pytest.raises(configurator.ConfiguratorError, match="No DipTrace Claude backup"):
        configurator.configure_claude(
            server=server,
            workspace=workspace,
            state_dir=state,
            env=env,
            restore_backup=True,
        )

    backup = config.parent / (
        "claude_desktop_config.json.diptrace-20260101T000000Z.backup.json"
    )
    backup.write_text(json.dumps({"mcpServers": {"old": {}}}), encoding="utf-8")
    result = configurator.configure_claude(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        restore_backup=True,
        dry_run=True,
    )
    assert result.status == "dry-run-restore"
    assert not config.exists()


def test_codex_restore_unconfigure_and_manual_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "codex"
    home.mkdir()
    config = home / "config.toml"
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"
    env = {"CODEX_HOME": str(home), "PATH": ""}

    with pytest.raises(configurator.ConfiguratorError, match="No DipTrace Codex backup"):
        configurator.configure_codex(
            server=server,
            workspace=workspace,
            state_dir=state,
            env=env,
            restore_backup=True,
        )

    backup = home / "config.toml.diptrace-20260101T000000Z.backup.toml"
    backup.write_text('[mcp_servers.other]\ncommand = "other.exe"\n', encoding="utf-8")
    restored = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        restore_backup=True,
        dry_run=True,
    )
    assert restored.status == "dry-run-restore"

    config.write_text('[mcp_servers.other]\ncommand = "other.exe"\n', encoding="utf-8")
    absent = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        unconfigure=True,
    )
    assert absent.status == "unchanged"

    config.write_text('[mcp_servers.diptrace]\ncommand = "old.exe"\n', encoding="utf-8")
    monkeypatch.setattr(configurator.shutil, "which", lambda _name, path=None: "codex.exe")
    planned = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        unconfigure=True,
        dry_run=True,
    )
    assert planned.status == "dry-run-unconfigure"
    assert planned.command == ("codex", "mcp", "remove", "diptrace")

    config.unlink()
    monkeypatch.setattr(configurator.shutil, "which", lambda _name, path=None: None)
    manual = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
    )
    assert manual.status == "manual-required"
    assert (state / "codex_setup.txt").is_file()


def test_configure_clients_validation_and_cli_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(configurator.ConfiguratorError, match="Unsupported client"):
        configurator.configure_clients(
            client="invalid",
            server=None,
            workspace=None,
            state_dir=None,
            env={},
        )

    skipped = configurator.configure_clients(
        client="none",
        server=None,
        workspace=None,
        state_dir=None,
        env={},
    )
    assert skipped[0].status == "skipped"

    with pytest.raises(configurator.ConfiguratorError, match="required"):
        configurator.configure_clients(
            client="claude",
            server=None,
            workspace=None,
            state_dir=None,
            env={},
        )

    assert configurator.main(["--client", "none", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["changes"][0]["status"] == "skipped"

    assert configurator.main(["--client", "claude", "--json"]) == 1
    error_payload = json.loads(capsys.readouterr().out)
    assert error_payload["ok"] is False


def test_remaining_helper_branches_and_actual_restore_paths(tmp_path: Path) -> None:
    install_root = tmp_path / "DipTrace"
    install_root.mkdir()
    installation = configurator.DipTraceInstallation(
        root=install_root,
        evidence=("executable:Pcb.exe",),
        source="test",
    )
    assert installation.display_name == f"DipTrace ({install_root})"

    assert configurator._load_json_object(tmp_path / "missing.json") == {}
    assert configurator._load_toml(tmp_path / "missing.toml") == {}
    assert configurator._backup_existing(tmp_path / "missing-config") is None
    assert configurator._default_state_dir({"LOCALAPPDATA": str(tmp_path / "Local")}) == (
        tmp_path / "Local" / "DipTraceMCP"
    )

    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"

    claude = tmp_path / "Claude" / "claude_desktop_config.json"
    claude.parent.mkdir()
    claude_backup = claude.parent / (
        "claude_desktop_config.json.diptrace-20260101T000000Z.backup.json"
    )
    claude_backup.write_text(
        json.dumps({"mcpServers": {"old": {"command": "old.exe"}}}),
        encoding="utf-8",
    )
    restored_claude = configurator.configure_claude(
        server=server,
        workspace=workspace,
        state_dir=state,
        env={"CLAUDE_DESKTOP_CONFIG": str(claude)},
        restore_backup=True,
    )
    assert restored_claude.status == "restored"
    restored_document = json.loads(claude.read_text(encoding="utf-8"))
    assert restored_document["mcpServers"]["old"]["command"] == "old.exe"

    codex_home = tmp_path / "codex-restore"
    codex_home.mkdir()
    codex = codex_home / "config.toml"
    codex_backup = codex_home / "config.toml.diptrace-20260101T000000Z.backup.toml"
    codex_backup.write_text('[mcp_servers.old]\ncommand = "old.exe"\n', encoding="utf-8")
    restored_codex = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env={"CODEX_HOME": str(codex_home), "PATH": ""},
        restore_backup=True,
    )
    assert restored_codex.status == "restored"
    assert "mcp_servers.old" in codex.read_text(encoding="utf-8")


def test_codex_matching_dry_run_and_unconfigure_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _server(tmp_path)
    workspace = _workspace(tmp_path)
    state = tmp_path / "state"
    home = tmp_path / "codex"
    home.mkdir()
    config = home / "config.toml"
    env = {"CODEX_HOME": str(home), "PATH": ""}

    entry = {
        "command": str(server),
        "env": {
            "DIPTRACE_MCP_WORKSPACE": str(workspace),
            "DIPTRACE_MCP_STATE_DIR": str(state),
        },
    }
    assert configurator._codex_entry({}) is None
    assert configurator._codex_entry({"mcp_servers": []}) is None
    assert configurator._codex_entry({"mcp_servers": {"diptrace": "bad"}}) is None
    assert configurator._codex_entry_matches(None, server, workspace, state) is False
    assert (
        configurator._codex_entry_matches(
            {"command": "wrong"}, server, workspace, state
        )
        is False
    )
    assert configurator._codex_entry_matches(entry, server, workspace, state) is True

    config.write_text(
        "[mcp_servers.diptrace]\n"
        f"command = {json.dumps(str(server))}\n"
        "[mcp_servers.diptrace.env]\n"
        f"DIPTRACE_MCP_WORKSPACE = {json.dumps(str(workspace))}\n"
        f"DIPTRACE_MCP_STATE_DIR = {json.dumps(str(state))}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(configurator.shutil, "which", lambda _name, path=None: "codex.exe")
    unchanged = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
    )
    assert unchanged.status == "unchanged"

    config.unlink()
    planned = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        dry_run=True,
    )
    assert planned.status == "dry-run"

    config.write_text('[mcp_servers.diptrace]\ncommand = "old.exe"\n', encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        configurator,
        "_run_codex",
        lambda command, _env: calls.append(tuple(command)),
    )
    removed = configurator.configure_codex(
        server=server,
        workspace=workspace,
        state_dir=state,
        env=env,
        unconfigure=True,
    )
    assert removed.status == "unconfigured"
    assert calls == [("codex", "mcp", "remove", "diptrace")]
    assert removed.backup_path is not None


def test_configure_clients_recovery_defaults_and_text_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    claude = tmp_path / "claude.json"
    unchanged = configurator.configure_clients(
        client="claude",
        server=None,
        workspace=None,
        state_dir=state,
        env={"CLAUDE_DESKTOP_CONFIG": str(claude)},
        unconfigure=True,
    )
    assert unchanged[0].status == "unchanged"

    assert configurator.main(["--client", "none"]) == 0
    assert "none: skipped" in capsys.readouterr().out

    assert configurator.main(["--client", "claude"]) == 1
    assert "Configuration failed:" in capsys.readouterr().err