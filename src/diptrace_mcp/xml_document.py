from __future__ import annotations

import copy
import difflib
import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _parse_root(data: bytes) -> ET.Element:
    if _FORBIDDEN_XML.search(data):
        raise DocumentError("DTD and ENTITY declarations are not allowed")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        return ET.fromstring(data, parser=parser)
    except ET.ParseError as exc:
        raise DocumentError(f"Invalid XML: {exc}") from exc


@dataclass(frozen=True)
class XmlEdit:
    operation: EditOperation
    xpath: str
    value: str | None = None
    attribute: str | None = None
    expected_matches: int = 1


@dataclass
class DipTraceDocument:
    path: Path
    root: ET.Element
    raw_bytes: bytes

    @classmethod
    def load(cls, path: Path, max_bytes: int) -> DipTraceDocument:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise DocumentError(f"Cannot stat document: {path}") from exc
        if size > max_bytes:
            raise DocumentError(f"Document is larger than {max_bytes} bytes: {path}")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise DocumentError(f"Cannot read document: {path}") from exc
        return cls.from_bytes(path, data)

    @classmethod
    def from_bytes(cls, path: Path, data: bytes) -> DipTraceDocument:
        root = _parse_root(data)
        if root.tag != "Source":
            raise DocumentError(f"Expected <Source> root, got <{root.tag}>")
        source_type = root.get("Type", "")
        if not source_type.startswith("DipTrace-"):
            raise DocumentError(f"Unsupported DipTrace XML type: {source_type or '<empty>'}")
        return cls(path=path, root=root, raw_bytes=data)

    @property
    def source_type(self) -> str:
        return self.root.get("Type", "")

    @property
    def version(self) -> str:
        return self.root.get("Version", "")

    @property
    def units(self) -> str:
        return self.root.get("Units", "")

    @property
    def kind(self) -> str:
        lowered = self.source_type.lower()
        if lowered == "diptrace-pcb":
            return "pcb"
        if lowered == "diptrace-schematic":
            return "schematic"
        if "componentlibrary" in lowered:
            return "component_library"
        if "patternlibrary" in lowered:
            return "pattern_library"
        return "generic"

    @property
    def container(self) -> ET.Element:
        if self.kind == "pcb":
            container = self.root.find("./Board")
        elif self.kind == "schematic":
            container = self.root.find("./Schematic")
        else:
            container = self.root
        if container is None:
            raise DocumentError(f"Missing main section for {self.source_type}")
        return container

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.raw_bytes)

    def serialize(self) -> bytes:
        return ET.tostring(
            self.root,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=True,
        )

    def _normalize_xpath(self, xpath: str) -> str:
        value = xpath.strip()
        if not value:
            raise EditError("XPath cannot be empty")
        if len(value) > 512:
            raise EditError("XPath is longer than 512 characters")
        if value in {".", "/", "/Source", "Source"}:
            return "."
        if value.startswith("/Source/"):
            return f"./{value[len('/Source/'):]}"
        if value.startswith("Source/"):
            return f"./{value[len('Source/'):]}"
        if value.startswith("//"):
            return f".{value}"
        if value.startswith("/"):
            raise EditError("Absolute XPath must start with /Source")
        if not value.startswith("."):
            return f"./{value}"
        return value

    def findall(self, xpath: str) -> list[ET.Element]:
        normalized = self._normalize_xpath(xpath)
        if normalized == ".":
            return [self.root]
        try:
            return list(self.root.findall(normalized))
        except (KeyError, SyntaxError) as exc:
            raise EditError(f"Unsupported XPath {xpath!r}: {exc}") from exc

    def xml_fragments(self, xpath: str, max_matches: int = 25) -> list[str]:
        matches = self.findall(xpath)
        if len(matches) > max_matches:
            raise DocumentError(
                f"XPath returned {len(matches)} elements; limit is {max_matches}"
            )
        return [ET.tostring(element, encoding="unicode") for element in matches]

    def apply_edits(self, edits: list[XmlEdit]) -> tuple[bytes, list[dict[str, object]]]:
        if not edits:
            raise EditError("At least one edit is required")
        original_type = self.source_type
        previews: list[dict[str, object]] = []

        for index, edit in enumerate(edits):
            if edit.expected_matches <= 0:
                raise EditError(f"Edit {index}: expected_matches must be greater than zero")
            matches = self.findall(edit.xpath)
            if len(matches) != edit.expected_matches:
                raise EditError(
                    f"Edit {index}: XPath {edit.xpath!r} matched {len(matches)} elements, "
                    f"expected {edit.expected_matches}"
                )
            before = [_short_xml(element) for element in matches]
            self._apply_one(index, edit, matches)
            previews.append(
                {
                    "index": index,
                    "operation": edit.operation,
                    "xpath": edit.xpath,
                    "matches": len(matches),
                    "before": before,
                    "after": [_short_xml(element) for element in matches]
                    if edit.operation not in {"delete_element", "replace_xml"}
                    else [],
                }
            )

        data = self.serialize()
        validated = DipTraceDocument.from_bytes(self.path, data)
        if validated.source_type != original_type:
            raise EditError("The edit changed the DipTrace document type")
        self.raw_bytes = data
        return data, previews

    def _apply_one(self, index: int, edit: XmlEdit, matches: list[ET.Element]) -> None:
        if edit.operation == "set_text":
            if edit.value is None:
                raise EditError(f"Edit {index}: set_text requires value")
            for element in matches:
                element.text = edit.value
            return

        if edit.operation == "set_attribute":
            if not edit.attribute or edit.value is None:
                raise EditError(f"Edit {index}: set_attribute requires attribute and value")
            for element in matches:
                element.set(edit.attribute, edit.value)
            return

        if edit.operation == "remove_attribute":
            if not edit.attribute:
                raise EditError(f"Edit {index}: remove_attribute requires attribute")
            missing = [element.tag for element in matches if edit.attribute not in element.attrib]
            if missing:
                raise EditError(
                    f"Edit {index}: attribute {edit.attribute!r} is missing on "
                    f"{len(missing)} element(s)"
                )
            for element in matches:
                del element.attrib[edit.attribute]
            return

        if edit.operation == "append_xml":
            template = _parse_fragment(index, edit.value)
            for element in matches:
                element.append(copy.deepcopy(template))
            return

        parent_map = {child: parent for parent in self.root.iter() for child in parent}
        if any(element is self.root for element in matches):
            raise EditError(f"Edit {index}: replacing or deleting <Source> is forbidden")

        if edit.operation == "replace_xml":
            template = _parse_fragment(index, edit.value)
            for element in matches:
                parent = parent_map[element]
                position = list(parent).index(element)
                replacement = copy.deepcopy(template)
                replacement.tail = element.tail
                parent.remove(element)
                parent.insert(position, replacement)
            return

        if edit.operation == "delete_element":
            for element in matches:
                parent_map[element].remove(element)
            return

        raise EditError(f"Edit {index}: unsupported operation {edit.operation!r}")


def _parse_fragment(index: int, value: str | None) -> ET.Element:
    if not value:
        raise EditError(f"Edit {index}: XML fragment is required")
    wrapper = _parse_root_fragment(value.encode("utf-8"))
    children = [child for child in wrapper if isinstance(child.tag, str)]
    if len(children) != 1 or (wrapper.text and wrapper.text.strip()):
        raise EditError(f"Edit {index}: XML fragment must contain exactly one root element")
    return children[0]


def _parse_root_fragment(data: bytes) -> ET.Element:
    if _FORBIDDEN_XML.search(data):
        raise EditError("DTD and ENTITY declarations are not allowed in XML fragments")
    try:
        return ET.fromstring(b"<McpFragment>" + data + b"</McpFragment>")
    except ET.ParseError as exc:
        raise EditError(f"Invalid XML fragment: {exc}") from exc


def _short_xml(element: ET.Element, limit: int = 800) -> str:
    rendered = ET.tostring(element, encoding="unicode")
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:limit]}..."


def unified_xml_diff(before: bytes, after: bytes, max_lines: int = 200) -> str:
    before_lines = before.decode("utf-8", errors="replace").splitlines()
    after_lines = after.decode("utf-8", errors="replace").splitlines()
    lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before.xml",
            tofile="after.xml",
            lineterm="",
        )
    )
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... diff truncated after {max_lines} lines ..."]
    return "\n".join(lines)


def write_with_backup(path: Path, data: bytes, backup_dir: Path) -> Path:
    original = path.read_bytes()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = backup_dir / f"{path.name}.{stamp}.{sha256_bytes(original)[:12]}.bak"
    atomic_write_bytes(backup, original)
    atomic_write_bytes(path, data)
    return backup
