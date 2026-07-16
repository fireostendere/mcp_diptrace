from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from .config import Settings, platform_path
from .errors import DipTraceMcpError
from .sessions import SessionAction, SessionStore
from .xml_document import sha256_bytes


class BridgeController:
    def __init__(self, exchange_path: Path, settings: Settings):
        self.store = SessionStore(settings.state_dir, settings.max_document_bytes)
        self.metadata = self.store.create(exchange_path)
        self.session_id = str(self.metadata["session_id"])
        self.finished = False

    @property
    def working_path(self) -> Path:
        return self.store.working_path(self.session_id)

    def current_sha256(self) -> str:
        return sha256_bytes(self.working_path.read_bytes())

    def is_modified(self) -> bool:
        return self.current_sha256() != str(self.metadata["original_sha256"])

    def finish(self, action: SessionAction, expected_sha256: str | None = None) -> dict[str, Any]:
        if self.finished:
            return self.store.read_metadata(self.session_id)
        result = self.store.finalize(self.session_id, action, expected_sha256)
        self.finished = True
        return result

    def poll_request(self) -> dict[str, Any] | None:
        return self.store.read_finish_request(self.session_id)

    def reject_request(self, message: str) -> None:
        self.store.clear_finish_request(self.session_id)
        self.store.update_metadata(
            self.session_id,
            last_error=message,
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )


def _show_fatal(message: str) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes_api: Any = ctypes
            ctypes_api.windll.user32.MessageBoxW(0, message, "DipTrace MCP Bridge", 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def run_gui(controller: BridgeController, timeout: int) -> int:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("DipTrace MCP Bridge")
    root.resizable(False, False)
    status = tk.StringVar(value="MCP session is active. DipTrace is waiting for the result.")
    details = tk.StringVar(value=f"Session: {controller.session_id}")
    started = time.monotonic()

    frame = tk.Frame(root, padx=18, pady=16)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="DipTrace MCP Bridge", font=("Segoe UI", 13, "bold")).pack(
        anchor="w"
    )
    tk.Label(frame, textvariable=status, justify="left", wraplength=480).pack(
        anchor="w", pady=(10, 4)
    )
    tk.Label(frame, textvariable=details, justify="left", fg="#555555").pack(anchor="w")

    buttons = tk.Frame(frame)
    buttons.pack(fill="x", pady=(16, 0))

    def finish(action: SessionAction, expected_sha256: str | None = None) -> bool:
        if controller.finished:
            return True
        try:
            controller.finish(action, expected_sha256)
        except Exception as exc:
            controller.reject_request(str(exc))
            status.set(f"Cannot finish session: {exc}")
            return False
        status.set("Changes were sent to DipTrace." if action == "apply" else "Session cancelled.")
        root.after(500, root.destroy)
        return True

    tk.Button(
        buttons,
        text="Apply MCP changes",
        width=22,
        command=lambda: finish("apply"),
    ).pack(side="left")
    tk.Button(
        buttons,
        text="Cancel",
        width=14,
        command=lambda: finish("cancel"),
    ).pack(side="right")

    def on_close() -> None:
        if controller.finished or messagebox.askyesno(
            "DipTrace MCP Bridge", "Discard this MCP session?"
        ):
            finish("cancel")

    root.protocol("WM_DELETE_WINDOW", on_close)

    def poll() -> None:
        if controller.finished:
            return
        if time.monotonic() - started >= timeout:
            finish("cancel")
            return
        try:
            modified = controller.is_modified()
            details.set(
                f"Session: {controller.session_id}\n"
                f"Working XML: {'modified' if modified else 'unchanged'}"
            )
            request = controller.poll_request()
            if request:
                action = request.get("action")
                if action not in {"apply", "cancel"}:
                    controller.reject_request(f"Unknown finish action: {action}")
                else:
                    if finish(action, request.get("expected_sha256")):
                        return
        except Exception as exc:
            status.set(f"Bridge error: {exc}")
        root.after(350, poll)

    root.after(350, poll)
    root.mainloop()
    if not controller.finished:
        controller.finish("cancel")
    return 0


def run_headless(controller: BridgeController, timeout: int) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = controller.poll_request()
        if request:
            action = request.get("action")
            if action not in {"apply", "cancel"}:
                controller.reject_request(f"Unknown finish action: {action}")
            else:
                controller.finish(action, request.get("expected_sha256"))
                return 0
        time.sleep(0.25)
    controller.finish("cancel")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DipTrace executable plug-in bridge for MCP")
    parser.add_argument("exchange_file")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("DIPTRACE_MCP_SESSION_TIMEOUT", "7200")),
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        exchange_path = platform_path(args.exchange_file).resolve(strict=True)
        controller = BridgeController(exchange_path, Settings.from_env())
        if args.headless:
            return run_headless(controller, args.timeout)
        return run_gui(controller, args.timeout)
    except (OSError, DipTraceMcpError, RuntimeError) as exc:
        _show_fatal(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
