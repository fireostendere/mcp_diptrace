"""Persistence: SQLite document registry + Qdrant vector store wrapper."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from .chunk import Chunk
from .sparse import SPARSE_NAME

DOC_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://kb.local/ns/doc")


def doc_id_for_hash(content_hash: str) -> str:
    return str(uuid.uuid5(DOC_NS, content_hash))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class DocRecord:
    doc_id: str
    title: str
    doc_type: str
    source: str            # original path or URL
    filename: str
    authority: str
    hash: str
    n_chunks: int
    n_pages: int
    manufacturer: str | None = None
    part_numbers: list[str] = field(default_factory=list)
    revision: str | None = None
    ingested_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Registry:
    """SQLite catalog of documents and their source mappings."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS docs (
            doc_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            authority TEXT NOT NULL,
            hash TEXT NOT NULL UNIQUE,
            n_chunks INTEGER NOT NULL DEFAULT 0,
            n_pages INTEGER NOT NULL DEFAULT 0,
            manufacturer TEXT,
            part_numbers TEXT NOT NULL DEFAULT '[]',
            revision TEXT,
            source TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            ingested_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sources (
            source_key TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES docs(doc_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            last_checked TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sources_doc ON sources(doc_id);
        """)
        # tiny forward migration for pre-existing databases
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(docs)")}
        if "source" not in cols:
            self.conn.execute("ALTER TABLE docs ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        if "filename" not in cols:
            self.conn.execute("ALTER TABLE docs ADD COLUMN filename TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    def get_doc(self, doc_id: str) -> DocRecord | None:
        row = self.conn.execute("SELECT * FROM docs WHERE doc_id=?", (doc_id,)).fetchone()
        return self._row_to_doc(row) if row else None

    def get_doc_by_hash(self, content_hash: str) -> DocRecord | None:
        row = self.conn.execute("SELECT * FROM docs WHERE hash=?", (content_hash,)).fetchone()
        return self._row_to_doc(row) if row else None

    def get_source(self, source_key: str) -> tuple[str, str] | None:
        """Returns (doc_id, kind) for a registered source key."""
        row = self.conn.execute(
            "SELECT doc_id, kind FROM sources WHERE source_key=?", (source_key,)).fetchone()
        return (row["doc_id"], row["kind"]) if row else None

    def upsert_doc(self, doc: DocRecord):
        self.conn.execute(
            """INSERT INTO docs (doc_id,title,doc_type,authority,hash,n_chunks,n_pages,
               manufacturer,part_numbers,revision,source,filename,ingested_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(hash) DO UPDATE SET
                 title=excluded.title, updated_at=excluded.updated_at""",
            (doc.doc_id, doc.title, doc.doc_type, doc.authority, doc.hash,
             doc.n_chunks, doc.n_pages, doc.manufacturer,
             json.dumps(doc.part_numbers), doc.revision,
             doc.source, doc.filename, doc.ingested_at, doc.updated_at))
        # doc_id may change on reindex; keep PK in sync with hash owner.
        self.conn.execute("UPDATE docs SET doc_id=? WHERE hash=?", (doc.doc_id, doc.hash))
        self.conn.commit()

    def map_source(self, source_key: str, doc_id: str, kind: str):
        self.conn.execute(
            """INSERT INTO sources (source_key,doc_id,kind,last_checked) VALUES (?,?,?,?)
               ON CONFLICT(source_key) DO UPDATE SET doc_id=excluded.doc_id,
                 kind=excluded.kind, last_checked=excluded.last_checked""",
            (source_key, doc_id, kind, utcnow()))
        self.conn.commit()

    def delete_source(self, source_key: str):
        self.conn.execute("DELETE FROM sources WHERE source_key=?", (source_key,))
        self.conn.commit()

    def delete_doc(self, doc_id: str) -> int:
        """Delete doc row unless another source still references it."""
        refs = self.conn.execute(
            "SELECT COUNT(*) c FROM sources WHERE doc_id=?", (doc_id,)).fetchone()["c"]
        if refs:
            return refs
        self.conn.execute("DELETE FROM docs WHERE doc_id=?", (doc_id,))
        self.conn.commit()
        return 0

    def list_docs(self, limit: int | None = None) -> list[DocRecord]:
        sql = "SELECT * FROM docs ORDER BY ingested_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [self._row_to_doc(r) for r in self.conn.execute(sql)]

    def counts(self) -> dict:
        d = self.conn.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        s = self.conn.execute("SELECT COUNT(*) c FROM sources").fetchone()["c"]
        chunks = self.conn.execute("SELECT COALESCE(SUM(n_chunks),0) c FROM docs").fetchone()["c"]
        return {"documents": d, "sources": s, "chunks": chunks}

    @staticmethod
    def _row_to_doc(row: sqlite3.Row) -> DocRecord:
        return DocRecord(
            doc_id=row["doc_id"], title=row["title"], doc_type=row["doc_type"],
            source=row["source"], filename=row["filename"],
            authority=row["authority"], hash=row["hash"],
            n_chunks=row["n_chunks"], n_pages=row["n_pages"],
            manufacturer=row["manufacturer"],
            part_numbers=json.loads(row["part_numbers"] or "[]"),
            revision=row["revision"], ingested_at=row["ingested_at"],
            updated_at=row["updated_at"])

    def close(self):
        self.conn.close()


class VectorStore:
    """Qdrant collection management and hybrid retrieval."""

    DENSE = "dense"

    def __init__(self, url: str, collection: str, dense_dim: int | None = None):
        self.client = QdrantClient(url=url, timeout=60)
        self.collection = collection
        self.dense_dim = dense_dim

    def ensure_collection(self):
        if self.dense_dim is None:
            raise ValueError("VectorStore created without dense_dim; pass embedder.dim")
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    self.DENSE: qm.VectorParams(size=self.dense_dim,
                                                distance=qm.Distance.COSINE)},
                sparse_vectors_config={
                    SPARSE_NAME: qm.SparseVectorParams(
                        index=qm.SparseIndexParams(on_disk=False),
                        modifier=qm.Modifier.IDF)})
        # Payload indexes for filtering / full-text match (idempotent).
        for field_name, schema in (
            ("authority", qm.PayloadSchemaType.KEYWORD),
            ("doc_type", qm.PayloadSchemaType.KEYWORD),
            ("manufacturer", qm.PayloadSchemaType.KEYWORD),
            ("part_numbers", qm.PayloadSchemaType.KEYWORD),
            ("title", qm.PayloadSchemaType.TEXT),
            ("filename", qm.PayloadSchemaType.TEXT),
            ("source", qm.PayloadSchemaType.TEXT),
        ):
            try:
                self.client.create_payload_index(self.collection, field_name, schema)
            except Exception:
                pass  # already exists

    def upsert_chunks(self, doc: DocRecord, chunks: list[Chunk],
                      dense_vectors: list[list[float]],
                      sparse_vectors: list):
        points = []
        for ch, dv, sv in zip(chunks, dense_vectors, sparse_vectors):
            payload = {
                "doc_id": doc.doc_id,
                "chunk_index": ch.index,
                "text": ch.text,
                "source": doc.source,
                "filename": doc.filename,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "authority": doc.authority,
                "page_start": ch.page_start,
                "page_end": ch.page_end,
                "section": ch.section,
                "manufacturer": doc.manufacturer,
                "part_numbers": doc.part_numbers,
                "revision": doc.revision,
                "doc_hash": doc.hash,
                "ingested_at": doc.ingested_at,
            }
            pid = uuid.uuid5(DOC_NS, f"{doc.doc_id}:{ch.index}")
            vectors: dict = {self.DENSE: dv}
            if getattr(sv, "non_empty", False):
                vectors[SPARSE_NAME] = qm.SparseVector(indices=sv.indices, values=sv.values)
            points.append(qm.PointStruct(id=str(pid), vector=vectors, payload=payload))
        for i in range(0, len(points), 128):
            self.client.upsert(collection_name=self.collection,
                               points=points[i:i + 128], wait=True)

    def delete_doc_points(self, doc_id: str):
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(filter=qm.Filter(must=[
                qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])),
            wait=True)

    def count_points(self) -> int:
        return self.client.count(collection_name=self.collection, exact=True).count

    def scroll_by_doc(self, doc_id: str, section: str | None = None, limit: int = 256):
        must = [qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
        if section:
            must.append(qm.FieldCondition(key="section",
                                          match=qm.MatchText(text=section)))
        points, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=qm.Filter(must=must), limit=limit, with_payload=True)
        return sorted(points, key=lambda p: p.payload.get("chunk_index", 0))

    def hybrid_search(self, query_dense: list[float], query_sparse,
                      flt: qm.Filter | None, top_k: int, fetch_mult: int = 8):
        """Weighted hybrid retrieval.

        Runs dense (cosine) and sparse (BM25) retrievals separately and merges
        them client-side with min-max normalized, weighted scores. Unlike pure
        RRF this keeps semantic strength meaningful for cross-lingual queries,
        where one branch often has no lexical matches at all.
        Returns list of (payload, base_score).
        """
        n = max(top_k * fetch_mult, 128)

        def _run(using: str, query) -> list:
            # plain nearest-neighbor: query goes on the top level, no prefetch
            kwargs = dict(collection_name=self.collection, query=query,
                          using=using, limit=n, with_payload=True)
            if flt is not None:
                kwargs["query_filter"] = flt
            return self.client.query_points(**kwargs).points

        dense = _run(self.DENSE, query_dense)
        sparse = _run(SPARSE_NAME, qm.SparseVector(indices=query_sparse.indices,
                                                   values=query_sparse.values)) \
            if query_sparse.non_empty else []

        def _minmax(points: list) -> dict:
            if not points:
                return {}
            scores = [p.score for p in points]
            lo, hi = min(scores), max(scores)
            span = (hi - lo) or 1.0
            return {p.id: (p.score - lo) / span for p in points}

        d_norm, s_norm = _minmax(dense), _minmax(sparse)
        W_DENSE, W_SPARSE = 0.7, 0.3
        payloads: dict = {}
        merged: dict = {}
        for p in dense:
            payloads[p.id] = p.payload or {}
            merged.setdefault(p.id, 0.0)
        for p in sparse:
            payloads.setdefault(p.id, p.payload or {})
            merged.setdefault(p.id, 0.0)
        for pid in merged:
            merged[pid] = (W_DENSE * d_norm.get(pid, 0.0)
                           + W_SPARSE * s_norm.get(pid, 0.0))
        ranked = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [(payloads[pid], score) for pid, score in ranked]

    def ping(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def close(self):
        self.client.close()
