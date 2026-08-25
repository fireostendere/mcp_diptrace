"""Hybrid retrieval: dense (e5) + BM25 merged client-side, then an optional
local cross-encoder rerank, with source-authority weighting, metadata filters
and a token budget.
"""
from __future__ import annotations

from .config import Settings
from .embed import get_embedder, get_reranker
from .metadata import extract_part_numbers
from .sparse import sparse_tf
from .store import VectorStore

FILTERABLE_EXACT = {"authority", "doc_type", "manufacturer"}
FILTERABLE_TEXT = {"title", "filename", "source"}

FILTER_HELP = {
    "authority": "trust tier: datasheet | appnote | reference_design | "
                 "official_docs | specification | article | community | forum",
    "doc_type": "pdf | markdown | text | web | youtube",
    "manufacturer": "exact manufacturer name",
    "part_number": "matches any detected part number",
    "title": "substring/full-text match on title",
    "filename": "substring match on filename",
    "source": "substring match on source path/URL",
}


def build_filter(parsed: dict | None):
    from qdrant_client import models as qm

    if not parsed:
        return None, None

    unknown = set(parsed) - FILTERABLE_EXACT - FILTERABLE_TEXT - {"part_number"}
    if unknown:
        raise ValueError(
            f"unsupported filter keys: {sorted(unknown)}; allowed: "
            f"{sorted(FILTERABLE_EXACT | FILTERABLE_TEXT | {'part_number'})}")

    must: list = []
    for key in ("authority", "doc_type", "manufacturer"):
        value = parsed.get(key)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        must.append(qm.FieldCondition(key=key, match=qm.MatchAny(any=values)))
    pn = parsed.get("part_number")
    if pn:
        # help the caller: expand bare tokens into part-number candidates too
        pns = pn if isinstance(pn, list) else [pn]
        must.append(qm.FieldCondition(key="part_numbers",
                                      match=qm.MatchAny(any=pns)))
    for key in ("title", "filename", "source"):
        value = parsed.get(key)
        if value:
            must.append(qm.FieldCondition(key=key,
                                          match=qm.MatchText(text=str(value))))
    if not must:
        return None, None
    return qm.Filter(must=must), None


def search(query: str, settings: Settings, store: VectorStore,
           top_k: int = 8, filters: dict | None = None):
    """Returns dict with hits and assembled context within the token budget."""
    flt, _ = build_filter(filters)

    embedder = get_embedder(settings.embedding_model)
    q_dense = embedder.embed_query(query)
    q_sparse = sparse_tf(query)

    fetch_k = max(top_k * 4, 24)
    points = store.hybrid_search(q_dense, q_sparse, flt, top_k, fetch_mult=4)

    hits = []
    seen_texts = set()
    for p, base in points:
        payload = p or {}
        key = (payload.get("doc_id"), payload.get("chunk_index"))
        if key in seen_texts:
            continue
        seen_texts.add(key)
        authority = payload.get("authority") or ""
        weight = settings.authority_weight(authority)
        score = float(base) * (0.5 + weight)
        hits.append({
            "score": round(score, 6),
            "retrieval_score": round(float(base), 6),
            "authority_weight": weight,
            "text": payload.get("text", ""),
            "document_id": payload.get("doc_id"),
            "chunk_index": payload.get("chunk_index"),
            "section": payload.get("section"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "title": payload.get("title"),
            "source": payload.get("source"),
            "filename": payload.get("filename"),
            "doc_type": payload.get("doc_type"),
            "authority": authority,
            "manufacturer": payload.get("manufacturer"),
            "part_numbers": payload.get("part_numbers") or [],
            "revision": payload.get("revision"),
        })

    hits.sort(key=lambda h: h["score"], reverse=True)

    # optional local cross-encoder rerank over the leading candidates
    n_cand = max(settings.rerank_candidates, top_k)
    cand = hits[:n_cand]
    reranker = get_reranker(settings.rerank_model)
    if reranker is not None and cand:
        try:
            scores = reranker.rerank(query, [h["text"] for h in cand])
        except Exception:
            scores = None  # model unavailable -> keep hybrid order
        if scores is not None:
            # final = relevance logit + mild trust bonus (max +0.3)
            for h, s in zip(cand, scores):
                h["rerank_score"] = round(s, 4)
                h["score"] = round(s + 0.3 * h["authority_weight"], 6)
            cand.sort(key=lambda h: h["score"], reverse=True)
    hits = cand[:top_k]

    # assemble context within budget
    budget_chars = int(settings.max_context_tokens * settings.chars_per_token)
    used = 0
    kept = []
    for i, h in enumerate(hits):
        block_len = len(h["text"])
        if used + block_len > budget_chars and kept:
            break
        kept.append(i)
        used += block_len

    context_parts = []
    for i in kept:
        h = hits[i]
        loc = []
        if h.get("section"):
            loc.append(h["section"])
        page = f"p.{h['page_start']}" if h.get("page_start") else None
        if page:
            loc.append(page)
        header = f"[{i + 1}] {h['title']} ({'; '.join(loc) or 'n/a'})"
        context_parts.append(header + "\n" + h["text"])

    est_tokens = int(used / settings.chars_per_token)
    return {
        "query": query,
        "hits": hits,
        "context": "\n\n".join(context_parts),
        "context_tokens_estimate": est_tokens,
        "max_context_tokens": settings.max_context_tokens,
        "total_hits": len(hits),
    }


def suggest_part_filters(query: str) -> list[str]:
    """Part-number candidates found in the query itself (handy for UI/debug)."""
    return extract_part_numbers(query)
