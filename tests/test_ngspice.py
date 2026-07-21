from __future__ import annotations

import stat
import time
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import ImpedanceInput
from diptrace_mcp.errors import DocumentError, ExternalToolUnavailableError
from diptrace_mcp.external_adapters import NgSpiceAdapter, parse_ngspice_log
from diptrace_mcp.impedance import analyze_stackup, calculate_impedance
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000

NGSPICE_LOG_OK = b"""\
Circuit: * rc filter
No. of Data Rows : 101
"""
NGSPICE_LOG_ERROR = b"""\
Circuit: broken
Error: no such device or model name
"""


def _service(
    workspace: Path,
    state: Path,
    *,
    ngspice: Path | None = None,
    policy: str = "automation",
) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
            ngspice_executable=ngspice,
            active_policy=policy,  # type: ignore[arg-type]
        )
    )


def _fake_ngspice(tmp_path: Path, *, fail: bool = False) -> Path:
    script = tmp_path / "fake_ngspice.sh"
    if fail:
        script.write_text("#!/bin/sh\necho 'Error: simulated failure'\nexit 1\n")
    else:
        script.write_text("#!/bin/sh\necho 'No. of Data Rows : 42'\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _wait_for_job(service: DipTraceService, jobid: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = service.get_job_status(jobid)["result"]["job"]
        if record["status"] in {"completed", "failed", "cancelled"}:
            return record
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {jobid}")


def test_parse_ngspice_log_extracts_rows_and_errors() -> None:
    ok = parse_ngspice_log(NGSPICE_LOG_OK)
    assert ok["data_rows"] == [101]
    assert ok["error_lines"] == []
    broken = parse_ngspice_log(NGSPICE_LOG_ERROR)
    assert broken["data_rows"] == []
    assert broken["error_lines"] == ["Error: no such device or model name"]


def test_ngspice_probe_unavailable_without_configuration(tmp_path: Path) -> None:
    adapter = NgSpiceAdapter(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
            ngspice_executable=None,
        )
    )
    probe = adapter.probe()
    assert probe.available is False
    with pytest.raises(ExternalToolUnavailableError):
        adapter.command(tmp_path / "input.cir")


def test_run_ngspice_simulation_completes_with_typed_result(tmp_path: Path) -> None:
    executable = _fake_ngspice(tmp_path)
    service = _service(tmp_path, tmp_path / ".state", ngspice=executable)
    response = service.run_ngspice_simulation(
        netlist="* rc\nR1 in out 1k\nC1 out 0 1n\n.end\n"
    )
    assert response["ok"] is True
    jobid = response["job"]["jobid"]
    record = _wait_for_job(service, jobid)
    assert record["status"] == "completed"
    assert record["result"]["data_rows"] == [42]
    assert record["command"][:1] == [str(executable)]
    assert record["command"][1] == "-b"


def test_run_ngspice_simulation_reports_solver_errors(tmp_path: Path) -> None:
    executable = _fake_ngspice(tmp_path, fail=True)
    service = _service(tmp_path, tmp_path / ".state", ngspice=executable)
    response = service.run_ngspice_simulation(netlist="* broken\n.end\n")
    record = _wait_for_job(service, response["job"]["jobid"])
    assert record["status"] == "failed"
    assert "simulated failure" in record["error"]["message"] or "simulation failure" in (
        record["error"]["message"]
    )


def test_run_ngspice_requires_exactly_one_input(tmp_path: Path) -> None:
    executable = _fake_ngspice(tmp_path)
    service = _service(tmp_path, tmp_path / ".state", ngspice=executable)
    with pytest.raises(DocumentError, match="exactly one"):
        service.run_ngspice_simulation()
    with pytest.raises(DocumentError, match="exactly one"):
        service.run_ngspice_simulation(netlist="* x", netlist_path="x.cir")


def test_run_ngspice_reads_netlist_from_workspace(tmp_path: Path) -> None:
    executable = _fake_ngspice(tmp_path)
    netlist = tmp_path / "filter.cir"
    netlist.write_text("* rc\n.end\n")
    service = _service(tmp_path, tmp_path / ".state", ngspice=executable)
    response = service.run_ngspice_simulation(netlist_path="filter.cir")
    record = _wait_for_job(service, response["job"]["jobid"])
    assert record["status"] == "completed"


def test_capabilities_report_ngspice_adapter(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    report = service.get_capabilities()
    adapter = report["external_adapters"]["ngspice"]
    assert adapter["available"] is False
    assert "DIPTRACE_MCP_NGSPICE" in adapter["reason"]


def test_stripline_stackup_candidates_from_generated_document() -> None:
    from diptrace_mcp.adapters import build_snapshot
    from diptrace_mcp.scaffolding import LayerSpec, PcbScaffold, build_pcb_document

    raw = build_pcb_document(
        PcbScaffold(
            layers=[
                LayerSpec(name="Top"),
                LayerSpec(name="L2"),
                LayerSpec(name="L3"),
                LayerSpec(name="Bottom"),
            ],
            dielectric_thickness_mm=0.5,
            dielectric_constant=4.2,
        )
    )
    snapshot = build_snapshot(DipTraceDocument.from_bytes(Path("g.xml"), raw))
    assert snapshot.board is not None
    analysis = analyze_stackup(snapshot.board.stackup)
    stripline = analysis["stripline_candidates"]
    assert [item["signal_layer"] for item in stripline] == ["L2", "L3"]
    assert stripline[0]["plane_to_plane_separation_mm"] == pytest.approx(1.0)
    assert stripline[0]["off_center_mm"] == pytest.approx(0.0)
    # Outer layers stay microstrip candidates.
    assert {item["signal_layer"] for item in analysis["microstrip_candidates"]} == {
        "Top",
        "Bottom",
    }
    impedance = calculate_impedance(
        ImpedanceInput(
            structure="symmetric_stripline",
            width_mm=0.2,
            copper_thickness_mm=0.035,
            dielectric_height_mm=stripline[0]["plane_to_plane_separation_mm"],
            dielectric_constant=stripline[0]["dielectric_constant"],
        )
    )
    assert impedance.estimated_impedance_ohm > 0.0
    assert impedance.validity["inside_published_range"] is True
