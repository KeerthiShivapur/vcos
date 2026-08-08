"""Phase 7.3 — context engine.

Assembles the grounded context bundle for a companion question from live
tenant data: who is asking, what page they are on, which entities the message
mentions, relevant durable memory, and relevant knowledge. The bundle is
passed to the LLM (Groq) and to the local intelligence engine, and recorded
as the message's ``context_json`` for auditability.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory import memory_manager
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.meeting import Meeting
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.user import User


class ContextBundle:
    def __init__(self, blocks: dict[str, Any]) -> None:
        self.blocks = blocks

    def get(self, key: str, default: Any = None) -> Any:
        return self.blocks.get(key, default)

    def is_empty(self) -> bool:
        return not any(self.blocks.values())

    def to_prompt(self) -> str:
        parts: list[str] = []
        for section, payload in self.blocks.items():
            if not payload:
                continue
            if isinstance(payload, list):
                lines = []
                for item in payload:
                    if isinstance(item, dict):
                        lines.append(" - " + " | ".join(f"{k}={v}" for k, v in item.items() if v is not None))
                    else:
                        lines.append(f" - {item}")
                if lines:
                    parts.append(f"## {section}\n" + "\n".join(lines))
            elif isinstance(payload, dict) and payload:
                parts.append(
                    f"## {section}\n" + "\n".join(f" - {k}: {v}" for k, v in payload.items() if v is not None)
                )
        return "\n\n".join(parts)

    def to_json(self) -> str:
        return json.dumps(self.blocks, default=str)[:8000]


class ContextEngine:
    async def build(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: User,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> ContextBundle:
        context = context or {}
        blocks: dict[str, Any] = {}
        org = await db.get(Organization, organization_id)
        if org:
            blocks["organization"] = {"name": org.name, "id": org.id}
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if employee:
            blocks["who"] = {
                "name": employee.full_name,
                "title": employee.designation,
                "email": employee.email,
            }
        page = {k: v for k, v in context.items() if k.endswith("_id") and v}
        if page:
            blocks["page"] = page
        entities = await self._find_entities(db, organization_id, message, context)
        if entities:
            blocks["entities"] = entities
        tasks = await self._my_tasks(db, organization_id, employee)
        if tasks:
            blocks["my_tasks"] = tasks
        meetings = await self._upcoming_meetings(db, organization_id, employee)
        if meetings:
            blocks["my_meetings"] = meetings
        memories = await memory_manager.recall(
            db, organization_id=organization_id, user_id=user.id, text=message, limit=8
        )
        if memories:
            blocks["memories"] = [
                {"type": m.memory_type, "kind": m.kind, "content": m.content, "importance": m.importance}
                for m in memories
            ]
        knowledge = await self._knowledge(db, organization_id, message)
        if knowledge:
            blocks["knowledge"] = knowledge
        return ContextBundle(blocks)

    async def _find_entities(
        self, db: AsyncSession, organization_id: str, message: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        lowered = (message or "").lower()
        for key, target in (("project_id", Project), ("goal_id", Goal), ("meeting_id", Meeting), ("task_id", Task)):
            entity_id = context.get(key)
            row = await db.get(target, entity_id) if entity_id else None
            if row is not None and getattr(row, "organization_id", None) == organization_id:
                found.append(
                    {
                        "kind": key.replace("_id", ""),
                        "id": row.id,
                        "title": getattr(row, "name", None) or getattr(row, "title", None),
                        "status": getattr(row, "status", None),
                    }
                )
                continue
            candidates = (
                await db.execute(
                    select(target)
                    .where(
                        target.organization_id == organization_id,
                        target.status.notin_(("archived", "cancelled")),
                    )
                    .limit(400)
                )
            ).scalars().all()
            title_attr = "name" if key in ("project_id", "goal_id") else "title"
            hits = [c for c in candidates if (getattr(c, title_attr, "") or "").lower() in lowered]
            for hit in hits[:2]:
                found.append(
                    {
                        "kind": key.replace("_id", ""),
                        "id": hit.id,
                        "title": getattr(hit, title_attr, None),
                        "status": getattr(hit, "status", None),
                    }
                )
        return found

    async def _my_tasks(self, db, organization_id: str, employee: Optional[Employee]) -> list[dict[str, Any]]:
        if employee is None:
            return []
        rows = (
            await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == employee.id,
                    Task.status.notin_(("completed", "archived")),
                )
                .order_by(Task.due_date.asc().nulls_last())
                .limit(8)
            )
        ).scalars().all()
        return [
            {"title": t.title, "status": t.status, "priority": t.priority, "due": t.due_date}
            for t in rows
        ]

    async def _upcoming_meetings(self, db, organization_id: str, employee: Optional[Employee]) -> list[dict[str, Any]]:
        if employee is None:
            return []
        rows = (
            await db.execute(
                select(Meeting)
                .join_from(Meeting, MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id)
                .where(
                    Meeting.organization_id == organization_id,
                    MeetingAttendee.employee_id == employee.id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                )
                .order_by(Meeting.start_at.asc().nulls_last())
                .limit(5)
            )
        ).scalars().all()
        return [
            {"title": m.title, "status": m.status, "start": m.start_at, "type": m.meeting_type}
            for m in rows
        ]

    async def _knowledge(self, db, organization_id: str, message: str) -> list[dict[str, Any]]:
        if not message:
            return []
        from app.knowledge.search_service import knowledge_search_service

        try:
            data = await knowledge_search_service.search(
                db, organization_id=organization_id, query=message[:120], mode="hybrid", limit=3
            )
        except Exception:
            return []
        return [
            {"title": r["title"], "type": r["type"], "url": r.get("url"), "summary": (r.get("summary") or "")[:160]}
            for r in data["results"][:3]
        ]


from app.models.meeting import MeetingAttendee  # noqa: E402

context_engine = ContextEngine()
