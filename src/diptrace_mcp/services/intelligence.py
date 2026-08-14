"""Read-only public tool surface for the documented EDA intelligence engines."""

from __future__ import annotations

from typing import Any

from ..errors import CapabilityUnavailableError, DocumentError
from ..library_adapters import get_library_model
from ..pattern_recommendation import PatternRequirement, recommend_patterns
from ..pcb_candidate_ensemble import PCBEnsembleConfig, build_pcb_candidate_ensemble
from ..release_readiness import run_release_readiness
from ..schematic_ensemble import rank_schematic_ensemble
from .context import DocumentGateway, ServiceContext, read_success

_RANK_LIMITATIONS = (
    "Builtin motifs are deterministic readability heuristics labeled "
    "source_kind='builtin'; they never represent datasheet or reference-design evidence.",
    "Route defects rank lexicographically above congestion and compactness terms.",
)

_PCB_ENSEMBLE_LIMITATIONS = (
    "Candidates come from the bounded Generation-A placement planner; Generation B/C "
    "data contributes conservative evidence proxies only.",
    "Selection is the existing hard-first Generation-D policy, not a global optimality claim.",
)

_RECOMMENDATION_LIMITATIONS = (
    "Ranking is a deterministic hard-filter plus bounded geometry score; no model is "
    "trained or called.",
)

_RELEASE_READINESS_LIMITATIONS = (
    "Checks are bounded to facts available in exported XML and supplement the review "
    "engine without replacing DipTrace DRC/ERC, fabrication review, assembly sign-off, "
    "or physical test-fixture review.",
)


class IntelligenceService:
    """Tool surface over the internal schematic/PCB intelligence engines."""

    def __init__(self, context: ServiceContext, gateway: DocumentGateway) -> None:
        self.context = context
        self.gateway = gateway

    def rank_schematic_placement_candidates(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = rank_schematic_ensemble(document)
        return read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            limitations=list(_RANK_LIMITATIONS),
        )

    def compare_pcb_placement_candidates(
        self,
        path: str | None = None,
        *,
        profiles: list[str] | None = None,
        include_existing_board: bool = True,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        overrides: dict[str, Any] = {"profiles": profiles} if profiles else {}
        overrides["include_existing_board"] = include_existing_board
        config = PCBEnsembleConfig.model_validate(overrides)
        result = build_pcb_candidate_ensemble(snapshot, config=config)
        return read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            limitations=list(_PCB_ENSEMBLE_LIMITATIONS),
        )

    def recommend_patterns(
        self,
        requirement: PatternRequirement,
        path: str | None = None,
        *,
        limit: int = 10,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        try:
            model = get_library_model(document)
        except DocumentError as exc:
            raise CapabilityUnavailableError(
                "Pattern recommendation requires a pattern or component library document"
            ) from exc
        result = recommend_patterns(model.patterns, requirement, limit=limit)
        return read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            limitations=list(_RECOMMENDATION_LIMITATIONS),
        )

    def analyze_release_readiness(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = run_release_readiness(snapshot)
        return read_success(
            snapshot.info,
            result,
            limitations=list(_RELEASE_READINESS_LIMITATIONS),
        )
