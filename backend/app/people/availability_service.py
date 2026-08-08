"""Availability services (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee, EmployeeAvailability
from app.services.event_service import event_service

logger = logging.getLogger("vcos.people")

AVAILABILITY_STATUSES = ("available", "busy", "meeting", "leave", "focus", "offline", "remote", "traveling")


class AvailabilityService:
    async def _get_or_create(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> EmployeeAvailability:
        row = (
            await db.execute(
                select(EmployeeAvailability).where(
                    EmployeeAvailability.organization_id == organization_id,
                    EmployeeAvailability.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = EmployeeAvailability(
                organization_id=organization_id, employee_id=employee_id, status="available"
            )
            db.add(row)
            await db.flush()
        return row

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        employee: Employee,
        data: dict[str, Any],
    ) -> EmployeeAvailability:
        if data.get("status") not in AVAILABILITY_STATUSES:
            raise ValueError("Invalid availability status")
        row = await self._get_or_create(db, organization_id=organization_id, employee_id=employee.id)
        old = row.status
        row.status = data["status"]
        if data.get("note") is not None:
            row.note = data["note"]
        if data.get("available_from") is not None:
            row.available_from = data["available_from"]
        if data.get("available_until") is not None:
            row.available_until = data["available_until"]
        row.updated_at = utcnow()
        await db.flush()
        if row.status != old:
            await event_service.emit(
                db, name="employee.availability.changed", actor_id=employee.user_id,
                organization_id=organization_id,
                payload={"employee_id": employee.id, "from": old, "to": row.status},
            )
        return row

    async def get(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> Optional[EmployeeAvailability]:
        return (
            await db.execute(
                select(EmployeeAvailability).where(
                    EmployeeAvailability.organization_id == organization_id,
                    EmployeeAvailability.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def on_leave_count(self, db: AsyncSession, *, organization_id: str) -> int:
        return len(
            (
                await db.execute(
                    select(EmployeeAvailability.id).where(
                        EmployeeAvailability.organization_id == organization_id,
                        EmployeeAvailability.status == "leave",
                    )
                )
            ).scalars().all()
        )


availability_service = AvailabilityService()
