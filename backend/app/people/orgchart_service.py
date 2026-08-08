"""Organization chart services (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeePresence
from app.models.organization import Organization

logger = logging.getLogger("vcos.people")

ACTIVE_STATUSES = ("active", "probation", "notice")


class OrgChartService:
    async def chart(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        department_id: Optional[str] = None,
        team_id: Optional[str] = None,
        max_depth: int = 6,
    ) -> dict[str, Any]:
        """Build a rooted reporting tree. Returns {"root", "roots", "total", "max_depth"}."""
        from app.models.department import Department
        from app.models.team import Team

        filters = [Employee.organization_id == organization_id, Employee.status.in_(ACTIVE_STATUSES)]
        if department_id:
            filters.append(Employee.department_id == department_id)
        if team_id:
            filters.append(Employee.team_id == team_id)
        result = await db.execute(
            select(Employee).where(*filters).order_by(Employee.joining_date.asc())
        )
        employees = list(result.scalars().all())
        if not employees:
            return {"root": None, "roots": [], "total": 0, "max_depth": 0}

        dep_map: dict[str, str] = {}
        team_map: dict[str, str] = {}
        dep_ids = {e.department_id for e in employees if e.department_id}
        team_ids = {e.team_id for e in employees if e.team_id}
        if dep_ids:
            dep_map = {
                d.id: d.name
                for d in (
                    await db.execute(
                        select(Department).where(Department.organization_id == organization_id, Department.id.in_(dep_ids))
                    )
                ).scalars().all()
            }
        if team_ids:
            team_map = {
                t.id: t.name
                for t in (
                    await db.execute(
                        select(Team).where(Team.organization_id == organization_id, Team.id.in_(team_ids))
                    )
                ).scalars().all()
            }
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

        def to_node(emp: Employee) -> dict[str, Any]:
            return {
                "id": emp.id,
                "employee_number": emp.employee_number,
                "name": emp.full_name,
                "designation": emp.designation,
                "department": dep_map.get(emp.department_id),
                "team": team_map.get(emp.team_id),
                "avatar_url": emp.avatar_url,
                "is_online": emp.id in online_ids,
                "children": [],
            }

        by_id = {e.id: e for e in employees}
        nodes = {e.id: to_node(e) for e in employees}
        roots: list[dict[str, Any]] = []
        for e in employees:
            if e.manager_id in by_id and e.manager_id != e.id:
                nodes[e.manager_id]["children"].append(nodes[e.id])
            else:
                roots.append(nodes[e.id])

        depth = 0

        def measure(node: dict[str, Any], level: int) -> int:
            nonlocal depth
            depth = max(depth, level)
            for child in node["children"]:
                measure(child, level + 1)
            return depth

        for root in roots:
            measure(root, 1)

        return {
            "root": roots[0] if len(roots) == 1 else None,
            "roots": roots,
            "total": len(employees),
            "max_depth": depth,
        }

    async def team_breakdown(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        result = await db.execute(
            select(Employee.department_id, func.count())
            .where(
                Employee.organization_id == organization_id,
                Employee.department_id.isnot(None),
                Employee.status.in_(ACTIVE_STATUSES),
            )
            .group_by(Employee.department_id)
        )
        return [{"department_id": dep_id, "count": count} for dep_id, count in result.all()]

    async def department_breakdown(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        return await self.team_breakdown(db, organization_id=organization_id)


orgchart_service = OrgChartService()
