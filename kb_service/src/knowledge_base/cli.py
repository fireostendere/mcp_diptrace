"""CLI entry point: `knowledge` command."""
from __future__ import annotations

import argparse
import json
import sys

from .config import Settings, load_settings, load_sources


def _open_stores(settings: Settings):
    from .embed import get_embedder
    from .store import Registry, VectorStore

    registry = Registry(settings.db_path)
    embedder = get_embedder(settings.embedding_model)
    store = VectorStore(settings.qdrant_url, settings.collection, embedder.dim)
    store.ensure_collection()
    return registry, store, embedder


def cmd_ingest(args, settings: Settings) -> int:
    from .ingest import ingest_anywhere
    registry, store, _ = _open_stores(settings)
    try:
        reports = ingest_anywhere(args.source, settings, registry, store,
                                  force=args.force)
    finally:
        registry.close()
        store.close()
    _print_reports(reports)
    return 0 if all(r.status != "failed" for r in reports) else 1


def cmd_ingest_all(args, settings: Settings) -> int:
    from .ingest import ingest_source_config
    sources = load_sources()
    if not sources:
        print("no sources configured in config/sources.yaml", file=sys.stderr)
        return 1
    registry, store, _ = _open_stores(settings)
    failures = 0
    try:
        for src in sources:
            label = src.path or src.url or src.kind
            print(f"==> source [{src.kind}] {label}", flush=True)
            try:
                reports = ingest_source_config(src, settings, registry, store,
                                               force=args.force)
            except Exception as exc:
                print(f"    source failed: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
                failures += 1
                continue
            _print_reports(reports, indent="  ")
            failures += sum(1 for r in reports if r.status == "failed")
    finally:
        registry.close()
        store.close()
    return 0 if failures == 0 else 1


def _print_reports(reports, indent: str = ""):
    for rep in reports:
        line = f"{indent}[{rep.status}] {rep.source}"
        if rep.n_chunks:
            line += f" ({rep.n_chunks} chunks)"
        if rep.detail:
            line += f" — {rep.detail}"
        print(line, flush=True)


def cmd_search(args, settings: Settings) -> int:
    from .search import search as do_search
    _, store, _ = _open_stores(settings)
    filters = json.loads(args.filter) if args.filter else None
    try:
        result = do_search(args.query, settings, store,
                           top_k=args.top_k, filters=filters)
    finally:
        store.close()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for i, hit in enumerate(result["hits"], start=1):
            loc = hit.get("section") or ""
            if hit.get("page_start"):
                loc += f" p.{hit['page_start']}"
            print(f"[{i}] {hit['score']:.4f} | {hit['title']} | {loc} "
                  f"| {hit['authority']} | {hit['source']}")
            text = hit["text"].replace("\n", " ")
            print(f"    {text[:300]}{'…' if len(text) > 300 else ''}\n")
    return 0


def cmd_get(args, settings: Settings) -> int:
    from .store import Registry, VectorStore
    registry = Registry(settings.db_path)
    doc = registry.get_doc(args.document_id)
    registry.close()
    if not doc:
        print(f"unknown document_id: {args.document_id}", file=sys.stderr)
        return 1
    _, store, _ = _open_stores(settings)
    try:
        points = store.scroll_by_doc(args.document_id, section=args.section)
    finally:
        store.close()
    out = {
        "document": {"doc_id": doc.doc_id, "title": doc.title,
                     "source": doc.source, "authority": doc.authority,
                     "n_chunks": doc.n_chunks, "revision": doc.revision,
                     "manufacturer": doc.manufacturer,
                     "part_numbers": doc.part_numbers},
        "sections": [{"chunk_index": p.payload.get("chunk_index"),
                      "section": p.payload.get("section"),
                      "page_start": p.payload.get("page_start"),
                      "page_end": p.payload.get("page_end"),
                      "text": p.payload.get("text")} for p in points],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_sources(args, settings: Settings) -> int:
    from .store import Registry
    registry = Registry(settings.db_path)
    docs = registry.list_docs()
    registry.close()
    q = (args.query or "").lower()
    rows = []
    for d in docs:
        blob = " ".join([d.title, d.filename, d.source,
                         " ".join(d.part_numbers)]).lower()
        if q and q not in blob:
            continue
        rows.append({
            "document_id": d.doc_id, "title": d.title, "authority": d.authority,
            "doc_type": d.doc_type, "chunks": d.n_chunks,
            "pages": d.n_pages, "manufacturer": d.manufacturer,
            "part_numbers": d.part_numbers, "revision": d.revision,
            "ingested_at": d.ingested_at,
        })
    print(json.dumps({"count": len(rows), "documents": rows},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_status(settings: Settings) -> int:
    from .store import Registry, VectorStore
    info = {
        "service": "knowledge-base-rag",
        "qdrant_url": settings.qdrant_url,
        "collection": settings.collection,
        "data_dir": str(settings.data_dir),
        "embedding_model": settings.embedding_model,
        "max_context_tokens": settings.max_context_tokens,
    }
    registry = Registry(settings.db_path)
    info["registry"] = registry.counts()
    docs = registry.list_docs(limit=100000)
    by_authority: dict[str, int] = {}
    for d in docs:
        by_authority[d.authority] = by_authority.get(d.authority, 0) + 1
    info["documents_by_authority"] = by_authority
    last = max((d.ingested_at for d in docs), default=None)
    info["last_ingest"] = last
    registry.close()

    store = VectorStore(settings.qdrant_url, settings.collection)  # ping-only
    reachable = store.ping()
    info["qdrant_reachable"] = reachable
    if reachable:
        try:
            info["indexed_points"] = store.count_points()
        except Exception:
            info["indexed_points"] = None
    store.close()
    configured = load_sources()
    info["configured_sources"] = [
        {"type": s.kind, "path": s.path, "url": s.url,
         "recursive": s.recursive, "authority": s.authority}
        for s in configured]
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_delete(args, settings: Settings) -> int:
    """Remove a document (by doc_id or source path/URL substring) from the KB."""
    import shutil

    from .store import Registry, VectorStore, doc_id_for_hash
    registry = Registry(settings.db_path)
    store = VectorStore(settings.qdrant_url, settings.collection)
    target = args.document
    doc = registry.get_doc(target)
    if not doc:
        mapped = registry.get_source(target)
        if mapped:
            doc = registry.get_doc(mapped[0])
    if not doc:
        rows = [d for d in registry.list_docs()
                if target.lower() in (d.source or "").lower()]
        if len(rows) == 1:
            doc = rows[0]
        elif len(rows) > 1:
            print(f"ambiguous: {len(rows)} documents match; be specific:",
                  file=sys.stderr)
            for r in rows[:10]:
                print(f"  {r.doc_id}  {r.source}")
            registry.close()
            store.close()
            return 1
    if not doc:
        print(f"document not found: {target}", file=sys.stderr)
        registry.close()
        store.close()
        return 1
    # drop all source mappings pointing at this doc
    for src_key in [s for s in _source_keys(registry, doc.doc_id)]:
        registry.delete_source(src_key)
    store.delete_doc_points(doc.doc_id)
    refs = registry.delete_doc(doc.doc_id)
    raw = settings.raw_dir / doc.doc_id
    if raw.exists():
        shutil.rmtree(raw, ignore_errors=True)
    print(f"deleted {doc.doc_id} ({doc.title}) — {doc.source}"
          + (f" [kept: referenced by {refs} other sources]" if refs else ""))
    registry.close()
    store.close()
    return 0


def _source_keys(registry, doc_id: str):
    rows = registry.conn.execute(
        "SELECT source_key FROM sources WHERE doc_id=?", (doc_id,))
    return [r["source_key"] for r in rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge",
        description="Local engineering knowledge base (RAG): ingest & search")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output where supported")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ingest", help="ingest a local path or URL")
    p.add_argument("source")
    p.add_argument("--force", action="store_true",
                   help="re-index even if unchanged")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ingest-all",
                       help="index every configured source (incremental)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ingest_all)

    p = sub.add_parser("search", help="hybrid semantic + BM25 search")
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--filter", dest="filter", default=None,
                   help='JSON dict, e.g. \'{"authority":"datasheet"}\'')
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get", help="fetch full document chunks by id")
    p.add_argument("document_id")
    p.add_argument("--section", default=None)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("sources", help="list indexed documents")
    p.add_argument("query", nargs="?", default=None)
    p.set_defaults(func=cmd_sources)

    sub.add_parser("status", help="service status").set_defaults(
        func=lambda a, s: cmd_status(s))

    p = sub.add_parser("delete", help="remove a document by id or source substring")
    p.add_argument("document")
    p.set_defaults(func=cmd_delete)

    sub.add_parser("serve", help="run the MCP server (stdio)").set_defaults(
        func=lambda a, s: _serve())

    return parser


def _serve():
    from .mcp_server import main as mcp_main
    raise SystemExit(mcp_main())


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    settings = load_settings()
    return args.func(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
