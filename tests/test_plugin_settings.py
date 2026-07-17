import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings


def test_plugin_settings_match_official_structure() -> None:
    root = Path(__file__).parents[1] / "plugin" / "settings"
    pcb = ET.parse(root / "pcb.settings.xml").getroot()
    schematic = ET.parse(root / "schematic.settings.xml").getroot()

    assert pcb.tag == "Source"
    assert pcb.get("Type") == "DipTrace_Pcb_Plugin"
    assert pcb.findtext("./Settings/ExpMode") == "All"
    assert pcb.findtext("./Settings/ImpMode") == "All"
    assert schematic.get("Type") == "DipTrace_Schematic_Plugin"
    assert schematic.findtext("./Settings/Patterns") == "Yes"


def test_installer_prefers_current_diptrace_directory() -> None:
    script = (
        Path(__file__).parents[1] / "plugin" / "install_plugin.ps1"
    ).read_text(encoding="utf-8")

    assert 'Join-Path $env:ProgramFiles "DipTrace5"' in script
    assert script.index('Join-Path $env:ProgramFiles "DipTrace5"') < script.index(
        'Join-Path $env:ProgramFiles "DipTrace"'
    )
    assert "Pass -DipTraceDir explicitly" in script


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
