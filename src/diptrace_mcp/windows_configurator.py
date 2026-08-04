"""Fail-closed Windows installation and MCP-client configuration helpers.

The module is deliberately independent from Inno Setup.  It can therefore be
tested with temporary APPDATA/LOCALAPPDATA trees and can be used by the
installer, portable package, and maintainers without embedding JSON/TOML
mutation logic in Pascal Script.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

if sys.version_info >= (3, 11):
    import tomllib as _tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as _tomllib

tomllib: Any = _tomllib


class ConfiguratorError(RuntimeError):
    """A user-actionable, fail-closed configuration error."""


_DIPTRACE_EXECUTABLES = (
    "Pcb.exe",
    "Schematic.exe",
    "CompEdit.exe",
    "PattEdit.exe",
)
_DIPTRACE_PLUGIN_DIRS = (
    Path("Plugins") / "Pcb",
    Path("Plugins") / "Schematic",
    Path("Plugins") / "CompEdit",
    Path("Plugins") / "PattEdit",
)
_DIPTRACE_ROOT_NAMES = ("DipTrace", "DipTrace5")
_CLIENT_ENTRY_NAME = "diptrace"


@dataclass(frozen=True)
class DipTraceInstallation:
    """A validated DipTrace root; a directory name alone is never sufficient."""

    root: Path
    evidence: tuple[str, ...]
    source: str

    @property
    def display_name(self) -> str:
        return f"{self.root.name} ({self.root})"


@dataclass(frozen=True)
class ConfigChange:
    client: str
    status: str
    config_path: Path | None = None
    backup_path: Path | None = None
    command: tuple[str, ...] = ()
    message: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "client": self.client,
            "status": self.status,
            "config_path": str(self.config_path) if self.config_path else None,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "command": list(self.command),
            "message": self.message,
        }


def _casefold_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False))).rstrip("\\/").casefold()


def _is_within(path: Path, root: Path) -> bool:
    candidate = _casefold_path(path)
    parent = _casefold_path(root)
    return candidate == parent or candidate.startswith(parent + os.sep.casefold())


def _windows_environment_value(name: str) -> str | None:
    folded = name.casefold()
    return next((value for key, value in os.environ.items() if key.casefold() == folded), None)


def _canonical_path(raw: str | os.PathLike[str], *, must_exist: bool) -> Path:
    value = os.fspath(raw)
    if not value or "\x00" in value:
        raise ConfiguratorError("Path must be non-empty and must not contain NUL")
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    try:
        return path.resolve(strict=must_exist)
    except OSError as exc:
        raise ConfiguratorError(f"Unable to resolve path: {value}") from exc


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor) if path.anchor else Path()
    for component in path.parts[1:] if path.anchor else path.parts:
        current /= component
        if current.is_symlink():
            raise ConfiguratorError(f"Refusing a symlink/reparse component: {current}")


def validate_workspace(raw: str | os.PathLike[str], *, create: bool = False) -> Path:
    """Return an existing canonical workspace, optionally creating it safely."""

    path = _canonical_path(raw, must_exist=False)
    if path.exists() and not path.is_dir():
        raise ConfiguratorError(f"Workspace is not a directory: {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() and not create:
        raise ConfiguratorError(f"Workspace directory does not exist: {path}")
    if not path.is_dir():
        raise ConfiguratorError(f"Workspace directory does not exist: {path}")
    _reject_symlink_components(path)
    return path.resolve()


def validate_state_dir(raw: str | os.PathLike[str], *, create: bool = True) -> Path:
    """Validate writable state outside protected application locations."""

    path = _canonical_path(raw, must_exist=False)
    if path.exists() and not path.is_dir():
        raise ConfiguratorError(f"State directory is not a directory: {path}")
    program_roots = [
        value
        for value in (
            _windows_environment_value("ProgramFiles"),
            _windows_environment_value("ProgramFiles(x86)"),
        )
        if value
    ]
    if any(_is_within(path, _canonical_path(root, must_exist=False)) for root in program_roots):
        raise ConfiguratorError("State must not be stored under Program Files")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ConfiguratorError(f"State directory does not exist: {path}")
    _reject_symlink_components(path)
    return path.resolve()


def validate_server_path(raw: str | os.PathLike[str]) -> Path:
    path = _canonical_path(raw, must_exist=True)
    if not path.is_file() or path.is_symlink():
        raise ConfiguratorError(f"Standalone server is not a regular file: {path}")
    if path.name.casefold() != "diptrace_mcp_server.exe":
        raise ConfiguratorError("Server path must point to diptrace_mcp_server.exe")
    return path


def _registry_install_locations() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg as _winreg
    except ImportError:
        return []

    winreg: Any = _winreg
    locations: list[Path] = []
    uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for access in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, uninstall_key, 0, winreg.KEY_READ | access) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            child_name = winreg.EnumKey(parent, index)
                            with winreg.OpenKey(parent, child_name) as child:
                                display = str(winreg.QueryValueEx(child, "DisplayName")[0])
                                install = winreg.QueryValueEx(child, "InstallLocation")[0]
                        except (OSError, ValueError):
                            continue
                        if (
                            "diptrace" in display.casefold()
                            and isinstance(install, str)
                            and install
                        ):
                            locations.append(Path(install))
            except OSError:
                continue
    return locations


def validate_diptrace_directory(
    raw: str | os.PathLike[str],
    *,
    source: str = "user",
) -> DipTraceInstallation:
    """Validate root plus known executable or module-directory evidence."""

    root = _canonical_path(raw, must_exist=True)
    if not root.is_dir() or root.is_symlink():
        raise ConfiguratorError(f"DipTrace path is not a regular directory: {root}")
    _reject_symlink_components(root)
    evidence = [
        f"executable:{name}"
        for name in _DIPTRACE_EXECUTABLES
        if (root / name).is_file() and not (root / name).is_symlink()
    ]
    evidence.extend(
        f"module-directory:{relative.as_posix()}"
        for relative in _DIPTRACE_PLUGIN_DIRS
        if (root / relative).is_dir() and not (root / relative).is_symlink()
    )
    if not evidence:
        expected = ", ".join(_DIPTRACE_EXECUTABLES)
        raise ConfiguratorError(
            "Directory does not contain a recognized DipTrace executable or module layout: "
            f"{root}. "
            f"Expected one of: {expected}"
        )
    return DipTraceInstallation(root=root, evidence=tuple(evidence), source=source)


def detect_diptrace_installations(
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[DipTraceInstallation, ...]:
    """Find validated installations from deterministic roots and safe registry reads."""

    variables = os.environ if env is None else env
    candidates: list[tuple[Path, str]] = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = variables.get(variable)
        if base:
            for name in _DIPTRACE_ROOT_NAMES:
                candidates.append((Path(base) / name, f"{variable}:{name}"))
    candidates.extend((path, "registry") for path in _registry_install_locations())

    found: dict[str, DipTraceInstallation] = {}
    for candidate, source in candidates:
        try:
            installation = validate_diptrace_directory(candidate, source=source)
        except ConfiguratorError:
            continue
        found[_casefold_path(installation.root)] = installation
    return tuple(sorted(found.values(), key=lambda item: _casefold_path(item.root)))


def _default_state_dir(env: Mapping[str, str]) -> Path:
    local_app_data = env.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DipTraceMCP"
    return Path.home() / "AppData" / "Local" / "DipTraceMCP"


def _default_claude_config(env: Mapping[str, str]) -> Path:
    override = env.get("CLAUDE_DESKTOP_CONFIG")
    if override:
        return Path(override)
    app_data = env.get("APPDATA")
    if not app_data:
        raise ConfiguratorError("APPDATA is not set; set CLAUDE_DESKTOP_CONFIG explicitly")
    return Path(app_data) / "Claude" / "claude_desktop_config.json"


def _claude_config_path(env: Mapping[str, str]) -> Path:
    path = _default_claude_config(env)
    if path.exists() and not path.is_file():
        raise ConfiguratorError(f"Claude Desktop config is not a regular file: {path}")
    return path.resolve(strict=False)


def _codex_config_path(env: Mapping[str, str]) -> Path:
    home = env.get("CODEX_HOME")
    return (Path(home) if home else Path.home() / ".codex") / "config.toml"


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfiguratorError(
            f"Claude Desktop config is invalid; it was not changed: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ConfiguratorError(f"Claude Desktop config root must be an object: {path}")
    servers = value.get("mcpServers")
    if servers is not None and not isinstance(servers, dict):
        raise ConfiguratorError("Claude Desktop mcpServers must be an object; it was not changed")
    return value


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return cast(dict[str, Any], tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfiguratorError(f"Codex config is invalid; it was not changed: {path}") from exc


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup_path(path: Path) -> Path:
    base = Path(f"{path}.{_CLIENT_ENTRY_NAME}-{_timestamp()}.backup{path.suffix}")
    candidate = base
    index = 1
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}-{index}{base.suffix}")
        index += 1
    return candidate


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.diptrace-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ConfiguratorError(
            f"Atomic write failed; original file was preserved: {path}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = _backup_path(path)
    try:
        shutil.copy2(path, backup)
    except OSError as exc:
        raise ConfiguratorError(
            f"Unable to create config backup; original was not changed: {path}"
        ) from exc
    return backup


def _server_entry(server: Path, workspace: Path, state_dir: Path) -> dict[str, Any]:
    return {
        "command": str(server),
        "args": [],
        "env": {
            "DIPTRACE_MCP_WORKSPACE": str(workspace),
            "DIPTRACE_MCP_STATE_DIR": str(state_dir),
        },
    }


def _claude_entry(server: Path, workspace: Path, state_dir: Path) -> dict[str, Any]:
    return _server_entry(server, workspace, state_dir)


def configure_claude(
    *,
    server: Path,
    workspace: Path,
    state_dir: Path,
    env: Mapping[str, str] | None = None,
    dry_run: bool = False,
    unconfigure: bool = False,
    restore_backup: bool = False,
) -> ConfigChange:
    variables = os.environ if env is None else env
    path = _claude_config_path(variables)
    if restore_backup:
        backup = _latest_backup(path)
        if backup is None:
            raise ConfiguratorError(f"No DipTrace Claude backup found beside {path}")
        restored = _load_json_object(backup)
        if dry_run:
            return ConfigChange("claude", "dry-run-restore", path, backup)
        _atomic_write(
            path, json.dumps(restored, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        _load_json_object(path)
        return ConfigChange("claude", "restored", path, backup)

    document = _load_json_object(path)
    servers = dict(document.get("mcpServers") or {})
    existing = servers.get(_CLIENT_ENTRY_NAME)
    if unconfigure:
        if existing is None:
            return ConfigChange("claude", "unchanged", path, message="diptrace entry was absent")
        updated = dict(document)
        updated_servers = dict(servers)
        updated_servers.pop(_CLIENT_ENTRY_NAME, None)
        updated["mcpServers"] = updated_servers
    else:
        updated = dict(document)
        updated_servers = dict(servers)
        updated_servers[_CLIENT_ENTRY_NAME] = _claude_entry(server, workspace, state_dir)
        updated["mcpServers"] = updated_servers
        if existing == updated_servers[_CLIENT_ENTRY_NAME]:
            return ConfigChange(
                "claude", "unchanged", path, message="diptrace entry already matches"
            )

    backup = _backup_existing(path) if not dry_run else None
    if dry_run:
        return ConfigChange("claude", "dry-run", path, message="atomic JSON update planned")
    payload = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    _atomic_write(path, payload)
    reparsed = _load_json_object(path)
    if reparsed.get("mcpServers", {}).get(_CLIENT_ENTRY_NAME) != updated["mcpServers"].get(
        _CLIENT_ENTRY_NAME
    ):
        raise ConfiguratorError(
            f"Claude Desktop config verification failed after atomic write: {path}"
        )
    return ConfigChange("claude", "unconfigured" if unconfigure else "configured", path, backup)


def _latest_backup(path: Path) -> Path | None:
    candidates = sorted(
        path.parent.glob(f"{path.name}.{_CLIENT_ENTRY_NAME}-*.backup{path.suffix}"),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _codex_entry(document: Mapping[str, Any]) -> Mapping[str, Any] | None:
    servers = document.get("mcp_servers")
    if not isinstance(servers, Mapping):
        return None
    entry = servers.get(_CLIENT_ENTRY_NAME)
    return entry if isinstance(entry, Mapping) else None


def build_codex_add_command(server: Path, workspace: Path, state_dir: Path) -> tuple[str, ...]:
    return (
        "codex",
        "mcp",
        "add",
        _CLIENT_ENTRY_NAME,
        "--env",
        f"DIPTRACE_MCP_WORKSPACE={workspace}",
        "--env",
        f"DIPTRACE_MCP_STATE_DIR={state_dir}",
        "--",
        str(server),
    )


def _codex_entry_matches(
    entry: Mapping[str, Any] | None, server: Path, workspace: Path, state_dir: Path
) -> bool:
    if entry is None:
        return False
    if str(entry.get("command", "")) != str(server):
        return False
    env = entry.get("env")
    return (
        isinstance(env, Mapping)
        and env.get("DIPTRACE_MCP_WORKSPACE") == str(workspace)
        and env.get("DIPTRACE_MCP_STATE_DIR") == str(state_dir)
    )


def _write_codex_setup_file(path: Path, command: Sequence[str]) -> None:
    rendered = subprocess.list2cmdline(list(command)) if os.name == "nt" else shlex.join(command)
    _atomic_write(path, (rendered + "\n").encode("utf-8"))


def _run_codex(command: Sequence[str], env: Mapping[str, str]) -> None:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        env=dict(env),
    )
    if completed.returncode != 0:
        raise ConfiguratorError(f"Codex command failed with exit code {completed.returncode}")


def configure_codex(
    *,
    server: Path,
    workspace: Path,
    state_dir: Path,
    env: Mapping[str, str] | None = None,
    dry_run: bool = False,
    unconfigure: bool = False,
    restore_backup: bool = False,
) -> ConfigChange:
    variables = dict(os.environ if env is None else env)
    path = _codex_config_path(variables).resolve(strict=False)
    command = build_codex_add_command(server, workspace, state_dir)
    document = _load_toml(path)
    existing = _codex_entry(document)
    codex = shutil.which("codex", path=variables.get("PATH"))

    if restore_backup:
        backup = _latest_backup(path)
        if backup is None:
            raise ConfiguratorError(f"No DipTrace Codex backup found beside {path}")
        _load_toml(backup)
        if dry_run:
            return ConfigChange("codex", "dry-run-restore", path, backup)
        _atomic_write(path, backup.read_bytes())
        _load_toml(path)
        return ConfigChange("codex", "restored", path, backup)

    if unconfigure:
        if existing is None:
            return ConfigChange("codex", "unchanged", path, message="diptrace entry was absent")
        if not codex:
            raise ConfiguratorError(
                "Codex CLI was not found; the diptrace entry was not removed. "
                "Run `codex mcp remove diptrace` manually or restore a known-good backup."
            )
        if dry_run:
            return ConfigChange(
                "codex",
                "dry-run-unconfigure",
                path,
                command=("codex", "mcp", "remove", _CLIENT_ENTRY_NAME),
            )
        backup = _backup_existing(path)
        _run_codex(("codex", "mcp", "remove", _CLIENT_ENTRY_NAME), variables)
        return ConfigChange("codex", "unconfigured", path, backup)

    if _codex_entry_matches(existing, server, workspace, state_dir):
        return ConfigChange(
            "codex", "unchanged", path, command=command, message="diptrace entry already matches"
        )
    if dry_run:
        return ConfigChange("codex", "dry-run", path, command=command)
    if not codex:
        setup = state_dir / "codex_setup.txt"
        _write_codex_setup_file(setup, command)
        return ConfigChange(
            "codex",
            "manual-required",
            path,
            command=command,
            message=f"Codex CLI not found; command saved to {setup}",
        )

    backup = _backup_existing(path) if path.exists() else None
    try:
        if existing is not None:
            _run_codex(("codex", "mcp", "remove", _CLIENT_ENTRY_NAME), variables)
        _run_codex(command, variables)
    except ConfiguratorError:
        if backup is not None:
            _atomic_write(path, backup.read_bytes())
        raise
    return ConfigChange("codex", "configured", path, backup, command)


def configure_clients(
    *,
    client: str,
    server: str | os.PathLike[str] | None,
    workspace: str | os.PathLike[str] | None,
    state_dir: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None = None,
    dry_run: bool = False,
    unconfigure: bool = False,
    restore_backup: bool = False,
) -> list[ConfigChange]:
    if client not in {"codex", "claude", "both", "none"}:
        raise ConfiguratorError(f"Unsupported client selection: {client}")
    if client == "none":
        return [ConfigChange("none", "skipped", message="client configuration was skipped")]
    if server is None or workspace is None:
        if unconfigure or restore_backup:
            server_path = Path(server) if server else Path("diptrace_mcp_server.exe")
            workspace_path = Path(workspace) if workspace else Path.cwd()
        else:
            raise ConfiguratorError(
                "--server and --workspace are required for client configuration"
            )
    else:
        server_path = validate_server_path(server)
        workspace_path = validate_workspace(workspace, create=False)
    variables = os.environ if env is None else env
    state_path = validate_state_dir(
        state_dir or _default_state_dir(variables),
        create=not dry_run and not (unconfigure or restore_backup),
    )
    # Preflight every selected client before mutating any of them. This keeps a
    # malformed Claude file from leaving Codex changed when --client both is
    # selected, and likewise fails closed for an invalid Codex TOML file.
    if client in {"codex", "both"}:
        _load_toml(_codex_config_path(variables))
    if client in {"claude", "both"}:
        _load_json_object(_claude_config_path(variables))
    changes: list[ConfigChange] = []
    if client in {"codex", "both"}:
        changes.append(
            configure_codex(
                server=server_path,
                workspace=workspace_path,
                state_dir=state_path,
                env=variables,
                dry_run=dry_run,
                unconfigure=unconfigure,
                restore_backup=restore_backup,
            )
        )
    if client in {"claude", "both"}:
        changes.append(
            configure_claude(
                server=server_path,
                workspace=workspace_path,
                state_dir=state_path,
                env=variables,
                dry_run=dry_run,
                unconfigure=unconfigure,
                restore_backup=restore_backup,
            )
        )
    return changes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Configure DipTrace MCP clients safely")
    parser.add_argument("--client", choices=("codex", "claude", "both", "none"), required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--state-dir")
    parser.add_argument("--server")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--unconfigure", action="store_true")
    parser.add_argument("--restore-backup", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        changes = configure_clients(
            client=args.client,
            server=args.server,
            workspace=args.workspace,
            state_dir=args.state_dir,
            dry_run=args.dry_run,
            unconfigure=args.unconfigure,
            restore_backup=args.restore_backup,
        )
        payload = {"ok": True, "changes": [change.as_dict() for change in changes]}
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            for change in changes:
                print(f"{change.client}: {change.status} — {change.message}".rstrip(" —"))
        return 0
    except ConfiguratorError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"Configuration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
