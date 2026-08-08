"""Offboarding service (Phase 11.7 — Offboarding & Alumni).

Resignation → approval → knowledge transfer → asset return → access
removal → exit interview → final settlement. On completion the employee
moves to inactive status and (optionally) becomes an AlumniProfile so the
relationship continues as an alumni network (boomerang rehires, mentorship,
referrals, knowledge contributions).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date
from app.models.employee import Employee
from app.models.hr import AlumniProfile, Offboarding, OffboardingTask

logger = logging.getLogger("vcos.hr.offboarding")

_event_bus = EventBus()

DEFAULT_TASKS: list[tuple[str, str]] = [
    ("knowledge", "Complete knowledge transfer of owned documents and responsibilities"),
    ("asset", "Return all assigned assets (laptop, phone, access card, licenses)"),
    ("access", "Revoke system access, credentials and memberships"),
    ("finance", "Finalize settlement, payouts and payroll for the exit date"),
    ("document", "Collect exit documents and sign-offs"),
    ("exit", "Complete the exit interview"),
]

STATUSES = ["requested", "approved", "in_progress", "completed"]


class OffboardingService:
    async def start(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], initiated_by: Optional[str] = None,
    ) -> Offboarding:
        employee = await db.get(Employee, data["employee_id"])
        if employee is None:
            raise ValueError("unknown employee")
        existing = (
            await db.execute(
                select(Offboarding).where(
                    Offboarding.organization_id == organization_id, Offboarding.employee_id == data["employee_id"]
                )
            )
        ).scalar_one_or_none()
        if existing and existing.status != "completed":
            raise ValueError("an offboarding is already active for this employee")
        offboarding = Offboarding(
            organization_id=organization_id,
            employee_id=data["employee_id"],
            reason=data.get("reason"),
            resignation_date=to_date(data.get("resignation_date")),
            exit_date=to_date(data.get("exit_date")),
            status=data.get("status", "requested") if data.get("status") in STATUSES else "requested",
            initiated_by=initiated_by,
            transitions_to_alumni=bool(data.get("transitions_to_alumni", True)),
        )
        db.add(offboarding)
        await db.flush()
        for position, (category, title) in enumerate(DEFAULT_TASKS):
            db.add(
                OffboardingTask(
                    organization_id=organization_id,
                    offboarding_id=offboarding.id,
                    title=title,
                    category=category,
                    position=position,
                )
            )
        for position, task in enumerate(data.get("tasks") or [], start=len(DEFAULT_TASKS)):
            db.add(
                OffboardingTask(
                    organization_id=organization_id,
                    offboarding_id=offboarding.id,
                    title=task.get("title", "Task"),
                    category=task.get("category", "knowledge"),
                    position=position,
                )
            )
        await db.flush()
        return offboarding

    async def get(self, db: AsyncSession, *, organization_id: str, offboarding_id: str) -> Optional[dict[str, Any]]:
        offboarding = (
            await db.execute(
                select(Offboarding).where(Offboarding.organization_id == organization_id, Offboarding.id == offboarding_id)
            )
        ).scalar_one_or_none()
        return await self._out(db, offboarding) if offboarding else None

    async def list(
        self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Offboarding).where(Offboarding.organization_id == organization_id)
        if status:
            query = query.where(Offboarding.status == status)
        rows = await db.execute(query.order_by(Offboarding.created_at.desc()))
        return [await self._out(db, offboarding) for offboarding in rows.scalars().all()]

    async def _out(self, db: AsyncSession, offboarding: Offboarding) -> dict[str, Any]:
        employee = await db.get(Employee, offboarding.employee_id)
        tasks = (
            await db.execute(
                select(OffboardingTask).where(OffboardingTask.offboarding_id == offboarding.id).order_by(OffboardingTask.position)
            )
        ).scalars().all()
        return {
            "id": offboarding.id,
            "employee_id": offboarding.employee_id,
            "employee_name": employee.full_name if employee else None,
            "designation": employee.designation if employee else None,
            "reason": offboarding.reason,
            "resignation_date": offboarding.resignation_date.isoformat() if offboarding.resignation_date else None,
            "exit_date": offboarding.exit_date.isoformat() if offboarding.exit_date else None,
            "status": offboarding.status,
            "initiated_by": offboarding.initiated_by,
            "completed_at": offboarding.completed_at.isoformat() if offboarding.completed_at else None,
            "knowledge_transfer": offboarding.knowledge_transfer or [],
            "exit_interview": offboarding.exit_interview,
            "transitions_to_alumni": offboarding.transitions_to_alumni,
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "category": task.category,
                    "status": task.status,
                    "completed_by": task.completed_by,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "notes": task.notes,
                }
                for task in tasks
            ],
        }

    async def add_task(
        self, db: AsyncSession, *, organization_id: str, offboarding_id: str, data: dict[str, Any],
    ) -> Optional[OffboardingTask]:
        offboarding = (
            await db.execute(
                select(Offboarding).where(Offboarding.organization_id == organization_id, Offboarding.id == offboarding_id)
            )
        ).scalar_one_or_none()
        if offboarding is None:
            return None
        count = (
            await db.execute(select(OffboardingTask).where(OffboardingTask.offboarding_id == offboarding.id))
        ).scalars().all()
        task = OffboardingTask(
            organization_id=organization_id,
            offboarding_id=offboarding.id,
            title=data["title"],
            category=data.get("category", "knowledge"),
            position=len(count),
        )
        db.add(task)
        await db.flush()
        return task

    async def complete_task(
        self, db: AsyncSession, *, organization_id: str, offboarding_id: str, task_id: str,
        completed_by: Optional[str] = None, notes: Optional[str] = None,
    ) -> Optional[OffboardingTask]:
        task = (
            await db.execute(
                select(OffboardingTask).where(
                    OffboardingTask.offboarding_id == offboarding_id, OffboardingTask.id == task_id
                )
            )
        ).scalar_one_or_none()
        if task is None:
            return None
        task.status = "completed"
        task.completed_by = completed_by
        task.completed_at = utcnow()
        if notes is not None:
            task.notes = notes
        offboarding = await db.get(Offboarding, offboarding_id)
        if offboarding and offboarding.status in ("requested", "approved"):
            offboarding.status = "in_progress"
        await db.flush()
        return task

    async def submit_exit_interview(
        self, db: AsyncSession, *, organization_id: str, offboarding_id: str, data: dict[str, Any],
    ) -> Optional[Offboarding]:
        offboarding = (
            await db.execute(
                select(Offboarding).where(Offboarding.organization_id == organization_id, Offboarding.id == offboarding_id)
            )
        ).scalar_one_or_none()
        if offboarding is None:
            return None
        offboarding.exit_interview = {
            "feedback": data.get("feedback"),
            "reason": data.get("reason") or offboarding.reason,
            "completed": True,
            "notes": data.get("notes"),
        }
        await db.flush()
        return offboarding

    async def complete(
        self, db: AsyncSession, *, organization_id: str, offboarding_id: str,
    ) -> Optional[dict[str, Any]]:
        """Finalize the offboarding: employee → inactive, alumni profile created."""
        offboarding = (
            await db.execute(
                select(Offboarding).where(Offboarding.organization_id == organization_id, Offboarding.id == offboarding_id)
            )
        ).scalar_one_or_none()
        if offboarding is None:
            return None
        tasks = (
            await db.execute(select(OffboardingTask).where(OffboardingTask.offboarding_id == offboarding.id))
        ).scalars().all()
        if not all(task.status == "completed" for task in tasks):
            raise ValueError("all offboarding tasks must be completed first")
        offboarding.status = "completed"
        offboarding.completed_at = utcnow()

        employee = await db.get(Employee, offboarding.employee_id)
        if employee:
            employee.status = "inactive"
            # hand over managed employees to their skip-level / keep direct reports open
            reports = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id, Employee.manager_id == employee.id
                    )
                )
            ).scalars().all()
            for report in reports:
                report.manager_id = employee.manager_id

        alumni = None
        if offboarding.transitions_to_alumni:
            alumni = AlumniProfile(
                organization_id=organization_id,
                employee_id=offboarding.employee_id,
                left_at=offboarding.exit_date,
                reason=offboarding.reason,
                keep_in_touch=True,
            )
            db.add(alumni)
            await db.flush()
        await _event_bus.publish(
            db,
            name="employee.offboarded",
            organization_id=organization_id,
            actor_id=offboarding.employee_id,
            payload={
                "employee_id": offboarding.employee_id,
                "employee_name": employee.full_name if employee else None,
                "reason": offboarding.reason,
                "exit_date": (offboarding.exit_date or utcnow().date()).isoformat(),
                "alumni_id": alumni.id if alumni else None,
            },
            flush=False,
        )
        await db.flush()
        return await self._out(db, offboarding)

    # ------------------------------------------------------------------ alumni

    async def alumni_list(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(AlumniProfile).where(AlumniProfile.organization_id == organization_id)
        if status:
            query = query.where(AlumniProfile.status == status)
        rows = await db.execute(query.order_by(AlumniProfile.created_at.desc()))
        result = []
        for profile in rows.scalars().all():
            employee = await db.get(Employee, profile.employee_id)
            result.append(
                {
                    "id": profile.id,
                    "employee_id": profile.employee_id,
                    "name": employee.full_name if employee else None,
                    "designation": employee.designation if employee else None,
                    "left_at": profile.left_at.isoformat() if profile.left_at else None,
                    "reason": profile.reason,
                    "status": profile.status,
                    "linkedin": profile.linkedin,
                    "keep_in_touch": profile.keep_in_touch,
                    "knowledge_contributions": profile.knowledge_contributions or [],
                    "last_activity": profile.last_activity.isoformat() if profile.last_activity else None,
                }
            )
        return result

    async def update_alumni(
        self, db: AsyncSession, *, organization_id: str, alumni_id: str, data: dict[str, Any],
    ) -> Optional[AlumniProfile]:
        profile = (
            await db.execute(
                select(AlumniProfile).where(AlumniProfile.organization_id == organization_id, AlumniProfile.id == alumni_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            return None
        for field in ("status", "linkedin", "keep_in_touch", "knowledge_contributions", "reason"):
            if field in data:
                setattr(profile, field, data[field])
        if "knowledge_contributions" in data:
            profile.last_activity = utcnow()
        await db.flush()
        return profile

    async def mark_boomerang(self, db: AsyncSession, *, organization_id: str, alumni_id: str) -> Optional[AlumniProfile]:
        """Mark an alumnus as a boomerang (rehired)."""
        return await self.update_alumni(
            db, organization_id=organization_id, alumni_id=alumni_id, data={"status": "boomerang"}
        )


offboarding_service = OffboardingService()
