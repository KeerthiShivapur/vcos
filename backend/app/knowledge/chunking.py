"""Slice 4D.2 — deterministic content chunking for semantic knowledge search.

Chunking never involves an LLM: text is split on paragraph and sentence
boundaries with a hard ``max_chars`` ceiling and a fixed overlap so each chunk
stays locally coherent. The output is fully deterministic — the same source
text always yields the same chunk list and the same content hashes, which is
what makes idempotent re-indexing (and stale-chunk deletion) possible.
"""

import hashlib
import re

MAX_CHARS = 1200
OVERLAP = 120
MAX_CHUNKS_PER_ENTITY = 100

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\s*[-*]\s+|\n+")


def content_hash(text: str) -> str:
    """Stable sha256 over the normalized chunk text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    *,
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP,
    max_chunks: int = MAX_CHUNKS_PER_ENTITY,
) -> list[str]:
    """Split ``text`` into deterministic, size-capped chunks.

    Paragraph boundaries (blank lines / list markers / line breaks) are the
    preferred split points; a long run of text is broken at sentence
    boundaries; an over-long single "sentence" is hard-split. Each chunk
    carries ``overlap`` trailing characters of the previous chunk so no
    boundary-bridge information is lost. Output is capped at ``max_chunks``.
    """
    if not text or not text.strip():
        return []
    normalized = re.sub(r"[ \t]+", " ", text.strip())
    parts = [part.strip() for part in _SENTENCE_RE.split(normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + " " + part).strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(part) <= max_chars:
            current = part
            continue
        current = ""
        remaining = part
        while len(remaining) > max_chars:
            chunks.append(remaining[:max_chars])
            remaining = remaining[max_chars - overlap :] if overlap else ""
        if remaining:
            current = remaining
    if current:
        chunks.append(current)
    if overlap and chunks:
        for index in range(len(chunks) - 1):
            tail = chunks[index][-overlap:]
            room = max_chars - len(tail) - 1
            chunks[index + 1] = (tail + " " + chunks[index + 1][:room]).strip()
    return chunks[:max_chunks]
