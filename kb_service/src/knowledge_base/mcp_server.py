"""MCP server exposing the knowledge base to OpenCode (stdio transport).

Tools:
  knowledge_search(query, filters?, top_k?)   — hybrid retrieval
  knowledge_get(document_id, section?)        — full chunks of one document
  knowledge_ingest(source)                    — index a local path or URL
  knowledge_research(query, preferred_sources?)
  knowledge_sources(query?)
  knowledge_status()
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Settings, load_settings

mcp = FastMCP(
    "knowledge",
    instructions=(
        "Local engineering knowledge base (datasheets, appnotes, DipTrace docs, "
        "YouTube transcripts). Use knowledge_search for retrieval; results carry "
        "document title, page/section, source and trust tier. Prefer "
        "authority='datasheet'/'appnote' filters when the user asks for "
        "manufacturer facts."))


def _settings() -> Settings:
    return load_settings()


def _stores(settings: Settings):
    from .embed import get_embedder
    from .store import Registry, VectorStore

    registry = Registry(settings.db_path)
    embedder = get_embedder(settings.embedding_model)
    store = VectorStore(settings.qdrant_url, settings.collection, embedder.dim)
    store.ensure_collection()
    return registry, store


@mcp.tool()
def knowledge_search(query: str, filters: dict[str, Any] | None = None,
                     top_k: int = 8) -> dict:
    """Hybrid (semantic + BM25) search over the engineering knowledge base.

    query: free-form question or keywords, EN or RU.
    filters: optional metadata filter dict. Allowed keys:
      authority ("datasheet"|"appnote"|"reference_design"|"official_docs"|
                 "specification"|"article"|"community"|"forum", or list),
      doc_type ("pdf"|"markdown"|"text"|"web"|"youtube"),
      manufacturer, part_number, title, filename, source.
    Returns hits with text, score, document_id, page_start/page_end, section,
    title, source, authority and an assembled `context` string within budget.
    """
    from .search import search as do_search
    settings = _settings()
    _, store = _stores(settings)
    try:
        return do_search(query, settings, store, top_k=max(1, min(top_k, 50)),
                         filters=filters)
    finally:
        store.close()


@mcp.tool()
def knowledge_get(document_id: str, section: str | None = None) -> dict:
    """Return all chunks of one indexed document (optionally only one section).

    Use document_id from knowledge_search / knowledge_sources.
    """
    from .store import Registry, VectorStore
    settings = _settings()
    registry = Registry(settings.db_path)
    doc = registry.get_doc(document_id)
    registry.close()
    if not doc:
        return {"error": f"unknown document_id: {document_id}",
                "hint": "list ids via knowledge_sources"}
    store = VectorStore(settings.qdrant_url, settings.collection)
    try:
        points = store.scroll_by_doc(document_id, section=section)
    finally:
        store.close()
    return {
        "document": {
            "document_id": doc.doc_id, "title": doc.title,
            "doc_type": doc.doc_type, "authority": doc.authority,
            "source": doc.source, "filename": doc.filename,
            "manufacturer": doc.manufacturer,
            "part_numbers": doc.part_numbers, "revision": doc.revision,
            "n_pages": doc.n_pages, "n_chunks": doc.n_chunks,
            "ingested_at": doc.ingested_at,
        },
        "chunks": [{
            "chunk_index": p.payload.get("chunk_index"),
            "section": p.payload.get("section"),
            "page_start": p.payload.get("page_start"),
            "page_end": p.payload.get("page_end"),
            "text": p.payload.get("text"),
        } for p in points],
    }


@mcp.tool()
def knowledge_ingest(source: str) -> dict:
    """Index one new source into the knowledge base.

    source: local file/directory path OR http(s) URL (web page or YouTube).
    Identical content is skipped automatically; changed files are re-indexed.
    """
    from .ingest import ingest_anywhere
    settings = _settings()
    registry, store = _stores(settings)
    try:
        reports = ingest_anywhere(source, settings, registry, store)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            registry.close()
            store.close()
        except Exception:
            pass
    return {"reports": [vars(r) for r in reports],
            "ok": all(r.status != "failed" for r in reports)}


@mcp.tool()
def knowledge_research(query: str,
                       preferred_sources: list[str] | None = None) -> dict:
    """Multi-source web research stub — NOT implemented on purpose.

    A trustworthy implementation needs a real web-search API (e.g. Tavily,
    Brave Search API or SearXNG endpoint) plus a fetch+ingest loop feeding
    knowledge_ingest. It is intentionally not faked: this tool never returns
    invented results and never writes LLM output back into the knowledge base.

    To enable it later: implement search provider integration and call
    knowledge_ingest on the found URLs before searching locally.
    """
    return {
        "status": "not_implemented",
        "query": query,
        "reason": (
            "Web research requires an external search API (Tavily/Brave/SearXNG). "
            "Configure KB_RESEARCH_PROVIDER and KB_RESEARCH_API_KEY to enable."),
        "what_works_today": [
            "knowledge_search over already-ingested sources",
            "knowledge_ingest for any URL found by other means",
        ],
        "preferred_sources_note": preferred_sources or None,
    }


@mcp.tool()
def knowledge_sources(query: str | None = None) -> dict:
    """List indexed documents (id, title, authority, pages/chunks, dates).

    query: optional substring filter over title/filename/source/part numbers.
    """
    from .store import Registry
    registry = Registry(_settings().db_path)
    try:
        docs = registry.list_docs()
    finally:
        registry.close()
    q = (query or "").lower()
    rows = []
    for d in docs:
        blob = " ".join([d.title, d.filename, d.source,
                         " ".join(d.part_numbers)]).lower()
        if q and q not in blob:
            continue
        rows.append({
            "document_id": d.doc_id, "title": d.title, "doc_type": d.doc_type,
            "authority": d.authority, "source": d.source,
            "manufacturer": d.manufacturer, "part_numbers": d.part_numbers,
            "revision": d.revision, "pages": d.n_pages, "chunks": d.n_chunks,
            "ingested_at": d.ingested_at})
    return {"count": len(rows), "documents": rows}


@mcp.tool()
def knowledge_status() -> dict:
    """Service status: Qdrant reachability, counts, model, configured sources."""
    from qdrant_client import QdrantClient

    settings = _settings()
    info: dict[str, Any] = {
        "qdrant_url": settings.qdrant_url,
        "collection": settings.collection,
        "data_dir": str(settings.data_dir),
        "embedding_model": settings.embedding_model,
        "max_context_tokens": settings.max_context_tokens,
    }
    reachable = False
    points = None
    try:
        client = QdrantClient(url=settings.qdrant_url, timeout=10)
        reachable = True
        try:
            points = client.count(collection_name=settings.collection,
                                  exact=True).count
        except Exception:
            points = None
        client.close()
    except Exception as exc:
        info["error"] = str(exc)
    info["qdrant_reachable"] = reachable
    info["indexed_points"] = points

    from .store import Registry
    registry = Registry(settings.db_path)
    info["registry"] = registry.counts()
    docs = registry.list_docs(limit=100000)
    by_authority: dict[str, int] = {}
    for d in docs:
        by_authority[d.authority] = by_authority.get(d.authority, 0) + 1
    info["documents_by_authority"] = by_authority
    info["last_ingest"] = max((d.ingested_at for d in docs), default=None)
    registry.close()

    from .config import load_sources
    info["configured_sources"] = [
        {"type": s.kind, "path": s.path, "url": s.url} for s in load_sources()]
    return info


def main() -> int:
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
