from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Preserve schematic wire geometry in the normalized model.
adapters = ROOT / "src/diptrace_mcp/adapters.py"
replace_once(
    adapters,
    '''                        attributes={
                            "sheet": wire.get("Sheet", ""),
                            "point_count": len(wire_points),
                            **dict(wire.attrib),
                        },''',
    '''                        attributes={
                            "sheet": wire.get("Sheet", ""),
                            "point_count": len(wire_points),
                            "points": [point.as_dict() for point in wire_points],
                            **dict(wire.attrib),
                        },''',
)

# Expose why a semantic comparison is incomplete.
domain = ROOT / "src/diptrace_mcp/domain.py"
text = domain.read_text(encoding="utf-8")
text = text.replace(
    '    compared_categories: list[str] = Field(default_factory=list)\n'
    '    differences: list[str] = Field(default_factory=list)\n',
    '    compared_categories: list[str] = Field(default_factory=list)\n'
    '    missing_required_categories: list[str] = Field(default_factory=list)\n'
    '    differences: list[str] = Field(default_factory=list)\n',
    2,
)
domain.write_text(text, encoding="utf-8")

service = ROOT / "src/diptrace_mcp/service.py"
service_text = service.read_text(encoding="utf-8")
service_text = service_text.replace("import math\n", "import math\nimport os\n", 1)
service_text = service_text.replace(
    '''def same_file_role(path_a: Path, path_b: Path) -> bool:
    """Platform-independent file identity check for evidence role exclusion.

    Resolves symlinks and normalizes paths before comparing.  Works correctly
    on Windows (drive letters, case-insensitive paths), Linux, and macOS.
    """
    try:
        return path_a.resolve(strict=False) == path_b.resolve(strict=False)
    except (OSError, ValueError):
        return path_a == path_b
''',
    '''def same_file_role(path_a: Path, path_b: Path) -> bool:
    """Return whether two evidence roles identify the same filesystem object."""
    try:
        if path_a.exists() and path_b.exists():
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    try:
        left = os.path.normcase(os.path.abspath(path_a.resolve(strict=False)))
        right = os.path.normcase(os.path.abspath(path_b.resolve(strict=False)))
    except (OSError, ValueError):
        left = os.path.normcase(os.path.abspath(path_a))
        right = os.path.normcase(os.path.abspath(path_b))
    return left == right
''',
    1,
)

new_function = r'''def _semantic_roundtrip_check(
    source: DipTraceDocument, reexport: DipTraceDocument
) -> dict[str, Any]:
    """Compare electrically meaningful normalized DipTrace structures."""
    differences: list[str] = []
    compared: list[str] = ["source_type"]
    unsupported: list[dict[str, str]] = []
    warnings: list[str] = []

    if source.source_type != reexport.source_type:
        differences.append(
            f"source_type: {source.source_type!r} vs {reexport.source_type!r}"
        )

    source_snapshot = build_snapshot(source)
    reexport_snapshot = build_snapshot(reexport)
    warnings.extend(source_snapshot.warnings)
    warnings.extend(reexport_snapshot.warnings)

    def rounded(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, dict):
            return tuple(sorted((str(key), rounded(item)) for key, item in value.items()))
        if isinstance(value, list):
            return tuple(rounded(item) for item in value)
        return value

    def record_key(record: ObjectRecord) -> tuple[str, str, str]:
        return (record.xml_id or "", record.refdes or "", record.label or record.stable_id)

    def compare_category(name: str, left: Any, right: Any) -> None:
        compared.append(name)
        if rounded(left) != rounded(right):
            differences.append(f"{name}: semantic content differs")

    if source_snapshot.board is not None and reexport_snapshot.board is not None:
        sb = source_snapshot.board
        rb = reexport_snapshot.board
        compare_category("board_outline", sb.outline, rb.outline)
        compare_category("copper_layers", sb.layers, rb.layers)
        compare_category(
            "via_styles",
            [item.model_dump(mode="json") for item in sb.via_styles],
            [item.model_dump(mode="json") for item in rb.via_styles],
        )

        def component_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item), item.name, item.value, item.side, item.locked,
                item.position, rounded(item.rotation_deg), item.mirrored,
                item.attributes.get("pattern_style"), item.attributes.get("pattern_name"),
            )

        compare_category(
            "components",
            [component_sig(item) for item in sorted(sb.components, key=record_key)],
            [component_sig(item) for item in sorted(rb.components, key=record_key)],
        )

        def endpoint_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item), item.parent_id, item.net_id, item.net_name,
                item.position, item.layer, item.attributes,
            )

        compare_category(
            "pads",
            [endpoint_sig(item) for item in sorted(sb.pads, key=record_key)],
            [endpoint_sig(item) for item in sorted(rb.pads, key=record_key)],
        )

        def net_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item), item.name, item.locked,
                item.attributes.get("net_class", item.attributes.get("NetClass")),
                sorted(item.relationships.get("endpoints", [])),
                sorted(item.relationships.get("traces", [])),
                sorted(item.relationships.get("vias", [])),
            )

        compare_category(
            "nets",
            [net_sig(item) for item in sorted(sb.nets, key=record_key)],
            [net_sig(item) for item in sorted(rb.nets, key=record_key)],
        )

        def trace_pair_membership(board: Any) -> dict[str, list[tuple[str, str]]]:
            membership: dict[str, list[tuple[str, str]]] = {}
            for pair in board.differential_pairs:
                for segment in pair.segments:
                    if segment.positive_trace_xml_id:
                        membership.setdefault(segment.positive_trace_xml_id, []).append(
                            (pair.name, "positive")
                        )
                    if segment.negative_trace_xml_id:
                        membership.setdefault(segment.negative_trace_xml_id, []).append(
                            (pair.name, "negative")
                        )
            return membership

        source_pairs = trace_pair_membership(sb)
        reexport_pairs = trace_pair_membership(rb)

        def trace_sig(item: ObjectRecord, pairs: dict[str, list[tuple[str, str]]]) -> Any:
            attrs = item.attributes
            return (
                record_key(item), item.net_id, item.net_name, item.layer, item.locked,
                attrs.get("Connected1"), attrs.get("Connected2"),
                attrs.get("points", []), attrs.get("segment_widths_mm", []),
                attrs.get("segment_layers", []), attrs.get("point_via_styles", []),
                attrs.get("point_arc_middle", []),
                sorted(pairs.get(item.xml_id or "", [])),
            )

        compare_category(
            "traces",
            [trace_sig(item, source_pairs) for item in sorted(sb.traces, key=record_key)],
            [trace_sig(item, reexport_pairs) for item in sorted(rb.traces, key=record_key)],
        )

        def via_sig(item: ObjectRecord) -> Any:
            attrs = item.attributes
            return (
                record_key(item), item.parent_id, item.net_id, item.net_name,
                item.position, item.layer, item.locked, attrs.get("via_style"),
                attrs.get("layer_start_id"), attrs.get("layer_end_id"),
                attrs.get("span_layer_ids", []), attrs.get("diameter_mm"),
                attrs.get("hole_mm"),
            )

        compare_category(
            "vias",
            [via_sig(item) for item in sorted(sb.vias, key=record_key)],
            [via_sig(item) for item in sorted(rb.vias, key=record_key)],
        )
        compare_category(
            "differential_pairs",
            [item.model_dump(mode="json", exclude={"stable_id"}) for item in sb.differential_pairs],
            [item.model_dump(mode="json", exclude={"stable_id"}) for item in rb.differential_pairs],
        )

    if source_snapshot.schematic is not None and reexport_snapshot.schematic is not None:
        ss = source_snapshot.schematic
        rs = reexport_snapshot.schematic
        compare_category("sheets", ss.sheets, rs.sheets)

        def part_sig(item: ObjectRecord) -> Any:
            attrs = item.attributes
            return (
                record_key(item), item.name, item.value, item.position,
                rounded(item.rotation_deg), item.mirrored, item.locked,
                attrs.get("sheet"), attrs.get("component_style"),
                attrs.get("component_part"), attrs.get("part_number"),
            )

        compare_category(
            "parts",
            [part_sig(item) for item in sorted(ss.parts, key=record_key)],
            [part_sig(item) for item in sorted(rs.parts, key=record_key)],
        )
        compare_category(
            "patterns",
            [(record_key(item), item.attributes.get("component_style"))
             for item in sorted(ss.parts, key=record_key)],
            [(record_key(item), item.attributes.get("component_style"))
             for item in sorted(rs.parts, key=record_key)],
        )

        def pin_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item), item.parent_id, item.net_id, item.net_name,
                item.attributes,
            )

        source_pins = [pin_sig(item) for item in sorted(ss.pins, key=record_key)]
        reexport_pins = [pin_sig(item) for item in sorted(rs.pins, key=record_key)]
        compare_category("pins", source_pins, reexport_pins)
        compare_category(
            "pin_net_membership",
            [(item.xml_id, item.net_id, item.net_name) for item in sorted(ss.pins, key=record_key)],
            [(item.xml_id, item.net_id, item.net_name) for item in sorted(rs.pins, key=record_key)],
        )

        def schematic_net_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item), item.name, item.locked,
                sorted(item.relationships.get("endpoints", [])),
            )

        compare_category(
            "schematic_nets",
            [schematic_net_sig(item) for item in sorted(ss.nets, key=record_key)],
            [schematic_net_sig(item) for item in sorted(rs.nets, key=record_key)],
        )

        def wire_sig(item: ObjectRecord, include_geometry: bool) -> Any:
            base = (
                record_key(item), item.net_id, item.net_name, item.locked,
                item.attributes.get("sheet"),
            )
            return base + ((item.attributes.get("points", []),) if include_geometry else ())

        compare_category(
            "wires",
            [wire_sig(item, False) for item in sorted(ss.wires, key=record_key)],
            [wire_sig(item, False) for item in sorted(rs.wires, key=record_key)],
        )
        compare_category(
            "wire_geometry",
            [wire_sig(item, True) for item in sorted(ss.wires, key=record_key)],
            [wire_sig(item, True) for item in sorted(rs.wires, key=record_key)],
        )
        compare_category(
            "hierarchy",
            [(record_key(item), item.attributes.get("sheet"))
             for item in sorted(ss.parts, key=record_key)],
            [(record_key(item), item.attributes.get("sheet"))
             for item in sorted(rs.parts, key=record_key)],
        )
        compare_category(
            "buses",
            [item.model_dump(mode="json") for item in ss.buses],
            [item.model_dump(mode="json") for item in rs.buses],
        )

        def label_signatures(document: DipTraceDocument) -> list[Any]:
            labels: list[Any] = []
            for element in document.container.iter():
                if "label" not in str(element.tag).casefold():
                    continue
                labels.append(
                    (
                        element.tag,
                        tuple(sorted(element.attrib.items())),
                        (element.text or "").strip(),
                        tuple(
                            (child.tag, tuple(sorted(child.attrib.items())), (child.text or "").strip())
                            for child in element
                        ),
                    )
                )
            return sorted(labels, key=repr)

        compare_category("labels", label_signatures(source), label_signatures(reexport))

    known_root_children = {"Library", "Board", "Schematic"}
    has_critical_unsupported = False
    for document_label, document in (("source", source), ("reexport", reexport)):
        for child in document.root:
            if child.tag not in known_root_children:
                unsupported.append({
                    "category": f"unknown_xml_section:{child.tag}",
                    "severity": "critical",
                    "reason": f"Unknown top-level section in {document_label}",
                })
                has_critical_unsupported = True

    required: set[str] = {"source_type"}
    if source_snapshot.board is not None or reexport_snapshot.board is not None:
        required.update(REQUIRED_PCB_COMPARISON_CATEGORIES)
        required.add("differential_pairs")
    if source_snapshot.schematic is not None or reexport_snapshot.schematic is not None:
        required.update(REQUIRED_SCHEMATIC_COMPARISON_CATEGORIES)
        required.update({"schematic_nets", "buses"})

    missing_required = sorted(required - set(compared))
    comparison_complete = not missing_required
    if missing_required:
        differences.append(
            "missing_required_categories: " + ", ".join(missing_required)
        )

    critical_warnings = [
        warning for warning in warnings
        if any(token in warning.casefold() for token in ("error", "invalid", "missing"))
    ]
    passed = (
        not differences
        and comparison_complete
        and not has_critical_unsupported
        and not critical_warnings
    )
    return {
        "passed": passed,
        "comparison_complete": comparison_complete,
        "compared_categories": compared,
        "missing_required_categories": missing_required,
        "differences": differences,
        "ignored_normalizations": [],
        "unsupported_categories": unsupported,
        "parse_warnings": warnings,
    }
'''

pattern = re.compile(
    r"def _semantic_roundtrip_check\(.*?\n\nclass DipTraceService:",
    re.DOTALL,
)
match = pattern.search(service_text)
if match is None:
    raise RuntimeError("semantic comparison function was not found")
service_text = service_text[: match.start()] + new_function + "\n\nclass DipTraceService:" + service_text[match.end():]
service.write_text(service_text, encoding="utf-8")

# Replace duplicated matrix CI with platform-specific responsibilities.
ci = ROOT / ".github/workflows/ci.yml"
ci.write_text('''name: CI

on:
  pull_request:
  push:
    branches:
      - main

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  test-linux:
    name: test-linux (${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.10", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q

  static-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m ruff check --no-cache src tests benchmarks scripts
      - run: python -m mypy --no-incremental src/diptrace_mcp
      - run: python scripts/generate_pcb_skills.py --check

  test-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q
      - run: diptrace-mcp --help

  test-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q
      - run: diptrace-mcp --help

  build-windows-bridge:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Build unsigned bridge
        shell: pwsh
        run: powershell -ExecutionPolicy Bypass -File .\\plugin\\build_bridge.ps1 -PythonCommand python -Clean
      - name: Verify bridge executable
        shell: pwsh
        run: |
          $path = ".\\plugin\\dist\\diptrace_mcp_bridge.exe"
          if (-not (Test-Path $path)) { throw "Bridge executable was not created" }
          if ((Get-Item $path).Length -le 0) { throw "Bridge executable is empty" }
      - uses: actions/upload-artifact@v4
        with:
          name: diptrace-bridge-ci-unsigned
          path: plugin/dist/diptrace_mcp_bridge.exe
''', encoding="utf-8")

# Remove temporary diagnostic/apply machinery from the resulting commit.
for temporary in (
    ROOT / ".github/workflows/diagnose-windows.yml",
    ROOT / ".github/workflows/apply-fix.yml",
    Path(__file__),
):
    temporary.unlink(missing_ok=True)
