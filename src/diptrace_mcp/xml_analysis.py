from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from xml.etree.ElementTree import Element

from pydantic import Field

from .domain import StrictModel
from .xml_document import DipTraceDocument


class XMLSemanticInventory(StrictModel):
    source_type: str
    root_tag: str
    semantic_sha256: str
    element_count: int = Field(ge=1)
    attribute_count: int = Field(ge=0)
    text_node_count: int = Field(ge=0)
    max_depth: int = Field(ge=0)
    tag_counts: dict[str, int] = Field(default_factory=dict)
    attribute_name_counts: dict[str, int] = Field(default_factory=dict)
    duplicate_tag_id_pairs: list[str] = Field(default_factory=list)


class XMLSemanticDelta(StrictModel):
    source_type_changed: bool
    root_tag_changed: bool
    semantic_equal: bool
    before_sha256: str
    after_sha256: str
    added_local_records: int = Field(ge=0)
    removed_local_records: int = Field(ge=0)
    tag_count_delta: dict[str, int] = Field(default_factory=dict)
    attribute_count_delta: dict[str, int] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def _text(value: str | None) -> str:
    return (value or "").strip()


def _canonical_node(element: Element) -> tuple[object, ...]:
    return (
        element.tag,
        tuple(
            sorted((str(key), str(value)) for key, value in element.attrib.items())
        ),
        _text(element.text),
        tuple(_canonical_node(child) for child in list(element)),
    )


def _digest(element: Element) -> str:
    payload = json.dumps(
        _canonical_node(element),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _walk(element: Element, *, depth: int = 0) -> Iterable[tuple[Element, int]]:
    yield element, depth
    for child in list(element):
        yield from _walk(child, depth=depth + 1)


def _local_record(element: Element) -> tuple[object, ...]:
    """Return a local record for bounded diffs without parent-cascade noise."""

    return (
        element.tag,
        tuple(
            sorted((str(key), str(value)) for key, value in element.attrib.items())
        ),
        _text(element.text),
    )


def analyze_xml_semantics(document: DipTraceDocument) -> XMLSemanticInventory:
    tags: Counter[str] = Counter()
    attributes: Counter[str] = Counter()
    ids: Counter[tuple[str, str]] = Counter()
    element_count = 0
    attribute_count = 0
    text_nodes = 0
    max_depth = 0
    for element, depth in _walk(document.root):
        element_count += 1
        max_depth = max(max_depth, depth)
        tags[element.tag] += 1
        attribute_count += len(element.attrib)
        attributes.update(element.attrib.keys())
        if _text(element.text):
            text_nodes += 1
        xml_id = element.get("Id")
        if xml_id is not None:
            ids[(element.tag, xml_id)] += 1
    duplicates = sorted(
        f"{tag}#{xml_id} x{count}"
        for (tag, xml_id), count in ids.items()
        if count > 1
    )
    return XMLSemanticInventory(
        source_type=document.source_type,
        root_tag=document.root.tag,
        semantic_sha256=_digest(document.root),
        element_count=element_count,
        attribute_count=attribute_count,
        text_node_count=text_nodes,
        max_depth=max_depth,
        tag_counts=dict(sorted(tags.items())),
        attribute_name_counts=dict(sorted(attributes.items())),
        duplicate_tag_id_pairs=duplicates,
    )


def _counter_delta(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    keys = sorted(set(before) | set(after))
    return {
        key: after[key] - before[key]
        for key in keys
        if after[key] != before[key]
    }


def compare_xml_semantics(
    before: DipTraceDocument,
    after: DipTraceDocument,
) -> XMLSemanticDelta:
    before_inventory = analyze_xml_semantics(before)
    after_inventory = analyze_xml_semantics(after)
    before_records = Counter(
        _local_record(element) for element, _depth in _walk(before.root)
    )
    after_records = Counter(
        _local_record(element) for element, _depth in _walk(after.root)
    )
    added = sum((after_records - before_records).values())
    removed = sum((before_records - after_records).values())
    return XMLSemanticDelta(
        source_type_changed=before.source_type != after.source_type,
        root_tag_changed=before.root.tag != after.root.tag,
        semantic_equal=(
            before_inventory.semantic_sha256 == after_inventory.semantic_sha256
        ),
        before_sha256=before_inventory.semantic_sha256,
        after_sha256=after_inventory.semantic_sha256,
        added_local_records=added,
        removed_local_records=removed,
        tag_count_delta=_counter_delta(
            Counter(before_inventory.tag_counts),
            Counter(after_inventory.tag_counts),
        ),
        attribute_count_delta=_counter_delta(
            Counter(before_inventory.attribute_name_counts),
            Counter(after_inventory.attribute_name_counts),
        ),
        limitations=[
            (
                "The semantic fingerprint ignores XML attribute order and outer text "
                "whitespace, but preserves element order because DipTrace collections "
                "can be order-sensitive."
            ),
            (
                "Local-record delta counts summarize structural change; they are not "
                "a replacement for domain-level PCB/schematic connectivity comparison."
            ),
            (
                "Unknown XML is fingerprinted and counted even when the normalized "
                "domain model does not interpret its meaning."
            ),
        ],
    )
