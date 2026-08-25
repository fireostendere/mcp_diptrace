"""Screenshot the native DRC Locate view for a specific error row.

Opens the board in the hidden-desktop Pcb.exe, runs DRC, selects the given
error row, presses Locate and captures the main window image.

Usage (Windows):
    python scripts\\diptrace_drc_locate_shot.py --project ... --row 1 --output shot.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import importlib.util as _ilu  # noqa: E402

from diptrace_mcp.headless_gui import (  # noqa: E402
    HeadlessGuiError,
    HiddenDesktop,
    _pywinauto_application,
)

_spec = _ilu.spec_from_file_location(
    "diptrace_menu_probe", Path(__file__).with_name("diptrace_menu_probe.py")
)
_probe = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_probe)
suppress_exception = _probe.suppress_exception
_dismiss_nags = _probe._dismiss_nags

_BM_CLICK = 0x00F5


def _workspace_window(app: Any, project: Path, seconds: float) -> Any:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        with suppress_exception():
            for candidate in app.windows(visible_only=True):
                title = str(candidate.window_text()).casefold()
                if project.stem.casefold() in title and candidate.menu() is not None:
                    return app.window(handle=int(candidate.handle))
        time.sleep(0.3)
    raise HeadlessGuiError("main workspace window not found")


def _find_window(app: Any, title: str, seconds: float) -> Any:
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        with suppress_exception():
            for candidate in app.windows(visible_only=True):
                if str(candidate.window_text()).strip() == title:
                    return app.window(handle=int(candidate.handle))
        time.sleep(0.25)
    raise HeadlessGuiError(f"window {title!r} not found")


def _click_button(dialog: Any, text: str) -> None:
    button = dialog.child_window(title=text, class_name="TButton")
    button.wait("visible enabled", timeout=10)
    button.send_message(_BM_CLICK)


def _run_worker(request: dict[str, Any], result_path: Path) -> int:
    app: Any = None
    try:
        project = Path(request["project"])
        executable = Path(request["diptrace_root"]) / "Pcb.exe"
        application_class = _pywinauto_application()
        app = application_class(backend="win32").start(
            f'"{executable}" "{project}"', timeout=60.0
        )
        _dismiss_nags(app, 40.0)
        window = _workspace_window(app, project, 40.0)
        time.sleep(2.0)

        from diptrace_mcp.headless_gui import _post_menu_item

        item = window.menu_item("#7->0")
        _post_menu_item(window, item)
        drc = _find_window(app, "DRC - Errors found", 20.0)
        time.sleep(1.0)
        list_box = drc.child_window(class_name="TListBox")
        _click_button(drc, "Run DRC")
        time.sleep(6.0)

        row = int(request["row"])
        with suppress_exception():
            list_box.select(row)
        time.sleep(0.3)
        _click_button(drc, "Locate")
        time.sleep(1.5)
        image = window.capture_as_image()
        image.save(request["output"])
        result_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        titles: list[str] = []
        if app is not None:
            with suppress_exception():
                titles = [str(w.window_text()) for w in app.windows(visible_only=True)]
        result_path.write_text(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                        "visible": titles[:10]}, ensure_ascii=False),
            encoding="utf-8",
        )
    finally:
        if app is not None:
            with suppress_exception():
                app.kill(soft=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diptrace-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--row", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        print("Windows required", file=sys.stderr)
        return 2
    request = {
        "diptrace_root": args.diptrace_root,
        "project": args.project,
        "row": args.row,
        "output": args.output,
    }
    desktop_name = f"DipTraceShot-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="diptrace-shot-") as raw_temp:
        result_path = Path(raw_temp) / "result.json"
        with HiddenDesktop(desktop_name) as desktop:
            argv = [
                sys.executable,
                str(Path(__file__).resolve()),
                "_worker",
                "--request",
                json.dumps(request),
                "--result",
                str(result_path),
            ]
            with desktop.launch(argv) as worker:
                worker.wait(240.0)
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "_worker":
        rest = sys.argv[2:]
        wp = argparse.ArgumentParser()
        wp.add_argument("--request", required=True)
        wp.add_argument("--result", required=True)
        wa = wp.parse_args(rest)
        raise SystemExit(_run_worker(json.loads(wa.request), Path(wa.result)))
    raise SystemExit(main())
