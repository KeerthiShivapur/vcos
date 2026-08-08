"""Team services — teams, cross-functional memberships, and goals (Phase 2)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.team import Team, TeamGoal, TeamMember
from app.services.audit_service import audit_service
from app.services.event_service import event_service

logger = logging.getLogger("vcos.people")


class TeamService:
    async def _check_unique(
        self, db: AsyncSession, organization_id: str, field: str, value: str, exclude_id: Optional[str] = None
    ) -> None:
        result = await db.execute(
            select(Team).where(
                Team.organization_id == organization_id,
                func.lower(getattr(Team, field)) == value.strip().lower(),
            )
        )
        row = result.scalar_one_or_none()
        if row is not None and row.id != exclude_id:
            raise ValueError(f"A team with this {field} already exists")

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Team:
        await self._check_unique(db, organization_id, "code", data["code"])
        await self._check_unique(db, organization_id, "name", data["name"])
        await self._validate_refs(db, organization_id, data)
        team = Team(organization_id=organization_id, **data)
        db.add(team)
        await db.flush()
        if team.lead_id:
            await self.add_member(
                db, organization_id=organization_id, team_id=team.id,
                employee_id=team.lead_id, role="Lead",
            )
        await event_service.emit(
            db, name="team.created", actor_id=actor.id if actor else None,
            organization_id=organization_id, payload={"team_id": team.id, "code": team.code},
        )
        await audit_service.log(
            db, organization_id=organization_id, action="team.created",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="team", resource_id=team.id, ip_address=ip_address,
        )
        return team

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        team: Team,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Team:
        if data.get("code"):
            await self._check_unique(db, organization_id, "code", data["code"], team.id)
        if data.get("name"):
            await self._check_unique(db, organization_id, "name", data["name"], team.id)
        await self._validate_refs(db, organization_id, data)
        for field, value in data.items():
            setattr(team, field, value)
        await db.flush()
        await event_service.emit(
            db, name="team.updated", actor_id=actor.id if actor else None,
            organization_id=organization_id, payload={"team_id": team.id, "fields": list(data.keys())},
        )
        await audit_service.log(
            db, organization_id=organization_id, action="team.updated",
            actor_id=actor.id if actor else None, actor_email=actor.email if actor else None,
            resource_type="team", resource_id=team.id, ip_address=ip_address,
            details={"fields": list(data.keys())},
        )
        return team

    async def list(self, db: AsyncSession, *, organization_id: str) -> list[Team]:
        result = await db.execute(
            select(Team).where(Team.organization_id == organization_id).order_by(Team.name.asc())
        )
        teams = list(result.scalars().all())
        await self._hydrate(db, organization_id, teams)
        return teams

    async def get(self, db: AsyncSession, *, organization_id: str, team_id: str) -> Optional[Team]:
        team = await db.get(Team, team_id)
        if team is None or team.organization_id != organization_id:
            return None
        await self._hydrate(db, organization_id, [team])
        return team

    async def _validate_refs(self, db: AsyncSession, organization_id: str, data: dict[str, Any]) -> None:
        from app.models.department import Department

        if data.get("department_id"):
            dep = await db.get(Department, data["department_id"])
            if dep is None or dep.organization_id != organization_id:
                raise ValueError("Invalid department reference")
        if data.get("lead_id"):
            lead = await db.get(Employee, data["lead_id"])
            if lead is None or lead.organization_id != organization_id:
                raise ValueError("Invalid lead reference")

    async def _hydrate(self, db: AsyncSession, organization_id: str, teams: list[Team]) -> None:
        if not teams:
            return
        ids = [t.id for t in teams]
        from app.models.department import Department

        dep_map = {
            d.id: d
            for d in (
                await db.execute(
                    select(Department).where(
                        Department.organization_id == organization_id,
                        Department.id.in_({t.department_id for t in teams if t.department_id}),
                    )
                )
            ).scalars().all()
        }
        leads: dict[str, str] = {}
        lead_ids = {t.lead_id for t in teams if t.lead_id}
        if lead_ids:
            rows = await db.execute(
                select(Employee.id, Employee.first_name, Employee.last_name, Employee.display_name)
                .where(Employee.organization_id == organization_id, Employee.id.in_(lead_ids))
            )
            for lid, first, last, display in rows.all():
                leads[lid] = display or f"{first} {last}".strip()

        primary_counts = dict(
            (
                await db.execute(
                    select(Employee.team_id, func.count())
                    .where(
                        Employee.organization_id == organization_id,
                        Employee.team_id.in_(ids),
                        Employee.status.in_(("active", "probation", "notice")),
                    )
                    .group_by(Employee.team_id)
                )
            ).all()
        )
        cross = (
            await db.execute(
                select(TeamMember)
                .where(
                    TeamMember.organization_id == organization_id, TeamMember.team_id.in_(ids)
                )
                .order_by(TeamMember.joined_at.asc())
            )
        ).scalars().all()
        member_rows = {t.id: [] for t in teams}
        for m in cross:
            member_rows[m.team_id].append(m)

        emp_map: dict[str, Employee] = {}
        emp_ids = {m.employee_id for members in member_rows.values() for m in members}
        if emp_ids:
            emp_map = {
                e.id: e
                for e in (
                    await db.execute(
                        select(Employee).where(Employee.id.in_(emp_ids))
                    )
                ).scalars().all()
            }

        for t in teams:
            t.department_name = dep_map.get(t.department_id).name if dep_map.get(t.department_id) else None
            t.lead_name = leads.get(t.lead_id)
            members = member_rows[t.id]
            t.members_count = primary_counts.get(t.id, 0) + len(members)
            t._member_rows = [
                {
                    "id": m.id,
                    "employee_id": m.employee_id,
                    "employee_name": emp_map[m.employee_id].full_name if m.employee_id in emp_map else "Unknown",
                    "designation": emp_map[m.employee_id].designation if m.employee_id in emp_map else None,
                    "avatar_url": emp_map[m.employee_id].avatar_url if m.employee_id in emp_map else None,
                    "role": m.role,
                    "joined_at": m.joined_at,
                    "is_primary": False,
                }
                for m in members
            ]

    # ------------------------------------------------------------------ members

    async def add_member(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        team_id: str,
        employee_id: str,
        role: Optional[str] = None,
    ) -> TeamMember:
        team = await db.get(Team, team_id)
        if team is None or team.organization_id != organization_id:
            raise ValueError("Team not found")
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            raise ValueError("Employee not found")
        if employee.team_id == team_id and team.department_id == employee.department_id:
            raise ValueError("Employee is already a primary member of this team")
        existing = (
            await db.execute(
                select(TeamMember).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team_id,
                    TeamMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if role:
                existing.role = role
                await db.flush()
            return existing
        member = TeamMember(
            organization_id=organization_id,
            team_id=team_id,
            employee_id=employee_id,
            role=role,
            joined_at=utcnow(),
        )
        db.add(member)
        await db.flush()
        await event_service.emit(
            db, name="team.member.added", organization_id=organization_id,
            payload={"team_id": team_id, "employee_id": employee_id},
        )
        await audit_service.log(
            db, organization_id=organization_id, action="team.member.added",
            resource_type="team", resource_id=team_id,
            details={"employee_id": employee_id, "role": role},
        )
        return member

    async def remove_member(
        self, db: AsyncSession, *, organization_id: str, team_id: str, employee_id: str
    ) -> None:
        member = (
            await db.execute(
                select(TeamMember).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team_id,
                    TeamMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if member:
            await db.delete(member)
            await db.flush()
            await event_service.emit(
                db, name="team.member.removed", organization_id=organization_id,
                payload={"team_id": team_id, "employee_id": employee_id},
            )
            await audit_service.log(
                db, organization_id=organization_id, action="team.member.removed",
                resource_type="team", resource_id=team_id,
                details={"employee_id": employee_id},
            )

    # ------------------------------------------------------------------ goals

    async def add_goal(
        self, db: AsyncSession, *, organization_id: str, team_id: str, title: str,
        status: str = "planned", meta: Optional[dict[str, Any]] = None,
    ) -> TeamGoal:
        team = await db.get(Team, team_id)
        if team is None or team.organization_id != organization_id:
            raise ValueError("Team not found")
        goal = TeamGoal(
            organization_id=organization_id, team_id=team_id,
            title=title, status=status, meta=meta, created_at=utcnow(),
        )
        db.add(goal)
        await db.flush()
        return goal

    async def update_goal(
        self, db: AsyncSession, *, organization_id: str, goal_id: str, **fields: Any
    ) -> TeamGoal:
        goal = await db.get(TeamGoal, goal_id)
        if goal is None or goal.organization_id != organization_id:
            raise ValueError("Goal not found")
        for field, value in fields.items():
            if value is not None:
                setattr(goal, field, value)
        await db.flush()
        return goal

    async def list_goals(
        self, db: AsyncSession, *, organization_id: str, team_id: Optional[str] = None
    ) -> list[TeamGoal]:
        filters = [TeamGoal.organization_id == organization_id]
        if team_id:
            filters.append(TeamGoal.team_id == team_id)
        result = await db.execute(
            select(TeamGoal).where(*filters).order_by(TeamGoal.created_at.desc())
        )
        return list(result.scalars().all())


team_service = TeamService()
