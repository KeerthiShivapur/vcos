"""Phase 20 — Company memory engine (permanent organizational memory).

One memory for the whole company: decisions, lessons, milestones, policies,
innovations and outcomes are never forgotten, and every meaningful event is
recorded into the company timeline so history stays traversable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.kernel.event_engine import event_engine
from app.memory.memory_service import memory_service
from app.memory.timeline_service import timeline_service


class MemoryEngine:
    """Unified memory + timeline layer over the persistent stores."""

    async def record_memory(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        memory_type: str = "institutional",
        title: str,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
        importance: str = "medium",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        source_event: Optional[str] = None,
        recorded_by: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        pin: bool = False,
    ) -> dict[str, Any]:
        row = await memory_service.record(
            db,
            organization_id=organization_id,
            memory_type=memory_type,
            title=title,
            content=content,
            tags=tags,
            importance=importance,
            entity_type=entity_type,
            entity_id=entity_id,
            source_event=source_event,
            recorded_by=recorded_by,
            occurred_at=occurred_at,
        )
        if pin:
            await memory_service.set_pinned(db, organization_id, row["id"], pinned=True)
        await event_engine.publish(
            db, organization_id, "memory.updated",
            payload={"memory_id": row["id"], "memory_type": memory_type},
        )
        return row

    async def list_memories(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        memory_type: Optional[str] = None,
        importance: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        rows = await memory_service.list(
            db, organization_id,
            memory_type=memory_type, importance=importance, search=search, limit=limit,
        )
        return {"total": len(rows), "memories": rows}

    async def recall(self, db: AsyncSession, organization_id: str, topic: Optional[str] = None) -> dict[str, Any]:
        return await memory_service.recall(db, organization_id, topic=topic)

    async def record_timeline(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        event_type: str,
        title: str,
        category: str = "system",
        detail: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        row = await timeline_service.record(
            db,
            organization_id=organization_id,
            event_type=event_type,
            title=title,
            category=category,
            detail=detail,
            occurred_at=occurred_at,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )
        return row

    async def list_timeline(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        category: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        rows = await timeline_service.list(
            db, organization_id, category=category, search=search, limit=limit
        )
        return {"total": len(rows), "entries": rows}

    async def timeline_summary(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        return await timeline_service.summary(db, organization_id)

    async def capture(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        event_type: str,
        title: str,
        category: str = "system",
        detail: Optional[str] = None,
        memory_type: str = "institutional",
        importance: str = "medium",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record the same event into the timeline AND as permanent memory."""
        now = utcnow()
        timeline = await self.record_timeline(
            db, organization_id,
            event_type=event_type, title=title, category=category, detail=detail,
            occurred_at=now, actor_id=actor_id,
            entity_type=entity_type, entity_id=entity_id,
            metadata={"memory": True},
        )
        memory = await self.record_memory(
            db, organization_id,
            memory_type=memory_type, title=title, content=detail,
            importance=importance, entity_type=entity_type, entity_id=entity_id,
            source_event=event_type, occurred_at=now,
        )
        return {"timeline_id": timeline["id"], "memory_id": memory["id"], "title": title}


memory_engine = MemoryEngine()
