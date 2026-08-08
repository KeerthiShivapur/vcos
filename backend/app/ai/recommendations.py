"""Phase 7.7 — recommendation engine.

Generates and persists ``ai_recommendations`` for users and the organization:

  user:           expert, document, collaborator, training, action
  organization:   knowledge_gap, overload, meeting_load, action

Recommendations carry a score, a human-readable reason and the evidence used,
and can be accepted or dismissed (status transitions feed the learning loop).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIRecommendation
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.meeting import Meeting, MeetingAttendee
from app.models.project import Project
from app.models.skill import ExpertiseScore, Skill
from app.models.task import Task
from app.models.user import User
from app.models.workload import WorkloadSnapshot


class RecommendationEngine:
    async def for_user(
        self, db: AsyncSession, *, organization_id: str, user: User, limit: int = 10
    ) -> list[dict[str, Any]]:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return []
        recommendations: list[dict[str, Any]] = []
        recommendations.extend(await self._expert_contacts(db, organization_id, employee))
        recommendations.extend(await self._training(db, organization_id, employee))
        recommendations.extend(await self._overload_actions(db, organization_id, employee))
        recommendations.sort(key=lambda r: r["score"], reverse=True)
        await self._persist(db, organization_id=organization_id, user_id=user.id, recommendations=recommendations)
        return recommendations[:limit]

    async def for_organization(
        self, db: AsyncSession, *, organization_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        recommendations.extend(await self._knowledge_gaps(db, organization_id))
        recommendations.extend(await self._overloaded_teams(db, organization_id))
        recommendations.extend(await self._meeting_load(db, organization_id))
        recommendations.sort(key=lambda r: r["score"], reverse=True)
        await self._persist(db, organization_id=organization_id, user_id=None, recommendations=recommendations)
        return recommendations[:limit]

    async def _expert_contacts(self, db, organization_id: str, employee: Employee) -> list[dict[str, Any]]:
        my_skills = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee.id,
                )
            )
        ).scalars().all()
        my_skill_ids = {s.skill_id for s in my_skills}
        if not my_skill_ids:
            return []
        rows = (
            await db.execute(
                select(ExpertiseScore)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.skill_id.in_(my_skill_ids),
                    ExpertiseScore.employee_id != employee.id,
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(6)
            )
        ).scalars().all()
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if row.employee_id in seen:
                continue
            seen.add(row.employee_id)
            expert = await db.get(Employee, row.employee_id)
            skill = await db.get(Skill, row.skill_id)
            if expert is None:
                continue
            results.append(
                {
                    "kind": "expert",
                    "target_type": "employee",
                    "target_id": expert.id,
                    "title": f"Meet {expert.full_name} — {skill.name if skill else 'shared skill'}",
                    "summary": f"Shares your interest in '{skill.name if skill else 'a skill'}' "
                    f"with an expertise score of {round(row.score, 1)}.",
                    "reason": f"You and {expert.full_name} both work on {skill.name if skill else 'that area'}.",
                    "score": min(1.0, row.score / 10 + 0.3),
                }
            )
            if len(results) >= 3:
                break
        return results

    async def _training(self, db, organization_id: str, employee: Employee) -> list[dict[str, Any]]:
        org_skills = (
            await db.execute(
                select(Skill).where(Skill.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        if not org_skills:
            return []
        results = []
        for skill in org_skills[:8]:
            count = (
                await db.execute(
                    select(func.count())
                    .select_from(ExpertiseScore)
                    .where(
                        ExpertiseScore.organization_id == organization_id,
                        ExpertiseScore.skill_id == skill.id,
                        ExpertiseScore.score >= 5,
                    )
                )
            ).scalar_one()
            if count <= 1 and skill.name not in (employee.designation or ""):
                results.append(
                    {
                        "kind": "training",
                        "target_type": "skill",
                        "target_id": skill.id,
                        "title": f"Skill up on '{skill.name}'",
                        "summary": f"Only {count} person(s) in the company have strong expertise here — "
                        "it's a differentiating skill.",
                        "reason": "Low expertise density in your organization for this skill.",
                        "score": 0.6,
                    }
                )
        return results

    async def _overload_actions(self, db, organization_id: str, employee: Employee) -> list[dict[str, Any]]:
        snapshot = (
            await db.execute(
                select(WorkloadSnapshot)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.employee_id == employee.id,
                )
                .order_by(WorkloadSnapshot.period_start.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None or not snapshot.is_overloaded:
            return []
        return [
            {
                "kind": "action",
                "target_type": "employee",
                "target_id": employee.id,
                "title": "Review your workload with your manager",
                "summary": (
                    f"You are at {round(snapshot.utilization)}% utilization with "
                    f"{snapshot.tasks_count} open task(s)."
                ),
                "reason": "Overload flag detected in the latest workload snapshot.",
                "score": 0.8,
            }
        ]

    async def _knowledge_gaps(self, db, organization_id: str) -> list[dict[str, Any]]:
        from app.models.knowledge import Document

        active_projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.status.in_(("active", "planning")),
                ).limit(50)
            )
        ).scalars().all()
        results = []
        for project in active_projects[:6]:
            docs = (
                await db.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(
                        Document.organization_id == organization_id,
                        Document.project_id == project.id,
                        Document.status == "published",
                    )
                )
            ).scalar_one()
            if docs == 0:
                results.append(
                    {
                        "kind": "knowledge_gap",
                        "target_type": "project",
                        "target_id": project.id,
                        "title": f"'{project.name}' has no published documents",
                        "summary": "An active project without documentation creates knowledge risk.",
                        "reason": f"0 published documents found for project '{project.name}'.",
                        "score": 0.7,
                    }
                )
        return results

    async def _overloaded_teams(self, db, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WorkloadSnapshot)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.is_overloaded == True,  # noqa: E712
                )
                .limit(10)
            )
        ).scalars().all()
        results = []
        for row in rows:
            employee = await db.get(Employee, row.employee_id)
            if employee is None:
                continue
            results.append(
                {
                    "kind": "overload",
                    "target_type": "employee",
                    "target_id": employee.id,
                    "title": f"{employee.full_name} is overloaded",
                    "summary": (
                        f"Utilization {round(row.utilization)}% with {row.tasks_count} open task(s) "
                        f"and {round(row.meetings_hours)} meeting hours this period."
                    ),
                    "reason": "Workload snapshot flagged overload for the latest period.",
                    "score": min(1.0, row.utilization / 120),
                }
            )
        return results

    async def _meeting_load(self, db, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(MeetingAttendee.employee_id, func.count(MeetingAttendee.id).label("cnt"))
                .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
                .where(
                    Meeting.organization_id == organization_id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                )
                .group_by(MeetingAttendee.employee_id)
                .order_by(func.count(MeetingAttendee.id).desc())
                .limit(5)
            )
        ).all()
        results = []
        for employee_id, cnt in rows:
            if cnt < 10:
                continue
            employee = await db.get(Employee, employee_id)
            if employee is None:
                continue
            results.append(
                {
                    "kind": "meeting_load",
                    "target_type": "employee",
                    "target_id": employee.id,
                    "title": f"{employee.full_name} has {cnt} upcoming meetings",
                    "summary": "High meeting load reduces deep-work time.",
                    "reason": f"{cnt} scheduled/in-progress meetings found for this employee.",
                    "score": min(1.0, cnt / 25),
                }
            )
        return results

    async def _persist(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: Optional[str],
        recommendations: list[dict[str, Any]],
    ) -> None:
        if not recommendations:
            return
        existing = (
            await db.execute(
                select(AIRecommendation).where(
                    AIRecommendation.organization_id == organization_id,
                    AIRecommendation.status == "active",
                )
            )
        ).scalars().all()
        for old in existing:
            old.status = "dismissed"
        for rec in recommendations[:10]:
            row = AIRecommendation(
                organization_id=organization_id,
                user_id=user_id,
                audience="user" if user_id else "organization",
                kind=rec["kind"],
                target_type=rec.get("target_type"),
                target_id=rec.get("target_id"),
                title=rec["title"],
                summary=rec.get("summary"),
                reason=rec.get("reason"),
                evidence_json=json.dumps(rec.get("evidence", {}), default=str),
                confidence=0.7,
                score=rec.get("score", 0.5),
            )
            db.add(row)
        await db.flush()

    async def accept(self, db: AsyncSession, recommendation_id: str) -> bool:
        row = await db.get(AIRecommendation, recommendation_id)
        if row is None:
            return False
        row.status = "accepted"
        return True

    async def dismiss(self, db: AsyncSession, recommendation_id: str) -> bool:
        row = await db.get(AIRecommendation, recommendation_id)
        if row is None:
            return False
        row.status = "dismissed"
        return True


recommendation_engine = RecommendationEngine()
