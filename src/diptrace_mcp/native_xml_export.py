"""Export native projects on an owned hidden desktop without saving the source.

An export is evidence for inspection, not an ERC/DRC or manufacturing acceptance.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import suppress
from ctypes import wintypes
from pathlib import Path
from typing import Any

from . import headless_gui as hg
from .windows_configurator import validate_diptrace_directory
from .xml_document import DipTraceDocument

_KINDS = {
    ".dch": ("schematic", ".dchxml", "DipTrace-Schematic"),
    ".dip": ("pcb", ".dipxml", "DipTrace-PCB"),
}
_MAX_BYTES = 128 * 1024 * 1024


def export_native_xml(
    diptrace_root: Path,
    project: Path,
    output_xml: Path,
    timeout: float = 90.0,
    startup_dialog_sha256: str | None = None,
) -> dict[str, Any]:
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError("timeout must be finite, > 0 and <= 300 seconds")
    if startup_dialog_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", startup_dialog_sha256
    ):
        raise ValueError("startup dialog approval must be a lowercase SHA-256")
    if project.is_symlink() or not project.is_file() or project.suffix.lower() not in _KINDS:
        raise ValueError("project must be a regular native .dch or .dip file")
    source = project.resolve()
    _, suffix, source_type = _KINDS[source.suffix.lower()]
    if output_xml.is_symlink() or output_xml.exists():
        raise FileExistsError(output_xml)
    target = output_xml.resolve()
    if target.suffix.lower() != suffix or target == source:
        raise ValueError(f"output must be a separate {suffix} file")
    if source.stat().st_size > _MAX_BYTES:
        raise ValueError("source exceeds the document size limit")
    before = hg._sha256(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".diptrace-export-", dir=target.parent) as raw:
        folder = Path(raw)
        private_source = folder / source.name
        private_output = folder / ("export" + suffix)
        shutil.copy2(source, private_source)
        if hg._sha256(private_source) != before:
            raise RuntimeError("source changed while copying")
        result = _run_hidden(
            diptrace_root, private_source, private_output, timeout, startup_dialog_sha256
        )
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "native XML export failed")))
        after = hg._sha256(source)
        if after != before:
            raise RuntimeError("source changed during export; no original was restored")
        document = DipTraceDocument.load(private_output, _MAX_BYTES)
        if document.source_type != source_type:
            raise ValueError(f"native export has unexpected type {document.source_type!r}")
        # Exclusive creation also protects a file created after the initial check.
        with target.open("xb") as destination, private_output.open("rb") as exported:
            shutil.copyfileobj(exported, destination)
        return {
            **result,
            "source": str(source),
            "output_xml": str(target),
            "source_sha256_before": before,
            "source_sha256_after": after,
            "source_type": source_type,
            "xml_sha256": document.sha256,
            "xml_version": document.version,
            "erc_drc": "not_run",
        }


def _run_hidden(
    root: Path, source: Path, output: Path, timeout: float, startup_dialog_sha256: str | None = None
) -> dict[str, Any]:
    if os.name != "nt":
        raise hg.HeadlessGuiError("native XML export requires Windows")
    root = validate_diptrace_directory(root).root
    if hg.process_is_elevated():
        raise hg.HeadlessGuiError("run the export with the normal user token")
    desktop_name = "DipTraceExport-" + uuid.uuid4().hex[:12]
    before = hg.input_desktop_name()
    request_path, result_path = source.parent / "request.json", source.parent / "result.json"
    hg._write_json(
        request_path,
        {
            "root": str(root),
            "source": str(source),
            "output": str(output),
            "timeout": timeout,
            "desktop": desktop_name,
            "station": hg.process_window_station_name(),
            "session": hg.process_session_id(),
            "startup_dialog_sha256": startup_dialog_sha256,
        },
    )
    with hg.HiddenDesktop(desktop_name) as desktop:
        argv = [
            sys.executable,
            "-m",
            "diptrace_mcp.native_xml_export",
            "_worker",
            str(request_path),
            str(result_path),
        ]
        with desktop.launch(argv) as worker:
            exit_code = worker.wait(timeout)
            if exit_code is None:
                worker.terminate(124)
                worker.wait(2)
                raise hg.HeadlessGuiError("native XML export timed out")
    after = hg.input_desktop_name()
    result = hg._load_json(result_path)
    result.update(
        input_desktop_before=before, input_desktop_after=after, desktop_changed=before != after
    )
    if before is None or after != before:
        raise hg.HeadlessGuiError("input desktop changed or could not be verified")
    if exit_code != 0:
        result["ok"] = False
    return result


def _save_as(window: Any, executable: Path) -> None:
    menu = window.menu()
    if menu is None:
        raise hg.HeadlessGuiError("project window is not menu-ready")
    file_items = [item for item in menu.items() if item.text().replace("&", "").strip() == "File"]
    if len(file_items) != 1:
        raise hg.HeadlessGuiError("no unique File menu")
    file_item = file_items[0]
    submenu = file_item.sub_menu()
    hg._send_window_message(int(window.handle), 0x0117, int(submenu.handle), int(file_item.index()))
    items = submenu.items()
    matches = [
        item
        for item in items
        if item.text().split("\t")[0].replace("&", "").strip() == "Save As..."
    ]
    if len(matches) == 1:
        hg._post_menu_item(window, matches[0])
        return
    # Owner-drawn captions can be blank. Never guess an unverified menu index.
    ids = tuple(int(item.item_id()) for item in items)
    schematic_ids = (
        2,
        3,
        4,
        10,
        11,
        12,
        13,
        14,
        27,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
    )
    pcb_ids = (
        2,
        3,
        4,
        10,
        11,
        12,
        13,
        14,
        15,
        45,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        84,
        94,
        95,
        96,
        97,
        98,
    )
    profiles = {
        "d85632b2c8fb445471339e875416782e3e62fb56ea13ab7d973052122352f568": schematic_ids,
        "d8cf49f62e9bdc02c4a8009de28af9fc9a9bc4986a3054331ee23de740aef801": pcb_ids,
    }
    executable_sha256 = hg._sha256(executable)
    if (
        executable_sha256 is not None
        and ids == profiles.get(executable_sha256)
        and all(not item.text().strip() for item in items)
        and items[4].sub_menu() is None
    ):
        hg._post_menu_item(window, items[4])
        return
    raise hg.HeadlessGuiError(
        "unverified Save As menu: "
        + repr(
            [(i, item.item_id(), item.text(), item.is_enabled()) for i, item in enumerate(items)]
        )
    )


def _worker(request: dict[str, Any]) -> dict[str, Any]:
    source, output = Path(request["source"]), Path(request["output"])
    editor = _KINDS[source.suffix.lower()][0]
    executable = Path(request["root"]) / hg._EDITOR_EXECUTABLES[editor]
    app: Any = None
    result: dict[str, Any] = {"ok": False, "forced_termination": False, "editor": editor}
    try:
        windll: Any = getattr(ctypes, "windll", None)
        if windll is None:
            raise hg.HeadlessGuiError("Windows bindings are unavailable")
        if (
            hg.thread_desktop_name() != request["desktop"]
            or hg.process_window_station_name() != request["station"]
            or hg.process_session_id() != request["session"]
            or hg.process_is_elevated()
        ):
            raise hg.HeadlessGuiError("worker desktop/session/token mismatch")
        app = hg._pywinauto_application()(backend="win32")
        app.start(subprocess.list2cmdline([str(executable), str(source)]), timeout=15)
        result["diptrace_pid"] = int(app.process)
        result["desktop_name"] = hg.thread_desktop_name()
        window = hg._main_window(app, source, min(20, request["timeout"] / 2))
        if window.menu() is None:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                from .cinematic_recording import _record_printwindow_video

                image = source.parent.parent / ("native-dialog-" + uuid.uuid4().hex + ".png")

                def snapshot(capture: Any, width: int, height: int) -> None:
                    user32 = windll.user32
                    bounds, client = wintypes.RECT(), wintypes.RECT()
                    origin = wintypes.POINT()
                    if not (
                        user32.GetWindowRect(int(window.handle), ctypes.byref(bounds))
                        and user32.GetClientRect(int(window.handle), ctypes.byref(client))
                        and user32.ClientToScreen(int(window.handle), ctypes.byref(origin))
                    ):
                        raise hg.HeadlessGuiError("cannot capture dialog client rectangle")
                    x, y = origin.x - bounds.left, origin.y - bounds.top
                    if not (
                        0 <= x < x + client.right <= width and 0 <= y < y + client.bottom <= height
                    ):
                        raise hg.HeadlessGuiError("dialog client rectangle outside captured frame")
                    subprocess.run(
                        [
                            ffmpeg,
                            "-v",
                            "error",
                            "-n",
                            "-f",
                            "rawvideo",
                            "-pixel_format",
                            "bgra",
                            "-video_size",
                            f"{width}x{height}",
                            "-i",
                            "pipe:0",
                            "-vf",
                            f"crop={client.right}:{client.bottom}:{x}:{y}",
                            "-frames:v",
                            "1",
                            str(image),
                        ],
                        input=capture(),
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )

                _record_printwindow_video(
                    user32=windll.user32,
                    hwnd=int(window.handle),
                    ffmpeg=ffmpeg,
                    output=source.parent / "dialog.mp4",
                    fps=2,
                    duration_seconds=0.5,
                    playback=lambda: None,
                    prepare=snapshot,
                )
                fingerprint = hg._sha256(image)
                if fingerprint != request.get("startup_dialog_sha256"):
                    raise hg.HeadlessGuiError(
                        f"unreviewed startup dialog: {image}; client SHA256={fingerprint}"
                    )
                if window.class_name() != "TFMyMessage":
                    raise hg.HeadlessGuiError(
                        "approved image belongs to an unexpected dialog class"
                    )
                buttons = [
                    child
                    for child in window.descendants()
                    if child.class_name() == "TButton"
                    and child.window_text() == "OK"
                    and child.is_visible()
                    and child.is_enabled()
                ]
                if len(buttons) != 1:
                    raise hg.HeadlessGuiError("approved dialog has no unique enabled OK button")
                hg._post_window_message(int(buttons[0].handle), 0x00F5)
                result["acknowledged_dialog_sha256"] = fingerprint
                window = hg._main_window(app, source, 20)
        _save_as(window, executable)
        dialog = hg._visible_dialog(app, 10)
        if dialog.class_name() != "#32770":
            raise hg.HeadlessGuiError("unexpected native Save As dialog")
        hg._save_dialog_as_xml(int(dialog.handle), output)
        hg._wait_for_export(app, output, 20)
        hg._post_window_message(int(window.handle), hg._WM_CLOSE)
        app.wait_for_process_exit(timeout=10)
        result["ok"] = True
    except Exception as exc:
        windows = []
        if app is not None:
            with suppress(Exception):
                for window in app.windows(visible_only=False):
                    with suppress(Exception):
                        if window.is_visible():
                            windows.append(
                                {
                                    "title": window.window_text(),
                                    "class": window.class_name(),
                                    "enabled": window.is_enabled(),
                                    "menu": window.menu() is not None,
                                    "controls": [c.window_text() for c in window.descendants()][
                                        :30
                                    ],
                                }
                            )
        result["error"] = f"{type(exc).__name__}: {exc}; visible windows: {windows!r}"
        if app is not None:
            with suppress(Exception):
                app.kill(soft=False)
                result["forced_termination"] = True
    return result


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        result = _worker(hg._load_json(Path(sys.argv[2])))
        hg._write_json(Path(sys.argv[3]), result)
        return 0 if result["ok"] else 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diptrace-root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-xml", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument(
        "--startup-dialog-sha256", help="SHA256 of an explicitly reviewed dialog client PNG"
    )
    args = parser.parse_args()
    try:
        result = export_native_xml(
            args.diptrace_root,
            args.project,
            args.output_xml,
            args.timeout,
            args.startup_dialog_sha256,
        )
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
