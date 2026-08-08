"""Organizational learning loop — every activity becomes learning.

Completed initiatives are converted into lessons, knowledge and AI memory that
improve future projects. Each loop is recorded as a learning cycle and emits
``learning.completed``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import CompanyMemory
from app.models.decision_history import DecisionHistory
from app.models.learning_cycle import LearningCycle
from app.models.project import Project


class LearningLoop:
    async def run(
        self, db: AsyncSession, organization_id: str, *, limit: int = 5, commit: bool = False
    ) -> dict[str, Any]:
        now = utcnow()
        cycles: list[dict[str, Any]] = []

        completed_projects = (
            await db.execute(
                select(Project)
                .where(
                    Project.organization_id == organization_id,
                    Project.status.in_(["completed", "done", "closed"]),
                )
                .order_by(Project.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        for project in completed_projects:
            already = (
                await db.execute(
                    select(LearningCycle.id).where(
                        LearningCycle.organization_id == organization_id,
                        LearningCycle.source_type == "project",
                        LearningCycle.source_id == project.id,
                        LearningCycle.stage == "completed",
                    )
                )
            ).scalars().first()
            if already is not None:
                continue
            cycle = await self._cycle_for_project(db, organization_id, project)
            cycles.append(cycle)

        if cycles and commit:
            await db.commit()
        return {"total": len(cycles), "cycles": cycles}

    async def _cycle_for_project(
        self, db: AsyncSession, organization_id: str, project: Project
    ) -> dict[str, Any]:
        decisions = (
            await db.execute(
                select(DecisionHistory)
                .where(
                    DecisionHistory.organization_id == organization_id,
                    DecisionHistory.title.ilike(f"%{project.name[:40]}%"),
                )
                .order_by(DecisionHistory.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
        lessons = []
        for decision in decisions:
            lessons.extend(decision.lessons or [])
        if not lessons:
            lessons.append("Structured delivery and regular reviews keep projects on track.")

        insights = [
            {"source": "decision", "title": d.title, "status": d.status, "outcome": d.outcome}
            for d in decisions
        ]
        if not insights:
            insights.append({"source": "project", "title": project.name, "status": "completed"})

        memory_ids: list[str] = []
        from app.memory.memory_service import memory_service

        for lesson in lessons[:3]:
            memory = await memory_service.record(
                db,
                organization_id=organization_id,
                memory_type="lesson",
                title=f"Lesson: {lesson[:120]}",
                content=lesson,
                tags=["lesson", "learning_loop"],
                importance="medium",
                entity_type="project",
                entity_id=project.id,
                source_event="learning.completed",
            )
            memory_ids.append(memory["id"])
        for insight in insights[:2]:
            if insight["source"] != "decision":
                continue
            memory = await memory_service.record(
                db,
                organization_id=organization_id,
                memory_type="milestone",
                title=f"Milestone: {insight['title'][:120]}",
                content=f"Outcome: {insight.get('outcome') or insight.get('status')}",
                tags=["milestone", "learning_loop"],
                importance="medium",
                entity_type="project",
                entity_id=project.id,
                source_event="learning.completed",
            )
            memory_ids.append(memory["id"])

        row = LearningCycle(
            organization_id=organization_id,
            cycle=f"project:{project.status}",
            stage="completed",
            source_type="project",
            source_id=project.id,
            insights=insights,
            lessons=lessons,
            memory_ids=memory_ids,
            started_at=now - timedelta(days=30),
            completed_at=now,
            source_event="learning.completed",
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="learning.completed", organization_id=organization_id,
            payload={"cycle_id": row.id, "source_id": project.id, "lessons": len(lessons)},
        )
        return {
            "id": row.id, "cycle": row.cycle, "source_type": "project",
            "source_id": project.id, "lessons": lessons,
            "insights": insights, "memory_ids": memory_ids,
        }

    async def list(
        self, db: AsyncSession, organization_id: str, *, limit: int = 50
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(LearningCycle)
                .where(LearningCycle.organization_id == organization_id)
                .order_by(LearningCycle.completed_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total": len(rows),
            "cycles": [
                {
                    "id": r.id, "cycle": r.cycle, "stage": r.stage,
                    "source_type": r.source_type, "source_id": r.source_id,
                    "insights": r.insights or [], "lessons": r.lessons or [],
                    "memory_ids": r.memory_ids or [],
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in rows
            ],
        }


learning_loop = LearningLoop()
