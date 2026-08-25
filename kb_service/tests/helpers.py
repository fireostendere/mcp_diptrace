"""Test helpers shared between fixtures and tests."""
from __future__ import annotations

from knowledge_base.embed import get_embedder
from knowledge_base.store import Registry, VectorStore


def open_stores(settings):
    registry = Registry(settings.db_path)
    embedder = get_embedder(settings.embedding_model)
    store = VectorStore(settings.qdrant_url, settings.collection, embedder.dim)
    store.ensure_collection()
    return registry, store, embedder
