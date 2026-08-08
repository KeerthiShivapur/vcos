"""Presence services (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee, EmployeePresence
from app.services.event_service import event_service

logger = logging.getLogger("vcos.people")

PRESENCE_STATUSES = ("online", "away", "busy", "offline")


class PresenceService:
    async def _get_or_create_presence(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> EmployeePresence:
        presence = (
            await db.execute(
                select(EmployeePresence).where(
                    EmployeePresence.organization_id == organization_id,
                    EmployeePresence.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if presence is None:
            presence = EmployeePresence(
                organization_id=organization_id, employee_id=employee_id,
                is_online=False, status="offline",
            )
            db.add(presence)
            await db.flush()
        return presence

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee: Employee,
        data: dict[str, Any],
        ip_address: Optional[str] = None,
    ) -> EmployeePresence:
        presence = await self._get_or_create_presence(
            db, organization_id=organization_id, employee_id=employee.id
        )
        old_status = presence.status
        if "status" in data and data["status"]:
            presence.status = data["status"]
            presence.is_online = data["status"] == "online"
        if data.get("working_hours") is not None:
            presence.working_hours = data["working_hours"]
        if data.get("timezone") is not None:
            presence.timezone = data["timezone"]
        if data.get("device") is not None:
            presence.device = data["device"]
        presence.last_active_at = utcnow()
        presence.updated_at = utcnow()
        await db.flush()
        if presence.status != old_status:
            await event_service.emit(
                db, name="employee.presence.changed", actor_id=employee.user_id,
                organization_id=organization_id,
                payload={"employee_id": employee.id, "from": old_status, "to": presence.status},
            )
        return presence

    async def heartbeat(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        status: str = "online",
    ) -> EmployeePresence:
        if status not in PRESENCE_STATUSES:
            raise ValueError("Invalid presence status")
        presence = await self._get_or_create_presence(
            db, organization_id=organization_id, employee_id=employee_id
        )
        old = presence.status
        presence.status = status
        presence.is_online = status == "online"
        presence.last_active_at = utcnow()
        presence.updated_at = utcnow()
        await db.flush()
        if presence.status != old:
            await event_service.emit(
                db, name="employee.presence.changed", organization_id=organization_id,
                payload={"employee_id": employee_id, "from": old, "to": presence.status},
            )
        return presence

    async def get(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> Optional[EmployeePresence]:
        return (
            await db.execute(
                select(EmployeePresence).where(
                    EmployeePresence.organization_id == organization_id,
                    EmployeePresence.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def online_count(self, db: AsyncSession, *, organization_id: str) -> int:
        return len(
            (
                await db.execute(
                    select(EmployeePresence.id).where(
                        EmployeePresence.organization_id == organization_id,
                        EmployeePresence.is_online.is_(True),
                    )
                )
            ).scalars().all()
        )


presence_service = PresenceService()
