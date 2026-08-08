"""Phase 7.11 — background intelligence insights.

The periodic worker runs this over each organization and persists actionable
insights (delay, overload, meeting_load, knowledge_gap) to ``ai_insights``.
Each insight is a single sentence a human can act on, plus evidence.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIInsight
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAttendee
from app.models.task import Task
from app.models.workload import WorkloadSnapshot


class InsightEngine:
    async def scan_organization(self, db: AsyncSession, *, organization_id: str, limit: int = 12) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        insights.extend(await self._overloaded(db, organization_id))
        insights.extend(await self._meeting_load(db, organization_id))
        insights.extend(await self._overdue_wave(db, organization_id))
        insights.sort(key=lambda i: {"critical": 3, "warning": 2, "info": 1}[i["severity"]], reverse=True)
        await self._replace(db, organization_id, insights[:limit])
        return insights[:limit]

    async def _overloaded(self, db, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WorkloadSnapshot)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.is_overloaded == True,  # noqa: E712
                )
                .limit(8)
            )
        ).scalars().all()
        results = []
        for row in rows:
            employee = await db.get(Employee, row.employee_id)
            if employee is None:
                continue
            severity = "critical" if row.utilization >= 110 else "warning"
            results.append(
                {
                    "kind": "overload",
                    "title": f"{employee.full_name} is at {round(row.utilization)}% utilization",
                    "content": (
                        f"{round(row.utilization)}% utilization with {row.tasks_count} open task(s) "
                        f"and {round(row.meetings_hours)} meeting hours in the latest period."
                    ),
                    "severity": severity,
                    "evidence": {"employee_id": employee.id, "utilization": row.utilization},
                }
            )
        return results

    async def _meeting_load(self, db, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(MeetingAttendee.employee_id, func.count(MeetingAttendee.id).label("cnt"))
                .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
                .where(
                    Meeting.organization_id == organization_id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                )
                .group_by(MeetingAttendee.employee_id)
                .order_by(func.count(MeetingAttendee.id).desc())
                .limit(5)
            )
        ).all()
        results = []
        for employee_id, cnt in rows:
            if cnt < 10:
                continue
            employee = await db.get(Employee, employee_id)
            if employee is None:
                continue
            results.append(
                {
                    "kind": "meeting_load",
                    "title": f"{employee.full_name} has {cnt} upcoming meetings",
                    "content": "High meeting load reduces deep-work time; consider protecting focus blocks.",
                    "severity": "warning",
                    "evidence": {"employee_id": employee.id, "meeting_count": int(cnt)},
                }
            )
        return results

    async def _overdue_wave(self, db, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Task.assignee_id, func.count(Task.id).label("cnt"))
                .where(
                    Task.organization_id == organization_id,
                    Task.status.notin_(("completed", "archived")),
                    Task.due_date.is_not(None),
                )
                .group_by(Task.assignee_id)
                .order_by(func.count(Task.id).desc())
                .limit(5)
            )
        ).all()
        results = []
        for employee_id, cnt in rows:
            if employee_id is None or cnt < 3:
                continue
            employee = await db.get(Employee, employee_id)
            if employee is None:
                continue
            results.append(
                {
                    "kind": "delay",
                    "title": f"{employee.full_name} has {cnt} overdue tasks",
                    "content": "A cluster of overdue tasks can cascade into project delays.",
                    "severity": "warning",
                    "evidence": {"employee_id": employee_id, "overdue_count": int(cnt)},
                }
            )
        return results

    async def _replace(self, db, organization_id: str, insights: list[dict[str, Any]]) -> None:
        old = (
            await db.execute(
                select(AIInsight).where(
                    AIInsight.organization_id == organization_id, AIInsight.status == "open"
                )
            )
        ).scalars().all()
        for row in old:
            row.status = "resolved"
        for insight in insights:
            db.add(
                AIInsight(
                    organization_id=organization_id,
                    kind=insight["kind"],
                    title=insight["title"],
                    content=insight.get("content"),
                    severity=insight["severity"],
                    evidence_json=json.dumps(insight.get("evidence", {}), default=str),
                )
            )
        await db.flush()


insight_engine = InsightEngine()
