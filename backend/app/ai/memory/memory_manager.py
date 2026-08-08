"""The memory manager — single facade over all five memory stores.

Routing rules:
  * ``remember`` with an explicit ``memory_type`` goes straight to that store.
  * ``recall`` without a memory type searches semantic + organizational +
    procedural first (the durable "true facts"), then episodic history.
  * ``consolidate`` folds the current working memory ring into durable
    episodic/semantic entries and clears the ring.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.base import _query_entries, _store_entry
from app.ai.memory.episodic import EpisodicMemory, episodic_memory
from app.ai.memory.organizational import OrganizationalMemory, organizational_memory
from app.ai.memory.procedural import ProceduralMemory, procedural_memory
from app.ai.memory.semantic import SemanticMemory, semantic_memory
from app.ai.memory.working import WorkingMemory
from app.models.ai import AIMemory

_STORES: dict[str, Any] = {
    "episodic": episodic_memory,
    "semantic": semantic_memory,
    "procedural": procedural_memory,
    "organizational": organizational_memory,
}

VALID_TYPES = frozenset(_STORES) | {"working"}


class MemoryManager:
    def __init__(self) -> None:
        self.working = WorkingMemory()

    async def remember(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        content: str,
        memory_type: str = "semantic",
        kind: str = "fact",
        scope: str = "organization",
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.9,
        importance: int = 5,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AIMemory]:
        if memory_type not in VALID_TYPES:
            memory_type = "semantic"
        if memory_type == "working":
            self.working.push(
                organization_id=organization_id,
                user_id=user_id,
                role="assistant",
                content=content,
            )
            return None
        store = _STORES[memory_type]
        if isinstance(store, EpisodicMemory):
            return await store.record_event(
                db,
                organization_id=organization_id,
                event=content,
                scope=scope,
                subject_type=subject_type,
                subject_id=subject_id,
                user_id=user_id,
                source=source,
                importance=importance,
                metadata_json=metadata and str(metadata),
            )
        if isinstance(store, SemanticMemory):
            return await store.remember(
                db,
                organization_id=organization_id,
                fact=content,
                kind=kind,
                scope=scope,
                subject_type=subject_type,
                subject_id=subject_id,
                user_id=user_id,
                source=source,
                confidence=confidence,
                importance=importance,
                metadata_json=metadata and str(metadata),
            )
        if isinstance(store, ProceduralMemory):
            return await store.remember_procedure(
                db,
                organization_id=organization_id,
                procedure=content,
                scope=scope,
                user_id=user_id,
                source=source,
                confidence=confidence,
                importance=importance,
            )
        if isinstance(store, OrganizationalMemory):
            return await store.remember(
                db,
                organization_id=organization_id,
                fact=content,
                kind=kind,
                scope=scope,
                subject_type=subject_type,
                subject_id=subject_id,
                source=source,
                confidence=confidence,
                importance=importance,
            )
        return await _store_entry(
            db,
            organization_id=organization_id,
            memory_type="semantic",
            scope=scope,
            content=content,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            source=source,
            confidence=confidence,
            importance=importance,
            metadata_json=metadata and str(metadata),
        )

    async def recall(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        memory_type: Optional[str] = None,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        user_id: Optional[str] = None,
        text: Optional[str] = None,
        limit: int = 20,
    ) -> list[AIMemory]:
        if memory_type == "working":
            return [AIMemory(content=item["content"]) for item in self.working.recent(organization_id=organization_id, user_id=user_id)]  # type: ignore[attr-defined]
        if memory_type and memory_type in _STORES:
            store = _STORES[memory_type]
            return await store.recall(
                db,
                organization_id=organization_id,
                kind=kind if isinstance(store, SemanticMemory) else None,
                scope=scope if isinstance(store, (SemanticMemory, EpisodicMemory)) else None,
                subject_type=subject_type if isinstance(store, (SemanticMemory, EpisodicMemory)) else None,
                subject_id=subject_id if isinstance(store, (SemanticMemory, EpisodicMemory)) else None,
                user_id=user_id if isinstance(store, (SemanticMemory, EpisodicMemory)) else None,
                text=text,
                limit=limit,
            )
        durable_types = ("semantic", "organizational", "procedural", "episodic")
        results: list[AIMemory] = []
        for mtype in durable_types:
            if mtype == "episodic":
                results.extend(
                    await episodic_memory.recall(
                        db,
                        organization_id=organization_id,
                        scope=scope,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        user_id=user_id,
                        text=text,
                        limit=limit,
                    )
                )
            else:
                results.extend(
                    await _query_entries(
                        db,
                        organization_id=organization_id,
                        memory_type=mtype,
                        scope=scope,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        kind=kind,
                        user_id=user_id,
                        text=text,
                        limit=limit,
                    )
                )
        results.sort(key=lambda m: (m.importance or 0, (m.created_at or "")), reverse=True)
        return results[:limit]

    async def forget(self, db: AsyncSession, memory_id: str) -> bool:
        entry = await db.get(AIMemory, memory_id)
        if entry is None:
            return False
        await db.delete(entry)
        return True

    async def consolidate(
        self, db: AsyncSession, *, organization_id: str, user_id: Optional[str] = None
    ) -> dict[str, int]:
        ring = self.working.recent(organization_id=organization_id, user_id=user_id, limit=20)
        written = {"episodic": 0, "semantic": 0}
        for item in ring:
            if item["role"] != "assistant":
                continue
            await episodic_memory.record_event(
                db,
                organization_id=organization_id,
                event=item["content"],
                scope="user",
                user_id=user_id,
                source="conversation",
                importance=4,
            )
            written["episodic"] += 1
        self.working.clear(organization_id=organization_id, user_id=user_id)
        return written


memory_manager = MemoryManager()
