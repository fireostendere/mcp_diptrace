from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]


def test_build_mcpb_and_checksum(tmp_path: Path) -> None:
    server = tmp_path / "server-build"
    (server / "_internal").mkdir(parents=True)
    (server / "diptrace_mcp_server.exe").write_bytes(b"fake executable")
    (server / "_internal" / "runtime.dat").write_bytes(b"runtime")
    output = tmp_path / "output"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_mcpb.py"),
            "--server-dir",
            str(server),
            "--output-dir",
            str(output),
            "--version",
            "9.8.7",
        ],
        cwd=ROOT,
        check=True,
    )

    bundle = output / "DipTrace-MCP-9.8.7-windows.mcpb"
    checksum = output / "DipTrace-MCP-9.8.7-windows.mcpb.sha256"
    assert bundle.is_file()
    expected = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="utf-8") == f"{expected}  {bundle.name}\n"

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "manifest.json" in names
        assert "server/diptrace_mcp_server.exe" in names
        assert "server/_internal/runtime.dat" in names
        assert all(
            not name.startswith("/") and ".." not in Path(name).parts for name in names
        )
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["manifest_version"] == "0.3"
    assert manifest["version"] == "9.8.7"
    assert manifest["server"]["type"] == "binary"
    assert manifest["server"]["entry_point"] == "server/diptrace_mcp_server.exe"
    assert manifest["compatibility"]["platforms"] == ["win32"]
    assert manifest["user_config"]["workspace"]["required"] is True


def test_generate_registry_server_json(tmp_path: Path) -> None:
    bundle = tmp_path / "DipTrace-MCP-9.8.7-windows.mcpb"
    bundle.write_bytes(b"bundle")
    output = tmp_path / "server.json"
    url = (
        "https://github.com/fireostendere/mcp_diptrace/releases/download/"
        "v9.8.7/DipTrace-MCP-9.8.7-windows.mcpb"
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_registry_server_json.py"),
            "--version",
            "9.8.7",
            "--mcpb-url",
            url,
            "--mcpb-file",
            str(bundle),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    package = data["packages"][0]
    assert data["name"] == "io.github.fireostendere/diptrace-mcp"
    assert data["version"] == "9.8.7"
    assert package["registryType"] == "mcpb"
    assert package["identifier"] == url
    assert package["transport"] == {"type": "stdio"}
    assert package["fileSha256"] == hashlib.sha256(b"bundle").hexdigest()


def test_registry_generator_rejects_non_https_url(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_registry_server_json.py"),
            "--version",
            "1.0.0",
            "--mcpb-url",
            "http://example.test/server.mcpb",
            "--mcpb-sha256",
            "0" * 64,
            "--output",
            str(tmp_path / "server.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "public HTTPS URL" in result.stderr
