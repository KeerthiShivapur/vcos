"""Shared helpers for the Phase 7.2 memory stores."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIMemory

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "about", "from",
    "this", "that", "these", "those", "what", "when", "where", "which",
    "who", "whom", "how", "why", "can", "could", "would", "should", "will",
    "shall", "may", "might", "must", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "of", "to", "in",
    "on", "at", "by", "i", "me", "my", "we", "our", "you", "your", "it",
    "its", "they", "them", "their", "he", "she", "his", "her", "please",
    "tell", "show", "give", "find", "help", "like", "want", "need", "theres",
    "there", "just", "also", "not", "no", "yes", "ok", "okay", "thanks",
}


def keywords(text: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_\-]{3,}", (text or "").lower())
    seen: list[str] = []
    for token in tokens:
        if token in STOPWORDS or token in seen:
            continue
        seen.append(token)
        if len(seen) >= limit:
            break
    return seen


async def _store_entry(
    db: AsyncSession,
    *,
    organization_id: str,
    memory_type: str,
    scope: str,
    content: str,
    kind: str,
    subject_type: Optional[str] = None,
    subject_id: Optional[str] = None,
    user_id: Optional[str] = None,
    source: Optional[str] = None,
    confidence: float = 0.9,
    importance: int = 5,
    metadata_json: Optional[str] = None,
) -> AIMemory:
    entry = AIMemory(
        organization_id=organization_id,
        user_id=user_id,
        memory_type=memory_type,
        scope=scope,
        subject_type=subject_type,
        subject_id=subject_id,
        kind=kind,
        content=content,
        source=source,
        confidence=confidence,
        importance=importance,
        metadata_json=metadata_json,
    )
    db.add(entry)
    await db.flush()
    return entry


async def _query_entries(
    db: AsyncSession,
    *,
    organization_id: str,
    memory_type: Optional[str] = None,
    scope: Optional[str] = None,
    subject_type: Optional[str] = None,
    subject_id: Optional[str] = None,
    kind: Optional[str] = None,
    user_id: Optional[str] = None,
    text: Optional[str] = None,
    min_importance: Optional[int] = None,
    limit: int = 20,
) -> list[AIMemory]:
    filters = [AIMemory.organization_id == organization_id]
    if memory_type:
        filters.append(AIMemory.memory_type == memory_type)
    if scope:
        filters.append(AIMemory.scope == scope)
    if subject_type:
        filters.append(AIMemory.subject_type == subject_type)
    if subject_id:
        filters.append(AIMemory.subject_id == subject_id)
    if kind:
        filters.append(AIMemory.kind == kind)
    if user_id:
        filters.append(AIMemory.user_id == user_id)
    if min_importance is not None:
        filters.append(AIMemory.importance >= min_importance)
    if text:
        terms = keywords(text, limit=8)
        if terms:
            like = [AIMemory.content.ilike(f"%{term}%") for term in terms]
            like.append(AIMemory.kind.ilike(f"%{text.lower()}%"))
            filters.append(or_(*like))
    result = await db.execute(
        select(AIMemory)
        .where(*filters)
        .order_by(AIMemory.importance.desc(), AIMemory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
