"""Text extraction into structured blocks: [{page, kind: heading|para, text}]."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx

KNOWN_SECTIONS = {
    "description", "features", "feature", "applications", "pin configuration",
    "pin functions", "pin descriptions", "pin description",
    "absolute maximum ratings", "electrical characteristics",
    "thermal information", "thermal properties", "typical application",
    "typical applications", "application information", "application circuit",
    "layout guidelines", "layout recommendation", "layout recommendations",
    "pcb layout", "board layout", "functional block diagram", "block diagram",
    "functional description", "detailed description", "theory of operation",
    "package information", "package outline", "ordering information",
    "revision history", "design requirements", "external components",
    "inductor selection", "capacitor selection", "compensation", "feedback",
    "grounding", "thermal design", "power dissipation", "schematic",
}

HEADING_RE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ./&()+,\-]{2,79}$")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Block:
    page: int          # 1-based; 0 for non-paginated docs
    kind: str          # heading | para
    text: str


def split_sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT_RE.split(text.strip()) if s.strip()]


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    low = stripped.lower().rstrip(":")
    if low in KNOWN_SECTIONS:
        return True
    if HEADING_RE.match(stripped) and len(stripped.split()) <= 12 and not stripped.endswith((".", ",", ";")):
        # numbered headings like "7.4 Layout Guidelines" or ALL CAPS titles
        if stripped.startswith(tuple("0123456789")) or stripped.isupper():
            return True
    return False


def clean_text(text: str) -> str:
    """De-hyphenate line wraps and collapse whitespace."""
    text = text.replace("\u00ad", "")                      # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # word-\nwrap -> wordwrap
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> tuple[list[Block], int]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages_text: list[list[str]] = []
    for pageno, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        pages_text.append([ln.strip() for ln in raw.splitlines()])

    # Drop repeated headers/footers: lines recurring on >= half the pages (pdf>=6p).
    npages = len(pages_text)
    if npages >= 6:
        freq: dict[str, int] = {}
        for lines in pages_text:
            seen = set()
            for ln in lines:
                norm = re.sub(r"\d+", "#", ln)[:60]
                if 0 < len(ln) < 80 and norm not in seen:
                    seen.add(norm)
                    freq[norm] = freq.get(norm, 0) + 1
        boilerplate = {norm for norm, n in freq.items()
                       if n >= max(3, npages // 2)}
        if boilerplate:
            for lines in pages_text:
                lines[:] = [ln for ln in lines
                            if re.sub(r"\d+", "#", ln)[:60] not in boilerplate]

    blocks: list[Block] = []
    for pageno, lines in enumerate(pages_text, start=1):
        para: list[str] = []
        for ln in lines:
            if not ln:
                continue
            if _is_heading(ln):
                if para:
                    blocks.append(Block(pageno, "para", " ".join(para)))
                    para = []
                blocks.append(Block(pageno, "heading", ln))
            else:
                para.append(ln)
        if para:
            blocks.append(Block(pageno, "para", " ".join(para)))
    blocks = [b for b in (Block(b.page, b.kind, clean_text(b.text)) for b in blocks) if b.text]
    return blocks, npages


def extract_markdown(path_or_text, base_page: int = 1) -> list[Block]:
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8", errors="replace")
    else:
        text = str(path_or_text)
    blocks: list[Block] = []
    para: list[str] = []
    def flush():
        if para:
            joined = clean_text(" ".join(para))
            if joined:
                blocks.append(Block(base_page, "para", joined))
            para.clear()
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            flush(); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush(); blocks.append(Block(base_page, "heading", m.group(2).strip()))
            continue
        if re.match(r"^[-*]{3,}$", s):   # horizontal rule
            flush(); continue
        para.append(re.sub(r"`{1,3}", "", s))
    flush()
    return blocks


def extract_plain_text(path: Path) -> list[Block]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[Block] = []
    for chunk in re.split(r"\n\s*\n", text):
        c = clean_text(chunk.replace("\n", " "))
        if c:
            first = c.split(". ", 1)[0][:80]
            kind = "heading" if len(first) < 75 and "\n" not in chunk and len(chunk.splitlines()) == 1 \
                   and not c.endswith((".", ",", ";", ":")) else "para"
            blocks.append(Block(0, kind, c))
    return blocks


class _HTMLText(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form"}
    _HEADINGS = {f"h{i}" for i in range(1, 7)}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.title = ""
        self._buf: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._HEADINGS:
            self._flush()
            self._in_heading = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._HEADINGS:
            self._flush_heading()
        elif tag in {"p", "div", "li", "section", "article", "br"}:
            self._flush()

    _in_heading = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        t = " ".join(data.split())
        if t:
            self._buf.append(t)

    def _flush(self):
        if self._buf:
            text = clean_text(" ".join(self._buf))
            if text:
                self.blocks.append(Block(0, "para", text))
        self._buf = []

    def _flush_heading(self):
        text = clean_text(" ".join(self._buf))
        self._buf = []
        if text:
            self.blocks.append(Block(0, "heading", text))
        self._in_heading = False


def extract_html(html: str, title_fallback: str = "") -> tuple[list[Block], str]:
    parser = _HTMLText()
    try:
        parser.feed(html)
    except Exception:
        pass
    parser._flush()
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        title = clean_text(re.sub(r"<[^>]+>", "", m.group(1)))[:200]
    if not title:
        title = title_fallback
    blocks = [b for b in parser.blocks if len(b.text) > 1]
    return blocks, title


def fetch_url(url: str, timeout: float = 30.0) -> tuple[str, bytes]:
    """GET a URL; returns (final_url, body_bytes)."""
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) kb-rag/0.1 (engineering knowledge indexer)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return str(resp.url), resp.content
