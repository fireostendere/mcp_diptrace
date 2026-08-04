from __future__ import annotations

import argparse
import re
from pathlib import Path

_COVERAGE_GATE_RE = re.compile(r"--cov-fail-under=(\d+(?:\.\d+)?)")


def read_coverage_gate(workflow_path: Path) -> str:
    text = workflow_path.read_text(encoding="utf-8")
    values = sorted(set(_COVERAGE_GATE_RE.findall(text)))
    if len(values) != 1:
        raise ValueError(
            f"expected exactly one coverage gate value in {workflow_path}, found {values}"
        )
    value = values[0]
    return value[:-2] if value.endswith(".0") else value


def render_badge(threshold: str) -> str:
    label = "coverage"
    value = f"≥{threshold}%"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="137" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="137" height="20" rx="3"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="82" height="20" fill="#555"/>
    <rect x="82" width="55" height="20" fill="#4c1"/>
    <rect width="137" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="42" y="15" fill="#010101" fill-opacity=".3">coverage</text>
    <text x="42" y="14">coverage</text>
    <text x="108.5" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="108.5" y="14">{value}</text>
  </g>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic README coverage-gate badge."
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=Path(".github/workflows/ci.yml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/badges/coverage.svg"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    expected = render_badge(read_coverage_gate(args.workflow))
    if args.check:
        if not args.output.is_file():
            raise SystemExit(f"coverage badge is missing: {args.output}")
        actual = args.output.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit(
                "coverage badge is stale; run python scripts/generate_coverage_badge.py"
            )
        print(f"coverage badge is current: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
