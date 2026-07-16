from __future__ import annotations

import time
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import DocumentError, Sha256MismatchError
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.specctra import (
    dsn_export_limitations,
    export_dsn,
    parse_ses,
    session_to_operations,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _embedded_board_bytes() -> bytes:
    raw = (FIXTURES / "pcb.xml").read_bytes()
    marker = b'<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm" />'
    library = b"""<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm">
    <PadStyles><PadStyle Name="SMD" Type="Surface" Side="Top">
      <MainStack Shape="Rectangle" Width="1" Height="0.8" />
    </PadStyle></PadStyles>
    <Patterns>
      <Pattern PatternStyle="PatType0"><Name>RES_0603</Name><DefPad Style="SMD" />
        <Pads><Pad Id="0" Style="SMD" X="0" Y="-1"><Number>1</Number></Pad>
          <Pad Id="1" Style="SMD" X="0" Y="0"><Number>2</Number></Pad></Pads>
      </Pattern>
      <Pattern PatternStyle="PatType1"><Name>TEST_MCU</Name><DefPad Style="SMD" />
        <Pads><Pad Id="0" Style="SMD" X="0" Y="-1"><Number>1</Number></Pad>
          <Pad Id="1" Style="SMD" X="0" Y="0"><Number>2</Number></Pad></Pads>
      </Pattern>
    </Patterns><UnknownCacheData Keep="Y" />
  </Library>"""
    return raw.replace(marker, library)


def _simple_ses(*, delay_coordinates: bool = False) -> bytes:
    x2 = "21000" if delay_coordinates else "20000"
    return f"""(session "result.ses"
  (base_design "board.dsn")
  (routes
    (resolution mm 1000)
    (parser (host_cad "mock"))
    (library_out)
    (network_out
      (net "VCC"
        (wire (path "Top" 250 10000 9000 {x2} 9000)))
    )
  )
)""".encode()


def _service(
    workspace: Path,
    state_dir: Path,
    executable: Path | None = None,
) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state_dir,
            max_document_bytes=10_000_000,
            max_scan_files=100,
            freerouting_executable=executable,
            java_executable=None,
            external_timeout_seconds=10,
            max_external_log_bytes=4096,
        )
    )


def _wait_for_job(service: DipTraceService, jobid: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.jobs.read(jobid).status
        if status in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {jobid}")


def _mock_router(path: Path, ses: bytes, *, delay_seconds: float = 0.0) -> None:
    source = """#!/usr/bin/env python3
import pathlib
import sys
import time

args = sys.argv[1:]
output = pathlib.Path(args[args.index("-do") + 1])
time.sleep(DELAY)
output.write_bytes(SES)
print("mock freerouting complete")
""".replace("DELAY", repr(delay_seconds)).replace("SES", repr(ses))
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def test_dsn_export_requires_and_uses_exact_embedded_pattern_geometry(tmp_path: Path) -> None:
    incomplete = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    assert any("embedded pattern" in item for item in dsn_export_limitations(incomplete))
    board_path = tmp_path / "board.xml"
    document = DipTraceDocument.from_bytes(board_path, _embedded_board_bytes())
    snapshot = build_snapshot(document)

    first = export_dsn(snapshot, design_name="Golden Board")
    second = export_dsn(snapshot, design_name="Golden Board")

    assert first == second
    text = first.decode()
    assert text.startswith('(pcb "Golden Board"')
    assert '(resolution mm 1000)' in text
    assert '(image "PatType0"' in text
    assert '(pin "PAD_SMD" "1" 0 -1000)' in text
    assert '(pins "R1"-"1" "U1"-"1")' in text
    assert '(padstack "MCP_VIA_0"' in text
    assert "UnknownCacheData" not in text
    assert b"UnknownCacheData" in document.raw_bytes


def test_ses_parser_and_simple_route_conversion() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    session = parse_ses(_simple_ses())
    plan = session_to_operations(snapshot, session)

    assert session.resolution_unit == "mm"
    assert session.routes[0].wires[0].width_mm == 0.25
    assert plan.imported_nets == ["VCC"]
    assert plan.metrics["importable_net_count"] == 1
    assert plan.operations[0].points[-1].x == 20.0


def test_ses_parser_rejects_malformed_and_nonmatching_route() -> None:
    with pytest.raises(DocumentError, match="Unclosed"):
        parse_ses(b'(session "bad" (routes')
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    plan = session_to_operations(
        build_snapshot(document), parse_ses(_simple_ses(delay_coordinates=True))
    )
    assert plan.operations == []
    assert plan.skipped == [{"net": "VCC", "reason": "route_endpoints_do_not_match_pads"}]


def test_mocked_freerouting_job_inspect_commit_and_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    dsn = workspace / "board.dsn"
    dsn.write_text("(pcb mock)", encoding="utf-8")
    router = workspace / "mock-freerouting"
    _mock_router(router, _simple_ses())
    service = _service(workspace, tmp_path / "state", router)

    started = service.run_external_autorouter(str(board), dsn_path=str(dsn), max_passes=2)
    jobid = started["job"]["jobid"]
    assert _wait_for_job(service, jobid) == "completed"
    assert "mock freerouting complete" in service.job_resource(jobid, "log")

    inspected = service.inspect_autorouter_result(jobid)
    plan = inspected["result"]["plan"]
    assert plan["metrics"]["importable_net_count"] == 1
    preview = service.import_autorouter_ses(plan["plan_id"])
    txid = preview["transaction"]["txid"]
    committed = service.import_autorouter_ses(
        plan["plan_id"],
        dry_run=False,
        expected_sha256=preview["transaction"]["source_sha256"],
        txid=txid,
    )
    assert committed["transaction"]["status"] == "committed"
    reloaded = DipTraceDocument.load(board, 10_000_000)
    assert len(reloaded.container.findall("./Nets/Net[@Id='0']/Traces/Trace")) == 1
    rolled_back = service.rollback_transaction(
        txid, expected_sha256=committed["transaction"]["committed_sha256"]
    )
    assert rolled_back["transaction"]["status"] == "rolled_back"
    restored = DipTraceDocument.load(board, 10_000_000)
    assert len(restored.container.findall("./Nets/Net[@Id='0']/Traces/Trace")) == 0


def test_autorouter_inspection_rejects_source_sha_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    dsn = workspace / "board.dsn"
    dsn.write_text("(pcb mock)", encoding="utf-8")
    router = workspace / "mock-freerouting"
    _mock_router(router, _simple_ses())
    service = _service(workspace, tmp_path / "state", router)
    jobid = service.run_external_autorouter(str(board), dsn_path=str(dsn))["job"]["jobid"]
    assert _wait_for_job(service, jobid) == "completed"
    board.write_bytes(board.read_bytes().replace(b"10k", b"11k", 1))

    with pytest.raises(Sha256MismatchError):
        service.inspect_autorouter_result(jobid)


def test_external_job_cancellation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    dsn = workspace / "board.dsn"
    dsn.write_text("(pcb mock)", encoding="utf-8")
    router = workspace / "slow-freerouting"
    _mock_router(router, _simple_ses(), delay_seconds=2.0)
    service = _service(workspace, tmp_path / "state", router)
    jobid = service.run_external_autorouter(str(board), dsn_path=str(dsn))["job"]["jobid"]

    service.cancel_job(jobid)

    assert _wait_for_job(service, jobid) == "cancelled"
    assert service.jobs.read(jobid).error["code"] == "job_cancelled"
