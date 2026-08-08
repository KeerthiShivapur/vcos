"""Meeting service â€” first-class meeting workspaces (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingActionItem, MeetingAgendaItem, MeetingAttendee


class MeetingService:
    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.goal import Goal
        from app.models.project import Project

        model = {"organizer_id": Employee, "project_id": Project, "goal_id": Goal}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def create(
        self, db, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Meeting:
        for key in ("organizer_id", "project_id", "goal_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        meeting = Meeting(
            organization_id=organization_id,
            title=data["title"],
            description=data.get("description"),
            meeting_type=data.get("meeting_type", "team"),
            status=data.get("status", "scheduled"),
            organizer_id=data.get("organizer_id") or (actor.id if actor else None),
            project_id=data.get("project_id"),
            goal_id=data.get("goal_id"),
            start_at=data.get("start_at"),
            end_at=data.get("end_at"),
            location=data.get("location"),
            meeting_link=data.get("meeting_link"),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(meeting)
        await db.flush()
        for idx, item in enumerate(data.get("agenda", []) or []):
            db.add(
                MeetingAgendaItem(
                    organization_id=organization_id,
                    meeting_id=meeting.id,
                    title=item.get("title", f"Agenda {idx + 1}"),
                    description=item.get("description"),
                    sort_order=idx,
                    duration_minutes=item.get("duration_minutes"),
                )
            )
        for attendee_id in data.get("attendee_ids", []) or []:
            db.add(
                MeetingAttendee(
                    organization_id=organization_id,
                    meeting_id=meeting.id,
                    employee_id=attendee_id,
                    role="participant",
                )
            )
        await db.flush()
        await self._emit(db, "meeting.created", organization_id, actor, ip_address, meeting)
        await self._alert_invites(db, organization_id, meeting, actor)
        return meeting

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], meeting: Meeting):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"meeting_id": meeting.id, "title": meeting.title, "project_id": meeting.project_id},
        )

    async def _alert_invites(self, db, organization_id: str, meeting: Meeting, actor: Optional[Employee]):
        from app.services.work_alerts import notify_employees

        attendee_ids = list(
            (
                await db.execute(
                    select(MeetingAttendee.employee_id).where(
                        MeetingAttendee.organization_id == organization_id,
                        MeetingAttendee.meeting_id == meeting.id,
                    )
                )
            ).scalars().all()
        )
        await notify_employees(
            db,
            organization_id=organization_id,
            employee_ids=attendee_ids,
            type="meeting.invited",
            title=f"You're invited: {meeting.title}",
            body=f"{meeting.meeting_type} meeting · {meeting.start_at.isoformat() if meeting.start_at else 'TBD'}",
            actor_id=actor.user_id if actor else None,
            entity_type="meeting",
            entity_id=meeting.id,
            link=f"/meetings/{meeting.id}",
            exclude_ids={actor.id} if actor else None,
        )

    async def get(self, db, *, organization_id: str, meeting_id: str) -> Optional[Meeting]:
        meeting = (
            await db.execute(
                select(Meeting).where(Meeting.organization_id == organization_id, Meeting.id == meeting_id)
            )
        ).scalar_one_or_none()
        if meeting:
            meeting.agenda = await self.agenda(db, organization_id=organization_id, meeting_id=meeting.id)
            meeting.attendees = await self.attendees(db, organization_id=organization_id, meeting_id=meeting.id)
            meeting.action_items = await self.action_items(db, organization_id=organization_id, meeting_id=meeting.id)
            if meeting.organizer_id:
                org = await db.get(Employee, meeting.organizer_id)
                meeting.organizer_name = org.full_name if org else None
        return meeting

    async def list_all(
        self, db, *, organization_id: str, project_id: Optional[str] = None,
        status: Optional[str] = None, from_date: Any = None, to_date: Any = None,
        employee_id: Optional[str] = None, limit: int = 200,
    ) -> list[Meeting]:
        stmt = select(Meeting).where(Meeting.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Meeting.project_id == project_id)
        if status:
            stmt = stmt.where(Meeting.status == status)
        if from_date:
            stmt = stmt.where(Meeting.start_at >= from_date)
        if to_date:
            stmt = stmt.where(Meeting.start_at < to_date)
        rows = await db.execute(stmt.order_by(Meeting.start_at.asc()).limit(limit))
        meetings = list(rows.scalars().all())
        for meeting in meetings:
            meeting.attendees = await self.attendees(db, organization_id=organization_id, meeting_id=meeting.id)
            if meeting.organizer_id:
                org = await db.get(Employee, meeting.organizer_id)
                meeting.organizer_name = org.full_name if org else None
        if employee_id:
            meetings = [m for m in meetings if any(a["employee_id"] == employee_id for a in m.attendees)]
        return meetings

    async def update(self, db, *, organization_id: str, meeting: Meeting, data: dict[str, Any]) -> Meeting:
        for key, value in data.items():
            if hasattr(meeting, key) and key not in ("id", "organization_id", "created_at"):
                setattr(meeting, key, value)
        meeting.updated_at = utcnow()
        return meeting

    async def attendee_rows(self, db, *, organization_id: str, meeting_id: str) -> list[MeetingAttendee]:
        rows = await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.organization_id == organization_id, MeetingAttendee.meeting_id == meeting_id
            )
        )
        return list(rows.scalars().all())

    async def attendees(self, db, *, organization_id: str, meeting_id: str) -> list[dict]:
        rows = await self.attendee_rows(db, organization_id=organization_id, meeting_id=meeting_id)
        out = []
        for attendee in rows:
            emp = await db.get(Employee, attendee.employee_id)
            out.append({
                "id": attendee.id,
                "employee_id": attendee.employee_id,
                "name": emp.full_name if emp else "Unknown",
                "designation": emp.designation if emp else None,
                "avatar_url": emp.avatar_url if emp else None,
                "role": attendee.role,
                "status": attendee.status,
                "rsvp_at": attendee.rsvp_at,
            })
        return out

    async def add_attendee(self, db, *, organization_id: str, meeting_id: str, employee_id: str, role: str = "participant") -> MeetingAttendee:
        emp = await db.get(Employee, employee_id)
        if emp is None or emp.organization_id != organization_id:
            raise ValueError("Invalid employee reference")
        exists = await self.attendee_rows(db, organization_id=organization_id, meeting_id=meeting_id)
        if any(a.employee_id == employee_id for a in exists):
            raise ValueError("Attendee already added")
        attendee = MeetingAttendee(
            organization_id=organization_id, meeting_id=meeting_id, employee_id=employee_id, role=role,
        )
        db.add(attendee)
        await db.flush()
        return attendee

    async def set_rsvp(self, db, *, organization_id: str, meeting_id: str, employee_id: str, status: str) -> MeetingAttendee:
        attendee = (
            await db.execute(
                select(MeetingAttendee).where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.meeting_id == meeting_id,
                    MeetingAttendee.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if attendee is None:
            attendee = MeetingAttendee(
                organization_id=organization_id, meeting_id=meeting_id, employee_id=employee_id,
            )
            db.add(attendee)
        attendee.status = status if status in ("accepted", "declined", "tentative") else "invited"
        attendee.rsvp_at = utcnow()
        await db.flush()
        return attendee

    async def remove_attendee(self, db, *, organization_id: str, meeting_id: str, employee_id: str):
        rows = await self.attendee_rows(db, organization_id=organization_id, meeting_id=meeting_id)
        for attendee in rows:
            if attendee.employee_id == employee_id:
                await db.delete(attendee)

    # ------------------------------------------------------------------ agenda

    async def agenda(self, db, *, organization_id: str, meeting_id: str) -> list[MeetingAgendaItem]:
        rows = await db.execute(
            select(MeetingAgendaItem)
            .where(MeetingAgendaItem.organization_id == organization_id, MeetingAgendaItem.meeting_id == meeting_id)
            .order_by(MeetingAgendaItem.sort_order.asc())
        )
        return list(rows.scalars().all())

    async def add_agenda_item(self, db, *, organization_id: str, meeting_id: str, data: dict[str, Any]) -> MeetingAgendaItem:
        item = MeetingAgendaItem(
            organization_id=organization_id,
            meeting_id=meeting_id,
            title=data["title"],
            description=data.get("description"),
            duration_minutes=data.get("duration_minutes"),
        )
        db.add(item)
        await db.flush()
        return item

    # ------------------------------------------------------------------ action items

    async def action_items(self, db, *, organization_id: str, meeting_id: str) -> list[MeetingActionItem]:
        rows = await db.execute(
            select(MeetingActionItem)
            .where(MeetingActionItem.organization_id == organization_id, MeetingActionItem.meeting_id == meeting_id)
            .order_by(MeetingActionItem.created_at.asc())
        )
        items = list(rows.scalars().all())
        for item in items:
            if item.assignee_id:
                emp = await db.get(Employee, item.assignee_id)
                item.assignee_name = emp.full_name if emp else None
        return items

    async def add_action_item(self, db, *, organization_id: str, meeting_id: str, data: dict[str, Any]) -> MeetingActionItem:
        item = MeetingActionItem(
            organization_id=organization_id,
            meeting_id=meeting_id,
            title=data["title"],
            assignee_id=data.get("assignee_id"),
            due_date=data.get("due_date"),
        )
        db.add(item)
        await db.flush()
        return item

    async def complete_action_item(self, db, *, organization_id: str, item: MeetingActionItem) -> MeetingActionItem:
        item.status = "completed"
        item.completed_at = utcnow()
        return item

    # ------------------------------------------------------------------ lifecycle

    async def complete(
        self, db, *, organization_id: str, meeting: Meeting,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Meeting:
        meeting.status = "completed"
        meeting.updated_at = utcnow()
        if meeting.ai_summary is None:
            meeting.ai_summary = self._build_summary(meeting)
        await db.flush()
        await self._emit(db, "meeting.ended", organization_id, actor, ip_address, meeting)
        return meeting

    def _build_summary(self, meeting: Meeting) -> str:
        titles = [a.title for a in meeting.agenda] if getattr(meeting, "agenda", None) else []
        attendees = getattr(meeting, "attendees", []) or []
        names = [a["name"] for a in attendees[:6]]
        parts = [f"{meeting.title} ({meeting.meeting_type})"]
        if names:
            parts.append(f"Attendees: {', '.join(names)}")
        if titles:
            parts.append(f"Agenda: {'; '.join(titles)}")
        return ". ".join(parts) + "."

    async def delete(self, db, *, meeting: Meeting):
        await db.delete(meeting)


meeting_service = MeetingService()

