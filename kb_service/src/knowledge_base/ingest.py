"""Ingestion pipeline: fetch -> hash -> dedup -> extract -> chunk -> embed -> store.

Extensibility: register_type(name, handler) adds new source types (github,
kicad, gerber, odb++...) without touching the dispatch logic.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

from .chunk import chunk_blocks
from .config import Settings, SourceConfig
from .embed import get_embedder
from .extract import (Block, extract_html, extract_markdown, extract_pdf,
                      fetch_url)
from .metadata import (detect_manufacturer, extract_part_numbers,
                       extract_revision, guess_title, infer_authority)
from .sparse import sparse_tf
from .store import DocRecord, Registry, VectorStore, doc_id_for_hash, utcnow

SUPPORTED_EXTS = {".pdf", ".txt", ".md", ".markdown", ".html", ".htm"}

YOUTUBE_RE = re.compile(
    r"(youtube\.com/(watch\?v=|playlist\?list=|@)|youtu\.be/)", re.I)


@dataclass
class IngestReport:
    source: str
    doc_id: str | None
    status: str          # indexed | unchanged | content-duplicate | updated | failed | skipped
    detail: str = ""
    n_chunks: int = 0


# ---------------------------------------------------------------- helpers

def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save_raw(settings: Settings, doc_id: str, filename: str, data: bytes) -> Path:
    out_dir = settings.raw_dir / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / filename
    out.write_bytes(data)
    return out


def _remove_raw(settings: Settings, doc_id: str):
    d = settings.raw_dir / doc_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _blocks_for_file(path: Path):
    """Returns (blocks, npages, pdf_meta_title)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return (*extract_pdf(path), None)
    if ext in (".md", ".markdown"):
        return extract_markdown(path), 0, None
    if ext == ".txt":
        from .extract import extract_plain_text
        return extract_plain_text(path), 0, None
    if ext in (".html", ".htm"):
        blocks, title = extract_html(path.read_text(encoding="utf-8", errors="replace"),
                                     title_fallback=path.stem)
        return blocks, 0, title
    raise ValueError(f"unsupported extension: {ext}")


def ingest_bytes(source_key: str, data: bytes, *, settings: Settings,
                 registry: Registry, store: VectorStore,
                 doc_type: str, authority: str, filename: str,
                 title_hint: str = "", force: bool = False) -> IngestReport:
    """Core pipeline for one document payload."""
    content_hash = _content_hash(data)

    # 1) identical source content -> skip entirely (but verify the vectors
    #    actually exist in this collection; self-heals registry/collection drift)
    mapped = registry.get_source(source_key)
    if mapped and not force:
        prev_doc = registry.get_doc(mapped[0])
        if prev_doc and prev_doc.hash == content_hash:
            if store.scroll_by_doc(prev_doc.doc_id, limit=1):
                registry.map_source(source_key, prev_doc.doc_id,
                                    "file" if source_key.startswith("/") else "url")
                return IngestReport(source=source_key, doc_id=prev_doc.doc_id,
                                    status="unchanged",
                                    detail="hash matches; not re-indexed")
            # vectors missing in this collection -> fall through and index

    # 2) same content from another source -> alias, no re-embedding
    #    (but verify vectors exist in this collection first)
    dup = registry.get_doc_by_hash(content_hash)
    if dup is not None and not force and store.scroll_by_doc(dup.doc_id, limit=1):
        if mapped is None:
            registry.map_source(source_key, dup.doc_id, "alias")
            return IngestReport(source=source_key, doc_id=dup.doc_id,
                                status="content-duplicate",
                                detail=f"same content as {dup.doc_id}")
        if mapped[0] != dup.doc_id:
            old_doc_id = mapped[0]
            if old_doc_id:
                store.delete_doc_points(old_doc_id)
                _remove_raw(settings, old_doc_id)
                registry.delete_doc(old_doc_id)
            registry.map_source(source_key, dup.doc_id, "alias")
            return IngestReport(source=source_key, doc_id=dup.doc_id,
                                status="content-duplicate",
                                detail=f"same content as {dup.doc_id}")

    # 3) changed content under a known source -> drop old version first
    if mapped:
        old_doc_id = mapped[0]
        old_doc = registry.get_doc(old_doc_id)
        if old_doc and old_doc.hash != content_hash:
            store.delete_doc_points(old_doc_id)
            _remove_raw(settings, old_doc_id)
            refs = registry.delete_doc(old_doc_id)
            if refs:  # other sources still reference the old content; keep it
                pass

    doc_id = doc_id_for_hash(content_hash)

    tmp_path = Path(filename or "document")
    blocks, npages, pdf_title = _extract_from_bytes(data, tmp_path, doc_type)
    title = guess_title(filename, blocks, pdf_title or title_hint)
    head_text = " ".join(b.text for b in blocks[:8])

    part_numbers = extract_part_numbers(filename or "", title)
    revision = extract_revision(head_text[:4000])
    manufacturer = detect_manufacturer(title, head_text[:6000])

    chunks = chunk_blocks(blocks, chunk_size=settings.chunk_size,
                          overlap=settings.chunk_overlap,
                          min_chars=settings.min_chunk_chars)
    if not chunks:
        return IngestReport(source=source_key, doc_id=None, status="failed",
                            detail="no text extracted")

    texts = [c.text for c in chunks]
    embedder = get_embedder(settings.embedding_model)
    dense = embedder.embed_documents(texts)
    sparses = [sparse_tf(t) for t in texts]

    doc = DocRecord(
        doc_id=doc_id, title=title, doc_type=doc_type,
        source=source_key, filename=filename or "",
        authority=authority, hash=content_hash, n_chunks=len(chunks),
        n_pages=npages, manufacturer=manufacturer, part_numbers=part_numbers,
        revision=revision, ingested_at=utcnow(), updated_at=utcnow())
    store.ensure_collection()
    store.upsert_chunks(doc, chunks, dense, sparses)
    registry.upsert_doc(doc)
    registry.map_source(source_key, doc_id,
                        "file" if not source_key.startswith(("http://", "https://")) else "url")
    _save_raw(settings, doc_id, filename or "original.bin", data)

    status = "reindexed" if mapped else "indexed"
    return IngestReport(source=source_key, doc_id=doc_id, status=status,
                        n_chunks=len(chunks))


def _extract_from_bytes(data: bytes, name: Path, doc_type: str):
    suffix = name.suffix.lower()
    if suffix == ".pdf":
        return (*_pdf_from_bytes(data), None)
    if suffix in (".md", ".markdown"):
        return extract_markdown(data.decode("utf-8", errors="replace")), 0, None
    if suffix == ".txt":
        from .extract import extract_plain_text as _pt
        return _pt_from_text(data), 0, None
    if suffix in (".html", ".htm"):
        blocks, title = extract_html(data.decode("utf-8", errors="replace"))
        return blocks, 0, title
    # fallback: treat as plain text
    return _pt_from_text(data), 0, None


def _pt_from_text(data: bytes):
    import tempfile
    from .extract import extract_plain_text
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(data)
        tmp = Path(f.name)
    try:
        return extract_plain_text(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def _pdf_from_bytes(data: bytes):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp = Path(f.name)
    try:
        return extract_pdf(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- file/dir

def ingest_path(path_str: str, settings: Settings, registry: Registry,
                store: VectorStore, authority_override: str | None = None,
                extensions: list[str] | None = None,
                recursive: bool = True, force: bool = False) -> list[IngestReport]:
    path = Path(path_str).expanduser().resolve()
    if path.is_file():
        files = [path]
    elif path.is_dir():
        pattern = "**/*" if recursive else "*"
        files = sorted(p for p in path.glob(pattern)
                       if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)
    else:
        return [IngestReport(source=str(path), doc_id=None, status="failed",
                             detail="path does not exist")]

    reports = []
    for f in files:
        if extensions and f.suffix.lower() not in [e.lower() for e in extensions]:
            continue
        auth = authority_override or infer_authority(str(f), "file")
        try:
            data = f.read_bytes()
            rep = ingest_bytes(str(f), data, settings=settings, registry=registry,
                               store=store, doc_type=_doctype_for_ext(f),
                               authority=auth, filename=f.name, force=force)
        except Exception as exc:  # keep ingesting the rest
            rep = IngestReport(source=str(f), doc_id=None, status="failed",
                               detail=f"{type(exc).__name__}: {exc}")
        reports.append(rep)
    return reports


def _doctype_for_ext(f: Path) -> str:
    return {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown",
            ".txt": "text", ".html": "web", ".htm": "web"}.get(f.suffix.lower(), "text")


# ---------------------------------------------------------------- web

def _same_site(url: str, base: str) -> bool:
    return httpx.URL(url).host == httpx.URL(base).host


def ingest_web(url: str, settings: Settings, registry: Registry,
               store: VectorStore, authority_override: str | None = None,
               recursive: bool = False, force: bool = False) -> list[IngestReport]:
    seen: set[str] = set()
    queue = [(url, 0)]
    reports: list[IngestReport] = []

    while queue and len(seen) < settings.web_max_pages:
        current, depth = queue.pop(0)
        norm = current.split("#")[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        auth = authority_override or infer_authority(current, "website")
        try:
            final_url, body = fetch_url(current, timeout=settings.request_timeout)
            ctype = body[:512].lower()
            if b"<html" not in ctype and not current.lower().endswith((".html", ".htm", "/")) \
                    and b"<body" not in ctype:
                # binary or non-HTML: index only obvious documents
                if final_url.lower().endswith(".pdf"):
                    rep = ingest_bytes(final_url, body, settings=settings,
                                       registry=registry, store=store,
                                       doc_type="pdf", authority=auth,
                                       filename=final_url.rsplit("/", 1)[-1] or "page.pdf",
                                       force=force)
                else:
                    rep = IngestReport(source=current, doc_id=None, status="skipped",
                                       detail="non-HTML response")
            else:
                html = body.decode("utf-8", errors="replace")
                blocks, title = extract_html(html)
                text_len = sum(len(b.text) for b in blocks)
                login_like = bool(re.search(
                    r"sign\s*in|log\s*in to|create an account", title or "", re.I))
                if text_len < 300 or (login_like and "diptrace" not in current.lower()):
                    rep = IngestReport(source=current, doc_id=None, status="skipped",
                                       detail=f"login/empty page ({text_len} chars)")
                    reports.append(rep)
                    continue
                rep = ingest_bytes(final_url, body, settings=settings,
                                   registry=registry, store=store,
                                   doc_type="web", authority=auth,
                                   filename=httpx.URL(final_url).path.strip("/").replace("/", "_") + ".html"
                                   or "index.html", force=force,
                                   title_hint=title)
                if recursive and depth < 2:
                    for link in re.findall(r'href=["\'](.*?)["\']', html, re.I):
                        if link.startswith(("mailto:", "javascript:", "#")):
                            continue
                        if link.startswith("//"):
                            link = "https:" + link
                        elif link.startswith("/"):
                            base = httpx.URL(final_url)
                            link = f"{base.scheme}://{base.host}{link}"
                        elif not link.startswith("http"):
                            continue
                        if _same_site(link, url) and "." not in httpx.URL(link).path.rsplit("/", 1)[-1]:
                            queue.append((link.split("#")[0], depth + 1))
        except Exception as exc:
            rep = IngestReport(source=current, doc_id=None, status="failed",
                               detail=f"{type(exc).__name__}: {exc}")
        reports.append(rep)
    return reports


# ---------------------------------------------------------------- youtube

def _yt_video_id(url: str) -> str | None:
    m = re.search(r"(?:watch\?v=|youtu\.be/)([\w\-]{11})", url)
    return m.group(1) if m else None


def ingest_youtube(url: str, settings: Settings, registry: Registry,
                   store: VectorStore, authority_override: str | None = None,
                   force: bool = False) -> list[IngestReport]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return [IngestReport(source=url, doc_id=None, status="failed",
                             detail="install extras: pip install -e '.[youtube]'")]

    video_ids: list[str] = []
    vid = _yt_video_id(url)
    if vid:
        video_ids = [vid]
    elif "playlist?list=" in url:
        video_ids = _yt_list_ids_ytdlp(url, settings)
    elif re.search(r"youtube\.com/@", url):
        video_ids = _yt_channel_ids_ytdlp(url.rstrip("/") + "/videos", settings)
    else:
        return [IngestReport(source=url, doc_id=None, status="failed",
                             detail="unrecognized YouTube URL")]

    api = YouTubeTranscriptApi()
    reports: list[IngestReport] = []
    for v in video_ids[:settings.youtube_max_videos]:
        page_url = f"https://www.youtube.com/watch?v={v}"
        try:
            fetched = api.fetch(v, languages=["ru", "en"])
            segments = [sn.text for sn in fetched]
            transcript = "\n".join(segments)
            title = ""
            try:
                _, oembed = fetch_url(
                    f"https://www.youtube.com/oembed?url={page_url}&format=json",
                    timeout=15)
                import json as _json
                title = _json.loads(oembed).get("title", "")
            except Exception:
                pass
            data = transcript.encode("utf-8")
            rep = ingest_bytes(page_url, data, settings=settings, registry=registry,
                               store=store, doc_type="youtube",
                               authority=authority_override or infer_authority(page_url, "youtube"),
                               filename=(title or v)[:80].replace("/", "_") + ".txt",
                               title_hint=title or f"YouTube video {v}",
                               force=force)
        except Exception as exc:
            rep = IngestReport(source=page_url, doc_id=None, status="failed",
                               detail=f"{type(exc).__name__}: {exc}")
        reports.append(rep)
    return reports


def _yt_channel_ids_ytdlp(channel_url: str, settings: Settings) -> list[str]:
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("channel ingestion needs yt-dlp: pip install -e '.[youtube]'")
    opts = {"quiet": True, "extract_flat": True,
            "playlistend": settings.youtube_max_videos}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    return [e["id"] for e in info.get("entries", []) if e.get("id")][:settings.youtube_max_videos]


def _yt_list_ids_ytdlp(playlist_url: str, settings: Settings) -> list[str]:
    return _yt_channel_ids_ytdlp(playlist_url, settings)


# ---------------------------------------------------------------- dispatch

_HANDLERS: dict = {}


def register_type(name: str, handler):
    """Extension point for new source types (github, kicad, gerber, odb++...).

    handler(source: SourceConfig, settings, registry, store, force) -> list[IngestReport]
    """
    _HANDLERS[name] = handler


def ingest_source_config(src: SourceConfig, settings: Settings, registry: Registry,
                         store: VectorStore, force: bool = False) -> list[IngestReport]:
    if src.kind == "directory":
        p = src.path
        if p and not Path(p).is_absolute():
            p = str((Path(__file__).resolve().parents[2] / p).resolve())
        return ingest_path(p or ".", settings, registry, store,
                           authority_override=src.authority,
                           extensions=src.extensions,
                           recursive=src.recursive, force=force)
    if src.kind == "file":
        p = src.path
        if p and not Path(p).is_absolute():
            p = str((Path(__file__).resolve().parents[2] / p).resolve())
        return ingest_path(p or ".", settings, registry, store,
                           authority_override=src.authority, force=force)
    if src.kind == "website":
        return ingest_web(src.url or "", settings, registry, store,
                          authority_override=src.authority,
                          recursive=src.recursive, force=force)
    if src.kind == "youtube":
        return ingest_youtube(src.url or "", settings, registry, store,
                              authority_override=src.authority, force=force)
    handler = _HANDLERS.get(src.kind)
    if handler is None:
        return [IngestReport(source=src.url or src.path or src.kind,
                             doc_id=None, status="failed",
                             detail=f"unknown source type: {src.kind}")]
    return handler(src, settings, registry, store, force)


def ingest_anywhere(source: str, settings: Settings, registry: Registry,
                    store: VectorStore, force: bool = False) -> list[IngestReport]:
    """MCP `knowledge_ingest`: local path or URL, auto-detected."""
    if source.startswith(("http://", "https://")):
        if YOUTUBE_RE.search(source):
            return ingest_youtube(source, settings, registry, store, force=force)
        return ingest_web(source, settings, registry, store, force=force)
    p = Path(source).expanduser()
    if p.is_dir():
        return ingest_path(str(p), settings, registry, store, force=force)
    if p.is_file():
        return ingest_path(str(p), settings, registry, store, force=force)
    return [IngestReport(source=source, doc_id=None, status="failed",
                         detail="not an existing local path or URL")]
