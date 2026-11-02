"""Employee service — the living digital identity of the organization (Phase 2)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import (
    Employee,
    EmployeeAchievement,
    EmployeeAvailability,
    EmployeeCertification,
    EmployeeFavorite,
    EmployeePresence,
    EmployeeSkill,
    EmployeeTimeline,
)
from app.models.skill import Skill
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.permission_service import permission_service

logger = logging.getLogger("vcos.people")

ACTIVE_STATUSES = ("active", "probation", "notice")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "intern", "freelance")

PROFILE_FIELDS = [
    "designation", "department_id", "team_id", "manager_id", "location_id",
    "employment_type", "joining_date", "bio", "phone", "timezone", "language",
]


class EmployeeService:
    # ------------------------------------------------------------------ helpers

    async def next_employee_number(self, db: AsyncSession, organization_id: str) -> str:
        count = (
            await db.execute(
                select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id)
            )
        ).scalar_one()
        return f"EMP-{count + 1:04d}"

    def _valid_refs(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v
            for k, v in data.items()
            if v is not None
            and k
            in ("department_id", "team_id", "manager_id", "location_id", "business_unit_id")
        }

    async def _validate_refs(
        self, db: AsyncSession, organization_id: str, refs: dict[str, Any]
    ) -> None:
        from app.models.department import BusinessUnit, Department, Location
        from app.models.team import Team

        for key, value in refs.items():
            model = {
                "department_id": Department,
                "team_id": Team,
                "manager_id": Employee,
                "location_id": Location,
                "business_unit_id": BusinessUnit,
            }[key]
            obj = await db.get(model, value)
            if obj is None or getattr(obj, "organization_id", None) != organization_id:
                raise ValueError(f"Invalid {key.replace('_id', '')} reference")

    async def _validate_manager_cycle(
        self,
        db: AsyncSession,
        organization_id: str,
        employee: Employee,
        manager_id: Optional[str],
    ) -> None:
        """Reject manager assignments that would create a reporting cycle.

        An employee may not report to themselves, and may not report to any
        employee who already reports (transitively) to them.
        """
        if not manager_id:
            return
        if manager_id == employee.id:
            raise ValueError("An employee cannot be their own manager")
        current_id: Optional[str] = manager_id
        seen: set[str] = set()
        while current_id is not None and current_id != employee.id:
            if current_id in seen:
                # Pre-existing corrupt data — bail instead of looping forever.
                break
            seen.add(current_id)
            row = await db.execute(
                select(Employee.manager_id).where(
                    Employee.organization_id == organization_id, Employee.id == current_id
                )
            )
            current_id = row.scalar_one_or_none()
        if current_id == employee.id:
            raise ValueError("Manager assignment would create a reporting cycle")

    # ------------------------------------------------------------------ CRUD

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Employee:
        refs = self._valid_refs(data)
        await self._validate_refs(db, organization_id, refs)
        employee_number = data.get("employee_number") or await self.next_employee_number(db, organization_id)
        employee = Employee(
            organization_id=organization_id,
            employee_number=employee_number,
            first_name=data["first_name"],
            last_name=data.get("last_name"),
            display_name=data.get("display_name"),
            email=data["email"].lower(),
            phone=data.get("phone"),
            avatar_url=data.get("avatar_url"),
            designation=data.get("designation"),
            employment_type=data.get("employment_type", "full_time"),
            joining_date=data.get("joining_date") or date.today(),
            timezone=data.get("timezone", "UTC"),
            language=data.get("language", "en"),
            bio=data.get("bio"),
            emergency_contact=data.get("emergency_contact"),
            **refs,
        )
        db.add(employee)
        await db.flush()
        self._add_timeline(db, employee, "joined", f"Joined {employee.full_name}",
                           f"Employee {employee_number} created", {"employee_number": employee_number})
        await self._emit(db, employee, "employee.created", actor, ip_address)
        await audit_service.log(
            db, organization_id=organization_id, action="employee.created",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="employee", resource_id=employee.id, ip_address=ip_address,
            details={"employee_number": employee_number},
        )
        return employee

    async def create_for_user(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        email: str,
        full_name: str,
        designation: Optional[str] = None,
    ) -> Employee:
        """Create the linked employee record when a user registers."""
        names = full_name.strip().split(" ", 1)
        first = names[0]
        last = names[1] if len(names) > 1 else None
        employee = Employee(
            organization_id=organization_id,
            user_id=user_id,
            employee_id=await self.next_employee_number(db, organization_id),
            first_name=first,
            last_name=last,
            display_name=full_name,
            email=email.lower(),
            job_title=designation,
        )
        db.add(employee)
        await db.flush()
        self._add_timeline(db, employee, "joined", f"{full_name} joined the organization",
                           "Employee profile created automatically on registration",
                           {"source": "registration"})
        return employee

    async def list(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        viewer_employee_id: Optional[str] = None,
        search: Optional[str] = None,
        department_id: Optional[str] = None,
        team_id: Optional[str] = None,
        location_id: Optional[str] = None,
        business_unit_id: Optional[str] = None,
        skill: Optional[str] = None,
        availability: Optional[str] = None,
        presence: Optional[str] = None,
        status: Optional[str] = None,
        sort: str = "name",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Employee], int]:
        filters = [Employee.organization_id == organization_id]
        if status:
            filters.append(Employee.status == status)
        else:
            filters.append(Employee.status.in_(ACTIVE_STATUSES))
        if department_id:
            filters.append(Employee.department_id == department_id)
        if team_id:
            filters.append(Employee.team_id == team_id)
        if location_id:
            filters.append(Employee.location_id == location_id)
        if business_unit_id:
            filters.append(Employee.business_unit_id == business_unit_id)
        if search:
            pattern = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Employee.first_name).like(pattern),
                    func.lower(Employee.last_name).like(pattern),
                    func.lower(Employee.display_name).like(pattern),
                    func.lower(Employee.email).like(pattern),
                    func.lower(Employee.designation).like(pattern),
                    func.lower(Employee.employee_number).like(pattern),
                )
            )
        if availability:
            filters.append(EmployeeAvailability.status == availability)
        if presence == "online":
            filters.append(EmployeePresence.is_online.is_(True))
        elif presence == "offline":
            filters.append(EmployeePresence.is_online.is_(False))
        if skill:
            filters.append(Skill.name.ilike(f"%{skill.strip()}%"))

        if availability or presence:
            query = (
                select(Employee)
                .outerjoin(EmployeeAvailability, EmployeeAvailability.employee_id == Employee.id)
                .outerjoin(EmployeePresence, EmployeePresence.employee_id == Employee.id)
                .distinct()
            )
        else:
            query = select(Employee)
        if skill:
            query = query.join(EmployeeSkill, EmployeeSkill.employee_id == Employee.id).join(
                Skill, Skill.id == EmployeeSkill.skill_id
            )
        query = query.where(*filters)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        order_map = {
            "name": (Employee.first_name.asc(), Employee.last_name.asc()),
            "joined": Employee.joining_date.desc(),
            "expertise": Employee.expertise_score.desc(),
            "recent": Employee.updated_at.desc(),
            "employee_number": Employee.employee_number.asc(),
        }
        order = order_map.get(sort, order_map["name"])
        query = query.order_by(*order if isinstance(order, tuple) else (order,))
        result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        employees = list(result.scalars().all())
        await self._hydrate(db, organization_id, employees, viewer_employee_id)
        return employees, total

    async def get(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: str,
        viewer_employee_id: Optional[str] = None,
    ) -> Optional[Employee]:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return None
        await self._hydrate(db, organization_id, [employee], viewer_employee_id)
        return employee

    async def get_by_user(
        self, db: AsyncSession, *, organization_id: str, user_id: str
    ) -> Optional[Employee]:
        result = await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id, Employee.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee: Employee,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Employee:
        refs = self._valid_refs(data)
        await self._validate_refs(db, organization_id, refs)
        if refs.get("manager_id") is not None:
            await self._validate_manager_cycle(
                db, organization_id, employee, refs["manager_id"]
            )
        old = {
            "department_id": employee.department_id,
            "team_id": employee.team_id,
            "manager_id": employee.manager_id,
            "designation": employee.designation,
            "status": employee.status,
        }
        for field, value in data.items():
            if field in ("organization_id", "id", "email") or value is None and field != "manager_id":
                continue
            if field == "email" and value:
                continue
            setattr(employee, field, value)
        await db.flush()
        await self._apply_change_events(db, employee, old, actor, ip_address)
        self._add_timeline(db, employee, "profile", "Profile updated", None, {"fields": list(data.keys())})
        if old["manager_id"] != employee.manager_id:
            await audit_service.log(
                db, organization_id=organization_id, action="manager.changed",
                actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
                resource_type="employee", resource_id=employee.id, ip_address=ip_address,
                details={"from": old["manager_id"], "to": employee.manager_id},
            )
        if old["department_id"] != employee.department_id or old["team_id"] != employee.team_id:
            await audit_service.log(
                db, organization_id=organization_id, action="employee.transferred",
                actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
                resource_type="employee", resource_id=employee.id, ip_address=ip_address,
                details={"from_department": old["department_id"], "to_department": employee.department_id},
            )
        if old["designation"] != employee.designation and employee.designation:
            await audit_service.log(
                db, organization_id=organization_id, action="employee.promoted",
                actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
                resource_type="employee", resource_id=employee.id, ip_address=ip_address,
                details={"from": old["designation"], "to": employee.designation},
            )
        if old["status"] != employee.status:
            await audit_service.log(
                db, organization_id=organization_id, action="employee.status.changed",
                actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
                resource_type="employee", resource_id=employee.id, ip_address=ip_address,
                details={"from": old["status"], "to": employee.status},
            )
        return employee

    async def archive(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee: Employee,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Employee:
        employee.status = "inactive"
        await db.flush()
        self._add_timeline(db, employee, "status", "Employee archived",
                           reason or "Employee record archived", {"status": "inactive"})
        await self._emit(db, employee, "employee.archived", actor, ip_address,
                         {"reason": reason})
        await audit_service.log(
            db, organization_id=organization_id, action="employee.archived",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="employee", resource_id=employee.id, ip_address=ip_address,
            details={"reason": reason},
        )
        return employee

    # ---------------------------------------------------------------- change events

    async def _apply_change_events(
        self,
        db: AsyncSession,
        employee: Employee,
        old: dict[str, Any],
        actor: Optional[Employee],
        ip_address: Optional[str],
    ) -> None:
        if old["manager_id"] != employee.manager_id:
            self._add_timeline(db, employee, "reporting", "Manager changed",
                               f"Now reports to {employee.manager_id or 'no one'}", {})
            await self._emit(db, employee, "manager.changed", actor, ip_address,
                             {"from": old["manager_id"], "to": employee.manager_id})
        if old["department_id"] != employee.department_id or old["team_id"] != employee.team_id:
            self._add_timeline(db, employee, "transfer", "Transferred",
                               "Moved between departments/teams", {})
            await self._emit(db, employee, "employee.transferred", actor, ip_address,
                             {"from_department": old["department_id"], "to_department": employee.department_id})
        if old["designation"] != employee.designation and employee.designation:
            self._add_timeline(db, employee, "promotion", "Designation changed",
                               f"Now {employee.designation}", {"designation": employee.designation})
            await self._emit(db, employee, "employee.promoted", actor, ip_address,
                             {"from": old["designation"], "to": employee.designation})
        if old["status"] != employee.status:
            self._add_timeline(db, employee, "status", f"Status → {employee.status}", None, {})
            await self._emit(db, employee, "employee.status.changed", actor, ip_address,
                             {"from": old["status"], "to": employee.status})
        if old != {
            "department_id": employee.department_id,
            "team_id": employee.team_id,
            "manager_id": employee.manager_id,
            "designation": employee.designation,
            "status": employee.status,
        }:
            await self._emit(db, employee, "employee.updated", actor, ip_address)

    # ------------------------------------------------------------------ timeline

    def _add_timeline(
        self,
        db: AsyncSession,
        employee: Employee,
        kind: str,
        title: str,
        description: Optional[str],
        meta: Optional[dict[str, Any]] = None,
    ) -> EmployeeTimeline:
        entry = EmployeeTimeline(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            event_type=kind,
            event_title=title,
            description=description,
            event_date=utcnow().date(),
            employmenttype_metadata=meta or {},
        )
        db.add(entry)
        return entry

    async def timeline(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 50
    ) -> list[EmployeeTimeline]:
        result = await db.execute(
            select(EmployeeTimeline)
            .where(
                EmployeeTimeline.organization_id == organization_id,
                EmployeeTimeline.employee_id == employee_id,
            )
            .order_by(EmployeeTimeline.occurred_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _emit(
        self,
        db: AsyncSession,
        employee: Employee,
        name: str,
        actor: Optional[Employee],
        ip_address: Optional[str],
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = {"employee_id": employee.id, "employee_number": employee.employee_number,
                   "email": employee.email}
        if extra:
            payload.update(extra)
        await event_service.emit(
            db, name=name, actor_id=actor.id if actor else None,
            organization_id=employee.organization_id, payload=payload,
        )

    # ------------------------------------------------------------------ skills

    async def add_skill(
        self, db: AsyncSession, *, organization_id: str, employee: Employee,
        skill_id: Optional[str] = None, name: Optional[str] = None,
        level: int = 2, years_experience: float = 0.0, verified: bool = False,
    ) -> EmployeeSkill:
        skill = None
        if skill_id:
            skill = await db.get(Skill, skill_id)
            if skill is None or skill.organization_id != organization_id:
                raise ValueError("Invalid skill")
        elif name:
            result = await db.execute(
                select(Skill).where(
                    Skill.organization_id == organization_id,
                    func.lower(Skill.name) == name.strip().lower(),
                )
            )
            skill = result.scalar_one_or_none()
            if skill is None:
                skill = Skill(organization_id=organization_id, name=name.strip())
                db.add(skill)
                await db.flush()
        else:
            raise ValueError("skill_id or name required")

        existing = await db.execute(
            select(EmployeeSkill).where(
                EmployeeSkill.organization_id == organization_id,
                EmployeeSkill.employee_id == employee.id,
                EmployeeSkill.skill_id == skill.id,
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.level = level
            row.years_experience = years_experience
            row.verified = verified
            row.updated_at = utcnow()
        else:
            row = EmployeeSkill(
                organization_id=organization_id, employee_id=employee.id, skill_id=skill.id,
                level=level, years_experience=years_experience, verified=verified,
                updated_at=utcnow(),
            )
            db.add(row)
        await db.flush()
        self._add_timeline(db, employee, "skill", f"Skill added: {skill.name}",
                           f"Level {level} · {years_experience} yrs", {"skill": skill.name})
        await self._emit(db, employee, "skill.updated", None, None, {"skill": skill.name})
        return row

    async def remove_skill(
        self, db: AsyncSession, *, organization_id: str, employee: Employee, skill_id: str
    ) -> None:
        row = await db.execute(
            select(EmployeeSkill).where(
                EmployeeSkill.organization_id == organization_id,
                EmployeeSkill.employee_id == employee.id,
                EmployeeSkill.skill_id == skill_id,
            )
        )
        entry = row.scalar_one_or_none()
        if entry:
            await db.delete(entry)
            await db.flush()

    async def add_certification(
        self, db: AsyncSession, *, organization_id: str, employee: Employee, data: dict[str, Any]
    ) -> EmployeeCertification:
        cert = EmployeeCertification(organization_id=organization_id, employee_id=employee.id, **data)
        db.add(cert)
        await db.flush()
        self._add_timeline(db, employee, "certification", f"Certified: {cert.name}",
                           cert.issuer, {"certification": cert.name})
        await self._emit(db, employee, "employee.certification.added", None, None,
                         {"certification": cert.name})
        return cert

    async def remove_certification(
        self, db: AsyncSession, *, organization_id: str, employee: Employee, cert_id: str
    ) -> None:
        cert = await db.get(EmployeeCertification, cert_id)
        if cert and cert.organization_id == organization_id and cert.employee_id == employee.id:
            await db.delete(cert)
            await db.flush()

    async def add_achievement(
        self, db: AsyncSession, *, organization_id: str, employee: Employee, data: dict[str, Any]
    ) -> EmployeeAchievement:
        achievement = EmployeeAchievement(organization_id=organization_id, employee_id=employee.id, **data)
        db.add(achievement)
        await db.flush()
        self._add_timeline(db, employee, "achievement", f"Achievement: {achievement.title}",
                           achievement.description, {"kind": achievement.kind})
        await self._emit(db, employee, "employee.achievement.added", None, None,
                         {"title": achievement.title, "kind": achievement.kind})
        return achievement

    async def remove_achievement(
        self, db: AsyncSession, *, organization_id: str, employee: Employee, achievement_id: str
    ) -> None:
        achievement = await db.get(EmployeeAchievement, achievement_id)
        if achievement and achievement.organization_id == organization_id and achievement.employee_id == employee.id:
            await db.delete(achievement)
            await db.flush()

    # ------------------------------------------------------------------ favorites

    async def add_favorite(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, target_employee_id: str
    ) -> None:
        existing = await db.execute(
            select(EmployeeFavorite).where(
                EmployeeFavorite.organization_id == organization_id,
                EmployeeFavorite.employee_id == employee_id,
                EmployeeFavorite.target_employee_id == target_employee_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                EmployeeFavorite(
                    organization_id=organization_id,
                    employee_id=employee_id,
                    target_employee_id=target_employee_id,
                )
            )
            await db.flush()

    async def remove_favorite(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, target_employee_id: str
    ) -> None:
        result = await db.execute(
            select(EmployeeFavorite).where(
                EmployeeFavorite.organization_id == organization_id,
                EmployeeFavorite.employee_id == employee_id,
                EmployeeFavorite.target_employee_id == target_employee_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await db.delete(row)
            await db.flush()

    async def favorite_ids(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> set[str]:
        result = await db.execute(
            select(EmployeeFavorite.target_employee_id).where(
                EmployeeFavorite.organization_id == organization_id,
                EmployeeFavorite.employee_id == employee_id,
            )
        )
        return set(result.scalars().all())

    async def favorites(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[Employee]:
        result = await db.execute(
            select(Employee)
            .join(EmployeeFavorite, EmployeeFavorite.target_employee_id == Employee.id)
            .where(
                EmployeeFavorite.organization_id == organization_id,
                EmployeeFavorite.employee_id == employee_id,
            )
        )
        employees = list(result.scalars().all())
        await self._hydrate(db, organization_id, employees, employee_id)
        return employees

    async def direct_reports(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[Employee]:
        result = await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id,
                Employee.manager_id == employee_id,
                Employee.status.in_(ACTIVE_STATUSES),
            )
        )
        employees = list(result.scalars().all())
        await self._hydrate(db, organization_id, employees)
        return employees

    async def reports_count(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> int:
        return (
            await db.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.manager_id == employee_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one()

    async def colleagues(
        self, db: AsyncSession, *, organization_id: str, employee: Employee
    ) -> list[Employee]:
        filters = [
            Employee.organization_id == organization_id,
            Employee.id != employee.id,
            Employee.status.in_(ACTIVE_STATUSES),
        ]
        if employee.team_id:
            filters.append(Employee.team_id == employee.team_id)
        elif employee.department_id:
            filters.append(Employee.department_id == employee.department_id)
        else:
            return []
        result = await db.execute(select(Employee).where(*filters).limit(20))
        employees = list(result.scalars().all())
        await self._hydrate(db, organization_id, employees)
        return employees

    # ------------------------------------------------------------------ hydration

    async def _hydrate(
        self,
        db: AsyncSession,
        organization_id: str,
        employees: list[Employee],
        viewer_employee_id: Optional[str] = None,
    ) -> None:
        if not employees:
            return
        ids = [e.id for e in employees]

        depts = await db.execute(
            select(Employee.department_id, func.count())
            .where(Employee.organization_id == organization_id, Employee.department_id.isnot(None))
            .group_by(Employee.department_id)
        )
        _dept_counts = dict(depts.all())

        from app.models.department import BusinessUnit, Department, Location
        from app.models.team import Team

        dep_map = {d.id: d for d in (await db.execute(select(Department).where(Department.organization_id == organization_id))).scalars().all()}
        team_map = {t.id: t for t in (await db.execute(select(Team).where(Team.organization_id == organization_id))).scalars().all()}
        loc_map = {l.id: l for l in (await db.execute(select(Location).where(Location.organization_id == organization_id))).scalars().all()}
        bu_map = {b.id: b for b in (await db.execute(select(BusinessUnit).where(BusinessUnit.organization_id == organization_id))).scalars().all()}

        avail_map = {
            a.employee_id: a
            for a in (
                await db.execute(
                    select(EmployeeAvailability).where(
                        EmployeeAvailability.organization_id == organization_id,
                        EmployeeAvailability.employee_id.in_(ids),
                    )
                )
            ).scalars().all()
        }
        pres_map = {
            p.employee_id: p
            for p in (
                await db.execute(
                    select(EmployeePresence).where(
                        EmployeePresence.organization_id == organization_id,
                        EmployeePresence.employee_id.in_(ids),
                    )
                )
            ).scalars().all()
        }
        skill_rows = (
            await db.execute(
                select(EmployeeSkill, Skill.name, Skill.category)
                .join(Skill, Skill.id == EmployeeSkill.skill_id)
                .where(
                    EmployeeSkill.organization_id == organization_id,
                    EmployeeSkill.employee_id.in_(ids),
                )
                .order_by(EmployeeSkill.level.desc(), EmployeeSkill.years_experience.desc())
            )
        ).all()
        skills_by_emp: dict[str, list] = {}
        for row in skill_rows:
            skills_by_emp.setdefault(row[0].employee_id, []).append(row)

        certs = (
            await db.execute(
                select(EmployeeCertification)
                .where(
                    EmployeeCertification.organization_id == organization_id,
                    EmployeeCertification.employee_id.in_(ids),
                )
                .order_by(EmployeeCertification.issue_date.desc())
            )
        ).scalars().all()
        certs_by_emp: dict[str, list] = {}
        for c in certs:
            certs_by_emp.setdefault(c.employee_id, []).append(c)

        achis = (
            await db.execute(
                select(EmployeeAchievement)
                .where(
                    EmployeeAchievement.organization_id == organization_id,
                    EmployeeAchievement.employee_id.in_(ids),
                )
                .order_by(EmployeeAchievement.achieved_on.desc())
            )
        ).scalars().all()
        achis_by_emp: dict[str, list] = {}
        for a in achis:
            achis_by_emp.setdefault(a.employee_id, []).append(a)

        manager_names: dict[str, str] = {}
        manager_ids = {e.manager_id for e in employees if e.manager_id}
        if manager_ids:
            mrows = await db.execute(select(Employee.id, Employee.first_name, Employee.last_name, Employee.display_name).where(Employee.id.in_(manager_ids)))
            for mid, first, last, display in mrows.all():
                manager_names[mid] = display or f"{first} {last}".strip()

        fav_set = set()
        if viewer_employee_id:
            fav_set = await self.favorite_ids(db, organization_id=organization_id, employee_id=viewer_employee_id)

        for emp in employees:
            dep = dep_map.get(emp.department_id)
            team = team_map.get(emp.team_id)
            loc = loc_map.get(emp.location_id)
            bu = bu_map.get(emp.business_unit_id)
            avail = avail_map.get(emp.id)
            pres = pres_map.get(emp.id)
            emp.department_name = dep.name if dep else None
            emp.team_name = team.name if team else None
            emp.location_name = loc.name if loc else None
            emp.business_unit_name = bu.name if bu else None
            emp.manager_name = manager_names.get(emp.manager_id)
            emp.availability_status = avail.status if avail else None
            emp.presence_status = pres.status if pres else None
            emp.is_online = bool(pres and pres.is_online)
            emp.top_skills = [row[1] for row in skills_by_emp.get(emp.id, [])[:4]]
            emp._skill_rows = skills_by_emp.get(emp.id, [])
            emp._availability = avail
            emp._presence = pres
            emp.is_favorite = emp.id in fav_set
            emp._certifications = certs_by_emp.get(emp.id, [])
            emp._achievements = achis_by_emp.get(emp.id, [])
            emp.reports_count = await self.reports_count(db, organization_id=organization_id, employee_id=emp.id)
            emp.timeline_count = (
                await db.execute(
                    select(func.count()).select_from(EmployeeTimeline).where(
                        EmployeeTimeline.organization_id == organization_id,
                        EmployeeTimeline.employee_id == emp.id,
                    )
                )
            ).scalar_one()
            emp.profile_completion = self.compute_profile_completion(emp)

    @staticmethod
    def compute_profile_completion(employee: Employee) -> int:
        if hasattr(employee, "_profile_completion"):
            return employee._profile_completion
        score = 0
        total = 0
        for field in ("first_name", "email", "designation", "department_id", "team_id",
                      "manager_id", "location_id", "employment_type", "joining_date",
                      "bio", "phone", "timezone"):
            total += 1
            if getattr(employee, field):
                score += 1
        if hasattr(employee, "_skill_rows") and len(employee._skill_rows) >= 2:
            score += 1
            total += 1
        completion = int(round(score / total * 100)) if total else 0
        employee._profile_completion = completion
        return completion


employee_service = EmployeeService()
