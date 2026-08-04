#!/usr/bin/env python3
"""Build a deterministic Windows MCPB from the frozen server directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

REPO_ROOT = Path(__file__).absolute().parents[1]
TEMPLATE = REPO_ROOT / "packaging" / "mcpb" / "manifest.template.json"
README_FIRST = REPO_ROOT / "packaging" / "mcpb" / "README_FIRST.md"
LICENSE = REPO_ROOT / "LICENSE"
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


class McpbBuildError(ValueError):
    """Raised when bundle inputs or output violate the packaging contract."""


def project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str) or not version.strip():
        raise McpbBuildError("project.version is missing")
    return version


def _safe_relative(root: Path, path: Path) -> PurePosixPath:
    relative = path.relative_to(root)
    if path.is_symlink() or any(part in {"", ".", ".."} for part in relative.parts):
        raise McpbBuildError(f"unsafe bundle path: {path}")
    return PurePosixPath(relative.as_posix())


def _assert_source_tree(server_dir: Path) -> Path:
    if server_dir.is_symlink():
        raise McpbBuildError("server directory must not be a symlink")
    resolved = server_dir.resolve()
    executable = resolved / "diptrace_mcp_server.exe"
    if not resolved.is_dir() or not executable.is_file():
        raise McpbBuildError(
            "server directory must contain diptrace_mcp_server.exe: " f"{resolved}"
        )
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise McpbBuildError(f"server tree contains a symlink: {path}")
    return resolved


def _manifest(version: str) -> dict[str, object]:
    raw = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise McpbBuildError("manifest template root must be an object")
    data = cast(dict[str, object], raw)
    if data.get("version") != "__VERSION__":
        raise McpbBuildError("manifest template version placeholder is missing")
    data["version"] = version
    return data


def _write_zip(stage: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    files = sorted(
        (path for path in stage.rglob("*") if path.is_file()),
        key=lambda path: _safe_relative(stage, path).as_posix(),
    )
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            relative = _safe_relative(stage, path)
            info = zipfile.ZipInfo(relative.as_posix(), FIXED_ZIP_TIME)
            mode = 0o755 if path.suffix.lower() == ".exe" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())


def build_bundle(server_dir: Path, output_dir: Path, version: str) -> tuple[Path, str]:
    server_dir = _assert_source_tree(server_dir)

    with tempfile.TemporaryDirectory(prefix="diptrace-mcpb-") as raw_stage:
        stage = Path(raw_stage)
        shutil.copytree(server_dir, stage / "server", symlinks=False)
        (stage / "manifest.json").write_text(
            json.dumps(_manifest(version), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(README_FIRST, stage / "README_FIRST.md")
        shutil.copy2(LICENSE, stage / "LICENSE")
        output = output_dir.resolve() / f"DipTrace-MCP-{version}-windows.mcpb"
        _write_zip(stage, output)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return output, digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server-dir",
        type=Path,
        default=REPO_ROOT / "dist" / "windows-server" / "diptrace_mcp_server",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "dist" / "mcpb",
    )
    parser.add_argument("--version", default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    version = args.version or project_version()
    output, digest = build_bundle(args.server_dir, args.output_dir, version)
    print(json.dumps({"bundle": str(output), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, McpbBuildError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
