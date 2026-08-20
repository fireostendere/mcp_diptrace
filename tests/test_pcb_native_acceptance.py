from __future__ import annotations

import json
from pathlib import Path

import pytest

from diptrace_mcp import pcb_native_acceptance as native

_FIXTURE = Path(__file__).parent / "fixtures" / "pcb_4layer.xml"


def _request(tmp_path: Path, **kwargs: object) -> native.PcbNativeAcceptanceRequest:
    values: dict[str, object] = {
        "diptrace_root": tmp_path / "DipTrace",
        "project": tmp_path / "board.dip",
        "output_xml": tmp_path / "board-roundtrip.dipxml",
    }
    values.update(kwargs)
    return native.PcbNativeAcceptanceRequest.model_validate(values)


def _worker(**kwargs: object) -> native.NativePcbWorkerEvidence:
    values: dict[str, object] = {
        "completed": True,
        "project": "board.dip",
        "output_xml": "board-roundtrip.dipxml",
        "project_sha256_before": "a" * 64,
        "project_sha256_after": "b" * 64,
        "output_xml_sha256": "c" * 64,
        "drc_status": "pass",
        "drc_texts": ["No Errors Found"],
        "native_steps": [{"name": "run_drc", "status": "completed"}],
        "worker_pid": 10,
        "diptrace_pids": [11, 12],
        "desktop_name": "hidden",
        "window_station_name": "WinSta0",
        "session_id": 1,
    }
    values.update(kwargs)
    return native.NativePcbWorkerEvidence.model_validate(values)


def test_request_normalizes_and_roundtrips_json(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        desktop_mode=" HIDDEN ",
        drc_success_tokens=(" No Errors Found ", "No Errors"),
    )

    assert request.desktop_mode == "hidden"
    assert request.drc_success_tokens == ("No Errors Found", "No Errors")
    restored = native.PcbNativeAcceptanceRequest.model_validate_json(request.model_dump_json())
    assert restored == request


@pytest.mark.parametrize("suffix", [".xml", ".dch", ""])
def test_request_rejects_non_pcb_project_suffix(tmp_path: Path, suffix: str) -> None:
    with pytest.raises(ValueError, match="project must use"):
        _request(tmp_path, project=tmp_path / f"board{suffix}")


def test_request_rejects_non_dipxml_output_and_same_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output_xml"):
        _request(tmp_path, output_xml=tmp_path / "board.xml")
    project = tmp_path / "board.dipxml"
    with pytest.raises(ValueError, match="distinct"):
        _request(tmp_path, project=project, output_xml=project)


def test_drc_dialog_classification_is_fail_closed() -> None:
    assert (
        native.classify_drc_dialog(
            ["Design Rules Check", "No Errors Found"],
            ("No Errors Found",),
        )
        == "pass"
    )
    assert (
        native.classify_drc_dialog(
            ["Design Rules Check", "2 Errors"],
            ("No Errors Found",),
        )
        == "fail"
    )
    assert (
        native.classify_drc_dialog(
            ["Design Rules Check", "Errors found: 3"],
            ("No Errors Found",),
        )
        == "fail"
    )
    assert (
        native.classify_drc_dialog(
            ["Design Rules Check", "Errors: 0"],
            ("No Errors Found",),
        )
        == "review_required"
    )
    assert (
        native.classify_drc_dialog(
            ["Design Rules Check", "Проверка завершена"],
            ("No Errors Found",),
        )
        == "review_required"
    )
    assert (
        native.classify_drc_dialog(
            ["PCB Layout - board.dipxml", "OK"],
            ("No Errors Found",),
            "TFMyMessage",
        )
        == "pass"
    )


def test_pcb_summary_exposes_whole_board_native_invariants() -> None:
    summary = native.summarize_pcb_xml(_FIXTURE)

    assert summary["source_type"] == "DipTrace-PCB"
    assert summary["components"] == 4
    assert summary["nets"] == 3
    assert summary["traces"] == 2
    assert summary["vias"] == 2
    assert summary["copper_layers"] == 4
    assert summary["plane_layers"] == 1
    assert summary["via_styles"] == 1
    assert summary["unrouted_multi_pad_nets"] == 1
    assert isinstance(summary["semantic_sha256"], str)


def test_identical_native_export_can_pass_without_human_review(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.dipxml"
    output = tmp_path / "output.dipxml"
    baseline.write_bytes(_FIXTURE.read_bytes())
    output.write_bytes(_FIXTURE.read_bytes())
    request = _request(tmp_path, output_xml=output, baseline_xml=baseline)
    worker = _worker(output_xml=str(output), output_xml_sha256=native._sha256(output))

    result = native._finalize_result(
        request,
        worker,
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )

    assert result.verdict == "PASS"
    assert result.ok is True
    assert result.ui_profile == "diptrace-5.3-en-v1"
    assert result.structural_delta == {}
    assert result.semantic_delta is not None
    assert result.semantic_delta["semantic_equal"] is True
    assert result.public_payload()["ok"] is True


def test_semantic_change_with_stable_structure_requires_review(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.dipxml"
    output = tmp_path / "output.dipxml"
    baseline.write_bytes(_FIXTURE.read_bytes())
    changed = _FIXTURE.read_text(encoding="utf-8").replace(
        "<Value>10k</Value>",
        "<Value>11k</Value>",
        1,
    )
    output.write_text(changed, encoding="utf-8")
    request = _request(tmp_path, output_xml=output, baseline_xml=baseline)

    result = native._finalize_result(
        request,
        _worker(output_xml=str(output)),
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )

    assert result.verdict == "HUMAN_REVIEW_REQUIRED"
    assert result.structural_delta == {}
    assert result.semantic_delta is not None
    assert result.semantic_delta["semantic_equal"] is False
    assert result.manual_review_reasons


def test_structural_change_or_drc_error_fails(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.dipxml"
    output = tmp_path / "output.dipxml"
    baseline.write_bytes(_FIXTURE.read_bytes())
    changed = _FIXTURE.read_text(encoding="utf-8").replace(
        "</Components>",
        '<Component Id="99"><RefDes>X1</RefDes></Component></Components>',
        1,
    )
    output.write_text(changed, encoding="utf-8")
    request = _request(tmp_path, output_xml=output, baseline_xml=baseline)
    result = native._finalize_result(
        request,
        _worker(output_xml=str(output)),
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )
    assert result.verdict == "FAIL"
    assert "components" in result.structural_delta

    clean = tmp_path / "clean.dipxml"
    clean.write_bytes(_FIXTURE.read_bytes())
    failed = native._finalize_result(
        _request(tmp_path, output_xml=clean, baseline_xml=baseline),
        _worker(output_xml=str(clean), drc_status="fail", drc_texts=["2 Errors"]),
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )
    assert failed.verdict == "FAIL"


def test_no_baseline_and_unknown_drc_require_review(tmp_path: Path) -> None:
    output = tmp_path / "output.dipxml"
    output.write_bytes(_FIXTURE.read_bytes())
    request = _request(tmp_path, output_xml=output)
    result = native._finalize_result(
        request,
        _worker(output_xml=str(output), drc_status="review_required"),
        None,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )
    assert result.verdict == "HUMAN_REVIEW_REQUIRED"
    assert len(result.manual_review_reasons) == 2


def test_desktop_or_session_identity_drift_fails(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.dipxml"
    output = tmp_path / "output.dipxml"
    baseline.write_bytes(_FIXTURE.read_bytes())
    output.write_bytes(_FIXTURE.read_bytes())
    request = _request(tmp_path, output_xml=output, baseline_xml=baseline)

    desktop = native._finalize_result(
        request,
        _worker(output_xml=str(output)),
        baseline,
        input_before="Default",
        input_after="ConsentUi",
        station_after="WinSta0",
        session_after=1,
    )
    assert desktop.verdict == "FAIL"
    assert "input desktop" in (desktop.error or "")

    session = native._finalize_result(
        request,
        _worker(output_xml=str(output), session_id=1),
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=2,
    )
    assert session.verdict == "FAIL"
    assert "session identity" in (session.error or "")


def test_worker_argv_supports_source_and_frozen_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(native.sys.__dict__, "frozen", raising=False)
    source = native._worker_argv("--request", "r", "--result", "o")
    assert source[1:4] == ["-m", "diptrace_mcp.pcb_native_acceptance", "_worker"]

    monkeypatch.setitem(native.sys.__dict__, "frozen", True)
    frozen = native._worker_argv("--request", "r", "--result", "o")
    assert frozen[1:3] == ["pcb-acceptance", "_worker"]


def test_parser_exposes_native_run_contract() -> None:
    parser = native._build_parser()
    args = parser.parse_args(
        [
            "run",
            "--diptrace-root",
            "root",
            "--project",
            "board.dip",
            "--output-xml",
            "board.dipxml",
        ]
    )
    assert args.desktop == "hidden"
    assert args.refill_menu == "#3->#14"
    assert args.drc_menu == "#7->#0"
    assert args.save_as_menu == "#0->#4"
    assert args.evidence_json is None


def test_cmd_worker_fails_closed_on_invalid_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    payload = request.model_dump(mode="json")
    payload["_expected_window_station"] = "WinSta0"
    payload["_expected_session_id"] = 1
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(native, "thread_desktop_name", lambda: "Other")

    parser = native._build_parser()
    args = parser.parse_args(
        [
            "_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
            "--desktop-name",
            "Hidden",
        ]
    )
    assert native._cmd_worker(args) == 1
    result = native.NativePcbWorkerEvidence.model_validate_json(
        result_path.read_text(encoding="utf-8")
    )
    assert result.completed is False
    assert "unexpected desktop" in (result.error or "")


def test_request_rejects_invalid_baseline_and_empty_native_tokens(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="baseline_xml"):
        _request(tmp_path, baseline_xml=tmp_path / "baseline.xml")
    with pytest.raises(ValueError, match="native menu path"):
        _request(tmp_path, refill_menu="   ")
    with pytest.raises(ValueError, match="drc_success_tokens"):
        _request(tmp_path, drc_success_tokens=(" ",))


def test_menu_dialog_and_exit_helpers_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[object] = []

    class Window:
        def menu(self) -> object:
            return object()

        def menu_item(self, path: str) -> str:
            if path == "primary":
                raise RuntimeError("missing")
            return path

    monkeypatch.setattr(native, "_post_menu_item", lambda _window, item: posted.append(item))
    assert native._post_menu_path(Window(), "primary", ("fallback",)) == "fallback"
    assert posted == ["fallback"]

    class NoMenu:
        def menu(self) -> object:
            raise RuntimeError("no menu")

    with pytest.raises(native.HeadlessGuiError, match="no native menu"):
        native._post_menu_path(NoMenu(), "x")

    class TextControl:
        def __init__(self, value: str) -> None:
            self.value = value

        def window_text(self) -> str:
            return self.value

    class Dialog(TextControl):
        def descendants(self) -> list[TextControl]:
            return [TextControl("child"), TextControl("child"), TextControl("")]

    assert native._dialog_texts(Dialog("dialog")) == ["dialog", "child"]

    class Button(TextControl):
        handle = 42

        def class_name(self) -> str:
            return "TButton"

    button = Button("OK")

    class ResultDialog(Dialog):
        def descendants(self) -> list[TextControl]:
            return [button]

        def is_visible(self) -> bool:
            return False

    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(
        native,
        "_send_window_message",
        lambda hwnd, message: sent.append((hwnd, message)),
    )
    native._dismiss_dialog(ResultDialog("result"), 2.0)
    assert sent == [(42, 0x00F5)]

    class App:
        def wait_for_process_exit(self, *, timeout: float) -> None:
            assert timeout == 2.0

    native._wait_for_exit(App(), 2.0, "ok")

    class Stuck:
        def wait_for_process_exit(self, *, timeout: float) -> None:
            raise RuntimeError(str(timeout))

    with pytest.raises(native.HeadlessGuiError, match="did not exit normally"):
        native._wait_for_exit(Stuck(), 2.0, "stuck")


def test_immutable_baseline_supports_explicit_implicit_and_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "baseline.dipxml"
    baseline.write_bytes(b"abc")
    request = _request(tmp_path, baseline_xml=baseline)
    explicit_root = tmp_path / "explicit"
    explicit_root.mkdir()
    snapshot = native._immutable_baseline(request, explicit_root)
    assert snapshot is not None
    assert snapshot.read_bytes() == b"abc"

    project = tmp_path / "board.dipxml"
    project.write_bytes(b"xyz")
    implicit_root = tmp_path / "implicit"
    implicit_root.mkdir()
    implicit = native._immutable_baseline(
        _request(tmp_path, project=project, output_xml=tmp_path / "out.dipxml"),
        implicit_root,
    )
    assert implicit is not None
    assert implicit.read_bytes() == b"xyz"

    assert native._immutable_baseline(_request(tmp_path), tmp_path / "none") is None

    monkeypatch.setattr(native, "_MAX_XML_BYTES", 2)
    with pytest.raises(native.HeadlessGuiError, match="larger"):
        native._immutable_baseline(request, tmp_path / "too-large")


def test_finalize_catches_bad_export_and_station_drift(tmp_path: Path) -> None:
    bad_output = tmp_path / "bad.dipxml"
    bad_output.write_text("not xml", encoding="utf-8")
    failed = native._finalize_result(
        _request(tmp_path, output_xml=bad_output),
        _worker(output_xml=str(bad_output)),
        None,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )
    assert failed.verdict == "FAIL"
    assert failed.completed is False

    baseline = tmp_path / "baseline.dipxml"
    output = tmp_path / "output.dipxml"
    baseline.write_bytes(_FIXTURE.read_bytes())
    output.write_bytes(_FIXTURE.read_bytes())
    drift = native._finalize_result(
        _request(tmp_path, output_xml=output, baseline_xml=baseline),
        _worker(output_xml=str(output), window_station_name="OtherSta"),
        baseline,
        input_before="Default",
        input_after="Default",
        station_after="WinSta0",
        session_after=1,
    )
    assert drift.verdict == "FAIL"
    assert "window station" in (drift.error or "")


def test_cmd_worker_success_path_is_context_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    payload = request.model_dump(mode="json")
    payload["_expected_window_station"] = "WinSta0"
    payload["_expected_session_id"] = 7
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(native, "thread_desktop_name", lambda: "Hidden")
    monkeypatch.setattr(native, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(native, "process_session_id", lambda: 7)
    monkeypatch.setattr(native, "process_is_elevated", lambda: False)
    monkeypatch.setattr(
        native,
        "_native_worker_evidence",
        lambda _request, desktop_name: _worker(completed=True, desktop_name=desktop_name),
    )

    args = native._build_parser().parse_args(
        [
            "_worker",
            "--request",
            str(request_path),
            "--result",
            str(result_path),
            "--desktop-name",
            "Hidden",
        ]
    )
    assert native._cmd_worker(args) == 0
    result = native.NativePcbWorkerEvidence.model_validate_json(
        result_path.read_text(encoding="utf-8")
    )
    assert result.completed is True
    assert result.desktop_name == "Hidden"


def test_cmd_run_writes_fail_closed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "output.dipxml"
    parser = native._build_parser()
    same = parser.parse_args(
        [
            "run",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(tmp_path / "board.dip"),
            "--output-xml",
            str(output),
            "--evidence-json",
            str(output),
        ]
    )
    assert native._cmd_run(same) == 1
    assert "distinct" in capsys.readouterr().out

    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    existing = parser.parse_args(
        [
            "run",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(tmp_path / "board.dip"),
            "--output-xml",
            str(output),
            "--evidence-json",
            str(evidence),
        ]
    )
    assert native._cmd_run(existing) == 1
    assert "already exists" in capsys.readouterr().out

    evidence.unlink()
    monkeypatch.setattr(
        native,
        "run_pcb_native_acceptance",
        lambda _request: (_ for _ in ()).throw(native.HeadlessGuiError("host unavailable")),
    )
    failed = parser.parse_args(
        [
            "run",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(tmp_path / "board.dip"),
            "--output-xml",
            str(output),
            "--evidence-json",
            str(evidence),
        ]
    )
    assert native._cmd_run(failed) == 1
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["verdict"] == "FAIL"
    assert payload["error"] == "host unavailable"


def test_run_rejects_non_windows_and_native_elevation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    native_request = _request(tmp_path, desktop_mode="native")
    monkeypatch.setattr(native.os, "name", "posix")
    with pytest.raises(native.HeadlessGuiError, match="only on Windows"):
        native.run_pcb_native_acceptance(request)

    monkeypatch.setattr(native.os, "name", "nt")
    monkeypatch.setattr(native, "_validate_request", lambda value: value)
    monkeypatch.setattr(native, "process_is_elevated", lambda: True)
    with pytest.raises(native.HeadlessGuiError, match="elevated process"):
        native.run_pcb_native_acceptance(native_request)


def test_main_dispatches_run_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        native,
        "run_pcb_native_acceptance",
        lambda _request: (_ for _ in ()).throw(native.HeadlessGuiError("host unavailable")),
    )
    evidence = tmp_path / "main-evidence.json"
    code = native.main(
        [
            "run",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(tmp_path / "board.dip"),
            "--output-xml",
            str(tmp_path / "main-output.dipxml"),
            "--evidence-json",
            str(evidence),
        ]
    )
    assert code == 1
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["verdict"] == "FAIL"
    assert payload["error"] == "host unavailable"
