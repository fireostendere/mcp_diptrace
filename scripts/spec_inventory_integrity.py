"""Integrity checks for the generated DipTrace specification inventory.

The coverage report is meaningful only when its upstream inventory was built
from the reviewed specification sources and their committed extracted-text
intermediates.  Keep these checks independent of the extractor so every
consumer can reject a truncated or substituted inventory before using it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA_VERSION = "diptrace-spec-inventory-v1"
EXTRACTED_TEXT_SCHEMA_VERSION = "diptrace-extracted-text-v1"
EXTRACTION_ENGINE = {"name": "pypdf", "version": "6.14.2"}
MIN_ELEMENT_COUNT = 250
MIN_ATTRIBUTE_COUNT = 500

_XML_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTRIBUTE_TYPES = frozenset({"Int", "Real", "Text", "Bool"})
_ATTRIBUTE_UNITS = frozenset(
    {"unknown", "document_units", "radians", "degrees"}
)


@dataclass(frozen=True)
class SourceManifest:
    """Pinned source and extracted-text metadata reviewed in the repository."""

    file: str
    url: str
    sha256: str
    pages: int
    size_bytes: int
    extracted_text_file: str
    extracted_text_sha256: str


SOURCE_MANIFESTS = (
    SourceManifest(
        file="DipTraceXML_Pcb_En.pdf",
        url="https://diptrace.com/books/DipTraceXML_Pcb_En.pdf",
        sha256="eab8d7f3a56ed8992f5b4a99ecfd731b1cc5c62915089d41dc954890ba4d2ece",
        pages=85,
        size_bytes=501750,
        extracted_text_file=(
            "reference/diptrace-xml/extracted_text/"
            "DipTraceXML_Pcb_En.pages.json"
        ),
        extracted_text_sha256=(
            "45959e1937d6b04a903a0fe2d863fdfdcfe32dd4141734458aeab4f1ef78207f"
        ),
    ),
    SourceManifest(
        file="DipTraceXML_Schematic_En.pdf",
        url="https://diptrace.com/books/DipTraceXML_Schematic_En.pdf",
        sha256="bd0ce42cff05b74614a480b4318d47acad946da0cc1dbf80f1fa3beef2a84bc8",
        pages=48,
        size_bytes=374896,
        extracted_text_file=(
            "reference/diptrace-xml/extracted_text/"
            "DipTraceXML_Schematic_En.pages.json"
        ),
        extracted_text_sha256=(
            "ce46d5b23b0ed14bb1685e54c95b04e803532ce87855c2eb74ab7a2d4145efb1"
        ),
    ),
    SourceManifest(
        file="DipTrace_Plugins.pdf",
        url="https://diptrace.com/books/DipTrace_Plugins.pdf",
        sha256="add1f39ac14062e8b086db2bdcf40d11398f1b8e01867fbffe1fc1ae7c26d0f0",
        pages=8,
        size_bytes=112751,
        extracted_text_file=(
            "reference/diptrace-xml/extracted_text/"
            "DipTrace_Plugins.pages.json"
        ),
        extracted_text_sha256=(
            "92a820fb60566ab5f3c5321e2422e369f52c9cfcd459a944a4c4675c30ea1e47"
        ),
    ),
)

_SOURCE_BY_FILE = {source.file: source for source in SOURCE_MANIFESTS}

_ROOT_FIELDS = frozenset({"schema_version", "sources", "elements"})
_SOURCE_REQUIRED_FIELDS = frozenset(
    {
        "file",
        "url",
        "sha256",
        "pages",
        "document_format_version",
        "published",
        "size_bytes",
        "extracted_text_file",
        "extracted_text_sha256",
        "extraction_engine",
    }
)
_SOURCE_OPTIONAL_FIELDS = frozenset({"note"})
_ELEMENT_FIELDS = frozenset(
    {"documents", "pages", "attributes", "text_content", "children"}
)
_ATTRIBUTE_FIELDS = frozenset(
    {"type", "description", "enum", "units", "omitted_when"}
)
_TEXT_CONTENT_FIELDS = frozenset(
    {
        "source_name",
        "type",
        "description",
        "enum",
        "units",
        "omitted_when",
        "documents",
        "pages",
    }
)


def _error(context: str, message: str) -> ValueError:
    return ValueError(f"{context}: {message}")


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise _error(context, "expected an object with string keys")
    return value


def _list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(context, "expected a list")
    return value


def _check_fields(
    value: dict[str, Any],
    *,
    required: frozenset[str],
    context: str,
    optional: frozenset[str] = frozenset(),
) -> None:
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        raise _error(context, f"missing fields {sorted(missing)}")
    if extra:
        raise _error(context, f"unexpected fields {sorted(extra)}")


def _nonempty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(context, "expected a non-empty string")
    return value


def _positive_int(value: object, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise _error(context, "expected a positive integer")
    return value


def _unique_strings(
    value: object,
    context: str,
    *,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    items = _list(value, context)
    if not items:
        raise _error(context, "must not be empty")
    if not all(isinstance(item, str) and item for item in items):
        raise _error(context, "must contain only non-empty strings")
    if len(items) != len(set(items)):
        raise _error(context, "contains duplicate values")
    if allowed is not None:
        unexpected = set(items) - allowed
        if unexpected:
            raise _error(context, f"contains unexpected values {sorted(unexpected)}")
    return items


def _unique_pages(value: object, context: str) -> list[int]:
    pages = _list(value, context)
    if not pages:
        raise _error(context, "must not be empty")
    if any(type(page) is not int or page <= 0 for page in pages):
        raise _error(context, "must contain only positive integer page numbers")
    if pages != sorted(set(pages)):
        raise _error(context, "must contain sorted, unique page numbers")
    return pages


def _validate_attribute_metadata(
    value: object,
    context: str,
    *,
    allow_alternatives: bool,
) -> None:
    metadata = _mapping(value, context)
    optional = frozenset({"alternatives"}) if allow_alternatives else frozenset()
    _check_fields(
        metadata,
        required=_ATTRIBUTE_FIELDS,
        optional=optional,
        context=context,
    )

    attr_type = metadata["type"]
    if not isinstance(attr_type, str) or attr_type not in _ATTRIBUTE_TYPES:
        raise _error(context, f"unsupported type {attr_type!r}")
    _nonempty_string(metadata["description"], f"{context}.description")

    enum = metadata["enum"]
    if enum is not None:
        _unique_strings(enum, f"{context}.enum")

    units = metadata["units"]
    if not isinstance(units, str) or units not in _ATTRIBUTE_UNITS:
        raise _error(context, f"unsupported units {units!r}")

    omitted_when = metadata["omitted_when"]
    if omitted_when is not None:
        _nonempty_string(omitted_when, f"{context}.omitted_when")

    alternatives = metadata.get("alternatives")
    if alternatives is None:
        return
    alternatives_list = _list(alternatives, f"{context}.alternatives")
    if not alternatives_list:
        raise _error(f"{context}.alternatives", "must not be empty")
    serialized: list[str] = []
    for index, alternative in enumerate(alternatives_list):
        alternative_context = f"{context}.alternatives[{index}]"
        _validate_attribute_metadata(
            alternative,
            alternative_context,
            allow_alternatives=False,
        )
        serialized.append(
            json.dumps(alternative, sort_keys=True, ensure_ascii=False)
        )
    if len(serialized) != len(set(serialized)):
        raise _error(f"{context}.alternatives", "contains duplicate definitions")


def _validate_bundle(
    repository_root: Path,
    manifest: SourceManifest,
) -> None:
    bundle_path = repository_root / manifest.extracted_text_file
    if not bundle_path.is_file():
        raise _error(
            f"source {manifest.file}",
            f"extracted-text bundle does not exist: {manifest.extracted_text_file}",
        )
    raw = bundle_path.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != manifest.extracted_text_sha256:
        raise _error(
            f"source {manifest.file}",
            "extracted-text bundle SHA-256 does not match the reviewed manifest",
        )
    try:
        bundle = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(
            f"source {manifest.file}",
            f"invalid extracted-text JSON: {exc}",
        ) from exc
    bundle_data = _mapping(bundle, f"bundle {manifest.extracted_text_file}")
    _check_fields(
        bundle_data,
        required=frozenset({"schema_version", "source", "extraction", "pages"}),
        context=f"bundle {manifest.extracted_text_file}",
    )
    canonical = (
        json.dumps(
            bundle_data,
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        )
        + "\n"
    ).encode()
    if raw != canonical:
        raise _error(
            f"bundle {manifest.extracted_text_file}",
            "JSON is not in canonical form",
        )
    if bundle_data["schema_version"] != EXTRACTED_TEXT_SCHEMA_VERSION:
        raise _error(
            f"bundle {manifest.extracted_text_file}",
            "unsupported schema version",
        )

    source = _mapping(
        bundle_data["source"],
        f"bundle {manifest.extracted_text_file}.source",
    )
    _check_fields(
        source,
        required=frozenset(
            {"file", "url", "sha256", "size_bytes", "page_count"}
        ),
        context=f"bundle {manifest.extracted_text_file}.source",
    )
    expected_source = {
        "file": manifest.file,
        "url": manifest.url,
        "sha256": manifest.sha256,
        "size_bytes": manifest.size_bytes,
        "page_count": manifest.pages,
    }
    if source != expected_source:
        raise _error(
            f"bundle {manifest.extracted_text_file}.source",
            "metadata does not match the reviewed source manifest",
        )

    extraction = _mapping(
        bundle_data["extraction"],
        f"bundle {manifest.extracted_text_file}.extraction",
    )
    if extraction != {
        "engine": EXTRACTION_ENGINE["name"],
        "version": EXTRACTION_ENGINE["version"],
    }:
        raise _error(
            f"bundle {manifest.extracted_text_file}.extraction",
            "metadata does not match the pinned extraction engine",
        )

    pages = _list(
        bundle_data["pages"],
        f"bundle {manifest.extracted_text_file}.pages",
    )
    if len(pages) != manifest.pages:
        raise _error(
            f"bundle {manifest.extracted_text_file}.pages",
            f"expected {manifest.pages} pages, found {len(pages)}",
        )
    for index, page_value in enumerate(pages, start=1):
        page_context = f"bundle {manifest.extracted_text_file}.pages[{index - 1}]"
        page = _mapping(page_value, page_context)
        _check_fields(
            page,
            required=frozenset({"page", "text"}),
            context=page_context,
        )
        if page["page"] != index:
            raise _error(page_context, f"expected page number {index}")
        if not isinstance(page["text"], str):
            raise _error(page_context, "text must be a string")


def _validate_source(
    value: object,
    manifest: SourceManifest,
    repository_root: Path,
) -> None:
    context = f"source {manifest.file}"
    source = _mapping(value, context)
    _check_fields(
        source,
        required=_SOURCE_REQUIRED_FIELDS,
        optional=_SOURCE_OPTIONAL_FIELDS,
        context=context,
    )
    expected_values: dict[str, object] = {
        "file": manifest.file,
        "url": manifest.url,
        "sha256": manifest.sha256,
        "pages": manifest.pages,
        "size_bytes": manifest.size_bytes,
        "extracted_text_file": manifest.extracted_text_file,
        "extracted_text_sha256": manifest.extracted_text_sha256,
        "extraction_engine": EXTRACTION_ENGINE,
        "document_format_version": "4.3.0.3",
        "published": "2023",
    }
    for field, expected in expected_values.items():
        if source[field] != expected:
            raise _error(
                context,
                f"{field} does not match the reviewed manifest",
            )
    if not _SHA256_RE.fullmatch(source["sha256"]):
        raise _error(context, "sha256 is not a lowercase SHA-256 digest")
    if not _SHA256_RE.fullmatch(source["extracted_text_sha256"]):
        raise _error(
            context,
            "extracted_text_sha256 is not a lowercase SHA-256 digest",
        )
    if "note" in source:
        _nonempty_string(source["note"], f"{context}.note")
    _validate_bundle(repository_root, manifest)


def _validate_sentinels(elements: dict[str, Any]) -> None:
    units_description = (
        "Measurement units of dimensions in the file: "
        "mm – millimetres; inch – inches; mil – mils."
    )
    expected_units = {
        "type": "Text",
        "description": units_description,
        "enum": ["mm", "inch", "mil"],
        "units": "document_units",
        "omitted_when": None,
    }
    for element_name in ("Source", "Library"):
        element = _mapping(
            elements.get(element_name),
            f"elements.{element_name}",
        )
        attributes = _mapping(
            element.get("attributes"),
            f"elements.{element_name}.attributes",
        )
        if attributes.get("Units") != expected_units:
            raise _error(
                f"elements.{element_name}.attributes.Units",
                "does not match the documented measurement-units definition",
            )

    expected_angle_units = {
        ("Component", "Angle"): "unknown",
        ("Shape", "Angle"): "radians",
        ("Table", "Orientation"): "degrees",
    }
    for (element_name, attribute_name), expected in expected_angle_units.items():
        element = _mapping(
            elements.get(element_name),
            f"elements.{element_name}",
        )
        attributes = _mapping(
            element.get("attributes"),
            f"elements.{element_name}.attributes",
        )
        attribute = _mapping(
            attributes.get(attribute_name),
            f"elements.{element_name}.attributes.{attribute_name}",
        )
        if attribute.get("units") != expected:
            raise _error(
                f"elements.{element_name}.attributes.{attribute_name}",
                f"expected units {expected!r}",
            )


def validate_inventory(
    data: object,
    repository_root: Path = Path("."),
) -> None:
    """Raise ``ValueError`` unless *data* is a complete reviewed inventory."""

    inventory = _mapping(data, "inventory")
    _check_fields(
        inventory,
        required=_ROOT_FIELDS,
        context="inventory",
    )
    if inventory["schema_version"] != INVENTORY_SCHEMA_VERSION:
        raise _error("inventory", "unsupported schema version")

    source_values = _list(inventory["sources"], "inventory.sources")
    if len(source_values) != len(SOURCE_MANIFESTS):
        raise _error(
            "inventory.sources",
            f"expected exactly {len(SOURCE_MANIFESTS)} sources",
        )
    sources_by_file: dict[str, object] = {}
    for index, source_value in enumerate(source_values):
        source = _mapping(source_value, f"inventory.sources[{index}]")
        file_name = source.get("file")
        if not isinstance(file_name, str):
            raise _error(f"inventory.sources[{index}]", "file must be a string")
        if file_name in sources_by_file:
            raise _error("inventory.sources", f"duplicate source {file_name!r}")
        sources_by_file[file_name] = source_value
    if set(sources_by_file) != set(_SOURCE_BY_FILE):
        raise _error(
            "inventory.sources",
            "source files do not match the reviewed manifest",
        )
    for manifest in SOURCE_MANIFESTS:
        _validate_source(
            sources_by_file[manifest.file],
            manifest,
            repository_root,
        )

    elements = _mapping(inventory["elements"], "inventory.elements")
    if len(elements) < MIN_ELEMENT_COUNT:
        raise _error(
            "inventory.elements",
            f"expected at least {MIN_ELEMENT_COUNT}, found {len(elements)}",
        )

    attribute_count = 0
    for element_name, element_value in elements.items():
        element_context = f"elements.{element_name}"
        if not _XML_NAME_RE.fullmatch(element_name):
            raise _error(element_context, "invalid XML element name")
        element = _mapping(element_value, element_context)
        _check_fields(
            element,
            required=_ELEMENT_FIELDS,
            context=element_context,
        )
        _unique_strings(
            element["documents"],
            f"{element_context}.documents",
            allowed=frozenset({"pcb", "schematic"}),
        )
        _unique_pages(element["pages"], f"{element_context}.pages")

        attributes = _mapping(
            element["attributes"],
            f"{element_context}.attributes",
        )
        attribute_count += len(attributes)
        for attribute_name, attribute_value in attributes.items():
            attribute_context = (
                f"{element_context}.attributes.{attribute_name}"
            )
            if not _XML_NAME_RE.fullmatch(attribute_name):
                raise _error(attribute_context, "invalid XML attribute name")
            _validate_attribute_metadata(
                attribute_value,
                attribute_context,
                allow_alternatives=True,
            )

        text_content = _list(
            element["text_content"],
            f"{element_context}.text_content",
        )
        for index, text_value in enumerate(text_content):
            text_context = f"{element_context}.text_content[{index}]"
            text = _mapping(text_value, text_context)
            _check_fields(
                text,
                required=_TEXT_CONTENT_FIELDS,
                context=text_context,
            )
            source_name = _nonempty_string(
                text["source_name"],
                f"{text_context}.source_name",
            )
            if not _XML_NAME_RE.fullmatch(source_name):
                raise _error(
                    f"{text_context}.source_name",
                    "invalid XML name",
                )
            _validate_attribute_metadata(
                {
                    field: text[field]
                    for field in _ATTRIBUTE_FIELDS
                },
                text_context,
                allow_alternatives=False,
            )
            _unique_strings(
                text["documents"],
                f"{text_context}.documents",
                allowed=frozenset({"pcb", "schematic"}),
            )
            _unique_pages(text["pages"], f"{text_context}.pages")

        children = element["children"]
        child_names = _list(children, f"{element_context}.children")
        if not all(
            isinstance(child_name, str)
            and _XML_NAME_RE.fullmatch(child_name)
            for child_name in child_names
        ):
            raise _error(
                f"{element_context}.children",
                "must contain only valid XML element names",
            )
        if len(child_names) != len(set(child_names)):
            raise _error(
                f"{element_context}.children",
                "contains duplicate element names",
            )

    if attribute_count < MIN_ATTRIBUTE_COUNT:
        raise _error(
            "inventory.elements",
            f"expected at least {MIN_ATTRIBUTE_COUNT} attributes, "
            f"found {attribute_count}",
        )

    for element_name, element_value in elements.items():
        element = _mapping(element_value, f"elements.{element_name}")
        for child_name in _list(
            element["children"],
            f"elements.{element_name}.children",
        ):
            if child_name not in elements:
                raise _error(
                    f"elements.{element_name}.children",
                    f"references unknown element {child_name!r}",
                )

    _validate_sentinels(elements)
