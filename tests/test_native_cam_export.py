from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from diptrace_mcp import native_cam_export as cam
from diptrace_mcp.xml_document import sha256_bytes


def test_manifest_requires_actual_native_outputs_and_records_partial_files(tmp_path):
    (tmp_path / "native-placement.csv").write_text("RefDes,X,Y\nR1,1,2\n")
    result = cam.manufacturing_manifest(tmp_path)
    assert result["complete"] is False
    assert result["fabrication_approved"] is False
    assert result["files"][0]["sha256"] == sha256_bytes(
        (tmp_path / "native-placement.csv").read_bytes()
    )
    assert "native-fabrication.zip" in str(result["errors"])


def test_manifest_inspects_zip_members_without_extracting(tmp_path):
    # Synthetic CAM signatures test the validator, not DipTrace export evidence.
    with zipfile.ZipFile(tmp_path / "native-fabrication.zip", "w") as archive:
        archive.writestr("top.gbr", "%FSLAX24Y24*%\nM02*\n")
        archive.writestr("holes.drl", "M48\nMETRIC,TZ\n%\nM30\n")
    (tmp_path / "native-placement.csv").write_text("RefDes,X,Y\nR1,1,2\n")
    result = cam.manufacturing_manifest(tmp_path)
    assert result["complete"] is True
    assert {item["kind"] for item in result["archive_members"]} == {"gerber", "nc_drill"}
    assert result["fabrication_approved"] is False
    assert not (tmp_path / "top.gbr").exists()


@pytest.mark.parametrize("member", [
    "../escape.gbr", "/absolute.gbr", "C:/escape.gbr", "a\\escape.gbr",
])
def test_manifest_rejects_unsafe_archive_names(tmp_path, member):
    with zipfile.ZipFile(tmp_path / "native-fabrication.zip", "w") as archive:
        archive.writestr(member, "%FSLAX24Y24*%\nM02*\n")
    assert cam.manufacturing_manifest(tmp_path)["complete"] is False


def _request(tmp_path):
    source = tmp_path / "board.dipxml"
    shutil.copy(Path(__file__).parent / "fixtures/pcb.xml", source)
    return cam.NativeCadRequest(
        source=source, output_dir=tmp_path / "output", diptrace_root=tmp_path / "DipTrace",
        expected_sha256=sha256_bytes(source.read_bytes()), export_manufacturing=True,
    )


def test_wrapper_keeps_partial_failure_evidence_and_never_claims_release(tmp_path, monkeypatch):
    request = _request(tmp_path)
    original = request.source.read_bytes()

    def fake_native(request):
        assert request.export_manufacturing is True
        request.output_dir.mkdir()
        (request.output_dir / "native-result.json").write_text('{"completed": false}')
        (request.output_dir / "native-placement.csv").write_text("partial")
        raise RuntimeError("native export interrupted")

    monkeypatch.setattr(cam, "run_native_cad", fake_native)
    result = cam.export_native_cam(request)
    assert result["completed"] is False
    assert result["fabrication_approved"] is False
    assert "interrupted" in result["error"]
    manifest = json.loads((request.output_dir / "cam-manifest.json").read_text())
    assert manifest["source_sha256"] == request.expected_sha256
    assert manifest["files"]
    assert request.source.read_bytes() == original


def test_wrapper_refuses_missing_frozen_helper_before_launch(tmp_path, monkeypatch):
    from diptrace_mcp.errors import ExternalToolUnavailableError

    request = _request(tmp_path)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / 'server.exe'))
    monkeypatch.setattr(cam, "run_native_cad", lambda _: pytest.fail("must not launch"))
    with pytest.raises(ExternalToolUnavailableError, match="missing"):
        cam.export_native_cam(request)


def test_wrapper_supports_frozen_helper_dispatch(tmp_path, monkeypatch):
    request = _request(tmp_path)
    helper = tmp_path / 'tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe'
    helper.parent.mkdir(parents=True)
    helper.touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'server.exe'))
    launched = []
    monkeypatch.setattr(cam, 'run_native_cad',
                        lambda request: launched.append(request) or {'completed': False})
    assert cam.export_native_cam(request)['completed'] is False
    assert len(launched) == 1


def test_wrapper_refuses_stale_sha_and_schematic(tmp_path, monkeypatch):
    request = _request(tmp_path)
    monkeypatch.setattr(cam, "run_native_cad", lambda _: pytest.fail("must not launch"))
    with pytest.raises(cam.HeadlessGuiError, match="hash"):
        cam.export_native_cam(request.model_copy(update={"expected_sha256": "0" * 64}))
    schematic = tmp_path / "schematic.xml"
    shutil.copy(Path(__file__).parent / "fixtures/schematic.xml", schematic)
    with pytest.raises(cam.HeadlessGuiError, match="PCB"):
        cam.export_native_cam(request.model_copy(update={
            "source": schematic, "expected_sha256": sha256_bytes(schematic.read_bytes()),
        }))


def test_wrapper_success_still_does_not_approve_fabrication(tmp_path, monkeypatch):
    request = _request(tmp_path)

    def fake_native(request):
        request.output_dir.mkdir()
        with zipfile.ZipFile(request.output_dir / "native-fabrication.zip", "w") as archive:
            archive.writestr("top.gbr", "%FSLAX24Y24*%\nM02*\n")
            archive.writestr("holes.drl", "M48\nMETRIC,TZ\n%\nM30\n")
        (request.output_dir / "native-placement.csv").write_text("RefDes,X,Y\nR1,1,2\n")
        return {"completed": True, "drc_status": "fail", "fabrication_approved": False}

    monkeypatch.setattr(cam, "run_native_cad", fake_native)
    result = cam.export_native_cam(request)
    assert result["completed"] is True  # Export evidence, deliberately not DRC acceptance.
    assert result["fabrication_approved"] is False
    assert result["native_report"]["drc_status"] == "fail"
    assert result["manifest"]["source_unchanged"] is True


def test_manifest_rejects_corrupt_archive_and_oversized_files(tmp_path, monkeypatch):
    (tmp_path / "native-fabrication.zip").write_bytes(b"not a zip")
    (tmp_path / "native-placement.csv").write_text("RefDes,X,Y\nR1,1,2\n")
    assert "inspection failed" in str(cam.manufacturing_manifest(tmp_path)["errors"])
    monkeypatch.setattr(cam, "MAX_CAM_BYTES", 1)
    assert "oversized" in str(cam.manufacturing_manifest(tmp_path)["errors"])


def test_manifest_keeps_errors_for_corrupt_deflate_stream(tmp_path):
    path = tmp_path / "native-fabrication.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("top.gbr", "%FSLAX24Y24*%\n" * 50)
        item = archive.getinfo("top.gbr")
    data = bytearray(path.read_bytes())
    offset = item.header_offset + 30 + len(item.filename.encode()) + len(item.extra)
    data[offset] = 0x07  # Final block with the reserved DEFLATE block type.
    path.write_bytes(data)
    (tmp_path / "native-placement.csv").write_text("RefDes,X,Y\nR1,1,2\n")
    manifest = cam.manufacturing_manifest(tmp_path)
    assert manifest["complete"] is False
    assert any("archive inspection failed" in error for error in manifest["errors"])


def test_wrapper_refuses_existing_output_without_launching(tmp_path, monkeypatch):
    request = _request(tmp_path)
    request.output_dir.mkdir()
    marker = request.output_dir / "keep.txt"
    marker.write_text("keep")
    monkeypatch.setattr(cam, "run_native_cad", lambda _: pytest.fail("must not launch"))
    with pytest.raises(cam.HeadlessGuiError, match="new output"):
        cam.export_native_cam(request)
    assert marker.read_text() == "keep"
