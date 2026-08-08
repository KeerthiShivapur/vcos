"""Procedural memory — how work happens: sops, playbooks, recipes.

Used by the agent layers so the companion can answer "how do we do X here?"
with the company's actual documented procedures instead of generic advice.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.base import _query_entries, _store_entry
from app.models.ai import AIMemory


class ProceduralMemory:
    memory_type = "procedural"

    async def remember_procedure(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        procedure: str,
        name: Optional[str] = None,
        scope: str = "organization",
        user_id: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.9,
        importance: int = 6,
    ) -> AIMemory:
        return await _store_entry(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            scope=scope,
            content=procedure,
            kind="procedure",
            subject_type="procedure",
            subject_id=None,
            user_id=user_id,
            source=source,
            confidence=confidence,
            importance=importance,
            metadata_json=f'{{"name": {name!r}}}' if name else None,
        )

    async def recall(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        text: Optional[str] = None,
        limit: int = 20,
    ) -> list[AIMemory]:
        return await _query_entries(
            db,
            organization_id=organization_id,
            memory_type=self.memory_type,
            kind="procedure",
            text=text,
            limit=limit,
        )


procedural_memory = ProceduralMemory()
