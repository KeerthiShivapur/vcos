"""Phase 7.10 — action engine.

Executes authorized actions on behalf of the companion. Every execution is
audited in ``ai_actions`` with the payload, result, and the permission check
that guarded it. Actions never bypass the regular services — they call the
same task/meeting/knowledge services the UI uses, so events, alerts and audit
trails stay intact.

Action catalog:
  create_task        tasks:manage     -> task_service.create
  update_task_status tasks:manage     -> task_service.update (status/progress)
  schedule_meeting   meetings:manage  -> meeting_service.create
  remember           ai:use           -> memory manager write
  find_assignee      ai:use           -> resolve an employee by name/email
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIAction
from app.models.employee import Employee
from app.models.user import User

_ACTION_PERMISSIONS = {
    "create_task": "tasks:manage",
    "update_task_status": "tasks:manage",
    "schedule_meeting": "meetings:manage",
    "remember": "ai:use",
    "find_assignee": "ai:use",
}

_CREATE_TASK = re.compile(
    r"(?:create|add|make|open)(?: a| an| new)? task(?: to| for| about|:)?\s*(.+)", re.IGNORECASE
)
_CREATE_TASK_ALT = re.compile(
    r"(?:create|add|make)(?: a| an| new)? to[- ]?do(?: to|:)?\s*(.+)", re.IGNORECASE
)
_MEETING = re.compile(
    r"(?:schedule|book|set up|plan)(?: a| an)? meeting(?: to| about|:)?\s*(.+)", re.IGNORECASE
)
_REMEMBER = re.compile(r"(?:remember|note) that\s+(.+)", re.IGNORECASE)
_COMPLETE_TASK = re.compile(
    r"mark\s+(?:the\s+)?(?:task\s+)?['\"]?(.+?)['\"]?\s+(?:as\s+)?(done|completed|complete|in progress)", re.IGNORECASE
)


def extract_action(text: str, context: Optional[dict[str, Any]] = None) -> Optional[tuple[str, dict[str, Any]]]:
    """Return (action_type, payload) when the message is an explicit action request."""
    text = (text or "").strip()
    context = context or {}
    m = _COMPLETE_TASK.search(text)
    if m:
        return "update_task_status", {"title": m.group(1).strip(), "status": "completed" if m.group(2).lower() in ("done", "completed", "complete") else m.group(2).lower()}
    m = _CREATE_TASK.search(text) or _CREATE_TASK_ALT.search(text)
    if m:
        payload: dict[str, Any] = {"title": m.group(1).strip().strip("'\"").rstrip(".")}
        if context.get("project_id"):
            payload["project_id"] = context["project_id"]
        return "create_task", payload
    m = _MEETING.search(text)
    if m:
        return "schedule_meeting", {"title": m.group(1).strip().strip("'\"").rstrip(".")}
    m = _REMEMBER.search(text)
    if m:
        return "remember", {"content": m.group(1).strip().strip("'\"").rstrip(".")}
    return None


class ActionEngine:
    def requires_permission(self, action_type: str) -> str:
        return _ACTION_PERMISSIONS.get(action_type, "ai:use")

    async def execute(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        action_type: str,
        payload: dict[str, Any],
        permitted: bool,
    ) -> dict[str, Any]:
        permission = self.requires_permission(action_type)
        if not permitted:
            row = AIAction(
                organization_id=organization_id,
                user_id=user.id,
                action_type=action_type,
                status="rejected",
                payload_json=json.dumps(payload, default=str),
                permission_check=permission,
            )
            db.add(row)
            await db.flush()
            return {"status": "rejected", "reason": f"missing_permission:{permission}", "id": row.id}

        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        handler = {
            "create_task": self._create_task,
            "update_task_status": self._update_task_status,
            "schedule_meeting": self._schedule_meeting,
            "remember": self._remember,
            "find_assignee": self._find_assignee,
        }.get(action_type)
        if handler is None:
            row = self._audit(
                db, organization_id, user, action_type, payload, "failed",
                {"error": "unknown_action"}, permission,
            )
            return {"status": "failed", "reason": "unknown_action", "id": row.id}
        try:
            result = await handler(db, organization_id=organization_id, user=user, employee=employee, payload=payload)
            row = self._audit(db, organization_id, user, action_type, payload, "executed", result, permission)
            result["id"] = row.id
            result["status"] = "executed"
            return result
        except Exception as exc:
            row = self._audit(
                db, organization_id, user, action_type, payload, "failed",
                {"error": str(exc)}, permission,
            )
            return {"status": "failed", "reason": str(exc), "id": row.id}

    def _audit(
        self, db, organization_id: str, user: User, action_type: str,
        payload: dict[str, Any], status: str, result: dict[str, Any], permission: str,
    ) -> AIAction:
        row = AIAction(
            organization_id=organization_id,
            user_id=user.id,
            action_type=action_type,
            status=status,
            payload_json=json.dumps(payload, default=str),
            result_json=json.dumps(result, default=str),
            permission_check=permission,
        )
        db.add(row)
        return row

    async def _create_task(self, db, organization_id: str, user: User, employee: Optional[Employee], payload: dict[str, Any]) -> dict[str, Any]:
        from app.work.task_service import task_service

        data = {
            "title": payload.get("title") or payload.get("task") or "",
            "description": payload.get("description"),
            "priority": payload.get("priority", "medium"),
            "status": payload.get("status", "backlog"),
            "project_id": payload.get("project_id"),
            "due_date": payload.get("due_date"),
        }
        if not data["title"]:
            raise ValueError("task title is required")
        if payload.get("assignee_id"):
            data["assignee_id"] = payload["assignee_id"]
        task = await task_service.create(
            db, organization_id=organization_id, data=data, actor=employee
        )
        return {"task_id": task.id, "title": task.title, "url": f"/tasks/{task.id}"}

    async def _update_task_status(self, db, organization_id: str, user: User, employee: Optional[Employee], payload: dict[str, Any]) -> dict[str, Any]:
        from app.work.task_service import task_service

        task_id = payload.get("task_id")
        if not task_id and payload.get("title"):
            tasks = await task_service.list_all(
                db,
                organization_id=organization_id,
                search=payload["title"],
                limit=5,
            )
            tasks = [t for t in tasks if payload["title"].lower() in t.title.lower()]
            if not tasks:
                raise ValueError(
                    f"I couldn't find a task matching '{payload['title']}'. "
                    "Say 'create a task to <title>' and I'll create one instead."
                )
            task_id = tasks[0].id
        task = await task_service.get(
            db, organization_id=organization_id, task_id=task_id or ""
        )
        if task is None:
            raise ValueError("task not found")
        data: dict[str, Any] = {}
        if payload.get("status"):
            data["status"] = payload["status"]
        if payload.get("progress") is not None:
            data["progress"] = payload["progress"]
        if not data:
            raise ValueError("nothing to update")
        task = await task_service.update(
            db, organization_id=organization_id, task=task, data=data, actor=employee
        )
        return {"task_id": task.id, "title": task.title, "status": task.status}

    async def _schedule_meeting(self, db, organization_id: str, user: User, employee: Optional[Employee], payload: dict[str, Any]) -> dict[str, Any]:
        from app.work.meeting_service import meeting_service

        data = {
            "title": payload.get("title") or payload.get("meeting") or "",
            "description": payload.get("description"),
            "meeting_type": payload.get("meeting_type", "team"),
            "start_at": payload.get("start_at"),
            "end_at": payload.get("end_at"),
            "location": payload.get("location"),
            "project_id": payload.get("project_id"),
            "attendee_ids": payload.get("attendee_ids") or [],
        }
        if not data["title"]:
            raise ValueError("meeting title is required")
        meeting = await meeting_service.create(
            db, organization_id=organization_id, data=data, actor=employee
        )
        return {"meeting_id": meeting.id, "title": meeting.title, "url": f"/meetings/{meeting.id}"}

    async def _remember(self, db, organization_id: str, user: User, employee: Optional[Employee], payload: dict[str, Any]) -> dict[str, Any]:
        from app.ai.memory import memory_manager

        content = payload.get("content") or payload.get("fact") or ""
        if not content:
            raise ValueError("memory content is required")
        memory = await memory_manager.remember(
            db,
            organization_id=organization_id,
            content=content,
            memory_type=payload.get("memory_type", "semantic"),
            kind=payload.get("kind", "fact"),
            scope=payload.get("scope", "organization"),
            subject_type=payload.get("subject_type"),
            subject_id=payload.get("subject_id"),
            user_id=user.id,
            source="companion_action",
        )
        return {"memory_id": memory.id if memory else None, "content": content}

    async def _find_assignee(self, db, organization_id: str, user: User, employee: Optional[Employee], payload: dict[str, Any]) -> dict[str, Any]:
        name = (payload.get("name") or "").lower()
        if not name:
            raise ValueError("employee name is required")
        rows = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                    (Employee.full_name.ilike(f"%{name}%"))
                    | (Employee.email.ilike(f"%{name}%")),
                ).limit(5)
            )
        ).scalars().all()
        return {
            "matches": [
                {"employee_id": e.id, "name": e.full_name, "email": e.email} for e in rows
            ]
        }


action_engine = ActionEngine()
