from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import diptrace_mcp.config as config_module
import diptrace_mcp.error_boundary as error_boundary
import diptrace_mcp.evidence_status as evidence_status
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.connectivity import build_connectivity_graph
from diptrace_mcp.errors import (
    CapabilityUnavailableError,
    DocumentError,
    ObjectNotFoundError,
    SessionError,
)
from diptrace_mcp.jobs import JobStore
from diptrace_mcp.numeric_inputs import xml_integer
from diptrace_mcp.policy import Policy
from diptrace_mcp.previews import RawPreviewStore
from diptrace_mcp.record_ids import InvalidRecordPath
from diptrace_mcp.services.context import (
    DocumentGateway,
    bounded_text,
    json_size,
    validate_page,
)
from diptrace_mcp.services.discovery import DiscoveryService
from diptrace_mcp.services.jobs import JobService
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.via_styles import (
    resolve_via_span,
    select_via_style,
    validate_via_geometry,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _settings(tmp_path: Path, *, max_scan_files: int = 100) -> Settings:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return Settings(
        workspace=workspace,
        allowed_roots=(workspace,),
        state_dir=tmp_path / "state",
        max_document_bytes=10_000_000,
        max_scan_files=max_scan_files,
    )


def test_context_gateway_missing_active_and_document_identity_guards(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sessions = SessionStore(
        settings.state_dir,
        settings.max_document_bytes,
        allowed_roots=settings.allowed_roots,
    )
    gateway = DocumentGateway(settings, sessions)

    with pytest.raises(ObjectNotFoundError, match="does not exist"):
        gateway.resolve_target(str(settings.workspace / "missing.xml"))
    with pytest.raises(SessionError, match="No active DipTrace session"):
        gateway.resolve_target(None)
    with pytest.raises(DocumentError, match="not registered"):
        gateway.load_document_id("document_deadbeefdeadbeef")

    board = settings.workspace / "board.xml"
    shutil.copyfile(FIXTURES / "pcb.xml", board)
    document, target = gateway.load(str(board))
    assert target.is_live is False
    document_id = next(iter(gateway.targets))
    loaded, loaded_target = gateway.load_document_id(document_id)
    assert loaded.sha256 == document.sha256
    assert loaded_target.path == board.resolve()

    board.write_bytes(FIXTURES.joinpath("schematic.xml").read_bytes())
    with pytest.raises(DocumentError, match="identity changed"):
        gateway.load_document_id(document_id)


def test_context_small_helpers_cover_bounds_and_unicode() -> None:
    encoded = json.dumps({"é": "x"}, ensure_ascii=False, sort_keys=True).encode()
    assert json_size({"é": "x"}) == len(encoded)
    assert bounded_text("abc", 3) == ("abc", False)
    assert bounded_text("abcdef", 3) == ("abc", True)
    validate_page(0, 1)
    validate_page(1, 500)
    with pytest.raises(DocumentError, match="offset"):
        validate_page(-1, 1)
    with pytest.raises(DocumentError, match="limit"):
        validate_page(0, 501)


def test_discovery_scans_valid_headers_filters_and_truncates(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_scan_files=2)
    root = settings.workspace
    shutil.copyfile(FIXTURES / "component_library.xml", root / "a.xml")
    shutil.copyfile(FIXTURES / "pattern_library.xml", root / "b.lib")
    (root / "bad.xml").write_text("<not-diptrace />", encoding="utf-8")
    (root / "ignored.txt").write_text("text", encoding="utf-8")
    nested = root / "nested"
    nested.mkdir()
    shutil.copyfile(FIXTURES / "pcb.xml", nested / "c.dip")

    service = DiscoveryService(settings)
    recursive = service.scan_documents(recursive=True)
    assert recursive["examined_candidates"] <= 2
    assert recursive["truncated"] is True
    assert all(item["type"].startswith("DipTrace-") for item in recursive["documents"])

    nonrecursive = DiscoveryService(_settings(tmp_path / "other", max_scan_files=100))
    nonrecursive.settings.workspace.joinpath("plain.xml").write_text(
        "<Source Type='Other'/>",
        encoding="utf-8",
    )
    assert nonrecursive.scan_documents(recursive=False)["documents"] == []

    file_root = root / "a.xml"
    with pytest.raises(DocumentError, match="not a directory"):
        service.scan_documents(str(file_root))


def test_discovery_header_reader_handles_io_and_library_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    service = DiscoveryService(settings)
    library = settings.workspace / "component.xml"
    shutil.copyfile(FIXTURES / "component_library.xml", library)
    header = service._read_source_header(library)
    assert header is not None
    assert header["type"] == "DipTrace-ComponentLibrary"

    original_open = Path.open

    def fail_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == library:
            raise OSError("busy")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)
    assert service._read_source_header(library) is None

    monkeypatch.setattr(Path, "open", original_open)
    filtered = service._scan_libraries("DipTrace-ComponentLibrary", None, True)
    assert filtered["result"]["matched_count"] == 1


def test_job_service_status_result_listing_resources_and_cancel(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JobStore(settings.state_dir)
    record = store.create(job_type="coverage")
    store.store_artifact(record.jobid, "log.txt", b"0123456789")
    store.store_artifact(record.jobid, "manifest.json", b"{}")
    store.update(
        record.jobid,
        status="completed",
        phase="completed",
        progress=1.0,
        result={"answer": 42},
        partial_result={"partial": True},
        warnings=["warning"],
    )

    class FakeManager:
        def cancel(self, jobid: str) -> Any:
            return store.update(jobid, status="cancelled", phase="cancelled")

    service = JobService(settings, store, FakeManager())
    status = service.get_job_status(record.jobid)
    assert status["result"]["job"]["status"] == "completed"
    result = service.get_job_result(record.jobid)
    assert result["result"]["result"] == {"answer": 42}
    assert service.list_jobs()["result"]["matched_count"] == 1
    assert service.list_jobs("completed")["result"]["matched_count"] == 1
    with pytest.raises(DocumentError, match="Unknown job status"):
        service.list_jobs("mystery")

    assert "completed" in service.job_resource(record.jobid, "status")
    assert "answer" in service.job_resource(record.jobid, "result")
    assert service.job_resource(record.jobid, "manifest.json") == "{}"
    assert service.job_resource(record.jobid, "output.ses") == ""
    with pytest.raises(CapabilityUnavailableError, match="Unknown job resource"):
        service.job_resource(record.jobid, "unknown")

    cancelled = service.cancel_job(record.jobid)
    assert cancelled["result"]["job"]["status"] == "cancelled"


def test_job_log_resource_is_tail_bounded(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    object.__setattr__(settings, "max_external_log_bytes", 4)
    store = JobStore(settings.state_dir)
    record = store.create(job_type="coverage")
    store.store_artifact(record.jobid, "log.txt", b"0123456789")
    service = JobService(settings, store, SimpleNamespace(cancel=lambda _jobid: record))
    assert service.job_resource(record.jobid, "log") == "6789"


def test_config_platform_translation_and_state_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if config_module.os.name != "nt":
        assert config_module.platform_path(r"C:\Users\tester\board.xml") == Path(
            "/mnt/c/Users/tester/board.xml"
        )

    configured_state = tmp_path / "configured-state"
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(configured_state))
    assert config_module._default_state_dir(tmp_path) == configured_state.resolve()

    monkeypatch.delenv("DIPTRACE_MCP_STATE_DIR", raising=False)
    if config_module.os.name == "nt":
        local_app_data = config_module.os.environ.get("LOCALAPPDATA")
        assert local_app_data is not None
        expected = (Path(local_app_data) / "DipTraceMCP").resolve()
    else:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
        expected = (tmp_path / "xdg" / "diptrace-mcp").resolve()
    assert config_module._default_state_dir(tmp_path) == expected


def test_policy_evidence_and_numeric_success_tails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Policy("interactive_edit").require_external_execution(operation="coverage")

    monkeypatch.setattr(evidence_status, "Q1_COMPONENT_ANGLE_LIVE_VALIDATED", True)
    assert evidence_status.component_angle_evidence_warnings() == []

    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    element = next(item for item in document.root.iter() if item.get("Id") is not None)
    assert xml_integer(document, element, "Id") == int(element.get("Id", "0"))


def test_connectivity_rejects_non_design_documents() -> None:
    document = DipTraceDocument.load(FIXTURES / "component_library.xml", 10_000_000)
    snapshot = build_snapshot(document)
    with pytest.raises(CapabilityUnavailableError, match="PCB or schematic"):
        build_connectivity_graph(snapshot)


def test_via_style_selection_and_geometry_fail_closed() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    assert snapshot.board is not None
    board = snapshot.board
    assert board.via_styles
    style = board.via_styles[0]

    with pytest.raises(ObjectNotFoundError, match="not found"):
        select_via_style(board, "missing-via-style")

    duplicate = style.model_copy(update={"id": "duplicate-style", "name": style.name})
    board.via_styles.append(duplicate)
    with pytest.raises(Exception, match="ambiguous"):
        select_via_style(board, style.name)
    board.via_styles.pop()

    invalid_geometry = style.model_copy(update={"diameter_mm": 0.1, "hole_mm": 0.2})
    with pytest.raises(Exception, match="valid exported diameter"):
        validate_via_geometry(invalid_geometry)

    invalid_explicit = style.model_copy(
        update={"span_source": "explicit", "span_layer_ids": ("missing-a", "missing-b")}
    )
    with pytest.raises(Exception, match="invalid copper-layer span"):
        resolve_via_span(board, invalid_explicit)

    invalid_source = style.model_copy(update={"span_source": "invalid"})
    with pytest.raises(Exception, match="incomplete or invalid"):
        resolve_via_span(board, invalid_source)


def test_raw_preview_retention_and_record_path_guards(tmp_path: Path) -> None:
    store = RawPreviewStore(tmp_path / "state")
    cases = (
        ("1" * 32, "{bad-json"),
        ("2" * 32, "[]"),
        ("3" * 32, json.dumps({"preview_id": "preview_" + "4" * 32, "created_at": "now"})),
        ("4" * 32, json.dumps({"preview_id": "preview_" + "4" * 32, "created_at": "not-a-time"})),
    )
    for suffix, metadata in cases:
        directory = store.previews_dir / f"preview_{suffix}"
        directory.mkdir()
        (directory / "metadata.json").write_text(metadata, encoding="utf-8")

    report = store._prune_retention()
    assert report.removed == ()

    with pytest.raises(DocumentError, match="Invalid raw preview id"):
        store.preview_dir("not-a-preview")

    with pytest.raises(InvalidRecordPath, match="store root"):
        store._require_safe_output_path(store.previews_dir)

    missing_parent = store.previews_dir / ("preview_" + "5" * 32) / "artifact.json"
    with pytest.raises(InvalidRecordPath, match="unavailable"):
        store._require_safe_output_path(missing_parent)

    directory = store.previews_dir / ("preview_" + "6" * 32)
    directory.mkdir()
    artifact_directory = directory / "artifact.json"
    artifact_directory.mkdir()
    with pytest.raises(InvalidRecordPath, match="not a regular file"):
        store._require_safe_output_path(artifact_directory)

    outside = tmp_path / "outside" / "artifact.json"
    outside.parent.mkdir()
    with pytest.raises(InvalidRecordPath, match="outside"):
        store._require_safe_output_path(outside)

    target = directory / "target.json"
    target.write_text("{}", encoding="utf-8")
    redirected = directory / "redirected.json"
    try:
        redirected.symlink_to(target)
    except OSError:
        return
    with pytest.raises(InvalidRecordPath, match="redirected"):
        store._require_safe_output_path(redirected)


def test_error_boundary_sanitizes_deep_and_non_scalar_details() -> None:
    deeply_nested: object = "leaf"
    for _ in range(6):
        deeply_nested = {"level": deeply_nested}
    sanitized = error_boundary._safe_value(deeply_nested)
    assert "[details truncated]" in repr(sanitized)
    assert error_boundary._safe_value(float("inf")) is None
    assert error_boundary._safe_value(("a", "b")) == ["a", "b"]

    class UnsafeValue:
        def __str__(self) -> str:
            return "/tmp/private/board.xml"

    assert "[path redacted]" in error_boundary._safe_value(UnsafeValue())
