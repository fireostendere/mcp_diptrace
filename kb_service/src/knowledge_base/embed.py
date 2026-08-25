"""FastEmbed dense embeddings (local ONNX, cached after first download)."""
from __future__ import annotations

import threading
import warnings


class Embedder:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            from fastembed import TextEmbedding
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*mean pooling.*")
                self._model = TextEmbedding(model_name=self.model_name)

    @property
    def dim(self) -> int:
        self._ensure()
        return len(next(iter(self._model.embed(["dim probe"]))))

    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        if not texts:
            return []
        self._ensure()
        return [v.tolist() for v in self._model.embed(texts, batch_size=batch_size)]

    def embed_query(self, text: str) -> list[float]:
        self._ensure()
        return next(iter(self._model.query_embed([text]))).tolist()


def get_embedder(model_name: str) -> Embedder:
    with Embedder._lock:
        if Embedder._instance is None or Embedder._instance.model_name != model_name:
            Embedder._instance = Embedder(model_name)
        return Embedder._instance


class Reranker:
    """Lazy local cross-encoder reranker (fastembed TextCrossEncoder)."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*mean pooling.*")
                self._model = TextCrossEncoder(model_name=self.model_name)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        self._ensure()
        return [float(s) for s in self._model.rerank(query, texts)]


def get_reranker(model_name: str) -> Reranker | None:
    if not model_name:
        return None
    with Reranker._lock:
        if Reranker._instance is None or Reranker._instance.model_name != model_name:
            Reranker._instance = Reranker(model_name)
        return Reranker._instance
