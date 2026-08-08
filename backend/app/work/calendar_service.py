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

    async def update(self, db, *, event: CalendarEvent, data: dict[str, Any]) -> CalendarEvent:
        for key, value in data.items():
            if hasattr(event, key) and key not in ("id", "organization_id", "created_at"):
                setattr(event, key, value)
        event.updated_at = utcnow()
        return event

    async def delete(self, db, *, event: CalendarEvent):
        await db.delete(event)


calendar_service = CalendarService()

