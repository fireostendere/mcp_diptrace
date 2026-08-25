"""Sparse BM25 vectors via hashing trick; IDF is applied server-side by Qdrant.

Client sends term frequencies only; the collection's sparse index is created
with modifier=IDF so Qdrant computes BM25 from global document frequencies.
This keeps scoring consistent across incremental ingestion batches (unlike
per-batch-fitted local BM25).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

SPARSE_NAME = "bm25"
DIM = 1 << 20  # hashed vocabulary size

TOKEN_RE = re.compile(r"[a-zа-яё0-9][a-zа-яё0-9._+\-]*", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.lower().strip("._-") for t in TOKEN_RE.findall(text)
            if len(t.strip("._-")) >= 2]


def _term_id(token: str) -> int:
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % DIM


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]

    @property
    def non_empty(self) -> bool:
        return bool(self.indices)


def sparse_tf(text: str) -> SparseVector:
    """Deterministic term-frequency vector for a chunk or query."""
    counts: dict[int, float] = {}
    for tok in tokenize(text):
        idx = _term_id(tok)
        counts[idx] = counts.get(idx, 0.0) + 1.0
    return SparseVector(indices=list(counts.keys()), values=list(counts.values()))
