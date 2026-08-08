"""Phase 7.9 — planning engine.

Builds daily/weekly plans from live data and persists them to ``ai_plans``:

  daily:   open tasks by due date, meetings, top 3 focus items
  weekly:  priority tasks, goals to advance, meetings to prepare for
  sprint:  (same data, longer window)

Plans are pure functions of the tenant's data, so they can be regenerated at
any time and stay accurate.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIPlan
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.meeting import Meeting, MeetingAttendee
from app.models.task import Task
from app.models.user import User


class PlanningEngine:
    async def plan(self, db: AsyncSession, *, organization_id: str, user: User, plan_type: str = "daily") -> dict[str, Any]:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            raise ValueError("no employee profile for planning")
        now = utcnow()
        today = now.date()
        tasks = (
            await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == employee.id,
                    Task.status.notin_(("completed", "archived")),
                )
                .order_by(Task.due_date.asc().nulls_last())
                .limit(20)
            )
        ).scalars().all()
        meetings = (
            await db.execute(
                select(Meeting)
                .join(MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id)
                .where(
                    Meeting.organization_id == organization_id,
                    MeetingAttendee.employee_id == employee.id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                )
                .order_by(Meeting.start_at.asc())
                .limit(10)
            )
        ).scalars().all()
        goals = (
            await db.execute(
                select(Goal).where(
                    Goal.organization_id == organization_id, Goal.owner_id == employee.id
                )
            )
        ).scalars().all()

        overdue = [t for t in tasks if t.due_date and t.due_date < today]
        open_tasks = [t for t in tasks if t.status != "completed"]
        window = 7 if plan_type == "weekly" else 1
        upcoming = [t for t in open_tasks if not t.due_date or t.due_date <= today + _days(window)]

        focus = [t.title for t in overdue[:2] + upcoming[:3]]
        plan = {
            "employee": employee.full_name,
            "plan_type": plan_type,
            "generated_at": now.isoformat(),
            "overdue": [t.title for t in overdue],
            "focus": focus,
            "tasks": [
                {
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "due": t.due_date.isoformat() if t.due_date else None,
                }
                for t in open_tasks[:8]
            ],
            "meetings": [
                {
                    "title": m.title,
                    "start": m.start_at.isoformat() if m.start_at else None,
                    "type": m.meeting_type,
                }
                for m in meetings
            ],
            "goals": [
                {"name": g.name, "progress": g.progress, "status": g.status} for g in goals
            ],
        }
        row = AIPlan(
            organization_id=organization_id,
            user_id=user.id,
            plan_type=plan_type,
            title=f"{plan_type.capitalize()} plan for {employee.full_name}",
            content_json=json.dumps(plan, default=str),
        )
        db.add(row)
        await db.flush()
        plan["id"] = row.id
        return plan

    async def latest(self, db: AsyncSession, *, organization_id: str, user: User, plan_type: str = "daily") -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(AIPlan)
                .where(
                    AIPlan.organization_id == organization_id,
                    AIPlan.user_id == user.id,
                    AIPlan.plan_type == plan_type,
                )
                .order_by(AIPlan.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "plan_type": row.plan_type,
            "title": row.title,
            "content": json.loads(row.content_json) if row.content_json else {},
            "created_at": row.created_at,
        }


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


planning_engine = PlanningEngine()
