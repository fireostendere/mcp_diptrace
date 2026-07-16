from __future__ import annotations

import difflib
import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast
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
_XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")


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
class _RawElementSpan:
    name: str
    start: int
    start_tag_end: int
    parent_index: int | None
    self_closing: bool
    content_end: int = -1
    end: int = -1


@dataclass(frozen=True)
class _TreeElementState:
    element: ET.Element
    span_index: int
    tag: str
    attributes: dict[str, str]
    text: str | None
    parent_id: int | None
    child_ids: tuple[int, ...]


@dataclass(frozen=True)
class RawTreeSnapshot:
    """Capture element identity before semantic mutations for raw-preserving compilation."""

    raw_bytes: bytes
    root_id: int
    spans: tuple[_RawElementSpan, ...]
    states: dict[int, _TreeElementState]

    @classmethod
    def capture(cls, document: DipTraceDocument) -> RawTreeSnapshot:
        spans, mapping = _element_span_map(document)
        states: dict[int, _TreeElementState] = {}

        def visit(element: ET.Element, parent_id: int | None) -> None:
            element_id = id(element)
            children = tuple(
                id(child) for child in element if isinstance(child.tag, str)
            )
            states[element_id] = _TreeElementState(
                element=element,
                span_index=mapping[element_id],
                tag=element.tag,
                attributes=dict(element.attrib),
                text=element.text,
                parent_id=parent_id,
                child_ids=children,
            )
            for child in element:
                if isinstance(child.tag, str):
                    visit(child, element_id)

        visit(document.root, None)
        return cls(
            raw_bytes=document.raw_bytes,
            root_id=id(document.root),
            spans=tuple(spans),
            states=states,
        )

    def compile(self, root: ET.Element, path: Path) -> bytes:
        if id(root) != self.root_id:
            raise EditError("Semantic compiler replaced the XML root")

        current: dict[int, ET.Element] = {}
        parents: dict[int, int | None] = {}
        children: dict[int, tuple[int, ...]] = {}

        def visit(element: ET.Element, parent_id: int | None) -> None:
            element_id = id(element)
            current[element_id] = element
            parents[element_id] = parent_id
            child_ids = tuple(
                id(child) for child in element if isinstance(child.tag, str)
            )
            children[element_id] = child_ids
            for child in element:
                if isinstance(child.tag, str):
                    visit(child, element_id)

        visit(root, None)
        existing = set(self.states) & set(current)
        for element_id in existing:
            state = self.states[element_id]
            element = current[element_id]
            if element.tag != state.tag:
                raise EditError("Semantic compiler changed an existing XML element name")
            if parents[element_id] != state.parent_id:
                raise EditError("Moving existing XML elements between parents is unsupported")

        replaced: set[int] = set()
        for element_id in existing:
            state = self.states[element_id]
            span = self.spans[state.span_index]
            if span.self_closing and (
                state.text != current[element_id].text
                or state.child_ids != children[element_id]
            ):
                replaced.add(element_id)

        def has_replaced_ancestor(element_id: int, *, current_tree: bool) -> bool:
            parent_id = (
                parents.get(element_id)
                if current_tree
                else self.states[element_id].parent_id
            )
            while parent_id is not None:
                if parent_id in replaced:
                    return True
                parent_id = (
                    parents.get(parent_id)
                    if current_tree
                    else self.states[parent_id].parent_id
                )
            return False

        for parent_id in existing - replaced:
            original_survivors = tuple(
                child_id
                for child_id in self.states[parent_id].child_ids
                if child_id in current
            )
            current_existing = tuple(
                child_id
                for child_id in children[parent_id]
                if child_id in self.states
            )
            if original_survivors != current_existing:
                raise EditError("Reordering existing XML siblings is unsupported")

        replacements: list[tuple[int, int, bytes]] = []
        for element_id in sorted(
            replaced,
            key=lambda item: self.spans[self.states[item].span_index].start,
        ):
            if has_replaced_ancestor(element_id, current_tree=True):
                continue
            state = self.states[element_id]
            span = self.spans[state.span_index]
            start_tag = self.raw_bytes[span.start : span.start_tag_end]
            start_tag = _patch_start_tag(start_tag, state.attributes, current[element_id].attrib)
            rendered = _open_self_closing_tag(start_tag)
            if current[element_id].text:
                rendered += _escape_xml_text(current[element_id].text or "")
            rendered += b"".join(
                _serialize_new_element(child)
                for child in current[element_id]
                if isinstance(child.tag, str)
            )
            rendered += f"</{state.tag}>".encode()
            replacements.append((span.start, span.end, rendered))

        for element_id in existing - replaced:
            if has_replaced_ancestor(element_id, current_tree=True):
                continue
            state = self.states[element_id]
            element = current[element_id]
            span = self.spans[state.span_index]
            start_tag = self.raw_bytes[span.start : span.start_tag_end]
            patched_start_tag = _patch_start_tag(start_tag, state.attributes, element.attrib)
            if patched_start_tag != start_tag:
                replacements.append((span.start, span.start_tag_end, patched_start_tag))
            if state.text != element.text:
                direct_children = [
                    child for child in self.spans if child.parent_index == state.span_index
                ]
                text_end = direct_children[0].start if direct_children else span.content_end
                replacements.append(
                    (
                        span.start_tag_end,
                        text_end,
                        _escape_xml_text(element.text or ""),
                    )
                )

        for element_id, state in self.states.items():
            if element_id in current or has_replaced_ancestor(element_id, current_tree=False):
                continue
            deleted_parent_id = state.parent_id
            if deleted_parent_id is not None and deleted_parent_id not in current:
                continue
            span = self.spans[state.span_index]
            replacements.append((span.start, span.end, b""))

        insertions: dict[int, list[tuple[int, bytes]]] = {}
        for parent_id in existing - replaced:
            if has_replaced_ancestor(parent_id, current_tree=True):
                continue
            sibling_ids = children[parent_id]
            parent_span = self.spans[self.states[parent_id].span_index]
            for index, child_id in enumerate(sibling_ids):
                if child_id in self.states:
                    continue
                if parents[child_id] not in self.states:
                    continue
                next_existing = next(
                    (
                        candidate
                        for candidate in sibling_ids[index + 1 :]
                        if candidate in self.states
                    ),
                    None,
                )
                offset = (
                    self.spans[self.states[next_existing].span_index].start
                    if next_existing is not None
                    else parent_span.content_end
                )
                insertions.setdefault(offset, []).append(
                    (index, _serialize_new_element(current[child_id]))
                )
        for offset, values in insertions.items():
            rendered = b"".join(value for _, value in sorted(values))
            replacements.append((offset, offset, rendered))

        compiled = _apply_replacements(self.raw_bytes, replacements)
        reparsed = DipTraceDocument.from_bytes(path, compiled)
        if _semantic_tree(reparsed.root) != _semantic_tree(root):
            raise EditError(
                "Raw-preserving semantic compilation does not match the mutated XML tree"
            )
        return compiled


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
        source_type = root.get("Type", "")
        valid_root = root.tag == "Source" or (
            root.tag == "Library"
            and source_type
            in {"DipTrace-ComponentLibrary", "DipTrace-PatternLibrary"}
        )
        if not valid_root:
            raise DocumentError(f"Expected a DipTrace <Source> or <Library> root, got <{root.tag}>")
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
        return cast(
            bytes,
            ET.tostring(
                self.root,
                encoding="utf-8",
                xml_declaration=True,
                short_empty_elements=True,
            ),
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
        working = self.raw_bytes
        previews: list[dict[str, object]] = []

        for index, edit in enumerate(edits):
            if edit.expected_matches <= 0:
                raise EditError(f"Edit {index}: expected_matches must be greater than zero")
            current = DipTraceDocument.from_bytes(self.path, working)
            matches = current.findall(edit.xpath)
            if len(matches) != edit.expected_matches:
                raise EditError(
                    f"Edit {index}: XPath {edit.xpath!r} matched {len(matches)} elements, "
                    f"expected {edit.expected_matches}"
                )
            before = [_short_xml(element) for element in matches]
            working = _apply_raw_edit(current, index, edit, matches)
            updated = DipTraceDocument.from_bytes(self.path, working)
            previews.append(
                {
                    "index": index,
                    "operation": edit.operation,
                    "xpath": edit.xpath,
                    "matches": len(matches),
                    "before": before,
                    "after": (
                        [_short_xml(element) for element in updated.findall(edit.xpath)]
                        if edit.operation not in {"delete_element", "replace_xml"}
                        else []
                    ),
                }
            )

        validated = DipTraceDocument.from_bytes(self.path, working)
        if validated.source_type != original_type:
            raise EditError("The edit changed the DipTrace document type")
        self.root = validated.root
        self.raw_bytes = working
        return working, previews


def _scan_start_tag_end(data: bytes, start: int) -> int:
    quote: int | None = None
    for position in range(start + 1, len(data)):
        value = data[position]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in {ord('"'), ord("'")}:
            quote = value
        elif value == ord(">"):
            return position + 1
    raise EditError(f"Unterminated XML start tag at byte {start}")


def _raw_element_spans(data: bytes) -> list[_RawElementSpan]:
    if _FORBIDDEN_XML.search(data):
        raise EditError("DTD and ENTITY declarations are not allowed")
    spans: list[_RawElementSpan] = []
    stack: list[int] = []
    parser = expat.ParserCreate()

    def start_element(name: str, _attributes: dict[str, str]) -> None:
        start = parser.CurrentByteIndex
        start_tag_end = _scan_start_tag_end(data, start)
        start_tag = data[start:start_tag_end]
        self_closing = start_tag.rstrip().endswith(b"/>")
        parent_index = stack[-1] if stack else None
        spans.append(
            _RawElementSpan(
                name=name,
                start=start,
                start_tag_end=start_tag_end,
                parent_index=parent_index,
                self_closing=self_closing,
            )
        )
        stack.append(len(spans) - 1)

    def end_element(_name: str) -> None:
        if not stack:
            raise EditError("XML span parser encountered an unbalanced end tag")
        span = spans[stack.pop()]
        if span.self_closing:
            span.content_end = span.start_tag_end
            span.end = span.start_tag_end
            return
        closing_start = parser.CurrentByteIndex
        span.content_end = closing_start
        span.end = _scan_start_tag_end(data, closing_start)

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(data, True)
    except (expat.ExpatError, EditError) as exc:
        raise EditError(f"Cannot map XML byte spans: {exc}") from exc
    if stack or any(span.end < 0 for span in spans):
        raise EditError("XML span parser did not close every element")
    return spans


def _element_span_map(document: DipTraceDocument) -> tuple[list[_RawElementSpan], dict[int, int]]:
    spans = _raw_element_spans(document.raw_bytes)
    elements = [element for element in document.root.iter() if isinstance(element.tag, str)]
    if len(elements) != len(spans):
        raise EditError(
            "XML parser disagreement while mapping byte spans: "
            f"ElementTree={len(elements)}, Expat={len(spans)}"
        )
    mapping: dict[int, int] = {}
    for index, (element, span) in enumerate(zip(elements, spans, strict=True)):
        element_name = str(element.tag)
        if element_name != span.name:
            raise EditError(
                "XML parser disagreement while mapping byte spans: "
                f"ElementTree={element_name!r}, Expat={span.name!r}"
            )
        mapping[id(element)] = index
    return spans, mapping


def _patch_start_tag(
    start_tag: bytes,
    before: dict[str, str],
    after: dict[str, str],
) -> bytes:
    patched = start_tag
    for name in before:
        if name not in after:
            patched = _remove_raw_attribute(patched, name)
    for name, value in after.items():
        if before.get(name) != value:
            patched = _set_raw_attribute(patched, name, value)
    return patched


def _serialize_new_element(element: ET.Element) -> bytes:
    clone = deepcopy(element)
    clone.tail = None
    return cast(
        bytes,
        ET.tostring(
            clone,
            encoding="utf-8",
            short_empty_elements=True,
        ),
    )


def _semantic_tree(element: ET.Element) -> tuple[object, ...]:
    text = element.text
    normalized_text = None if text is None or not text.strip() else text
    tag = element.tag if isinstance(element.tag, str) else "#comment"
    return (
        tag,
        tuple(sorted(element.attrib.items())),
        normalized_text,
        tuple(_semantic_tree(child) for child in element),
    )


def _escape_xml_text(value: str) -> bytes:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").encode(
        "utf-8"
    )


def _escape_xml_attribute(value: str, quote: bytes) -> bytes:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;")
    escaped = escaped.replace('"', "&quot;") if quote == b'"' else escaped.replace("'", "&apos;")
    return escaped.encode("utf-8")


def _attribute_match(start_tag: bytes, name: str) -> re.Match[bytes] | None:
    encoded = re.escape(name.encode("utf-8"))
    pattern = re.compile(
        rb"(?P<leading>\s)"
        + encoded
        + rb"(?P<equals>\s*=\s*)(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
        re.DOTALL,
    )
    return pattern.search(start_tag)


def _set_raw_attribute(start_tag: bytes, name: str, value: str) -> bytes:
    if not _XML_NAME.fullmatch(name):
        raise EditError(f"Invalid XML attribute name: {name!r}")
    match = _attribute_match(start_tag, name)
    if match is not None:
        quote = match.group("quote")
        replacement = (
            match.group("leading")
            + name.encode("utf-8")
            + match.group("equals")
            + quote
            + _escape_xml_attribute(value, quote)
            + quote
        )
        return start_tag[: match.start()] + replacement + start_tag[match.end() :]
    insert_at = len(start_tag) - 1
    if start_tag[:insert_at].rstrip().endswith(b"/"):
        insert_at = start_tag.rfind(b"/", 0, insert_at)
    addition = b" " + name.encode("utf-8") + b'="' + _escape_xml_attribute(value, b'"') + b'"'
    return start_tag[:insert_at] + addition + start_tag[insert_at:]


def _remove_raw_attribute(start_tag: bytes, name: str) -> bytes:
    if not _XML_NAME.fullmatch(name):
        raise EditError(f"Invalid XML attribute name: {name!r}")
    match = _attribute_match(start_tag, name)
    if match is None:
        raise EditError(f"XML attribute {name!r} is missing")
    leading = match.group("leading")
    preserved = leading if leading in {b"\r", b"\n"} else b""
    return start_tag[: match.start()] + preserved + start_tag[match.end() :]


def _open_self_closing_tag(start_tag: bytes) -> bytes:
    closing = start_tag.rfind(b"/")
    if closing < 0:
        raise EditError("Expected a self-closing XML tag")
    return start_tag[:closing].rstrip() + b">"


def _apply_replacements(data: bytes, replacements: list[tuple[int, int, bytes]]) -> bytes:
    ordered = sorted(replacements, key=lambda item: (item[0], item[1]), reverse=True)
    previous_start = len(data) + 1
    for start, end, replacement in ordered:
        if not (0 <= start <= end <= len(data)):
            raise EditError("XML byte replacement is outside the document")
        if end > previous_start:
            raise EditError("Overlapping XML byte replacements are ambiguous")
        data = data[:start] + replacement + data[end:]
        previous_start = start
    return data


def _apply_raw_edit(
    document: DipTraceDocument,
    index: int,
    edit: XmlEdit,
    matches: list[ET.Element],
) -> bytes:
    spans, mapping = _element_span_map(document)
    replacements: list[tuple[int, int, bytes]] = []
    if edit.operation in {"replace_xml", "delete_element"} and any(
        element is document.root for element in matches
    ):
        raise EditError(f"Edit {index}: replacing or deleting <Source> is forbidden")

    if edit.operation == "set_text" and edit.value is None:
        raise EditError(f"Edit {index}: set_text requires value")
    if edit.operation == "set_attribute" and (not edit.attribute or edit.value is None):
        raise EditError(f"Edit {index}: set_attribute requires attribute and value")
    if edit.operation == "remove_attribute" and not edit.attribute:
        raise EditError(f"Edit {index}: remove_attribute requires attribute")
    fragment: bytes | None = None
    if edit.operation in {"append_xml", "replace_xml"}:
        _parse_fragment(index, edit.value)
        assert edit.value is not None
        fragment = edit.value.strip().encode("utf-8")

    for element in matches:
        span_index = mapping[id(element)]
        span = spans[span_index]
        start_tag = document.raw_bytes[span.start : span.start_tag_end]
        if edit.operation == "set_text":
            assert edit.value is not None
            escaped = _escape_xml_text(edit.value)
            if span.self_closing:
                replacement = _open_self_closing_tag(start_tag) + escaped
                replacement += f"</{span.name}>".encode()
                replacements.append((span.start, span.end, replacement))
            else:
                direct_children = [
                    child for child in spans if child.parent_index == span_index
                ]
                text_end = direct_children[0].start if direct_children else span.content_end
                replacements.append((span.start_tag_end, text_end, escaped))
        elif edit.operation == "set_attribute":
            assert edit.attribute is not None and edit.value is not None
            replacements.append(
                (
                    span.start,
                    span.start_tag_end,
                    _set_raw_attribute(start_tag, edit.attribute, edit.value),
                )
            )
        elif edit.operation == "remove_attribute":
            assert edit.attribute is not None
            replacements.append(
                (
                    span.start,
                    span.start_tag_end,
                    _remove_raw_attribute(start_tag, edit.attribute),
                )
            )
        elif edit.operation == "append_xml":
            assert fragment is not None
            if span.self_closing:
                replacement = _open_self_closing_tag(start_tag) + fragment
                replacement += f"</{span.name}>".encode()
                replacements.append((span.start, span.end, replacement))
            else:
                replacements.append((span.content_end, span.content_end, fragment))
        elif edit.operation == "replace_xml":
            assert fragment is not None
            replacements.append((span.start, span.end, fragment))
        elif edit.operation == "delete_element":
            replacements.append((span.start, span.end, b""))
        else:
            raise EditError(f"Edit {index}: unsupported operation {edit.operation!r}")

    return _apply_replacements(document.raw_bytes, replacements)


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
