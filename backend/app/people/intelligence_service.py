"""Organization intelligence — the living pulse of the org (Phase 2)."""

import logging
from collections import deque
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import (
    Employee,
    EmployeeAvailability,
    EmployeePresence,
    EmployeeSkill,
    EmployeeTimeline,
)
from app.models.skill import Skill
from app.schemas.people import OrgIntelligence

logger = logging.getLogger("vcos.people")

ACTIVE_STATUSES = ("active", "probation", "notice")


class IntelligenceService:
    async def compute(self, db: AsyncSession, *, organization_id: str) -> OrgIntelligence:
        from app.models.department import BusinessUnit, Department, Location
        from app.models.team import Team

        total_employees = (
            await db.execute(
                select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id)
            )
        ).scalar_one()
        active_employees = (
            await db.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one()

        departments = (
            await db.execute(
                select(func.count()).select_from(Department).where(Department.organization_id == organization_id)
            )
        ).scalar_one()
        teams = (
            await db.execute(
                select(func.count()).select_from(Team).where(Team.organization_id == organization_id)
            )
        ).scalar_one()
        locations = (
            await db.execute(
                select(func.count()).select_from(Location).where(Location.organization_id == organization_id)
            )
        ).scalar_one()
        business_units = (
            await db.execute(
                select(func.count()).select_from(BusinessUnit).where(BusinessUnit.organization_id == organization_id)
            )
        ).scalar_one()

        managers = (
            await db.execute(
                select(func.count(func.distinct(Employee.manager_id))).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.manager_id.isnot(None),
                )
            )
        ).scalar_one()

        avg_expertise, avg_completion = (
            await db.execute(
                select(
                    func.coalesce(func.avg(Employee.expertise_score), 0.0),
                    func.coalesce(func.avg(Employee.profile_completion), 0.0),
                ).where(Employee.organization_id == organization_id)
            )
        ).all()[0]

        online_now = (
            await db.execute(
                select(func.count()).select_from(EmployeePresence).where(
                    EmployeePresence.organization_id == organization_id,
                    EmployeePresence.is_online.is_(True),
                )
            )
        ).scalar_one()
        on_leave = (
            await db.execute(
                select(func.count()).select_from(EmployeeAvailability).where(
                    EmployeeAvailability.organization_id == organization_id,
                    EmployeeAvailability.status == "leave",
                )
            )
        ).scalar_one()

        recent_joins = [
            {
                "employee_id": e.id,
                "name": e.full_name,
                "designation": e.designation,
                "employee_number": e.employee_number,
                "joining_date": e.joining_date,
            }
            for e in (
                await db.execute(
                    select(Employee)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.joining_date.isnot(None),
                    )
                    .order_by(Employee.joining_date.desc())
                    .limit(5)
                )
            ).scalars().all()
        ]

        recent_transfers = [
            {
                "employee_id": row.employee_id,
                "title": row.title,
                "description": row.description,
                "occurred_at": row.occurred_at,
            }
            for row in (
                await db.execute(
                    select(EmployeeTimeline)
                    .where(
                        EmployeeTimeline.organization_id == organization_id,
                        EmployeeTimeline.kind == "transfer",
                    )
                    .order_by(EmployeeTimeline.occurred_at.desc())
                    .limit(5)
                )
            ).scalars().all()
        ]

        dep_dist = [
            {"department_id": dep_id, "name": name, "count": count}
            for dep_id, name, count in (
                await db.execute(
                    select(Employee.department_id, Department.name, func.count())
                    .join(Department, Department.id == Employee.department_id)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.department_id.isnot(None),
                        Employee.status.in_(ACTIVE_STATUSES),
                    )
                    .group_by(Employee.department_id, Department.name)
                    .order_by(func.count().desc())
                )
            ).all()
        ]
        team_dist = [
            {"team_id": team_id, "name": name, "count": count}
            for team_id, name, count in (
                await db.execute(
                    select(Employee.team_id, Team.name, func.count())
                    .join(Team, Team.id == Employee.team_id)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.team_id.isnot(None),
                        Employee.status.in_(ACTIVE_STATUSES),
                    )
                    .group_by(Employee.team_id, Team.name)
                    .order_by(func.count().desc())
                )
            ).all()
        ]
        loc_dist = [
            {"location_id": loc_id, "name": name, "count": count}
            for loc_id, name, count in (
                await db.execute(
                    select(Employee.location_id, Location.name, func.count())
                    .join(Location, Location.id == Employee.location_id)
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.location_id.isnot(None),
                        Employee.status.in_(ACTIVE_STATUSES),
                    )
                    .group_by(Employee.location_id, Location.name)
                    .order_by(func.count().desc())
                )
            ).all()
        ]
        skill_dist = [
            {"skill_id": skill_id, "name": name, "count": count}
            for skill_id, name, count in (
                await db.execute(
                    select(EmployeeSkill.skill_id, Skill.name, func.count(func.distinct(EmployeeSkill.employee_id)))
                    .join(Skill, Skill.id == EmployeeSkill.skill_id)
                    .where(EmployeeSkill.organization_id == organization_id)
                    .group_by(EmployeeSkill.skill_id, Skill.name)
                    .order_by(func.count(func.distinct(EmployeeSkill.employee_id)).desc())
                    .limit(8)
                )
            ).all()
        ]

        now = utcnow()
        joins_30 = await self._joins_since(db, organization_id=organization_id, days=30)
        joins_90 = await self._joins_since(db, organization_id=organization_id, days=90)

        reporting_depth, management_span = await self._structure_metrics(
            db, organization_id=organization_id
        )

        score = 0.0
        score += min(avg_completion / 10, 10.0)  # up to 10
        score += min(avg_expertise / 10, 10.0)  # up to 10
        score += min(online_now / max(active_employees, 1) * 10, 10.0)  # up to 10
        score += min((departments + teams) / max(active_employees, 1) * 25, 15.0)  # up to 15
        score += 20.0 if managers > 0 else 0.0  # up to 20
        score += min(active_employees / max(total_employees, 1) * 35, 35.0)  # up to 35
        org_health = max(0, min(100, int(round(score))))

        return OrgIntelligence(
            total_employees=total_employees,
            active_employees=active_employees,
            departments=departments,
            teams=teams,
            locations=locations,
            business_units=business_units,
            managers=managers,
            avg_expertise=round(float(avg_expertise), 1),
            avg_profile_completion=round(float(avg_completion), 1),
            online_now=online_now,
            on_leave=on_leave,
            recent_joins=recent_joins,
            recent_transfers=recent_transfers,
            department_distribution=dep_dist,
            team_distribution=team_dist,
            location_distribution=loc_dist,
            skill_distribution=skill_dist,
            growth_30d=joins_30,
            growth_90d=joins_90,
            reporting_depth=reporting_depth,
            management_span=round(management_span, 2),
            org_health=org_health,
        )

    async def _joins_since(
        self, db: AsyncSession, *, organization_id: str, days: int
    ) -> int:
        cutoff = utcnow() - timedelta(days=days)
        return (
            await db.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.joining_date.isnot(None),
                    func.date(Employee.joining_date) >= cutoff.date(),
                )
            )
        ).scalar_one()

    async def _structure_metrics(
        self, db: AsyncSession, *, organization_id: str
    ) -> tuple[int, float]:
        employees = (
            await db.execute(
                select(Employee.id, Employee.manager_id).where(
                    Employee.organization_id == organization_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
            )
        ).all()
        if not employees:
            return 0, 0.0
        by_id = {eid: manager_id for eid, manager_id in employees}
        children: dict[str, list[str]] = {eid: [] for eid in by_id}
        for eid, manager_id in employees:
            if manager_id in by_id and manager_id != eid:
                children[manager_id].append(eid)
        max_depth = 0
        for eid in by_id:
            if by_id[eid] not in by_id:
                queue = deque([(eid, 1)])
                while queue:
                    node, depth = queue.popleft()
                    max_depth = max(max_depth, depth)
                    for child in children.get(node, []):
                        queue.append((child, depth + 1))
        with_subordinates = sum(1 for eid in by_id if children.get(eid))
        span = (
            sum(len(c) for c in children.values()) / with_subordinates
            if with_subordinates
            else 0.0
        )
        return max_depth, span


intelligence_service = IntelligenceService()
