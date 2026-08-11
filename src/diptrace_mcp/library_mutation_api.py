from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from .domain import StrictModel
from .errors import Sha256MismatchError
from .library_mutation import (
    CollisionPolicy,
    ComponentSpec,
    LibraryMutationResult,
    PatternSpec,
    attach_pattern,
    mutate_component,
    mutate_pattern,
    validate_explicit_pin_pad_mapping,
)
from .xml_analysis import XMLSemanticDelta, analyze_xml_semantics, compare_xml_semantics
from .xml_document import DipTraceDocument, sha256_bytes

LibraryMutationAction = Literal[
    "mutate_pattern",
    "mutate_component",
    "attach_pattern",
    "validate_mapping",
]


class LibraryMutationRequest(StrictModel):
    """Stable package-level contract prepared for future public registration.

    This model is intentionally not registered as an MCP tool. It makes the request/preview boundary
    explicit first so evidence and API review can happen without silently expanding the public tool
    surface.
    """

    action: LibraryMutationAction
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pattern: PatternSpec | None = None
    component: ComponentSpec | None = None
    component_name: str | None = Field(default=None, min_length=1, max_length=512)
    pattern_style: str | None = Field(default=None, min_length=1, max_length=512)
    part_indexes: list[int] | None = Field(default=None, max_length=256)
    collision: CollisionPolicy = "error"
    replace_pads: bool = False
    replace_graphics: bool = False
    replace_parts: bool = False
    replace_pins: bool = False
    replace_fields: bool = False

    @model_validator(mode="after")
    def _shape_matches_action(self) -> LibraryMutationRequest:
        if self.action == "mutate_pattern":
            if self.pattern is None:
                raise ValueError("mutate_pattern requires pattern")
            if self.component is not None or self.component_name is not None or self.pattern_style is not None:
                raise ValueError("mutate_pattern contains fields for another action")
        elif self.action == "mutate_component":
            if self.component is None:
                raise ValueError("mutate_component requires component")
            if self.pattern is not None or self.component_name is not None or self.pattern_style is not None:
                raise ValueError("mutate_component contains fields for another action")
        elif self.action == "attach_pattern":
            if self.component_name is None or self.pattern_style is None:
                raise ValueError("attach_pattern requires component_name and pattern_style")
            if self.pattern is not None or self.component is not None:
                raise ValueError("attach_pattern contains fields for another action")
        elif self.action == "validate_mapping":
            if self.component_name is None:
                raise ValueError("validate_mapping requires component_name")
            if self.pattern is not None or self.component is not None or self.pattern_style is not None:
                raise ValueError("validate_mapping contains fields for another action")
        return self


class LibraryMutationPreview(StrictModel):
    action: LibraryMutationAction
    source_sha256: str
    result_sha256: str
    changed: bool
    changed_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mapping_errors: list[str] = Field(default_factory=list)
    semantic_delta: XMLSemanticDelta
    result_inventory_sha256: str
    public_registration: bool = False
    evidence_boundary: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LibraryMutationExecution:
    preview: LibraryMutationPreview
    raw_bytes: bytes


def _check_expected_sha(document: DipTraceDocument, expected_sha256: str) -> str:
    actual = sha256_bytes(document.raw_bytes)
    if actual != expected_sha256:
        raise Sha256MismatchError(expected_sha256, actual)
    return actual


def _mutate(document: DipTraceDocument, request: LibraryMutationRequest) -> LibraryMutationResult:
    if request.action == "mutate_pattern":
        assert request.pattern is not None
        return mutate_pattern(
            document,
            request.pattern,
            collision=request.collision,
            replace_pads=request.replace_pads,
            replace_graphics=request.replace_graphics,
        )
    if request.action == "mutate_component":
        assert request.component is not None
        return mutate_component(
            document,
            request.component,
            collision=request.collision,
            replace_parts=request.replace_parts,
            replace_pins=request.replace_pins,
            replace_fields=request.replace_fields,
            replace_graphics=request.replace_graphics,
        )
    if request.action == "attach_pattern":
        assert request.component_name is not None
        assert request.pattern_style is not None
        return attach_pattern(
            document,
            request.component_name,
            request.pattern_style,
            part_indexes=request.part_indexes,
        )
    assert request.action == "validate_mapping"
    return LibraryMutationResult(document.raw_bytes, False, ())


def preview_library_mutation(
    document: DipTraceDocument,
    request: LibraryMutationRequest,
) -> LibraryMutationExecution:
    """Execute one in-memory mutation behind an expected-SHA preview boundary.

    No filesystem write occurs. Callers can inspect the typed preview, review the byte result, and
    later route it through an appropriate guarded persistence/real-editor evidence path.
    """

    source_sha = _check_expected_sha(document, request.expected_sha256)
    result = _mutate(document, request)
    result_document = DipTraceDocument.from_bytes(document.path, result.raw_bytes)
    mapping_errors: list[str] = []
    component_name: str | None = None
    if request.action == "mutate_component" and request.component is not None:
        component_name = request.component.name
    elif request.action in {"attach_pattern", "validate_mapping"}:
        component_name = request.component_name
    if component_name is not None and result_document.source_type == "DipTrace-ComponentLibrary":
        mapping_errors = validate_explicit_pin_pad_mapping(result_document, component_name)
    result_inventory = analyze_xml_semantics(result_document)
    preview = LibraryMutationPreview(
        action=request.action,
        source_sha256=source_sha,
        result_sha256=sha256_bytes(result.raw_bytes),
        changed=result.changed,
        changed_ids=list(result.changed_ids),
        warnings=list(result.warnings),
        mapping_errors=mapping_errors,
        semantic_delta=compare_xml_semantics(document, result_document),
        result_inventory_sha256=result_inventory.semantic_sha256,
        public_registration=False,
        evidence_boundary=[
            "This package-level request/preview contract is intentionally not registered as a public MCP tool.",
            "The internal raw-preserving writer has real-editor evidence, but a future public write API still requires explicit product/API review and public-contract snapshot updates.",
            "Preview execution is in-memory only and cannot bypass expected-SHA, persistence, review, or real-DipTrace acceptance requirements.",
        ],
    )
    return LibraryMutationExecution(preview=preview, raw_bytes=result.raw_bytes)
