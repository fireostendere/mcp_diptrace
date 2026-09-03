"""BOM grouping and component provenance helpers.

Sources: attiny85-arduino-clone/set_bom_fields.py, COMPONENT_PROVENANCE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diptrace_mcp.xml_document import DipTraceDocument


@dataclass(frozen=True)
class BomLine:
    refdes: list[str]
    value: str
    pattern: str
    mpn: str
    manufacturer: str
    lcsc: str
    datasheet: str


def export_bom(schematic_path: str | Path) -> list[BomLine]:
    """Group BOM records by exact sourcing identity (MPN+value+pattern)."""
    doc = DipTraceDocument.load(Path(schematic_path), 128 * 1024 * 1024)
    # Use the MCP's own grouping: by refdes dedup on MPN+manufacturer+value+pattern
    groups: dict[tuple[str, str, str, str], BomLine] = {}
    for p in doc.root.findall("./Schematic/Components/Part"):
        refdes = p.findtext("./RefDes") or ""
        if refdes.startswith(("PSG", "PWR", "NPI", "NPO")):
            continue
        value = p.findtext("./Value") or ""
        add_fields = {f.findtext("./Name") or "": f.findtext("./Text") or ""
                      for f in p.findall("./AddFields/AddField")}
        mpn = add_fields.get("MPN", "")
        manuf = add_fields.get("Manufacturer", p.findtext("./Manufacturer") or "")
        lcsc = add_fields.get("LCSC", "")
        ds = p.findtext("./Datasheet") or add_fields.get("Datasheet", "")
        pat_el = p.find("./Pattern")
        pat = pat_el.get("Style", "") if pat_el is not None else ""
        key = (mpn, manuf, value, pat)
        if key not in groups:
            groups[key] = BomLine(refdes=[refdes], value=value, pattern=pat,
                                  mpn=mpn, manufacturer=manuf, lcsc=lcsc, datasheet=ds)
        else:
            # extend refdes list
            groups[key] = BomLine(
                refdes=groups[key].refdes + [refdes],
                value=groups[key].value, pattern=groups[key].pattern,
                mpn=groups[key].mpn, manufacturer=groups[key].manufacturer,
                lcsc=groups[key].lcsc, datasheet=groups[key].datasheet,
            )
    return sorted(groups.values(), key=lambda b: b.mpn)


def write_provenance_markdown(lines: list[BomLine], output: Path) -> None:
    output.write_text(
        "# Component provenance\n\n"
        "Lookup order: DipTrace exact match → LCSC exact MPN → custom.\n\n"
        "| RefDes | MPN | Manufacturer | Value | Pattern | LCSC | Datasheet |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(
            f"| {', '.join(line.refdes)} | {line.mpn} | {line.manufacturer} "
            f"| {line.value} | {line.pattern} | {line.lcsc} | {line.datasheet} |"
            for line in lines
        ) + "\n",
        encoding="utf-8",
    )


def set_bom_fields(
    schematic_path: str | Path,
    fields: dict[str, dict[str, str]],
    expected_sha256: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Set custom BOM fields (MPN/LCSC/Manufacturer/Datasheet) on selected
    parts. Wraps SetComponentPropertiesOperation per refdes.

    fields: {refdes: {"MPN": "...", "LCSC": "C2845237", ...}}
    """
    from diptrace_mcp.domain import QuerySelector
    from diptrace_mcp.operations import SemanticOperation, SetComponentPropertiesOperation
    from diptrace_mcp.semantic_compiler import apply_semantic_operations

    doc = DipTraceDocument.load(Path(schematic_path), 128 * 1024 * 1024)
    ops: list[SemanticOperation] = [
        SetComponentPropertiesOperation(
            selector=QuerySelector(refdes=[refdes]),
            fields=kv,
        )
        for refdes, kv in fields.items()
    ]
    compiled = apply_semantic_operations(doc, ops)
    if not dry_run:
        compiled.document.path.write_bytes(compiled.document.raw_bytes)
    return {"sha256": compiled.document.sha256, "updated": len(fields)}
