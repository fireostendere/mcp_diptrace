"""Collect native schematic evidence on an owned hidden desktop, never on the source."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from . import cinematic_recording as cr
from . import headless_gui as hg
from .windows_job import KillOnCloseJob
from .xml_document import DipTraceDocument

_EXE_SHA = "d85632b2c8fb445471339e875416782e3e62fb56ea13ab7d973052122352f568"
_MAX_BYTES = 128 * 1024 * 1024
# Reviewed lossless client image: English "No errors found", same pinned editor.
_ERC_CLEAR_SHA = "1338c992f812c02ca9777e8a035d4d23dcd5e8dccde5dd2b3cdbe51a779027e0"
# Reviewed native File/Verification images and initialized 5.3.0.3 menu inventory.
_MENU_PROFILES = {
    ("File", "Save As..."): (
        (2, 3, 4, 10, 11, 12, 13, 14, 27, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61),
        frozenset({6, 9, 13, 17, 20}),
        4,
    ),
    ("Verification", "Electrical Rule Check"): ((282, 283, 284), frozenset(), 0),
}
# Reviewed builds: version, initialized menu inventory, "No errors found" ERC images.
# 5.3.5.1 has the same main-form menu items at these positions; its command IDs
# shift because File > Import and View > Drawing Mode gained entries (CI inventory).
_BUILDS: dict[str, tuple[str, dict[tuple[str, str], Any], frozenset[str]]] = {
    _EXE_SHA: ("5.3.0.3", _MENU_PROFILES, frozenset({_ERC_CLEAR_SHA})),
    "0ba7c41229b3c63766e7c67f5624cc6b284d4498de9a45768496667e4a0e8ea0": (
        "5.3.5.1",
        {
            ("File", "Save As..."): (
                (2, 3, 4, 10, 11, 12, 13, 14, 28, *range(50, 63)),
                frozenset({6, 9, 13, 17, 20}),
                4,
            ),
            ("Verification", "Electrical Rule Check"): ((285, 286, 287), frozenset(), 0),
        },
        frozenset({"91d51dc32df6900dbfabf84dc04dd9cb6fe104bb4d4a171677e9b8387447fcac"}),
    ),
}


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _validate_source(source: Path, expected_sha: str) -> None:
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".dchxml":
        raise ValueError("source must be a regular schematic XML file")
    if source.stat().st_size > _MAX_BYTES or hg._sha256(source) != expected_sha:
        raise ValueError("source size or SHA-256 guard failed")
    if DipTraceDocument.load(source, _MAX_BYTES).kind != "schematic":
        raise ValueError("source is not a DipTrace schematic")


def _startup_hashes(value: Any) -> list[str]:
    hashes = [] if value is None else [value] if isinstance(value, str) else value
    if not isinstance(hashes, list) or any(
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in hashes
    ):
        raise ValueError("startup dialog hashes must be exact lowercase SHA-256 values")
    return hashes


def _require_menu_ready(app: Any, window: Any) -> None:
    if hg._owned_dialogs(app, window) or not window.is_enabled() or window.menu() is None:
        raise hg.HeadlessGuiError("project is blocked by a native dialog, not menu-ready")


def _window_evidence(window: Any) -> dict[str, Any]:
    evidence: dict[str, Any] = {"handle": int(window.handle)}
    for field, method in (
        ("title", "window_text"), ("class", "class_name"), ("visible", "is_visible"),
        ("enabled", "is_enabled"), ("pid", "process_id"),
    ):
        with suppress(Exception):
            evidence[field] = getattr(window, method)()
    with suppress(Exception):
        parent = window.parent()
        evidence["owner_handle"] = int(parent.handle) if parent else None
    with suppress(Exception):
        evidence["controls"] = [
            {"class": child.class_name(), "title": child.window_text(), "id": child.control_id()}
            for child in window.descendants()[:32]
        ]
    return evidence


def _menu(window: Any, executable: Path, section: str, label: str) -> str:
    root_item = cr._find_exact_menu_item(window.menu(), section, menu_name="root")
    submenu = cr._initialized_submenu(window, root_item)
    matches = cr._menu_items_named(submenu, label)
    if not matches and (section, label) in _MENU_PROFILES:
        digest = hg._sha256(executable) or ""
        if digest not in _BUILDS:
            raise hg.HeadlessGuiError("unverified schematic menu executable")
        version, profiles, _ = _BUILDS[digest]
        ids, separators, target = profiles[section, label]
        items = cr._pinned_menu_items(submenu, ids, separators, menu_name=section)
        if items[target].sub_menu() is not None:
            raise hg.HeadlessGuiError("expected schematic menu leaf")
        hg._post_menu_item(window, items[target])
        return f"schematic-{version}-en-{section}-{ids[target]}-{digest[:8]}"
    if len(matches) != 1:
        raise hg.HeadlessGuiError(
            f"unverified {section}->{label} menu: "
            + json.dumps(cr._menu_snapshot(submenu, section))
        )
    hg._post_menu_item(window, matches[0])
    return "exact-text-path"


def _capture(window: Any, folder: Path, name: str) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise hg.HeadlessGuiError("ffmpeg is required for --capture")
    video, image = folder / f"{name}.mp4", folder / f"{name}.png"
    client_image = folder / f"{name}.client.png"
    if any(path.exists() for path in (video, image, client_image)):
        raise FileExistsError("capture output already exists")
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise hg.HeadlessGuiError("Win32 API is required for native capture")
    user32 = windll.user32

    def snapshot(
        capture: Callable[[], bytes],
        width: int,
        height: int,
    ) -> None:
        frame = capture()
        bounds, client = wintypes.RECT(), wintypes.RECT()
        origin = wintypes.POINT()
        if not (
            user32.GetWindowRect(int(window.handle), ctypes.byref(bounds))
            and user32.GetClientRect(int(window.handle), ctypes.byref(client))
            and user32.ClientToScreen(int(window.handle), ctypes.byref(origin))
        ):
            raise hg.HeadlessGuiError("cannot bind captured client rectangle")
        x, y = origin.x - bounds.left, origin.y - bounds.top
        box = (x, y, x + client.right, y + client.bottom)
        if not (0 <= x < box[2] <= width and 0 <= y < box[3] <= height):
            raise hg.HeadlessGuiError("captured client rectangle is out of bounds")
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-n",
                "-f",
                "rawvideo",
                "-pixel_format",
                "bgr0",
                "-video_size",
                f"{width}x{height}",
                "-i",
                "pipe:0",
                "-frames:v",
                "1",
                str(image),
                "-vf",
                f"crop={client.right}:{client.bottom}:{x}:{y}",
                "-frames:v",
                "1",
                str(client_image),
            ],
            input=frame,
            check=True,
            timeout=15,
            capture_output=True,
        )

    cr._record_printwindow_video(
        user32=user32,
        hwnd=int(window.handle),
        ffmpeg=ffmpeg,
        output=video,
        fps=2,
        duration_seconds=0.6,
        playback=lambda: None,
        prepare=snapshot,
    )
    digest = hg._sha256(client_image)
    if digest is None:
        raise hg.HeadlessGuiError("captured client image is missing or unreadable")
    return digest


def _worker(request: dict[str, Any]) -> dict[str, Any]:
    folder = Path(request["output_dir"])
    source = folder / "input.dchxml"
    executable = Path(request["diptrace_root"]) / "Schematic.exe"
    report: dict[str, Any] = {
        "completed": False,
        "worker_pid": os.getpid(),
        "diptrace_pids": [],
        "native_steps": [],
        "forced_termination": False,
        "erc_status": "not_run",
        "startup_dialogs": [],
        "desktop_name": hg.thread_desktop_name(),
        "window_station_name": hg.process_window_station_name(),
        "session_id": hg.process_session_id(),
        "executable_sha256": hg._sha256(executable),
    }
    process = None
    window = None
    app = None
    try:
        startup_hashes = _startup_hashes(request.get("startup_dialog_sha256"))
        if hg.process_is_elevated() or report["desktop_name"] != request["desktop_name"]:
            raise hg.HeadlessGuiError("worker token or desktop mismatch")
        if (report["window_station_name"], report["session_id"]) != (
            request["station"],
            request["session"],
        ):
            raise hg.HeadlessGuiError("worker station/session mismatch")
        if report["executable_sha256"] not in _BUILDS:
            raise hg.HeadlessGuiError("unverified Schematic.exe build")
        _validate_source(source, request["source_sha256"])
        phases = (
            [("inspect", source, None)]
            if request["inspect"]
            else [
                ("open_save", source, folder / "open-save.dchxml"),
                ("reopen_export", folder / "open-save.dchxml", folder / "reexport.dchxml"),
                ("reopen_final", folder / "reexport.dchxml", None),
            ]
        )
        for name, project, target in phases:
            process = hg._launch_process_on_desktop(
                [str(executable), str(project)],
                f"{request['station']}\\{request['desktop_name']}",
            )
            report["diptrace_pids"].append(process.pid)
            app = hg._pywinauto_application()(backend="win32")
            app.connect(process=process.pid, timeout=30)
            window = hg._main_window(app, project, 30)
            window.wait("exists enabled", timeout=30)
            if window.menu() is None and window.class_name() == "TFMyMessage":
                if window.process_id() != process.pid or hg._owned_dialogs(app, window):
                    raise hg.HeadlessGuiError(
                        "startup dialog ownership or uniqueness is unverified"
                    )
                fingerprint = _capture(window, folder, f"{name}-startup")
                report["startup_dialogs"].append(
                    {"phase": name, "client_sha256": fingerprint, **_window_evidence(window)}
                )
                if fingerprint not in startup_hashes:
                    raise hg.HeadlessGuiError(
                        "unreviewed startup dialog image; acknowledgement refused"
                    )
                buttons = [
                    child
                    for child in window.descendants()
                    if child.class_name() == "TButton"
                    and child.window_text() == "OK"
                    and child.is_enabled()
                    and child.is_visible()
                ]
                if len(buttons) != 1:
                    raise hg.HeadlessGuiError("reviewed startup dialog has no unique OK button")
                hg._post_window_message(int(buttons[0].handle), 0x00F5)
                report["startup_dialogs"][-1]["acknowledged"] = True
                app.window(handle=int(window.handle)).wait_not("visible", timeout=10)
                window = hg._main_window(app, project, 30)
            _require_menu_ready(app, window)
            report["native_steps"].append(
                {"step": name, "opened": str(project), "status": "started"}
            )
            if name in {"inspect", "open_save"}:
                menus = {}
                for section in ("File", "Verification", "View"):
                    item = cr._find_exact_menu_item(window.menu(), section, menu_name="root")
                    menus[section] = cr._menu_snapshot(
                        cr._initialized_submenu(window, item), section
                    )
                _write_new(folder / "menus.json", menus)
                if request["capture"]:
                    _require_menu_ready(app, window)
                    windll = getattr(ctypes, "windll", None)
                    if windll is None:
                        raise hg.HeadlessGuiError("Win32 API is required for capture")
                    user32 = windll.user32
                    with cr._physical_pixel_dpi_context(user32):
                        user32.ShowWindow(int(window.handle), 9)
                        window.move_window(x=0, y=0, width=3000, height=2000, repaint=True)
                    time.sleep(0.5)
                    _require_menu_ready(app, window)
                    cr._zoom_extents_via_native_menu(process.pid, int(window.handle), executable)
                    time.sleep(0.5)
                    _require_menu_ready(app, window)
                    _capture(window, folder, "sheet")
            if target is not None:
                if target.exists():
                    raise FileExistsError(target)
                _require_menu_ready(app, window)
                profile = _menu(window, executable, "File", "Save As...")
                dialog = hg._visible_dialog(app, 15, owner=window, save_as=True)
                hg._save_dialog_as_xml(int(dialog.handle), target)
                hg._wait_for_export(app, target, 30)
                if DipTraceDocument.load(target, _MAX_BYTES).kind != "schematic":
                    raise hg.HeadlessGuiError("native export is not schematic XML")
                report["native_steps"][-1].update(
                    exported=str(target),
                    sha256=hg._sha256(target),
                    menu_profile=profile,
                )
            if request["erc"] and name in {"inspect", "reopen_final"}:
                _require_menu_ready(app, window)
                profile = _menu(window, executable, "Verification", "Electrical Rule Check")
                deadline = time.monotonic() + 30
                while True:
                    dialogs = [
                        candidate
                        for candidate in app.windows(visible_only=True, enabled_only=True)
                        if candidate.class_name() in {"TForm32", "TFMyMessage"}
                    ]
                    if len(dialogs) == 1:
                        break
                    if time.monotonic() >= deadline:
                        raise hg.HeadlessGuiError("native ERC result is absent or ambiguous")
                    time.sleep(0.1)
                dialog = dialogs[0]
                controls = [
                    {
                        "class": child.class_name(),
                        "title": child.window_text(),
                        "texts": child.texts(),
                        "handle": int(child.handle),
                    }
                    for child in dialog.descendants()[:128]
                ]
                report["erc_status"] = "review_required"
                evidence = {
                    "class": dialog.class_name(),
                    "title": dialog.window_text(),
                    "menu_profile": profile,
                    "controls": controls,
                    "client_sha256": _capture(dialog, folder, "erc"),
                }
                if (
                    evidence["class"] == "TFMyMessage"
                    and evidence["client_sha256"] in _BUILDS[report["executable_sha256"]][2]
                ):
                    report["erc_status"] = "no_errors_found"
                evidence["status"] = report["erc_status"]
                _write_new(folder / "erc.json", evidence)
                hg._post_window_message(int(dialog.handle), 0x0010)
                app.window(handle=int(dialog.handle)).wait_not("visible", timeout=5)
            hg._post_window_message(int(window.handle), 0x0010)
            if process.wait(10) is None:
                raise hg.HeadlessGuiError("owned Schematic.exe did not close normally")
            report["native_steps"][-1]["closed"] = True
            report["native_steps"][-1]["status"] = "completed"
            process.close()
            process = window = None
        if hg._sha256(source) != request["source_sha256"]:
            raise hg.HeadlessGuiError("isolated input changed unexpectedly")
        report["completed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["error_traceback"] = traceback.format_exc()[-8000:]
        if report["native_steps"] and report["native_steps"][-1]["status"] == "started":
            report["native_steps"][-1]["status"] = "failed"
        report["error_windows"] = []
        if app is not None:
            candidates = []
            with suppress(Exception):
                # Put visible windows first: dozens of hidden Delphi forms must not hide the modal.
                candidates = app.windows(visible_only=True)
                seen = {int(candidate.handle) for candidate in candidates}
                candidates += [
                    candidate for candidate in app.windows(visible_only=False)
                    if int(candidate.handle) not in seen
                ]
                if window is not None:
                    modal_handles = {int(modal.handle) for modal in hg._owned_dialogs(app, window)}
                    candidates.sort(
                        key=lambda candidate: int(candidate.handle) not in modal_handles
                    )
            captures = 0
            for candidate in candidates[:64]:
                with suppress(Exception):
                    evidence = _window_evidence(candidate)
                    report["error_windows"].append(evidence)
                    if candidate.is_visible() and candidate.menu() is None and captures < 8:
                        image_name = f"rejected-dialog-{captures}"
                        captures += 1
                        evidence["client_image"] = str(folder / f"{image_name}.client.png")
                        try:
                            evidence["client_sha256"] = _capture(candidate, folder, image_name)
                        except Exception as capture_error:
                            evidence["capture_error"] = str(capture_error)
    finally:
        if process is not None:
            if window is not None:
                with suppress(Exception):
                    hg._post_window_message(int(window.handle), 0x0010)
            if process.wait(2) is None:
                report["forced_termination"] = True
                process.terminate(126)
                process.wait(2)
            process.close()
    return report


def run(args: argparse.Namespace) -> dict[str, Any]:
    source, folder = Path(args.project), Path(args.output_dir)
    _validate_source(source, args.expected_sha256)
    startup_hashes = _startup_hashes(args.startup_dialog_sha256)
    if not math.isfinite(args.timeout) or not 30 <= args.timeout <= 300:
        raise ValueError("timeout must be finite and between 30 and 300 seconds")
    if os.name != "nt" or hg.process_is_elevated():
        raise hg.HeadlessGuiError("non-elevated Windows process required")
    if hg._sha256(Path(args.diptrace_root) / "Schematic.exe") not in _BUILDS:
        raise hg.HeadlessGuiError("unverified Schematic.exe build")
    if any(path.is_symlink() for path in (folder, *folder.parents)):
        raise ValueError("output directory must not traverse symlinks")
    folder.mkdir(exist_ok=False)
    with (folder / "input.dchxml").open("xb") as stream, source.open("rb") as original:
        shutil.copyfileobj(original, stream)
    _validate_source(folder / "input.dchxml", args.expected_sha256)
    before = hg.input_desktop_name()
    request = {
        "output_dir": str(folder.resolve()),
        "diptrace_root": args.diptrace_root,
        "source_sha256": args.expected_sha256,
        "inspect": args.inspect,
        "capture": args.capture,
        "erc": args.erc,
        "startup_dialog_sha256": startup_hashes,
        "station": hg.process_window_station_name(),
        "session": hg.process_session_id(),
        "desktop_name": f"DipTraceSchematic-{os.getpid()}-{uuid.uuid4().hex[:8]}",
    }
    if before is None or request["station"].casefold() != "winsta0":
        raise hg.HeadlessGuiError("interactive desktop identity is unavailable")
    _write_new(folder / "request.json", request)
    report: dict[str, Any] = {"completed": False}
    try:
        with hg.HiddenDesktop(request["desktop_name"]) as desktop:
            job = KillOnCloseJob.create()
            try:
                argv = [sys.executable, "-B", "-m", __spec__.name, "_worker", str(folder.resolve())]
                with desktop.launch(argv, job=job) as worker:
                    code = worker.wait(args.timeout)
                    if code is None:
                        job.terminate_and_close()
                        worker.wait(2)
                        raise hg.HeadlessGuiError("schematic evidence worker timed out")
            finally:
                job.terminate_and_close()
        report = hg._load_json(folder / "worker-result.json")
        if code != 0:
            report["completed"] = False
    except Exception as exc:
        report.update(completed=False, error=f"{type(exc).__name__}: {exc}")
    after = hg.input_desktop_name()
    report.update(
        source=str(source),
        source_sha256=args.expected_sha256,
        source_sha256_after=hg._sha256(source),
        input_desktop_before=before,
        input_desktop_after=after,
        mode="inspect" if args.inspect else "export",
    )
    if (
        before != after
        or (hg.process_window_station_name(), hg.process_session_id())
        != (
            request["station"],
            request["session"],
        )
        or hg._sha256(source) != args.expected_sha256
    ):
        report.update(completed=False, error="source or desktop/session identity changed")
    _write_new(folder / "result.json", report)
    return report


def main() -> int:
    if sys.argv[1:2] == ["_worker"]:
        folder = Path(sys.argv[2])
        report = _worker(hg._load_json(folder / "request.json"))
        _write_new(folder / "worker-result.json", report)
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--diptrace-root", required=True)
        parser.add_argument("--project", required=True)
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--timeout", type=float, default=180)
        parser.add_argument("--inspect", action="store_true")
        parser.add_argument("--capture", action="store_true")
        parser.add_argument(
            "--erc", action="store_true", help="Capture native ERC result for review"
        )
        parser.add_argument(
            "--startup-dialog-sha256", action="append",
            help="Exact SHA-256 of a reviewed client PNG; repeat for reviewed variants"
        )
        report = run(parser.parse_args())
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
