"""Skill Engine (Phase 10.3-10.4 — AI Skill Graph & Skill Gap Analysis).

Every employee has a living skill graph. Skill levels come from the skill
catalog (EmployeeSkill + ExpertiseScore) and are continuously boosted by
real work: course completions, passed assessments, earned certifications,
mentorship sessions and project contributions. The gap analyzer compares
the current role's required skills (career path framework) with current
levels and persists prioritized SkillGap rows. The org skill map aggregates
per-skill snapshots for executives.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.employee import Employee, EmployeeSkill
from app.models.skill import ExpertiseScore, Skill
from app.models.skill_gap import SkillGap, SkillSnapshot

logger = logging.getLogger("vcos.learning.skills")

_event_bus = EventBus()

_LEVEL_LABELS = {1: "beginner", 2: "junior", 3: "intermediate", 4: "advanced", 5: "expert"}


def level_to_value(level: str) -> int:
    mapping = {
        "beginner": 1, "junior": 2, "intermediate": 3, "advanced": 4, "expert": 5,
    }
    if isinstance(level, str):
        value = mapping.get(level.lower())
        if value:
            return value
        try:
            return int(level)
        except ValueError:
            return 2
    return int(level or 2)


class SkillService:
    # ------------------------------------------------------------------ graph

    async def graph(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[dict[str, Any]]:
        """The employee's skill graph: merged skill + level + provenance."""
        rows = await db.execute(
            select(EmployeeSkill, Skill)
            .join(Skill, Skill.id == EmployeeSkill.skill_id)
            .where(
                EmployeeSkill.organization_id == organization_id,
                EmployeeSkill.employee_id == employee_id,
            )
            .order_by(EmployeeSkill.level.desc())
        )
        graph: list[dict[str, Any]] = []
        for emp_skill, skill in rows.all():
            graph.append(
                {
                    "skill_id": skill.id,
                    "name": skill.name,
                    "category": skill.category,
                    "level": emp_skill.level,
                    "label": _LEVEL_LABELS.get(emp_skill.level, "intermediate"),
                    "years_experience": emp_skill.years_experience,
                    "verified": emp_skill.verified,
                    "source": "skill_graph",
                }
            )
        # merge expertise scores that aren't in the employee_skills catalog yet
        scores = await db.execute(
            select(ExpertiseScore, Skill)
            .join(Skill, Skill.id == ExpertiseScore.skill_id)
            .where(
                ExpertiseScore.organization_id == organization_id,
                ExpertiseScore.employee_id == employee_id,
            )
        )
        existing = {row["name"] for row in graph}
        for score, skill in scores.all():
            if skill.name in existing:
                continue
            graph.append(
                {
                    "skill_id": skill.id,
                    "name": skill.name,
                    "category": skill.category,
                    "level": max(1, min(5, round(score.score * 5))),
                    "label": _LEVEL_LABELS.get(max(1, min(5, round(score.score * 5))), "intermediate"),
                    "years_experience": score.years_experience,
                    "verified": False,
                    "source": "expertise_engine",
                }
            )
        graph.sort(key=lambda row: (-row["level"], row["name"]))
        return graph

    async def boost_skill(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        skill_name: str,
        points: float = 1.0,
        source: str = "learning",
        reason: Optional[str] = None,
        emit: bool = True,
    ) -> Optional[EmployeeSkill]:
        """Upsert a skill at a level derived from the accumulated boosts.

        First touch creates the skill at level 2 (junior). Each boost adds
        half a level up to a ceiling of 5 (expert).
        """
        if not skill_name or not skill_name.strip():
            return None
        name = skill_name.strip()
        skill = (
            await db.execute(
                select(Skill).where(Skill.organization_id == organization_id, Skill.name == name)
            )
        ).scalar_one_or_none()
        if skill is None:
            skill = Skill(organization_id=organization_id, name=name, category="Learning")
            db.add(skill)
            await db.flush()
        emp_skill = (
            await db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == employee_id,
                    EmployeeSkill.skill_id == skill.id,
                )
            )
        ).scalar_one_or_none()
        if emp_skill is None:
            emp_skill = EmployeeSkill(
                organization_id=organization_id,
                employee_id=employee_id,
                skill_id=skill.id,
                level=min(5, int(round(2 + points))),
                verified=False,
            )
            db.add(emp_skill)
        else:
            emp_skill.level = min(5, int(round(emp_skill.level + points)))
        emp_skill.updated_at = utcnow()
        await db.flush()

        # keep the expertise engine's aggregate in sync
        score = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                    ExpertiseScore.skill_id == skill.id,
                )
            )
        ).scalar_one_or_none()
        if score is None:
            score = ExpertiseScore(
                organization_id=organization_id,
                employee_id=employee_id,
                skill_id=skill.id,
                score=min(1.0, emp_skill.level / 5.0),
                level=emp_skill.level,
            )
            db.add(score)
        else:
            score.score = min(1.0, max(score.score, emp_skill.level / 5.0))
            score.level = max(score.level, emp_skill.level)
            score.updated_at = utcnow()
        await db.flush()

        if emit:
            await _event_bus.publish(
                db,
                name="skill.updated",
                organization_id=organization_id,
                actor_id=employee_id,
                payload={
                    "employee_id": employee_id,
                    "skill_id": skill.id,
                    "skill_name": name,
                    "level": emp_skill.level,
                    "source": source,
                    "reason": reason,
                },
                flush=False,
            )
        return emp_skill

    async def set_skill_level(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        skill_name: str,
        level: int,
        category: Optional[str] = None,
        verified: bool = False,
    ) -> Optional[EmployeeSkill]:
        level = max(1, min(5, int(level)))
        skill = (
            await db.execute(
                select(Skill).where(Skill.organization_id == organization_id, Skill.name == skill_name)
            )
        ).scalar_one_or_none()
        if skill is None:
            skill = Skill(
                organization_id=organization_id, name=skill_name.strip(),
                category=category or "Learning",
            )
            db.add(skill)
            await db.flush()
        emp_skill = (
            await db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == employee_id,
                    EmployeeSkill.skill_id == skill.id,
                )
            )
        ).scalar_one_or_none()
        if emp_skill is None:
            emp_skill = EmployeeSkill(
                organization_id=organization_id,
                employee_id=employee_id,
                skill_id=skill.id,
                level=level,
                verified=verified,
            )
            db.add(emp_skill)
        else:
            emp_skill.level = level
            emp_skill.verified = emp_skill.verified or verified
        emp_skill.updated_at = utcnow()
        await db.flush()
        await self.boost_skill(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_name=skill.name, points=0.0, source="manual",
            emit=False,
        )
        return emp_skill

    # ------------------------------------------------------------------ gaps

    async def detect_gaps(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        required: Optional[list[dict[str, Any]]] = None,
        source: str = "role_framework",
    ) -> list[SkillGap]:
        """Compare required skills against the current graph and persist gaps."""
        if required is None:
            from app.learning.career_service import career_service
            required = await career_service.required_skills_for_employee(
                db, organization_id=organization_id, employee_id=employee_id
            )
        graph = {row["name"].lower(): row["level"] for row in await self.graph(db, organization_id=organization_id, employee_id=employee_id)}
        created: list[SkillGap] = []
        for requirement in required or []:
            name = requirement.get("skill") or requirement.get("name")
            if not name:
                continue
            required_level = int(requirement.get("level", 3))
            current = graph.get(name.lower(), 0)
            gap_value = max(0.0, required_level - current)
            if gap_value <= 0:
                # skill is at or above requirement — close any stale gap
                stale = (
                    await db.execute(
                        select(SkillGap).where(
                            SkillGap.organization_id == organization_id,
                            SkillGap.employee_id == employee_id,
                            SkillGap.skill_name == name,
                            SkillGap.status == "open",
                        )
                    )
                ).scalars().all()
                for gap in stale:
                    gap.status = "closed"
                await db.flush()
                continue
            priority = "high" if gap_value >= 3 else ("medium" if gap_value == 2 else "low")
            skill = (
                await db.execute(
                    select(Skill).where(
                        Skill.organization_id == organization_id,
                        func.lower(Skill.name) == name.lower(),
                    )
                )
            ).scalar_one_or_none()
            existing = (
                await db.execute(
                    select(SkillGap).where(
                        SkillGap.organization_id == organization_id,
                        SkillGap.employee_id == employee_id,
                        SkillGap.skill_name == name,
                        SkillGap.status.in_(("open", "addressed")),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.required_level = required_level
                existing.current_level = current
                existing.gap = gap_value
                existing.priority = priority
                existing.source = source
                created.append(existing)
            else:
                gap = SkillGap(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    skill_id=skill.id if skill else None,
                    skill_name=name,
                    required_level=required_level,
                    current_level=current,
                    gap=gap_value,
                    priority=priority,
                    source=source,
                    status="open",
                )
                db.add(gap)
                created.append(gap)
        await db.flush()
        return created

    async def list_gaps(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: Optional[str] = None,
        status: str = "open",
        priority: Optional[str] = None,
        limit: int = 100,
    ) -> list[SkillGap]:
        query = select(SkillGap).where(
            SkillGap.organization_id == organization_id, SkillGap.status == status
        )
        if employee_id:
            query = query.where(SkillGap.employee_id == employee_id)
        if priority:
            query = query.where(SkillGap.priority == priority)
        query = query.order_by(SkillGap.priority.asc(), SkillGap.gap.desc()).limit(limit)
        return (await db.execute(query)).scalars().all()

    async def close_gap(self, db: AsyncSession, *, organization_id: str, gap_id: str, status: str = "closed") -> Optional[SkillGap]:
        gap = (
            await db.execute(
                select(SkillGap).where(SkillGap.organization_id == organization_id, SkillGap.id == gap_id)
            )
        ).scalar_one_or_none()
        if gap is None:
            return None
        gap.status = status
        await db.flush()
        return gap

    async def apply_assessment_result(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        skill_names: list[str],
        score_pct: float,
        source: str,
    ) -> None:
        """Passed assessments/skill evaluations update the skill graph."""
        boost = 0.5 if score_pct >= 85 else 0.0
        if score_pct < 70:
            return
        for name in skill_names or []:
            await self.boost_skill(
                db, organization_id=organization_id, employee_id=employee_id,
                skill_name=name, points=boost, source=source,
            )

    # ------------------------------------------------------------------ org skill map

    async def refresh_snapshot(self, db: AsyncSession, *, organization_id: str) -> Optional[SkillSnapshot]:
        """Recompute today's Organization Skill Map."""
        from app.core.timeutils import utcnow as _now
        today = _now().date()
        skills = (
            await db.execute(
                select(Skill).where(Skill.organization_id == organization_id)
            )
        ).scalars().all()
        latest: Optional[SkillSnapshot] = None
        for skill in skills:
            employee_rows = await db.execute(
                select(EmployeeSkill.level).where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.skill_id == skill.id,
                )
            )
            levels = [level for (level,) in employee_rows.all()]
            gaps = (
                await db.execute(
                    select(func.count(SkillGap.id), func.sum(SkillGap.gap)).where(
                        SkillGap.organization_id == organization_id,
                        SkillGap.skill_id == skill.id,
                        SkillGap.status == "open",
                    )
                )
            ).one()
            open_gaps = gaps[0] or 0
            high_gaps = (
                (
                    await db.execute(
                        select(func.count(SkillGap.id)).where(
                            SkillGap.organization_id == organization_id,
                            SkillGap.skill_id == skill.id,
                            SkillGap.status == "open",
                            SkillGap.priority == "high",
                        )
                    )
                ).scalar()
                or 0
            )
            average = round(sum(levels) / len(levels), 2) if levels else 0.0
            demand = min(5, max(1, int(round(open_gaps * 1.5))) or (1 if not levels else 1))
            snapshot = (
                await db.execute(
                    select(SkillSnapshot).where(
                        SkillSnapshot.organization_id == organization_id,
                        SkillSnapshot.skill_id == skill.id,
                        SkillSnapshot.snapshot_date == today,
                    )
                )
            ).scalar_one_or_none()
            if snapshot is None:
                snapshot = SkillSnapshot(
                    organization_id=organization_id,
                    skill_id=skill.id,
                    skill_name=skill.name,
                    snapshot_date=today,
                )
                db.add(snapshot)
            snapshot.employee_count = len(levels)
            snapshot.average_level = average
            snapshot.max_level = max(levels) if levels else 0.0
            snapshot.open_gaps = open_gaps
            snapshot.high_gaps = high_gaps
            snapshot.demand_level = demand
            snapshot.projected_shortage = open_gaps >= 3 and average < 3
            latest = snapshot
        await db.flush()
        return latest

    async def org_skill_map(self, db: AsyncSession, *, organization_id: str, snapshot_date: Optional[str] = None) -> list[dict[str, Any]]:
        from datetime import date as _date
        target = _date.fromisoformat(snapshot_date) if snapshot_date else utcnow().date()
        rows = await db.execute(
            select(SkillSnapshot).where(
                SkillSnapshot.organization_id == organization_id,
                SkillSnapshot.snapshot_date == target,
            ).order_by(SkillSnapshot.demand_level.desc(), SkillSnapshot.open_gaps.desc())
        )
        return [
            {
                "skill_id": row.skill_id,
                "skill_name": row.skill_name,
                "employee_count": row.employee_count,
                "average_level": row.average_level,
                "max_level": row.max_level,
                "open_gaps": row.open_gaps,
                "high_gaps": row.high_gaps,
                "demand_level": row.demand_level,
                "projected_shortage": row.projected_shortage,
                "snapshot_date": row.snapshot_date.isoformat(),
            }
            for row in rows.scalars().all()
        ]

    async def who_has_skill(self, db: AsyncSession, *, organization_id: str, skill_name: str, min_level: int = 3, limit: int = 20) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(EmployeeSkill, Employee)
            .join(Skill, Skill.id == EmployeeSkill.skill_id)
            .join(Employee, Employee.id == EmployeeSkill.employee_id)
            .where(
                EmployeeSkill.organization_id == organization_id,
                func.lower(Skill.name) == skill_name.lower(),
                EmployeeSkill.level >= min_level,
                Employee.status == "active",
            )
            .order_by(EmployeeSkill.level.desc())
            .limit(limit)
        )
        return [
            {
                "employee_id": emp_skill.employee_id,
                "name": employee.full_name,
                "designation": employee.designation,
                "level": emp_skill.level,
                "label": _LEVEL_LABELS.get(emp_skill.level, "intermediate"),
                "verified": emp_skill.verified,
            }
            for emp_skill, employee in rows.all()
        ]

    async def can_mentor(self, db: AsyncSession, *, organization_id: str, skill_name: str, min_level: int = 4) -> list[dict[str, Any]]:
        """Employees qualified to mentor a skill (expertise + mentor profile)."""
        return await self.who_has_skill(db, organization_id=organization_id, skill_name=skill_name, min_level=min_level, limit=20)


skill_service = SkillService()
