"""Organizational memory — how the company works: structure, roles, norms.

Captures departments, reporting lines, team norms and culture so the
companion can answer "who owns X", "who does Y report to" and "how do we
behave here" from durable memory rather than stale guesses.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.base import _query_entries, _store_entry
from app.models.ai import AIMemory


class OrganizationalMemory:
    memory_type = "organizational"

    async def remember(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        fact: str,
        kind: str = "structure",
        scope: str = "organization",
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.9,
        importance: int = 6,
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
            source=source,
            confidence=confidence,
            importance=importance,
        )

    async def recall(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kind: Optional[str] = None,
        text: Optional[str] = None,
        limit: int = 20,
    ) -> list[AIMemory]:
        return await _query_entries(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            kind=kind,
            text=text,
            limit=limit,
        )


organizational_memory = OrganizationalMemory()
