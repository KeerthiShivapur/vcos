"""Workload engine — capacity, utilization, overload detection (Phase 3)."""

from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.calendar import CalendarEvent
from app.models.employee import Employee
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

STANDARD_WEEK_HOURS = 40.0


class WorkloadService:
    async def compute_for_employee(
        self, db, *, organization_id: str, employee_id: str,
        period_start=None, period_end=None,
    ) -> dict:
        from app.models.meeting import MeetingAttendee

        now = utcnow()
        start = period_start or (now - timedelta(days=7))
        end = period_end or now
        tasks = (
            await db.execute(
                select(Task.estimate_hours, Task.status)
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == employee_id,
                    Task.status != "archived",
                )
            )
        ).all()
        active_tasks = [t for t in tasks if t[1] in ("todo", "in_progress", "review", "blocked")]
        allocated = sum((t[0] or 0) for t in active_tasks)
        meeting_hours = (
            await db.execute(
                select(func.coalesce(func.sum(func.extract("epoch", Meeting.end_at - Meeting.start_at) / 3600.0), 0.0))
                .select_from(MeetingAttendee)
                .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
                .where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.employee_id == employee_id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                    Meeting.start_at >= start,
                    Meeting.start_at < end,
                )
            )
        ).scalar() or 0.0
        capacity = STANDARD_WEEK_HOURS
        utilization = min(100.0, round(((allocated + meeting_hours) / capacity) * 100, 1)) if capacity else 0.0
        return {
            "employee_id": employee_id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "capacity_hours": capacity,
            "allocated_hours": round(allocated, 1),
            "meeting_hours": round(meeting_hours, 1),
            "utilization": utilization,
            "active_tasks": len(active_tasks),
            "is_overloaded": utilization > 90.0,
        }

    async def snapshot_week(self, db, *, organization_id: str) -> int:
        """Persist a weekly workload snapshot for every employee (worker)."""
        from datetime import datetime, timezone

        now = utcnow()
        start = now - timedelta(days=7)
        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status.in_(("active", "probation", "notice")),
                )
            )
        ).scalars().all()
        for emp in employees:
            data = await self.compute_for_employee(
                db, organization_id=organization_id, employee_id=emp.id, period_start=start, period_end=now
            )
            newly_overloaded = data["is_overloaded"] and not await self._was_overloaded(
                db, organization_id=organization_id, employee_id=emp.id
            )
            db.add(
                WorkloadSnapshot(
                    organization_id=organization_id,
                    employee_id=emp.id,
                    period_start=start,
                    period_end=now,
                    capacity_hours=data["capacity_hours"],
                    allocated_hours=data["allocated_hours"],
                    utilization=data["utilization"],
                    tasks_count=data["active_tasks"],
                    meetings_hours=data["meeting_hours"],
                    is_overloaded=data["is_overloaded"],
                    created_at=now,
                )
            )
            if newly_overloaded:
                await self._alert_overload(db, organization_id=organization_id, employee=emp, data=data)
        return len(employees)

    async def _was_overloaded(self, db, *, organization_id: str, employee_id: str) -> bool:
        row = (
            await db.execute(
                select(WorkloadSnapshot.is_overloaded)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.employee_id == employee_id,
                )
                .order_by(WorkloadSnapshot.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return bool(row)

    async def _alert_overload(self, db, *, organization_id: str, employee: Employee, data: dict) -> None:
        """Notify the employee the first time their load crosses the threshold."""
        from app.services.work_alerts import notify_employee
        from app.services.work_audit import record
        from app.services.event_service import event_service

        await event_service.emit(
            db, name="workload.overload", actor_id=None,
            organization_id=organization_id,
            payload={
                "employee_id": employee.id,
                "utilization": data["utilization"],
                "allocated_hours": data["allocated_hours"],
                "meeting_hours": data["meeting_hours"],
            },
        )
        await notify_employee(
            db,
            organization_id=organization_id,
            employee_id=employee.id,
            type="workload.overload",
            title="Your workload is over capacity",
            body=(
                f"Utilization is at {data['utilization']:.0f}% — "
                f"{data['allocated_hours']:.0f}h of allocated work plus "
                f"{data['meeting_hours']:.0f}h of meetings on a 40h week."
            ),
            priority="high",
            entity_type="employee",
            entity_id=employee.id,
            link="/my-work",
        )
        await record(
            db, organization_id=organization_id, action="workload.overload",
            actor=None, ip_address=None,
            resource_type="employee", resource_id=employee.id,
            details={"utilization": data["utilization"]},
        )

    async def team_load_summary(self, db, *, organization_id: str) -> list[dict]:
        """Per-team utilization: member count, average load, overloaded count."""
        from app.models.team import Team, TeamMember

        teams = (
            await db.execute(
                select(Team).where(Team.organization_id == organization_id).order_by(Team.name.asc())
            )
        ).scalars().all()
        out = []
        for team in teams:
            members = (
                await db.execute(
                    select(TeamMember.employee_id).where(
                        TeamMember.organization_id == organization_id, TeamMember.team_id == team.id
                    )
                )
            ).scalars().all()
            loads = []
            for employee_id in members:
                loads.append(await self.compute_for_employee(db, organization_id=organization_id, employee_id=employee_id))
            avg = round(sum(l["utilization"] for l in loads) / len(loads), 1) if loads else 0.0
            out.append(
                {
                    "team_id": team.id,
                    "team_name": team.name,
                    "member_count": len(loads),
                    "avg_utilization": avg,
                    "overloaded_count": sum(1 for l in loads if l["is_overloaded"]),
                    "overloaded_employees": [l["employee_id"] for l in loads if l["is_overloaded"]],
                }
            )
        return sorted(out, key=lambda t: t["avg_utilization"], reverse=True)

    async def team_load(self, db, *, organization_id: str, team_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Utilization across employees (optionally filtered by team)."""
        stmt = select(Employee).where(Employee.organization_id == organization_id)
        if team_id:
            from app.models.team import TeamMember

            member_ids = (
                await db.execute(
                    select(TeamMember.employee_id).where(
                        TeamMember.organization_id == organization_id, TeamMember.team_id == team_id
                    )
                )
            ).scalars().all()
            stmt = stmt.where(Employee.id.in_(member_ids))
        employees = (
            await db.execute(stmt.limit(limit))
        ).scalars().all()
        out = []
        for emp in employees:
            data = await self.compute_for_employee(db, organization_id=organization_id, employee_id=emp.id)
            data["name"] = emp.full_name
            data["designation"] = emp.designation
            out.append(data)
        return sorted(out, key=lambda x: x["utilization"], reverse=True)


workload_service = WorkloadService()
