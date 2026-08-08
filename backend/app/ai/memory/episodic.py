"""Episodic memory — what happened: events, experiences, meeting outcomes.

Writes land in ``ai_memories`` with ``memory_type=episodic`` and a ``scope``
that keeps them organized per organization, per user, or per meeting/project.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.base import _query_entries, _store_entry
from app.models.ai import AIMemory


class EpisodicMemory:
    memory_type = "episodic"

    async def record_event(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event: str,
        scope: str = "organization",
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source: Optional[str] = None,
        importance: int = 5,
        metadata_json: Optional[str] = None,
    ) -> AIMemory:
        return await _store_entry(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            scope=scope,
            content=event,
            kind="event",
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            source=source,
            confidence=1.0,
            importance=importance,
            metadata_json=metadata_json,
        )

    async def recall(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
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
            user_id=user_id,
            text=text,
            limit=limit,
        )


episodic_memory = EpisodicMemory()
