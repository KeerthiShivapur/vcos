"""Expertise engine — skills catalog, scoring, experts, successors, mentors (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.models.employee import Employee, EmployeePresence, EmployeeSkill
from app.models.skill import ExpertiseScore, Skill
from app.services.event_service import event_service

logger = logging.getLogger("vcos.people")

ACTIVE_STATUSES = ("active", "probation", "notice")


class ExpertiseService:
    # ------------------------------------------------------------------ skill catalog

    async def create_skill(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]
    ) -> Skill:
        name = data["name"].strip()
        existing = (
            await db.execute(
                select(Skill).where(
                    Skill.organization_id == organization_id,
                    func.lower(Skill.name) == name.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        skill = Skill(organization_id=organization_id, name=name, category=data.get("category"),
                      description=data.get("description"))
        db.add(skill)
        await db.flush()
        await event_service.emit(
            db, name="skill.created", organization_id=organization_id,
            payload={"skill_id": skill.id, "name": skill.name},
        )
        return skill

    async def list_skills(
        self, db: AsyncSession, *, organization_id: str, category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Skill]:
        filters = [Skill.organization_id == organization_id]
        if category:
            filters.append(Skill.category == category)
        if search:
            filters.append(Skill.name.ilike(f"%{search.strip()}%"))
        result = await db.execute(
            select(Skill).where(*filters).order_by(Skill.category.asc(), Skill.name.asc())
        )
        skills = list(result.scalars().all())
        if skills:
            ids = [s.id for s in skills]
            counts = dict(
                (
                    await db.execute(
                        select(EmployeeSkill.skill_id, func.count(func.distinct(EmployeeSkill.employee_id)))
                        .where(
                            EmployeeSkill.organization_id == organization_id,
                            EmployeeSkill.skill_id.in_(ids),
                        )
                        .group_by(EmployeeSkill.skill_id)
                    )
                ).all()
            )
            for s in skills:
                s.employees_count = counts.get(s.id, 0)
        return skills

    async def categories(self, db: AsyncSession, *, organization_id: str) -> list[str]:
        result = await db.execute(
            select(Skill.category)
            .where(Skill.organization_id == organization_id, Skill.category.isnot(None))
            .distinct()
            .order_by(Skill.category.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ scoring

    async def recompute_for_employee(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[ExpertiseScore]:
        """Recompute expertise scores from skill rows. score = 0..100."""
        rows = (
            await db.execute(
                select(EmployeeSkill)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id == employee_id,
                )
            )
        ).scalars().all()
        existing = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                )
            )
        ).scalars().all()
        by_skill = {s.skill_id: s for s in existing}
        total = 0.0
        now = utcnow()
        for row in rows:
            score = round(
                min(100.0, (row.level / 5.0) * 70.0 + min(row.years_experience, 10.0) / 10.0 * 30.0),
                1,
            )
            entry = by_skill.get(row.skill_id)
            factors = {"level": row.level, "years_experience": row.years_experience, "verified": row.verified}
            if entry is None:
                entry = ExpertiseScore(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    skill_id=row.skill_id,
                    score=score,
                    level=row.level,
                    years_experience=row.years_experience,
                    factors=factors,
                    updated_at=now,
                )
                db.add(entry)
            else:
                entry.score = score
                entry.level = row.level
                entry.years_experience = row.years_experience
                entry.factors = factors
                entry.updated_at = now
            total += score
        for skill_id, entry in by_skill.items():
            if skill_id not in {r.skill_id for r in rows}:
                await db.delete(entry)
        await db.flush()

        employee = await db.get(Employee, employee_id)
        if employee:
            employee.expertise_score = round(total / len(rows), 1) if rows else 0.0
            await db.flush()
        return (
            await db.execute(
                select(ExpertiseScore)
                .join(Skill, Skill.id == ExpertiseScore.skill_id)
                .options(joinedload(ExpertiseScore.skill))
                .where(
                    ExpertiseScore.organization_id == organization_id,
                    ExpertiseScore.employee_id == employee_id,
                )
                .order_by(ExpertiseScore.score.desc())
            )
        ).scalars().all()

    async def recompute_all(self, db: AsyncSession, *, organization_id: str) -> int:
        employees = (
            await db.execute(
                select(Employee.id).where(Employee.organization_id == organization_id)
            )
        ).scalars().all()
        for employee_id in employees:
            await self.recompute_for_employee(db, organization_id=organization_id, employee_id=employee_id)
        await db.flush()
        return len(employees)

    async def employee_scores(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[ExpertiseScore]:
        result = await db.execute(
            select(ExpertiseScore)
            .join(Skill, Skill.id == ExpertiseScore.skill_id)
            .options(joinedload(ExpertiseScore.skill))
            .where(
                ExpertiseScore.organization_id == organization_id,
                ExpertiseScore.employee_id == employee_id,
            )
            .order_by(ExpertiseScore.score.desc())
        )
        return list(result.scalars().all())

    async def experts(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        skill_id: Optional[str] = None,
        skill_name: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from app.models.department import Department
        from app.models.team import Team

        filters = [
            ExpertiseScore.organization_id == organization_id,
            Employee.status.in_(ACTIVE_STATUSES),
            ExpertiseScore.score > 0,
        ]
        query = (
            select(ExpertiseScore, Employee, Skill, Department.name, Team.name)
            .join(Employee, Employee.id == ExpertiseScore.employee_id)
            .join(Skill, Skill.id == ExpertiseScore.skill_id)
            .outerjoin(Department, Department.id == Employee.department_id)
            .outerjoin(Team, Team.id == Employee.team_id)
            .where(*filters)
        )
        if skill_id:
            query = query.where(ExpertiseScore.skill_id == skill_id)
        if skill_name:
            query = query.where(Skill.name.ilike(f"%{skill_name.strip()}%"))
        if category:
            query = query.where(Skill.category == category)
        rows = (
            await db.execute(
                query.order_by(ExpertiseScore.score.desc(), ExpertiseScore.level.desc())
                .limit(limit)
            )
        ).all()
        online_ids = set(
            (
                await db.execute(
                    select(EmployeePresence.employee_id).where(
                        EmployeePresence.organization_id == organization_id,
                        EmployeePresence.is_online.is_(True),
                    )
                )
            ).scalars().all()
        )
        return [
            {
                "employee_id": emp.id,
                "employee_number": emp.employee_number,
                "name": emp.full_name,
                "designation": emp.designation,
                "department": dep_name,
                "team": team_name,
                "avatar_url": emp.avatar_url,
                "skill": skill.name,
                "score": round(score.score, 1),
                "level": score.level,
                "years_experience": score.years_experience,
                "is_online": emp.id in online_ids,
            }
            for score, emp, skill, dep_name, team_name in rows
        ]

    # ------------------------------------------------------------------ successors & mentors

    async def successors(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            raise ValueError("Employee not found")
        from app.models.department import Department

        my_skills = {
            skill_id: level
            for skill_id, level in (
                await db.execute(
                    select(EmployeeSkill.skill_id, EmployeeSkill.level).where(
                        EmployeeSkill.organization_id == organization_id,
                        EmployeeSkill.employee_id == employee_id,
                    )
                )
            ).all()
        }
        if not my_skills:
            return []
        candidates = (
            await db.execute(
                select(Employee)
                .where(
                    Employee.organization_id == organization_id,
                    Employee.id != employee_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
                .limit(100)
            )
        ).scalars().all()
        rows = (
            await db.execute(
                select(EmployeeSkill.employee_id, EmployeeSkill.skill_id, EmployeeSkill.level,
                       EmployeeSkill.years_experience, EmployeeSkill.verified)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.skill_id.in_(my_skills.keys()),
                )
            )
        ).all()
        skills_by_emp: dict[str, list] = {}
        for emp_id, skill_id, level, years, verified in rows:
            skills_by_emp.setdefault(emp_id, []).append((skill_id, level, years, verified))

        dep_map: dict[str, str] = {}
        dep_ids = {e.department_id for e in candidates if e.department_id}
        if dep_ids:
            dep_map = {
                d.id: d.name
                for d in (
                    await db.execute(
                        select(Department).where(
                            Department.organization_id == organization_id, Department.id.in_(dep_ids)
                        )
                    )
                ).scalars().all()
            }

        ranked: list[dict[str, Any]] = []
        for candidate in candidates:
            their_skills = skills_by_emp.get(candidate.id, [])
            if not their_skills:
                continue
            overlap = sum(
                my_skills.get(skill_id, 0) * level for skill_id, level, _, _ in their_skills
            )
            score = round(min(100.0, overlap * 2.0 + candidate.expertise_score * 0.5), 1)
            if score <= 0:
                continue
            shared = sorted(
                (my_skills.get(skill_id, 0) for skill_id, _, _, _ in their_skills), reverse=True
            )
            reasons = [
                f"Shares {len(their_skills)} skill(s) with the role holder",
                f"Expertise score {candidate.expertise_score:.0f}",
            ]
            if candidate.department_id == employee.department_id:
                reasons.append("Same department")
            ranked.append(
                {
                    "employee_id": candidate.id,
                    "employee_number": candidate.employee_number,
                    "name": candidate.full_name,
                    "designation": candidate.designation,
                    "department": dep_map.get(candidate.department_id),
                    "avatar_url": candidate.avatar_url,
                    "score": score,
                    "reasons": reasons[:3],
                }
            )
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return ranked[:limit]

    async def mentors(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        skill_id: Optional[str] = None, skill_name: Optional[str] = None, limit: int = 5,
    ) -> list[dict[str, Any]]:
        experts = await self.experts(
            db, organization_id=organization_id, skill_id=skill_id,
            skill_name=skill_name, limit=limit + 1,
        )
        return [
            {**e, "mentor_name": e["name"]}
            for e in experts
            if e["employee_id"] != employee_id and not (
                skill_id is None and skill_name is None and e["employee_id"] == employee_id
            )
        ][:limit]

    async def mentors_for(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        skill_id: Optional[str] = None, skill_name: Optional[str] = None, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return only the fields MentorOut needs."""
        rows = await self.mentors(
            db, organization_id=organization_id, employee_id=employee_id,
            skill_id=skill_id, skill_name=skill_name, limit=limit,
        )
        return [
            {
                "employee_id": r["employee_id"],
                "name": r["name"],
                "designation": r["designation"],
                "skill": r["skill"],
                "score": r["score"],
                "years_experience": r["years_experience"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ gaps

    async def skill_gaps(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        skills = (
            await db.execute(
                select(Skill).where(Skill.organization_id == organization_id)
            )
        ).scalars().all()
        if not skills:
            return []
        skill_ids = [s.id for s in skills]
        supply = dict(
            (
                await db.execute(
                    select(EmployeeSkill.skill_id, func.count(func.distinct(EmployeeSkill.employee_id)))
                    .where(
                        EmployeeSkill.organization_id == organization_id,
                        EmployeeSkill.skill_id.in_(skill_ids),
                    )
                    .group_by(EmployeeSkill.skill_id)
                )
            ).all()
        )
        dept_skill = dict(
            (
                await db.execute(
                    select(Skill.id, func.count(func.distinct(Employee.department_id)))
                    .select_from(EmployeeSkill)
                    .join(Skill, Skill.id == EmployeeSkill.skill_id)
                    .join(Employee, Employee.id == EmployeeSkill.employee_id)
                    .where(
                        EmployeeSkill.organization_id == organization_id,
                        EmployeeSkill.skill_id.in_(skill_ids),
                        Employee.department_id.isnot(None),
                        Employee.status.in_(ACTIVE_STATUSES),
                    )
                    .group_by(Skill.id)
                )
            ).all()
        )
        headcount = (
            await db.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one()
        gaps: list[dict[str, Any]] = []
        for skill in skills:
            supply_count = supply.get(skill.id, 0)
            if supply_count == 0:
                continue
            demand = max(supply_count, int(round(headcount * 0.4)))
            ratio = round(supply_count / demand, 2) if demand else 1.0
            gaps.append(
                {
                    "skill": skill.name,
                    "category": skill.category,
                    "demand": demand,
                    "supply": supply_count,
                    "ratio": ratio,
                }
            )
        gaps.sort(key=lambda g: g["ratio"])
        return gaps


expertise_service = ExpertiseService()
