from __future__ import annotations

import json
from pathlib import Path

from diptrace_mcp import __version__

ROOT = Path(__file__).parents[1]


def test_frozen_server_delegates_to_production_main() -> None:
    source = (ROOT / "src/diptrace_mcp/frozen_server.py").read_text(encoding="utf-8")

    assert "from diptrace_mcp.server import main" in source
    assert "server.run" not in source


def test_server_spec_is_explicit_and_uses_onedir_collect() -> None:
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")

    assert "Analysis(" in spec
    assert "COLLECT(" in spec
    assert 'name="diptrace_mcp_server"' in spec
    assert 'collect_submodules(\n        "mcp.server",' in spec
    assert 'collect_submodules(\n        "mcp.shared",' in spec
    assert 'collect_submodules("diptrace_mcp")' in spec
    assert 'copy_metadata("mcp")' in spec
    assert "tests" not in spec.split("excludes =", 1)[1].split("]", 1)[0]
    assert "onefile" not in spec.lower()


def test_packaging_constraints_pin_pyinstaller_and_geometry_inputs() -> None:
    constraints = (ROOT / "packaging/windows-constraints.txt").read_text(encoding="utf-8")

    assert "pyinstaller==6.14.2" in constraints
    assert "shapely==2.1.2" in constraints
    assert "mcp==1.28.1" in constraints


def test_server_version_contract_is_stable() -> None:
    assert __version__ == "0.2.0"


def test_runtime_registry_is_json_and_spec_does_not_collect_forbidden_sources() -> None:
    registry = json.loads(
        (ROOT / "src/diptrace_mcp/data/trusted_provenance_registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(registry, dict)
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")
    assert "tests/fixtures" not in spec
    assert "reference/diptrace-xml/sources" not in spec
    assert "reference/diptrace-xml/extracted_text" not in spec


def test_skill_data_destinations_are_directories_without_filename_duplication() -> None:
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")

    assert "relative.parent" in spec
    assert "relative_to(directory).as_posix()" not in spec
