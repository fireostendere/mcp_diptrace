"""Generate a deterministic, explicitly synthetic acceptance fixture pack.

The pack is useful for CI coverage of parser, writer, recommendation and SES
plumbing without a DipTrace installation.  Its manifest deliberately refuses to
claim ``diptrace_exported`` or real round-trip evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scaffolding import PcbScaffold, SchematicScaffold, build_pcb_document, build_schematic_document
from .specctra import parse_ses
from .xml_document import DipTraceDocument, sha256_bytes

_PATTERN_LIBRARY = b'''<?xml version="1.0" encoding="UTF-8"?>
<Library Type="DipTrace-PatternLibrary" Name="Automated Synthetic Patterns" Hint="MCP generated; not DipTrace verified" Version="4.3.0.3" Units="mm">
  <PadStyles><PadStyle Name="SMD_SYNTH" Type="Surface" Side="Top"><MainStack Shape="Rectangle" Width="1" Height="0.8" XOff="0" YOff="0"/><MaskPaste TopMask="Common" BotMask="Common" TopPaste="Common" BotPaste="Common"/></PadStyle></PadStyles>
  <Patterns><Pattern PatternStyle="PatSynth2" RefDes="R" Mounting="SMD" Width="3.2" Height="1.6" Orientation="0" Type="Free"><Name>SYNTH_2PAD</Name><Name_Unique>SYNTH_2PAD_UNIQUE</Name_Unique><DefPad Style="SMD_SYNTH"/><Pads><Pad Id="0" Style="SMD_SYNTH" X="-0.8" Y="0" Angle="0" Locked="N" Side="Top"><Number>1</Number></Pad><Pad Id="1" Style="SMD_SYNTH" X="0.8" Y="0" Angle="0" Locked="N" Side="Top"><Number>2</Number></Pad></Pads><SyntheticUnknown Preserve="Y"/></Pattern></Patterns>
</Library>'''

_COMPONENT_LIBRARY = b'''<?xml version="1.0" encoding="UTF-8"?>
<Library Type="DipTrace-ComponentLibrary" Name="Automated Synthetic Components" Hint="MCP generated; not DipTrace verified" Version="4.3.0.3" Units="mm">
  <Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm"><PadStyles><PadStyle Name="SMD_SYNTH" Type="Surface" Side="Top"><MainStack Shape="Rectangle" Width="1" Height="0.8" XOff="0" YOff="0"/></PadStyle></PadStyles><Patterns><Pattern PatternStyle="PatSynth2" RefDes="R" Mounting="SMD"><Name>SYNTH_2PAD</Name><DefPad Style="SMD_SYNTH"/><Pads><Pad Id="0" Style="SMD_SYNTH" X="-0.8" Y="0"><Number>1</Number></Pad><Pad Id="1" Style="SMD_SYNTH" X="0.8" Y="0"><Number>2</Number></Pad></Pads></Pattern></Patterns></Library>
  <Components><Component><Part RefDes="R" PartType="Normal" ShowNumbers="Common" Type="Free"><Name>SYNTH_RESISTOR</Name><Value>1k</Value><Pins><Pin Id="0" X="-1" Y="0" Type="Default" ElectricType="Passive" PadId="0"><Name>A</Name><PadNumber>1</PadNumber></Pin><Pin Id="1" X="1" Y="0" Type="Default" ElectricType="Passive" PadId="1"><Name>B</Name><PadNumber>2</PadNumber></Pin></Pins><Pattern Style="PatSynth2"/><SyntheticUnknown Preserve="Y"/></Part></Component></Components>
</Library>'''

_SYNTHETIC_DSN = b'''(pcb "synthetic-board"
  (parser (string_quote "))
  (resolution mm 1000)
  (structure (layer "Top" (type signal)) (layer "Bottom" (type signal)))
  (network)
)'''

_SYNTHETIC_SES = b'''(session "synthetic.ses"
  (base_design "synthetic.dsn")
  (routes
    (resolution mm 1000)
    (parser (host_cad "diptrace-mcp-synthetic"))
    (library_out)
    (network_out)
  )
)'''


def build_synthetic_fixture_bytes() -> dict[str, bytes]:
    """Return the canonical pack in stable filename order."""

    return {
        "pcb.xml": build_pcb_document(PcbScaffold(width_mm=40.0, height_mm=30.0)),
        "schematic.xml": build_schematic_document(SchematicScaffold(sheet_names=["Main"])),
        "component_library.xml": _COMPONENT_LIBRARY,
        "pattern_library.xml": _PATTERN_LIBRARY,
        "router.dsn": _SYNTHETIC_DSN,
        "router.ses": _SYNTHETIC_SES,
    }


def synthetic_fixture_manifest(files: dict[str, bytes]) -> dict[str, Any]:
    entries = []
    for name in sorted(files):
        kind = "specctra" if name.endswith((".dsn", ".ses")) else "diptrace_xml"
        entries.append(
            {
                "path": name,
                "kind": kind,
                "sha256": sha256_bytes(files[name]),
                "size_bytes": len(files[name]),
                "validation_level": "synthetic_parser_only",
                "diptrace_verified": False,
            }
        )
    return {
        "schema_version": "diptrace-mcp-synthetic-fixture-pack-v1",
        "origin": "mcp_generated",
        "redistributable": True,
        "diptrace_verified": False,
        "claims": ["deterministic_generation", "parser_ci_scaffolding"],
        "non_claims": [
            "diptrace_exported",
            "diptrace_open_save_verified",
            "diptrace_roundtrip_verified",
        ],
        "files": entries,
    }


def write_synthetic_fixture_pack(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = build_synthetic_fixture_bytes()
    for name, data in files.items():
        (output_dir / name).write_bytes(data)
    manifest = synthetic_fixture_manifest(files)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_synthetic_fixture_pack(output_dir: Path) -> dict[str, Any]:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for entry in manifest.get("files", []):
        path = output_dir / str(entry["path"])
        if not path.is_file():
            errors.append(f"missing:{path.name}")
            continue
        data = path.read_bytes()
        if sha256_bytes(data) != entry.get("sha256"):
            errors.append(f"sha256:{path.name}")
            continue
        if path.suffix == ".xml":
            try:
                DipTraceDocument.from_bytes(path, data)
            except Exception as exc:  # validation summary intentionally aggregates failures
                errors.append(f"xml:{path.name}:{type(exc).__name__}")
        elif path.suffix == ".ses":
            try:
                parse_ses(data, max_bytes=max(1024, len(data) + 1))
            except Exception as exc:
                errors.append(f"ses:{path.name}:{type(exc).__name__}")
    return {
        "ok": not errors,
        "errors": errors,
        "file_count": len(manifest.get("files", [])),
        "diptrace_verified": False,
    }
