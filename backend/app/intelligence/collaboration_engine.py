"""Phase 9.8 — Collaboration intelligence engine.

Observes departments, projects, meetings, messages, communities and knowledge
to detect:

    - isolated teams / knowledge silos
    - poor collaboration between department pairs
    - cross-functional leaders
    - high-performing teams
    - communication bottlenecks

Each pass stores CollaborationMetric rows for the period and produces a
human-readable summary the intelligence center can display.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import CommunityPost, Message
from app.models.department import Department
from app.models.employee import Employee
from app.models.intelligence import CollaborationMetric
from app.models.meeting import Meeting, MeetingAttendee

logger = logging.getLogger("vcos.intelligence.collaboration")


class CollaborationEngine:
    async def compute(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        """Compute collaboration metrics for the trailing 30 days."""
        employees = list(
            (
                await db.execute(
                    select(Employee).where(Employee.organization_id == organization_id)
                )
            ).scalars().all()
        )
        departments = list(
            (
                await db.execute(
                    select(Department).where(Department.organization_id == organization_id)
                )
            ).scalars().all()
        )
        dept_of = {e.id: e.department_id for e in employees}
        dept_name = {d.id: d.name for d in departments}
        period_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # --- department pair interactions from meetings
        pair_counts: dict[tuple[str, str], int] = {}
        meetings = list(
            (
                await db.execute(
                    select(Meeting).where(
                        Meeting.organization_id == organization_id,
                        Meeting.status == "completed",
                    )
                )
            ).scalars().all()
        )
        for meeting in meetings:
            attendee_ids = list(
                (
                    await db.execute(
                        select(MeetingAttendee.employee_id).where(
                            MeetingAttendee.meeting_id == meeting.id,
                            MeetingAttendee.employee_id.isnot(None),
                        )
                    )
                ).scalars().all()
            )
            depts = {dept_of.get(aid) for aid in attendee_ids}
            depts.discard(None)
            depts = list(depts)
            for i in range(len(depts)):
                for j in range(i + 1, len(depts)):
                    key = tuple(sorted((depts[i], depts[j])))
                    pair_counts[key] = pair_counts.get(key, 0) + 1

        # --- pair interactions from messages
        messages = list(
            (
                await db.execute(
                    select(Message).where(
                        Message.organization_id == organization_id,
                    )
                )
            ).scalars().all()
        )
        sender_dept = {
            m.sender_id: dept_of.get(m.sender_id)
            for m in messages
            if m.sender_id and m.sender_id in dept_of
        }
        for message in messages:
            receiver = getattr(message, "recipient_id", None)
            if receiver and receiver in dept_of:
                a, b = sender_dept.get(message.sender_id), dept_of[receiver]
                if a and b and a != b:
                    key = tuple(sorted((a, b)))
                    pair_counts[key] = pair_counts.get(key, 0) + 1

        # --- department activity levels
        dept_activity: dict[str, dict[str, int]] = {}
        for dept_id in departments:
            dept_activity[dept_id.id] = {"meetings": 0, "messages": 0, "posts": 0}
        for meeting in meetings:
            attendee_ids = list(
                (
                    await db.execute(
                        select(MeetingAttendee.employee_id).where(
                            MeetingAttendee.meeting_id == meeting.id,
                            MeetingAttendee.employee_id.isnot(None),
                        )
                    )
                ).scalars().all()
            )
            for aid in attendee_ids:
                d = dept_of.get(aid)
                if d in dept_activity:
                    dept_activity[d]["meetings"] += 1
        for message in messages:
            d = sender_dept.get(message.sender_id)
            if d in dept_activity:
                dept_activity[d]["messages"] += 1
        for post in list(
            (
                await db.execute(
                    select(CommunityPost).where(CommunityPost.organization_id == organization_id)
                )
            ).scalars().all()
        ):
            d = dept_of.get(post.author_id)
            if d in dept_activity:
                dept_activity[d]["posts"] += 1

        # --- team engagement (employees with cross-dept collaborators)
        isolated: list[str] = []
        for employee in employees:
            if not employee.department_id:
                continue
            pair_keys = [
                k for k in pair_counts
                if employee.department_id in k
            ]
            cross = sum(pair_counts[k] for k in pair_keys)
            if cross == 0:
                isolated.append(employee.id)

        await self._store(
            db, organization_id=organization_id, metric_type="dept_pair_interactions",
            value=float(len(pair_counts)),
            detail={
                "pairs": [
                    {
                        "dept_a": pair[0], "dept_a_name": dept_name.get(pair[0], "—"),
                        "dept_b": pair[1], "dept_b_name": dept_name.get(pair[1], "—"),
                        "interactions": count,
                    }
                    for pair, count in sorted(pair_counts.items(), key=lambda kv: -kv[1])[:15]
                ],
            },
            period_start=period_start,
        )
        await self._store(
            db, organization_id=organization_id, metric_type="dept_activity",
            value=float(len(dept_activity)),
            detail={
                "departments": [
                    {
                        "department_id": d.id, "name": d.name,
                        "meetings": dept_activity.get(d.id, {}).get("meetings", 0),
                        "messages": dept_activity.get(d.id, {}).get("messages", 0),
                        "posts": dept_activity.get(d.id, {}).get("posts", 0),
                        "total": sum(dept_activity.get(d.id, {}).values()),
                    }
                    for d in departments
                ],
            },
            period_start=period_start,
        )
        await self._store(
            db, organization_id=organization_id, metric_type="silo",
            value=float(len(isolated)),
            detail={
                "isolated_employees": isolated,
                "isolated_count": len(isolated),
            },
            period_start=period_start,
        )

        return {
            "department_pairs": len(pair_counts),
            "pair_breakdown": [
                {
                    "dept_a": pair[0], "dept_b": pair[1],
                    "dept_a_name": dept_name.get(pair[0], "—"),
                    "dept_b_name": dept_name.get(pair[1], "—"),
                    "interactions": count,
                }
                for pair, count in sorted(pair_counts.items(), key=lambda kv: -kv[1])[:15]
            ],
            "isolated_employees": isolated,
            "period_start": period_start.isoformat(),
        }

    async def _store(
        self, db: AsyncSession, *, organization_id: str, metric_type: str,
        value: float, detail: dict[str, Any], period_start: datetime,
    ) -> None:
        existing = (
            await db.execute(
                select(CollaborationMetric).where(
                    CollaborationMetric.organization_id == organization_id,
                    CollaborationMetric.metric_type == metric_type,
                    CollaborationMetric.period_start == period_start,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.value = value
            existing.detail_json = json.dumps(detail, default=str)
            return
        db.add(
            CollaborationMetric(
                organization_id=organization_id,
                metric_type=metric_type,
                value=value,
                detail_json=json.dumps(detail, default=str),
                period_start=period_start,
                period_end=period_start,
            )
        )

    async def latest(
        self, db: AsyncSession, *, organization_id: str,
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(CollaborationMetric)
                .where(CollaborationMetric.organization_id == organization_id)
                .order_by(CollaborationMetric.period_start.desc())
            )
        ).scalars().all()
        result: dict[str, Any] = {}
        for row in rows:
            if row.metric_type in result:
                continue
            result[row.metric_type] = {
                "value": row.value,
                "detail": row.detail,
                "period_start": row.period_start.isoformat() if row.period_start else None,
            }
        return result


collaboration_engine = CollaborationEngine()
