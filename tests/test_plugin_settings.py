import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings


def test_plugin_settings_match_official_structure() -> None:
    root = Path(__file__).parents[1] / "plugin" / "settings"
    pcb = ET.parse(root / "pcb.settings.xml").getroot()
    schematic = ET.parse(root / "schematic.settings.xml").getroot()
    component = ET.parse(root / "component.settings.xml").getroot()
    pattern = ET.parse(root / "pattern.settings.xml").getroot()

    assert pcb.tag == "Source"
    assert pcb.get("Type") == "DipTrace_Pcb_Plugin"
    assert pcb.findtext("./Settings/ExpMode") == "All"
    assert pcb.findtext("./Settings/ImpMode") == "All"
    assert schematic.get("Type") == "DipTrace_Schematic_Plugin"
    assert schematic.findtext("./Settings/Patterns") == "Yes"
    assert component.get("Type") == "DipTrace_CompEdit_Plugin"
    assert component.findtext("./Settings/ExpMode") == "Library All"
    assert component.findtext("./Settings/ImpMode") == "None"
    assert component.findtext("./Settings/Pattern") == "Yes"
    assert pattern.get("Type") == "DipTrace_PattEdit_Plugin"
    assert pattern.findtext("./Settings/ExpMode") == "Library All"
    assert pattern.findtext("./Settings/ImpMode") == "None"
    assert pattern.findtext("./Settings/Pad") == "All"


def test_installer_prefers_current_diptrace_directory() -> None:
    script = (
        Path(__file__).parents[1] / "plugin" / "install_plugin.ps1"
    ).read_text(encoding="utf-8")

    assert 'Join-Path $env:ProgramFiles "DipTrace5"' in script
    assert script.index('Join-Path $env:ProgramFiles "DipTrace5"') < script.index(
        'Join-Path $env:ProgramFiles "DipTrace"'
    )
    assert "Pass -DipTraceDir explicitly" in script
    modes = (
        'ValidateSet("PCB", "Schematic", "Component", "Pattern", '
        '"Libraries", "Both", "All")'
    )
    assert modes in script
    assert '"Plugins\\CompEdit\\DipTraceMCP"' in script
    assert '"Plugins\\PattEdit\\DipTraceMCP"' in script
    assert "Test-IsElevated" in script
    assert "Administrator elevation is required" in script
    assert "Assert-CopiedFile" in script
    assert "Get-Sha256Hex" in script
    assert "[Security.Cryptography.SHA256]::Create()" in script


@pytest.mark.skipif(os.name != "nt", reason="native PowerShell installer execution")
def test_installer_copies_and_hash_verifies_files_on_windows(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    script = root / "plugin" / "install_plugin.ps1"
    bridge = tmp_path / "bridge.exe"
    diptrace_dir = tmp_path / "DipTrace5"
    bridge.write_bytes(b"synthetic bridge executable for installer verification")
    diptrace_dir.mkdir()
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    assert powershell is not None

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-DipTraceDir",
            str(diptrace_dir),
            "-Mode",
            "PCB",
            "-BridgeExe",
            str(bridge),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    installed = diptrace_dir / "Plugins" / "Pcb" / "DipTraceMCP"
    assert (installed / "diptrace_mcp_bridge.exe").read_bytes() == bridge.read_bytes()
    assert (installed / "settings.xml").read_bytes() == (
        root / "plugin" / "settings" / "pcb.settings.xml"
    ).read_bytes()
    ET.parse(installed / "settings.xml")


@pytest.mark.skipif(os.name == "nt", reason="WSL path mapping is POSIX-only")
def test_wsl_state_directory_detection_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", "/mnt/c/users/Alice/Documents")
    monkeypatch.delenv("DIPTRACE_MCP_STATE_DIR", raising=False)

    settings = Settings.from_env()

    assert settings.state_dir == Path(
        "/mnt/c/Users/Alice/AppData/Local/DipTraceMCP"
    )


@pytest.mark.skipif(os.name != "nt", reason="native Windows path policy")
def test_windows_state_directory_uses_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(workspace))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("DIPTRACE_MCP_STATE_DIR", raising=False)

    settings = Settings.from_env()

    assert settings.state_dir == (local_app_data / "DipTraceMCP").resolve()
