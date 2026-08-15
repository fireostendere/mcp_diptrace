"""Read-only access to the installed DipTrace library catalog."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from ..errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    DocumentError,
    ObjectNotFoundError,
)
from ..geometry import from_mm, to_mm
from ..headless_gui import export_component_library_xml
from ..operations import PlacePartOperation, SemanticOperation
from ..windows_configurator import (
    ConfiguratorError,
    detect_diptrace_installations,
    validate_diptrace_directory,
)
from ..xml_document import DipTraceDocument
from .context import DocumentGateway, ServiceContext, validate_page

CatalogKind = Literal["component", "pattern", "library"]
SemanticWrite = Callable[
    [SemanticOperation, str | None, bool, str | None, str | None], dict[str, Any]
]
_CATALOG_ID = re.compile(r"^builtin-component:([0-9]+):([0-9]+)$")
_MAX_EXPORT_BYTES = 512 * 1024 * 1024
_GEOMETRY_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "Part": ("Width", "Height"),
    "Origin": ("X", "Y"),
    "Group": ("X", "Y"),
    "Pin": (
        "X",
        "Y",
        "Length",
        "NumXShift",
        "NumYShift",
        "NameXShift",
        "NameYShift",
    ),
    "Shape": ("LineWidth", "TextWidth", "TextHeight"),
    "Point": ("X", "Y"),
    "Pattern": ("Width", "Height"),
    "Pad": ("X", "Y"),
    "Hole": ("X", "Y", "Diam", "HoleDiam"),
    "PadStyle": ("Hole",),
    "MainStack": ("Width", "Height", "XOff", "YOff"),
    "TopStack": ("Width", "Height", "XOff", "YOff"),
    "BottomStack": ("Width", "Height", "XOff", "YOff"),
    "InnerStack": ("Width", "Height", "XOff", "YOff"),
    "Terminal": ("X", "Y", "Width", "Height"),
    "Item": ("X1", "Y1", "X2", "Y2"),
    "MaskPaste": ("CustomSwell", "CustomShrink"),
    "RefDesMarking": ("X", "Y"),
    "NameMarking": ("X", "Y"),
    "ValueMarking": ("X", "Y"),
    "ManufacturerMarking": ("X", "Y"),
    "DatasheetMarking": ("X", "Y"),
}


@dataclass(frozen=True, slots=True)
class CatalogLocation:
    root: Path
    library_root: Path
    database: Path


def _catalog_location(diptrace_root: str | None) -> CatalogLocation:
    try:
        if diptrace_root:
            installation = validate_diptrace_directory(Path(diptrace_root))
        else:
            installations = detect_diptrace_installations()
            if not installations:
                raise CapabilityUnavailableError(
                    "DipTrace installation was not found; pass diptrace_root"
                )
            installation = installations[0]
    except ConfiguratorError as exc:
        raise CapabilityUnavailableError(str(exc)) from exc
    root = installation.root
    library_root = root / "Lib"
    candidates = [root / "Data_Unicode" / "compat.db"]
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        candidates.append(Path(program_data) / "DipTrace" / "Data_Unicode" / "compat.db")
    if len(root.parents) >= 2:
        candidates.append(
            root.parents[1] / "ProgramData" / "DipTrace" / "Data_Unicode" / "compat.db"
        )
    database = next((candidate for candidate in candidates if candidate.is_file()), None)
    if not library_root.is_dir() or database is None:
        raise CapabilityUnavailableError("DipTrace built-in library catalog is unavailable")
    return CatalogLocation(root, library_root.resolve(), database.resolve())


def _connect(location: CatalogLocation) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{location.database.as_uri()}?mode=ro&immutable=1",
            uri=True,
            timeout=1.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as exc:
        raise CapabilityUnavailableError("DipTrace catalog cannot be opened read-only") from exc


def _like_query(query: str) -> str:
    escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _library_path(location: CatalogLocation, database_path: str) -> Path:
    return location.library_root / PureWindowsPath(database_path).name


def _catalog_item(
    location: CatalogLocation,
    kind: Literal["component", "pattern"],
    row: sqlite3.Row,
) -> dict[str, Any]:
    prefix = "builtin-component" if kind == "component" else "builtin-pattern"
    library = _library_path(location, str(row["library_file"]))
    return {
        "catalog_id": f"{prefix}:{row['uid32']}:{row['number']}",
        "kind": kind,
        "name": row["cname"] or (row["cpattern"] if kind == "pattern" else "") or "",
        "value": row["cvalue"] or "",
        "refdes": row["clab"] or "",
        "pattern": row["cpattern"] or "",
        "manufacturer": row["cmanufacturer"] or "",
        "datasheet": row["cdatasheet"] or "",
        "supplier": row["csupplier"] or "",
        "mounting": row["cmounting"] or "",
        "description": row["cdescription"] or "",
        "category": row["category"] or "",
        "library_name": row["library_name"] or "",
        "library_file": str(library),
        "library_available": library.is_file(),
        "library_uid32": int(row["uid32"]),
        "library_index": int(row["number"]),
    }


def query_catalog(
    diptrace_root: str | None,
    kind: CatalogKind,
    query: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    validate_page(offset, limit)
    if kind not in {"component", "pattern", "library"}:
        raise DocumentError("Built-in catalog kind must be component, pattern, or library")
    location = _catalog_location(diptrace_root)
    normalized = (query or "").strip()
    if len(normalized) > 256:
        raise DocumentError("Built-in library query exceeds 256 characters")
    with _connect(location) as database:
        if kind == "library":
            parameters: list[Any] = []
            where = ""
            if normalized:
                where = (
                    " WHERE lower(coalesce(f.name,'') || ' ' || coalesce(f.caption,'')) "
                    "LIKE ? ESCAPE '\\'"
                )
                parameters.append(_like_query(normalized))
            count = int(
                database.execute(
                    f"SELECT count(*) FROM Files f{where}", parameters
                ).fetchone()[0]
            )
            rows = database.execute(
                f"""
                SELECT f.uid32, f.name library_file, f.caption library_name,
                       (SELECT count(*) FROM Components c WHERE c.file_id=f.id) component_count,
                       (SELECT count(*) FROM Patterns p WHERE p.file_id=f.id) pattern_count
                FROM Files f{where}
                ORDER BY lower(f.caption), lower(f.name)
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
            items = []
            for row in rows:
                library = _library_path(location, str(row["library_file"]))
                items.append(
                    {
                        "catalog_id": f"builtin-library:{row['uid32']}",
                        "kind": "library",
                        "name": row["library_name"] or library.stem,
                        "library_file": str(library),
                        "library_available": library.is_file(),
                        "component_count": int(row["component_count"]),
                        "pattern_count": int(row["pattern_count"]),
                    }
                )
        else:
            table = "Components" if kind == "component" else "Patterns"
            category_table = "CCategories" if kind == "component" else "PCategories"
            parameters = []
            where = ""
            rank = "0"
            if normalized:
                searchable = (
                    "coalesce(c.cname,'') || ' ' || coalesce(c.cvalue,'') || ' ' || "
                    "coalesce(c.clab,'') || ' ' || coalesce(c.cpattern,'') || ' ' || "
                    "coalesce(c.cpossiblenames,'') || ' ' || "
                    "coalesce(c.cmanufacturer,'') || ' ' || "
                    "coalesce(c.cadditional,'') || ' ' || coalesce(c.cdescription,'')"
                )
                where = f" WHERE lower({searchable}) LIKE ? ESCAPE '\\'"
                parameters.append(_like_query(normalized))
                rank = (
                    "CASE WHEN lower(c.cname)=? THEN 0 "
                    "WHEN lower(c.cname) LIKE ? THEN 1 ELSE 2 END"
                )
            count = int(
                database.execute(f"SELECT count(*) FROM {table} c{where}", parameters).fetchone()[0]
            )
            rank_parameters: list[Any] = []
            if normalized:
                rank_parameters = [normalized.casefold(), f"{normalized.casefold()}%"]
            rows = database.execute(
                f"""
                SELECT c.number, c.cname, c.cvalue, c.clab, c.cpattern,
                       c.cmanufacturer, c.cdatasheet, c.csupplier, c.cmounting,
                       c.cdescription, f.uid32, f.name library_file,
                       f.caption library_name, cat.name category
                FROM {table} c
                JOIN Files f ON f.id=c.file_id
                LEFT JOIN {category_table} cat ON cat.id=c.category_id
                {where}
                ORDER BY {rank}, lower(c.cname), f.uid32, c.number
                LIMIT ? OFFSET ?
                """,
                [*parameters, *rank_parameters, limit, offset],
            ).fetchall()
            items = [_catalog_item(location, kind, row) for row in rows]
    return {
        "ok": True,
        "document": None,
        "result": {
            "kind": kind,
            "query": normalized or None,
            "matched_count": count,
            "offset": offset,
            "limit": limit,
            "items": items,
            "catalog_database": str(location.database),
            "read_only": True,
            "native_library_mutation": False,
        },
        "warnings": [],
        "limitations": [],
        "resources": [],
        "transaction": None,
        "job": None,
    }


def _component_row(location: CatalogLocation, component: str) -> dict[str, Any]:
    match = _CATALOG_ID.fullmatch(component.strip())
    with _connect(location) as database:
        if match:
            rows = database.execute(
                """
                SELECT c.number, c.cname, c.cvalue, c.clab, c.cpattern,
                       c.cmanufacturer, c.cdatasheet, c.csupplier, c.cmounting,
                       c.cdescription, f.uid32, f.name library_file,
                       f.caption library_name, cat.name category
                FROM Components c JOIN Files f ON f.id=c.file_id
                LEFT JOIN CCategories cat ON cat.id=c.category_id
                WHERE f.uid32=? AND c.number=?
                """,
                (int(match.group(1)), int(match.group(2))),
            ).fetchall()
        else:
            rows = database.execute(
                """
                SELECT c.number, c.cname, c.cvalue, c.clab, c.cpattern,
                       c.cmanufacturer, c.cdatasheet, c.csupplier, c.cmounting,
                       c.cdescription, f.uid32, f.name library_file,
                       f.caption library_name, cat.name category
                FROM Components c JOIN Files f ON f.id=c.file_id
                LEFT JOIN CCategories cat ON cat.id=c.category_id
                WHERE lower(c.cname)=lower(?) ORDER BY f.uid32, c.number LIMIT 11
                """,
                (component.strip(),),
            ).fetchall()
    if not rows:
        raise ObjectNotFoundError(f"Built-in component was not found: {component}")
    if len(rows) != 1:
        raise AmbiguousSelectorError(
            f"Built-in component name is ambiguous: {component}",
            object_ids=[
                f"builtin-component:{row['uid32']}:{row['number']}" for row in rows[:10]
            ],
        )
    return _catalog_item(location, "component", rows[0])


def _next_numeric_id(elements: list[ET.Element]) -> int:
    values = [int(value) for item in elements if (value := item.get("Id", "")).isdigit()]
    return max(values, default=-1) + 1


def _next_style(prefix: str, existing: set[str], start: int) -> tuple[str, int]:
    while f"{prefix}{start}".casefold() in existing:
        start += 1
    style = f"{prefix}{start}"
    existing.add(style.casefold())
    return style, start + 1


def _convert_library_units(
    elements: list[ET.Element], source_units: str, target_units: str
) -> None:
    if source_units.casefold() == target_units.casefold():
        return

    def convert(element: ET.Element) -> None:
        if element.tag == "Model3D":
            return
        for attribute in _GEOMETRY_ATTRIBUTES.get(element.tag, ()):
            raw = element.get(attribute)
            if raw is None:
                continue
            try:
                converted = from_mm(to_mm(float(raw), source_units), target_units)
            except ValueError as exc:
                raise DocumentError(
                    f"Invalid {attribute} geometry in built-in <{element.tag}>"
                ) from exc
            element.set(attribute, f"{converted:.12g}")
        for child in element:
            convert(child)

    for item in elements:
        convert(item)


def _component_definitions(
    source: DipTraceDocument,
    target: DipTraceDocument,
    row: dict[str, Any],
) -> dict[str, Any]:
    if source.source_type != "DipTrace-ComponentLibrary":
        raise DocumentError("Component Editor export is not a component library")
    if target.kind != "schematic":
        raise DocumentError("Built-in components can be placed only in schematics")
    source_components = source.root.findall("./Components/Component")
    index = int(row["library_index"])
    if index >= len(source_components):
        raise DocumentError("DipTrace catalog index is outside the exported library")
    component = ET.fromstring(ET.tostring(source_components[index], encoding="unicode"))
    part = component.find("./Part[@Id='0']")
    if part is None:
        part = component.find("./Part")
    if part is None or (part.findtext("./Name") or "").casefold() != str(row["name"]).casefold():
        raise DocumentError("DipTrace catalog entry does not match the exported component")

    target_library = target.root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    if target_library is None:
        raise DocumentError("Schematic has no embedded component library")
    target_components = target_library.findall("./Components/Component")
    component_id = _next_numeric_id(target_components)
    component_styles = {
        item.get("ComponentStyle", "").casefold() for item in target_components
    }
    component_style, _ = _next_style("CompType", component_styles, component_id)
    component.set("Id", str(component_id))
    component.set("ComponentStyle", component_style)

    source_pattern_library = source.root.find("./Library[@Type='DipTrace-PatternLibrary']")
    target_pattern_library = target_library.find("./Library[@Type='DipTrace-PatternLibrary']")
    source_patterns = (
        source_pattern_library.findall("./Patterns/Pattern")
        if source_pattern_library is not None
        else []
    )
    source_patterns_by_style = {
        item.get("PatternStyle", "").casefold(): item
        for item in source_patterns
        if item.get("PatternStyle")
    }
    target_patterns = (
        target_pattern_library.findall("./Patterns/Pattern")
        if target_pattern_library is not None
        else []
    )
    pattern_styles = {item.get("PatternStyle", "").casefold() for item in target_patterns}
    next_pattern_id = _next_numeric_id(target_patterns)
    pattern_mapping: dict[str, str] = {}
    cloned_patterns: list[ET.Element] = []
    for pattern_ref in component.findall("./Part/Pattern"):
        source_style = pattern_ref.get("Style", "")
        key = source_style.casefold()
        if not source_style or key in pattern_mapping:
            continue
        source_pattern = source_patterns_by_style.get(key)
        if source_pattern is None:
            raise DocumentError(f"Attached built-in pattern was not exported: {source_style}")
        new_style, next_pattern_id = _next_style(
            "PatType", pattern_styles, next_pattern_id
        )
        cloned = ET.fromstring(ET.tostring(source_pattern, encoding="unicode"))
        cloned.set("Id", str(next_pattern_id - 1))
        cloned.set("PatternStyle", new_style)
        pattern_mapping[key] = new_style
        cloned_patterns.append(cloned)
    for pattern_ref in component.findall("./Part/Pattern"):
        key = pattern_ref.get("Style", "").casefold()
        if key in pattern_mapping:
            pattern_ref.set("Style", pattern_mapping[key])

    source_pad_styles = (
        source_pattern_library.findall("./PadStyles/PadStyle")
        if source_pattern_library is not None
        else []
    )
    source_pad_styles_by_name = {
        item.get("Name", "").casefold(): item
        for item in source_pad_styles
        if item.get("Name")
    }
    target_pad_styles = (
        target_pattern_library.findall("./PadStyles/PadStyle")
        if target_pattern_library is not None
        else []
    )
    pad_names = {item.get("Name", "").casefold() for item in target_pad_styles}
    pad_mapping: dict[str, str] = {}
    cloned_pad_styles: list[ET.Element] = []
    next_pad = 0
    for pattern in cloned_patterns:
        for element in pattern.iter():
            source_name = element.get("Style", "")
            key = source_name.casefold()
            if key not in source_pad_styles_by_name or key in pad_mapping:
                continue
            new_name, next_pad = _next_style("PadT", pad_names, next_pad)
            cloned = ET.fromstring(
                ET.tostring(source_pad_styles_by_name[key], encoding="unicode")
            )
            cloned.set("Name", new_name)
            pad_mapping[key] = new_name
            cloned_pad_styles.append(cloned)
    for pattern in cloned_patterns:
        for element in pattern.iter():
            key = element.get("Style", "").casefold()
            if key in pad_mapping:
                element.set("Style", pad_mapping[key])

    _convert_library_units(
        [component, *cloned_patterns, *cloned_pad_styles], source.units, target.units
    )

    pins = part.findall("./Pins/Pin")
    return {
        "component_style": component_style,
        "component_xml": ET.tostring(component, encoding="unicode"),
        "pattern_xml": [ET.tostring(item, encoding="unicode") for item in cloned_patterns],
        "pad_style_xml": [ET.tostring(item, encoding="unicode") for item in cloned_pad_styles],
        "pin_count": len(pins),
        "name": part.findtext("./Name") or str(row["name"]),
    }


class BuiltinLibraryService:
    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        semantic_write: SemanticWrite,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.semantic_write = semantic_write

    def query(
        self,
        diptrace_root: str | None = None,
        kind: CatalogKind = "component",
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return query_catalog(diptrace_root, kind, query, offset, limit)

    def _exported_library(
        self,
        location: CatalogLocation,
        row: dict[str, Any],
    ) -> DipTraceDocument:
        source = Path(str(row["library_file"])).resolve(strict=True)
        if not source.is_relative_to(location.library_root):
            raise CapabilityUnavailableError("Catalog resolved outside DipTrace/Lib")
        stat = source.stat()
        key = hashlib.sha256(
            f"{source}:{stat.st_size}:{stat.st_mtime_ns}".encode()
        ).hexdigest()[:20]
        cache = self.context.settings.state_dir / "builtin-library-cache"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / f"{source.stem}-{key}.elixml"
        if not target.is_file():
            temporary = cache / f".{source.stem}-{key}-{os.getpid()}.elixml"
            temporary.unlink(missing_ok=True)
            try:
                export_component_library_xml(location.root, source, temporary)
                exported = DipTraceDocument.load(temporary, _MAX_EXPORT_BYTES)
                if exported.source_type != "DipTrace-ComponentLibrary":
                    raise DocumentError("Component Editor exported an unexpected XML type")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return DipTraceDocument.load(target, _MAX_EXPORT_BYTES)

    def place_component(
        self,
        component: str,
        refdes: str,
        x: float,
        y: float,
        *,
        value: str | None = None,
        sheet: int = 0,
        angle_deg: float = 0.0,
        path: str | None = None,
        diptrace_root: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        location = _catalog_location(diptrace_root)
        row = _component_row(location, component)
        source = self._exported_library(location, row)
        target, _target = self.gateway.load(path)
        definitions = _component_definitions(source, target, row)
        operation = PlacePartOperation.model_validate(
            {
                "component_style": definitions["component_style"],
                "refdes": refdes,
                "x": x,
                "y": y,
                "pin_count": definitions["pin_count"],
                "name": definitions["name"],
                "value": row["value"] if value is None else value,
                "sheet": sheet,
                "angle_deg": angle_deg,
                "library_component_xml": definitions["component_xml"],
                "library_pattern_xml": definitions["pattern_xml"],
                "library_pad_style_xml": definitions["pad_style_xml"],
            }
        )
        return self.semantic_write(operation, path, dry_run, expected_sha256, None)
