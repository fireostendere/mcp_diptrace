"""Gate 11: native DipTrace refill/DRC on a hidden Windows desktop.

Flow: open the board in the real Pcb.exe, dismiss startup nags, invoke the
Verification menu DRC command, press "Run DRC", read the error list, close,
save the file in place (native pour refill state), and report both file SHAs.

Usage (Windows):
    python scripts\\diptrace_native_gate11.py ^
        --diptrace-root "C:\\Program Files\\DipTrace" ^
        --project "...\\attiny85-arduino-clone-pcb.dipxml" ^
        --output gate11_result.json
"""

from __future__ import annotations

import argparse
import hashlib
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

_probe_spec = _ilu.spec_from_file_location(
    "diptrace_menu_probe", Path(__file__).with_name("diptrace_menu_probe.py")
)
_probe = _ilu.module_from_spec(_probe_spec)
_probe_spec.loader.exec_module(_probe)
suppress_exception = _probe.suppress_exception
_dismiss_nags = _probe._dismiss_nags

_BM_CLICK = 0x00F5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace_window(app: Any, project: Path, seconds: float) -> Any:
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
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        with suppress_exception():
            for candidate in app.windows(visible_only=True):
                if str(candidate.window_text()).strip() == title:
                    return app.window(handle=int(candidate.handle))
        time.sleep(0.25)
    raise HeadlessGuiError(f"window {title!r} not found within {seconds:.0f}s")


def _click_button(dialog: Any, text: str) -> None:
    button = dialog.child_window(title=text, class_name="TButton")
    button.wait("visible enabled", timeout=10)
    button.send_message(_BM_CLICK)


def _run_worker(request: dict[str, Any], result_path: Path) -> int:
    error: str | None = None
    report: dict[str, Any] = {}
    app: Any = None
    try:
        project = Path(request["project"])
        executable = Path(request["diptrace_root"]) / "Pcb.exe"
        sha_before = _sha256(project)
        report["sha_before"] = sha_before

        application_class = _pywinauto_application()
        app = application_class(backend="win32").start(
            f'"{executable}" "{project}"', timeout=60.0
        )
        _dismiss_nags(app, 40.0)
        window = _workspace_window(app, project, 40.0)
        time.sleep(2.0)

        # Invoke Verification -> DRC (menu index 7 -> 0; see verification_map).
        from diptrace_mcp.headless_gui import _post_menu_item, _save_window

        # The DRC menu post occasionally does not land on a loaded host:
        # the menus are owner-drawn, so text-path resolution ("#7->0")
        # matches synthetic hash-ordered names and is not stable across
        # launches. Resolve strictly by index instead (Verification -> [0],
        # per scripts/verification_map.json) and retry the post.
        #
        # DipTrace opens the "DRC - Errors found" window only when the check
        # finds something; a clean board posts through silently (verified by
        # an error-injected control copy). No window after the retries on an
        # enabled item means zero findings.
        drc = None
        clean_run = False
        for attempt in range(3):
            verification = window.menu().items()[7].sub_menu()
            _post_menu_item(window, verification.items()[0])
            try:
                drc = _find_window(app, "DRC - Errors found", 45.0)
                break
            except HeadlessGuiError:
                if attempt == 2:
                    clean_run = True
                    break
                time.sleep(3.0)
        time.sleep(1.0)

        if clean_run:
            report["drc_item_count"] = 0
            report["drc_errors"] = []
            report["window_title"] = "DRC clean (no errors window)"
            report["drc_located"] = []
        else:
            list_box = drc.child_window(class_name="TListBox")
            _click_button(drc, "Run DRC")
            # Wait for the run to settle: poll the error list until stable.
            stable = 0
            last_count = -1
            deadline = time.monotonic() + 90.0
            while time.monotonic() < deadline and stable < 3:
                with suppress_exception():
                    count = int(list_box.item_count())
                stable = stable + 1 if count == last_count else 0
                last_count = count
                time.sleep(1.0)
            time.sleep(1.0)
            with suppress_exception():
                items = [str(t) for t in list_box.texts()]
            report["drc_item_count"] = last_count
            report["drc_errors"] = items
            report["window_title"] = str(drc.window_text()).strip()

        # Locate each error: select list row, press Locate, screenshot the
        # layout window so the highlighted offender can be inspected.
        located: list[dict[str, Any]] = []
        shots_dir = Path(request.get("shots_dir") or "")
        if not clean_run:
            try:
                count = int(list_box.item_count())
                for i in range(count):
                    with suppress_exception():
                        list_box.select(i)
                    time.sleep(0.15)
                    _click_button(drc, "Locate")
                    time.sleep(0.6)
                    entry: dict[str, Any] = {"index": i}
                    if i < len(items):
                        entry["error"] = items[i]
                    if shots_dir:
                        for cand in app.windows(visible_only=True):
                            with suppress_exception():
                                title = str(cand.window_text())
                            if "PCB Layout" in title and "attiny85" in title:
                                with suppress_exception():
                                    img = app.window(handle=int(cand.handle)).capture_as_image()
                                    shot = shots_dir / f"drc_{i}.png"
                                    img.save(shot)
                                    entry["shot"] = str(shot)
                                break
                    located.append(entry)
            except Exception as exc:  # noqa: BLE001 - locate pass is best-effort
                located.append({"locate_pass_error": f"{type(exc).__name__}: {exc}"})
        report["drc_located"] = located

        if not clean_run:
            _click_button(drc, "Close")
            time.sleep(1.0)

        # Save via the library's proven Save-As machinery into a SEPARATE
        # native artifact: no overwrite prompt, original untouched until the
        # result is inspected on the WSL side.
        from diptrace_mcp.headless_gui import (
            _post_window_message,
            _save_dialog_as_xml,
            _visible_dialog,
        )

        native_target = project.with_name(f".{project.stem}-native-gate11{project.suffix}")
        native_target.unlink(missing_ok=True)
        dialog = None
        for attempt in range(3):
            _save_window(window, "File->Save")
            try:
                dialog = _visible_dialog(app, 25.0)
                break
            except HeadlessGuiError:
                if attempt == 2:
                    raise
                time.sleep(2.0)
        _save_dialog_as_xml(int(dialog.handle), native_target)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if native_target.is_file() and native_target.stat().st_size > 0:
                time.sleep(1.0)
                break
            time.sleep(0.5)
        if not native_target.is_file():
            raise HeadlessGuiError("native save did not produce a file")
        time.sleep(1.0)
        report["native_artifact"] = str(native_target)
        report["sha_after"] = _sha256(native_target)
        report["changed"] = report["sha_after"] != sha_before

        _post_window_message(int(window.handle), 0x0010)  # WM_CLOSE
        try:
            app.wait_for_process_exit(timeout=15.0)
        except Exception:
            app.kill(soft=False)
    except Exception as exc:  # noqa: BLE001
        titles: list[str] = []
        if app is not None:
            with suppress_exception():
                titles = [str(w.window_text()) for w in app.windows(visible_only=True)]
        error = f"{type(exc).__name__}: {exc}; visible={titles[:12]!r}"
    finally:
        if app is not None:
            with suppress_exception():
                app.kill(soft=False)
    result_path.write_text(
        json.dumps({"ok": error is None, "error": error, **report},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0 if error is None else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diptrace-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    if os.name != "nt":
        print("Windows required", file=sys.stderr)
        return 2
    request = {
        "diptrace_root": args.diptrace_root,
        "project": args.project,
        "shots_dir": str(Path(args.output).parent),
    }
    desktop_name = f"DipTraceGate11-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="diptrace-gate11-") as raw_temp:
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
                exit_code = worker.wait(args.timeout + 120.0)
                if exit_code is None:
                    worker.terminate(124)
                    raise HeadlessGuiError("gate 11 driver timed out")
        if not result_path.is_file():
            raise HeadlessGuiError(f"worker exited {exit_code} without a result")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps({k: payload.get(k) for k in
                      ("ok", "error", "drc_item_count", "window_title", "changed")},
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
