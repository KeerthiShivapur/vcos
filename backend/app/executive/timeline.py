"""Phase 8.8 — Organization Timeline.

Everything the company does is recorded: hiring, promotions, projects,
meetings, knowledge, policies, learning, incidents, releases, achievements
and community activity. The timeline merges the event stream, audit log,
employee timelines, project timelines and knowledge activity into one
chronological view so AI (and executives) understand the company's history.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import EmployeeTimeline
from app.models.knowledge import Decision, Document, Policy, WikiPage
from app.models.meeting import Meeting
from app.models.notification import AuditLog, Event
from app.models.project import ProjectTimeline


class OrganizationTimeline:
    async def get(self, db: AsyncSession, *, organization_id: str, limit: int = 60) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []

        events = (await db.execute(
            select(Event).where(Event.organization_id == organization_id)
            .order_by(Event.occurred_at.desc()).limit(400)
        )).scalars().all()
        for ev in events:
            payload = {}
            try:
                payload = json.loads(ev.payload_json) if ev.payload_json else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            entries.append({
                "source": "event",
                "kind": ev.name,
                "title": self._event_title(ev.name, payload),
                "occurred_at": ev.occurred_at.isoformat(),
                "payload": {k: v for k, v in payload.items() if isinstance(v, (str, int, float, bool)) or v is None},
            })

        audits = (await db.execute(
            select(AuditLog).where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc()).limit(400)
        )).scalars().all()
        for a in audits:
            details = a.details or {}
            entries.append({
                "source": "audit",
                "kind": "action",
                "title": f"{a.action.replace('.', ' ').replace('_', ' ').title()} — {a.actor_email or 'system'}",
                "occurred_at": a.created_at.isoformat(),
                "payload": {k: v for k, v in details.items() if isinstance(v, (str, int, float, bool)) or v is None},
            })

        for model, kind, title_attr in (
            (EmployeeTimeline, "employee", "title"),
            (ProjectTimeline, "project", "title"),
        ):
            rows = (await db.execute(
                select(model).where(model.organization_id == organization_id)
                .order_by(model.occurred_at.desc()).limit(300)
            )).scalars().all()
            for r in rows:
                meta = {}
                if hasattr(r, "meta") and r.meta:
                    meta = r.meta if isinstance(r.meta, dict) else {}
                entries.append({
                    "source": kind,
                    "kind": r.kind,
                    "title": getattr(r, title_attr) or r.kind,
                    "occurred_at": r.occurred_at.isoformat(),
                    "payload": meta,
                })

        meetings = (await db.execute(
            select(Meeting).where(
                Meeting.organization_id == organization_id,
                Meeting.status == "completed",
            ).order_by(Meeting.end_at.desc()).limit(150)
        )).scalars().all()
        for m in meetings:
            entries.append({
                "source": "meeting",
                "kind": "meeting_completed",
                "title": f"Meeting completed: {m.title}",
                "occurred_at": (m.end_at or m.created_at).isoformat(),
                "payload": {"meeting_type": m.meeting_type, "has_summary": bool(m.ai_summary)},
            })

        for model, source, statuses in (
            (Document, "document", ("published",)),
            (WikiPage, "wiki", ("published",)),
            (Policy, "policy", ("published", "active")),
            (Decision, "decision", ()),
        ):
            rows = (await db.execute(
                select(model).where(model.organization_id == organization_id)
                .order_by(model.created_at.desc()).limit(200)
            )).scalars().all()
            for r in rows:
                if statuses and getattr(r, "status", None) not in statuses:
                    continue
                entries.append({
                    "source": source,
                    "kind": f"{source}_created",
                    "title": f"{source.replace('_', ' ').title()} created: {r.title}",
                    "occurred_at": (r.created_at or r.updated_at).isoformat() if r.created_at else None,
                    "payload": {},
                })

        entries = [e for e in entries if e["occurred_at"]]
        entries.sort(key=lambda e: e["occurred_at"], reverse=True)
        return {"total": len(entries), "entries": entries[:limit]}

    @staticmethod
    def _event_title(name: str, payload: dict[str, Any]) -> str:
        label = name.replace(".", " ").replace("_", " ").title()
        subject = (
            payload.get("title")
            or payload.get("name")
            or payload.get("entity_type")
            or payload.get("user_id")
            or payload.get("employee_id")
        )
        if subject:
            return f"{label}: {subject}"
        return label


organization_timeline = OrganizationTimeline()
