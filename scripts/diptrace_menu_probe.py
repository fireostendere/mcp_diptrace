"""Probe the native DipTrace PCB editor menu tree on a hidden Windows desktop.

Parent process creates a hidden Win32 desktop, launches itself as a worker on
it, the worker opens the project in Pcb.exe, dumps the full menu tree to JSON
and closes the editor without saving. Read-only: no menu item is invoked.

Usage (from Windows, repo root available):
    set PYTHONPATH=C:\\Users\\fireo\\mcp_diptrace\\src
    python scripts\\diptrace_menu_probe.py ^
        --diptrace-root "C:\\Program Files\\DipTrace" ^
        --project "C:\\Users\\fireo\\mcp_diptrace\\attiny85-arduino-clone" \\
        "\\attiny85-arduino-clone-pcb.dipxml" ^
        --output menus.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diptrace_mcp.headless_gui import (  # noqa: E402
    HeadlessGuiError,
    HiddenDesktop,
    _pywinauto_application,
)

_MF_POPUP = 0x10
_MF_SEPARATOR = 0x800


def _dump_menu(menu: Any, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if menu is None or depth > 4:
        return out
    try:
        items = menu.items()
    except Exception as exc:  # pragma: no cover - defensive
        return [{"error": f"items(): {exc}"}]
    for item in items:
        entry: dict[str, Any] = {}
        with suppress_exception():
            entry["text"] = item.text()
        item_type = 0
        with suppress_exception():
            item_type = int(item.item_type())
        sub: Any = None
        with suppress_exception():
            sub = item.sub_menu()
        if item_type & _MF_SEPARATOR:
            entry["type"] = "separator"
        elif sub is not None:
            entry["type"] = "popup"
        else:
            entry["type"] = "item"
        with suppress_exception():
            entry["path"] = str(item.index())
        if entry["type"] == "popup":
            children = _dump_menu(sub, depth + 1)
            if children:
                entry["children"] = children
        if entry["type"] != "separator":
            out.append(entry)
    return out


class suppress_exception:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> bool:
        return True


_NAG_TITLES = (
    "DipTrace Evaluation",
    "DipTrace News",
    "Getting Started",
    "Upgrade DipTrace",
    "Tip of the Day",
    "Order PCB",
    "dipregist",
)


def _dismiss_nags(app: Any, seconds: float) -> list[str]:
    """Close visible startup nag windows until only the workspace remains."""
    import time

    dismissed: list[str] = []
    deadline = time.monotonic() + seconds
    quiet_rounds = 0
    while time.monotonic() < deadline and quiet_rounds < 4:
        found = False
        for window in app.windows(visible_only=True):
            try:
                title = str(window.window_text()).strip()
                if not title or not window.is_visible():
                    continue
            except Exception:
                continue
            for nag in _NAG_TITLES:
                if nag.casefold() in title.casefold():
                    try:
                        window.close()
                        dismissed.append(title)
                        found = True
                    except Exception:
                        pass
                    break
        if found:
            quiet_rounds = 0
            time.sleep(0.4)
        else:
            quiet_rounds += 1
            time.sleep(0.25)
    return dismissed


def _workspace_window(app: Any, project: Path, seconds: float) -> Any:
    """Wait for the visible main window with a live menu bar."""
    import time

    identifiers = (project.name.casefold(), project.stem.casefold())
    deadline = time.monotonic() + seconds
    last_error = "not polled"
    while time.monotonic() < deadline:
        for window in app.windows(visible_only=True):
            try:
                title = str(window.window_text()).casefold()
                if not any(i and i in title for i in identifiers):
                    continue
                menu = window.menu()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if menu is not None:
                return window
        time.sleep(0.3)
    raise HeadlessGuiError(
        f"main window with menu not found within {seconds:.0f}s ({last_error})"
    )


def _run_worker(request: dict[str, Any], result_path: Path) -> int:
    error: str | None = None
    menus: list[dict[str, Any]] = []
    window_title: str | None = None
    dismissed: list[str] = []
    app: Any = None
    try:
        root = Path(request["diptrace_root"])
        project = Path(request["project"])
        executable = root / "Pcb.exe"
        if not executable.is_file():
            raise HeadlessGuiError(f"missing editor: {executable}")
        application_class = _pywinauto_application()
        command = f'"{executable}" "{project}"'
        app = application_class(backend="win32").start(
            command, timeout=float(request.get("timeout_seconds", 60.0))
        )
        dismissed = _dismiss_nags(app, 40.0)
        window = _workspace_window(app, project, 40.0)
        with suppress_exception():
            window_title = window.window_text()
        menus = _dump_menu(window.menu())
    except Exception as exc:  # noqa: BLE001 - report everything to the parent
        titles: list[str] = []
        if app is not None:
            with suppress_exception():
                titles = [
                    str(w.window_text())
                    for w in app.windows(visible_only=True)
                ]
        error = f"{type(exc).__name__}: {exc}; dismissed={len(dismissed)}; visible={titles[:12]!r}"
    finally:
        if app is not None:
            with suppress_exception():
                app.kill(soft=False)
    result_path.write_text(
        json.dumps(
            {"ok": error is None, "error": error, "title": window_title, "menus": menus},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0 if error is None else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diptrace-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if os.name != "nt":
        print("Windows required", file=sys.stderr)
        return 2
    request = {
        "diptrace_root": args.diptrace_root,
        "project": args.project,
        "timeout_seconds": args.timeout,
    }
    desktop_name = f"DipTraceMenuProbe-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="diptrace-menu-probe-") as raw_temp:
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
                exit_code = worker.wait(args.timeout + 60.0)
                if exit_code is None:
                    worker.terminate(124)
                    raise HeadlessGuiError("menu probe timed out")
        if not result_path.is_file():
            raise HeadlessGuiError(f"worker exited {exit_code} without a result")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({"ok": payload.get("ok"), "error": payload.get("error"),
                      "title": payload.get("title"),
                      "top_menus": [m.get("text") for m in payload.get("menus", [])]},
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
            _run_worker(
                json.loads(worker_args.request), Path(worker_args.result)
            )
        )
    raise SystemExit(main())
