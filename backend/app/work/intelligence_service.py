"""Work intelligence service — health, prediction, dashboards (Phase 3)."""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.approval import Risk
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.meeting import Meeting, MeetingAttendee
from app.models.project import Milestone, Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot

HEALTH_GOOD = 80
HEALTH_WATCH = 60


class IntelligenceService:
    async def execution_insights(
        self, db: AsyncSession, *, organization_id: str, project_id: Optional[str] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Execution intelligence: overdue, at-risk, stalled, blocked, ready-to-start.

        The dependency graph plus schedule state — the operational picture of
        what is slipping, what is stuck, and what is safe to pick up next.
        """
        now = utcnow()
        tomorrow = now.date() + timedelta(days=1)
        horizon = now.date() + timedelta(days=7)
        stale_cutoff = now - timedelta(days=5)

        stmt = select(Task).where(
            Task.organization_id == organization_id,
            Task.status != "archived",
        )
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        tasks = (await db.execute(stmt)).scalars().all()

        overdue, at_risk, stalled, open_tasks = [], [], [], []
        for t in tasks:
            if t.status == "completed":
                continue
            open_tasks.append(t)
            if t.due_date and t.due_date < tomorrow:
                overdue.append(t)
            elif (
                t.due_date and t.due_date <= horizon
                and (t.status in ("backlog", "todo", "review") or t.progress < 50)
            ):
                at_risk.append(t)
            if t.status in ("in_progress", "review") and t.updated_at and t.updated_at < stale_cutoff:
                stalled.append(t)

        from app.work.dependency_service import dependency_service

        blocked = await dependency_service.blocked_tasks(
            db, organization_id=organization_id, project_id=project_id
        )
        ready = await dependency_service.ready_to_start(
            db, organization_id=organization_id, project_id=project_id, limit=limit
        )
        critical = {}
        if project_id:
            critical = await dependency_service.critical_path(
                db, organization_id=organization_id, project_id=project_id
            )

        def _brief(t: Task) -> dict[str, Any]:
            return {
                "task_id": t.id, "title": t.title, "status": t.status,
                "priority": t.priority, "progress": t.progress,
                "due_date": t.due_date, "estimate_hours": t.estimate_hours,
                "assignee_id": t.assignee_id, "project_id": t.project_id,
                "updated_at": t.updated_at,
            }

        return {
            "project_id": project_id,
            "counts": {
                "open_tasks": len(open_tasks),
                "overdue": len(overdue),
                "at_risk": len(at_risk),
                "stalled": len(stalled),
                "blocked": len(blocked),
                "deeply_blocked": sum(1 for b in blocked if b.get("deeply_blocked")),
                "ready_to_start": len(ready),
                "completed": sum(1 for t in tasks if t.status == "completed"),
                "completion_rate": round(
                    sum(1 for t in tasks if t.status == "completed") * 100 / len(tasks), 1
                ) if tasks else 0.0,
            },
            "overdue": [_brief(t) for t in sorted(overdue, key=lambda t: t.due_date or now.date())[:limit]],
            "at_risk": [_brief(t) for t in sorted(at_risk, key=lambda t: t.due_date or horizon)[:limit]],
            "stalled": [_brief(t) for t in sorted(stalled, key=lambda t: t.updated_at or now)[:limit]],
            "blocked": blocked[:limit],
            "ready_to_start": ready,
            "critical_path": critical,
        }
    async def project_health(self, db: AsyncSession, *, organization_id: str, project_id: str) -> dict[str, Any]:
        project = await db.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            raise ValueError("Project not found")
        counts = dict(
            (await db.execute(
                select(Task.status, func.count(Task.id))
                .where(Task.organization_id == organization_id, Task.project_id == project_id)
                .group_by(Task.status)
            )).all()
        )
        total = sum(counts.values())
        completed = counts.get("completed", 0)
        blocked = counts.get("blocked", 0)
        in_progress = counts.get("in_progress", 0)
        overdue = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.project_id == project_id,
                    Task.due_date.isnot(None),
                    Task.due_date < utcnow(),
                    Task.status.notin_(("completed", "archived")),
                )
            )
        ).scalar() or 0
        milestones = (
            await db.execute(
                select(Milestone).where(
                    Milestone.organization_id == organization_id, Milestone.project_id == project_id
                )
            )
        ).scalars().all()
        overdue_milestones = [m for m in milestones if m.due_date and m.due_date < utcnow().date() and m.status != "completed"]

        progress = int((completed / total) * 100) if total else (project.progress or 0)
        health = HEALTH_GOOD
        signals = []
        if blocked > 0:
            health -= min(30, blocked * 8)
            signals.append(f"{blocked} blocked task(s)")
        if overdue > 0:
            health -= min(25, overdue * 6)
            signals.append(f"{overdue} overdue task(s)")
        if overdue_milestones:
            health -= min(20, len(overdue_milestones) * 10)
            signals.append(f"{len(overdue_milestones)} overdue milestone(s)")
        if project.end_date and utcnow().date() > project.end_date and project.status not in ("completed", "cancelled"):
            health -= 15
            signals.append("past end date")
        if progress >= 90 and completed < total:
            health -= 5
        if progress == 100 and total:
            health = 100
        health = max(0, min(100, health))

        risk_rows = (
            await db.execute(
                select(Risk).where(Risk.organization_id == organization_id, Risk.project_id == project_id, Risk.status != "closed")
            )
        ).scalars().all()
        top_risks = sorted(risk_rows, key=lambda r: r.risk_score, reverse=True)[:5]
        return {
            "project_id": project_id,
            "health": health,
            "status": "good" if health >= HEALTH_GOOD else ("watch" if health >= HEALTH_WATCH else "at_risk"),
            "signals": signals,
            "progress": progress,
            "total_tasks": total,
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "blocked_tasks": blocked,
            "overdue_tasks": overdue,
            "milestones_total": len(milestones),
            "milestones_completed": sum(1 for m in milestones if m.status == "completed"),
            "overdue_milestones": len(overdue_milestones),
            "risks": [
                {
                    "id": r.id, "title": r.title, "risk_score": r.risk_score,
                    "severity": ("critical" if r.risk_score >= 16 else "high" if r.risk_score >= 9 else "medium" if r.risk_score >= 4 else "low"),
                    "status": r.status,
                }
                for r in top_risks
            ],
        }

    async def executive_dashboard(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        projects = (await db.execute(
            select(Project).where(Project.organization_id == organization_id)
        )).scalars().all()
        active_projects = [p for p in projects if p.status not in ("completed", "cancelled")]
        task_total = (
            await db.execute(select(func.count(Task.id)).where(Task.organization_id == organization_id))
        ).scalar() or 0
        task_completed = (
            await db.execute(
                select(func.count(Task.id)).where(Task.organization_id == organization_id, Task.status == "completed")
            )
        ).scalar() or 0
        task_blocked = (
            await db.execute(
                select(func.count(Task.id)).where(Task.organization_id == organization_id, Task.status == "blocked")
            )
        ).scalar() or 0
        meetings_count = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id, Meeting.start_at >= week_ago
                )
            )
        ).scalar() or 0
        overloaded = (
            await db.execute(
                select(func.count(func.distinct(WorkloadSnapshot.employee_id))).where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.period_start >= week_ago,
                    WorkloadSnapshot.is_overloaded.is_(True),
                )
            )
        ).scalar() or 0
        risks_open = (
            await db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id, Risk.status != "closed"
                )
            )
        ).scalar() or 0
        high_risks = (
            await db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id, Risk.status != "closed", Risk.risk_score >= 9
                )
            )
        ).scalar() or 0
        goals = (await db.execute(
            select(Goal).where(Goal.organization_id == organization_id)
        )).scalars().all()
        goals_completed = sum(1 for g in goals if g.status == "completed")
        avg_health = 0
        healths = []
        for p in active_projects[:25]:
            healths.append(await self.project_health(db, organization_id=organization_id, project_id=p.id))
        if healths:
            avg_health = round(sum(h["health"] for h in healths) / len(healths), 1)
        return {
            "projects_total": len(projects),
            "projects_active": len(active_projects),
            "projects_completed": sum(1 for p in projects if p.status == "completed"),
            "avg_project_health": avg_health,
            "project_status": "good" if avg_health >= HEALTH_GOOD else ("watch" if avg_health >= HEALTH_WATCH else "at_risk"),
            "tasks_total": task_total,
            "tasks_completed": task_completed,
            "tasks_blocked": task_blocked,
            "tasks_completion_rate": round((task_completed / task_total) * 100, 1) if task_total else 0.0,
            "meetings_last_7d": meetings_count,
            "overloaded_employees": overloaded,
            "risks_open": risks_open,
            "high_risks": high_risks,
            "goals_total": len(goals),
            "goals_completed": goals_completed,
            "goals_completion_rate": round((goals_completed / len(goals)) * 100, 1) if goals else 0.0,
            "avg_progress": round(sum(p.progress or 0 for p in active_projects) / len(active_projects), 1) if active_projects else 0.0,
        }

    async def my_work(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> dict[str, Any]:
        now = utcnow()
        my_tasks = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id, Task.assignee_id == employee_id
            ).order_by(Task.due_date.asc().nulls_last())
        )).scalars().all()
        open_tasks = [t for t in my_tasks if t.status not in ("completed", "archived")]
        overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < now.date()]
        completed_tasks = [t for t in my_tasks if t.status == "completed"]
        from app.work.workload_service import workload_service

        workload = await workload_service.compute_for_employee(
            db, organization_id=organization_id, employee_id=employee_id
        )
        my_meetings = (await db.execute(
            select(Meeting).join(MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id).where(
                Meeting.organization_id == organization_id,
                MeetingAttendee.employee_id == employee_id,
                Meeting.start_at >= now,
                Meeting.status.in_(("scheduled", "in_progress")),
            ).order_by(Meeting.start_at.asc()).limit(20)
        )).scalars().all()
        my_goals = (await db.execute(
            select(Goal).where(
                Goal.organization_id == organization_id, Goal.owner_id == employee_id
            )
        )).scalars().all()
        return {
            "employee_id": employee_id,
            "tasks": {
                "total": len(open_tasks),
                "completed": len(completed_tasks),
                "overdue": len(overdue_tasks),
                "blocked": sum(1 for t in open_tasks if t.status == "blocked"),
                "in_progress": sum(1 for t in open_tasks if t.status == "in_progress"),
                "estimate_hours": round(sum(t.estimate_hours or 0 for t in open_tasks), 1),
            },
            "workload": workload,
            "upcoming_meetings": len(my_meetings),
            "goals": [
                {"id": g.id, "name": g.name, "status": g.status, "progress": g.progress or 0} for g in my_goals
            ],
            "today_tasks": [
                {"id": t.id, "title": t.title, "status": t.status, "due_date": t.due_date}
                for t in sorted(open_tasks, key=lambda t: t.due_date or now.date())[:10]
            ],
        }

    async def organization_load(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        snapshots = (await db.execute(
            select(WorkloadSnapshot).where(WorkloadSnapshot.organization_id == organization_id)
        )).scalars().all()
        latest: dict[str, WorkloadSnapshot] = {}
        for s in snapshots:
            cur = latest.get(s.employee_id)
            if cur is None or (s.period_start or utcnow()) > (cur.period_start or utcnow()):
                latest[s.employee_id] = s
        rows = list(latest.values())
        overloaded = [s for s in rows if s.is_overloaded]
        under = [s for s in rows if s.utilization < 50]
        return {
            "employees_tracked": len(rows),
            "overloaded": len(overloaded),
            "underutilized": len(under),
            "avg_utilization": round(sum(s.utilization for s in rows) / len(rows), 1) if rows else 0.0,
            "overloaded_employees": [s.employee_id for s in overloaded],
        }


intelligence_service = IntelligenceService()
