"""Meeting room service — physical + virtual rooms, availability, scoping (Phase 6)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collaboration.collab_base import emit_and_audit, safe_json
from app.core.timeutils import utcnow
from app.models.collaboration import MeetingRoom
from app.models.employee import Employee
from app.models.meeting import Meeting


class RoomService:
    async def _validate_refs(self, db: AsyncSession, organization_id: str, data: dict[str, Any]) -> None:
        from app.models.department import Department
        from app.models.project import Project
        from app.models.team import Team

        for key, model in (("department_id", Department), ("team_id", Team), ("project_id", Project)):
            value = data.get(key)
            if not value:
                continue
            obj = await db.get(model, value)
            if obj is None or getattr(obj, "organization_id", None) != organization_id:
                raise ValueError(f"Invalid {key} reference")

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> MeetingRoom:
        await self._validate_refs(db, organization_id, data)
        room = MeetingRoom(
            organization_id=organization_id,
            name=data["name"],
            room_type=data.get("room_type", "meeting"),
            description=data.get("description"),
            capacity=data.get("capacity", 8),
            location=data.get("location"),
            status=data.get("status", "available"),
            department_id=data.get("department_id"),
            team_id=data.get("team_id"),
            project_id=data.get("project_id"),
            created_by=data.get("created_by") or (actor.id if actor else None),
            is_public=data.get("is_public", True),
            allow_recording=data.get("allow_recording", True),
            settings=safe_json(data.get("settings")),
        )
        db.add(room)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="room.created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"room_id": room.id, "name": room.name, "room_type": room.room_type},
            resource_type="meeting_room",
            resource_id=room.id,
        )
        return room

    async def get(self, db: AsyncSession, *, organization_id: str, room_id: str) -> Optional[MeetingRoom]:
        return (
            await db.execute(
                select(MeetingRoom).where(
                    MeetingRoom.organization_id == organization_id, MeetingRoom.id == room_id
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        room_type: Optional[str] = None,
        status: Optional[str] = None,
        department_id: Optional[str] = None,
        team_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[MeetingRoom]:
        stmt = select(MeetingRoom).where(MeetingRoom.organization_id == organization_id)
        if room_type:
            stmt = stmt.where(MeetingRoom.room_type == room_type)
        if status:
            stmt = stmt.where(MeetingRoom.status == status)
        if department_id:
            stmt = stmt.where(MeetingRoom.department_id == department_id)
        if team_id:
            stmt = stmt.where(MeetingRoom.team_id == team_id)
        rows = await db.execute(stmt.order_by(MeetingRoom.name.asc()).limit(limit))
        return list(rows.scalars().all())

    async def update(
        self, db: AsyncSession, *, organization_id: str, room: MeetingRoom, data: dict[str, Any]
    ) -> MeetingRoom:
        await self._validate_refs(db, organization_id, data)
        for key, value in data.items():
            if key == "settings":
                value = safe_json(value)
            if hasattr(room, key) and key not in ("id", "organization_id", "created_at"):
                setattr(room, key, value)
        room.updated_at = utcnow()
        return room

    async def delete(self, db: AsyncSession, *, room: MeetingRoom) -> None:
        await db.delete(room)

    async def availability(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        room_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Meetings + calendar events booked in this room over the window."""
        from app.models.calendar import CalendarEvent

        out: list[dict[str, Any]] = []
        conditions = [Meeting.organization_id == organization_id, Meeting.room_id == room_id]
        if start:
            conditions.append(Meeting.end_at >= start)
        if end:
            conditions.append(Meeting.start_at <= end)
        meetings = (
            await db.execute(select(Meeting).where(*conditions).order_by(Meeting.start_at.asc()))
        ).scalars().all()
        for meeting in meetings:
            out.append(
                {
                    "kind": "meeting",
                    "id": meeting.id,
                    "title": meeting.title,
                    "start_at": meeting.start_at,
                    "end_at": meeting.end_at,
                    "status": meeting.status,
                }
            )
        event_conditions = [CalendarEvent.organization_id == organization_id]
        if room_id:
            event_conditions.append(
                or_(
                    CalendarEvent.location == room_id,
                    CalendarEvent.location == f"room:{room_id}",
                )
            )
        if start:
            event_conditions.append(CalendarEvent.end_at >= start)
        if end:
            event_conditions.append(CalendarEvent.start_at <= end)
        events = (
            await db.execute(select(CalendarEvent).where(*event_conditions).order_by(CalendarEvent.start_at.asc()))
        ).scalars().all()
        for event in events:
            out.append(
                {
                    "kind": "event",
                    "id": event.id,
                    "title": event.title,
                    "start_at": event.start_at,
                    "end_at": event.end_at,
                    "status": event.status,
                }
            )
        return sorted(out, key=lambda item: item["start_at"] or utcnow())

    async def sessions(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        room_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        from app.models.collaboration import MeetingSession

        stmt = select(MeetingSession).where(
            MeetingSession.organization_id == organization_id, MeetingSession.room_id == room_id
        )
        if status:
            stmt = stmt.where(MeetingSession.status == status)
        rows = await db.execute(stmt.order_by(MeetingSession.started_at.desc().nullslast()).limit(limit))
        return list(rows.scalars().all())


room_service = RoomService()
