"""Run actual DipTrace on isolated copies; retain evidence even when a gate fails."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from diptrace_mcp.native_cad import NativeCadRequest, run_native_cad
from diptrace_mcp.xml_document import DipTraceDocument


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diptrace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path("i2c-level-shifter-pcb.dipxml").resolve()
    document = DipTraceDocument.load(source, 64 * 1024 * 1024)
    result = run_native_cad(
        NativeCadRequest(
            source=source,
            output_dir=args.output.resolve() / "i2c-board",
            diptrace_root=args.diptrace_root,
            expected_sha256=document.sha256,
            timeout_seconds=180.0,
            export_manufacturing=True,
        )
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if not result["completed"]:
        raise SystemExit("Native execution incomplete; inspect retained evidence")
    # This initial integration checks actual native output, not PCB approval.
    output = args.output.resolve() / "i2c-board"
    for name in (
        "saved.dip",
        "reexport.dipxml",
        "native-fabrication.zip",
        "native-placement.csv",
    ):
        if not (output / name).is_file() or (output / name).stat().st_size == 0:
            raise SystemExit(f"Missing or empty native output: {name}")


if __name__ == "__main__":
    main()
