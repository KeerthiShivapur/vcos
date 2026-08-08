"""Learning recommendation service (Phase 10.5, 10.9 — Learning
Recommendations & Continuous Learning AI).

The AI builds a personalized recommendation feed per employee from:
  1. skill gaps (courses + certifications covering the missing skills)
  2. career path next-step skills (courses + mentors)
  3. role/company needs (academies + certifications)
  4. project context (knowledge + communities)
  5. available mentors (skill expertise matching)

Recommendations are deduplicated per (employee, kind, entity), scored and
acted on by the employee (enroll, request mentorship, join community).
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.learning_recommendation import LearningRecommendation

logger = logging.getLogger("vcos.learning.recommendations")


class RecommendationService:
    # ------------------------------------------------------------------ generation

    async def refresh_for_employee(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> int:
        """Regenerate the recommendation feed for one employee."""
        candidates = await self._collect_candidates(db, organization_id=organization_id, employee_id=employee_id)
        created = 0
        existing = await self.list(
            db, organization_id=organization_id, employee_id=employee_id,
            statuses=("pending", "accepted"),
        ) 
        seen = {(r.kind, r.entity_id or "") for r in existing}
        for candidate in candidates:
            key = (candidate["kind"], candidate.get("entity_id") or "")
            if key in seen:
                continue
            db.add(
                LearningRecommendation(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    kind=candidate["kind"],
                    title=candidate["title"],
                    description=candidate.get("description"),
                    reason=candidate.get("reason"),
                    score=candidate.get("score", 0.0),
                    source=candidate.get("source", "ai"),
                    entity_id=candidate.get("entity_id"),
                    status="pending",
                )
            )
            created += 1
        await db.flush()
        return created

    async def refresh_org(self, db: AsyncSession, *, organization_id: str, limit_employees: int = 200) -> int:
        """Regenerate feeds for all employees (worker pass)."""
        from app.models.employee import Employee

        employees = (
            await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                ).limit(limit_employees)
            )
        ).scalars().all()
        total = 0
        for employee_id in employees:
            try:
                total += await self.refresh_for_employee(
                    db, organization_id=organization_id, employee_id=employee_id
                )
            except Exception as exc:  # noqa: BLE001 - per-employee isolation
                logger.warning("recommendation refresh failed for %s: %s", employee_id, exc)
        return total

    async def _collect_candidates(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[dict[str, Any]]:
        from app.learning.career_service import career_service
        from app.learning.certification_service import certification_service
        from app.learning.course_service import course_service
        from app.learning.mentorship_service import mentorship_service
        from app.learning.skill_service import skill_service

        candidates: list[dict[str, Any]] = []
        gaps = await skill_service.list_gaps(
            db, organization_id=organization_id, employee_id=employee_id, status="open"
        )
        gap_skills = [gap.skill_name for gap in gaps]
        high_gap_skills = [gap.skill_name for gap in gaps if gap.priority == "high"]

        # 1. courses for gaps
        for course in await course_service.recommended_for(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_names=gap_skills, limit=8,
        ):
            matched = [s for s in (course.skills or []) if s.strip().lower() in {g.lower() for g in gap_skills}]
            candidates.append(
                {
                    "kind": "course",
                    "entity_id": course.id,
                    "title": course.title,
                    "description": course.description,
                    "reason": f"Covers: {', '.join(matched[:3]) or 'your target skills'}",
                    "score": 0.9 if high_gap_skills and matched else 0.6,
                    "source": "skill_gap",
                }
            )

        # 2. certifications for gaps
        for cert in await certification_service.recommended_for(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_names=gap_skills, limit=5,
        ):
            candidates.append(
                {
                    "kind": "certification",
                    "entity_id": cert.id,
                    "title": cert.name,
                    "description": cert.description,
                    "reason": "Internal certification aligned with your skill gaps",
                    "score": 0.7,
                    "source": "skill_gap",
                }
            )

        # 3. career next-step skills → courses + mentors
        progress = await career_service.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        next_step = progress.get("next") or {}
        for requirement in next_step.get("required_skills") or []:
            skill_name = (requirement.get("skill") or requirement.get("name") or "").strip()
            if not skill_name:
                continue
            for course in await course_service.recommended_for(
                db, organization_id=organization_id, employee_id=employee_id,
                skill_names=[skill_name], limit=2,
            ):
                candidates.append(
                    {
                        "kind": "course",
                        "entity_id": course.id,
                        "title": course.title,
                        "description": course.description,
                        "reason": f"Prepares you for {next_step.get('title', 'the next step')} ({skill_name})",
                        "score": 0.8,
                        "source": "career",
                    }
                )
        if next_step:
            for mentor in await mentorship_service.recommend_mentors(
                db, organization_id=organization_id, employee_id=employee_id,
                skills=[r.get("skill") or r.get("name") for r in (next_step.get("required_skills") or [])],
                limit=3,
            ):
                candidates.append(
                    {
                        "kind": "mentor",
                        "entity_id": mentor["employee_id"],
                        "title": f"Get mentored by {mentor['name']}",
                        "description": mentor.get("bio"),
                        "reason": "Expert who can accelerate your next career step",
                        "score": 0.85,
                        "source": "career",
                    }
                )

        # 4. role/company needs → academies
        from app.learning.academy_service import academy_service
        for academy in await academy_service.list_academies(db, organization_id=organization_id):
            if gap_skills and academy.category and academy.category.lower() in {g.lower() for g in gap_skills}:
                candidates.append(
                    {
                        "kind": "training",
                        "entity_id": academy.id,
                        "title": f"Join the {academy.name}",
                        "description": academy.description,
                        "reason": "Academy aligned with your growth areas",
                        "score": 0.6,
                        "source": "role",
                    }
                )

        # 5. projects using gap skills (learning by doing)
        from app.models.project import Project
        from app.models.task import Task
        matching_projects = (
            await db.execute(
                select(Project)
                .join(Task, Task.project_id == Project.id)
                .where(
                    Project.organization_id == organization_id,
                    Project.status == "active",
                )
                .limit(50)
            )
        ).scalars().all()
        for project in matching_projects[:3]:
            candidates.append(
                {
                    "kind": "project",
                    "entity_id": project.id,
                    "title": f"Apply skills on {project.name}",
                    "description": project.description,
                    "reason": "Hands-on practice accelerates skill growth",
                    "score": 0.5,
                    "source": "ai",
                }
            )

        # dedupe within this batch
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for candidate in candidates:
            key = (candidate["kind"], candidate.get("entity_id") or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        unique.sort(key=lambda row: -row.get("score", 0))
        return unique[:25]

    # ------------------------------------------------------------------ query

    async def list(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        statuses: tuple[str, ...] = ("pending",), limit: int = 50,
    ) -> list[LearningRecommendation]:
        query = select(LearningRecommendation).where(
            LearningRecommendation.organization_id == organization_id,
            LearningRecommendation.employee_id == employee_id,
            LearningRecommendation.status.in_(statuses),
        )
        return (await db.execute(query.order_by(LearningRecommendation.score.desc()).limit(limit))).scalars().all()

    async def update_status(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        recommendation_id: str, status: str,
    ) -> Optional[LearningRecommendation]:
        recommendation = (
            await db.execute(
                select(LearningRecommendation).where(
                    LearningRecommendation.organization_id == organization_id,
                    LearningRecommendation.employee_id == employee_id,
                    LearningRecommendation.id == recommendation_id,
                )
            )
        ).scalar_one_or_none()
        if recommendation is None:
            return None
        recommendation.status = status
        await db.flush()
        return recommendation


recommendation_service = RecommendationService()
