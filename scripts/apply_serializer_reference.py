from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new)


def main() -> None:
    parts = [ROOT / f".github/serializer-reference.part{i}" for i in range(5)]
    if not all(path.exists() for path in parts):
        raise RuntimeError("serializer reference staging parts are incomplete")
    payload = json.loads("".join(path.read_text(encoding="utf-8") for path in parts))
    if payload.get("schema_version") != "diptrace-serializer-reference-v1":
        raise RuntimeError("unexpected serializer reference schema version")
    trust = payload.get("trust", {})
    if trust.get("trust_effect") != "none" or trust.get("may_grant_roundtrip_trust") is not False:
        raise RuntimeError("serializer reference must remain reference-only")
    target = ROOT / "src/diptrace_mcp/data/serializer_reference.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    domain = ROOT / "src/diptrace_mcp/domain.py"
    text = domain.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    hole_width: float | None = Field(default=None, ge=0.0)\n"
        "    hole_height: float | None = Field(default=None, ge=0.0)\n"
        "    mask_paste: dict[str, str] = Field(default_factory=dict)\n",
        "    hole_width: float | None = Field(default=None, ge=0.0)\n"
        "    hole_height: float | None = Field(default=None, ge=0.0)\n"
        "    fiducial_keepout: float | None = Field(default=None, ge=0.0)\n"
        "    mask_paste: dict[str, str] = Field(default_factory=dict)\n",
        "LibraryPadStyle",
    )
    domain.write_text(text, encoding="utf-8")

    adapters = ROOT / "src/diptrace_mcp/library_adapters.py"
    text = adapters.read_text(encoding="utf-8")
    pad_geometry = '''def _pad_geometry(
    style: LibraryPadStyle | None,
    x: float,
    y: float,
    rotation_deg: float,
) -> GeometryShape | None:
    if style is None or style.width <= 0.0:
        return None
    shape_name = style.shape.casefold().replace(" ", "")
    effective_height = style.width if shape_name == "fiducial" else style.height
    if effective_height <= 0.0:
        return None
    approximation: str | None = None
    if shape_name == "fiducial":
        kind: Literal["circle", "ellipse", "rectangle", "obround"] = "circle"
    elif shape_name in {"ellipse", "oval"}:
        kind = "circle" if math.isclose(style.width, effective_height) else "ellipse"
    elif shape_name in {"rectangle", "rect"}:
        kind = "rectangle"
    elif shape_name in {"obround", "roundedrectangle", "long"}:
        kind = "obround"
    elif shape_name in {"d-shape", "dshape"}:
        kind = "rectangle"
        approximation = "D-shape is conservatively represented as a rectangle"
    elif shape_name == "polygon" and len(style.polygon_points) >= 3:
        transform = Transform(translate_x=x, translate_y=y, rotation_deg=rotation_deg)
        return GeometryShape(
            kind="polygon",
            points=[
                transform.apply_point(
                    Point(point["x"] + style.x_offset, point["y"] + style.y_offset)
                ).as_dict()
                for point in style.polygon_points
            ],
        )
    else:
        return None
    transform = Transform(translate_x=x, translate_y=y, rotation_deg=rotation_deg)
    center = transform.apply_point(Point(style.x_offset, style.y_offset))
    return GeometryShape(
        kind=kind,
        center=center.as_dict(),
        width=style.width,
        height=effective_height,
        rotation_deg=rotation_deg,
        approximation=(
            approximation
            or (
                "Rounded corner is conservatively represented as a rectangle"
                if style.corner_percent > 0.0 and kind == "rectangle"
                else None
            )
        ),
    )
'''
    text, count = re.subn(
        r"def _pad_geometry\([\s\S]*?\n\n\ndef _mask_paste_geometry\(",
        pad_geometry + "\n\ndef _mask_paste_geometry(",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("_pad_geometry replacement failed")

    pad_styles = '''def _pad_styles(root: ET.Element | None, units: str) -> list[LibraryPadStyle]:
    if root is None:
        return []
    styles: list[LibraryPadStyle] = []
    for element in root.findall("./PadStyles/PadStyle"):
        main = element.find("./MainStack")
        if main is None:
            shape = ""
            width = 0.0
            height = 0.0
        else:
            shape = main.get("Shape", "")
            width = to_mm(_number(main, "Width"), units)
            height = (
                width
                if shape.casefold().replace(" ", "") == "fiducial"
                else to_mm(_number(main, "Height"), units)
            )
        is_fiducial = shape.casefold().replace(" ", "") == "fiducial"
        hole = element.get("Hole")
        hole_height = element.get("HoleH")
        hole_width_mm = to_mm(float(hole), units) if hole else None
        hole_height_mm = to_mm(float(hole_height), units) if hole_height else None
        mask = element.find("./MaskPaste")
        swell_raw = (
            float(mask.get("CustomSwell"))
            if mask is not None and mask.get("CustomSwell") is not None
            else None
        )
        shrink_raw = (
            float(mask.get("CustomShrink"))
            if mask is not None and mask.get("CustomShrink") is not None
            else None
        )
        custom_swell = (
            None
            if swell_raw is None or math.isclose(swell_raw, -1000.0)
            else to_mm(swell_raw, units)
        )
        custom_shrink = (
            None
            if shrink_raw is None or math.isclose(shrink_raw, -1000.0)
            else to_mm(shrink_raw, units)
        )
        polygon_points = (
            [
                {
                    "x": to_mm(_number(point, "X"), units),
                    "y": to_mm(_number(point, "Y"), units),
                }
                for point in _point_elements(main)
            ]
            if main is not None
            else []
        )
        segments: dict[str, list[dict[str, float]]] = {}
        if mask is not None:
            for side, tag in (("Top", "TopSegments"), ("Bottom", "BotSegments")):
                items = [
                    {
                        key.casefold(): to_mm(_number(item, key), units)
                        for key in ("X1", "Y1", "X2", "Y2")
                    }
                    for item in mask.findall(f"./{tag}/Item")
                ]
                if items:
                    segments[side] = items
        styles.append(
            LibraryPadStyle(
                name=element.get("Name", "") or "<unnamed>",
                pad_type=element.get("Type", "Surface"),
                side=element.get("Side", "Top"),
                shape=shape,
                width=width,
                height=height,
                x_offset=(to_mm(_number(main, "XOff"), units) if main is not None else 0.0),
                y_offset=(
                    to_mm(_number(main, "YOff", _number(main, "Yoff")), units)
                    if main is not None
                    else 0.0
                ),
                corner_percent=(_number(main, "Corner") if main is not None else 0.0),
                polygon_points=polygon_points,
                hole_type=element.get("HoleType"),
                hole_width=(
                    hole_width_mm
                    if not is_fiducial and hole_width_mm is not None and hole_width_mm >= 0
                    else None
                ),
                hole_height=(
                    hole_height_mm
                    if not is_fiducial and hole_height_mm is not None and hole_height_mm >= 0
                    else None
                ),
                fiducial_keepout=(
                    hole_width_mm
                    if is_fiducial and hole_width_mm is not None and hole_width_mm >= 0
                    else None
                ),
                mask_paste=dict(mask.attrib) if mask is not None else {},
                mask_paste_segments=segments,
                custom_swell=custom_swell,
                custom_shrink=custom_shrink,
            )
        )
    return styles
'''
    text, count = re.subn(
        r"def _pad_styles\([\s\S]*?\n\n\ndef _pattern_bbox\(",
        pad_styles + "\n\ndef _pattern_bbox(",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("_pad_styles replacement failed")

    replacements = [
        ('            mounting=element.get("Mounting", "None"),\n', '            mounting=element.get("Mounting", ""),\n'),
        ('                    "filename": _text(model, "./Filename"),\n', '                    "filename": _text(model, "./Filename/Path"),\n                    "filename_path": _text(model, "./Filename/Path"),\n                    "filename_var": _text(model, "./Filename/Var"),\n'),
        ('                        pad_id=pin.get("PadId"),\n', '                        pad_id=pin.get("PadId") or pin.get("PadIndex"),\n'),
        ('                    attached_pattern.get("Style") if attached_pattern is not None else None\n', '                    (attached_pattern.get("Style") or attached_pattern.get("PatternType"))\n                    if attached_pattern is not None\n                    else None\n'),
        ('            "Parser coverage is based on the official DipTrace 4.3 XML specification; "\n            "unknown newer fields are preserved but not interpreted."\n', '            "Parser coverage for newer library fields is constrained by the bundled "\n            "serializer-derived reference; unknown fields are preserved and real DipTrace "\n            "round-trip verification is still required."\n'),
        ('            if style.hole_width is not None:\n', '            if style.hole_width is not None and style.shape.casefold().replace(" ", "") != "fiducial":\n'),
    ]
    for old, new in replacements:
        text = replace_once(text, old, new, old[:60])
    adapters.write_text(text, encoding="utf-8")

    test = ROOT / "tests/test_serializer_reference.py"
    test_text = test.read_text(encoding="utf-8")
    if not test_text.startswith("# ruff: noqa: E501"):
        test.write_text("# ruff: noqa: E501\n" + test_text, encoding="utf-8")

    for path in parts:
        path.unlink(missing_ok=True)
    for path in [
        ROOT / ".github/workflows/integrate-serializer-reference.yml",
        ROOT / ".github/workflows/verify-serializer-final.yml",
        ROOT / "scripts/apply_serializer_reference.py",
    ]:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
