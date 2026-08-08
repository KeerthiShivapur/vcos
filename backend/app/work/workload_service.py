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
        return len(employees)

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
