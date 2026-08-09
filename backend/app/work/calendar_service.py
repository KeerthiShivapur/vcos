"""Calendar service â€” the organization's time system (Phase 3)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.calendar import CalendarEvent
from app.models.employee import Employee


class CalendarService:
    async def create(
        self, db, *, organization_id: str, data: dict[str, Any], created_by: Optional[str] = None,
    ) -> CalendarEvent:
        event = CalendarEvent(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            event_type=data.get("event_type", "event"),
            start_at=data.get("start_at"),
            end_at=data.get("end_at"),
            all_day=data.get("all_day", False),
            location=data.get("location"),
            calendar_scope=data.get("calendar_scope", "personal"),
            department_id=data.get("department_id"),
            team_id=data.get("team_id"),
            project_id=data.get("project_id"),
            milestone_id=data.get("milestone_id"),
            created_by=created_by,
            attendee_ids=data.get("attendee_ids"),
            status=data.get("status", "confirmed"),
        )
        db.add(event)
        await db.flush()
        return event

    async def get(self, db, *, organization_id: str, event_id: str) -> Optional[CalendarEvent]:
        return (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.organization_id == organization_id, CalendarEvent.id == event_id
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self, db, *, organization_id: str, employee_id: Optional[str] = None,
        start: Optional[datetime] = None, end: Optional[datetime] = None,
        scope: Optional[str] = None, project_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> list[CalendarEvent]:
        conditions = [CalendarEvent.organization_id == organization_id, CalendarEvent.status != "cancelled"]
        if start:
            conditions.append(CalendarEvent.end_at >= start)
        if end:
            conditions.append(CalendarEvent.start_at <= end)
        if scope:
            conditions.append(CalendarEvent.calendar_scope == scope)
        if project_id:
            conditions.append(CalendarEvent.project_id == project_id)
        if team_id:
            conditions.append(CalendarEvent.team_id == team_id)
        if employee_id:
            conditions.append(
                or_(
                    CalendarEvent.created_by == employee_id,
                    CalendarEvent.attendee_ids.contains([employee_id]),
                )
            )
        rows = await db.execute(
            select(CalendarEvent).where(and_(*conditions)).order_by(CalendarEvent.start_at.asc())
        )
        events = list(rows.scalars().all())
        owner_ids = {e.created_by for e in events if e.created_by}
        owners = {}
        if owner_ids:
            owners = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(owner_ids)))).scalars().all()}
        for event in events:
            event.creator_name = owners[event.created_by].full_name if event.created_by and owners.get(event.created_by) else None
        return events

    async def feed(
        self, db, *, organization_id: str, start: Optional[datetime] = None,
        end: Optional[datetime] = None, employee_id: Optional[str] = None,
    ) -> list[dict]:
        """The company calendar: events + meetings + task deadlines + leave.

        One merged, time-sorted feed so the calendar UI is a single call.
        """
        from app.models.meeting import Meeting, MeetingAttendee
        from app.models.task import Task
        from app.hr.leave_service import leave_service

        items: list[dict] = []

        events = await self.list_all(
            db, organization_id=organization_id, employee_id=employee_id, start=start, end=end
        )
        for event in events:
            items.append(
                {
                    "id": event.id,
                    "source": "event",
                    "title": event.title,
                    "start_at": event.start_at.isoformat() if event.start_at else None,
                    "end_at": event.end_at.isoformat() if event.end_at else None,
                    "all_day": event.all_day,
                    "status": event.status,
                    "event_type": event.event_type,
                }
            )

        meeting_conditions = [
            Meeting.organization_id == organization_id,
            Meeting.status.in_(("scheduled", "in_progress")),
        ]
        if start:
            meeting_conditions.append(Meeting.end_at >= start)
        if end:
            meeting_conditions.append(Meeting.start_at <= end)
        if employee_id:
            meeting_conditions.append(
                MeetingAttendee.employee_id == employee_id,
            )
        meeting_stmt = select(Meeting).join(MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id) if employee_id else select(Meeting)
        meetings = (
            await db.execute(meeting_stmt.where(*meeting_conditions).order_by(Meeting.start_at.asc()))
        ).scalars().all()
        for meeting in meetings:
            items.append(
                {
                    "id": meeting.id,
                    "source": "meeting",
                    "title": meeting.title,
                    "start_at": meeting.start_at.isoformat() if meeting.start_at else None,
                    "end_at": meeting.end_at.isoformat() if meeting.end_at else None,
                    "all_day": False,
                    "status": meeting.status,
                    "event_type": "meeting",
                }
            )

        if start or end:
            task_conditions = [
                Task.organization_id == organization_id,
                Task.status != "archived",
                Task.due_date.is_not(None),
            ]
            if start:
                task_conditions.append(Task.due_date >= start.date())
            if end:
                task_conditions.append(Task.due_date <= end.date())
            tasks = (
                await db.execute(select(Task).where(*task_conditions).order_by(Task.due_date.asc()))
            ).scalars().all()
            for task in tasks:
                items.append(
                    {
                        "id": task.id,
                        "source": "task",
                        "title": task.title,
                        "start_at": None,
                        "end_at": None,
                        "all_day": True,
                        "due_date": task.due_date.isoformat(),
                        "status": task.status,
                        "event_type": "deadline",
                    }
                )

        if start:
            start_date = start.date()
            end_date = (end or start).date()
            for entry in await leave_service.calendar(db, organization_id=organization_id, start=start_date, end=end_date):
                if entry["kind"] == "leave":
                    items.append(
                        {
                            "id": entry["id"],
                            "source": "leave",
                            "title": f"{entry['employee_name']} · {entry['leave_type_name'] or entry['leave_type']}",
                            "start_at": f"{entry['start_date']}T00:00:00",
                            "end_at": f"{entry['end_date']}T23:59:59",
                            "all_day": True,
                            "status": "approved",
                            "event_type": "leave",
                        }
                    )
                else:
                    items.append(
                        {
                            "id": f"holiday-{entry['holiday_id']}",
                            "source": "holiday",
                            "title": entry["name"],
                            "start_at": f"{entry['date']}T00:00:00",
                            "end_at": f"{entry['date']}T23:59:59",
                            "all_day": True,
                            "status": "confirmed",
                            "event_type": "holiday",
                        }
                    )

        def _sort_key(item: dict):
            return item.get("start_at") or item.get("due_date") or ""

        return sorted(items, key=_sort_key)

    async def update(self, db, *, event: CalendarEvent, data: dict[str, Any]) -> CalendarEvent:
        for key, value in data.items():
            if hasattr(event, key) and key not in ("id", "organization_id", "created_at"):
                setattr(event, key, value)
        event.updated_at = utcnow()
        return event

    async def delete(self, db, *, event: CalendarEvent):
        await db.delete(event)


calendar_service = CalendarService()

