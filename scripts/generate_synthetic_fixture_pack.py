#!/usr/bin/env python3
"""Generate/validate the deterministic synthetic fixture pack."""

from __future__ import annotations

import argparse
from pathlib import Path

from diptrace_mcp.synthetic_fixture_pack import (
    validate_synthetic_fixture_pack,
    write_synthetic_fixture_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        write_synthetic_fixture_pack(args.output)
    result = validate_synthetic_fixture_pack(args.output)
    if not result["ok"]:
        for error in result["errors"]:
            print(f"FAIL: {error}")
        return 1
    print(
        f"OK: {result['file_count']} synthetic fixtures validated; "
        "no DipTrace compatibility claim is made"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
