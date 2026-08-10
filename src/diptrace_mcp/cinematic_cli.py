from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .cinematic import PRESETS, CinematicRecorder, ffmpeg_commands


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-cinematic",
        description="Build deterministic DipTrace cinematic timelines and recording commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Create an append-only cinematic capture file."
    )
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--preset", choices=sorted(PRESETS), default="cinematic")
    init_parser.add_argument(
        "--domain",
        choices=("auto", "general", "pcb", "schematic"),
        default="auto",
    )
    init_parser.add_argument("--include-payload", action="store_true")
    init_parser.add_argument("--force", action="store_true")

    event_parser = subparsers.add_parser("event", help="Append one MCP/service event to a capture.")
    event_parser.add_argument("path", type=Path)
    event_parser.add_argument("tool")
    event_parser.add_argument("--label")
    event_parser.add_argument("--target")
    event_parser.add_argument("--phase", choices=("before", "after", "single"), default="single")
    event_parser.add_argument(
        "--payload-json",
        help=(
            "Optional JSON object. It is persisted only if the capture was initialized "
            "with --include-payload."
        ),
    )

    compile_parser = subparsers.add_parser(
        "compile", help="Compile a capture into a deterministic cinematic manifest."
    )
    compile_parser.add_argument("capture", type=Path)
    compile_parser.add_argument("--output", type=Path)

    ffmpeg_parser = subparsers.add_parser(
        "ffmpeg", help="Print MP4 and two-pass GIF conversion commands."
    )
    ffmpeg_parser.add_argument("input_video", type=Path)
    ffmpeg_parser.add_argument("output_stem", type=Path)
    ffmpeg_parser.add_argument("--preset", choices=sorted(PRESETS), default="cinematic")

    return parser


def _capture_header(path: Path) -> dict[str, object]:
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    value = json.loads(first_line)
    if not isinstance(value, dict) or value.get("type") != "diptrace-cinematic-capture":
        raise ValueError("cinematic capture header is invalid")
    return value


def _payload(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--payload-json must contain a JSON object")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            recorder = CinematicRecorder(
                args.path,
                title=args.title,
                preset=args.preset,
                domain=args.domain,
                include_payload=args.include_payload,
            )
            path = recorder.initialize(overwrite=args.force)
            print(path)
            return 0

        if args.command == "event":
            header = _capture_header(args.path)
            recorder = CinematicRecorder(
                args.path,
                title=str(header.get("title") or "Cinematic capture"),
                preset=str(header.get("preset") or "cinematic"),
                domain=str(header.get("domain") or "auto"),  # type: ignore[arg-type]
                include_payload=bool(header.get("include_payload", False)),
            )
            recorder.observe_tool(
                args.tool,
                phase=args.phase,
                label=args.label,
                target=args.target,
                payload=_payload(args.payload_json),
            )
            return 0

        if args.command == "compile":
            timeline = CinematicRecorder.load(args.capture)
            manifest = timeline.manifest()
            text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
            if args.output is None:
                sys.stdout.write(text)
            else:
                args.output.write_text(text, encoding="utf-8")
                print(args.output)
            return 0

        if args.command == "ffmpeg":
            commands = ffmpeg_commands(
                args.input_video,
                output_stem=args.output_stem,
                preset=args.preset,
            )
            for name, command in commands.items():
                print(f"{name}: {command}")
            return 0
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        parser.error(str(exc))

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
