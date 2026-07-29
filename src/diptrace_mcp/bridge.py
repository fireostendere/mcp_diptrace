from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .config import DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS, Settings
from .errors import ConfigurationError, DipTraceMcpError
from .sessions import SessionAction, SessionStore
from .xml_document import atomic_write_bytes, utc_now

BRIDGE_ERROR_LOG_NAME = "diptrace_mcp_bridge.log"
BRIDGE_ERROR_LOG_MAX_BYTES = 64 * 1024


class BridgeController:
    def __init__(self, exchange_path: Path, settings: Settings):
        self.store = SessionStore(
            settings.state_dir,
            settings.max_document_bytes,
            allowed_roots=settings.allowed_roots,
            retention=settings.retention_policy,
            active_ttl_seconds=settings.live_session_ttl_seconds,
        )
        self.metadata = self.store.create(exchange_path)
        self.session_id = str(self.metadata["session_id"])
        self.finished = False
        self._preview_sha256: str | None = None
        self._preview_payload: dict[str, Any] | None = None

    @property
    def working_path(self) -> Path:
        return self.store.working_path(self.session_id)

    def current_sha256(self) -> str:
        return self.store.working_sha256(self.session_id)

    def is_modified(self) -> bool:
        return self.current_sha256() != str(self.metadata["original_sha256"])

    @property
    def can_apply(self) -> bool:
        return self.metadata.get("apply_supported") is True

    def preview_summary(self) -> dict[str, Any]:
        """Return one bounded impact summary, cached by stable working SHA-256."""

        try:
            current_sha256 = self.current_sha256()
            if (
                current_sha256 == self._preview_sha256
                and self._preview_payload is not None
            ):
                return self._preview_payload
            payload = self.store.live_preview_summary(self.session_id)
        except Exception as exc:
            self._preview_sha256 = None
            self._preview_payload = None
            message = str(exc)
            payload = {
                "available": False,
                "complete": False,
                "working_sha256": None,
                "modified": None,
                "normalized_object_count": None,
                "structural_element_count": None,
                "object_count": None,
                "changed_ids": [],
                "changed_id_count": None,
                "changed_ids_complete": False,
                "limitations": ["preview impact is unavailable"],
                "reason": message[:240],
            }
            return payload
        payload_sha256 = payload.get("working_sha256")
        if (
            not isinstance(payload_sha256, str)
            or len(payload_sha256) != 64
            or any(character not in "0123456789abcdef" for character in payload_sha256)
        ):
            self._preview_sha256 = None
            self._preview_payload = None
            return {
                "available": False,
                "complete": False,
                "working_sha256": None,
                "modified": None,
                "normalized_object_count": None,
                "structural_element_count": None,
                "object_count": None,
                "changed_ids": [],
                "changed_id_count": None,
                "changed_ids_complete": False,
                "limitations": ["preview impact has no valid working-file binding"],
                "reason": "invalid working_sha256 in preview summary",
            }
        # The file may have moved from current_sha256=A to payload_sha256=B
        # between the two stable reads. Cache the summary under B, never under A.
        self._preview_sha256 = payload_sha256
        self._preview_payload = payload
        return payload

    def finish(self, action: SessionAction, expected_sha256: str | None = None) -> dict[str, Any]:
        if self.finished:
            return self.store.read_metadata(self.session_id)
        result = self.store.finalize(self.session_id, action, expected_sha256)
        self.finished = True
        return result

    def inspected_sha256(self) -> str | None:
        """Return the exact working SHA bound to the preview shown to the operator."""

        if self._preview_payload is None:
            return None
        value = self._preview_payload.get("working_sha256")
        return value if isinstance(value, str) else None

    def poll_request(self) -> dict[str, Any] | None:
        return self.store.read_finish_request(self.session_id)

    def reject_request(
        self,
        message: str,
        *,
        request_id: str | None = None,
        control_sha256: str | None = None,
    ) -> None:
        if request_id is not None:
            self.store.reject_finish_request(
                self.session_id,
                message,
                expected_request_id=request_id,
            )
            return
        if control_sha256 is None:
            raise ValueError("control_sha256 is required for malformed request rejection")
        self.store.reject_malformed_finish_request(
            self.session_id,
            message,
            expected_control_sha256=control_sha256,
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


def _fatal_error_payload(exc: OSError | DipTraceMcpError | RuntimeError) -> dict[str, Any]:
    if isinstance(exc, DipTraceMcpError):
        return exc.payload.as_dict()
    return {
        "code": "bridge_io_error" if isinstance(exc, OSError) else "bridge_runtime_error",
        "message": str(exc),
        "details": {},
        "recoverable": False,
        "suggested_action": "",
        "object_ids": [],
        "txid": None,
        "jobid": None,
    }


def _write_fatal_log(
    exchange_path: Path,
    exc: OSError | DipTraceMcpError | RuntimeError,
) -> Path | None:
    """Write one bounded failure record beside an already validated exchange file."""

    try:
        parent = exchange_path.resolve(strict=False).parent
        log_path = parent / BRIDGE_ERROR_LOG_NAME
        record = {
            "timestamp": utc_now(),
            "error": _fatal_error_payload(exc),
        }
        data = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if len(data) > BRIDGE_ERROR_LOG_MAX_BYTES:
            error = record["error"]
            assert isinstance(error, dict)
            original_bytes = len(data)
            message = str(error.get("message", ""))
            bounded_error: dict[str, Any] = {
                "code": error.get("code", "bridge_runtime_error"),
                "message": message,
                "details": {
                    "bridge_log_truncated": True,
                    "original_serialized_bytes": original_bytes,
                },
                "recoverable": error.get("recoverable", False),
                "suggested_action": "",
                "object_ids": [],
                "txid": None,
                "jobid": None,
            }
            record["error"] = bounded_error
            while True:
                data = (
                    json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
                    + b"\n"
                )
                if len(data) <= BRIDGE_ERROR_LOG_MAX_BYTES:
                    break
                message = message[: len(message) // 2]
                bounded_error["message"] = message
        atomic_write_bytes(log_path, data)
        return log_path
    except (OSError, RuntimeError, ValueError):
        # The original error remains authoritative when its diagnostic cannot be
        # persisted (for example, because the exchange directory is read-only).
        return None


def _preview_details_text(session_id: str, summary: dict[str, Any]) -> str:
    if not summary.get("available"):
        reason = str(summary.get("reason") or "working XML could not be parsed")
        return (
            f"Session: {session_id}\n"
            "Preview: unavailable/incomplete\n"
            f"Reason: {reason}"
        )
    changed_ids = [str(value) for value in summary.get("changed_ids", [])]
    changed = ", ".join(changed_ids) if changed_ids else "(no normalized stable ids)"
    completeness = "complete" if summary.get("complete") else "incomplete/truncated"
    return (
        f"Session: {session_id}\n"
        f"Working XML: {'modified' if summary.get('modified') else 'unchanged'}\n"
        f"Impact: {summary.get('normalized_object_count')} normalized, "
        f"{summary.get('structural_element_count')} structural "
        f"({summary.get('object_count')} conservative total)\n"
        f"First changed stable IDs: {changed}\n"
        f"Preview: {completeness}"
    )


def _valid_finish_request(request: dict[str, Any]) -> bool:
    request_id = request.get("request_id")
    action = request.get("action")
    expected_sha256 = request.get("expected_sha256")
    requested_at = request.get("requested_at")
    return (
        isinstance(request_id, str)
        and action in {"apply", "cancel"}
        and isinstance(expected_sha256, str)
        and len(expected_sha256) == 64
        and all(character in "0123456789abcdef" for character in expected_sha256)
        and isinstance(requested_at, str)
        and bool(requested_at)
    )


def run_gui(controller: BridgeController, timeout: int) -> int:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("DipTrace MCP Bridge")
    root.resizable(False, False)
    initial_status = (
        "MCP session is active. DipTrace is waiting for the result."
        if controller.can_apply
        else (
            "This library bridge profile is read-only (ImpMode=None). "
            "Inspect the document, then cancel the session."
        )
    )
    status = tk.StringVar(value=initial_status)
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

    def finish(
        action: SessionAction,
        expected_sha256: str | None = None,
        *,
        reject_pending: bool = False,
        request_id: str | None = None,
    ) -> bool:
        if controller.finished:
            return True
        try:
            controller.finish(action, expected_sha256)
        except Exception as exc:
            if reject_pending and request_id is not None:
                controller.reject_request(str(exc), request_id=request_id)
            status.set(f"Cannot finish session: {exc}")
            return False
        status.set(
            (
                "The local exchange XML was finalized. DipTrace host import "
                "acknowledgement is unavailable."
            )
            if action == "apply"
            else "The session was cancelled locally; the exchange XML was not replaced."
        )
        root.after(500, root.destroy)
        return True

    apply_button = tk.Button(
        buttons,
        text="Apply MCP changes",
        width=22,
        command=lambda: finish("apply", controller.inspected_sha256()),
        state="disabled",
    )
    apply_button.pack(side="left")
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
        try:
            summary = controller.preview_summary()
            details.set(
                _preview_details_text(
                    controller.session_id,
                    summary,
                )
            )
            apply_button.configure(
                state=(
                    "normal"
                    if controller.can_apply and summary.get("available") is True
                    else "disabled"
                )
            )
            request = controller.poll_request()
            if request:
                action = request.get("action")
                request_id = request.get("request_id")
                control_sha256 = request.get("_control_sha256")
                if not _valid_finish_request(request):
                    if not isinstance(control_sha256, str):
                        raise ValueError("Finish request has no valid control hash")
                    controller.reject_request(
                        (
                            f"Unknown finish action: {action}"
                            if action not in {"apply", "cancel"}
                            else "Malformed finish request"
                        ),
                        control_sha256=control_sha256,
                    )
                    root.after(350, poll)
                    return
                assert isinstance(request_id, str)
                assert action in {"apply", "cancel"}
                if finish(
                    action,
                    request.get("expected_sha256"),
                    reject_pending=True,
                    request_id=request_id,
                ):
                    return
        except Exception as exc:
            status.set(f"Bridge error: {exc}")
        if time.monotonic() - started >= timeout and finish("cancel"):
            return
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
        if request and _handle_headless_request(controller, request):
            return 0
        time.sleep(0.25)
    request = controller.poll_request()
    if request and _handle_headless_request(controller, request):
        return 0
    controller.finish("cancel")
    return 2


def _handle_headless_request(
    controller: BridgeController,
    request: dict[str, Any],
) -> bool:
    action = request.get("action")
    request_id = request.get("request_id")
    control_sha256 = request.get("_control_sha256")
    if not _valid_finish_request(request):
        if not isinstance(control_sha256, str):
            raise ValueError("Finish request has no valid control hash")
        controller.reject_request(
            (
                f"Unknown finish action: {action}"
                if action not in {"apply", "cancel"}
                else "Malformed finish request"
            ),
            control_sha256=control_sha256,
        )
        return False
    assert isinstance(request_id, str)
    assert action in {"apply", "cancel"}
    try:
        controller.finish(action, request.get("expected_sha256"))
    except DipTraceMcpError as exc:
        controller.reject_request(str(exc), request_id=request_id)
        return False
    return True


def _positive_timeout(value: str) -> int:
    try:
        timeout = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be an integer") from exc
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return timeout


def _timeout_from_environment() -> int:
    raw = os.environ.get("DIPTRACE_MCP_SESSION_TIMEOUT")
    if raw is None:
        return DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
    try:
        return _positive_timeout(raw)
    except argparse.ArgumentTypeError as exc:
        raise ConfigurationError(f"DIPTRACE_MCP_SESSION_TIMEOUT {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DipTrace executable plug-in bridge for MCP")
    parser.add_argument("exchange_file")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        default=None,
        help=(
            "operator workflow timeout in seconds "
            f"(default: {DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS}; "
            "env: DIPTRACE_MCP_SESSION_TIMEOUT)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    exchange_path: Path | None = None
    try:
        settings = Settings.from_env()
        exchange_path = settings.resolve_allowed_path(args.exchange_file, must_exist=True)
        timeout = args.timeout if args.timeout is not None else _timeout_from_environment()
        controller = BridgeController(exchange_path, settings)
        if args.headless:
            return run_headless(controller, timeout)
        return run_gui(controller, timeout)
    except (OSError, DipTraceMcpError, RuntimeError) as exc:
        if exchange_path is not None:
            _write_fatal_log(exchange_path, exc)
        _show_fatal(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
