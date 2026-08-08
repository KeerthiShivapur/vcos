"""Department, business unit, and location services (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import BusinessUnit, Department, Location
from app.models.employee import Employee, EmployeeSkill
from app.models.skill import Skill
from app.models.team import Team
from app.services.audit_service import audit_service
from app.services.event_service import event_service

logger = logging.getLogger("vcos.people")


class DepartmentService:
    async def _check_unique(
        self, db: AsyncSession, organization_id: str, model: type, field: str, value: str, exclude_id: Optional[str] = None
    ) -> None:
        result = await db.execute(
            select(model).where(
                getattr(model, "organization_id") == organization_id,
                func.lower(getattr(model, field)) == value.strip().lower(),
            )
        )
        row = result.scalar_one_or_none()
        if row is not None and row.id != exclude_id:
            raise ValueError(f"{model.__name__} with this {field} already exists")

    # ------------------------------------------------------------------ departments

    async def create_department(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Department:
        await self._check_unique(db, organization_id, Department, "code", data["code"])
        await self._check_unique(db, organization_id, Department, "name", data["name"])
        for ref in ("parent_id", "head_id", "location_id"):
            if data.get(ref):
                await self._validate_ref(db, organization_id, ref, data[ref])
        dep = Department(organization_id=organization_id, **data)
        db.add(dep)
        await db.flush()
        await event_service.emit(
            db, name="department.created", actor_id=actor.id if actor else None,
            organization_id=organization_id, payload={"department_id": dep.id, "code": dep.code},
        )
        await audit_service.log(
            db, organization_id=organization_id, action="department.created",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="department", resource_id=dep.id, ip_address=ip_address,
        )
        return dep

    async def update_department(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        department: Department,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Department:
        if data.get("code"):
            await self._check_unique(db, organization_id, Department, "code", data["code"], department.id)
        if data.get("name"):
            await self._check_unique(db, organization_id, Department, "name", data["name"], department.id)
        for ref in ("parent_id", "head_id", "location_id"):
            if data.get(ref):
                await self._validate_ref(db, organization_id, ref, data[ref])
        for field, value in data.items():
            setattr(department, field, value)
        await db.flush()
        await event_service.emit(
            db, name="department.updated", actor_id=actor.id if actor else None,
            organization_id=organization_id,
            payload={"department_id": department.id, "fields": list(data.keys())},
        )
        await audit_service.log(
            db, organization_id=organization_id, action="department.updated",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="department", resource_id=department.id, ip_address=ip_address,
            details={"fields": list(data.keys())},
        )
        return department

    async def list_departments(self, db: AsyncSession, *, organization_id: str) -> list[Department]:
        result = await db.execute(
            select(Department)
            .where(Department.organization_id == organization_id)
            .order_by(Department.name.asc())
        )
        depts = list(result.scalars().all())
        await self._hydrate_departments(db, organization_id, depts)
        return depts

    async def get_department(
        self, db: AsyncSession, *, organization_id: str, department_id: str
    ) -> Optional[Department]:
        dep = await db.get(Department, department_id)
        if dep is None or dep.organization_id != organization_id:
            return None
        await self._hydrate_departments(db, organization_id, [dep])
        return dep

    async def department_stats(
        self, db: AsyncSession, *, organization_id: str, department_id: str
    ) -> dict[str, Any]:
        dep = await self.get_department(db, organization_id=organization_id, department_id=department_id)
        if dep is None:
            raise ValueError("Department not found")
        members, avg = (
            await db.execute(
                select(func.count(), func.coalesce(func.avg(Employee.expertise_score), 0.0))
                .select_from(Employee)
                .where(
                    Employee.organization_id == organization_id,
                    Employee.department_id == department_id,
                    Employee.status.in_(("active", "probation", "notice")),
                )
            )
        ).all()[0]
        skill_rows = (
            await db.execute(
                select(EmployeeSkill.skill_id, Skill.name, func.count())
                .select_from(EmployeeSkill)
                .join(Employee, Employee.id == EmployeeSkill.employee_id)
                .join(Skill, Skill.id == EmployeeSkill.skill_id)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    Employee.department_id == department_id,
                )
                .group_by(EmployeeSkill.skill_id, Skill.name)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
        return {
            "department_id": dep.id,
            "department_name": dep.name,
            "members": members,
            "teams": len(dep.teams),
            "avg_expertise": round(float(avg), 1),
            "skills": [{"skill": name, "count": count} for _, name, count in skill_rows],
        }

    async def _validate_ref(
        self, db: AsyncSession, organization_id: str, ref: str, value: str
    ) -> None:
        model = {
            "parent_id": Department,
            "head_id": Employee,
            "location_id": Location,
        }[ref]
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {ref} reference")

    async def _hydrate_departments(
        self, db: AsyncSession, organization_id: str, depts: list[Department]
    ) -> None:
        if not depts:
            return
        ids = [d.id for d in depts]
        member_counts = dict(
            (
                await db.execute(
                    select(Employee.department_id, func.count())
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.department_id.in_(ids),
                        Employee.status.in_(("active", "probation", "notice")),
                    )
                    .group_by(Employee.department_id)
                )
            ).all()
        )
        team_counts = dict(
            (
                await db.execute(
                    select(Team.department_id, func.count())
                    .where(Team.organization_id == organization_id, Team.department_id.in_(ids))
                    .group_by(Team.department_id)
                )
            ).all()
        )
        name_map: dict[str, str] = {}
        ref_ids = {d.parent_id for d in depts if d.parent_id}
        ref_ids |= {d.head_id for d in depts if d.head_id}
        ref_ids |= {d.location_id for d in depts if d.location_id}
        if ref_ids:
            all_refs = (
                await db.execute(
                    select(Department).where(
                        Department.organization_id == organization_id, Department.id.in_(ref_ids)
                    )
                )
            ).scalars().all()
            name_map.update({d.id: d.name for d in all_refs})
            heads = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id, Employee.id.in_(ref_ids)
                    )
                )
            ).scalars().all()
            name_map.update({e.id: e.full_name for e in heads})
            locs = (
                await db.execute(
                    select(Location).where(
                        Location.organization_id == organization_id, Location.id.in_(ref_ids)
                    )
                )
            ).scalars().all()
            name_map.update({l.id: l.name for l in locs})
        for d in depts:
            d.parent_name = name_map.get(d.parent_id)
            d.head_name = name_map.get(d.head_id)
            d.location_name = name_map.get(d.location_id)
            d.members_count = member_counts.get(d.id, 0)
            d.teams_count = team_counts.get(d.id, 0)
        children_map: dict[str, list[Department]] = {d.id: [] for d in depts}
        if depts:
            child_rows = (
                await db.execute(
                    select(Department).where(
                        Department.organization_id == organization_id,
                        Department.parent_id.in_(ids),
                    )
                )
            ).scalars().all()
            for child in child_rows:
                children_map.setdefault(child.parent_id, []).append(child)
        for d in depts:
            d._children = children_map.get(d.id, [])

    # ------------------------------------------------------------------ business units

    async def create_business_unit(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]
    ) -> BusinessUnit:
        await self._check_unique(db, organization_id, BusinessUnit, "code", data["code"])
        if data.get("head_id"):
            head = await db.get(Employee, data["head_id"])
            if head is None or head.organization_id != organization_id:
                raise ValueError("Invalid head reference")
        bu = BusinessUnit(organization_id=organization_id, **data)
        db.add(bu)
        await db.flush()
        await event_service.emit(
            db, name="business_unit.created", organization_id=organization_id,
            payload={"business_unit_id": bu.id, "code": bu.code},
        )
        return bu

    async def list_business_units(
        self, db: AsyncSession, *, organization_id: str
    ) -> list[BusinessUnit]:
        result = await db.execute(
            select(BusinessUnit)
            .where(BusinessUnit.organization_id == organization_id)
            .order_by(BusinessUnit.name.asc())
        )
        units = list(result.scalars().all())
        await self._hydrate_business_units(db, organization_id, units)
        return units

    async def _hydrate_business_units(
        self, db: AsyncSession, organization_id: str, units: list[BusinessUnit]
    ) -> None:
        if not units:
            return
        ids = [u.id for u in units]
        counts = dict(
            (
                await db.execute(
                    select(Employee.business_unit_id, func.count())
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.business_unit_id.in_(ids),
                        Employee.status.in_(("active", "probation", "notice")),
                    )
                    .group_by(Employee.business_unit_id)
                )
            ).all()
        )
        heads: dict[str, str] = {}
        head_ids = {u.head_id for u in units if u.head_id}
        if head_ids:
            rows = await db.execute(
                select(Employee.id, Employee.first_name, Employee.last_name, Employee.display_name)
                .where(Employee.organization_id == organization_id, Employee.id.in_(head_ids))
            )
            for hid, first, last, display in rows.all():
                heads[hid] = display or f"{first} {last}".strip()
        for u in units:
            u.head_name = heads.get(u.head_id)
            u.employees_count = counts.get(u.id, 0)

    # ------------------------------------------------------------------ locations

    async def create_location(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]
    ) -> Location:
        await self._check_unique(db, organization_id, Location, "code", data["code"])
        loc = Location(organization_id=organization_id, **data)
        db.add(loc)
        await db.flush()
        await event_service.emit(
            db, name="location.created", organization_id=organization_id,
            payload={"location_id": loc.id, "code": loc.code},
        )
        return loc

    async def list_locations(self, db: AsyncSession, *, organization_id: str) -> list[Location]:
        result = await db.execute(
            select(Location)
            .where(Location.organization_id == organization_id)
            .order_by(Location.name.asc())
        )
        locs = list(result.scalars().all())
        ids = [l.id for l in locs]
        if ids:
            counts = dict(
                (
                    await db.execute(
                        select(Employee.location_id, func.count())
                        .where(
                            Employee.organization_id == organization_id,
                            Employee.location_id.in_(ids),
                            Employee.status.in_(("active", "probation", "notice")),
                        )
                        .group_by(Employee.location_id)
                    )
                ).all()
            )
            for l in locs:
                l.employees_count = counts.get(l.id, 0)
        return locs


department_service = DepartmentService()
