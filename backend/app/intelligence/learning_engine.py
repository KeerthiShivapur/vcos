"""Phase 9.15 — Organizational learning engine.

VCOS learns. Lessons are captured from completed and failed work, decisions,
and repeated patterns, then folded into AI memory so the AI Companion and
future recommendations benefit from organizational history.

record() stores a LearningEvent and, when the lesson is substantive, upserts
a fact into AIMemory (kind="lesson").
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIMemory
from app.models.intelligence import LearningEvent

logger = logging.getLogger("vcos.intelligence.learning")


class LearningEngine:
    async def record(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event_type: str,
        title: str,
        detail: Optional[str] = None,
        lesson: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        memory: bool = True,
    ) -> LearningEvent:
        row = LearningEvent(
            organization_id=organization_id,
            event_type=event_type,
            title=title,
            detail=detail,
            lesson=lesson,
            entity_type=entity_type,
            entity_id=entity_id,
            tags_json=json.dumps(tags or []),
        )
        db.add(row)
        await db.flush()
        if memory and lesson:
            existing = (
                await db.execute(
                    select(AIMemory).where(
                        AIMemory.organization_id == organization_id,
                        AIMemory.kind == "lesson",
                        AIMemory.content == lesson,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    AIMemory(
                        organization_id=organization_id,
                        user_id=None,
                        memory_type="organizational",
                        scope="organization",
                        subject_type=entity_type,
                        subject_id=entity_id,
                        kind="lesson",
                        content=lesson,
                        source=f"learning:{event_type}",
                        confidence=0.85,
                        importance=6,
                        metadata_json=json.dumps({"event_type": event_type, "title": title, "tags": tags or []}),
                    )
                )
        from app.events.publisher import publish_background_event

        await publish_background_event(
            db,
            name="learning.recorded",
            organization_id=organization_id,
            payload={"event_type": event_type, "title": title[:200]},
        )
        return row

    async def lessons(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        filters = [LearningEvent.organization_id == organization_id]
        if event_type:
            filters.append(LearningEvent.event_type == event_type)
        rows = (
            await db.execute(
                select(LearningEvent).where(*filters).order_by(LearningEvent.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "title": r.title,
                "detail": r.detail,
                "lesson": r.lesson,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "tags": r.tags,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func

        rows = (
            await db.execute(
                select(LearningEvent.event_type, func.count(LearningEvent.id))
                .where(LearningEvent.organization_id == organization_id)
                .group_by(LearningEvent.event_type)
            )
        ).all()
        total = sum(count for _, count in rows)
        return {"total": total, "by_type": {t: c for t, c in rows}}


learning_engine = LearningEngine()
