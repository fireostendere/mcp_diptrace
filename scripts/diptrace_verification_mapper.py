"""Map the DipTrace Verification menu commands by invoking them one by one.

Every Verification command is a read-only check, so invoking each item and
recording which dialog appears is safe. The resulting JSON maps menu index ->
dialog title -> control tree, which the gate-11 driver uses to run the native
DRC and read its results.

Usage (Windows):
    python scripts\\diptrace_verification_mapper.py ^
        --diptrace-root "C:\\Program Files\\DipTrace" ^
        --project "...\\attiny85-arduino-clone-pcb.dipxml" ^
        --output verification_map.json
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

from diptrace_mcp.headless_gui import (  # noqa: E402
    HeadlessGuiError,
    HiddenDesktop,
    _pywinauto_application,
)

import importlib.util as _ilu  # noqa: E402

_probe_spec = _ilu.spec_from_file_location(
    "diptrace_menu_probe", Path(__file__).with_name("diptrace_menu_probe.py")
)
_probe = _ilu.module_from_spec(_probe_spec)
_probe_spec.loader.exec_module(_probe)
suppress_exception = _probe.suppress_exception
_dismiss_nags = _probe._dismiss_nags


def _visible_titles(app: Any) -> list[str]:
    titles: list[str] = []
    with suppress_exception():
        for window in app.windows(visible_only=True):
            with suppress_exception():
                title = str(window.window_text()).strip()
            if title:
                titles.append(title)
    return titles


def _control_tree(element: Any, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if depth > 4:
        return out
    with suppress_exception():
        for child in element.children():
            entry: dict[str, Any] = {}
            with suppress_exception():
                entry["class"] = child.class_name()
            with suppress_exception():
                entry["text"] = child.window_text()
            with suppress_exception():
                entry["type"] = str(child.element_info.control_type)
            kids = _control_tree(child, depth + 1)
            if kids:
                entry["children"] = kids
            out.append(entry)
    return out


def _run_worker(request: dict[str, Any], result_path: Path) -> int:
    error: str | None = None
    mapping: dict[str, Any] = {}
    app: Any = None
    try:
        root = Path(request["diptrace_root"])
        project = Path(request["project"])
        executable = root / "Pcb.exe"
        application_class = _pywinauto_application()
        app = application_class(backend="win32").start(
            f'"{executable}" "{project}"', timeout=60.0
        )
        _dismiss_nags(app, 40.0)
        deadline = time.monotonic() + 40.0
        window = None
        while window is None and time.monotonic() < deadline:
            with suppress_exception():
                for candidate in app.windows(visible_only=True):
                    title = str(candidate.window_text()).casefold()
                    if project.stem.casefold() in title and candidate.menu() is not None:
                        window = candidate
                        break
            if window is None:
                time.sleep(0.3)
        if window is None:
            raise HeadlessGuiError("main window not found")
        time.sleep(2.0)  # let the workspace finish settling
        baseline = set(_visible_titles(app))
        for index in (0, 1, 2, 4, 5):
            before = set(_visible_titles(app))
            try:
                item = window.menu_item(f"#7->{index}")
                from diptrace_mcp.headless_gui import _post_menu_item

                _post_menu_item(window, item)
            except Exception as exc:
                mapping[str(index)] = {"invoke_error": str(exc)}
                continue
            time.sleep(4.0)
            after = _visible_titles(app)
            new_titles = [t for t in after if t not in before and t not in baseline]
            entry: dict[str, Any] = {"new_windows": new_titles}
            for title in new_titles:
                with suppress_exception():
                    dlg = app.window(title=title)
                    entry[title] = _control_tree(dlg)
            mapping[str(index)] = entry
            # close whatever opened (Esc to the dialog, safe for read-only checks)
            for _ in range(3):
                with suppress_exception():
                    import ctypes

                    ctypes.windll.user32.keybd_event(0x1B, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x1B, 0, 2, 0)
                time.sleep(0.5)
            time.sleep(1.0)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}; visible={_visible_titles(app)[:10]!r}"
    finally:
        if app is not None:
            with suppress_exception():
                app.kill(soft=False)
    result_path.write_text(
        json.dumps({"ok": error is None, "error": error, "verification": mapping},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0 if error is None else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diptrace-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        print("Windows required", file=sys.stderr)
        return 2
    request = {"diptrace_root": args.diptrace_root, "project": args.project}
    desktop_name = f"DipTraceVerifMap-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="diptrace-verif-map-") as raw_temp:
        temp = Path(raw_temp)
        result_path = temp / "result.json"
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
                exit_code = worker.wait(300.0)
                if exit_code is None:
                    worker.terminate(124)
                    raise HeadlessGuiError("verification mapper timed out")
        if not result_path.is_file():
            raise HeadlessGuiError(f"worker exited {exit_code} without a result")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({"ok": payload.get("ok"), "error": payload.get("error")},
                     ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "_worker":
        rest = sys.argv[2:]
        worker_parser = argparse.ArgumentParser()
        worker_parser.add_argument("--request", required=True)
        worker_parser.add_argument("--result", required=True)
        worker_args = worker_parser.parse_args(rest)
        raise SystemExit(
            _run_worker(json.loads(worker_args.request), Path(worker_args.result))
        )
    raise SystemExit(main())
