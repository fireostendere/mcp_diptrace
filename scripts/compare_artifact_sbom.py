#!/usr/bin/env python3
"""Compare a Syft CycloneDX artifact inventory with declared project names."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def _name(requirement: str) -> str:
    value = requirement.split("[", 1)[0]
    value = re.split(r"[<>=!~; ]", value, maxsplit=1)[0]
    return value.lower().replace("_", "-")


def _safe_component_name(value: object) -> str:
    text = str(value or "").replace("\\", "/")
    if re.match(r"^(?:/|[A-Za-z]:/)", text):
        return "<absolute-path>"
    return text


def summarize(sbom: Path, pyproject: Path) -> dict[str, Any]:
    data = json.loads(sbom.read_text(encoding="utf-8"))
    components = data.get("components", []) if isinstance(data, dict) else []
    observed = sorted(
        {
            _safe_component_name(item.get("name")).lower().replace("_", "-")
            for item in components
            if isinstance(item, dict) and item.get("name")
        }
    )
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    metadata = project["project"]
    declared = {_name(value) for value in metadata.get("dependencies", [])}
    for requirements in metadata.get("optional-dependencies", {}).values():
        declared.update(_name(value) for value in requirements)
    declared.update(_name(value) for value in project.get("build-system", {}).get("requires", []))
    return {
        "sbom": sbom.name,
        "declared_names": sorted(declared),
        "observed_component_names": observed,
        "observed_not_declared": sorted(set(observed) - declared),
        "declared_not_observed": sorted(declared - set(observed)),
        "interpretation": (
            "Differences require review; they are not automatically license or security findings."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--pyproject", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.sbom, args.pyproject)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
