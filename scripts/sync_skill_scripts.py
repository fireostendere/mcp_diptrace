#!/usr/bin/env python3
"""Keep packaged evidence-capture scripts generated from canonical scripts."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    (
        ROOT / "scripts/capture_diptrace_evidence.py",
        ROOT / "skills/diptrace-evidence-capture/scripts/capture_diptrace_evidence.py",
    ),
    (
        ROOT / "scripts/ingest_fixtures.py",
        ROOT / "skills/diptrace-evidence-capture/scripts/ingest_fixtures.py",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches: list[str] = []
    for canonical, packaged in PAIRS:
        if args.check:
            if not packaged.exists() or canonical.read_bytes() != packaged.read_bytes():
                mismatches.append(
                    f"{packaged.relative_to(ROOT)} != {canonical.relative_to(ROOT)}"
                )
        else:
            packaged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(canonical, packaged)
    if mismatches:
        for item in mismatches:
            print(f"FAIL: {item}")
        print("Run: python scripts/sync_skill_scripts.py")
        return 1
    print("OK: packaged skill scripts are synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
