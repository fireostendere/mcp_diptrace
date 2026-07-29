from __future__ import annotations

import difflib
import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol, cast
from xml.parsers import expat

from .errors import DocumentError, EditError

EditOperation = Literal[
    "set_text",
    "set_attribute",
    "remove_attribute",
    "append_xml",
    "replace_xml",
    "delete_element",
]

_FORBIDDEN_XML = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_FORBIDDEN_XML_TEXT = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)
_XML_DECLARATION_ENCODING = re.compile(
    rb"^\s*<\?xml\b[^>]*?\bencoding\s*=\s*([\"'])([^\"']+)\1",
    re.IGNORECASE,
)
_XML_DECLARATION_ENCODING_TEXT = re.compile(
    r"^\s*<\?xml\b[^>]*?\bencoding\s*=\s*([\"'])([^\"']+)\1",
    re.IGNORECASE,
)
_INVALID_XML_10_CHARACTER = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]"
)
_ALLOWED_XML_ENCODINGS = frozenset(
    {
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
        "us-ascii",
        "iso-8859-1",
    }
)
_XML_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xff\xfe", "utf-16-le"),
)
_XML_BYTE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x00\x00\x00<", "utf-32-be"),
    (b"<\x00\x00\x00", "utf-32-le"),
    (b"\x00<\x00?", "utf-16-be"),
    (b"<\x00?\x00", "utf-16-le"),
)
ForbiddenXmlContext = Literal["document", "fragment", "pattern_definition"]
_FORBIDDEN_XML_MESSAGES: dict[ForbiddenXmlContext, str] = {
    "document": "DTD and ENTITY declarations are not allowed",
    "fragment": "DTD and ENTITY declarations are not allowed in XML fragments",
    "pattern_definition": "DTD and ENTITY declarations are forbidden in pattern definitions",
}
_XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class _XmlEncoding:
    codec: str
    bom: bytes = b""
    declared_name: str | None = None


def _canonical_encoding_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _declaration_from_prefix(data: bytes, codec: str, bom: bytes) -> str | None:
    body = data[len(bom) :] if bom and data.startswith(bom) else data
    unit_size = 4 if codec.startswith("utf-32") else 2 if codec.startswith("utf-16") else 1
    prefix_size = min(len(body), 4096)
    prefix_size -= prefix_size % unit_size
    try:
        prefix = body[:prefix_size].decode(codec, errors="strict")
    except (LookupError, UnicodeError, ValueError):
        return None
    match = _XML_DECLARATION_ENCODING_TEXT.search(prefix)
    return match.group(2) if match is not None else None


def _declaration_matches_codec(declared: str, codec: str) -> bool:
    normalized = _canonical_encoding_name(declared)
    if normalized == "utf-16":
        return codec in {"utf-16-le", "utf-16-be"}
    if normalized == "utf-32":
        return codec in {"utf-32-le", "utf-32-be"}
    if normalized == "utf-8-sig":
        return codec == "utf-8"
    return normalized == codec


def _expat_encoding_hint(codec: str) -> str | None:
    """Use Expat's generic multibyte names without trusting an XML declaration."""
    if codec.startswith("utf-16"):
        return "utf-16"
    if codec.startswith("utf-32"):
        return "utf-32"
    return None


def _expat_byte_encoding_hint(data: bytes) -> str | None:
    for bom, codec in _XML_BOMS:
        if data.startswith(bom):
            return _expat_encoding_hint(codec)
    for signature, codec in _XML_BYTE_SIGNATURES:
        if data.startswith(signature):
            return _expat_encoding_hint(codec)
    return None


def _detect_xml_encoding(data: bytes) -> _XmlEncoding:
    """Detect the source codec without trusting an arbitrary declaration codec."""

    for bom, codec in _XML_BOMS:
        if not data.startswith(bom):
            continue
        declared = _declaration_from_prefix(data, codec, bom)
        if declared is not None:
            normalized = _canonical_encoding_name(declared)
            if normalized not in _ALLOWED_XML_ENCODINGS:
                raise DocumentError(f"Unsupported XML encoding declaration: {declared!r}")
            if not _declaration_matches_codec(declared, codec):
                raise DocumentError(
                    f"XML declaration encoding {declared!r} conflicts with the byte-order mark"
                )
        return _XmlEncoding(codec=codec, bom=bom, declared_name=declared)

    for signature, codec in _XML_BYTE_SIGNATURES:
        if not data.startswith(signature):
            continue
        declared = _declaration_from_prefix(data, codec, b"")
        if declared is not None:
            normalized = _canonical_encoding_name(declared)
            if normalized not in _ALLOWED_XML_ENCODINGS:
                raise DocumentError(f"Unsupported XML encoding declaration: {declared!r}")
            if not _declaration_matches_codec(declared, codec):
                raise DocumentError(
                    f"XML declaration encoding {declared!r} conflicts with the byte order"
                )
        return _XmlEncoding(codec=codec, declared_name=declared)

    declaration = _XML_DECLARATION_ENCODING.search(data[:4096])
    if declaration is None:
        return _XmlEncoding(codec="utf-8")
    try:
        declared = declaration.group(2).decode("ascii")
    except (LookupError, UnicodeError, ValueError) as exc:
        raise DocumentError("XML encoding declaration must use an ASCII codec name") from exc
    normalized = _canonical_encoding_name(declared)
    if normalized not in _ALLOWED_XML_ENCODINGS:
        raise DocumentError(f"Unsupported XML encoding declaration: {declared!r}")
    if normalized in {"utf-16", "utf-32"}:
        raise DocumentError(
            f"XML encoding {declared!r} requires a BOM or an encoded byte-order signature"
        )
    codec = "utf-8" if normalized == "utf-8-sig" else normalized
    return _XmlEncoding(codec=codec, declared_name=declared)
