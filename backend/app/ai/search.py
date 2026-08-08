"""Phase 7.4 — universal search.

One query, every workspace: employees, knowledge (documents/wiki/policies/
sops/templates/decisions), projects, tasks, meetings, goals and AI memories.
Results are normalized into a single hit shape and ranked by a small
score (field matches weighted) so the companion can cite links to results.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory import memory_manager
from app.models.ai import AIMemory
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.task import Task
from app.schemas.knowledge import entity_url

_ROUTES = {
    "project": "projects",
    "task": "tasks",
    "meeting": "meetings",
    "goal": "goals",
    "employee": "employees",
}


def _hit(kind: str, entity_id: str, title: str, snippet: str, score: float, extra: Optional[dict] = None) -> dict[str, Any]:
    hit = {
        "type": kind,
        "id": entity_id,
        "title": title,
        "snippet": snippet,
        "score": round(score, 3),
    }
    route = _ROUTES.get(kind)
    if route:
        hit["url"] = f"/{route}/{entity_id}"
    elif kind in ("document", "wiki", "policy", "sop", "template", "decision"):
        hit["url"] = entity_url(kind, entity_id)
    else:
        hit["url"] = ""
    if extra:
        hit.update(extra)
    return hit


class UniversalSearch:
    async def search(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        limit: int = 20,
        scopes: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"query": query, "total": 0, "results": []}
        lowered = query.lower()
        terms = [t for t in lowered.split() if len(t) >= 2]
        hits: list[dict[str, Any]] = []
        if not scopes or "employees" in scopes:
            hits.extend(await self._employees(db, organization_id, lowered, terms))
        if not scopes or "knowledge" in scopes:
            hits.extend(await self._knowledge(db, organization_id, lowered, terms))
        if not scopes or "projects" in scopes:
            hits.extend(await self._projects(db, organization_id, lowered, terms))
        if not scopes or "tasks" in scopes:
            hits.extend(await self._tasks(db, organization_id, lowered, terms))
        if not scopes or "meetings" in scopes:
            hits.extend(await self._meetings(db, organization_id, lowered, terms))
        if not scopes or "goals" in scopes:
            hits.extend(await self._goals(db, organization_id, lowered, terms))
        if not scopes or "memories" in scopes:
            hits.extend(await self._memories(db, organization_id, lowered, terms))
        hits.sort(key=lambda h: h["score"], reverse=True)
        return {"query": query, "total": len(hits), "results": hits[:limit]}

    async def _employees(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        filters = [Employee.organization_id == organization_id, Employee.status == "active"]
        if terms:
            like = [Employee.first_name.ilike(f"%{t}%") for t in terms]
            like.append(Employee.last_name.ilike(f"%{lowered}%"))
            like.append(Employee.email.ilike(f"%{lowered}%"))
            like.append(Employee.designation.ilike(f"%{lowered}%"))
            filters.append(or_(*like))
        rows = (
            await db.execute(select(Employee).where(*filters).limit(25))
        ).scalars().all()
        hits = []
        for emp in rows:
            score = 2.0 if lowered in emp.full_name.lower() else 1.0
            if lowered in (emp.email or "").lower():
                score += 0.5
            if lowered in (emp.designation or "").lower():
                score += 0.5
            hits.append(
                _hit(
                    "employee", emp.id, emp.full_name,
                    emp.designation or emp.email or "",
                    score,
                    {"email": emp.email},
                )
            )
        return hits

    async def _knowledge(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        from app.models.knowledge import Decision, Document, Policy, SOP, Template, WikiPage

        table_info = [
            ("document", Document),
            ("wiki", WikiPage),
            ("policy", Policy),
            ("sop", SOP),
            ("template", Template),
            ("decision", Decision),
        ]
        hits = []
        for kind, model in table_info:
            if not hasattr(model, "title") or not hasattr(model, "status"):
                continue
            filters = [model.organization_id == organization_id, model.status == "published"]
            like = [model.title.ilike(f"%{lowered}%")]
            like.append(model.description.ilike(f"%{lowered}%"))
            like.append(model.content.ilike(f"%{lowered}%"))
            filters.append(or_(*like))
            rows = (
                await db.execute(select(model).where(*filters).limit(10))
            ).scalars().all()
            for row in rows:
                score = 3.0 if lowered in (row.title or "").lower() else 1.0
                snippet = (row.summary or row.description or (row.content or "")[:180] or "").strip()
                hits.append(_hit(kind, row.id, row.title, snippet[:200], score))
        return hits

    async def _projects(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        rows = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    or_(Project.name.ilike(f"%{lowered}%"), Project.code.ilike(f"%{lowered}%")),
                ).limit(10)
            )
        ).scalars().all()
        return [
            _hit(
                "project", p.id, p.name,
                f"{p.code} · {p.status}" if p.code else p.status,
                3.0 if lowered in p.name.lower() else 1.5,
                {"status": p.status},
            )
            for p in rows
        ]

    async def _tasks(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        rows = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    or_(
                        Task.title.ilike(f"%{lowered}%"),
                        Task.description.ilike(f"%{lowered}%"),
                    ),
                ).limit(10)
            )
        ).scalars().all()
        return [
            _hit(
                "task", t.id, t.title,
                (t.description or "")[:200] or f"{t.status} · {t.priority}",
                3.0 if lowered in t.title.lower() else 1.5,
                {"status": t.status, "priority": t.priority},
            )
            for t in rows
        ]

    async def _meetings(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        rows = (
            await db.execute(
                select(Meeting).where(
                    Meeting.organization_id == organization_id,
                    Meeting.title.ilike(f"%{lowered}%"),
                ).limit(10)
            )
        ).scalars().all()
        return [
            _hit(
                "meeting", m.id, m.title,
                f"{m.meeting_type} · {m.status} · {m.start_at.isoformat() if m.start_at else 'TBD'}",
                3.0,
                {"status": m.status, "meeting_type": m.meeting_type},
            )
            for m in rows
        ]

    async def _goals(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        rows = (
            await db.execute(
                select(Goal).where(
                    Goal.organization_id == organization_id,
                    Goal.name.ilike(f"%{lowered}%"),
                ).limit(10)
            )
        ).scalars().all()
        return [
            _hit("goal", g.id, g.name, f"{g.status} · {g.progress}%", 3.0, {"status": g.status})
            for g in rows
        ]

    async def _memories(self, db, organization_id: str, lowered: str, terms: list[str]) -> list[dict]:
        rows = await memory_manager.recall(
            db, organization_id=organization_id, text=lowered, limit=10
        )
        return [
            _hit(
                "memory", m.id, f"{m.memory_type} · {m.kind}",
                (m.content or "")[:200],
                2.0,
                {"memory_type": m.memory_type, "importance": m.importance},
            )
            for m in rows
        ]


universal_search = UniversalSearch()
