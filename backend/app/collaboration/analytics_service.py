"""Meeting Analytics (Phase 6.14) — organization-level collaboration metrics:
meeting load, time spent, participation, quality, knowledge generated, and
cross-team collaboration."""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.captions_service import transcript_service
from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import (
    MeetingAnalytics,
    MeetingDecision,
    MeetingNote,
    MeetingRecording,
    MeetingSession,
)
from app.models.meeting import Meeting, MeetingActionItem, MeetingAttendee


class MeetingAnalyticsService:
    async def overview(
        self, db: AsyncSession, *, organization_id: str, days: int = 30
    ) -> dict[str, Any]:
        cutoff = utcnow() - timedelta(days=days)
        meetings = (
            await db.execute(
                select(Meeting)
                .where(
                    Meeting.organization_id == organization_id,
                    (Meeting.created_at.is_(None)) | (Meeting.created_at >= cutoff),
                )
                .order_by(Meeting.created_at.asc())
            )
        ).scalars().all()

        sessions = (
            await db.execute(
                select(MeetingSession).where(
                    MeetingSession.organization_id == organization_id,
                    (MeetingSession.started_at.is_(None)) | (MeetingSession.started_at >= cutoff),
                )
            )
        ).scalars().all()
        analytics = (
            await db.execute(
                select(MeetingAnalytics).where(
                    MeetingAnalytics.organization_id == organization_id,
                    MeetingAnalytics.created_at >= cutoff,
                )
            )
        ).scalars().all()

        total_seconds = sum(s.duration_seconds for s in sessions if s.duration_seconds)
        avg_engagement = (
            sum(a.engagement_score for a in analytics) // len(analytics)
            if analytics else 0
        )
        decisions = (
            await db.execute(
                select(func.count(MeetingDecision.id)).where(
                    MeetingDecision.organization_id == organization_id,
                    MeetingDecision.created_at >= cutoff,
                )
            )
        ).scalar_one()
        notes = (
            await db.execute(
                select(func.count(MeetingNote.id)).where(
                    MeetingNote.organization_id == organization_id,
                    MeetingNote.created_at >= cutoff,
                )
            )
        ).scalar_one()
        recordings = (
            await db.execute(
                select(func.count(MeetingRecording.id)).where(
                    MeetingRecording.organization_id == organization_id,
                    MeetingRecording.created_at >= cutoff,
                )
            )
        ).scalar_one()
        action_items = (
            await db.execute(
                select(func.count(MeetingActionItem.id)).where(
                    MeetingActionItem.organization_id == organization_id,
                    MeetingActionItem.created_at >= cutoff,
                )
            )
        ).scalar_one()
        action_completed = (
            await db.execute(
                select(func.count(MeetingActionItem.id)).where(
                    MeetingActionItem.organization_id == organization_id,
                    MeetingActionItem.created_at >= cutoff,
                    MeetingActionItem.completed_at.isnot(None),
                )
            )
        ).scalar_one()

        # Cross-team collaboration: unique department pairs in shared meetings.
        attendee_rows = (
            await db.execute(
                select(MeetingAttendee.meeting_id, MeetingAttendee.employee_id)
                .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
                .where(
                    Meeting.organization_id == organization_id,
                    Meeting.created_at >= cutoff,
                )
            )
        ).all()
        from app.models.employee import Employee

        meeting_employees: dict[str, set[str]] = {}
        for meeting_id, employee_id in attendee_rows:
            meeting_employees.setdefault(meeting_id, set()).add(employee_id)
        employee_ids = {e for ids in meeting_employees.values() for e in ids}
        dept_by_employee: dict[str, str] = {}
        for emp_id in employee_ids:
            emp = await db.get(Employee, emp_id)
            if emp and emp.department_id:
                dept_by_employee[emp_id] = emp.department_id
        dept_pairs: set[tuple[str, str]] = set()
        for ids in meeting_employees.values():
            depts = sorted({dept_by_employee[e] for e in ids if e in dept_by_employee})
            for i in range(len(depts)):
                for j in range(i + 1, len(depts)):
                    dept_pairs.add((depts[i], depts[j]))

        per_week: dict[str, int] = {}
        for meeting in meetings:
            if meeting.created_at is None:
                continue
            week = ensure_aware(meeting.created_at).strftime("%Y-W%W")
            per_week[week] = per_week.get(week, 0) + 1

        return {
            "period_days": days,
            "meetings_total": len(meetings),
            "meetings_completed": sum(1 for m in meetings if m.status == "completed"),
            "meetings_cancelled": sum(1 for m in meetings if m.status == "cancelled"),
            "time_in_meetings_hours": round(total_seconds / 3600, 1),
            "avg_duration_minutes": round(total_seconds / 60 / len(sessions), 1) if sessions else 0,
            "avg_engagement_score": avg_engagement,
            "action_items": action_items,
            "action_items_completed": action_completed,
            "action_completion_rate": int(round(100 * action_completed / action_items)) if action_items else 0,
            "decisions": decisions,
            "notes": notes,
            "recordings": recordings,
            "cross_team_pairs": len(dept_pairs),
            "meetings_per_week": per_week,
            "recent": [
                {
                    "id": m.id,
                    "title": m.title,
                    "status": m.status,
                    "created_at": m.created_at,
                }
                for m in meetings[-10:]
            ],
        }

    async def for_session(
        self, db: AsyncSession, *, organization_id: str, meeting_id: str
    ) -> Optional[MeetingAnalytics]:
        return (
            await db.execute(
                select(MeetingAnalytics)
                .where(
                    MeetingAnalytics.organization_id == organization_id,
                    MeetingAnalytics.meeting_id == meeting_id,
                )
                .order_by(MeetingAnalytics.created_at.desc())
            )
        ).scalars().first()


meeting_analytics_service = MeetingAnalyticsService()
