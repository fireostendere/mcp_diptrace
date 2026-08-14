from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_inno_installer_is_user_scoped_and_has_required_wizard_contracts() -> None:
    script = (ROOT / "installer/DipTraceMCP.iss").read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in script
    assert "DefaultDirName={localappdata}\\Programs\\DipTraceMCP" in script
    assert "OutputBaseFilename=DipTrace-MCP-Setup-{#AppVersion}" in script
    assert "Name: full;" in script
    assert "Name: server;" in script
    assert "Name: custom;" in script
    assert "Configure Codex" in script
    assert "Configure Claude Desktop" in script
    assert "Configure both" in script
    assert "Skip client configuration" in script
    assert "settings-templates\\*" in script
    assert "diptrace_mcp_server.exe" in script
    assert "--help" in script
    assert "--json" in script
    assert "runas" in script
    assert "Remove local DipTrace MCP state and logs" in script
    assert "Projects are never removed".casefold() in script.casefold()
    assert 'Type: files; Name: "{app}\\plugin-targets.txt"' in script
    assert 'Type: files; Name: "{app}\\state-dir.txt"' in script
    assert 'Type: dirifempty; Name: "{app}"' in script
    assert "{autopf}" not in script
    assert "{autopf32}" not in script
    assert "{commonpf}" in script
    assert "{commonpf32}" in script
    assert "PrivilegesRequired=admin" not in script


def test_installer_has_no_network_or_shell_pipeline() -> None:
    script = (ROOT / "installer/DipTraceMCP.iss").read_text(encoding="utf-8").casefold()
    wrapper = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8").casefold()

    assert "download" not in script
    assert "curl" not in script
    assert "invoke-webrequest" not in script
    assert "curl | powershell" not in wrapper
    assert "innosetup-6.4.2.exe" not in wrapper


def test_windows_build_wrapper_pins_inno_and_emits_two_named_assets() -> None:
    wrapper = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8")

    assert "6.4.2" in wrapper
    assert "DipTrace-MCP-Setup-{0}.exe" in wrapper
    assert "DipTrace-MCP-Portable-{0}.zip" in wrapper
    assert "SHA256SUMS.txt" in wrapper
    assert "artifact-inventory.json" in wrapper
    assert "SIGNING_REQUIRED" not in wrapper or "SigningRequired" in wrapper
    assert "Invoke-Checked (Join-Path $RepoRoot 'scripts\\build_windows_server.ps1')" not in wrapper
    assert "-NoGeometry:$NoGeometry" in wrapper
    assert "if (-not ($isccVersions | Where-Object" in wrapper


def test_existing_bridge_pipeline_remains_the_source_of_bridge_artifact() -> None:
    script = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8")

    assert "plugin\\build_bridge.ps1" in script
    assert "BridgePath" in script
    assert "diptrace_mcp_bridge.exe" in script
    assert "windows-constraints.txt" in (ROOT / "plugin/build_bridge.ps1").read_text(
        encoding="utf-8"
    )


def test_portable_helpers_are_python_free_and_state_removal_is_narrow() -> None:
    readme = (ROOT / "packaging/README_FIRST.txt").read_text(encoding="utf-8")
    remover = (ROOT / "packaging/remove_owned_state.ps1").read_text(encoding="utf-8")

    assert "no-Python" in readme
    assert "requires Python" not in readme
    for owned in ("logs", "sessions", "records", "offline_backups", "codex_setup.txt"):
        assert owned in remover
    assert "USERPROFILE" in remover
    assert "workspace" not in remover.casefold()


def test_plugin_detection_and_uninstall_preserve_existing_bridge_script() -> None:
    script = (ROOT / "plugin/install_plugin.ps1").read_text(encoding="utf-8")

    assert "Pcb.exe" in script
    assert "Schematic.exe" in script
    assert "Plugins\\Pcb" in script
    assert "ProgramFiles(x86)" in script
    assert "-not $Uninstall" in script
    assert (ROOT / "plugin/uninstall_plugin.ps1").is_file()


def test_state_removal_requires_matching_manifest_and_owner_marker() -> None:
    writer = (ROOT / "packaging/write_installation_manifest.ps1").read_text(encoding="utf-8")
    remover = (ROOT / "packaging/remove_owned_state.ps1").read_text(encoding="utf-8")

    assert ".diptrace-mcp-state-owner.json" in writer
    assert "installation_id" in writer
    assert "non-empty state directory" in writer
    assert "ManifestPath" in remover
    assert "state_marker_file" in remover
    assert "installation_id" in remover
    assert "owned_state_paths" in remover
    assert "-StateDir" not in remover


def test_portable_helper_uses_packaged_paths_and_compensating_rollback() -> None:
    helper = (ROOT / "packaging/install_portable.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "packaging/README_FIRST.txt").read_text(encoding="utf-8")

    assert r"bridge\diptrace_mcp_bridge.exe" in helper
    assert r"tools\diptrace_mcp_configure\diptrace_mcp_configure.exe" in helper
    assert "uninstall_plugin.ps1" in helper
    assert "install_portable.ps1" in readme
    assert r"tools\diptrace_mcp_configure\diptrace_mcp_configure.exe" in readme


def test_release_checksum_and_all_executable_signature_contracts_are_present() -> None:
    wrapper = (ROOT / "scripts/build_windows_installer.ps1").read_text(encoding="utf-8")

    assert "Write-ReleaseAssetShaManifest" in wrapper
    assert "DipTrace-MCP-Setup-{0}.exe" in wrapper
    assert "DipTrace-MCP-Portable-{0}.zip" in wrapper
    assert "diptrace_mcp_server.exe" in wrapper
    assert "diptrace_mcp_configure.exe" in wrapper
    assert "signatureTargets" in wrapper
