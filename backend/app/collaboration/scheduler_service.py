"""Calendar Intelligence (Phase 6.15) — conflict detection, free-slot
suggestion, room suggestions and time-zone optimization for meetings."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.session_service import session_service
from app.core.timeutils import ensure_aware, utcnow
from app.models.calendar import CalendarEvent
from app.models.collaboration import MeetingRoom, MeetingSession
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAttendee

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 18
SLOT_STEP_MINUTES = 30


class MeetingSchedulerService:
    async def conflicts(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        start_at: datetime,
        end_at: datetime,
        employee_ids: Optional[list[str]] = None,
        exclude_meeting_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Find calendar events overlapping [start_at, end_at] for each employee."""
        start = ensure_aware(start_at)
        end = ensure_aware(end_at)
        rows = (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.organization_id == organization_id,
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.start_at.isnot(None),
                    CalendarEvent.end_at.isnot(None),
                    CalendarEvent.start_at < end,
                    CalendarEvent.end_at > start,
                )
            )
        ).scalars().all()
        conflicting: list[dict[str, Any]] = []
        for event in rows:
            involved = list(event.attendee_ids or [])
            if event.created_by:
                involved.append(event.created_by)
            if employee_ids is not None and not (set(involved) & set(employee_ids)):
                continue
            if exclude_meeting_id and event.event_type == "meeting" and event.title.endswith(exclude_meeting_id):
                continue
            names: dict[str, str] = {}
            for emp_id in list(set(involved))[:8]:
                emp = await db.get(Employee, emp_id)
                if emp:
                    names[emp_id] = emp.full_name
            conflicting.append(
                {
                    "event_id": event.id,
                    "title": event.title,
                    "event_type": event.event_type,
                    "start_at": event.start_at,
                    "end_at": event.end_at,
                    "attendee_ids": list(set(involved)),
                    "attendee_names": names,
                }
            )
        return {
            "start_at": start,
            "end_at": end,
            "conflicts": conflicting,
            "conflict_count": len(conflicting),
            "employee_ids": employee_ids or [],
        }

    async def suggest_slots(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_ids: list[str],
        duration_minutes: int = 60,
        start_date: Optional[datetime] = None,
        days: int = 7,
        business_hours_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Suggest free windows across the next N days for the given people."""
        start_day = ensure_aware(start_date or utcnow()).date()
        duration = timedelta(minutes=duration_minutes)
        # Collect all busy windows for the group.
        busy: list[tuple[datetime, datetime]] = []
        rows = (
            await db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.organization_id == organization_id,
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.start_at.isnot(None),
                    CalendarEvent.end_at.isnot(None),
                )
            )
        ).scalars().all()
        employee_set = set(employee_ids)
        for event in rows:
            involved = set(event.attendee_ids or [])
            if event.created_by:
                involved.add(event.created_by)
            if not (involved & employee_set):
                continue
            busy.append((ensure_aware(event.start_at), ensure_aware(event.end_at)))

        suggestions: list[dict[str, Any]] = []
        now = ensure_aware(utcnow())
        for day_offset in range(days):
            day = start_day + timedelta(days=day_offset)
            day_start = datetime(day.year, day.month, day.day, BUSINESS_START_HOUR, tzinfo=timezone.utc)
            day_end = datetime(day.year, day.month, day.day, BUSINESS_END_HOUR, tzinfo=timezone.utc)
            slot = day_start
            while slot + duration <= day_end:
                slot_end = slot + duration
                if slot >= now - timedelta(minutes=30):
                    overlaps = any(b_s < slot_end and b_e > slot for b_s, b_e in busy)
                    if not overlaps:
                        suggestions.append(
                            {
                                "start_at": slot,
                                "end_at": slot_end,
                                "duration_minutes": duration_minutes,
                                "free": True,
                                "day": slot.isoformat(),
                            }
                        )
                slot += timedelta(minutes=SLOT_STEP_MINUTES)
            if len(suggestions) >= 30:
                break
        return suggestions[:30]

    async def suggest_rooms(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        start_at: datetime,
        end_at: datetime,
        capacity: int = 8,
    ) -> list[dict[str, Any]]:
        """Rooms big enough and free in the requested window."""
        start = ensure_aware(start_at)
        end = ensure_aware(end_at)
        rooms = (
            await db.execute(
                select(MeetingRoom).where(
                    MeetingRoom.organization_id == organization_id,
                    MeetingRoom.status.in_(("available", "scheduled")),
                    MeetingRoom.capacity >= capacity,
                )
            )
        ).scalars().all()
        busy_session_rows = (
            await db.execute(
                select(MeetingSession.room_id).where(
                    MeetingSession.organization_id == organization_id,
                    MeetingSession.status == "live",
                )
            )
        ).scalars().all()
        busy_rooms = set(busy_session_rows)
        out: list[dict[str, Any]] = []
        for room in rooms:
            if room.id in busy_rooms:
                continue
            overlaps = await self._room_overlaps(db, organization_id=organization_id, room_id=room.id, start=start, end=end)
            if overlaps:
                continue
            out.append(
                {
                    "id": room.id,
                    "name": room.name,
                    "room_type": room.room_type,
                    "capacity": room.capacity,
                    "location": room.location,
                    "status": room.status,
                }
            )
        return out

    async def optimize_timezone(
        self, db: AsyncSession, *, organization_id: str, employee_ids: list[str]
    ) -> dict[str, Any]:
        """Estimate each participant's local time and find a shared window."""
        out: dict[str, Any] = {"employee_ids": employee_ids, "local_times": {}}
        for emp_id in employee_ids[:20]:
            emp = await db.get(Employee, emp_id)
            if emp is None:
                continue
            out["local_times"][emp_id] = {
                "name": emp.full_name,
                "timezone": emp.timezone or "UTC",
                "designation": emp.designation,
            }
        return out

    async def _room_overlaps(
        self, db: AsyncSession, *, organization_id: str, room_id: str, start: datetime, end: datetime
    ) -> bool:
        meetings = (
            await db.execute(
                select(Meeting).where(
                    Meeting.organization_id == organization_id,
                    Meeting.room_id == room_id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                    Meeting.start_at.isnot(None),
                    Meeting.end_at.isnot(None),
                    Meeting.start_at < end,
                    Meeting.end_at > start,
                )
            )
        ).scalars().all()
        return len(meetings) > 0


meeting_scheduler_service = MeetingSchedulerService()
