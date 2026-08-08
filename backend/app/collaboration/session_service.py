"""Meeting session service — join codes, live lifecycle, invites, calendar sync (Phase 6)."""

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.collab_base import (
    emit_and_audit,
    new_join_code,
    notify_employee_ids,
    parse_json,
    safe_json,
)
from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import MeetingNote, MeetingParticipant, MeetingRoom, MeetingSession
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAttendee


class SessionService:
    async def ensure(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        data: Optional[dict[str, Any]] = None,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> MeetingSession:
        """Get or create the session for a meeting; sets the join code on the meeting."""
        existing = await self.by_meeting(db, organization_id=organization_id, meeting_id=meeting.id)
        if existing:
            return existing
        data = data or {}
        code = data.get("meeting_code") or new_join_code()
        session = MeetingSession(
            organization_id=organization_id,
            meeting_id=meeting.id,
            room_id=data.get("room_id") or meeting.room_id,
            status="scheduled",
            meeting_code=code,
            timezone=data.get("timezone") or meeting.timezone or "UTC",
            max_participants=data.get("max_participants", 50),
            is_recording=data.get("is_recording", False),
            is_captions_enabled=data.get("is_captions_enabled", False),
            is_translation_enabled=data.get("is_translation_enabled", False),
            settings=safe_json(data.get("settings")),
        )
        db.add(session)
        await db.flush()
        if not meeting.meeting_code:
            meeting.meeting_code = code
        if data.get("room_id") and not meeting.room_id:
            meeting.room_id = data["room_id"]
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="meeting.session_ready",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"meeting_id": meeting.id, "session_id": session.id, "code": code},
            resource_type="meeting_session",
            resource_id=session.id,
        )
        return session

    async def by_meeting(
        self, db: AsyncSession, *, organization_id: str, meeting_id: str
    ) -> Optional[MeetingSession]:
        return (
            await db.execute(
                select(MeetingSession).where(
                    MeetingSession.organization_id == organization_id,
                    MeetingSession.meeting_id == meeting_id,
                )
            )
        ).scalar_one_or_none()

    async def by_code(self, db: AsyncSession, *, organization_id: str, code: str) -> Optional[MeetingSession]:
        return (
            await db.execute(
                select(MeetingSession).where(
                    MeetingSession.organization_id == organization_id,
                    MeetingSession.meeting_code == code.upper().strip(),
                )
            )
        ).scalar_one_or_none()

    async def start(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: MeetingSession,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> MeetingSession:
        now = utcnow()
        if session.status == "scheduled":
            session.status = "live"
            session.started_at = session.started_at or now
            if meeting.status == "scheduled":
                meeting.status = "in_progress"
            meeting.updated_at = now
            await emit_and_audit(
                db,
                organization_id=organization_id,
                name="meeting.started",
                actor=actor,
                actor_user_id=None,
                ip_address=ip_address,
                payload={"meeting_id": meeting.id, "session_id": session.id},
                resource_type="meeting_session",
                resource_id=session.id,
            )
        return session

    async def end(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: MeetingSession,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
        ai_summary: Optional[str] = None,
    ) -> MeetingSession:
        now = utcnow()
        if session.status in ("live", "scheduled"):
            session.status = "ended"
            session.ended_at = now
            if session.started_at:
                session.duration_seconds = int((now - ensure_aware(session.started_at)).total_seconds())
            meeting.status = "completed"
            meeting.updated_at = now
            if meeting.ai_summary is None:
                meeting.ai_summary = ai_summary or self._build_summary(meeting)
            await emit_and_audit(
                db,
                organization_id=organization_id,
                name="meeting.ended",
                actor=actor,
                actor_user_id=None,
                ip_address=ip_address,
                payload={
                    "meeting_id": meeting.id,
                    "session_id": session.id,
                    "duration_seconds": session.duration_seconds,
                },
                resource_type="meeting_session",
                resource_id=session.id,
            )
        return session

    def _build_summary(self, meeting: Meeting) -> str:
        titles = [a.title for a in getattr(meeting, "agenda", None) or []]
        attendees = getattr(meeting, "attendees", None) or []
        names = [a.get("name") for a in attendees[:6] if isinstance(a, dict)]
        parts = [f"{meeting.title} ({meeting.meeting_type})"]
        if names:
            parts.append(f"Attendees: {', '.join(names)}")
        if titles:
            parts.append(f"Agenda: {'; '.join(titles)}")
        return ". ".join(parts) + "."

    async def upcoming(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee_id: Optional[str] = None,
        scope: str = "organization",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Meeting]:
        """Meetings with session context, scoped personal / department / organization."""
        from app.models.employee import Employee

        stmt = select(Meeting).where(
            Meeting.organization_id == organization_id,
            Meeting.status.in_(("scheduled", "in_progress")),
        )
        if from_date:
            stmt = stmt.where(Meeting.end_at.is_(None) | (Meeting.end_at >= from_date))
        if to_date:
            stmt = stmt.where(Meeting.start_at.is_(None) | (Meeting.start_at <= to_date))
        if scope == "personal" and employee_id:
            stmt = stmt.where(
                Meeting.id.in_(
                    select(MeetingAttendee.meeting_id).where(
                        MeetingAttendee.organization_id == organization_id,
                        MeetingAttendee.employee_id == employee_id,
                    )
                )
            )
        elif scope == "department" and employee_id:
            employee = await db.get(Employee, employee_id)
            dept_id = employee.department_id if employee else None
            if dept_id:
                stmt = stmt.where(
                    (Meeting.department_id == dept_id)
                    | Meeting.id.in_(
                        select(MeetingAttendee.meeting_id).where(
                            MeetingAttendee.organization_id == organization_id,
                            MeetingAttendee.employee_id == employee_id,
                        )
                    )
                )
        rows = await db.execute(stmt.order_by(Meeting.start_at.asc().nullslast()).limit(limit))
        meetings = list(rows.scalars().all())
        for meeting in meetings:
            meeting.session = await self.by_meeting(db, organization_id=organization_id, meeting_id=meeting.id)
        return meetings

    # ------------------------------------------------------------------ joins

    async def join(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: MeetingSession,
        employee: Employee,
        device: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> MeetingParticipant:
        """Start the session (if scheduled) and mark the employee present."""
        if session.status == "scheduled":
            await self.start(
                db,
                organization_id=organization_id,
                meeting=meeting,
                session=session,
                actor=employee,
                ip_address=ip_address,
            )
        participant = await self._participant(
            db, organization_id=organization_id, session_id=session.id, employee_id=employee.id
        )
        now = utcnow()
        if participant is None:
            participant = MeetingParticipant(
                organization_id=organization_id,
                session_id=session.id,
                meeting_id=meeting.id,
                employee_id=employee.id,
                role="host" if employee.id == meeting.organizer_id else "participant",
                status="joined",
                joined_at=now,
                device=device,
                is_present=True,
                last_active_at=now,
            )
            db.add(participant)
            await db.flush()
            await emit_and_audit(
                db,
                organization_id=organization_id,
                name="participant.joined",
                actor=employee,
                actor_user_id=None,
                ip_address=ip_address,
                payload={"meeting_id": meeting.id, "session_id": session.id},
                resource_type="meeting_participant",
                resource_id=participant.id,
            )
        else:
            participant.status = "joined"
            participant.is_present = True
            participant.joined_at = participant.joined_at or now
            participant.device = device
            participant.last_active_at = now
        await self._ensure_attendee(db, organization_id=organization_id, meeting_id=meeting.id, employee=employee)
        return participant

    async def leave(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        session: MeetingSession,
        employee: Employee,
        ip_address: Optional[str] = None,
    ) -> Optional[MeetingParticipant]:
        participant = await self._participant(
            db, organization_id=organization_id, session_id=session.id, employee_id=employee.id
        )
        if participant is None:
            return None
        now = utcnow()
        participant.status = "left"
        participant.is_present = False
        participant.left_at = now
        if participant.joined_at:
            participant.speaking_seconds += max(
                0, int((now - ensure_aware(participant.joined_at)).total_seconds()) // 10
            )
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="participant.left",
            actor=employee,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"meeting_id": session.meeting_id, "session_id": session.id},
            resource_type="meeting_participant",
            resource_id=participant.id,
        )
        return participant

    async def _participant(
        self, db: AsyncSession, *, organization_id: str, session_id: str, employee_id: str
    ) -> Optional[MeetingParticipant]:
        return (
            await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.organization_id == organization_id,
                    MeetingParticipant.session_id == session_id,
                    MeetingParticipant.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def _ensure_attendee(self, db: AsyncSession, *, organization_id: str, meeting_id: str, employee: Employee) -> None:
        row = (
            await db.execute(
                select(MeetingAttendee.id).where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.meeting_id == meeting_id,
                    MeetingAttendee.employee_id == employee.id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                MeetingAttendee(
                    organization_id=organization_id,
                    meeting_id=meeting_id,
                    employee_id=employee.id,
                    role="participant",
                    status="accepted",
                    rsvp_at=utcnow(),
                )
            )
            await db.flush()

    # ------------------------------------------------------------------ invites + calendar

    async def invite(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        employee_ids: list[str],
        actor: Employee,
        ip_address: Optional[str],
        message: Optional[str] = None,
    ) -> list[str]:
        from app.work.meeting_service import meeting_service

        added: list[str] = []
        existing = {
            attendee.employee_id
            for attendee in await meeting_service.attendee_rows(
                db, organization_id=organization_id, meeting_id=meeting.id
            )
        }
        for employee_id in employee_ids:
            if not employee_id or employee_id in existing:
                continue
            await meeting_service.add_attendee(
                db, organization_id=organization_id, meeting_id=meeting.id, employee_id=employee_id
            )
            added.append(employee_id)
        await notify_employee_ids(
            db,
            organization_id=organization_id,
            employee_ids=added,
            type="meeting.invited",
            title=f"You're invited: {meeting.title}",
            body=message or f"{meeting.meeting_type} meeting · {meeting.start_at.isoformat() if meeting.start_at else 'TBD'}",
            actor=actor,
            priority="normal",
            link=f"/meetings/{meeting.id}",
            entity_type="meeting",
            entity_id=meeting.id,
            exclude_ids={actor.id},
        )
        await self.sync_calendar(db, organization_id=organization_id, meeting=meeting, actor=actor)
        if added:
            await emit_and_audit(
                db,
                organization_id=organization_id,
                name="meeting.invited",
                actor=actor,
                actor_user_id=None,
                ip_address=ip_address,
                payload={"meeting_id": meeting.id, "invited": added},
                resource_type="meeting",
                resource_id=meeting.id,
            )
        return added

    async def sync_calendar(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        actor: Optional[Employee] = None,
    ) -> None:
        """Mirror the meeting into the calendar (create once, update attendees)."""
        from app.work.calendar_service import calendar_service

        attendee_rows = (
            await db.execute(
                select(MeetingAttendee.employee_id).where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.meeting_id == meeting.id,
                )
            )
        ).scalars().all()
        attendee_ids = list(attendee_rows)
        if meeting.calendar_event_id:
            event = await calendar_service.get(
                db, organization_id=organization_id, event_id=meeting.calendar_event_id
            )
            if event is not None:
                await calendar_service.update(
                    db,
                    event=event,
                    data={"attendee_ids": attendee_ids, "status": "confirmed"},
                )
                return
        event = await calendar_service.create(
            db,
            organization_id=organization_id,
            data={
                "title": meeting.title,
                "description": meeting.description,
                "event_type": "meeting",
                "start_at": meeting.start_at,
                "end_at": meeting.end_at,
                "location": meeting.location or (meeting.room_id if meeting.room_id else None),
                "calendar_scope": "organization",
                "department_id": meeting.department_id,
                "team_id": meeting.team_id,
                "project_id": meeting.project_id,
                "created_by": meeting.organizer_id or (actor.id if actor else None),
                "attendee_ids": attendee_ids,
                "status": "confirmed",
            },
        )
        meeting.calendar_event_id = event.id

    async def accept_rsvp(self, db: AsyncSession, *, organization_id: str, meeting: Meeting, employee: Employee) -> None:
        """An accept RSVP keeps the calendar invite list current."""
        await self.sync_calendar(db, organization_id=organization_id, meeting=meeting, actor=employee)


session_service = SessionService()
