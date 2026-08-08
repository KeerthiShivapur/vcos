"""Phase 8.6 — Organization Digital Twin.

The organization gets a living digital model. The twin continuously reflects
the current state of employees, departments, projects, tasks, meetings,
knowledge, clients(contacts), learning, community, goals, policies and
processes — and executives can ask "show my company" to see it all in one
connected view.

Phase 8.9 — Organizational Memory: everything is searchable ("when did we
decide this?", "who approved the migration?") through events, audit logs,
decisions and AI memory.
"""

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIMemory
from app.models.communication import Community, CommunityPost, InnovationIdea, Recognition
from app.models.department import Department
from app.models.employee import Employee, EmployeeAchievement, EmployeeCertification, EmployeeSkill
from app.models.executive import OrganizationSnapshot, StrategicRisk
from app.models.goal import Goal
from app.models.knowledge import Decision, Document, Policy, SOP, Template, WikiPage
from app.models.meeting import Meeting
from app.models.notification import AuditLog, Event
from app.models.project import Milestone, Project, ProjectMember
from app.models.task import Task

logger = logging.getLogger("vcos.executive.twin")


class DigitalTwin:
    async def describe(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        now = utcnow()

        employees = (await db.execute(
            select(Employee).where(Employee.organization_id == organization_id)
        )).scalars().all()
        active_employees = [e for e in employees if e.status == "active"]

        departments = (await db.execute(
            select(Department).where(Department.organization_id == organization_id)
        )).scalars().all()

        projects = (await db.execute(
            select(Project).where(Project.organization_id == organization_id)
        )).scalars().all()
        active_projects = [p for p in projects if p.status not in ("completed", "cancelled", "archived")]

        tasks = (await db.execute(
            select(Task).where(Task.organization_id == organization_id)
        )).scalars().all()
        open_tasks = [t for t in tasks if t.status not in ("completed", "archived")]
        overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < now.date()]

        meetings = (await db.execute(
            select(Meeting).where(Meeting.organization_id == organization_id)
        )).scalars().all()
        upcoming_meetings = [m for m in meetings if m.start_at and m.start_at >= now and m.status != "cancelled"]
        upcoming_meetings.sort(key=lambda m: m.start_at)
        upcoming_meetings = upcoming_meetings[:8]

        goals = (await db.execute(
            select(Goal).where(Goal.organization_id == organization_id)
        )).scalars().all()

        communities = (await db.execute(
            select(Community).where(Community.organization_id == organization_id)
        )).scalars().all()

        knowledge_counts = {}
        for label, model in (
            ("documents", Document), ("wiki_pages", WikiPage), ("policies", Policy),
            ("sops", SOP), ("templates", Template), ("decisions", Decision),
        ):
            knowledge_counts[label] = (
                await db.execute(select(func.count(model.id)).where(
                    model.organization_id == organization_id
                ))
            ).scalar() or 0

        skills = (
            await db.execute(select(func.count(EmployeeSkill.id)).where(
                EmployeeSkill.organization_id == organization_id
            ))
        ).scalar() or 0
        achievements = (
            await db.execute(select(func.count(EmployeeAchievement.id)).where(
                EmployeeAchievement.organization_id == organization_id
            ))
        ).scalar() or 0
        certifications = (
            await db.execute(select(func.count(EmployeeCertification.id)).where(
                EmployeeCertification.organization_id == organization_id
            ))
        ).scalar() or 0
        ideas = (
            await db.execute(select(func.count(InnovationIdea.id)).where(
                InnovationIdea.organization_id == organization_id
            ))
        ).scalar() or 0
        recognitions = (
            await db.execute(select(func.count(Recognition.id)).where(
                Recognition.organization_id == organization_id
            ))
        ).scalar() or 0
        posts = (
            await db.execute(select(func.count(CommunityPost.id)).where(
                CommunityPost.organization_id == organization_id
            ))
        ).scalar() or 0
        milestones = (
            await db.execute(select(func.count(Milestone.id)).where(
                Milestone.organization_id == organization_id
            ))
        ).scalar() or 0
        open_risks = (await db.execute(
            select(StrategicRisk).where(
                StrategicRisk.organization_id == organization_id, StrategicRisk.status == "open"
            )
        )).scalars().all()

        project_edges = (
            await db.execute(
                select(ProjectMember.employee_id, ProjectMember.project_id).where(
                    ProjectMember.organization_id == organization_id
                )
            )
        ).all()
        by_employee: dict[str, set[str]] = {}
        for employee_id, project_id in project_edges:
            by_employee.setdefault(employee_id, set()).add(project_id)

        top_projects = sorted(
            active_projects, key=lambda p: p.progress or 0, reverse=True
        )[:5]

        entity_counts = {
            "employees": len(employees),
            "employees_active": len(active_employees),
            "departments": len(departments),
            "projects": len(projects),
            "projects_active": len(active_projects),
            "tasks": len(tasks),
            "tasks_open": len(open_tasks),
            "tasks_overdue": len(overdue_tasks),
            "meetings": len(meetings),
            "goals": len(goals),
            "communities": len(communities),
            "knowledge": sum(knowledge_counts.values()),
            "skills": skills,
            "achievements": achievements,
            "certifications": certifications,
            "ideas": ideas,
            "recognitions": recognitions,
            "posts": posts,
            "milestones": milestones,
            "open_risks": len(open_risks),
        }

        twin = {
            "organization_id": organization_id,
            "captured_at": now.isoformat(),
            "people": {
                "total": len(employees),
                "active": len(active_employees),
                "departments": [
                    {"name": d.name, "members": sum(1 for e in employees if e.department_id == d.id)}
                    for d in departments
                ],
            },
            "work": {
                "projects_active": len(active_projects),
                "projects": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "status": p.status,
                        "progress": p.progress,
                        "health": p.health,
                        "members": len(by_employee.get(p.id, set())),
                    }
                    for p in top_projects
                ],
                "tasks_open": len(open_tasks),
                "tasks_overdue": len(overdue_tasks),
                "milestones": milestones,
            },
            "collaboration": {
                "meetings_total": len(meetings),
                "upcoming": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "start_at": m.start_at.isoformat() if m.start_at else None,
                        "meeting_type": m.meeting_type,
                    }
                    for m in upcoming_meetings
                ],
                "communities": len(communities),
                "posts": posts,
            },
            "knowledge": {**knowledge_counts, "skills": skills, "decisions": knowledge_counts["decisions"]},
            "learning": {"achievements": achievements, "certifications": certifications},
            "innovation": {"ideas": ideas, "recognitions": recognitions},
            "strategy": {
                "goals": len(goals),
                "goals_progress": round(sum(g.progress or 0 for g in goals) / len(goals), 1) if goals else 0.0,
            },
            "risks": [
                {"id": r.id, "title": r.title, "level": r.level, "score": r.score}
                for r in sorted(open_risks, key=lambda r: r.score, reverse=True)[:5]
            ],
            "graph": {
                "nodes": entity_counts["employees"] + entity_counts["projects"],
                "project_memberships": len(project_edges),
            },
        }
        return {"entity_counts": entity_counts, "twin": twin}

    async def snapshot(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        payload = await self.describe(db, organization_id=organization_id)
        db.add(OrganizationSnapshot(
            organization_id=organization_id,
            twin_json=json.dumps(payload["twin"]),
            entity_counts_json=json.dumps(payload["entity_counts"]),
            captured_at=payload["twin"]["captured_at"],
        ))
        return payload

    async def search_memory(
        self, db: AsyncSession, *, organization_id: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        q = query.strip().lower()
        results: list[dict[str, Any]] = []
        if not q:
            return results

        def _match(*fields: str | None) -> bool:
            return any(f and q in f.lower() for f in fields)

        events = (await db.execute(
            select(Event).where(Event.organization_id == organization_id)
            .order_by(Event.occurred_at.desc()).limit(500)
        )).scalars().all()
        for ev in events:
            payload = {}
            try:
                payload = json.loads(ev.payload_json) if ev.payload_json else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            text = f"{ev.name} {json.dumps(payload)}"
            if q in text.lower():
                results.append({
                    "source": "event", "id": ev.id, "name": ev.name,
                    "occurred_at": ev.occurred_at.isoformat(),
                    "payload": payload,
                })

        decisions = (await db.execute(
            select(Decision).where(Decision.organization_id == organization_id)
            .order_by(Decision.created_at.desc()).limit(300)
        )).scalars().all()
        for d in decisions:
            if _match(d.title, d.content):
                results.append({
                    "source": "decision", "id": d.id, "name": d.title,
                    "occurred_at": d.created_at.isoformat() if d.created_at else None,
                    "content": (d.content or "")[:500],
                })

        audits = (await db.execute(
            select(AuditLog).where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc()).limit(500)
        )).scalars().all()
        for a in audits:
            details = a.details or {}
            text = f"{a.action} {a.resource_type or ''} {a.actor_email or ''} {json.dumps(details)}"
            if q in text.lower():
                results.append({
                    "source": "audit", "id": a.id, "name": a.action,
                    "occurred_at": a.created_at.isoformat(),
                    "actor": a.actor_email,
                    "details": details,
                })

        memories = (await db.execute(
            select(AIMemory).where(AIMemory.organization_id == organization_id)
            .order_by(AIMemory.created_at.desc()).limit(300)
        )).scalars().all()
        for m in memories:
            if q in (m.content or "").lower():
                results.append({
                    "source": "memory", "id": m.id, "name": m.content[:120],
                    "occurred_at": m.created_at.isoformat() if m.created_at else None,
                    "kind": m.kind,
                })

        results.sort(key=lambda r: r.get("occurred_at") or "", reverse=True)
        return results[:limit]


digital_twin = DigitalTwin()
