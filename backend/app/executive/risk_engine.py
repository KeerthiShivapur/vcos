"""Phase 8.4 — Strategic Risk Engine.

AI constantly detects risks across the organization: project delay, key
employee dependency, overloaded teams, burnout signals, meeting overload,
knowledge gaps, missed deadlines, stalled projects and customer pressure.

Each risk carries probability x impact -> score, level, affected teams,
recommended actions and a traceable evidence chain, and persists to
``strategic_risks`` for the executive dashboard and alerts.
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Risk
from app.models.employee import Employee
from app.models.executive import StrategicRisk
from app.models.knowledge import Document, WikiPage
from app.models.meeting import Meeting, MeetingAttendee
from app.models.project import Milestone, Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

logger = logging.getLogger("vcos.executive.risk")


def _level(score: float) -> str:
    if score >= 0.7:
        return "critical"
    if score >= 0.45:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


class RiskEngine:
    async def detect_all(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        risks.extend(await self._project_delay_risks(db, organization_id=organization_id))
        risks.extend(await self._key_dependency_risks(db, organization_id=organization_id))
        risks.extend(await self._team_overload_risks(db, organization_id=organization_id))
        risks.extend(await self._burnout_risks(db, organization_id=organization_id))
        risks.extend(await self._meeting_overload_risks(db, organization_id=organization_id))
        risks.extend(await self._knowledge_gap_risks(db, organization_id=organization_id))
        risks.extend(await self._stalled_projects_risks(db, organization_id=organization_id))
        risks.extend(await self._missed_deadline_risks(db, organization_id=organization_id))
        risks.sort(key=lambda r: r["score"], reverse=True)
        return risks

    async def _project_delay_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.status.in_(("active", "paused")),
            )
        )).scalars().all()
        results = []
        now = utcnow().date()
        for p in projects:
            signals: list[str] = []
            probability = 0.2
            impact = 0.6
            overdue_tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.project_id == p.id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_(("completed", "archived")),
                ))
            ).scalar() or 0
            blocked_tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.project_id == p.id,
                    Task.status == "blocked",
                ))
            ).scalar() or 0
            overdue_milestones = (await db.execute(
                select(func.count(Milestone.id)).where(
                    Milestone.organization_id == organization_id,
                    Milestone.project_id == p.id,
                    Milestone.due_date.isnot(None),
                    Milestone.due_date < now,
                    Milestone.status != "completed",
                ))
            ).scalar() or 0
            if overdue_tasks:
                probability += 0.15
                signals.append(f"{overdue_tasks} overdue task(s)")
            if blocked_tasks:
                probability += 0.15
                signals.append(f"{blocked_tasks} blocked task(s)")
            if overdue_milestones:
                probability += 0.2
                signals.append(f"{overdue_milestones} overdue milestone(s)")
            if p.end_date and p.end_date < now:
                probability += 0.15
                signals.append("past planned end date")
            if p.health == "critical":
                probability += 0.15
                signals.append("project flagged critical")
            elif p.health == "at_risk":
                probability += 0.1
                signals.append("project flagged at risk")
            probability = min(0.95, probability)
            if signals:
                score = round(probability * impact, 3)
                results.append(self._build(
                    db, organization_id=organization_id,
                    kind="project_delay", title=f"Project '{p.name}' is at risk of missing its deadline",
                    description="The project has " + ", ".join(signals) + ".",
                    probability=probability, impact=impact, score=score,
                    subject_type="project", subject_id=p.id, subject_name=p.name,
                    affected_teams=[p.department_id] if p.department_id else [],
                    recommended_actions=[
                        "Assign additional engineers to the project",
                        "Re-sequence the remaining milestones",
                        "Hold a focused review to unblock critical tasks",
                    ],
                    evidence={"signals": signals, "progress": p.progress, "status": p.status},
                ))
        return results

    async def _key_dependency_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        employees = (await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id, Employee.status == "active"
            )
        )).scalars().all()
        results = []
        for e in employees:
            open_tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == e.id,
                    Task.status.notin_(("completed", "archived")),
                ))
            ).scalar() or 0
            if open_tasks < 6:
                continue
            projects = (
                await db.execute(
                    select(func.count(func.distinct(Task.project_id))).where(
                        Task.organization_id == organization_id,
                        Task.assignee_id == e.id,
                        Task.status.notin_(("completed", "archived")),
                        Task.project_id.isnot(None),
                    )
                )
            ).scalar() or 0
            if projects < 2:
                continue
            name = e.display_name or f"{e.first_name} {e.last_name or ''}".strip()
            score = round(min(0.9, 0.4 + open_tasks * 0.01 + projects * 0.05) * 0.75, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="key_dependency",
                title=f"Key dependency on {name} ({open_tasks} open tasks across {projects} projects)",
                description=f"{name} is the assignee of {open_tasks} open tasks across {projects} projects. Their absence would stall critical delivery.",
                probability=min(0.85, 0.4 + open_tasks * 0.01), impact=0.75, score=score,
                subject_type="employee", subject_id=e.id, subject_name=name,
                affected_teams=[e.department_id] if e.department_id else [],
                recommended_actions=[
                    "Redistribute a portion of their workload",
                    "Assign a backup owner to each critical project",
                    "Identify and record their unique knowledge in the wiki",
                ],
                evidence={"open_tasks": open_tasks, "projects": projects},
            ))
        return results

    async def _team_overload_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        week_ago = utcnow() - timedelta(days=7)
        snapshots = (await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == organization_id,
                WorkloadSnapshot.period_start >= week_ago,
            )
        )).scalars().all()
        by_employee: dict[str, int] = {}
        for s in snapshots:
            if s.is_overloaded:
                by_employee[s.employee_id] = by_employee.get(s.employee_id, 0) + 1
        if not by_employee:
            return []
        employees = {
            e.id: e
            for e in (await db.execute(select(Employee).where(Employee.id.in_(list(by_employee.keys())))))
            .scalars().all()
        }
        results = []
        for employee_id, count in sorted(by_employee.items(), key=lambda x: x[1], reverse=True)[:5]:
            e = employees.get(employee_id)
            if e is None:
                continue
            name = e.display_name or f"{e.first_name} {e.last_name or ''}".strip()
            ratio = count / 7
            score = round(min(0.9, ratio) * 0.7, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="overload",
                title=f"Team overload signal: {name} is overloaded",
                description=f"Workload snapshots flagged {name} as overloaded {count} time(s) in the last 7 days.",
                probability=min(0.85, ratio), impact=0.7, score=score,
                subject_type="employee", subject_id=employee_id, subject_name=name,
                affected_teams=[e.department_id] if e.department_id else [],
                recommended_actions=[
                    "Redistribute tasks away from this employee",
                    "Review and reprioritize their current workload",
                ],
                evidence={"overloaded_days": count},
            ))
        return results

    async def _burnout_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        month_ago = utcnow() - timedelta(days=30)
        tasks = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.status.in_(("in_progress", "review", "todo")),
                Task.created_at >= month_ago,
            )
        )).scalars().all()
        by_employee: dict[str, int] = {}
        for t in tasks:
            if t.assignee_id:
                by_employee[t.assignee_id] = by_employee.get(t.assignee_id, 0) + 1
        results = []
        for employee_id, count in sorted(by_employee.items(), key=lambda x: x[1], reverse=True)[:5]:
            if count < 8:
                continue
            e = await db.get(Employee, employee_id)
            if e is None:
                continue
            name = e.display_name or f"{e.first_name} {e.last_name or ''}".strip()
            score = round(min(0.9, count * 0.03) * 0.65, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="burnout",
                title=f"Burnout signal: {name} carries {count} active tasks",
                description=f"{name} has been assigned {count} active tasks in the last 30 days — a heavy sustained workload.",
                probability=min(0.8, count * 0.03), impact=0.65, score=score,
                subject_type="employee", subject_id=employee_id, subject_name=name,
                affected_teams=[e.department_id] if e.department_id else [],
                recommended_actions=[
                    "Review workload balance and redistribute tasks",
                    "Check in with the employee about capacity",
                ],
                evidence={"active_tasks_30d": count},
            ))
        return results

    async def _meeting_overload_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        week_ago = utcnow() - timedelta(days=7)
        attendees = (await db.execute(
            select(MeetingAttendee.employee_id, func.count(MeetingAttendee.id)).join(
                Meeting, Meeting.id == MeetingAttendee.meeting_id
            ).where(
                Meeting.organization_id == organization_id,
                Meeting.start_at >= week_ago,
                Meeting.status != "cancelled",
            ).group_by(MeetingAttendee.employee_id)
        )).all()
        results = []
        for employee_id, count in attendees:
            if count < 10:
                continue
            e = await db.get(Employee, employee_id)
            if e is None:
                continue
            name = e.display_name or f"{e.first_name} {e.last_name or ''}".strip()
            score = round(min(0.85, count * 0.03) * 0.6, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="meeting_overload",
                title=f"Meeting overload: {name} attended {count} meetings this week",
                description=f"{name} was invited to {count} meetings in the last 7 days, leaving little focus time.",
                probability=min(0.8, count * 0.03), impact=0.6, score=score,
                subject_type="employee", subject_id=employee_id, subject_name=name,
                affected_teams=[e.department_id] if e.department_id else [],
                recommended_actions=[
                    "Cut or merge low-value recurring meetings",
                    "Introduce async updates to free focus time",
                ],
                evidence={"meetings_7d": count},
            ))
        return results

    async def _knowledge_gap_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.status.in_(("active", "paused", "draft")),
            )
        )).scalars().all()
        results = []
        for p in projects[:10]:
            docs = (
                await db.execute(select(func.count(Document.id)).where(
                    Document.organization_id == organization_id,
                    Document.project_id == p.id,
                    Document.status == "published",
                ))
            ).scalar() or 0
            wikis = (
                await db.execute(select(func.count(WikiPage.id)).where(
                    WikiPage.organization_id == organization_id,
                    WikiPage.project_id == p.id,
                    WikiPage.status == "published",
                ))
            ).scalar() or 0
            tasks = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.project_id == p.id
                ))
            ).scalar() or 0
            if docs + wikis == 0 and tasks >= 5:
                score = round(0.5 * 0.55, 3)
                results.append(self._build(
                    db, organization_id=organization_id,
                    kind="knowledge_gap",
                    title=f"Knowledge gap: project '{p.name}' has no documentation",
                    description=f"The project has {tasks} tasks but no published documents or wiki pages, so critical knowledge is at risk.",
                    probability=0.5, impact=0.55, score=score,
                    subject_type="project", subject_id=p.id, subject_name=p.name,
                    affected_teams=[p.department_id] if p.department_id else [],
                    recommended_actions=[
                        "Create a project wiki page and onboarding docs",
                        "Assign a documentation owner for the project",
                    ],
                    evidence={"tasks": tasks, "documents": docs, "wiki_pages": wikis},
                ))
        return results

    async def _stalled_projects_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        month_ago = utcnow() - timedelta(days=30)
        projects = (await db.execute(
            select(Project).where(
                Project.organization_id == organization_id, Project.status == "active"
            )
        )).scalars().all()
        results = []
        for p in projects[:10]:
            recent = (
                await db.execute(select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.project_id == p.id,
                    Task.updated_at >= month_ago,
                ))
            ).scalar() or 0
            if recent > 0:
                continue
            score = round(0.55 * 0.5, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="stalled_project",
                title=f"Project '{p.name}' appears stalled",
                description=f"No task activity in the last 30 days while the project is marked active.",
                probability=0.55, impact=0.5, score=score,
                subject_type="project", subject_id=p.id, subject_name=p.name,
                affected_teams=[p.department_id] if p.department_id else [],
                recommended_actions=[
                    "Confirm the project status and reprioritize",
                    "Assign an owner and define the next milestone",
                ],
                evidence={"last_task_activity_days": 30, "progress": p.progress},
            ))
        return results

    async def _missed_deadline_risks(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        week_ahead = utcnow().date() + timedelta(days=7)
        tasks = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.due_date.isnot(None),
                Task.due_date >= utcnow().date(),
                Task.due_date <= week_ahead,
                Task.status.notin_(("completed", "archived")),
                Task.priority.in_(("high", "critical")),
            )
        )).scalars().all()
        results = []
        for t in tasks[:10]:
            if (t.progress or 0) >= 70:
                continue
            days_left = (t.due_date - utcnow().date()).days
            probability = min(0.9, 0.3 + (0.1 * max(0, (70 - (t.progress or 0))) / 10) + max(0, 0.15 - days_left * 0.02))
            score = round(probability * 0.55, 3)
            results.append(self._build(
                db, organization_id=organization_id,
                kind="missed_deadline",
                title=f"High-priority task '{t.title}' may miss its deadline",
                description=f"The task is due in {days_left} day(s) at {t.progress or 0}% progress.",
                probability=probability, impact=0.55, score=score,
                subject_type="task", subject_id=t.id, subject_name=t.title,
                affected_teams=[],
                recommended_actions=[
                    "Add support or reprioritize the task",
                    "Check blockers with the assignee",
                ],
                evidence={"due_in_days": days_left, "progress": t.progress or 0},
            ))
        return results

    def _build(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "organization_id": kwargs["organization_id"],
            "kind": kwargs["kind"],
            "title": kwargs["title"],
            "description": kwargs["description"],
            "probability": round(kwargs["probability"], 2),
            "impact": round(kwargs["impact"], 2),
            "score": kwargs["score"],
            "level": _level(kwargs["score"]),
            "subject_type": kwargs.get("subject_type"),
            "subject_id": kwargs.get("subject_id"),
            "subject_name": kwargs.get("subject_name"),
            "affected_teams": kwargs.get("affected_teams", []),
            "recommended_actions": kwargs.get("recommended_actions", []),
            "evidence": kwargs.get("evidence", {}),
        }
        payload["explanation"] = (
            f"Probability {payload['probability']:.0%} x impact {payload['impact']:.0%} "
            f"= score {payload['score']:.2f} ({payload['level']}). "
            + (" ".join(payload["evidence"].get("signals", []) or []) if isinstance(payload["evidence"].get("signals"), list) else "")
        )
        return payload

    async def persist(self, db: AsyncSession, *, organization_id: str, risks: list[dict[str, Any]]) -> int:
        active = (
            await db.execute(select(StrategicRisk).where(
                StrategicRisk.organization_id == organization_id,
                StrategicRisk.status == "open",
            ))
        ).scalars().all()
        active_by_key = {(r.kind, r.subject_id or ""): r for r in active}
        new_ids = {(r["kind"], r.get("subject_id") or ""): r for r in risks}
        created = 0
        for key, payload in new_ids.items():
            existing = active_by_key.get(key)
            if existing is not None:
                existing.score = payload["score"]
                existing.level = payload["level"]
                existing.probability = payload["probability"]
                existing.impact = payload["impact"]
                existing.title = payload["title"]
                existing.description = payload["description"]
                existing.affected_teams_json = json.dumps(payload["affected_teams"])
                existing.recommended_actions_json = json.dumps(payload["recommended_actions"])
                existing.evidence_json = json.dumps(payload["evidence"])
                continue
            db.add(StrategicRisk(
                organization_id=organization_id,
                kind=payload["kind"],
                title=payload["title"],
                description=payload["description"],
                probability=payload["probability"],
                impact=payload["impact"],
                score=payload["score"],
                level=payload["level"],
                subject_type=payload.get("subject_type"),
                subject_id=payload.get("subject_id"),
                subject_name=payload.get("subject_name"),
                affected_teams_json=json.dumps(payload["affected_teams"]),
                recommended_actions_json=json.dumps(payload["recommended_actions"]),
                evidence_json=json.dumps(payload["evidence"]),
            ))
            created += 1
        return created


risk_engine = RiskEngine()
