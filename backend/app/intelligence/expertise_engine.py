"""Phase 9.3 — Expertise evolution engine.

Expertise should never depend on manual entry alone. This engine continuously
evolves per-skill expertise scores from organizational activity:

    writes documentation -> +score on writing/authoring skills
    completes tasks/milestones -> +score on matching skills
    participates in meetings, answers in forums, gets recognized

Each change is recorded in ExpertiseHistory (auditable) and refreshes the
employee aggregate `expertise_score`. All deltas are damped so a single event
cannot dominate a score.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_models import EXPERTISE_EVENTS
from app.models.employee import Employee, EmployeeSkill
from app.models.intelligence import ExpertiseHistory
from app.models.skill import ExpertiseScore, Skill

logger = logging.getLogger("vcos.intelligence.expertise")

MAX_SCORE = 100.0
DECAY_FACTOR = 0.98  # slow decay so historical dominance fades


class ExpertiseEngine:
    async def record_activity(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        event_name: str,
        tokens: Optional[list[str]] = None,
        reason: Optional[str] = None,
        event_id: Optional[str] = None,
        points: Optional[float] = None,
    ) -> list[ExpertiseHistory]:
        """Bump expertise on the employee's matching skills for an activity."""
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return []
        if event_name not in EXPERTISE_EVENTS and points is None:
            return []
        base_points = points if points is not None else EXPERTISE_EVENTS[event_name][0]
        tokens = tokens or []

        rows = (
            await db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == employee_id,
                )
            )
        ).scalars().all()
        skill_rows: list[Skill] = []
        if rows:
            skill_rows = list(
                (
                    await db.execute(
                        select(Skill).where(Skill.id.in_([r.skill_id for r in rows]))
                    )
                ).scalars().all()
            )

        if not skill_rows:
            return []

        now = utcnow()
        history: list[ExpertiseHistory] = []
        token_text = " ".join(tokens).lower()
        for skill in skill_rows:
            delta = base_points
            if tokens and skill.name.lower() in token_text:
                delta = base_points * 2.5
            elif tokens and any(token in skill.name.lower() for token in tokens if len(token) >= 3):
                delta = base_points * 1.5
            else:
                delta = base_points * 0.4  # general activity still matters

            score = await self._score_for(db, organization_id, employee_id, skill.id)
            before = score.score
            after = min(MAX_SCORE, before + delta)
            if abs(after - before) < 0.01:
                continue
            score.score = round(after, 2)
            score.level = min(5, max(1, int(after // 20) + 1))
            score.updated_at = now
            history.append(
                ExpertiseHistory(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    skill_id=skill.id,
                    skill_name=skill.name,
                    before=round(before, 2),
                    after=round(after, 2),
                    delta=round(after - before, 2),
                    source_event=event_name,
                    reason=reason,
                    event_id=event_id,
                )
            )

        if history:
            db.add_all(history)
            await db.flush()
            aggregate = (
                await db.execute(
                    select(ExpertiseScore.score).where(
                        ExpertiseScore.organization_id == organization_id,
                        ExpertiseScore.employee_id == employee_id,
                    )
                )
            ).scalars().all()
            employee.expertise_score = round(min(MAX_SCORE, sum(aggregate)), 2)
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="expertise.updated",
                organization_id=organization_id,
                payload={
                    "employee_id": employee_id,
                    "event": event_name,
                    "changed_skills": len(history),
                    "delta": round(sum(h.delta for h in history), 2),
                },
            )
        return history

    async def _score_for(self, db: AsyncSession, organization_id: str, employee_id: str, skill_id: str) -> ExpertiseScore:
        row = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                    ExpertiseScore.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        score = ExpertiseScore(
            organization_id=organization_id,
            employee_id=employee_id,
            skill_id=skill_id,
            score=0.0,
            level=1,
            factors={"source": "expertise_engine", "first_activity": utcnow().isoformat()},
        )
        db.add(score)
        await db.flush()
        return score

    async def recompute_employee(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> float:
        """Refresh the employee aggregate expertise score + decay old deltas."""
        rows = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                )
            )
        ).scalars().all()
        total = 0.0
        for row in rows:
            row.score = round(min(MAX_SCORE, row.score * DECAY_FACTOR), 2)
            total += row.score
        employee = await db.get(Employee, employee_id)
        if employee is not None and employee.organization_id == organization_id:
            employee.expertise_score = round(total, 2)
        return total

    async def recompute_all(self, db: AsyncSession, *, organization_id: str) -> int:
        employee_ids = (
            await db.execute(
                select(Employee.id).where(Employee.organization_id == organization_id)
            )
        ).scalars().all()
        for employee_id in employee_ids:
            await self.recompute_employee(db, organization_id=organization_id, employee_id=employee_id)
        return len(employee_ids)

    async def history(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ExpertiseHistory)
                .where(
                    ExpertiseHistory.organization_id == organization_id,
                    ExpertiseHistory.employee_id == employee_id,
                )
                .order_by(ExpertiseHistory.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "employee_id": row.employee_id,
                "skill_id": row.skill_id,
                "skill_name": row.skill_name,
                "before": row.before,
                "after": row.after,
                "delta": row.delta,
                "source_event": row.source_event,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    async def leaderboard(
        self, db: AsyncSession, *, organization_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Employee)
                .where(Employee.organization_id == organization_id, Employee.status == "active")
                .order_by(Employee.expertise_score.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "employee_id": e.id,
                "name": e.display_name or f"{e.first_name} {e.last_name or ''}".strip(),
                "designation": e.designation,
                "department_id": e.department_id,
                "expertise_score": round(e.expertise_score or 0.0, 2),
                "top_skills": await self._top_skills(db, organization_id, e.id),
            }
            for e in rows
        ]

    async def _top_skills(self, db: AsyncSession, organization_id: str, employee_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ExpertiseScore)
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                )
                .order_by(ExpertiseScore.score.desc())
                .limit(limit)
            )
        ).scalars().all()
        if not rows:
            return []
        skills = {
            s.id: s.name
            for s in (
                await db.execute(select(Skill).where(Skill.id.in_([r.skill_id for r in rows])))
            ).scalars().all()
        }
        return [
            {"skill_id": r.skill_id, "name": skills.get(r.skill_id, r.skill_id), "score": round(r.score, 2), "level": r.level}
            for r in rows
        ]


expertise_engine = ExpertiseEngine()
