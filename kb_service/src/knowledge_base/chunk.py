"""Structure-aware chunker: respects sections (headings), pages, paragraphs.

Chunks never span a section boundary; oversized sections are split on
sentences with a configurable overlap tail. Sizes are in characters.
"""
from __future__ import annotations

from dataclasses import dataclass

from .extract import Block, split_sentences


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    section: str | None
    index: int = 0  # filled by caller


def _pack(sentences: list[str], size: int, overlap: int):
    """Split sentences into pieces of <= size chars, each piece (after the
    first) starting with an overlap tail of the previous one."""
    pieces: list[list[str]] = []
    cur: list[str] = []
    total = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(s) > size:
            if cur:
                pieces.append(cur)
                cur, total = [], 0
            # hard-split pathological sentence
            for i in range(0, len(s), size):
                pieces.append([s[i:i + size]])
            continue
        if cur and total + len(s) + 1 > size:
            pieces.append(cur)
            tail: list[str] = []
            t = 0
            for prev in reversed(cur):
                if t + len(prev) + 1 > overlap:
                    break
                tail.insert(0, prev)
                t += len(prev) + 1
            cur, total = list(tail), t
        cur.append(s)
        total += len(s) + 1
    if cur:
        pieces.append(cur)

    out = [" ".join(p).strip() for p in pieces]
    return [p for p in out if p]


def chunk_blocks(blocks: list[Block], chunk_size: int = 1600,
                 overlap: int = 200, min_chars: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []

    section: str | None = None
    sec_text: list[str] = []
    sec_pages: set[int] = set()

    def flush_section():
        nonlocal sec_text, sec_pages, section
        text = " ".join(sec_text).strip()
        pages = sorted(sec_pages)
        p_start = pages[0] if pages else 0
        p_end = pages[-1] if pages else 0
        if not text:
            sec_text, sec_pages = [], set()
            return
        if len(text) <= chunk_size * 1.15:
            chunks.append(Chunk(text=text, page_start=p_start,
                                page_end=p_end, section=section))
        else:
            pieces = _pack(split_sentences(text), chunk_size, overlap)
            n = len(pieces)
            for i, piece in enumerate(pieces):
                # page attribution proportional to position inside the section
                lo = int(i / n * (p_end - p_start + 1))
                hi = int((i + 1) / n * (p_end - p_start + 1))
                chunks.append(Chunk(text=piece, page_start=p_start + max(lo, 0),
                                    page_end=p_start + max(hi - 1, 0) if hi > lo else p_start + lo,
                                    section=section))
        sec_text, sec_pages = [], set()

    for block in blocks:
        if block.kind == "heading":
            flush_section()
            section = block.text.strip()[:200]
            continue
        if block.text.strip():
            sec_text.append(block.text.strip())
            sec_pages.add(max(block.page, 0))
    flush_section()

    # merge tiny trailing chunk into its predecessor within the same section
    if len(chunks) >= 2:
        last, prev = chunks[-1], chunks[-2]
        if len(last.text) < min_chars and last.section == prev.section \
                and len(prev.text) + len(last.text) < chunk_size * 1.3:
            prev.text = prev.text.rstrip() + " " + last.text
            prev.page_end = max(prev.page_end, last.page_end)
            chunks.pop()

    for i, c in enumerate(chunks):
        c.index = i
    return chunks
