"""Learning profile service (Phase 10.1 — Learning Foundation).

Every employee has exactly one living learning profile. This service
ensures the profile exists on first touch and recomputes the learning score
from the employee's actual learning history.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.learning_profile import LearningHistoryEntry, LearningProfile

logger = logging.getLogger("vcos.learning.profile")


class ProfileService:
    async def ensure_profile(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> LearningProfile:
        profile = (
            await db.execute(
                select(LearningProfile).where(
                    LearningProfile.organization_id == organization_id,
                    LearningProfile.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if profile is None:
            profile = LearningProfile(
                organization_id=organization_id,
                employee_id=employee_id,
                learning_score=0.0,
                career_stage="developing",
                preferred_learning="mixed",
                weekly_learning_hours=4,
                completed_courses=0,
                certifications=0,
                career_goals=[],
                learning_goals=[],
            )
            db.add(profile)
            await db.flush()
        return profile

    async def get_profile(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> LearningProfile:
        return await self.ensure_profile(db, organization_id=organization_id, employee_id=employee_id)

    async def update_profile(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        data: dict[str, Any],
    ) -> LearningProfile:
        profile = await self.ensure_profile(db, organization_id=organization_id, employee_id=employee_id)
        allowed = {
            "career_stage", "preferred_learning", "weekly_learning_hours",
            "career_goals", "learning_goals",
        }
        for key, value in data.items():
            if key in allowed and value is not None:
                setattr(profile, key, value)
        await db.flush()
        return profile

    async def recompute_score(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> LearningProfile:
        """Derive the learning score from the employee's learning history."""
        profile = await self.ensure_profile(db, organization_id=organization_id, employee_id=employee_id)
        total_time = (
            await db.execute(
                select(func.coalesce(func.sum(LearningHistoryEntry.time_minutes), 0)).where(
                    LearningHistoryEntry.organization_id == organization_id,
                    LearningHistoryEntry.employee_id == employee_id,
                )
            )
        ).scalar() or 0
        activities = (
            await db.execute(
                select(func.count(LearningHistoryEntry.id)).where(
                    LearningHistoryEntry.organization_id == organization_id,
                    LearningHistoryEntry.employee_id == employee_id,
                )
            )
        ).scalar() or 0
        last = (
            await db.execute(
                select(func.max(LearningHistoryEntry.occurred_at)).where(
                    LearningHistoryEntry.organization_id == organization_id,
                    LearningHistoryEntry.employee_id == employee_id,
                )
            )
        ).scalar()
        score = min(100.0, activities * 4.0 + (total_time / 60.0) * 1.5)
        profile.learning_score = round(score, 1)
        profile.last_learning_date = last or profile.last_learning_date or utcnow()
        await db.flush()
        return profile

    async def history(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 50
    ) -> list[LearningHistoryEntry]:
        return (
            await db.execute(
                select(LearningHistoryEntry)
                .where(
                    LearningHistoryEntry.organization_id == organization_id,
                    LearningHistoryEntry.employee_id == employee_id,
                )
                .order_by(LearningHistoryEntry.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()


profile_service = ProfileService()
