"""Company memory service (Phase 19.1) — permanent organizational memory.

Memories capture decisions, lessons, milestones, policies, innovations and
institutional knowledge so nothing important is ever forgotten. Memory recall
surfaces pinned and high-importance entries, and memories are searchable
through universal search.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import CompanyMemory, MEMORY_TYPES

MEMORY_TYPES_SET = set(MEMORY_TYPES)
IMPORTANCE_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class MemoryService:
    async def record(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        memory_type: str,
        title: str,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
        importance: str = "medium",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        source_event: Optional[str] = None,
        recorded_by: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if memory_type not in MEMORY_TYPES_SET:
            raise ValueError(f"memory_type must be one of {MEMORY_TYPES}")
        if importance not in IMPORTANCE_WEIGHT:
            raise ValueError(f"importance must be one of {list(IMPORTANCE_WEIGHT)}")
        row = CompanyMemory(
            organization_id=organization_id,
            memory_type=memory_type,
            title=title,
            content=content,
            tags=tags or [],
            importance=importance,
            entity_type=entity_type,
            entity_id=entity_id,
            source_event=source_event,
            recorded_by=recorded_by,
            occurred_at=ensure_aware(occurred_at or utcnow()),
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="memory.recorded", organization_id=organization_id,
            payload={
                "memory_id": row.id,
                "memory_type": memory_type,
                "importance": importance,
                "title": title[:120],
            },
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        memory_type: Optional[str] = None,
        importance: Optional[str] = None,
        pinned: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(CompanyMemory).where(CompanyMemory.organization_id == organization_id)
        if memory_type:
            stmt = stmt.where(CompanyMemory.memory_type == memory_type)
        if importance:
            stmt = stmt.where(CompanyMemory.importance == importance)
        if pinned is not None:
            stmt = stmt.where(CompanyMemory.pinned.is_(pinned))
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    CompanyMemory.title.ilike(pattern),
                    CompanyMemory.content.ilike(pattern),
                )
            )
        rows = (
            await db.execute(stmt.order_by(CompanyMemory.occurred_at.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, organization_id: str, memory_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.id == memory_id,
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def set_pinned(
        self, db: AsyncSession, organization_id: str, memory_id: str, pinned: bool = True
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.id == memory_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.pinned = pinned
        await db.flush()
        return self.serialize(row)

    async def delete(self, db: AsyncSession, organization_id: str, memory_id: str) -> bool:
        row = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.id == memory_id,
                )
            )
        ).scalars().first()
        if row is None:
            return False
        await db.delete(row)
        await db.flush()
        return True

    async def recall(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        topic: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Recall the most relevant memories (pinned + high importance first)."""
        rows = await self.list(db, organization_id, search=topic, limit=limit)
        rows.sort(key=lambda m: (m["pinned"], IMPORTANCE_WEIGHT.get(m["importance"], 2)), reverse=True)
        await publish_background_event(
            db, name="memory.recalled", organization_id=organization_id,
            payload={"topic": topic or "", "recalled": len(rows)},
        )
        return {"total": len(rows), "memories": rows[:limit]}

    async def capture_from_decision(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        decision: dict[str, Any],
        lessons: Optional[list[str]] = None,
        commit: bool = False,
    ) -> list[dict[str, Any]]:
        """Auto-capture a decision and its lessons as company memory."""
        out = []
        memory = await self.record(
            db,
            organization_id=organization_id,
            memory_type="decision",
            title=f"Decision: {decision.get('decision', 'Untitled')}",
            content=f"Category: {decision.get('category', 'strategy')}. "
                    f"Reason: {decision.get('reason', '')} "
                    f"Verdict: {decision.get('verdict', 'unknown')}.",
            tags=["decision"] + (decision.get("category") or []),
            importance="high",
            entity_type="decision",
            entity_id=decision.get("id"),
            source_event="decision.analyzed",
        )
        out.append(memory)
        for lesson in lessons or []:
            out.append(
                await self.record(
                    db,
                    organization_id=organization_id,
                    memory_type="lesson",
                    title=f"Lesson: {lesson[:120]}",
                    content=lesson,
                    tags=["lesson"],
                    importance="medium",
                    entity_type="decision",
                    entity_id=decision.get("id"),
                    source_event="decision.analyzed",
                )
            )
        if commit:
            await db.commit()
        return out

    def serialize(self, row: CompanyMemory) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "memory_type": row.memory_type,
            "title": row.title,
            "content": row.content,
            "tags": row.tags or [],
            "importance": row.importance,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "source_event": row.source_event,
            "recorded_by": row.recorded_by,
            "pinned": row.pinned,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


memory_service = MemoryService()
