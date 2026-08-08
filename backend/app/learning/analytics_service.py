"""Learning analytics service (Phase 10.13-10.14 — Learning Analytics &
Organizational Skill Intelligence).

Executives and managers see learning completion, skill growth, department
skills, knowledge growth, certification rates, mentorship health, career
progress and training ROI. The service also predicts future skill
shortages from the Organization Skill Map (open gaps + demand).
"""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.assessment import AssessmentAttempt
from app.models.career import PromotionSignal
from app.models.certification import CertificationEarned
from app.models.course import Course, CourseEnrollment
from app.models.employee import Employee, EmployeeSkill
from app.models.learning_profile import LearningHistoryEntry
from app.models.learning_recommendation import LearningRecommendation
from app.models.mentorship import Mentorship
from app.models.skill import Skill
from app.models.skill_gap import SkillGap, SkillSnapshot

logger = logging.getLogger("vcos.learning.analytics")


class AnalyticsService:
    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        active = (
            (
                await db.execute(
                    select(func.count(CourseEnrollment.id)).where(
                        CourseEnrollment.organization_id == organization_id,
                        CourseEnrollment.status.in_(("enrolled", "in_progress")),
                    )
                )
            ).scalar()
            or 0
        )
        completed = (
            (
                await db.execute(
                    select(func.count(CourseEnrollment.id)).where(
                        CourseEnrollment.organization_id == organization_id,
                        CourseEnrollment.status == "completed",
                    )
                )
            ).scalar()
            or 0
        )
        certs = (
            (
                await db.execute(
                    select(func.count(CertificationEarned.id)).where(
                        CertificationEarned.organization_id == organization_id,
                        CertificationEarned.status == "valid",
                    )
                )
            ).scalar()
            or 0
        )
        mentorships = (
            (
                await db.execute(
                    select(func.count(Mentorship.id)).where(
                        Mentorship.organization_id == organization_id,
                        Mentorship.status == "active",
                    )
                )
            ).scalar()
            or 0
        )
        learning_time = (
            (
                await db.execute(
                    select(func.coalesce(func.sum(LearningHistoryEntry.time_minutes), 0)).where(
                        LearningHistoryEntry.organization_id == organization_id
                    )
                )
            ).scalar()
            or 0
        )
        employees = (
            (
                await db.execute(
                    select(func.count(Employee.id)).where(
                        Employee.organization_id == organization_id, Employee.status == "active"
                    )
                )
            ).scalar()
            or 1
        )
        learning_hours = round(learning_time / 60.0, 1)
        return {
            "active_learners": active,
            "completions": completed,
            "completion_rate": round(completed / max(1, completed + active) * 100, 1),
            "certifications": certs,
            "certification_rate": round(certs / employees * 100, 1),
            "active_mentorships": mentorships,
            "learning_hours": learning_hours,
            "hours_per_employee": round(learning_hours / employees, 1),
            "employees": employees,
        }

    async def skill_distribution(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        """Skill coverage across the organization (from today's snapshot)."""
        today = utcnow().date()
        rows = await db.execute(
            select(SkillSnapshot)
            .where(
                SkillSnapshot.organization_id == organization_id,
                SkillSnapshot.snapshot_date == today,
            )
            .order_by(SkillSnapshot.employee_count.desc())
            .limit(30)
        )
        return [
            {
                "skill_name": row.skill_name,
                "employee_count": row.employee_count,
                "average_level": row.average_level,
                "max_level": row.max_level,
                "open_gaps": row.open_gaps,
                "demand_level": row.demand_level,
                "projected_shortage": row.projected_shortage,
            }
            for row in rows.scalars().all()
        ]

    async def department_skills(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        """Skill depth per department."""
        rows = await db.execute(
            select(Employee.department_id, Skill.name, func.avg(EmployeeSkill.level), func.count(EmployeeSkill.id))
            .join(EmployeeSkill, EmployeeSkill.employee_id == Employee.id)
            .join(Skill, Skill.id == EmployeeSkill.skill_id)
            .where(Employee.organization_id == organization_id, Employee.status == "active")
            .group_by(Employee.department_id, Skill.name)
            .order_by(func.count(EmployeeSkill.id).desc())
            .limit(40)
        )
        from app.models.department import Department
        departments = {
            d.id: d.name
            for d in (
                await db.execute(
                    select(Department).where(Department.organization_id == organization_id)
                )
            ).scalars().all()
        }
        return [
            {
                "department_id": department_id,
                "department_name": departments.get(department_id, "General"),
                "skill_name": skill_name,
                "average_level": round(avg_level or 0, 2),
                "employees": count,
            }
            for department_id, skill_name, avg_level, count in rows.all()
        ]

    async def certification_progress(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        attempts = (
            await db.execute(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.organization_id == organization_id,
                    AssessmentAttempt.evaluated_at.isnot(None),
                )
            )
        ).scalars().all()
        passed = sum(1 for attempt in attempts if attempt.passed)
        return {
            "attempts": len(attempts),
            "passed": passed,
            "pass_rate": round(passed / len(attempts) * 100, 1) if attempts else 0.0,
        }

    async def course_completion(self, db: AsyncSession, *, organization_id: str, days: int = 30) -> list[dict[str, Any]]:
        since = utcnow() - timedelta(days=days)
        rows = await db.execute(
            select(Course.title, func.count(CourseEnrollment.id), func.sum(CourseEnrollment.progress))
            .join(CourseEnrollment, CourseEnrollment.course_id == Course.id)
            .where(
                CourseEnrollment.organization_id == organization_id,
                CourseEnrollment.enrolled_at >= since,
            )
            .group_by(Course.title)
            .order_by(func.count(CourseEnrollment.id).desc())
            .limit(15)
        )
        return [
            {"course": title, "enrollments": enrollments, "progress_sum": round(sum_progress or 0, 1)}
            for title, enrollments, sum_progress in rows.all()
        ]

    async def mentorship_health(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        total = (
            (
                await db.execute(
                    select(func.count(Mentorship.id)).where(
                        Mentorship.organization_id == organization_id
                    )
                )
            ).scalar()
            or 0
        )
        active = (
            (
                await db.execute(
                    select(func.count(Mentorship.id)).where(
                        Mentorship.organization_id == organization_id,
                        Mentorship.status == "active",
                    )
                )
            ).scalar()
            or 0
        )
        return {
            "total": total,
            "active": active,
            "completion_rate": round(active / total * 100, 1) if total else 0.0,
        }

    async def career_progress(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        signals = (
            (
                await db.execute(
                    select(func.count(PromotionSignal.id)).where(
                        PromotionSignal.organization_id == organization_id,
                        PromotionSignal.status == "open",
                    )
                )
            ).scalar()
            or 0
        )
        employees = (
            (
                await db.execute(
                    select(func.count(Employee.id)).where(
                        Employee.organization_id == organization_id, Employee.status == "active"
                    )
                )
            ).scalar()
            or 0
        )
        return {"promotion_ready": signals, "promotion_rate": round(signals / employees * 100, 1) if employees else 0.0}

    async def skill_shortages(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Predict future skill shortages: high demand + low coverage + high gaps."""
        today = utcnow().date()
        rows = await db.execute(
            select(SkillSnapshot)
            .where(
                SkillSnapshot.organization_id == organization_id,
                SkillSnapshot.snapshot_date == today,
                SkillSnapshot.projected_shortage.is_(True),
            )
            .order_by(SkillSnapshot.demand_level.desc(), SkillSnapshot.open_gaps.desc())
            .limit(limit)
        )
        return [
            {
                "skill_name": row.skill_name,
                "employee_count": row.employee_count,
                "average_level": row.average_level,
                "open_gaps": row.open_gaps,
                "demand_level": row.demand_level,
                "prediction": "shortage risk" if row.open_gaps >= 5 else "growing demand",
            }
            for row in rows.scalars().all()
        ]

    async def recommendations_health(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        rows = await db.execute(
            select(LearningRecommendation.status, func.count(LearningRecommendation.id))
            .where(LearningRecommendation.organization_id == organization_id)
            .group_by(LearningRecommendation.status)
        )
        counts = dict(rows.all())
        pending = counts.get("pending", 0) + counts.get("accepted", 0)
        acted = counts.get("completed", 0)
        return {
            "total": sum(counts.values()),
            "pending": pending,
            "completed": acted,
            "action_rate": round(acted / max(1, acted + pending) * 100, 1),
        }


analytics_service = AnalyticsService()
