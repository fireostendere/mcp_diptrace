"""Configuration: config/settings.yaml defaults + env overrides + sources.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = SERVICE_ROOT / "config"

AUTHORITY_TIERS = (
    "datasheet",
    "appnote",
    "reference_design",
    "official_docs",
    "specification",
    "article",
    "community",
    "forum",
)


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines); never overrides real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    qdrant_url: str
    collection: str
    data_dir: Path
    embedding_model: str
    rerank_model: str
    rerank_candidates: int
    chunk_size: int
    chunk_overlap: int
    min_chunk_chars: int
    max_context_tokens: int
    chars_per_token: float
    authority_weights: dict[str, float]
    web_max_pages: int
    youtube_max_videos: int
    request_timeout: float

    def authority_weight(self, tier: str | None) -> float:
        if not tier:
            return 0.5
        return self.authority_weights.get(tier, 0.5)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "knowledge.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


def _get(raw: dict[str, Any], key: str, env: str, default):
    if env in os.environ:
        value = os.environ[env]
        proto = type(default)
        if proto is bool:
            return value.lower() in ("1", "true", "yes")
        try:
            return proto(value)
        except (TypeError, ValueError):
            return default
    return raw.get(key, default)


def load_settings() -> Settings:
    _load_dotenv(SERVICE_ROOT / ".env")
    cfg_path = CONFIG_DIR / "settings.yaml"
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    data_dir = Path(str(_get(raw, "data_dir", "KB_DATA_DIR", "./data")))
    if not data_dir.is_absolute():
        data_dir = SERVICE_ROOT / data_dir

    weights_raw = dict(raw.get("authority_weights") or {})
    weights = {t: float(weights_raw.get(t, w)) for t, w in (
        ("datasheet", 1.0), ("appnote", 0.95), ("reference_design", 0.95),
        ("official_docs", 0.85), ("specification", 0.85), ("article", 0.6),
        ("community", 0.35), ("forum", 0.15),
    )}

    return Settings(
        qdrant_url=str(_get(raw, "qdrant_url", "QDRANT_URL", "http://localhost:6333")),
        collection=str(_get(raw, "collection", "KB_COLLECTION", "engineering")),
        data_dir=data_dir.resolve(),
        embedding_model=str(_get(raw, "embedding_model", "KB_EMBEDDING_MODEL",
                                 "intfloat/multilingual-e5-large")),
        rerank_model=str(_get(raw, "rerank_model", "KB_RERANK_MODEL",
                              ("jinaai/jina-reranker-v2-base-multilingual"))),
        rerank_candidates=int(_get(raw, "rerank_candidates", "KB_RERANK_CANDIDATES", 32)),
        chunk_size=int(_get(raw, "chunk_size", "KB_CHUNK_SIZE", 1600)),
        chunk_overlap=int(_get(raw, "chunk_overlap", "KB_CHUNK_OVERLAP", 200)),
        min_chunk_chars=int(_get(raw, "min_chunk_chars", "KB_MIN_CHUNK_CHARS", 120)),
        max_context_tokens=int(_get(raw, "max_context_tokens", "KB_MAX_CONTEXT_TOKENS", 4000)),
        chars_per_token=float(_get(raw, "chars_per_token", "KB_CHARS_PER_TOKEN", 3.5)),
        authority_weights=weights,
        web_max_pages=int(_get(raw, "web_max_pages", "KB_WEB_MAX_PAGES", 40)),
        youtube_max_videos=int(_get(raw, "youtube_max_videos", "KB_YOUTUBE_MAX_VIDEOS", 30)),
        request_timeout=float(_get(raw, "request_timeout", "KB_REQUEST_TIMEOUT", 30)),
    )


@dataclass
class SourceConfig:
    kind: str                      # directory | file | website | youtube
    path: str | None = None
    url: str | None = None
    recursive: bool = True
    authority: str | None = None   # explicit override
    extensions: list[str] | None = None


def load_sources() -> list[SourceConfig]:
    path = CONFIG_DIR / "sources.yaml"
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for entry in raw.get("sources", []):
        auth = entry.get("authority")
        if auth and auth not in AUTHORITY_TIERS:
            raise ValueError(f"unknown authority tier: {auth!r} in sources.yaml")
        out.append(SourceConfig(
            kind=entry["type"],
            path=entry.get("path"),
            url=entry.get("url"),
            recursive=bool(entry.get("recursive", True)),
            authority=auth,
            extensions=entry.get("extensions"),
        ))
    return out
