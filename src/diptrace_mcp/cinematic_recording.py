from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .diptrace_window import find_window_handle


def build_windows_capture_command(
    output: str | Path,
    *,
    window_title: str | None = "DipTrace",
    window_handle: int | None = None,
    desktop: bool = False,
    fps: int = 60,
    duration_seconds: float | None = None,
    draw_mouse: bool = True,
) -> list[str]:
    """Build a shell-free ffmpeg gdigrab command for one window or the desktop."""

    if fps < 1 or fps > 240:
        raise ValueError("fps must be between 1 and 240")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if window_handle is not None and window_handle <= 0:
        raise ValueError("window_handle must be a positive integer")
    if desktop and (window_handle is not None or window_title not in {None, "DipTrace"}):
        raise ValueError("desktop capture cannot also select a window")
    if not desktop and window_handle is None and (window_title is None or not window_title.strip()):
        raise ValueError("window_title or window_handle is required for window capture")

    if desktop:
        target = "desktop"
    elif window_handle is not None:
        target = f"hwnd=0x{window_handle:x}"
    else:
        target = f"title={window_title}"
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        str(fps),
        "-draw_mouse",
        "1" if draw_mouse else "0",
        "-i",
        target,
    ]
    if duration_seconds is not None:
        command.extend(["-t", f"{duration_seconds:g}"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return command


def record_windows(
    output: str | Path,
    *,
    window_title: str | None = "DipTrace",
    desktop: bool = False,
    fps: int = 60,
    duration_seconds: float | None = None,
    draw_mouse: bool = True,
) -> int:
    """Record synchronously with ffmpeg. Without duration, Ctrl+C stops capture."""

    if os.name != "nt":
        raise RuntimeError("cinematic window recording is currently available only on Windows")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for cinematic window recording")
    window_handle = None
    if not desktop:
        if window_title is None or not window_title.strip():
            raise ValueError("window_title is required unless desktop capture is selected")
        window_handle = find_window_handle(window_title)
    command = build_windows_capture_command(
        output,
        window_title=window_title,
        window_handle=window_handle,
        desktop=desktop,
        fps=fps,
        duration_seconds=duration_seconds,
        draw_mouse=draw_mouse,
    )
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-cinematic-record",
        description="Record a DipTrace or arbitrary Windows window for cinematic playback.",
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--window-title", default="DipTrace")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--hide-mouse", action="store_true")
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print a title-based shell-free ffmpeg argument vector without recording.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    window_title = None if args.desktop else args.window_title
    if args.print_command:
        command = build_windows_capture_command(
            args.output,
            window_title=window_title,
            desktop=args.desktop,
            fps=args.fps,
            duration_seconds=args.duration,
            draw_mouse=not args.hide_mouse,
        )
        print(subprocess.list2cmdline(command))
        return 0
    return record_windows(
        args.output,
        window_title=window_title,
        desktop=args.desktop,
        fps=args.fps,
        duration_seconds=args.duration,
        draw_mouse=not args.hide_mouse,
    )


if __name__ == "__main__":
    raise SystemExit(main())
