"""Phase 20 — Universal context engine.

Context flows automatically between modules: meeting -> project -> knowledge
-> tasks -> learning -> community -> dashboard -> AI memory. The engine
assembles context bundles for any entity and produces an organization-wide
"what happened" digest.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.memory.context_service import context_service
from app.memory.memory_service import memory_service
from app.memory.timeline_service import timeline_service
from app.models.company_memory import CompanyMemory
from app.models.knowledge import Document
from app.models.meeting import Meeting
from app.models.notification import Event as EventRow
from app.models.task import Task


class ContextEngine:
    """Universal context flow across every entity type."""

    async def flow(
        self, db: AsyncSession, organization_id: str, entity_type: str, entity_id: str
    ) -> dict[str, Any]:
        bundle = await context_service.flow(db, organization_id, entity_type, entity_id)
        if bundle is None:
            return {"entity_type": entity_type, "entity_id": entity_id, "related": {}, "summary": None}
        return bundle

    async def digest(
        self, db: AsyncSession, organization_id: str, *, days: int = 1
    ) -> dict[str, Any]:
        """What happened across the whole organization recently."""
        since = utcnow() - timedelta(days=days)
        events = (
            await db.execute(
                select(EventRow)
                .where(
                    EventRow.organization_id == organization_id,
                    EventRow.created_at >= since,
                )
                .order_by(EventRow.created_at.desc())
                .limit(50)
            )
        ).scalars().all()
        timeline = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.created_at >= since
                )
            )
        ).scalar() or 0
        documents = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id, Document.created_at >= since
                )
            )
        ).scalar() or 0
        meetings = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id, Meeting.created_at >= since
                )
            )
        ).scalar() or 0
        memories = (
            await db.execute(
                select(func.count(CompanyMemory.id)).where(
                    CompanyMemory.organization_id == organization_id,
                    CompanyMemory.created_at >= since,
                )
            )
        ).scalar() or 0
        timeline_rows = await timeline_service.list(
            db, organization_id, limit=10
        )
        return {
            "since": since.isoformat(),
            "events": [
                {
                    "id": r.id, "name": r.name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in events
            ],
            "new_tasks": timeline,
            "new_documents": documents,
            "new_meetings": meetings,
            "new_memories": memories,
            "timeline_headlines": timeline_rows[:10],
        }


context_engine = ContextEngine()
