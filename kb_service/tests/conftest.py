"""Shared fixtures: isolated settings (tmp data dir, unique collection)."""
from __future__ import annotations

import os
import socket
import uuid
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _qdrant_up(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/healthz", timeout=3)
        return r.status_code == 200
    except Exception:
        try:
            r = httpx.get(url, timeout=3)
            return r.status_code in (200, 404)
        except Exception:
            return False


@pytest.fixture(scope="module")
def test_settings(tmp_path_factory, request):
    """Settings pointing at a throwaway collection + tmp storage (per module)."""
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    if not _qdrant_up(qdrant_url):
        pytest.skip("Qdrant is not reachable; start it with: docker compose up -d")
    data_dir = tmp_path_factory.mktemp(f"kbdata_{request.module.__name__.split('.')[-1]}")
    collection = f"test_{request.module.__name__.split('.')[-1]}_{uuid.uuid4().hex[:8]}"
    from knowledge_base.config import Settings

    return Settings(
        qdrant_url=qdrant_url,
        collection=collection,
        data_dir=data_dir.resolve(),
        embedding_model=os.environ.get("KB_EMBEDDING_MODEL",
                                       "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        rerank_model=os.environ.get("KB_RERANK_MODEL", ""),  # keep unit-ish tests fast
        rerank_candidates=8,
        chunk_size=1200,
        chunk_overlap=150,
        min_chunk_chars=80,
        max_context_tokens=2000,
        chars_per_token=3.5,
        authority_weights={
            "datasheet": 1.0, "appnote": 0.95, "reference_design": 0.95,
            "official_docs": 0.85, "specification": 0.85, "article": 0.6,
            "community": 0.35, "forum": 0.15},
        web_max_pages=5,
        youtube_max_videos=2,
        request_timeout=10.0,
    )


@pytest.fixture()
def stores(test_settings):
    from tests.helpers import open_stores

    registry, store, embedder = open_stores(test_settings)
    yield registry, store, embedder
    store.close()
    registry.close()
