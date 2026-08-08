"""Events and clubs service (Phase 5.11, 5.12, 5.13, 5.14)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_community_members, notify_mentions
from app.models.communication import CommunityEvent, EventRegistration
from app.models.employee import Employee


class EventService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> CommunityEvent:
        event = CommunityEvent(
            organization_id=organization_id,
            title=payload["title"],
            description=payload.get("description"),
            type=payload.get("type", "other"),
            community_id=payload.get("community_id"),
            starts_at=payload["starts_at"],
            ends_at=payload.get("ends_at"),
            location=payload.get("location"),
            virtual_url=payload.get("virtual_url"),
            capacity=payload.get("capacity", 0),
            status=payload.get("status", "open"),
            registration_deadline=payload.get("registration_deadline"),
            team_based=payload.get("team_based", False),
            created_by=actor.id,
        )
        db.add(event)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="event.created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"event_id": event.id, "title": event.title},
            resource_type="community_event",
            resource_id=event.id,
        )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text=f"{event.title} {event.description or ''}",
            type="mention",
            title="You were mentioned in an event",
            body=event.title,
            actor_id=actor.id,
            link=f"/events/{event.id}",
            entity_type="community_event",
            entity_id=event.id,
        )
        if event.community_id:
            await notify_community_members(
                db,
                organization_id=organization_id,
                community_id=event.community_id,
                type="community.event",
                title=f"New event: {event.title}",
                body=event.description or "",
                actor_id=actor.id,
                link=f"/events/{event.id}",
                entity_type="community_event",
                entity_id=event.id,
            )
        return event

    async def get(self, db: AsyncSession, *, organization_id: str, event_id: str) -> Optional[CommunityEvent]:
        return (
            await db.execute(
                select(CommunityEvent).where(
                    CommunityEvent.organization_id == organization_id,
                    CommunityEvent.id == event_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        type: Optional[str] = None,
        upcoming: Optional[bool] = None,
        community_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CommunityEvent]:
        filters = [CommunityEvent.organization_id == organization_id]
        if type:
            filters.append(CommunityEvent.type == type)
        if upcoming is True:
            filters.append(CommunityEvent.starts_at >= datetime.utcnow())
        elif upcoming is False:
            filters.append(CommunityEvent.starts_at < datetime.utcnow())
        if community_id:
            filters.append(CommunityEvent.community_id == community_id)
        if search:
            filters.append(func.lower(CommunityEvent.title).like(f"%{search.lower()}%"))
        return list(
            (
                await db.execute(
                    select(CommunityEvent)
                    .where(*filters)
                    .order_by(CommunityEvent.starts_at.asc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, event_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[CommunityEvent]:
        event = await self.get(db, organization_id=organization_id, event_id=event_id)
        if event is None:
            return None
        allowed = {
            "title", "description", "type", "community_id", "starts_at", "ends_at",
            "location", "virtual_url", "capacity", "status", "registration_deadline",
            "team_based",
        }
        for key, value in payload.items():
            if key in allowed and value is not None:
                setattr(event, key, value)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="event.updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"event_id": event_id},
            resource_type="community_event",
            resource_id=event_id,
        )
        return event

    async def delete(
        self, db: AsyncSession, *, organization_id: str, event_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        event = await self.get(db, organization_id=organization_id, event_id=event_id)
        if event is None:
            return False
        await db.delete(event)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="event.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"event_id": event_id},
            resource_type="community_event",
            resource_id=event_id,
        )
        return True

    async def register(
        self, db: AsyncSession, *, organization_id: str, event_id: str, actor: Employee, team_name: Optional[str], role: str
    ) -> dict[str, Any]:
        event = await self.get(db, organization_id=organization_id, event_id=event_id)
        if event is None:
            raise ValueError("Event not found")
        if event.status not in ("open", "completed"):
            raise ValueError("Event is not open for registration")
        existing = (
            await db.execute(
                select(EventRegistration).where(
                    EventRegistration.organization_id == organization_id,
                    EventRegistration.event_id == event_id,
                    EventRegistration.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await db.delete(existing)
            event.registration_count = max(0, (event.registration_count or 1) - 1)
            return {"registered": False, "registration_count": event.registration_count}
        if event.capacity and (event.registration_count or 0) >= event.capacity:
            raise ValueError("Event is full")
        db.add(
            EventRegistration(
                organization_id=organization_id,
                event_id=event_id,
                employee_id=actor.id,
                team_name=team_name,
                role=role,
                status="registered",
            )
        )
        event.registration_count = (event.registration_count or 0) + 1
        if event.created_by and event.created_by != actor.id:
            from app.communication.events import notify_user

            await notify_user(
                db,
                organization_id=organization_id,
                recipient_id=event.created_by,
                type="community.activity",
                title="New event registration",
                body=f"{actor.display_name or actor.first_name} registered for {event.title}",
                actor_id=actor.id,
                link=f"/events/{event_id}",
                entity_type="community_event",
                entity_id=event_id,
            )
        return {"registered": True, "registration_count": event.registration_count}

    async def my_registration(
        self, db: AsyncSession, *, organization_id: str, event_id: str, employee_id: str
    ) -> Optional[EventRegistration]:
        return (
            await db.execute(
                select(EventRegistration).where(
                    EventRegistration.organization_id == organization_id,
                    EventRegistration.event_id == event_id,
                    EventRegistration.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def registrations(
        self, db: AsyncSession, *, organization_id: str, event_id: str, limit: int = 500
    ) -> list[EventRegistration]:
        return list(
            (
                await db.execute(
                    select(EventRegistration)
                    .where(EventRegistration.organization_id == organization_id, EventRegistration.event_id == event_id)
                    .order_by(EventRegistration.created_at.asc())
                    .limit(min(limit, 1000))
                )
            ).scalars().all()
        )

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        total = (
            await db.execute(select(func.count(CommunityEvent.id)).where(CommunityEvent.organization_id == organization_id))
        ).scalar_one()
        upcoming = (
            await db.execute(
                select(func.count(CommunityEvent.id)).where(
                    CommunityEvent.organization_id == organization_id,
                    CommunityEvent.starts_at >= datetime.utcnow(),
                    CommunityEvent.status == "open",
                )
            )
        ).scalar_one()
        registrations = (
            await db.execute(select(func.count(EventRegistration.id)).where(EventRegistration.organization_id == organization_id))
        ).scalar_one()
        return {"total": total, "upcoming": upcoming, "registrations": registrations}


event_service = EventService()
