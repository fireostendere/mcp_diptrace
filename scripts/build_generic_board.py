#!/usr/bin/env python3
"""One-command board builder driven by a declarative JSON spec.

Wraps the proven pipeline stages so a new board is just:

    cp docs/BOARD_SPEC_TEMPLATE.json my-board.json
    # edit parts/nets/placement
    PYTHONPATH=src .venv/bin/python scripts/build_generic_board.py --spec my-board.json

Stages (all optional via --from/--to):
  source  → fetch LCSC JSONs
  lib     → convert to .elixml
  sch     → build schematic
  wire    → add visual wires
  native  → transplant into native template
  pcb     → sync + placement
  route   → autoroute
  finish  → pours + silk + QC
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

STAGES = ["source", "lib", "sch", "wire", "native", "pcb", "route", "finish"]


def run(cmd: str, env: dict[str, str] | None = None, ignore_error: bool = False) -> None:
    print(f"\n$ {cmd}")
    import os
    import shlex
    e = os.environ.copy()
    e["PYTHONHASHSEED"] = "0"
    e["PYTHONPATH"] = "src:."
    if env:
        e.update(env)

    parts = shlex.split(cmd)
    while parts and "=" in parts[0] and not parts[0].startswith("-"):
        k, v = parts[0].split("=", 1)
        e[k] = v
        parts.pop(0)

    if len(parts) >= 2 and parts[-2] == "||" and parts[-1] == "true":
        parts = parts[:-2]
        ignore_error = True

    if not parts:
        return

    r = subprocess.run(parts, env=e)
    if r.returncode != 0 and not ignore_error:
        sys.exit(r.returncode)


def main() -> None:
    p = argparse.ArgumentParser(description="One-command board builder from JSON spec")
    p.add_argument("--spec", required=True, type=Path)
    p.add_argument("--from", dest="from_stage", choices=STAGES, default=STAGES[0])
    p.add_argument("--to", dest="to_stage", choices=STAGES, default=STAGES[-1])
    p.add_argument("--native-sch-template", default="i2c-level-shifter-module.dchxml")
    p.add_argument(
        "--native-pcb-template",
        default="attiny85-arduino-clone/attiny85-arduino-clone-pcb.dipxml",
    )
    p.add_argument("--vendor-dir", default="vendor")
    args = p.parse_args()

    spec = json.loads(args.spec.read_text())
    project = spec.get("project", "my-board")

    start = STAGES.index(args.from_stage)
    end = STAGES.index(args.to_stage)

    def active(name: str) -> bool:
        return start <= STAGES.index(name) <= end

    if active("source"):
        vendor = Path(args.vendor_dir)
        vendor.mkdir(exist_ok=True)
        for comp in spec.get("components", []):
            code = comp.get("lcsc_or_builtin", "")
            if code.startswith("C") and code[1:].isdigit():
                run(
                    f'python3 -m diptrace_mcp.pipeline pipeline_source_component '
                    f'"{code}" "{vendor}" || true'
                )

    if active("lib"):
        run(".venv/bin/python scripts/lcsc_library.py")

    if active("sch"):
        # Delegate to the project's own sch builder if it exists, else wire path
        if Path("scripts/revabuild.py").exists():
            sch_builder = "scripts/revabuild.py"
        else:
            sch_builder = "scripts/build_dut_controller_reva.py"
        run(f".venv/bin/python {sch_builder} || true")

    if active("wire"):
        # Wire the most recent native or synthetic file
        for cand in [f"{project}.dchxml", "dut-controller-reva.dchxml"]:
            if Path(cand).exists():
                run(f".venv/bin/python scripts/wire_schematic.py {cand}")
                break

    if active("native"):
        run(".venv/bin/python scripts/nativeize_reva.py sch")
        run(".venv/bin/python scripts/nativeize_reva.py pcb")

    if active("pcb"):
        run(".venv/bin/python scripts/build_dut_controller_reva_pcb.py")

    if active("route"):
        pcb_script = "scripts/build_dut_controller_reva_pcb.py"
        run(f".venv/bin/python {pcb_script} --route-usb-all || true")
        run(f".venv/bin/python {pcb_script} --route-rest || true")

    if active("finish"):
        pcb_script = "scripts/build_dut_controller_reva_pcb.py"
        run(f".venv/bin/python {pcb_script} --sanitize-pads || true")
        run(f".venv/bin/python {pcb_script} --finish || true")

    print("\nDone. Gates: check PCB_BUILD.md and run --finish QC.")


if __name__ == "__main__":
    main()
