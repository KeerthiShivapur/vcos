"""Task collaboration — comments, @mentions, attachments, and activity history.

Each mutation is audited and emitted on the event bus so the work stream,
notifications and the audit trail stay consistent with the execution reality.
"""

import json
import re
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.notification import AuditLog
from app.models.task import Task, TaskAttachment, TaskComment

_MENTION_RE = re.compile(r"@([\w\.\-+]+@[\w\.\-]+)")


class TaskCollabService:
    # ------------------------------------------------------------------ comments

    async def _resolve_task(self, db: AsyncSession, *, organization_id: str, task_id: str) -> Optional[Task]:
        return (
            await db.execute(
                select(Task).where(Task.organization_id == organization_id, Task.id == task_id)
            )
        ).scalar_one_or_none()

    async def _resolve_mentioned(
        self, db: AsyncSession, *, organization_id: str, body: str,
        explicit: Optional[list[str]] = None,
    ) -> list[tuple[Employee, str]]:
        """Mentioned employees: explicit ids plus @email tokens from the body."""
        employees: dict[str, Employee] = {}
        for employee_id in explicit or []:
            if not employee_id:
                continue
            emp = await db.get(Employee, employee_id)
            if emp is not None and emp.organization_id == organization_id:
                employees[emp.id] = emp
        for email in _MENTION_RE.findall(body):
            emp = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == organization_id,
                        Employee.email == email,
                    )
                )
            ).scalar_one_or_none()
            if emp is not None:
                employees[emp.id] = emp
        return list(employees.values())

    async def add_comment(
        self, db: AsyncSession, *, organization_id: str, task_id: str, body: str,
        author: Optional[Employee] = None, mentions: Optional[list[str]] = None,
        ip_address: Optional[str] = None,
    ) -> TaskComment:
        task = await self._resolve_task(db, organization_id=organization_id, task_id=task_id)
        if task is None:
            raise ValueError("Task not found")
        mentioned = await self._resolve_mentioned(
            db, organization_id=organization_id, body=body, explicit=mentions
        )
        comment = TaskComment(
            organization_id=organization_id,
            task_id=task_id,
            author_id=author.id if author else None,
            body=body,
            mentions=[e.id for e in mentioned] or None,
        )
        db.add(comment)
        await db.flush()

        from app.services.event_service import event_service

        await event_service.emit(
            db, name="task.commented", actor_id=author.user_id if author else None,
            organization_id=organization_id,
            payload={
                "task_id": task_id, "comment_id": comment.id, "title": task.title,
                "author_id": author.id if author else None, "body": body[:200],
            },
        )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.commented",
            actor=author, ip_address=ip_address,
            resource_type="task", resource_id=task_id,
            details={"comment_id": comment.id, "title": task.title},
        )
        for emp in mentioned:
            if author is not None and emp.id == author.id:
                continue
            from app.services.work_alerts import notify_employee

            await notify_employee(
                db, organization_id=organization_id, employee_id=emp.id,
                type="task.mention",
                title=f"You were mentioned in: {task.title}",
                body=body[:200],
                actor_id=author.user_id if author else None,
                entity_type="task", entity_id=task_id,
                link=f"/tasks/{task_id}",
                priority="normal",
            )
        return comment

    async def list_comments(
        self, db: AsyncSession, *, organization_id: str, task_id: str, limit: int = 100,
    ) -> list[TaskComment]:
        rows = await db.execute(
            select(TaskComment)
            .where(TaskComment.organization_id == organization_id, TaskComment.task_id == task_id)
            .order_by(desc(TaskComment.created_at))
            .limit(limit)
        )
        comments = list(rows.scalars().all())
        author_ids = {c.author_id for c in comments if c.author_id}
        authors = {}
        if author_ids:
            authors = {
                e.id: e for e in (
                    await db.execute(select(Employee).where(Employee.id.in_(author_ids)))
                ).scalars().all()
            }
        for c in comments:
            c.author_name = authors[c.author_id].full_name if c.author_id and authors.get(c.author_id) else None
        return comments

    async def delete_comment(
        self, db: AsyncSession, *, organization_id: str, comment: TaskComment,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.comment_deleted",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=comment.task_id,
            details={"comment_id": comment.id},
        )
        await db.delete(comment)

    # ---------------------------------------------------------------- attachments

    async def add_attachment(
        self, db: AsyncSession, *, organization_id: str, task_id: str,
        filename: str, url: str, size_bytes: int = 0, kind: Optional[str] = None,
        uploader: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> TaskAttachment:
        task = await self._resolve_task(db, organization_id=organization_id, task_id=task_id)
        if task is None:
            raise ValueError("Task not found")
        attachment = TaskAttachment(
            organization_id=organization_id,
            task_id=task_id,
            filename=filename,
            url=url,
            size_bytes=size_bytes,
            kind=kind,
            uploaded_by=uploader.id if uploader else None,
        )
        db.add(attachment)
        await db.flush()

        from app.services.event_service import event_service

        await event_service.emit(
            db, name="task.attachment_added", actor_id=uploader.user_id if uploader else None,
            organization_id=organization_id,
            payload={
                "task_id": task_id, "attachment_id": attachment.id,
                "title": task.title, "filename": filename,
            },
        )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.attachment_added",
            actor=uploader, ip_address=ip_address,
            resource_type="task", resource_id=task_id,
            details={"attachment_id": attachment.id, "filename": filename, "title": task.title},
        )
        return attachment

    async def list_attachments(
        self, db: AsyncSession, *, organization_id: str, task_id: str, limit: int = 100,
    ) -> list[TaskAttachment]:
        rows = await db.execute(
            select(TaskAttachment)
            .where(TaskAttachment.organization_id == organization_id, TaskAttachment.task_id == task_id)
            .order_by(desc(TaskAttachment.created_at))
            .limit(limit)
        )
        attachments = list(rows.scalars().all())
        uploader_ids = {a.uploaded_by for a in attachments if a.uploaded_by}
        uploaders = {}
        if uploader_ids:
            uploaders = {
                e.id: e for e in (
                    await db.execute(select(Employee).where(Employee.id.in_(uploader_ids)))
                ).scalars().all()
            }
        for a in attachments:
            a.uploaded_by_name = uploaders[a.uploaded_by].full_name if a.uploaded_by and uploaders.get(a.uploaded_by) else None
        return attachments

    async def delete_attachment(
        self, db: AsyncSession, *, organization_id: str, attachment: TaskAttachment,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name="task.attachment_removed", actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"task_id": attachment.task_id, "attachment_id": attachment.id, "filename": attachment.filename},
        )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.attachment_removed",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=attachment.task_id,
            details={"attachment_id": attachment.id, "filename": attachment.filename},
        )
        await db.delete(attachment)

    # ---------------------------------------------------------------- activity

    async def activity(
        self, db: AsyncSession, *, organization_id: str, task_id: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(AuditLog)
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.resource_type == "task",
                AuditLog.resource_id == task_id,
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        return [
            {
                "id": r.id,
                "action": r.action,
                "actor_id": r.actor_id,
                "actor_email": r.actor_email,
                "details": r.details,
                "severity": r.severity,
                "outcome": r.outcome,
                "created_at": r.created_at,
            }
            for r in rows.scalars().all()
        ]


task_collab_service = TaskCollabService()
