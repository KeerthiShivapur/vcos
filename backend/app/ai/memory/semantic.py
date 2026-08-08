"""Semantic memory — what is true: facts, preferences, decisions, insights.

The default store for general knowledge extracted from conversations,
documents and user feedback. ``kind`` distinguishes the flavor:
``fact | preference | decision | insight | summary | relation``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.base import _query_entries, _store_entry
from app.models.ai import AIMemory


class SemanticMemory:
    memory_type = "semantic"

    async def remember(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        fact: str,
        kind: str = "fact",
        scope: str = "organization",
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.9,
        importance: int = 5,
        metadata_json: Optional[str] = None,
    ) -> AIMemory:
        return await _store_entry(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            scope=scope,
            content=fact,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            source=source,
            confidence=confidence,
            importance=importance,
            metadata_json=metadata_json,
        )

    async def recall(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_id: Optional[str] = None,
        text: Optional[str] = None,
        limit: int = 20,
    ) -> list[AIMemory]:
        return await _query_entries(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            scope=scope,
            subject_type=subject_type,
            subject_id=subject_id,
            kind=kind,
            user_id=user_id,
            text=text,
            limit=limit,
        )


semantic_memory = SemanticMemory()
