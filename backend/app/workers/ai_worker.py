"""AI worker — fills AI summaries where the AI gateway is unavailable.

Projects, tasks, and meetings expose an `ai_summary` column. When the AI
provider is "none" (or offline), this worker generates deterministic,
rule-based summaries from real data so the surface always has content. When
an AI provider is configured, the gateway path in the services takes over
and this worker only backfills gaps.

Run standalone: python -m app.workers.ai_worker
"""

import asyncio
import logging

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAttendee
from app.models.project import Milestone, Project
from app.models.task import Task

logger = logging.getLogger("vcos.workers.ai")


def _project_summary(db_row, task_total: int, completed: int) -> str:
    milestones = db_row.milestones_total
    return (
        f"{db_row.name} ({db_row.code}) — {completed}/{task_total} tasks completed"
        + (f", {milestones} milestone(s)" if milestones else "")
        + f". Status: {db_row.status}."
    )


def _task_summary(task: Task) -> str:
    parts = [f"{task.title} — {task.status}"]
    if task.assignee_id:
        parts.append(f"assigned to {task.assignee_id}")
    if task.progress:
        parts.append(f"{task.progress}% progress")
    if task.due_date:
        parts.append(f"due {task.due_date}")
    return " · ".join(parts) + "."


def _meeting_summary(meeting: Meeting, attendee_names: list[str]) -> str:
    return (
        f"{meeting.title} ({meeting.meeting_type}, {meeting.status})"
        + (f" — attendees: {', '.join(attendee_names)}" if attendee_names else "")
        + "."
    )


async def run_once() -> int:
    settings = get_settings()
    if settings.AI_PROVIDER not in (None, "", "none", "local"):
        return 0
    updated = 0
    async with SessionLocal() as db:
        # Projects
        projects = (await db.execute(
            select(Project).where(Project.ai_summary.is_(None))
        )).scalars().all()
        for p in projects:
            total = (
                await db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == p.organization_id, Task.project_id == p.id
                    )
                )
            ).scalar() or 0
            completed = (
                await db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == p.organization_id,
                        Task.project_id == p.id,
                        Task.status == "completed",
                    )
                )
            ).scalar() or 0
            milestones = (
                await db.execute(
                    select(func.count(Milestone.id)).where(
                        Milestone.organization_id == p.organization_id, Milestone.project_id == p.id
                    )
                )
            ).scalar() or 0
            p.milestones_total = milestones
            p.ai_summary = _project_summary(p, total, completed)
            updated += 1

        # Tasks
        tasks = (await db.execute(
            select(Task).where(Task.ai_summary.is_(None))
        )).scalars().all()
        for t in tasks:
            t.ai_summary = _task_summary(t)
            updated += 1

        # Meetings
        meetings = (await db.execute(
            select(Meeting).where(Meeting.ai_summary.is_(None))
        )).scalars().all()
        for m in meetings:
            attendee_ids = (
                await db.execute(
                    select(MeetingAttendee.employee_id).where(
                        MeetingAttendee.organization_id == m.organization_id,
                        MeetingAttendee.meeting_id == m.id,
                    )
                )
            ).scalars().all()
            names = []
            if attendee_ids:
                emps = {e.id: e.full_name for e in (await db.execute(
                    select(Employee).where(Employee.id.in_(attendee_ids))
                )).scalars().all()}
                names = [emps.get(i) or i for i in attendee_ids[:6]]
            m.ai_summary = _meeting_summary(m, names)
            updated += 1

        # Knowledge entities (Phase 4) — summaries + keywords + quality
        from app.knowledge import knowledge_base as kb
        from app.knowledge.ai_service import ai_service

        for kind, model in kb.KIND_MODELS.items():
            entities = (
                await db.execute(
                    select(model).where(model.ai_summary.is_(None))
                )
            ).scalars().all()
            for entity in entities:
                await ai_service.enrich(
                    db, entity_type=kind, entity_id=entity.id, organization_id=entity.organization_id
                )
                updated += 1

        await db.commit()
        return updated


async def run_forever(interval_seconds: int = 1800) -> None:
    while True:
        try:
            updated = await run_once()
            if updated:
                logger.info("ai worker backfilled %s summaries", updated)
        except Exception as exc:  # pragma: no cover
            logger.exception("ai worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
