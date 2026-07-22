from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import FieldSolverRequest, ImpedanceInput
from diptrace_mcp.errors import ExternalToolFailedError, ExternalToolUnavailableError
from diptrace_mcp.external_adapters import OpenEmsAdapter, parse_field_solver_result
from diptrace_mcp.impedance import calculate_impedance
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _request() -> FieldSolverRequest:
    return FieldSolverRequest(
        width_mm=0.2,
        copper_thickness_mm=0.035,
        lower_dielectric_height_mm=0.4825,
        upper_dielectric_height_mm=0.4825,
        dielectric_constant=4.2,
        frequencies_hz=[1_000_000_000.0, 2_000_000_000.0],
    )


def _service(
    workspace: Path,
    state: Path,
    *,
    runner: Path | None = None,
    timeout: int = 10,
) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
            openems_runner=runner,
            external_timeout_seconds=timeout,
            active_policy="automation",
        )
    )


def _fake_runner(tmp_path: Path, *, mode: str = "success") -> Path:
    script = tmp_path / f"fake_openems_{mode}.py"
    script.write_text(
        """\
import argparse
import json
import time

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.loads(open(args.input, encoding="utf-8").read())
mode = MODE
if mode == "timeout":
    time.sleep(5)
if mode == "exit":
    print("simulated solver failure")
    raise SystemExit(2)
if mode == "malformed":
    open(args.output, "w", encoding="utf-8").write("not-json")
    raise SystemExit(0)
frequencies = request["frequencies_hz"]
if mode == "mismatch":
    frequencies = [value + 1_000_000 for value in frequencies]
result = {
    "schema_version": "diptrace-field-solver-result-v1",
    "backend": "openems",
    "solver_version": "fake-openEMS 1.0",
    "converged": mode != "nonconverged",
    "points": [
        {
            "frequency_hz": frequency,
            "characteristic_impedance_real_ohm": 66.7,
            "characteristic_impedance_imag_ohm": -0.2,
            "propagation_alpha_np_per_m": 0.02,
            "propagation_beta_rad_per_m": 43.0 * (frequency / 1e9),
            "conductor_loss_db_per_m": 0.1,
            "dielectric_loss_db_per_m": 0.05,
        }
        for frequency in frequencies
    ],
    "mesh": {"cells": 1000, "energy_decay_db": -50.0},
    "warnings": ["simulated non-convergence"] if mode == "nonconverged" else [],
}
open(args.output, "w", encoding="utf-8").write(json.dumps(result))
""".replace("MODE", repr(mode)),
        encoding="utf-8",
    )
    return script


def _wait_for_job(service: DipTraceService, jobid: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = service.get_job_status(jobid)["result"]["job"]
        if record["status"] in {"completed", "failed", "cancelled"}:
            return record
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {jobid}")


def _run(service: DipTraceService, *, timeout_seconds: int | None = None) -> dict:
    response = service.run_openems_stripline_analysis(
        width_mm=0.2,
        copper_thickness_mm=0.035,
        lower_dielectric_height_mm=0.4825,
        upper_dielectric_height_mm=0.4825,
        dielectric_constant=4.2,
        frequencies_hz=[1_000_000_000.0, 2_000_000_000.0],
        timeout_seconds=timeout_seconds,
    )
    return _wait_for_job(service, response["job"]["jobid"])


def test_parse_stored_result_and_compare_centered_analytical_baseline() -> None:
    result = parse_field_solver_result(
        (FIXTURES / "openems_stripline_result.json").read_bytes(), _request()
    )
    analytical = calculate_impedance(
        ImpedanceInput(
            structure="symmetric_stripline",
            width_mm=0.2,
            copper_thickness_mm=0.035,
            dielectric_height_mm=1.0,
            dielectric_constant=4.2,
        )
    )
    assert result.points[0].characteristic_impedance_real_ohm == pytest.approx(
        analytical.estimated_impedance_ohm, rel=0.02
    )
    assert (
        result.points[1].characteristic_impedance_real_ohm
        != result.points[0].characteristic_impedance_real_ohm
    )


def test_field_solver_request_requires_increasing_unique_frequency_sweep() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        FieldSolverRequest(
            width_mm=0.2,
            copper_thickness_mm=0.035,
            lower_dielectric_height_mm=0.4,
            upper_dielectric_height_mm=0.6,
            dielectric_constant=4.2,
            frequencies_hz=[2e9, 1e9],
        )


def test_openems_probe_and_command_are_portable(tmp_path: Path) -> None:
    unavailable = OpenEmsAdapter(
        Settings(workspace=tmp_path, allowed_roots=(tmp_path,), state_dir=tmp_path / ".state")
    )
    assert unavailable.probe().available is False
    with pytest.raises(ExternalToolUnavailableError):
        unavailable.command(tmp_path / "input.json", tmp_path / "output.json")

    runner = _fake_runner(tmp_path)
    configured = OpenEmsAdapter(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state2",
            openems_runner=runner,
        )
    )
    command = configured.command(tmp_path / "input.json", tmp_path / "output.json")
    assert command[:2] == [sys.executable, str(runner)]
    assert command[2:] == [
        "--input",
        str(tmp_path / "input.json"),
        "--output",
        str(tmp_path / "output.json"),
    ]


def test_openems_job_completes_with_typed_result_and_artifacts(tmp_path: Path) -> None:
    runner = _fake_runner(tmp_path)
    service = _service(tmp_path, tmp_path / ".state", runner=runner)
    record = _run(service)
    assert record["status"] == "completed"
    assert record["job_type"] == "openems_stripline"
    assert record["result"]["backend"] == "openems"
    assert len(record["result"]["points"]) == 2
    assert record["command"][:2] == [sys.executable, str(runner)]
    result = service.job_resource(record["jobid"], "field_solver_result.json")
    assert '"schema_version": "diptrace-field-solver-result-v1"' in result
    request = service.job_resource(record["jobid"], "field_solver_input.json")
    assert "diptrace-field-solver-request-v1" in request


def test_openems_job_preserves_off_center_stripline_geometry(tmp_path: Path) -> None:
    runner = _fake_runner(tmp_path)
    service = _service(tmp_path, tmp_path / ".state", runner=runner)
    response = service.run_openems_stripline_analysis(
        width_mm=0.2,
        copper_thickness_mm=0.035,
        lower_dielectric_height_mm=0.3,
        upper_dielectric_height_mm=0.7,
        dielectric_constant=4.2,
        frequencies_hz=[1_000_000_000.0],
    )
    record = _wait_for_job(service, response["job"]["jobid"])
    assert record["status"] == "completed"
    request = json.loads(
        service.job_resource(record["jobid"], "field_solver_input.json")
    )
    assert request["lower_dielectric_height_mm"] == 0.3
    assert request["upper_dielectric_height_mm"] == 0.7


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("malformed", "malformed result JSON"),
        ("nonconverged", "non-converged"),
        ("mismatch", "frequency sweep"),
        ("exit", "exited with status 2"),
    ],
)
def test_openems_job_reports_solver_failures(
    tmp_path: Path, mode: str, message: str
) -> None:
    service = _service(tmp_path, tmp_path / ".state", runner=_fake_runner(tmp_path, mode=mode))
    record = _run(service)
    assert record["status"] == "failed"
    assert message in record["error"]["message"]


def test_openems_job_timeout_is_bounded(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        tmp_path / ".state",
        runner=_fake_runner(tmp_path, mode="timeout"),
        timeout=1,
    )
    record = _run(service, timeout_seconds=1)
    assert record["status"] == "failed"
    assert record["error"]["code"] == "job_timeout"


def test_capabilities_report_configured_openems_runner(tmp_path: Path) -> None:
    runner = _fake_runner(tmp_path)
    service = _service(tmp_path, tmp_path / ".state", runner=runner)
    report = service.get_capabilities()
    assert report["external_adapters"]["openems"]["available"] is True
    assert not any(
        item["feature"] == "external_si_pi_solver"
        for item in report["reasons_unavailable"]
    )


def test_parse_result_rejects_frequency_mismatch() -> None:
    request = _request().model_copy(update={"frequencies_hz": [1e9, 3e9]})
    with pytest.raises(ExternalToolFailedError, match="frequency sweep"):
        parse_field_solver_result(
            (FIXTURES / "openems_stripline_result.json").read_bytes(), request
        )
