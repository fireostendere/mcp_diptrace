from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .diptrace_ui import (
    CalibrationAnchor,
    ClientPoint,
    DesignPoint,
    DesignToClientTransform,
    DipTraceUIProfile,
    make_diptrace_profile,
)
from .diptrace_window import normalized_cursor_position


def _point(value: Any, *, field_name: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError(f"{field_name} must contain [x, y]")
    return float(value[0]), float(value[1])


def _load_anchors(path: Path) -> list[CalibrationAnchor]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("calibration anchors must be a JSON array")
    anchors: list[CalibrationAnchor] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"calibration anchor {index} must be an object")
        design_x, design_y = _point(
            item.get("design"),
            field_name=f"anchors[{index}].design",
        )
        client_x, client_y = _point(
            item.get("client"),
            field_name=f"anchors[{index}].client",
        )
        anchors.append(
            CalibrationAnchor(
                DesignPoint(design_x, design_y),
                ClientPoint(client_x, client_y),
            )
        )
    return anchors


def _output_path(source: Path, output: Path | None) -> Path:
    return output if output is not None else source


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-ui-profile",
        description="Create, calibrate and validate DipTrace cinematic UI profiles.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser(
        "template",
        help="Create an uncalibrated profile template.",
    )
    template.add_argument("--editor", required=True, choices=("pcb", "schematic"))
    template.add_argument("--version", default="5.3")
    template.add_argument("--window", default="DipTrace")
    template.add_argument("--output", required=True, type=Path)

    calibrate = commands.add_parser(
        "calibrate",
        help="Fit design coordinates to client space.",
    )
    calibrate.add_argument("profile", type=Path)
    calibrate.add_argument("anchors", type=Path)
    calibrate.add_argument("--output", type=Path)
    calibrate.add_argument("--max-rms-error", type=float, default=0.01)
    calibrate.add_argument("--max-point-error", type=float, default=0.025)

    action = commands.add_parser(
        "action",
        help="Install or replace one UI action macro.",
    )
    action.add_argument("profile", type=Path)
    action.add_argument("name")
    action.add_argument("steps", type=Path)
    action.add_argument("--output", type=Path)

    probe = commands.add_parser(
        "probe",
        help="Print current cursor coordinates normalized to a DipTrace client window.",
    )
    probe.add_argument("--window", default="DipTrace")

    validate = commands.add_parser("validate", help="Validate profile readiness.")
    validate.add_argument("profile", type=Path)
    return parser


def _set_action(profile: DipTraceUIProfile, name: str, steps_path: Path) -> DipTraceUIProfile:
    steps = json.loads(steps_path.read_text(encoding="utf-8"))
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)) or not steps:
        raise ValueError("UI action steps must be a non-empty JSON array")
    raw = profile.to_dict()
    actions = raw["actions"]
    if not isinstance(actions, dict):
        raise ValueError("generated profile actions must be an object")
    actions[name] = list(steps)
    return DipTraceUIProfile.from_dict(raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            profile = make_diptrace_profile(
                args.editor,
                version=args.version,
                window_title_contains=args.window,
            )
            print(profile.save(args.output))
            return 0

        if args.command == "calibrate":
            profile = DipTraceUIProfile.load(args.profile)
            anchors = _load_anchors(args.anchors)
            transform = DesignToClientTransform.calibrate(
                anchors,
                max_rms_error=args.max_rms_error,
                max_point_error=args.max_point_error,
            )
            rms, maximum = transform.error(anchors)
            target = _output_path(args.profile, args.output)
            profile.with_transform(transform).save(target)
            print(
                json.dumps(
                    {
                        "profile": str(target),
                        "anchors": len(anchors),
                        "rms_error": rms,
                        "max_error": maximum,
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "action":
            profile = DipTraceUIProfile.load(args.profile)
            target = _output_path(args.profile, args.output)
            _set_action(profile, args.name, args.steps).save(target)
            print(target)
            return 0

        if args.command == "probe":
            point = normalized_cursor_position(args.window)
            print(json.dumps({"client": [point.x, point.y]}, sort_keys=True))
            return 0

        if args.command == "validate":
            profile = DipTraceUIProfile.load(args.profile)
            result = {
                "profile_id": profile.profile_id,
                "editor": profile.editor,
                "calibrated": profile.is_calibrated,
                "missing_actions": list(profile.missing_actions),
                "ready": profile.is_ready,
            }
            print(json.dumps(result, sort_keys=True))
            return 0 if profile.is_ready else 1
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
