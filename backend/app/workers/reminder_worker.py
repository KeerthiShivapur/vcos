"""Reminder worker — proactive nudges for time-sensitive work.

Creates in-app notifications for:
  - meetings starting within 30 minutes (for accepted attendees)
  - tasks due within 24 hours or overdue (for assignees)
  - pending approvals nearing their due date (for approvers)

Deduplicates by (entity_type, entity_id) so reminders fire once per entity.

Run standalone: python -m app.workers.reminder_worker
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.approval import Approval
from app.models.meeting import Meeting, MeetingAttendee
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.task import Task
from app.services.notification_service import notification_service

logger = logging.getLogger("vcos.workers.reminder")

MEETING_WINDOW_MINUTES = 30
TASK_WINDOW_HOURS = 24


async def _already_reminded(db, *, organization_id: str, entity_type: str, entity_id: str) -> bool:
    row = await db.execute(
        select(Notification.id).where(
            Notification.organization_id == organization_id,
            Notification.type == "reminder",
            Notification.entity_type == entity_type,
            Notification.entity_id == entity_id,
        )
    )
    return row.scalars().first() is not None


async def run_once() -> int:
    created = 0
    now = utcnow()
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(
                select(Organization.id).where(Organization.status == "active")
            )
        ).scalars().all()

        for org_id in org_ids:
            try:
                # Meetings starting soon
                soon = now + timedelta(minutes=MEETING_WINDOW_MINUTES)
                meetings = (
                    await db.execute(
                        select(Meeting).where(
                            Meeting.organization_id == org_id,
                            Meeting.status == "scheduled",
                            Meeting.start_at.isnot(None),
                            Meeting.start_at > now,
                            Meeting.start_at <= soon,
                        )
                    )
                ).scalars().all()
                for meeting in meetings:
                    attendees = (
                        await db.execute(
                            select(MeetingAttendee).where(
                                MeetingAttendee.organization_id == org_id,
                                MeetingAttendee.meeting_id == meeting.id,
                                MeetingAttendee.status.in_(("accepted", "invited")),
                            )
                        )
                    ).scalars().all()
                    for attendee in attendees:
                        if await _already_reminded(
                            db, organization_id=org_id,
                            entity_type="meeting", entity_id=f"{meeting.id}:{attendee.employee_id}",
                        ):
                            continue
                        await notification_service.create(
                            db, organization_id=org_id, recipient_id=attendee.employee_id,
                            type="reminder", title=f"Meeting in {MEETING_WINDOW_MINUTES} minutes: {meeting.title}",
                            body=f"Starts at {meeting.start_at.isoformat() if meeting.start_at else 'soon'}",
                            priority="high", link=f"/meetings/{meeting.id}",
                            entity_type="meeting", entity_id=f"{meeting.id}:{attendee.employee_id}",
                        )
                        created += 1

                # Tasks due soon / overdue
                window_end = now + timedelta(hours=TASK_WINDOW_HOURS)
                tasks = (
                    await db.execute(
                        select(Task).where(
                            Task.organization_id == org_id,
                            Task.assignee_id.isnot(None),
                            Task.status.notin_(("completed", "archived")),
                            Task.due_date.isnot(None),
                            Task.due_date <= window_end,
                        )
                    )
                ).scalars().all()
                for task in tasks:
                    if await _already_reminded(
                        db, organization_id=org_id,
                        entity_type="task", entity_id=f"{task.id}:{task.due_date.isoformat() if task.due_date else ''}",
                    ):
                        continue
                    overdue = task.due_date < now
                    await notification_service.create(
                        db, organization_id=org_id, recipient_id=task.assignee_id,
                        type="reminder",
                        title=f"{'Overdue' if overdue else 'Due soon'}: {task.title}",
                        body=f"Due {task.due_date.isoformat()}",
                        priority="high" if overdue else "normal",
                        link=f"/tasks/{task.id}",
                        entity_type="task",
                        entity_id=f"{task.id}:{task.due_date.isoformat() if task.due_date else ''}",
                    )
                    created += 1

                # Pending approvals near due date
                approvals = (
                    await db.execute(
                        select(Approval).where(
                            Approval.organization_id == org_id,
                            Approval.status == "pending",
                            Approval.approver_id.isnot(None),
                            Approval.due_at.isnot(None),
                            Approval.due_at <= now + timedelta(hours=24),
                        )
                    )
                ).scalars().all()
                for approval in approvals:
                    if await _already_reminded(
                        db, organization_id=org_id,
                        entity_type="approval", entity_id=approval.id,
                    ):
                        continue
                    await notification_service.create(
                        db, organization_id=org_id, recipient_id=approval.approver_id,
                        type="reminder", title=f"Approval needed: {approval.title}",
                        body=f"Due {approval.due_at.isoformat()}",
                        priority="normal", link=f"/approvals/{approval.id}",
                        entity_type="approval", entity_id=approval.id,
                    )
                    created += 1
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("reminder worker skipped org %s: %s", org_id, exc)

        await db.commit()
        return created


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            created = await run_once()
            if created:
                logger.info("reminder worker created %s notifications", created)
        except Exception as exc:  # pragma: no cover
            logger.exception("reminder worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
