"""Learning path service (Phase 10.2 — Learning Paths).

Career-based learning paths with ordered steps. Employees enroll, steps are
marked complete (auto-completing when a referenced course is completed) and
the path emits learning.path.completed on 100%.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.course import CourseEnrollment
from app.models.learning_path import LearningPath, LearningPathStep, PathEnrollment
from app.models.learning_profile import LearningHistoryEntry, LearningProfile

logger = logging.getLogger("vcos.learning.paths")

_event_bus = EventBus()


class LearningPathService:
    # ------------------------------------------------------------------ catalog

    async def create_path(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> LearningPath:
        path = LearningPath(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            category=data.get("category"),
            target_role=data.get("target_role"),
            difficulty=data.get("difficulty", "beginner"),
            estimated_days=data.get("estimated_days"),
            tags=data.get("tags") or [],
            status=data.get("status", "published"),
            sort_order=data.get("sort_order", 0),
        )
        db.add(path)
        await db.flush()
        for index, step in enumerate(data.get("steps") or [], start=1):
            db.add(
                LearningPathStep(
                    organization_id=organization_id,
                    path_id=path.id,
                    title=step["title"],
                    description=step.get("description"),
                    position=index,
                    kind=step.get("kind", "course"),
                    skill_name=step.get("skill_name"),
                    course_id=step.get("course_id"),
                    reference_id=step.get("reference_id"),
                )
            )
        await db.flush()
        return path

    async def add_step(self, db: AsyncSession, *, organization_id: str, path_id: str, data: dict[str, Any]) -> Optional[LearningPathStep]:
        path = await self.get_path(db, organization_id=organization_id, path_id=path_id)
        if path is None:
            return None
        position = (
            (
                await db.execute(
                    select(func.max(LearningPathStep.position)).where(
                        LearningPathStep.organization_id == organization_id,
                        LearningPathStep.path_id == path_id,
                    )
                )
            ).scalar()
            or 0
        ) + 1
        step = LearningPathStep(
            organization_id=organization_id,
            path_id=path_id,
            title=data["title"],
            description=data.get("description"),
            position=position,
            kind=data.get("kind", "course"),
            skill_name=data.get("skill_name"),
            course_id=data.get("course_id"),
            reference_id=data.get("reference_id"),
        )
        db.add(step)
        await db.flush()
        return step

    async def get_path(self, db: AsyncSession, *, organization_id: str, path_id: str) -> Optional[LearningPath]:
        return (
            await db.execute(
                select(LearningPath)
                .options(selectinload(LearningPath.steps))
                .where(
                    LearningPath.organization_id == organization_id, LearningPath.id == path_id
                )
            )
        ).scalar_one_or_none()

    async def list_paths(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        target_role: Optional[str] = None,
        status: str = "published",
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[LearningPath]:
        query = select(LearningPath).where(LearningPath.organization_id == organization_id)
        if status:
            query = query.where(LearningPath.status == status)
        if target_role:
            query = query.where(LearningPath.target_role == target_role)
        if search:
            query = query.where(LearningPath.title.ilike(f"%{search}%"))
        query = query.options(selectinload(LearningPath.steps))
        if limit is not None:
            query = query.limit(limit)
        return (await db.execute(query.order_by(LearningPath.sort_order, LearningPath.created_at))).scalars().all()

    # ------------------------------------------------------------------ enrollment

    async def enroll(self, db: AsyncSession, *, organization_id: str, path_id: str, employee_id: str) -> Optional[PathEnrollment]:
        path = await self.get_path(db, organization_id=organization_id, path_id=path_id)
        if path is None or path.status != "published":
            return None
        existing = (
            await db.execute(
                select(PathEnrollment).where(
                    PathEnrollment.organization_id == organization_id,
                    PathEnrollment.path_id == path_id,
                    PathEnrollment.employee_id == employee_id,
                    PathEnrollment.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        enrollment = PathEnrollment(
            organization_id=organization_id, path_id=path_id, employee_id=employee_id,
            status="active", progress=0.0, started_at=utcnow(),
        )
        db.add(enrollment)
        await db.flush()
        from app.learning.profile_service import profile_service
        await profile_service.ensure_profile(db, organization_id=organization_id, employee_id=employee_id)
        return enrollment

    async def my_enrollments(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> list[PathEnrollment]:
        return (
            await db.execute(
                select(PathEnrollment).where(
                    PathEnrollment.organization_id == organization_id,
                    PathEnrollment.employee_id == employee_id,
                ).order_by(PathEnrollment.started_at.desc())
            )
        ).scalars().all()

    async def complete_step(self, db: AsyncSession, *, organization_id: str, path_id: str, employee_id: str, step_id: str) -> Optional[PathEnrollment]:
        enrollment = (
            await db.execute(
                select(PathEnrollment).where(
                    PathEnrollment.organization_id == organization_id,
                    PathEnrollment.path_id == path_id,
                    PathEnrollment.employee_id == employee_id,
                    PathEnrollment.status == "active",
                )
            )
        ).scalar_one_or_none()
        if enrollment is None:
            return None
        step = (
            await db.execute(
                select(LearningPathStep).where(
                    LearningPathStep.organization_id == organization_id,
                    LearningPathStep.id == step_id,
                )
            )
        ).scalar_one_or_none()
        if step is None:
            return None
        total = (
            (
                await db.execute(
                    select(func.count(LearningPathStep.id)).where(
                        LearningPathStep.organization_id == organization_id,
                        LearningPathStep.path_id == path_id,
                    )
                )
            ).scalar()
            or 0
        )
        done = set(enrollment.completed_step_ids or [])
        done.add(step_id)
        enrollment.completed_step_ids = list(done)
        if total:
            enrollment.progress = round((len(done) / total) * 100, 1)
        else:
            enrollment.progress = 100.0
        await db.flush()
        if enrollment.progress >= 100.0 and enrollment.status != "completed":
            enrollment.status = "completed"
            enrollment.completed_at = utcnow()
            path = await self.get_path(db, organization_id=organization_id, path_id=path_id)
            db.add(
                LearningHistoryEntry(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    kind="path_completion",
                    title=f"Learning path: {path.title if path else 'Completed'}",
                    entity_id=path_id,
                    occurred_at=utcnow(),
                )
            )
            profile = (
                await db.execute(
                    select(LearningProfile).where(
                        LearningProfile.organization_id == organization_id,
                        LearningProfile.employee_id == employee_id,
                    )
                )
            ).scalar_one_or_none()
            if profile:
                profile.learning_score = min(100.0, (profile.learning_score or 0) + 10.0)
                profile.last_learning_date = utcnow()
            await _event_bus.publish(
                db,
                name="learning.path.completed",
                organization_id=organization_id,
                actor_id=employee_id,
                payload={
                    "employee_id": employee_id,
                    "path_id": path_id,
                    "path_title": path.title if path else "",
                },
                flush=False,
            )
        return enrollment

    async def auto_complete_course_steps(self, db: AsyncSession, *, organization_id: str, employee_id: str, course_id: str) -> int:
        """When a course completes, complete every path step referencing it."""
        steps = (
            await db.execute(
                select(LearningPathStep).where(
                    LearningPathStep.organization_id == organization_id,
                    LearningPathStep.course_id == course_id,
                )
            )
        ).scalars().all()
        completed = 0
        for step in steps:
            enrollment = (
                await db.execute(
                    select(PathEnrollment).where(
                        PathEnrollment.organization_id == organization_id,
                        PathEnrollment.employee_id == employee_id,
                        PathEnrollment.path_id == step.path_id,
                        PathEnrollment.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if enrollment and await self.complete_step(
                db, organization_id=organization_id, path_id=step.path_id,
                employee_id=employee_id, step_id=step.id,
            ):
                completed += 1
        return completed


learning_path_service = LearningPathService()
