from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .cinematic_preflight import preflight_cinematic_manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-cinematic-preflight",
        description="Validate cinematic timing/payload safety budgets before desktop playback.",
    )
    parser.add_argument("manifest", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    value = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("cinematic manifest root must be an object")
    result = preflight_cinematic_manifest(value)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
