#!/usr/bin/env python3
"""Prepare or validate the manual-only acceptance evidence pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from diptrace_mcp.manual_acceptance import (
    validate_manual_acceptance_pack,
    write_manual_acceptance_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", default="0.2.1")
    parser.add_argument("--commit", default="0" * 40)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        write_manual_acceptance_pack(
            args.output,
            version=args.version,
            commit=args.commit,
        )
        print(f"Prepared manual-only acceptance pack in {args.output}")
        return 0
    result = validate_manual_acceptance_pack(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
