"""Collect bounded native PCB acceptance evidence from real DipTrace.

The workflow composes the isolated Win32 desktop primitives from ``headless_gui``.
It never falls back to physical mouse/keyboard input and it does not add MCP tools.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, field_validator, model_validator

from .domain import StrictModel
from .headless_gui import (
    HeadlessGuiError,
    HiddenDesktop,
    _interactive_context,
    _launch_on_current_desktop,
    _load_json,
    _main_window,
    _post_menu_item,
    _post_window_message,
    _pywinauto_application,
    _save_dialog_as_xml,
    _save_window,
    _send_window_message,
    _sha256,
    _visible_dialog,
    _wait_for_export,
    _window_titles,
    _write_json,
    input_desktop_name,
    process_is_elevated,
    process_session_id,
    process_window_station_name,
    thread_desktop_name,
)
from .windows_configurator import ConfiguratorError, validate_diptrace_directory
from .xml_analysis import analyze_xml_semantics, compare_xml_semantics
from .xml_document import DipTraceDocument

_MAX_XML_BYTES = 128 * 1024 * 1024
_DEFAULT_REFILL_MENU = "#3->#14"
_REFILL_MENU_FALLBACKS = (
    "Objects->Update All Copper Pours",
    "Object->Update All Copper Pours",
)
_DEFAULT_DRC_MENU = "#7->#0"
_DEFAULT_SAVE_AS_MENU = "#0->#4"
_DEFAULT_DRC_SUCCESS_TOKENS = ("No Errors Found", "No Errors")
_UI_PROFILE: Literal["diptrace-5.3-en-v1"] = "diptrace-5.3-en-v1"

Verdict = Literal["PASS", "FAIL", "HUMAN_REVIEW_REQUIRED"]
DrcStatus = Literal["pass", "fail", "review_required", "not_run"]
DesktopMode = Literal["hidden", "native"]


class PcbNativeAcceptanceRequest(StrictModel):
    diptrace_root: Path
    project: Path
    output_xml: Path
    baseline_xml: Path | None = None
    timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    desktop_mode: DesktopMode = "hidden"
    refill_menu: str = Field(default=_DEFAULT_REFILL_MENU, min_length=1, max_length=256)
    drc_menu: str = Field(default=_DEFAULT_DRC_MENU, min_length=1, max_length=256)
    save_as_menu: str = Field(default=_DEFAULT_SAVE_AS_MENU, min_length=1, max_length=256)
    drc_success_tokens: tuple[str, ...] = _DEFAULT_DRC_SUCCESS_TOKENS

    @field_validator("desktop_mode", mode="before")
    @classmethod
    def _normalize_desktop_mode(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("refill_menu", "drc_menu", "save_as_menu")
    @classmethod
    def _normalize_menu(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("native menu path must not be empty")
        return normalized

    @field_validator("drc_success_tokens")
    @classmethod
    def _normalize_success_tokens(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value if item.strip())
        if not normalized:
            raise ValueError("drc_success_tokens must contain at least one token")
        return normalized

    @model_validator(mode="after")
    def _validate_paths(self) -> PcbNativeAcceptanceRequest:
        if self.project.suffix.casefold() not in {".dip", ".dipxml"}:
            raise ValueError("project must use the .dip or .dipxml suffix")
        if self.output_xml.suffix.casefold() != ".dipxml":
            raise ValueError("output_xml must use the .dipxml suffix")
        if self.baseline_xml is not None and self.baseline_xml.suffix.casefold() != ".dipxml":
            raise ValueError("baseline_xml must use the .dipxml suffix")
        if self.project.resolve(strict=False) == self.output_xml.resolve(strict=False):
            raise ValueError("output_xml must be distinct from project")
        return self


class NativePcbWorkerEvidence(StrictModel):
    completed: bool = False
    project: str = ""
    output_xml: str = ""
    project_sha256_before: str | None = None
    project_sha256_after: str | None = None
    output_xml_sha256: str | None = None
    drc_status: DrcStatus = "not_run"
    drc_texts: list[str] = Field(default_factory=list)
    native_steps: list[dict[str, Any]] = Field(default_factory=list)
    worker_pid: int | None = None
    diptrace_pids: list[int] = Field(default_factory=list)
    automation_backend: str = "pywinauto-win32-message"
    desktop_mode: DesktopMode = "hidden"
    desktop_name: str = ""
    window_station_name: str | None = None
    session_id: int | None = None
    forced_termination: bool = False
    error: str | None = None


class PcbNativeAcceptanceResult(StrictModel):
    schema_version: Literal["diptrace-pcb-native-acceptance-v1"] = (
        "diptrace-pcb-native-acceptance-v1"
    )
    ui_profile: Literal["diptrace-5.3-en-v1"] = _UI_PROFILE
    verdict: Verdict
    completed: bool
    project: str
    output_xml: str
    baseline_xml: str | None = None
    project_sha256_before: str | None = None
    project_sha256_after: str | None = None
    output_xml_sha256: str | None = None
    drc_status: DrcStatus
    drc_texts: list[str] = Field(default_factory=list)
    structural_before: dict[str, Any] | None = None
    structural_after: dict[str, Any] | None = None
    structural_delta: dict[str, dict[str, Any]] = Field(default_factory=dict)
    semantic_delta: dict[str, Any] | None = None
    native_steps: list[dict[str, Any]] = Field(default_factory=list)
    worker_pid: int | None = None
    diptrace_pids: list[int] = Field(default_factory=list)
    automation_backend: str
    desktop_mode: DesktopMode
    desktop_name: str
    input_desktop_before: str | None = None
    input_desktop_after: str | None = None
    window_station_name: str | None = None
    session_id: int | None = None
    forced_termination: bool = False
    manual_review_reasons: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"

    def public_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["ok"] = self.ok
        return payload


def _validate_request(request: PcbNativeAcceptanceRequest) -> PcbNativeAcceptanceRequest:
    try:
        root = validate_diptrace_directory(request.diptrace_root).root
    except ConfiguratorError as exc:
        raise HeadlessGuiError(str(exc)) from exc
    executable = root / "Pcb.exe"
    if not executable.is_file():
        raise HeadlessGuiError(f"DipTrace PCB Layout is missing: {executable}")
    project = request.project.expanduser().resolve(strict=False)
    if not project.is_file():
        raise HeadlessGuiError(f"PCB project does not exist: {project}")
    output = request.output_xml.expanduser().resolve(strict=False)
    if output.exists():
        raise HeadlessGuiError(f"output XML already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    baseline = request.baseline_xml
    if baseline is not None:
        baseline = baseline.expanduser().resolve(strict=False)
        if not baseline.is_file():
            raise HeadlessGuiError(f"baseline XML does not exist: {baseline}")
    return request.model_copy(
        update={
            "diptrace_root": root,
            "project": project,
            "output_xml": output,
            "baseline_xml": baseline,
        }
    )


def summarize_pcb_xml(path: Path) -> dict[str, Any]:
    document = DipTraceDocument.load(path, _MAX_XML_BYTES)
    if document.kind != "pcb":
        raise ValueError(f"expected DipTrace PCB XML, got {document.source_type!r}")
    board = document.container
    components = board.findall("./Components/Component")
    nets = board.findall("./Nets/Net")
    traces = board.findall("./Nets/Net/Traces/Trace")
    trace_points = board.findall("./Nets/Net/Traces/Trace/Points/Point")
    copper_layers = board.findall("./CopperLayers/Lay")
    inventory = analyze_xml_semantics(document)
    return {
        "source_type": document.source_type,
        "version": document.version,
        "units": document.units,
        "document_sha256": document.sha256,
        "semantic_sha256": inventory.semantic_sha256,
        "components": len(components),
        "nets": len(nets),
        "net_endpoints": sum(len(net.findall("./Pads/Item")) for net in nets),
        "traces": len(traces),
        "trace_points": len(trace_points),
        "vias": sum(point.get("ViaStyle") not in {None, "", "-1"} for point in trace_points),
        "copper_layers": len(copper_layers),
        "plane_layers": sum(layer.get("Type", "").casefold() == "plane" for layer in copper_layers),
        "via_styles": len(board.findall("./ViaStyles/ViaStyle")),
        "copper_pours": len(board.findall("./CopperPours/*")),
        "ratlines": len(board.findall("./Ratlines/Ratline")),
        "unrouted_multi_pad_nets": sum(
            len(net.findall("./Pads/Item")) > 1 and not net.findall("./Traces/Trace")
            for net in nets
        ),
        "duplicate_tag_id_pairs": list(inventory.duplicate_tag_id_pairs),
    }


def _structural_delta(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    ignored = {"document_sha256", "semantic_sha256", "version"}
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted((set(before) | set(after)) - ignored)
        if before.get(key) != after.get(key)
    }


def classify_drc_dialog(
    texts: Sequence[str],
    success_tokens: Sequence[str],
    dialog_class: str = "",
) -> DrcStatus:
    normalized = "\n".join(texts).casefold()
    if any(token.casefold() in normalized for token in success_tokens):
        return "pass"
    if dialog_class.casefold() == "tfmymessage":
        return "pass"
    if re.search(r"\b[1-9][0-9]*\s+errors?\b", normalized) or re.search(
        r"\berrors?(?:\s+found)?\s*[:=]\s*[1-9][0-9]*\b", normalized
    ):
        return "fail"
    return "review_required"


def _post_menu_path(
    window: Any,
    path: str,
    fallbacks: Sequence[str] = (),
    *,
    timeout_seconds: float = 0.0,
) -> str:
    menu: Any = None
    with suppress(Exception):
        menu = window.menu()
    if menu is None:
        raise HeadlessGuiError("DipTrace PCB window has no native menu")
    deadline = time.monotonic() + timeout_seconds
    while True:
        errors: list[str] = []
        disabled = False
        for candidate in (path, *fallbacks):
            try:
                _post_menu_item(window, window.menu_item(candidate))
                return candidate
            except Exception as exc:
                disabled |= str(exc) == "native menu item is disabled"
                errors.append(f"{candidate!r}: {type(exc).__name__}: {exc}")
        remaining = deadline - time.monotonic()
        if not disabled or remaining <= 0:
            raise HeadlessGuiError(f"native menu item {path!r} was not found ({'; '.join(errors)})")
        time.sleep(min(0.1, remaining))


def _dialog_texts(dialog: Any) -> list[str]:
    controls: list[Any] = [dialog]
    with suppress(Exception):
        controls.extend(dialog.descendants())
    values: list[str] = []
    for control in controls[:512]:
        with suppress(Exception):
            text = str(control.window_text()).strip()[:2048]
            if text and text not in values:
                values.append(text)
    return values


def _dismiss_dialog(dialog: Any, timeout_seconds: float) -> None:
    for control in dialog.descendants()[:512]:
        with suppress(Exception):
            if control.class_name().casefold() in {
                "button",
                "tbutton",
            } and control.window_text().strip().casefold() in {"ok", "ок"}:
                _send_window_message(int(control.handle), 0x00F5)
                break
    else:
        _post_window_message(int(dialog.handle), 0x0010)
    deadline = time.monotonic() + min(5.0, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            if not dialog.is_visible():
                return
        except Exception:
            return
        time.sleep(0.05)
    raise HeadlessGuiError("DipTrace result dialog did not close")


def _wait_for_exit(app: Any, timeout_seconds: float, label: str) -> None:
    try:
        app.wait_for_process_exit(timeout=min(15.0, timeout_seconds))
    except Exception as exc:
        raise HeadlessGuiError(f"{label} did not exit normally") from exc


def _native_worker_evidence(
    request: PcbNativeAcceptanceRequest, *, desktop_name: str
) -> NativePcbWorkerEvidence:
    request = _validate_request(request)
    project_sha_before = _sha256(request.project)
    application_class = _pywinauto_application()
    steps: list[dict[str, Any]] = []
    pids: list[int] = []
    drc_status: DrcStatus = "not_run"
    drc_texts: list[str] = []
    app: Any = None
    forced = False
    error: str | None = None
    saved_project = request.project

    def step(name: str, status: str, **evidence: Any) -> None:
        steps.append({"name": name, "status": status, **evidence})

    try:
        command = subprocess.list2cmdline(
            [str(request.diptrace_root / "Pcb.exe"), str(request.project)]
        )
        app = application_class(backend="win32").start(command, timeout=request.timeout_seconds)
        pids.append(int(app.process))
        window = _main_window(app, request.project, request.timeout_seconds)
        window.wait("exists enabled", timeout=request.timeout_seconds)
        step("open", "completed", pid=int(app.process))

        refill_menu = _post_menu_path(
            window,
            request.refill_menu,
            _REFILL_MENU_FALLBACKS,
            timeout_seconds=request.timeout_seconds,
        )
        step("refill_copper", "posted", menu=refill_menu)

        drc_menu = _post_menu_path(
            window, request.drc_menu, timeout_seconds=request.timeout_seconds
        )
        dialog = _visible_dialog(app, request.timeout_seconds)
        dialog_class = str(dialog.class_name())
        drc_texts = _dialog_texts(dialog)
        drc_status = classify_drc_dialog(drc_texts, request.drc_success_tokens, dialog_class)
        step(
            "run_drc",
            "completed",
            menu=drc_menu,
            drc_status=drc_status,
            dialog_class=dialog_class,
            dialog_texts=drc_texts,
        )
        _dismiss_dialog(dialog, request.timeout_seconds)

        _save_window(window, "File->Save")
        if request.project.suffix.casefold() == ".dipxml":
            saved_project = request.output_xml.with_name(
                f".{request.output_xml.stem}.{uuid.uuid4().hex}.saved.dipxml"
            )
            save_dialog = _visible_dialog(app, request.timeout_seconds)
            _save_dialog_as_xml(int(save_dialog.handle), saved_project)
            _wait_for_export(app, saved_project, request.timeout_seconds)
            step(
                "save",
                "completed",
                menu="File->Save",
                temporary_xml_sha256=_sha256(saved_project),
            )
        else:
            step("save", "posted", menu="File->Save")
        _post_window_message(int(window.handle), 0x0010)
        _wait_for_exit(app, request.timeout_seconds, "DipTrace PCB save/close phase")
        step("close", "completed")

        reopen_command = subprocess.list2cmdline(
            [str(request.diptrace_root / "Pcb.exe"), str(saved_project)]
        )
        app = application_class(backend="win32").start(
            reopen_command, timeout=request.timeout_seconds
        )
        pids.append(int(app.process))
        reopened = _main_window(app, saved_project, request.timeout_seconds)
        reopened.wait("exists enabled", timeout=request.timeout_seconds)
        step("reopen", "completed", pid=int(app.process))

        save_as_menu = _post_menu_path(
            reopened, request.save_as_menu, timeout_seconds=request.timeout_seconds
        )
        save_dialog = _visible_dialog(app, request.timeout_seconds)
        _save_dialog_as_xml(int(save_dialog.handle), request.output_xml)
        _wait_for_export(app, request.output_xml, request.timeout_seconds)
        step(
            "export_xml",
            "completed",
            menu=save_as_menu,
            output_sha256=_sha256(request.output_xml),
        )
        _post_window_message(int(reopened.handle), 0x0010)
        _wait_for_exit(app, request.timeout_seconds, "DipTrace PCB re-export phase")
        step("close_reopened", "completed")
    except Exception as exc:
        titles = _window_titles(app) if app is not None else []
        suffix = f"; open windows: {titles!r}" if titles else ""
        error = f"{type(exc).__name__}: {exc}{suffix}"
        step("pipeline", "failed", error=error)
        if app is not None:
            with suppress(Exception):
                forced = True
                app.kill(soft=False)
        request.output_xml.unlink(missing_ok=True)

    if saved_project != request.project:
        saved_project.unlink(missing_ok=True)

    return NativePcbWorkerEvidence(
        completed=error is None and request.output_xml.is_file(),
        project=str(request.project),
        output_xml=str(request.output_xml),
        project_sha256_before=project_sha_before,
        project_sha256_after=_sha256(request.project),
        output_xml_sha256=_sha256(request.output_xml),
        drc_status=drc_status,
        drc_texts=drc_texts,
        native_steps=steps,
        worker_pid=os.getpid(),
        diptrace_pids=pids,
        desktop_mode=request.desktop_mode,
        desktop_name=desktop_name,
        window_station_name=process_window_station_name(),
        session_id=process_session_id(),
        forced_termination=forced,
        error=error,
    )


def _immutable_baseline(request: PcbNativeAcceptanceRequest, root: Path) -> Path | None:
    source = request.baseline_xml
    if source is None and request.project.suffix.casefold() == ".dipxml":
        source = request.project
    if source is None:
        return None
    data = source.read_bytes()
    if len(data) > _MAX_XML_BYTES:
        raise HeadlessGuiError(f"baseline XML is larger than {_MAX_XML_BYTES} bytes")
    snapshot = root / "baseline.dipxml"
    snapshot.write_bytes(data)
    return snapshot


def _semantic_delta(before: Path, after: Path) -> dict[str, Any]:
    before_document = DipTraceDocument.load(before, _MAX_XML_BYTES)
    after_document = DipTraceDocument.load(after, _MAX_XML_BYTES)
    if before_document.kind != "pcb" or after_document.kind != "pcb":
        raise ValueError("semantic comparison requires two DipTrace PCB XML documents")
    return cast(
        dict[str, Any],
        compare_xml_semantics(before_document, after_document).model_dump(mode="json"),
    )


def _finalize_result(
    request: PcbNativeAcceptanceRequest,
    worker: NativePcbWorkerEvidence,
    baseline_snapshot: Path | None,
    *,
    input_before: str | None,
    input_after: str | None,
    station_after: str | None,
    session_after: int | None,
) -> PcbNativeAcceptanceResult:
    completed = worker.completed
    error = worker.error
    structural_before: dict[str, Any] | None = None
    structural_after: dict[str, Any] | None = None
    structural_delta: dict[str, dict[str, Any]] = {}
    semantic_delta: dict[str, Any] | None = None
    manual_reasons: list[str] = []

    if completed and request.output_xml.is_file():
        try:
            structural_after = summarize_pcb_xml(request.output_xml)
            if baseline_snapshot is None:
                manual_reasons.append(
                    "No immutable baseline XML was available for semantic comparison."
                )
            else:
                structural_before = summarize_pcb_xml(baseline_snapshot)
                structural_delta = _structural_delta(structural_before, structural_after)
                semantic_delta = _semantic_delta(baseline_snapshot, request.output_xml)
        except Exception as exc:
            completed = False
            error = f"{type(exc).__name__}: {exc}"

    if not completed or error is not None or worker.drc_status == "fail" or structural_delta:
        verdict: Verdict = "FAIL"
    else:
        semantic_equal = bool(
            semantic_delta is not None and semantic_delta.get("semantic_equal") is True
        )
        if worker.drc_status != "pass":
            manual_reasons.append(
                "The DRC dialog did not match a verified success token for this UI locale/build."
            )
        if semantic_delta is not None and not semantic_equal:
            manual_reasons.append(
                "Native refill/save/re-export changed the full XML semantic fingerprint; "
                "the stable structural invariants still require bounded review."
            )
        verdict = (
            "PASS"
            if worker.drc_status == "pass" and semantic_equal and not manual_reasons
            else "HUMAN_REVIEW_REQUIRED"
        )

    if input_before is not None and input_after is not None and input_before != input_after:
        verdict = "FAIL"
        error = error or (
            f"input desktop changed unexpectedly: {input_before!r} -> {input_after!r}"
        )
    if (
        worker.window_station_name is not None
        and station_after is not None
        and worker.window_station_name.casefold() != station_after.casefold()
    ):
        verdict = "FAIL"
        error = error or "window station identity changed across native evidence run"
    if (
        worker.session_id is not None
        and session_after is not None
        and worker.session_id != session_after
    ):
        verdict = "FAIL"
        error = error or "Windows session identity changed across native evidence run"

    implicit_baseline = request.project if request.project.suffix.casefold() == ".dipxml" else None
    return PcbNativeAcceptanceResult(
        verdict=verdict,
        completed=completed,
        project=worker.project or str(request.project),
        output_xml=worker.output_xml or str(request.output_xml),
        baseline_xml=str(request.baseline_xml or implicit_baseline)
        if request.baseline_xml is not None or implicit_baseline is not None
        else None,
        project_sha256_before=worker.project_sha256_before,
        project_sha256_after=worker.project_sha256_after,
        output_xml_sha256=worker.output_xml_sha256,
        drc_status=worker.drc_status,
        drc_texts=worker.drc_texts,
        structural_before=structural_before,
        structural_after=structural_after,
        structural_delta=structural_delta,
        semantic_delta=semantic_delta,
        native_steps=worker.native_steps,
        worker_pid=worker.worker_pid,
        diptrace_pids=worker.diptrace_pids,
        automation_backend=worker.automation_backend,
        desktop_mode=request.desktop_mode,
        desktop_name=worker.desktop_name,
        input_desktop_before=input_before,
        input_desktop_after=input_after,
        window_station_name=station_after,
        session_id=session_after,
        forced_termination=worker.forced_termination,
        manual_review_reasons=manual_reasons,
        error=error,
    )


def _worker_argv(*args: str) -> list[str]:
    if bool(sys.__dict__.get("frozen", False)):
        return [sys.executable, "pcb-acceptance", "_worker", *args]
    return [sys.executable, "-m", "diptrace_mcp.pcb_native_acceptance", "_worker", *args]


def run_pcb_native_acceptance(
    request: PcbNativeAcceptanceRequest,
) -> PcbNativeAcceptanceResult:
    if os.name != "nt":
        raise HeadlessGuiError("native PCB acceptance is available only on Windows")
    request = _validate_request(request)
    if request.desktop_mode == "native" and process_is_elevated():
        raise HeadlessGuiError(
            "native launch declined from an elevated process; run with the normal user token"
        )
    input_before = input_desktop_name()
    station_before = process_window_station_name()
    session_before = process_session_id()
    if request.desktop_mode == "native":
        _interactive_context()

    with tempfile.TemporaryDirectory(prefix="diptrace-pcb-native-acceptance-") as raw:
        temp = Path(raw)
        baseline_snapshot = _immutable_baseline(request, temp)
        request_path = temp / "request.json"
        result_path = temp / "worker-result.json"
        payload = request.model_dump(mode="json")
        payload["_expected_window_station"] = station_before
        payload["_expected_session_id"] = session_before
        _write_json(request_path, payload)
        desktop_name = f"DipTracePCB-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        argv_args = (
            "--request",
            str(request_path),
            "--result",
            str(result_path),
            "--desktop-name",
        )
        if request.desktop_mode == "native":
            if input_before is None:
                raise HeadlessGuiError("cannot determine the current input desktop")
            desktop_name = input_before
            with _launch_on_current_desktop(_worker_argv(*argv_args, desktop_name)) as process:
                exit_code = process.wait(request.timeout_seconds * 2 + 30.0)
                if exit_code is None:
                    process.terminate(124)
                    process.wait(2.0)
                    raise HeadlessGuiError("native PCB acceptance worker timed out")
        else:
            with HiddenDesktop(desktop_name) as desktop:
                with desktop.launch(_worker_argv(*argv_args, desktop_name)) as process:
                    exit_code = process.wait(request.timeout_seconds * 2 + 30.0)
                    if exit_code is None:
                        process.terminate(124)
                        process.wait(2.0)
                        raise HeadlessGuiError("headless PCB acceptance worker timed out")
        if not result_path.is_file():
            raise HeadlessGuiError(
                f"PCB acceptance worker exited with code {exit_code} without a result"
            )
        worker = NativePcbWorkerEvidence.model_validate(_load_json(result_path))
        return _finalize_result(
            request,
            worker,
            baseline_snapshot,
            input_before=input_before,
            input_after=input_desktop_name(),
            station_after=process_window_station_name(),
            session_after=process_session_id(),
        )


def _cmd_worker(args: argparse.Namespace) -> int:
    result_path = Path(str(args.result))
    try:
        payload = _load_json(Path(str(args.request)))
        expected_station = payload.pop("_expected_window_station", None)
        expected_session = payload.pop("_expected_session_id", None)
        request = PcbNativeAcceptanceRequest.model_validate(payload)
        actual_desktop = thread_desktop_name()
        expected_desktop = str(args.desktop_name)
        if actual_desktop.casefold() != expected_desktop.casefold():
            raise HeadlessGuiError(
                f"worker connected to unexpected desktop: "
                f"{actual_desktop!r} != {expected_desktop!r}"
            )
        actual_station = process_window_station_name()
        if not isinstance(expected_station, str) or (
            actual_station.casefold() != expected_station.casefold()
        ):
            raise HeadlessGuiError("worker connected to unexpected window station")
        if (
            not isinstance(expected_session, int)
            or isinstance(expected_session, bool)
            or process_session_id() != expected_session
        ):
            raise HeadlessGuiError("worker connected to unexpected Windows session")
        if request.desktop_mode == "native" and process_is_elevated():
            raise HeadlessGuiError("native worker unexpectedly has an elevated token")
        result = _native_worker_evidence(request, desktop_name=expected_desktop)
    except Exception as exc:
        result = NativePcbWorkerEvidence(
            desktop_name=str(args.desktop_name),
            error=f"{type(exc).__name__}: {exc}",
        )
    _write_json(result_path, result.model_dump(mode="json"))
    return 0 if result.completed else 1


def _cmd_run(args: argparse.Namespace) -> int:
    output_xml = Path(str(args.output_xml))
    evidence_json = (
        Path(str(args.evidence_json))
        if args.evidence_json
        else output_xml.with_name(f"{output_xml.stem}.native-evidence.json")
    )
    if evidence_json.resolve(strict=False) == output_xml.resolve(strict=False):
        payload: dict[str, Any] = {
            "ok": False,
            "verdict": "FAIL",
            "error": "evidence JSON must be distinct from output XML",
        }
        print(json.dumps(payload, indent=2))
        return 1
    if evidence_json.exists():
        payload = {
            "ok": False,
            "verdict": "FAIL",
            "error": f"evidence JSON already exists: {evidence_json}",
        }
        print(json.dumps(payload, indent=2))
        return 1
    request = PcbNativeAcceptanceRequest(
        diptrace_root=Path(str(args.diptrace_root)),
        project=Path(str(args.project)),
        output_xml=output_xml,
        baseline_xml=Path(str(args.baseline_xml)) if args.baseline_xml else None,
        timeout_seconds=float(args.timeout),
        desktop_mode=cast(DesktopMode, str(args.desktop)),
        refill_menu=str(args.refill_menu),
        drc_menu=str(args.drc_menu),
        save_as_menu=str(args.save_as_menu),
        drc_success_tokens=tuple(args.drc_success_token or _DEFAULT_DRC_SUCCESS_TOKENS),
    )
    try:
        result = run_pcb_native_acceptance(request)
        payload = result.public_payload()
    except (HeadlessGuiError, OSError, ValueError) as exc:
        payload = {"ok": False, "verdict": "FAIL", "error": str(exc)}
    payload["evidence_json"] = str(evidence_json)
    _write_json(evidence_json, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("verdict") == "PASS":
        return 0
    return 2 if payload.get("verdict") == "HUMAN_REVIEW_REQUIRED" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-pcb-native-acceptance",
        description="Collect bounded native PCB refill/DRC/round-trip evidence from DipTrace.",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run", help="run native PCB acceptance on a real DipTrace host")
    run.add_argument("--diptrace-root", required=True)
    run.add_argument("--project", required=True)
    run.add_argument("--output-xml", required=True)
    run.add_argument("--baseline-xml")
    run.add_argument("--evidence-json")
    run.add_argument("--timeout", type=float, default=90.0)
    run.add_argument("--desktop", choices=("hidden", "native"), default="hidden")
    run.add_argument("--refill-menu", default=_DEFAULT_REFILL_MENU)
    run.add_argument("--drc-menu", default=_DEFAULT_DRC_MENU)
    run.add_argument("--save-as-menu", default=_DEFAULT_SAVE_AS_MENU)
    run.add_argument("--drc-success-token", action="append")
    run.set_defaults(handler=_cmd_run)

    worker = subs.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--request", required=True)
    worker.add_argument("--result", required=True)
    worker.add_argument("--desktop-name", required=True)
    worker.set_defaults(handler=_cmd_worker)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
