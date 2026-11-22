"""Native CAM helper; native outputs are evidence, never release approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

from .headless_gui import HeadlessGuiError
from .native_cad import NativeCadRequest, run_native_cad
from .native_helper import helper_command
from .xml_document import DipTraceDocument

MAX_CAM_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def _file_digest(path: Path, limit: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            if size > limit:
                raise ValueError("Native file exceeds inspection bound")
            digest.update(chunk)
    return size, digest.hexdigest()


def manufacturing_manifest(directory: Path) -> dict[str, Any]:
    """Hash actual files and inspect bounded ZIP contents without extracting them."""
    files: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    errors: list[str] = []
    for name in ("native-fabrication.zip", "native-placement.csv"):
        path = directory / name
        if directory.is_symlink() or path.is_symlink() or not path.is_file():
            errors.append(f"Missing or redirected native output: {name}")
            continue
        size = path.stat().st_size
        if not 0 < size <= MAX_CAM_BYTES:
            errors.append(f"Empty or oversized native output: {name}")
            continue
        try:
            size, digest = _file_digest(path, MAX_CAM_BYTES)
        except (OSError, ValueError) as exc:
            errors.append(f"Native output inspection failed: {name}: {exc}")
            continue
        files.append({"path": name, "size_bytes": size, "sha256": digest})
        if name != "native-fabrication.zip":
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if (len(entries) > 512
                        or sum(item.file_size for item in entries) > MAX_ARCHIVE_BYTES):
                    raise ValueError("Native archive exceeds inspection bounds")
                seen: set[str] = set()
                for item in entries:
                    member = PurePosixPath(item.filename)
                    if (member.is_absolute() or ".." in member.parts
                            or ":" in item.filename or "\\" in item.filename
                            or item.filename in seen
                            or stat.S_ISLNK(item.external_attr >> 16)):
                        raise ValueError("Unsafe or duplicate native archive member")
                    seen.add(item.filename)
                    if item.is_dir():
                        continue
                    member_hasher = hashlib.sha256()
                    prefix = b""
                    size = 0
                    with archive.open(item) as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            size += len(chunk)
                            if size > MAX_CAM_BYTES:
                                raise ValueError("Native archive member exceeds inspection bound")
                            prefix = (prefix + chunk)[:4096]
                            member_hasher.update(chunk)
                    kind = ("gerber" if b"%FS" in prefix or b"%MO" in prefix else
                            "nc_drill" if b"M48" in prefix else "other")
                    members.append({"path": item.filename, "size_bytes": size,
                                    "sha256": member_hasher.hexdigest(), "kind": kind})
        except (OSError, ValueError, RuntimeError, NotImplementedError,
                zipfile.BadZipFile, zlib.error, EOFError) as exc:
            errors.append(f"Native archive inspection failed: {exc}")
    for kind in ("gerber", "nc_drill"):
        if not any(item["kind"] == kind for item in members):
            errors.append(f"No recognizable {kind} content in native archive")
    return {
        "schema_version": 1, "complete": not errors, "files": files,
        "archive_members": members, "errors": errors, "fabrication_approved": False,
        "limitations": [
            "Signatures and CRC reads are not CAM layer, drill alignment or DFM validation.",
            "Placement is hashed raw native CSV; columns, populations and rotations need review.",
        ],
    }


def export_native_cam(request: NativeCadRequest) -> dict[str, Any]:
    helper_command("native-cad-worker")  # Fail closed before creating output if bundle is absent.
    if (request.source.is_symlink() or request.output_dir.exists()
            or request.output_dir.is_symlink()):
        raise HeadlessGuiError("CAM requires a regular source and a new output directory")
    source = DipTraceDocument.load(request.source, 64 * 1024 * 1024)
    if source.kind != "pcb":
        raise HeadlessGuiError("Native CAM requires PCB XML")
    if source.sha256 != request.expected_sha256:
        raise HeadlessGuiError("Native CAM input hash is stale")
    request = request.model_copy(update={"export_manufacturing": True})
    try:
        report = run_native_cad(request)
    except Exception as exc:
        report = {"completed": False, "error": f"{type(exc).__name__}: {exc}"}
    manifest = manufacturing_manifest(request.output_dir)
    manifest["source_sha256"] = source.sha256
    try:
        manifest["source_unchanged"] = (
            not request.source.is_symlink()
            and _file_digest(request.source, 64 * 1024 * 1024)[1] == source.sha256
        )
    except (OSError, ValueError):
        manifest["source_unchanged"] = False
    result = {
        "completed": bool(report.get("completed") and manifest["complete"]
                          and manifest["source_unchanged"]),
        "fabrication_approved": False, "native_report": report, "manifest": manifest,
    }
    if "error" in report:
        result["error"] = report["error"]
    if request.output_dir.is_dir() and not request.output_dir.is_symlink():
        (request.output_dir / "cam-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8",
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--diptrace-root", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    result = export_native_cam(NativeCadRequest(
        source=args.project, output_dir=args.output_dir, diptrace_root=args.diptrace_root,
        expected_sha256=args.expected_sha256, timeout_seconds=args.timeout,
        export_manufacturing=True,
    ))
    print(json.dumps(result, indent=2))
    return 0 if result["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
